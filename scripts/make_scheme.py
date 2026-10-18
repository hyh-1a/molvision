"""Compose a synthetic reaction scheme for segmentation experiments."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from rdkit import Chem
from rdkit.Chem import rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D

OUT = Path(__file__).resolve().parent.parent / "samples"
MOLS = [
    ("1a", "CC(=O)Oc1ccccc1C(=O)O"),
    ("2", "Cn1cnc2c1c(=O)n(C)c(=O)n2C"),
    ("3a", "CC(C)Cc1ccc(cc1)C(C)C(=O)O"),
]


def render(smiles: str, w: int = 420, h: int = 320) -> Image.Image:
    mol = Chem.MolFromSmiles(smiles)
    rdDepictor.Compute2DCoords(mol)
    d = rdMolDraw2D.MolDraw2DCairo(w, h)
    d.drawOptions().bondLineWidth = 3
    rdMolDraw2D.PrepareAndDrawMolecule(d, mol)
    d.FinishDrawing()
    img = Image.open(io.BytesIO(d.GetDrawingText())).convert("RGBA")
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, img).convert("RGB")


def label(img: Image.Image, text: str) -> Image.Image:
    canvas = Image.new("RGB", (img.width, img.height + 34), "white")
    canvas.paste(img, (0, 34))
    d = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except OSError:
        font = ImageFont.load_default()
    d.text((6, 4), text, fill=(20, 20, 20), font=font)
    return canvas


def build() -> Image.Image:
    cells = [label(render(smi), tag) for tag, smi in MOLS]
    gap, arrow_w = 90, 90
    width = sum(c.width for c in cells) + gap * 2 + arrow_w * 2 + 40
    height = max(c.height for c in cells) + 40
    canvas = Image.new("RGB", (width, height), "white")
    x = 20
    for i, cell in enumerate(cells):
        canvas.paste(cell, (x, 20))
        x += cell.width
        if i < len(cells) - 1:
            y = height // 2
            d = ImageDraw.Draw(canvas)
            d.line([(x + 10, y), (x + arrow_w - 10, y)], fill=(0, 0, 0), width=4)
            d.polygon([(x + arrow_w - 10, y), (x + arrow_w - 26, y - 9),
                       (x + arrow_w - 26, y + 9)], fill=(0, 0, 0))
            d.text((x + 4, y - 46), "NIS", fill=(0, 0, 0))
            x += arrow_w
    return canvas


def main() -> None:
    canvas = build()
    path = OUT / "scheme_synthetic.png"
    canvas.save(path)
    print("wrote", path, canvas.size)


if __name__ == "__main__":
    main()
