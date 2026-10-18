"""Validate generated 3D conformers against experimental PDB ligand geometry.

For each (PDB entry, ligand) pair:
  1. extract the ligand with crystal coordinates from the entry
  2. build the reference molecule from the CCD stereo SMILES
  3. generate one (or N) ETKDG+MMFF conformers
  4. map atoms with MCS (bond orders in PDB are unreliable) and align
  5. report heavy-atom RMSD vs the crystal conformer

Also reports the CCD "ideal" geometry vs crystal as a baseline: a rigid ligand
should be near 0, a flexible one can be several Å.

    python scripts/pdb_rmsd.py --confs 20
"""
from __future__ import annotations

import argparse
import json
import math
import time
import urllib.request
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, rdFMCS, rdMolAlign

RDLogger.DisableLog("rdApp.*")

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "pdb"
CACHE.mkdir(parents=True, exist_ok=True)

# (pdb entry, ligand id, label, flexibility note)
ENTRIES = [
    ("3PTB", "BEN", "benzamidine", "rigid control"),
    ("1STP", "BTN", "biotin", "rigid-ish"),
    ("4DFR", "MTX", "methotrexate", "semi-rigid"),
    ("1IEP", "STI", "imatinib", "flexible"),
    ("1M17", "AQ4", "erlotinib", "flexible"),
    ("1HSG", "MK1", "indinavir", "very flexible"),
    ("6LU7", "PJE", "N3 inhibitor", "peptidomimetic"),
    ("1ATP", "ATP", "ATP", "flexible/charged"),
    ("1CBS", "REA", "retinoic acid", "flexible"),
    ("1ERE", "EST", "estradiol", "rigid-ish"),
    ("3ERT", "OHT", "4-hydroxytamoxifen", "flexible"),
    ("1HVR", "XK2", "HIV protease inhibitor", "flexible"),
]


def fetch(url: str, path: Path) -> Path:
    if not path.exists():
        urllib.request.urlretrieve(url, path)
    return path


def ligand_from_pdb(pdb_id: str, lig_id: str):
    path = fetch(f"https://files.rcsb.org/download/{pdb_id}.pdb",
                 CACHE / f"{pdb_id.lower()}.pdb")
    # RDKit's C++ file loader cannot open paths containing non-ASCII characters
    # (the Windows user name here), so parse the text block instead.
    block = path.read_text(encoding="utf-8", errors="ignore")
    mol = Chem.MolFromPDBBlock(block, removeHs=False, sanitize=False)
    if mol is None:
        raise ValueError("PDB parse failed")
    parts = Chem.SplitMolByPDBResidues(mol)
    if lig_id not in parts:
        raise ValueError(f"ligand {lig_id} not found")
    frags = Chem.GetMolFrags(parts[lig_id], asMols=True, sanitizeFrags=False)
    lig = max(frags, key=lambda m: m.GetNumAtoms())
    return Chem.RemoveHs(lig, sanitize=False)


def ccd_smiles(lig_id: str) -> str:
    path = CACHE / f"{lig_id}_smiles.json"
    if not path.exists():
        url = f"https://data.rcsb.org/rest/v1/core/chemcomp/{lig_id}"
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read())
        desc = data["rcsb_chem_comp_descriptor"]
        smi = desc.get("SMILES_stereo") or desc.get("SMILES")
        path.write_text(json.dumps({"smiles": smi}), encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))["smiles"]


def ideal_mol(lig_id: str):
    path = fetch(f"https://files.rcsb.org/ligands/download/{lig_id}_ideal.sdf",
                 CACHE / f"{lig_id}_ideal.sdf")
    block = path.read_text(encoding="utf-8", errors="ignore")
    mol = Chem.MolFromMolBlock(block, removeHs=False, sanitize=False)
    frags = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False)
    lig = max(frags, key=lambda m: m.GetNumAtoms())
    return Chem.RemoveHs(lig, sanitize=False)


def mapping(ref, probe):
    mcs = rdFMCS.FindMCS([ref, probe],
                         atomCompare=rdFMCS.AtomCompare.CompareElements,
                         bondCompare=rdFMCS.BondCompare.CompareAny,
                         timeout=60)
    patt = Chem.MolFromSmarts(mcs.smartsString)
    ref_idx = ref.GetSubstructMatch(patt)
    if not ref_idx:
        raise ValueError("no consistent MCS mapping")
    return patt, ref_idx


def best_rmsd(ref, probe, patt, ref_idx, conf_id: int = -1,
              max_matches: int = 20) -> float:
    """Minimum RMSD over symmetry-equivalent atom mappings (e.g. amidine N)."""
    matches = probe.GetSubstructMatches(patt, uniquify=False,
                                        maxMatches=max_matches)
    best = float("inf")
    for m in matches:
        if len(m) != len(ref_idx):
            continue
        best = min(best, aligned_rmsd(ref, probe, list(zip(m, ref_idx)), conf_id))
    if best == float("inf"):
        raise ValueError("no atom mapping")
    return best


def aligned_rmsd(ref, probe, atom_map, conf_id: int = -1) -> float:
    probe_c = Chem.Mol(probe)
    if conf_id >= 0:
        rdMolAlign.AlignMol(probe_c, ref, prbCid=conf_id, atomMap=atom_map)
    else:
        rdMolAlign.AlignMol(probe_c, ref, atomMap=atom_map)
    c1 = ref.GetConformer()
    c2 = probe_c.GetConformer(conf_id if conf_id >= 0 else 0)
    sq = 0.0
    for pi, ri in atom_map:
        p1 = c1.GetAtomPosition(ri)
        p2 = c2.GetAtomPosition(pi)
        sq += (p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2 + (p1.z - p2.z) ** 2
    return math.sqrt(sq / len(atom_map))


def generate(ref, smiles: str, n_conf: int):
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    params = AllChem.ETKDGv3()
    params.randomSeed = 0xF00D
    params.useMacrocycleTorsions = True
    params.useSmallRingTorsions = True
    if n_conf <= 1:
        cid = AllChem.EmbedMolecule(mol, params)
        if cid < 0:
            raise ValueError("embed failed")
        conf_ids = [0]
    else:
        conf_ids = list(AllChem.EmbedMultipleConfs(mol, numConfs=n_conf, params=params))
        if not conf_ids:
            raise ValueError("embed failed")
    try:
        props = AllChem.MMFFGetMoleculeProperties(mol)
        if props is not None:
            res = AllChem.MMFFOptimizeMoleculeConfs(mol, maxIters=1000)
            energies = [e for _, e in res]
            method = "MMFF94"
        else:
            raise ValueError("no MMFF params")
    except Exception:
        res = AllChem.UFFOptimizeMoleculeConfs(mol, maxIters=1000)
        energies = [e for _, e in res]
        method = "UFF"
    probe = Chem.RemoveHs(mol)
    return probe, conf_ids, energies, method


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confs", type=int, default=20,
                    help="conformers per ligand for the ensemble test")
    ap.add_argument("--out", default=str(ROOT / "data" / "pdb_rmsd.json"))
    args = ap.parse_args()

    rows = []
    print(f"{'ligand':16s} {'pdb':5s} {'atoms':>5s} {'1-conf':>8s} "
          f"{'best-of-N':>9s} {'ideal':>7s} {'method':7s}")
    for pdb_id, lig_id, label, note in ENTRIES:
        try:
            ref = ligand_from_pdb(pdb_id, lig_id)
            smiles = ccd_smiles(lig_id)
            patt, ref_idx = mapping(ref, Chem.RemoveHs(Chem.MolFromSmiles(smiles)))
            probe, conf_ids, energies, method = generate(ref, smiles, 1)
            rmsd1 = best_rmsd(ref, probe, patt, ref_idx, 0, 10)

            probe_n, conf_ids_n, energies_n, method_n = generate(ref, smiles, args.confs)
            rmsd_n = min(best_rmsd(ref, probe_n, patt, ref_idx, cid, 5)
                         for cid in range(len(conf_ids_n)))

            ideal = ideal_mol(lig_id)
            ipatt, iref = mapping(ref, ideal)
            rmsd_ideal = best_rmsd(ref, ideal, ipatt, iref, -1, 10)

            rows.append({
                "pdb": pdb_id, "ligand": lig_id, "label": label, "note": note,
                "atoms": ref.GetNumAtoms(), "rmsd_1conf": round(rmsd1, 2),
                "rmsd_best_of_n": round(rmsd_n, 2), "n_confs": args.confs,
                "rmsd_ideal": round(rmsd_ideal, 2), "method": method,
            })
            print(f"{label:16s} {pdb_id:5s} {ref.GetNumAtoms():5d} {rmsd1:8.2f} "
                  f"{rmsd_n:9.2f} {rmsd_ideal:7.2f} {method:7s}")
        except Exception as exc:  # noqa: BLE001
            print(f"{label:16s} {pdb_id:5s}  FAILED: {exc}")
            rows.append({"pdb": pdb_id, "ligand": lig_id, "label": label,
                         "error": str(exc)})

    Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    ok = [r for r in rows if "rmsd_1conf" in r]
    if ok:
        print(f"\n{len(ok)}/{len(rows)} evaluated")
        print(f"median 1-conf RMSD: {sorted(r['rmsd_1conf'] for r in ok)[len(ok)//2]:.2f} A")
        print(f"median best-of-{args.confs}: "
              f"{sorted(r['rmsd_best_of_n'] for r in ok)[len(ok)//2]:.2f} A")


if __name__ == "__main__":
    main()
