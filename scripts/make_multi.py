"""Compose paper-like figures with several structures, for segmentation tests."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from rdkit import Chem
from rdkit.Chem import rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D

OUT = Path(__file__).resolve().parent.parent / "samples"
OUT.mkdir(exist_ok=True)

MOLS = [
    ("1", "aspirin", "CC(=O)Oc1ccccc1C(=O)O"),
    ("2", "caffeine", "Cn1cnc2c1c(=O)n(C)c(=O)n2C"),
    ("3", "ibuprofen", "CC(C)Cc1ccc(cc1)C(C)C(=O)O"),
    ("4", "paracetamol", "CC(=O)Nc1ccc(O)cc1"),
]


def render(smiles: str, w: int = 620, h: int = 460) -> Image.Image:
    mol = Chem.MolFromSmiles(smiles)
    rdDepictor.Compute2DCoords(mol)
    drawer = rdMolDraw2D.MolDraw2DCairo(w, h)
    opts = drawer.drawOptions()
    opts.bondLineWidth = 3
    opts.minFontSize = 20
    opts.maxFontSize = 30
    opts.clearBackground = False
    rdMolDraw2D.PrepareAndDrawMolecule(drawer, mol)
    drawer.FinishDrawing()
    img = Image.open(io.BytesIO(drawer.GetDrawingText())).convert("RGBA")
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, img).convert("RGB")


def label(img: Image.Image, text: str) -> Image.Image:
    canvas = Image.new("RGB", (img.width, img.height + 56), "white")
    canvas.paste(img, (0, 56))
    d = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 34)
    except OSError:
        font = ImageFont.load_default()
    d.text((10, 8), text, fill=(20, 20, 20), font=font)
    return canvas


def compose(rows: int, cols: int, name: str) -> None:
    cells = [label(render(smi), num) for num, _, smi in MOLS]
    cw = max(c.width for c in cells)
    ch = max(c.height for c in cells)
    gap = 40
    W = cols * cw + (cols + 1) * gap
    H = rows * ch + (rows + 1) * gap + 40
    canvas = Image.new("RGB", (W, H), "white")
    for i, cell in enumerate(cells[: rows * cols]):
        r, c = divmod(i, cols)
        x = gap + c * (cw + gap)
        y = gap + r * (ch + gap)
        canvas.paste(cell, (x, y))
    canvas.save(OUT / name)
    print("wrote", OUT / name, canvas.size)


if __name__ == "__main__":
    compose(2, 2, "multi_4.png")
    compose(1, 3, "multi_3.png")
