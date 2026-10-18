"""3D conformer stress on genuinely complex molecules (fetched from PubChem)."""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem

RDLogger.DisableLog("rdApp.*")

NAMES = [
    "erythromycin", "cyclosporine", "rapamycin", "paclitaxel", "ivermectin",
    "vancomycin", "chlorophyll a", "ferrocene", "cisplatin", "carboplatin",
    "sucrose", "adenosine triphosphate", "doxorubicin", "cyanocobalamin",
    "reserpine", "digoxin", "gramicidin", "polymyxin B", "taxol", "heme",
]


def fetch_smiles(name: str) -> str | None:
    url = ("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
           + urllib.parse.quote(name)
           + "/property/IsomericSMILES,CanonicalSMILES/JSON")
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read())
        props = data["PropertyTable"]["Properties"][0]
        return (props.get("IsomericSMILES") or props.get("CanonicalSMILES")
                or props.get("ConnectivitySMILES"))
    except Exception:
        return None


def embed(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None, "parse", 0, 0.0
    heavy = mol.GetNumHeavyAtoms()
    molh = Chem.AddHs(mol)
    t0 = time.time()
    params = AllChem.ETKDGv3()
    params.randomSeed = 0xF00D
    params.useMacrocycleTorsions = True
    params.useSmallRingTorsions = True
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
        return None, "embed", heavy, time.time() - t0
    method = "none"
    try:
        if AllChem.MMFFGetMoleculeProperties(molh) is not None:
            AllChem.MMFFOptimizeMolecule(molh, maxIters=1000)
            method = "MMFF94"
    except Exception:
        method = "none"
    if method == "none":
        try:
            if AllChem.UFFOptimizeMolecule(molh, maxIters=1000) >= 0:
                method = "UFF"
        except Exception:
            method = "none"
    return molh, method, heavy, time.time() - t0


def main() -> None:
    print(f"{'molecule':18s} {'heavy':>5s} {'status':10s} {'method':8s} {'sec':>7s}")
    ok = 0
    for name in NAMES:
        smiles = fetch_smiles(name)
        if not smiles:
            print(f"{name:18s} {'':>5s} FETCH-FAIL")
            continue
        mol, method, heavy, dt = embed(smiles)
        status = "OK" if mol is not None else "FAIL"
        ok += mol is not None
        print(f"{name:18s} {heavy:5d} {status:10s} {method:8s} {dt:7.2f}")
    print(f"\n{ok}/{len(NAMES)} embedded")


if __name__ == "__main__":
    main()
