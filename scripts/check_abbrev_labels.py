"""Audit common abbreviation labels: render [Me]/[Et]/... and check recognition."""
from __future__ import annotations

import base64
import io
import json
import sys
import urllib.request
from pathlib import Path

from PIL import Image
from rdkit import Chem, RDLogger
from rdkit.Chem import rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.chem import canonical_smiles, expand_abbreviations, parse_smiles  # noqa: E402

RDLogger.DisableLog("rdApp.*")
BASE = "http://127.0.0.1:8765"

# (label, base SMILES with one dummy *, expected molecule)
CASES = [
    ("Me", "CC(=O)Nc1ccc(*)cc1", "CC(=O)Nc1ccc(C)cc1"),
    ("Et", "CC(=O)Nc1ccc(*)cc1", "CC(=O)Nc1ccc(CC)cc1"),
    ("iPr", "CC(=O)Nc1ccc(*)cc1", "CC(=O)Nc1ccc(C(C)C)cc1"),
    ("tBu", "CC(=O)Nc1ccc(*)cc1", "CC(=O)Nc1ccc(C(C)(C)C)cc1"),
    ("Ph", "CC(=O)Nc1ccc(*)cc1", "CC(=O)Nc1ccc(-c2ccccc2)cc1"),
    ("Bn", "CC(=O)Nc1ccc(*)cc1", "CC(=O)Nc1ccc(Cc2ccccc2)cc1"),
    ("Ac", "c1ccccc1*", "CC(=O)c1ccccc1"),
    ("OMe", "c1ccccc1*", "COc1ccccc1"),
    ("CO2Et", "c1ccccc1*", "CCOC(=O)c1ccccc1"),
]


def render(base: str, label: str) -> bytes:
    mol = Chem.MolFromSmiles(base)
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() == 0:
            atom.SetProp("atomLabel", label)
    rdDepictor.Compute2DCoords(mol)
    d = rdMolDraw2D.MolDraw2DCairo(760, 560)
    d.drawOptions().bondLineWidth = 3
    rdMolDraw2D.PrepareAndDrawMolecule(d, mol)
    d.FinishDrawing()
    img = Image.open(io.BytesIO(d.GetDrawingText())).convert("RGBA")
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    buf = io.BytesIO()
    Image.alpha_composite(bg, img).convert("RGB").save(buf, "PNG")
    return buf.getvalue()


def key(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles or "")
    if mol is None:
        return "INVALID:" + (smiles or "")
    return Chem.MolToInchiKey(mol) or ("SMI:" + Chem.MolToSmiles(mol))


def post(png: bytes) -> dict:
    payload = json.dumps({
        "image": "data:image/png;base64," + base64.b64encode(png).decode(),
        "single": True,
    }).encode()
    req = urllib.request.Request(BASE + "/api/recognize", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())


def main() -> None:
    ok_count = 0
    print(f"{'label':8s} {'result':6s} got")
    for label, base, expected in CASES:
        data = post(render(base, label))
        got = [s["smiles"] for s in data.get("structures", []) if s.get("ok")]
        exact = len(got) == 1 and key(got[0]) == key(expected)
        ok_count += int(exact)
        print(f"{label:8s} {'OK' if exact else 'FAIL':6s} {got}")
    print(f"\n{ok_count}/{len(CASES)} exact")


if __name__ == "__main__":
    main()
