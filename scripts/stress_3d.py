"""Stress-test 3D conformer generation on the NCI sample set shipped with RDKit.

    python scripts/stress_3d.py --n 1000

Reports: embed success, MMFF/UFF method, failures by heavy-atom count, timing.
"""
from __future__ import annotations

import argparse
import time
from collections import Counter
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem

RDLogger.DisableLog("rdApp.*")

ROOT = Path(__file__).resolve().parent.parent
NCI = ROOT / ".venv" / "Lib" / "site-packages" / "rdkit" / "Data" / "NCI" / "first_5K.smi"


def load(n: int, offset: int) -> list[tuple[str, str]]:
    out = []
    with open(NCI, encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            if i < offset:
                continue
            parts = line.strip().split()
            if not parts:
                continue
            out.append((parts[0], parts[1] if len(parts) > 1 else f"mol{i}"))
            if len(out) >= n:
                break
    return out


def embed(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None, "parse", 0
    heavy = mol.GetNumHeavyAtoms()
    molh = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = 0xF00D
    params.useSmallRingTorsions = True
    params.useMacrocycleTorsions = True
    try:
        cid = AllChem.EmbedMolecule(molh, params)
    except Exception:
        cid = -1
    if cid < 0:
        try:
            cid = AllChem.EmbedMolecule(molh, randomSeed=0xF00D, useRandomCoords=True)
        except Exception:
            cid = -1
    if cid < 0:
        return None, "embed", heavy

    method = "none"
    try:
        props = AllChem.MMFFGetMoleculeProperties(molh)
        if props is not None:
            AllChem.MMFFOptimizeMolecule(molh, maxIters=500)
            method = "MMFF94"
    except Exception:
        method = "none"
    if method == "none":
        try:
            if AllChem.UFFOptimizeMolecule(molh, maxIters=500) >= 0:
                method = "UFF"
        except Exception:
            method = "none"
    return molh, method, heavy


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--offset", type=int, default=0)
    args = ap.parse_args()

    data = load(args.n, args.offset)
    print(f"loaded {len(data)} molecules from {NCI.name}")

    ok = 0
    methods = Counter()
    failures = []
    times = []
    by_size_ok = Counter()
    by_size_all = Counter()
    t_all = time.time()

    for i, (smiles, name) in enumerate(data):
        t0 = time.time()
        mol, method, heavy = embed(smiles)
        dt = time.time() - t0
        times.append(dt)
        bin_ = "<=20" if heavy <= 20 else "21-40" if heavy <= 40 else "41-70" if heavy <= 70 else ">70"
        by_size_all[bin_] += 1
        if mol is not None:
            ok += 1
            methods[method] += 1
            by_size_ok[bin_] += 1
        else:
            failures.append((name, smiles[:60], method, heavy))
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(data)} ok={ok} ({time.time() - t_all:.0f}s)")

    total = len(data)
    print("\n=== 3D conformer stress ===")
    print(f"molecules: {total}")
    print(f"success:   {ok} ({ok / total * 100:.1f}%)")
    print(f"methods:   {dict(methods)}")
    print(f"failures:  {len(failures)}")
    print(f"time:      total {time.time() - t_all:.1f}s | "
          f"mean {sum(times) / len(times):.2f}s | max {max(times):.1f}s")
    print("\nby heavy atoms (ok/all):")
    for b in ["<=20", "21-40", "41-70", ">70"]:
        if by_size_all[b]:
            print(f"  {b:6s} {by_size_ok[b]:4d}/{by_size_all[b]:4d}")
    if failures:
        print("\nfailures (first 15):")
        for name, smi, reason, heavy in failures[:15]:
            print(f"  {reason:6s} heavy={heavy:3d} {name}  {smi}")


if __name__ == "__main__":
    main()
