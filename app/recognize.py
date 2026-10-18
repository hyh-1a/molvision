"""Structure-image recognition via DECIMER, with figure segmentation.

A single uploaded figure may contain several structures (papers usually do).
We split it first, recognise each crop, and return a list. All TensorFlow
inference is serialised through ``_INFER_LOCK`` (the graph is not thread-safe
for our use), and results are memoised by image SHA-256.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import tempfile
import threading
from collections import OrderedDict

from app.segment import looks_like_structure, segment_image

_MODEL = None
_LOAD_LOCK = threading.Lock()
_INFER_LOCK = threading.Lock()

_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 128


class RecognizerUnavailable(RuntimeError):
    """Raised when the recognition backend cannot be loaded."""


def model_loaded() -> bool:
    """True once the TensorFlow model has actually been loaded."""
    return _MODEL is not None


def _get_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    with _LOAD_LOCK:
        if _MODEL is None:
            try:
                # Importing DECIMER triggers weight download/load on first use.
                from DECIMER import predict_SMILES
            except Exception as exc:  # pragma: no cover - env dependent
                raise RecognizerUnavailable(f"DECIMER 不可用: {exc}") from exc
            _MODEL = predict_SMILES
    return _MODEL


def _cache_get(key: str) -> dict | None:
    with _CACHE_LOCK:
        value = _CACHE.get(key)
        if value is not None:
            _CACHE.move_to_end(key)
        return value


def _cache_put(key: str, value: dict) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = value
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _predict(image, hand_drawn: bool = False) -> str:
    """Run DECIMER on one PIL image and return the raw SMILES."""
    predict = _get_model()
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        image.save(path, format="PNG")
        with _INFER_LOCK:
            raw = predict(path, hand_drawn=True) if hand_drawn else predict(path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    return (raw or "").strip()


def _thumb(image, size: int = 240) -> str:
    thumb = image.copy()
    thumb.thumbnail((size, size))
    buf = io.BytesIO()
    thumb.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _looks_like_junk(smiles: str) -> bool:
    """Reject decoder degenerations such as 'CC.CC.CC...' repeated to the limit."""
    parts = smiles.split(".")
    if len(parts) > 6:
        return True
    from collections import Counter

    if len(parts) >= 4 and Counter(parts).most_common(1)[0][1] >= 4:
        return True
    if _long_alkane(smiles):
        return True
    return len(smiles) > 220 and len(parts) > 4


def _long_alkane(smiles: str) -> bool:
    """Long unbranched alkane chains are the classic 302-token degeneration."""
    return smiles.count("C") >= 25 and smiles.count("(") <= 2 and smiles.count("c") == 0


def _atom_symbols(smiles: str) -> set[str]:
    from rdkit import Chem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return set()
    return {a.GetSymbol() for a in mol.GetAtoms()}


def _has_suspicious_halogen(smiles: str) -> bool:
    """I/Br together with S/P is almost always a misread heteroatom label.

    DECIMER turns the glyphs "S"/"P" at a fragment edge into iodine, which is
    exactly the failure seen when a molecule is split at its central atom.
    """
    syms = _atom_symbols(smiles)
    return bool(syms & {"I", "Br"}) and bool(syms & {"S", "P"})


def _has_halogen(smiles: str) -> bool:
    return bool(_atom_symbols(smiles) & {"I", "Br"})


def _has_suspicious_metal(smiles: str) -> bool:
    """Pb/Sn/Bi/... at a substituent position is usually a misread "Ph"."""
    return bool(_atom_symbols(smiles) & {"Pb", "Sn", "Bi", "Hg", "Cd",
                                         "Tl", "U", "Ge", "Sb"})


def _has_stereo(smiles: str) -> bool:
    from rdkit import Chem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return False
    if any(a.GetChiralTag() != Chem.ChiralType.CHI_UNSPECIFIED for a in mol.GetAtoms()):
        return True
    return any(b.GetStereo() != Chem.BondStereo.STEREONONE for b in mol.GetBonds())


def _parse_candidate(raw: str):
    """Parse + canonicalise a raw prediction; None means unusable."""
    import re

    from rdkit import Chem

    from app.chem import expand_abbreviations, normalize_markush

    # "Ph" drawn as text is often read as lead/tin ([Pb]/[Sn]); repair it.
    raw = re.sub(r"\[Pb\]|\[Sn\]", "[Ph]", raw)

    attempts = [
        expand_abbreviations(raw),
        expand_abbreviations(normalize_markush(raw)),
        raw,
        normalize_markush(raw),
    ]

    mol = None
    seen = set()
    for candidate in attempts:
        if candidate in seen:
            continue
        seen.add(candidate)
        mol = Chem.MolFromSmiles(candidate)
        if mol is not None:
            break
    if mol is None:
        return None

    # Deuterium / tritium labels are read as ²H/³H. Users draw "D" to mean a
    # hydrogen position, so fold hydrogen isotopes back to plain H.
    if any(a.GetAtomicNum() == 1 and a.GetIsotope() for a in mol.GetAtoms()):
        try:
            for atom in mol.GetAtoms():
                if atom.GetAtomicNum() == 1:
                    atom.SetIsotope(0)
            mol = Chem.RemoveHs(mol)
            Chem.SanitizeMol(mol)
        except Exception:
            pass

    canonical = Chem.MolToSmiles(mol, canonical=True)
    if _looks_like_junk(canonical):
        return None
    return mol, canonical


def _recognize_crops(image, force_single: bool = False) -> list[dict]:
    from rdkit import Chem

    if force_single:
        crops = [{"image": image, "bbox": [0, 0, image.width, image.height]}]
    else:
        crops = segment_image(image)
        # A single structure with generous margins can be over-split into fragments;
        # if most crops do not look structure-like, treat the image as one drawing.
        if len(crops) > 1:
            good = sum(1 for c in crops if looks_like_structure(c["image"]))
            if good < max(2, len(crops) // 2):
                crops = [{"image": image, "bbox": [0, 0, image.width, image.height]}]

    structures = []
    for idx, crop in enumerate(crops):
        item = {
            "index": idx,
            "bbox": crop["bbox"],
            "thumb": _thumb(crop["image"]),
            "ok": False,
        }
        try:
            if not looks_like_structure(crop["image"]):
                raise ValueError("该区域不像化学结构（可能是文字/箭头）")
            raw = _predict(crop["image"])
            parsed = _parse_candidate(raw) if raw else None
            if parsed is None:
                # Printed model failed: try the hand-drawn weights, already loaded.
                alt = _predict(crop["image"], hand_drawn=True)
                parsed = _parse_candidate(alt) if alt else None
                if parsed is not None:
                    raw = alt
            if parsed is None:
                raise ValueError(
                    f"识别结果无法解析或疑似噪声: {raw}" if raw else "未能识别出结构式"
                )
            mol, canonical = parsed
            if _has_suspicious_halogen(canonical) or _has_suspicious_metal(canonical):
                # Retry with the hand-drawn weights; accept only if the
                # spurious element disappears.
                alt = _predict(crop["image"], hand_drawn=True)
                alt_parsed = _parse_candidate(alt) if alt else None
                if alt_parsed and not _has_suspicious_halogen(alt_parsed[1]) \
                        and not _has_suspicious_metal(alt_parsed[1]):
                    mol, canonical = alt_parsed
                    raw = alt
            try:
                inchikey = Chem.MolToInchiKey(mol)
            except Exception:
                inchikey = ""
            item.update(ok=True, smiles=canonical, raw_smiles=raw,
                        inchikey=inchikey, stereo=_has_stereo(canonical))
        except Exception as exc:  # noqa: BLE001 - report per-structure failures
            item["error"] = str(exc)
        structures.append(item)
    return _merge_split_fragments(image, crops, structures)


def _merge_split_fragments(image, crops, structures):
    """Rejoin a molecule that was cut into two horizontal halves.

    RDKit/ChemDraw labels have a white halo; a central S/P label can split one
    molecule into two crops. When the two halves sit side by side and a
    heteroatom-hallucination is present, recognise the union instead.
    """
    from rdkit import Chem

    if len(crops) != 2 or len(structures) != 2:
        return structures
    a, b = crops[0]["bbox"], crops[1]["bbox"]
    overlap_y = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    if overlap_y < 0.5 * min(a[3], b[3]):
        return structures
    gap = max(a[0], b[0]) - min(a[0] + a[2], b[0] + b[2])
    # The gap between two halves of one molecule includes the central label
    # and its halo, which can be ~15% of the image width.
    limit = max(80, int(0.55 * min(a[2], b[2])))
    if gap < 0 or gap > limit:
        return structures
    ok_structs = [s for s in structures if s.get("ok")]
    halogen = any(_has_halogen(s["smiles"]) for s in ok_structs)
    identical = (len(ok_structs) == 2
                 and ok_structs[0]["smiles"] == ok_structs[1]["smiles"])
    if not (halogen or identical):
        return structures

    x0 = min(a[0], b[0])
    y0 = min(a[1], b[1])
    x1 = max(a[0] + a[2], b[0] + b[2])
    y1 = max(a[1] + a[3], b[1] + b[3])
    pad = max(10, int(0.02 * min(image.size)))
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(image.width, x1 + pad), min(image.height, y1 + pad)
    crop = image.crop((x0, y0, x1, y1))
    raw = _predict(crop)
    parsed = _parse_candidate(raw) if raw else None
    if parsed is None:
        return structures

    mol, canonical = parsed

    # Two identical halves could also be two genuinely separate molecules;
    # accept the merge only if the union roughly doubles the heavy atoms.
    if identical and not halogen:
        half = max(Chem.MolFromSmiles(s["smiles"]).GetNumHeavyAtoms()
                   for s in ok_structs)
        if mol.GetNumHeavyAtoms() < 1.6 * half:
            return structures

    try:
        inchikey = Chem.MolToInchiKey(mol)
    except Exception:
        inchikey = ""
    return [{
        "index": 0,
        "bbox": [x0, y0, x1 - x0, y1 - y0],
        "thumb": _thumb(crop),
        "ok": True,
        "smiles": canonical,
        "raw_smiles": raw,
        "inchikey": inchikey,
        "stereo": _has_stereo(canonical),
        "merged": True,
    }]


def recognize_image(image_bytes: bytes, single: bool = False) -> dict:
    """Segment a figure, recognise every structure, return them in reading order.

    ``single=True`` skips segmentation and treats the whole image as one
    structure (used by the split-merge fallback and debugging).
    """
    from PIL import Image, ImageOps
    from rdkit import Chem

    cache_key = hashlib.sha256(image_bytes + (b"|single" if single else b"")).hexdigest()
    cached = _cache_get(cache_key)
    if cached is not None:
        return {**cached, "cached": True}

    try:
        image = Image.open(io.BytesIO(image_bytes))
        # Phone photos carry orientation in EXIF; honour it before anything else.
        image = ImageOps.exif_transpose(image).convert("RGB")
        if max(image.size) > 3000:
            scale = 3000.0 / max(image.size)
            image = image.resize(
                (int(image.width * scale), int(image.height * scale)), Image.LANCZOS
            )
    except Exception as exc:
        raise ValueError(f"无法读取图片: {exc}") from exc

    structures = _recognize_crops(image, single)
    if not any(s.get("ok") for s in structures):
        # Rotated scans (90/270 degrees) defeat the upright model; retry.
        for angle in (90, 270):
            rotated = image.rotate(angle, expand=True, fillcolor=(255, 255, 255))
            alt = _recognize_crops(rotated)
            if any(s.get("ok") for s in alt):
                structures = alt
                break

    result = {
        "ok": True,
        "count": len(structures),
        "structures": structures,
        "engine": "DECIMER",
    }
    _cache_put(cache_key, result)
    return {**result, "cached": False}


def recognize_smiles(image_bytes: bytes) -> dict:
    """Backwards-compatible single-structure API (first recognised crop)."""
    out = recognize_image(image_bytes)
    first = next((s for s in out["structures"] if s.get("ok")), None)
    if first is None:
        raise ValueError("未能识别出结构式（图片可能太模糊或不是结构式）")
    return {
        "ok": True,
        "smiles": first["smiles"],
        "raw_smiles": first.get("raw_smiles"),
        "engine": out["engine"],
        "cached": out.get("cached", False),
    }
