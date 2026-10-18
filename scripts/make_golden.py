"""Build a deterministic golden set for MolVision evaluation.

Each case is a rendered image with a known answer, covering the situations the
tool is expected to handle (and a few it should refuse). Output:

    samples/golden/*.png
    samples/golden/expected.json
"""
from __future__ import annotations

import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from rdkit import Chem
from rdkit.Chem import rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D

OUT = Path(__file__).resolve().parent.parent / "samples" / "golden"
OUT.mkdir(parents=True, exist_ok=True)

MOLS = {
    "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
    "caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
    "ibuprofen": "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    "alanine": "C[C@@H](N)C(=O)O",
    "glucose": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
    "paracetamol": "CC(=O)Nc1ccc(O)cc1",
    "oxadiazole_r": "*c1nnc(OCC)o1",
}


def render(smiles: str, w: int = 760, h: int = 560, scale: int = 3,
           r_label: str | None = None) -> Image.Image:
    mol = Chem.MolFromSmiles(smiles)
    if r_label:
        for atom in mol.GetAtoms():
            if atom.GetAtomicNum() == 0:
                atom.SetProp("atomLabel", r_label)
    rdDepictor.Compute2DCoords(mol)
    drawer = rdMolDraw2D.MolDraw2DCairo(w, h)
    opts = drawer.drawOptions()
    opts.bondLineWidth = scale
    opts.minFontSize = 20
    opts.maxFontSize = 32
    opts.clearBackground = False
    rdMolDraw2D.PrepareAndDrawMolecule(drawer, mol)
    drawer.FinishDrawing()
    img = Image.open(io.BytesIO(drawer.GetDrawingText())).convert("RGBA")
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, img).convert("RGB")


def text_noise(w: int = 1000, h: int = 700) -> Image.Image:
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    lines = [
        "Table 1. Optimization of the reaction conditions.a",
        "Entry   Solvent   Temp (°C)   Time (h)   Yield (%)",
        "1       THF       25          12         61",
        "2       THF       40          12         70",
        "3       DMSO      25          12         55",
        "4       DMF       40          6          75",
        "a Reactions run at 0.2 M; isolated yields.",
    ]
    for i, line in enumerate(lines):
        d.text((40, 60 + i * 90), line, fill=(20, 20, 20), font=font)
    return img


def table_noise(w: int = 900, h: int = 600) -> Image.Image:
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = 60, 80, 840, 520
    for i in range(6):
        y = y0 + i * (y1 - y0) // 5
        d.line([(x0, y), (x1, y)], fill=(0, 0, 0), width=2)
    for j in range(5):
        x = x0 + j * (x1 - x0) // 4
        d.line([(x, y0), (x, y1)], fill=(0, 0, 0), width=2)
    return img


def stacked(a: Image.Image, b: Image.Image) -> Image.Image:
    w = max(a.width, b.width)
    canvas = Image.new("RGB", (w, a.height + b.height + 80), "white")
    canvas.paste(a, ((w - a.width) // 2, 0))
    canvas.paste(b, ((w - b.width) // 2, a.height + 80))
    return canvas


def main() -> None:
    expected: dict[str, dict] = {}

    def save(name: str, img: Image.Image, smiles: list[str], strict: bool = True,
             note: str = "") -> None:
        img.save(OUT / name)
        expected[name] = {"expect": smiles, "strict": strict, "note": note}

    for name in ["aspirin", "caffeine", "ibuprofen", "alanine", "glucose"]:
        save(f"single_{name}.png", render(MOLS[name]), [MOLS[name]])

    rot = render(MOLS["caffeine"]).rotate(90, expand=True, fillcolor=(255, 255, 255))
    save("single_caffeine_rot90.png", rot, [MOLS["caffeine"]], note="rotated 90 degrees")

    save("multi_2x2.png",
         stacked(render(MOLS["aspirin"]), render(MOLS["caffeine"])),
         [MOLS["aspirin"], MOLS["caffeine"]], note="two structures stacked")

    save("markush_oxadiazole.png", render(MOLS["oxadiazole_r"], r_label="R"),
         [MOLS["oxadiazole_r"]], note="R-group wildcard, drawn with an R label")

    amide_core = "CC(=O)Nc1ccc(*)cc1"
    save("abbrev_ph.png", render(amide_core, r_label="Ph"),
         ["CC(=O)Nc1ccc(-c2ccccc2)cc1"], note="Ph abbreviation for phenyl")
    save("abbrev_me.png", render(amide_core, r_label="Me"),
         ["CC(=O)Nc1ccc(C)cc1"], note="Me abbreviation for methyl")

    save("noise_text.png", text_noise(), [], note="prose only: expect no structures")
    save("noise_table.png", table_noise(), [], note="table rules only: expect no structures")

    import make_scheme

    save("scheme_3.png", make_scheme.build(),
         [MOLS["aspirin"], MOLS["caffeine"], MOLS["ibuprofen"]],
         note="synthetic reaction scheme with arrows")

    low = render(MOLS["aspirin"], 900, 700)
    low = low.resize((220, 171), Image.LANCZOS).resize((440, 342), Image.LANCZOS)
    save("lowres_aspirin.png", low, [MOLS["aspirin"]], strict=False, note="blurry, soft case")

    (OUT / "expected.json").write_text(
        json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {len(expected)} cases to {OUT}")


if __name__ == "__main__":
    main()
