"""Recognition stress test: render N diverse molecules, measure exact match.

    python scripts/stress_recognition.py --n 100
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import time
import urllib.request
from pathlib import Path

from PIL import Image
from rdkit import Chem, RDLogger
from rdkit.Chem import rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D

RDLogger.DisableLog("rdApp.*")

BASE = "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parent.parent
NCI = ROOT / ".venv" / "Lib" / "site-packages" / "rdkit" / "Data" / "NCI" / "first_5K.smi"
ALLOWED = {1, 6, 7, 8, 9, 15, 16, 17, 35, 53}


def candidates(n: int) -> list[tuple[str, str]]:
    out = []
    with open(NCI, encoding="utf-8", errors="ignore") as f:
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
            smi = parts[0]
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                continue
            heavy = mol.GetNumHeavyAtoms()
            if not (8 <= heavy <= 40):
                continue
            if any(a.GetAtomicNum() not in ALLOWED for a in mol.GetAtoms()):
                continue
            out.append((smi, parts[1] if len(parts) > 1 else f"mol{len(out)}"))
            if len(out) >= n:
                break
    return out


def render(smiles: str) -> bytes:
    mol = Chem.MolFromSmiles(smiles)
    rdDepictor.Compute2DCoords(mol)
    d = rdMolDraw2D.MolDraw2DCairo(700, 520)
    d.drawOptions().bondLineWidth = 3
    d.drawOptions().minFontSize = 18
    rdMolDraw2D.PrepareAndDrawMolecule(d, mol)
    d.FinishDrawing()
    img = Image.open(io.BytesIO(d.GetDrawingText())).convert("RGBA")
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    out = Image.alpha_composite(bg, img).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def post(image_png: bytes) -> dict:
    payload = json.dumps({
        "image": "data:image/png;base64," + base64.b64encode(image_png).decode()
    }).encode()
    req = urllib.request.Request(BASE + "/api/recognize", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def key(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return "INVALID:" + smiles
    ik = Chem.MolToInchiKey(mol)
    return ik or ("SMI:" + Chem.MolToSmiles(mol))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out", default=str(ROOT / "data" / "stress_recognition.json"))
    args = ap.parse_args()

    data = candidates(args.n)
    print(f"test molecules: {len(data)}")
    results = []
    t_all = time.time()
    t0 = time.time()

    for i, (smiles, name) in enumerate(data):
        png = render(smiles)
        try:
            resp = post(png)
            got = [s["smiles"] for s in resp.get("structures", []) if s.get("ok")]
            exact = len(got) == 1 and key(got[0]) == key(smiles)
            results.append({"name": name, "expected": smiles, "got": got,
                            "exact": exact, "count": resp.get("count", 0)})
        except Exception as exc:
            results.append({"name": name, "expected": smiles, "got": [],
                            "exact": False, "error": str(exc)})
        if (i + 1) % 10 == 0:
            ok = sum(r["exact"] for r in results)
            print(f"  {i + 1}/{len(data)} exact={ok} ({time.time() - t0:.0f}s)")

    exact = sum(r["exact"] for r in results)
    total = len(results)
    elapsed = time.time() - t_all
    print(f"\n=== recognition stress ===")
    print(f"molecules: {total}")
    print(f"exact:     {exact}/{total} ({exact / total * 100:.1f}%)")
    print(f"time:      {elapsed:.0f}s (mean {elapsed / total:.1f}s)")
    bad = [r for r in results if not r["exact"]]
    print(f"failures:  {len(bad)}")
    for r in bad[:15]:
        print(f"  {r['name']:10s} exp={r['expected'][:50]:50s} got={r['got']}")

    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2),
                              encoding="utf-8")


if __name__ == "__main__":
    main()
