"""Render structure images that look like paper figures, for recognition tests."""
from __future__ import annotations

import io
import random
from pathlib import Path

from PIL import Image, ImageFilter
from rdkit import Chem
from rdkit.Chem import AllChem, rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D

OUT = Path(__file__).resolve().parent.parent / "samples"
OUT.mkdir(exist_ok=True)

MOLS = {
    "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
    "caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
    "ibuprofen": "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    "alanine": "C[C@@H](N)C(=O)O",
    "paracetamol": "CC(=O)Nc1ccc(O)cc1",
    "glucose": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
}


def render(smiles: str, w: int = 900, h: int = 700) -> Image.Image:
    mol = Chem.MolFromSmiles(smiles)
    rdDepictor.Compute2DCoords(mol)
    drawer = rdMolDraw2D.MolDraw2DCairo(w, h)
    opts = drawer.drawOptions()
    opts.bondLineWidth = 4
    opts.minFontSize = 22
    opts.maxFontSize = 34
    opts.clearBackground = False  # transparent -> we composite on white
    rdMolDraw2D.PrepareAndDrawMolecule(drawer, mol)
    drawer.FinishDrawing()
    img = Image.open(io.BytesIO(drawer.GetDrawingText())).convert("RGBA")
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, img).convert("RGB")


def degrade(img: Image.Image, seed: int) -> Image.Image:
    rnd = random.Random(seed)
    img = img.filter(ImageFilter.GaussianBlur(radius=rnd.uniform(0.4, 0.9)))
    # slight rotation, like a phone photo of a page
    img = img.rotate(rnd.uniform(-1.2, 1.2), expand=True, fillcolor=(255, 255, 255))
    # gaussian noise
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            n = rnd.randint(-6, 6)
            px[x, y] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))
    return img


def main() -> None:
    for i, (name, smi) in enumerate(MOLS.items()):
        img = degrade(render(smi), seed=i)
        path = OUT / f"{name}.png"
        img.save(path)
        print(f"wrote {path}  ({img.size[0]}x{img.size[1]})")


if __name__ == "__main__":
    main()
