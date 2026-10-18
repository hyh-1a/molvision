"""Head-to-head: MolScribe vs MolVision (DECIMER) on the same rendered molecules.

    python scripts/compare_molscribe.py --limit 5
    python scripts/compare_molscribe.py --n 100
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from rdkit import Chem, RDLogger

RDLogger.DisableLog("rdApp.*")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from stress_recognition import candidates, render  # noqa: E402

CKPT = Path(r"E:\MolVisionData\molscribe\swin.pth")


def key(smiles: str, strip_stereo: bool = False) -> str:
    mol = Chem.MolFromSmiles(smiles or "")
    if mol is None:
        return "INVALID:" + (smiles or "")
    if strip_stereo:
        Chem.RemoveStereochemistry(mol)
    ik = Chem.MolToInchiKey(mol)
    return ik or ("SMI:" + Chem.MolToSmiles(mol))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--limit", type=int, default=0, help="smoke-test first N")
    ap.add_argument("--out", default=str(ROOT / "data" / "molscribe_compare.json"))
    args = ap.parse_args()

    import torch
    from molscribe import MolScribe

    data = candidates(args.n)
    if args.limit:
        data = data[: args.limit]
    print(f"molecules: {len(data)}  checkpoint: {CKPT.exists()}")

    model = MolScribe(str(CKPT), device=torch.device("cpu"))
    # OpenCV cannot read paths containing non-ASCII characters (Windows user
    # name), so the intermediates live on the ASCII-only E: path.
    img_dir = Path(r"E:\MolVisionData\molscribe-imgs")
    img_dir.mkdir(parents=True, exist_ok=True)

    results = []
    t0 = time.time()
    for i, (smiles, name) in enumerate(data):
        path = img_dir / f"{i:03d}_{name}.png"
        path.write_bytes(render(smiles))
        try:
            out = model.predict_image_file(str(path))
            pred = out.get("smiles", "") if isinstance(out, dict) else ""
            exact = bool(pred) and key(pred) == key(smiles)
            conn = bool(pred) and key(pred, True) == key(smiles, True)
            results.append({"name": name, "expected": smiles, "got": pred,
                            "exact": exact, "connectivity": conn})
        except Exception as exc:  # noqa: BLE001
            results.append({"name": name, "expected": smiles, "got": "",
                            "exact": False, "connectivity": False,
                            "error": str(exc)})
        if (i + 1) % 10 == 0:
            ok = sum(r["exact"] for r in results)
            print(f"  {i + 1}/{len(data)} exact={ok} ({time.time() - t0:.0f}s)")

    total = len(results)
    exact = sum(r["exact"] for r in results)
    conn = sum(r["connectivity"] for r in results)
    elapsed = time.time() - t0
    print("\n=== MolScribe ===")
    print(f"exact:        {exact}/{total} ({exact / total * 100:.1f}%)")
    print(f"connectivity: {conn}/{total} ({conn / total * 100:.1f}%)")
    print(f"time:         {elapsed:.0f}s (mean {elapsed / total:.1f}s)")
    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
