"""Summarise a run_pdf results.csv: counts, unique catalogue, noise candidates."""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

from rdkit import Chem


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/pdf_out/results.csv")
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))

    ok = [r for r in rows if r.get("ok") == "True"]
    failed = [r for r in rows if r.get("ok") != "True"]
    unique: dict[str, dict] = {}
    for r in ok:
        unique.setdefault(r["smiles"], r)

    print(f"rows={len(rows)}  recognised={len(ok)}  failed={len(failed)}  unique={len(unique)}")
    print(f"per page: {dict(sorted(Counter(int(r['page']) for r in ok).items()))}")

    noise_small, noise_wild, clean = [], [], []
    for smi, r in unique.items():
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            continue
        heavy = mol.GetNumHeavyAtoms()
        wild = any(a.GetAtomicNum() == 0 for a in mol.GetAtoms())
        rec = (smi, r.get("formula", ""), heavy, r.get("sa_score", ""), r.get("source", ""))
        if wild:
            noise_wild.append(rec)
        elif heavy < 4:
            noise_small.append(rec)
        else:
            clean.append(rec)

    print(f"\n--- likely real molecules ({len(clean)}) ---")
    for smi, formula, heavy, sa, src in sorted(clean, key=lambda x: x[2], reverse=True):
        print(f"  {formula:15s} heavy={heavy:3d} SA={sa:>5}  {src:6s} {smi}")

    if noise_wild:
        print(f"\n--- R-group / Markush ({len(noise_wild)}) ---")
        for smi, formula, heavy, sa, src in noise_wild:
            print(f"  {src:6s} {smi}")

    if noise_small:
        print(f"\n--- fragments < 4 heavy atoms ({len(noise_small)}) ---")
        for smi, formula, heavy, sa, src in noise_small:
            print(f"  {src:6s} {formula:12s} {smi}")

    if failed:
        print(f"\n--- failed ({len(failed)}) ---")
        for r in failed[:10]:
            print(f"  {r.get('source')}: {r.get('error')}")


if __name__ == "__main__":
    main()
