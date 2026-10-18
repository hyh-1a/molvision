"""Core cheminformatics for MolVision.

SMILES -> validated molecule -> 2D depiction / 3D conformer -> properties.

Everything here is deterministic: the same input always yields the same
output, which matters a lot for a live hackathon demo.
"""
from __future__ import annotations

import base64
import json
import math
import threading
from dataclasses import dataclass, field, asdict
from typing import Any

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, Crippen, Descriptors, Draw, rdDepictor, rdMolDescriptors, rdMolAlign
from rdkit.Chem.Draw import rdMolDraw2D

# RDKit is chatty on stderr; keep the server output clean.
RDLogger.DisableLog("rdApp.*")


class ChemError(Exception):
    """Raised for anything the user can fix (bad SMILES, failed embedding...)."""


# --------------------------------------------------------------------------- #
# Parsing / normalisation
# --------------------------------------------------------------------------- #

import re

_RGROUP_BRACKET = re.compile(r"\[(?:R\d*[a-z]?'{0,2}|Ar|R)\]", re.IGNORECASE)
_RGROUP_BARE = re.compile(r"(?<![A-Za-z])R\d*[a-z]?'{0,2}(?![a-z])")

# Common organic-chemistry abbreviations. DECIMER emits labels like [Ph] or
# [Boc] as pseudo-atoms; each expansion is written so that its FIRST atom is
# the attachment point (e.g. [Bn] -> Cc1ccccc1 attaches at the CH2).
# Ring-closure digits are placeholders ({r}, {r1}...): they are replaced with
# fresh %90+ numbers per occurrence, otherwise an expansion inside a ring
# would collide with the host's ring numbering and fuse the rings.
ABBREVIATIONS: dict[str, str] = {
    # alkyl
    "Me": "C", "Et": "CC", "nPr": "CCC", "iPr": "C(C)C",
    "nBu": "CCCC", "iBu": "CC(C)C", "sBu": "C(C)CC", "tBu": "C(C)(C)C",
    "nPent": "CCCCC", "nHex": "CCCCCC", "Cy": "C{r}CCCCC{r}",
    # aryl / acyl
    "Ph": "c{r}ccccc{r}", "Bn": "Cc{r}ccccc{r}",
    "Bz": "C(=O)c{r}ccccc{r}", "Ar": "*",
    # protecting groups
    "Boc": "C(=O)OC(C)(C)C",
    "Cbz": "C(=O)OCc{r}ccccc{r}",
    "Fmoc": "C(=O)OCC{r1}c{r2}ccccc{r2}-c{r3}ccccc{r3}{r1}",
    "Ac": "C(=O)C",
    "Ts": "S(=O)(=O)c{r}ccc(C)cc{r}",
    "Ms": "S(=O)(=O)C",
    "Tf": "S(=O)(=O)C(F)(F)F",
    "TMS": "[Si](C)(C)C",
    "TBS": "[Si](C)(C)C(C)(C)C",
    "TBDPS": "[Si](c{r1}ccccc{r1})(c{r2}ccccc{r2})C(C)(C)C",
    # esters / amides / ethers
    "OMe": "OC", "OEt": "OCC", "OPh": "Oc{r}ccccc{r}",
    "CO2Me": "C(=O)OC", "CO2Et": "C(=O)OCC", "CO2H": "C(=O)O",
    "CONH2": "C(=O)N", "CONMe2": "C(=O)N(C)C",
    "NHBoc": "NC(=O)OC(C)(C)C", "NHAc": "NC(=O)C",
    "SO2Me": "S(=O)(=O)C",
    "CF3": "C(F)(F)F", "CCl3": "C(Cl)(Cl)Cl",
}

_ABBREV_TOKEN = re.compile(r"\[([A-Za-z][A-Za-z0-9]*)\]")
_ISOTOPE_METHYL = re.compile(r"\[1[0-9]CH3\]")


def _format_expansion(template: str, counter: int) -> tuple[str, int]:
    kwargs = {}
    for key in ("r", "r1", "r2", "r3"):
        if "{" + key + "}" in template:
            kwargs[key] = f"%{counter}"
            counter += 1
    return template.format(**kwargs), counter


def expand_abbreviations(smiles: str) -> str:
    # "Me" is sometimes read as an isotope-labelled methyl (e.g. [14CH3]).
    smiles = _ISOTOPE_METHYL.sub("C", smiles)
    counter = 90

    def repl(m: re.Match) -> str:
        nonlocal counter
        template = ABBREVIATIONS.get(m.group(1))
        if template is None:
            return m.group(0)
        while f"%{counter}" in smiles:
            counter += 1
        out, counter = _format_expansion(template, counter)
        return out

    return _ABBREV_TOKEN.sub(repl, smiles)


def find_abbreviations(smiles: str) -> list[str]:
    return sorted({m.group(1) for m in _ABBREV_TOKEN.finditer(smiles)
                   if m.group(1) in ABBREVIATIONS})


def normalize_markush(smiles: str) -> str:
    """Map R-group placeholders (R, R1, R17a, R'', Ar) onto the '*' dummy atom."""
    s = _RGROUP_BRACKET.sub("*", smiles)
    return _RGROUP_BARE.sub("*", s)


def is_markush(mol: Chem.Mol) -> bool:
    return any(a.GetAtomicNum() == 0 for a in mol.GetAtoms())


def substitute_r_groups(mol: Chem.Mol, symbol: str = "C") -> Chem.Mol:
    """Replace undefined R-group placeholders with methyls (default assumption).

    The user-facing convention is: if R is not specified, treat it as CH3 so
    that a 3D conformer and descriptors can still be produced.
    """
    m = Chem.Mol(mol)
    for atom in m.GetAtoms():
        if atom.GetAtomicNum() == 0:
            atom.SetAtomicNum(6)
            atom.SetNoImplicit(True)
            atom.SetNumExplicitHs(3)
            atom.SetFormalCharge(0)
            atom.SetNumRadicalElectrons(0)
            atom.SetIsotope(0)
            atom.SetChiralTag(Chem.ChiralType.CHI_UNSPECIFIED)
    try:
        Chem.SanitizeMol(m)
    except Exception as exc:
        raise ChemError(f"R 基替换为甲基后无法解析: {exc}") from exc
    return m


def parse_smiles(smiles: str) -> Chem.Mol:
    if not smiles or not smiles.strip():
        raise ChemError("SMILES 为空")
    text = smiles.strip()

    # Expand known abbreviations first: RDKit happily parses unknown bracket
    # atoms like [Ts] as dummy atoms, which would silently bypass expansion.
    attempts: list[str] = [
        expand_abbreviations(text),
        expand_abbreviations(normalize_markush(text)),
        text,
    ]
    markush = normalize_markush(text)
    if markush != text:
        attempts.append(markush)

    seen = set()
    for candidate in attempts:
        if candidate in seen:
            continue
        seen.add(candidate)
        mol = Chem.MolFromSmiles(candidate)
        if mol is not None:
            return mol
    raise ChemError(f"无法解析 SMILES: {smiles!r}")


def canonical_smiles(mol: Chem.Mol) -> str:
    return Chem.MolToSmiles(mol, canonical=True)


def largest_fragment(mol: Chem.Mol) -> Chem.Mol:
    """Drop salts / solvents: keep the biggest fragment (by heavy atoms)."""
    frags = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=True)
    if len(frags) == 1:
        return mol
    return max(frags, key=lambda m: m.GetNumHeavyAtoms())


def normalize(smiles: str) -> tuple[Chem.Mol, Chem.Mol]:
    """Return (full molecule, largest fragment used for 3D embedding)."""
    mol = parse_smiles(smiles)
    return mol, largest_fragment(mol)


# --------------------------------------------------------------------------- #
# Properties
# --------------------------------------------------------------------------- #

def properties(mol: Chem.Mol) -> dict[str, Any]:
    """Human-facing descriptors. All computed by RDKit, no estimation."""
    try:
        inchikey = Chem.MolToInchiKey(mol)
    except Exception:
        inchikey = ""

    centers = Chem.FindMolChiralCenters(
        mol, includeUnassigned=True, useLegacyImplementation=False
    )
    assigned = [c for c in centers if c[1] != "?"]
    unassigned = [c for c in centers if c[1] == "?"]

    return {
        "formula": rdMolDescriptors.CalcMolFormula(mol),
        "canonical_smiles": canonical_smiles(mol),
        "inchikey": inchikey,
        "mw": round(Descriptors.MolWt(mol), 3),
        "exact_mass": round(Descriptors.ExactMolWt(mol), 4),
        "logp": round(Crippen.MolLogP(mol), 3),
        "tpsa": round(rdMolDescriptors.CalcTPSA(mol), 2),
        "hbd": rdMolDescriptors.CalcNumHBD(mol),
        "hba": rdMolDescriptors.CalcNumHBA(mol),
        "rotatable_bonds": rdMolDescriptors.CalcNumRotatableBonds(mol),
        "rings": rdMolDescriptors.CalcNumRings(mol),
        "aromatic_rings": rdMolDescriptors.CalcNumAromaticRings(mol),
        "heavy_atoms": mol.GetNumHeavyAtoms(),
        "formal_charge": Chem.GetFormalCharge(mol),
        "stereocenters": len(assigned),
        "unspecified_stereocenters": len(unassigned),
        "stereo_centers_detail": [
            {"atom_idx": idx, "tag": tag} for idx, tag in centers
        ],
    }


# --------------------------------------------------------------------------- #
# 2D depiction
# --------------------------------------------------------------------------- #

def depict_2d_png(mol: Chem.Mol, width: int = 480, height: int = 360) -> bytes:
    """Render a clean 2D structure PNG."""
    m = Chem.Mol(mol)
    rdDepictor.Compute2DCoords(m)
    drawer = rdMolDraw2D.MolDraw2DCairo(width, height)
    opts = drawer.drawOptions()
    opts.clearBackground = True
    opts.bondLineWidth = 2
    opts.minFontSize = 13
    opts.maxFontSize = 22
    try:
        rdMolDraw2D.PrepareAndDrawMolecule(drawer, m)
    except Exception as exc:  # very defensive: depiction must not kill the demo
        raise ChemError(f"2D 绘制失败: {exc}") from exc
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


def depict_2d_svg(mol: Chem.Mol) -> str:
    m = Chem.Mol(mol)
    rdDepictor.Compute2DCoords(m)
    drawer = rdMolDraw2D.MolDraw2DSVG(420, 320)
    rdMolDraw2D.PrepareAndDrawMolecule(drawer, m)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


# --------------------------------------------------------------------------- #
# 3D conformer
# --------------------------------------------------------------------------- #

@dataclass
class Conformer:
    molblock: str
    energy_kcal: float | None
    method: str          # "MMFF94" | "UFF" | "none"
    atoms: int
    warnings: list[str] = field(default_factory=list)


def embed_3d(mol: Chem.Mol, random_seed: int = 0xF00D, max_iters: int = 500) -> Conformer:
    """Generate one optimised 3D conformer (ETKDGv3 + MMFF94, UFF fallback)."""
    try:
        molh = Chem.AddHs(mol)
        params = AllChem.ETKDGv3()
        params.randomSeed = random_seed
        params.useSmallRingTorsions = True
        params.useMacrocycleTorsions = True
        cid = AllChem.EmbedMolecule(molh, params)
        if cid < 0:
            # last resort: random coordinates then optimise
            cid = AllChem.EmbedMolecule(molh, randomSeed=random_seed, useRandomCoords=True)
        if cid < 0:
            raise ChemError("3D 构象生成失败（分子过大或结构过于紧张）")
    except ChemError:
        raise
    except Exception as exc:
        raise ChemError(f"3D 构象生成失败: {exc}") from exc

    warnings: list[str] = []
    energy: float | None = None
    method = "none"

    try:
        props = AllChem.MMFFGetMoleculeProperties(molh)
        if props is not None:
            ff = AllChem.MMFFGetMoleculeForceField(molh, props)
            if ff is not None:
                AllChem.MMFFOptimizeMolecule(molh, maxIters=max_iters)
                ff = AllChem.MMFFGetMoleculeForceField(molh, props)
                energy = ff.CalcEnergy()
                method = "MMFF94"
    except Exception as exc:
        warnings.append(f"MMFF94 优化失败，回退 UFF: {exc}")

    if method == "none":
        try:
            AllChem.UFFOptimizeMolecule(molh, maxIters=max_iters)
            ff = AllChem.UFFGetMoleculeForceField(molh)
            if ff is not None:
                energy = ff.CalcEnergy()
            method = "UFF"
        except Exception as exc:
            warnings.append(f"UFF 优化失败: {exc}")

    try:
        # Do NOT call AssignStereochemistryFrom3D here: for a structure whose
        # stereocentres were unspecified in the drawing, that would bake an
        # arbitrary enantiomer into the exported SDF. The 3D geometry is still
        # one arbitrary conformer, but the file must not claim a configuration.
        block = Chem.MolToMolBlock(molh)
    except Exception as exc:
        raise ChemError(f"3D 结构导出失败: {exc}") from exc

    return Conformer(
        molblock=block,
        energy_kcal=round(energy, 3) if energy is not None else None,
        method=method,
        atoms=molh.GetNumAtoms(),
        warnings=warnings,
    )


def embed_conformers(mol: Chem.Mol, n_confs: int = 10,
                     energy_window: float = 10.0) -> list[dict[str, Any]]:
    """Generate an ensemble, optimise each conformer, return sorted by energy.

    Only conformers within `energy_window` kcal/mol of the lowest are kept.
    """
    try:
        molh = Chem.AddHs(mol)
        params = AllChem.ETKDGv3()
        params.randomSeed = 0xF00D
        params.useSmallRingTorsions = True
        params.useMacrocycleTorsions = True
        cids = list(AllChem.EmbedMultipleConfs(molh, numConfs=n_confs, params=params))
        if not cids:
            raise ChemError("多构象生成失败")
    except ChemError:
        raise
    except Exception as exc:
        raise ChemError(f"多构象生成失败: {exc}") from exc

    try:
        results = AllChem.MMFFOptimizeMoleculeConfs(molh, maxIters=500)
        energies = [e for _, e in results]
        method = "MMFF94"
    except Exception:
        results = AllChem.UFFOptimizeMoleculeConfs(molh, maxIters=500)
        energies = [e for _, e in results]
        method = "UFF"

    pairs = sorted(zip(cids, energies), key=lambda x: x[1])
    emin = float(pairs[0][1])

    # Greedy dedupe: symmetry-equivalent embeddings would otherwise fill the
    # ensemble with copies (aspirin yields ~5 identical conformers).
    # GetBestRMS needs two separate molecule objects, otherwise it returns
    # nonsense for different confIds of the same object.
    probe_copy = Chem.Mol(molh)
    ref_copy = Chem.Mol(molh)
    kept: list[tuple[int, float]] = []
    for cid, energy in pairs:
        if float(energy) - emin > energy_window:
            break
        duplicate = False
        for prev, _ in kept:
            try:
                if rdMolAlign.GetBestRMS(probe_copy, ref_copy, prbId=cid,
                                         refId=prev, maxMatches=5000) <= 0.5:
                    duplicate = True
                    break
            except Exception:
                continue
        if not duplicate:
            kept.append((cid, energy))
        if len(kept) >= n_confs:
            break

    return [
        {
            "molblock": Chem.MolToMolBlock(molh, confId=cid),
            "energy_kcal": round(float(e), 3),
            "method": method,
        }
        for cid, e in kept
    ]


# --------------------------------------------------------------------------- #
# Structural alerts
# --------------------------------------------------------------------------- #

_PAINS_CATALOG = None

# Elements that almost never appear in the organic structure figures this tool
# targets, but that DECIMER hallucinates from stray glyphs/arrows.
_SUSPICIOUS_ELEMENTS = {
    81: "Tl", 92: "U", 82: "Pb", 32: "Ge", 80: "Hg",
    48: "Cd", 52: "Te", 51: "Sb", 46: "Pd", 78: "Pt",
}


def sa_score(mol: Chem.Mol) -> float | None:
    """Ertl & Schuffenhauer synthetic-accessibility score (1 easy ... 10 hard).

    Heuristic, not a synthesis plan: a high score means "look closer", not
    "impossible".
    """
    try:
        import os
        import sys

        from rdkit.Chem import RDConfig

        path = os.path.join(RDConfig.RDContribDir, "SA_Score")
        if path not in sys.path:
            sys.path.append(path)
        import sascorer

        return round(float(sascorer.calculateScore(mol)), 2)
    except Exception:
        return None



def _pains_catalog():
    global _PAINS_CATALOG
    if _PAINS_CATALOG is None:
        from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams

        params = FilterCatalogParams()
        params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
        _PAINS_CATALOG = FilterCatalog(params)
    return _PAINS_CATALOG


def structural_alerts(mol: Chem.Mol, props: dict[str, Any]) -> list[dict[str, str]]:
    """Chemically meaningful warnings a reviewer would care about."""
    out: list[dict[str, str]] = []

    if props["unspecified_stereocenters"]:
        out.append({
            "level": "warn",
            "text": f"{props['unspecified_stereocenters']} 个手性中心未指定（2D 图无楔形键）",
        })
    if props["fragments"] > 1:
        out.append({
            "level": "info",
            "text": f"含 {props['fragments']} 个片段（盐/溶剂）；3D 仅取最大片段",
        })
    if props["formal_charge"] != 0:
        out.append({"level": "info", "text": f"净电荷 {props['formal_charge']:+d}"})
    if props["mw"] > 500:
        out.append({"level": "info", "text": "MW > 500，超出 Lipinski 类药空间"})
    if props["logp"] > 5:
        out.append({"level": "info", "text": "cLogP > 5（Lipinski 违反）"})
    if props["tpsa"] > 140:
        out.append({"level": "info", "text": "TPSA > 140，口服吸收可能受限"})
    if any(a.GetNumRadicalElectrons() for a in mol.GetAtoms()):
        out.append({"level": "warn", "text": "含未配对电子（自由基）"})
    if any(a.GetAtomicNum() == 0 for a in mol.GetAtoms()):
        n = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() == 0)
        out.append({"level": "warn",
                    "text": f"含 {n} 个 R 基（*），且未能按甲基代入；3D 可能不可用"})
    if any(a.GetIsotope() for a in mol.GetAtoms()):
        out.append({"level": "warn",
                    "text": "含同位素标记（如 ²H）；识别图中这通常是噪声，请核对"})

    rare = sorted({a.GetSymbol() for a in mol.GetAtoms()
                   if a.GetAtomicNum() in _SUSPICIOUS_ELEMENTS})
    if rare:
        out.append({"level": "warn",
                    "text": f"含非常见元素 {'/'.join(rare)}；结构图中常为识别噪声，请核对"})

    try:
        if _pains_catalog().HasMatch(mol):
            out.append({"level": "warn", "text": "命中 PAINS 结构警示（可能干扰生物实验）"})
    except Exception:
        pass

    return out


# --------------------------------------------------------------------------- #
# One-shot analysis used by the API
# --------------------------------------------------------------------------- #

# RDKit is not fully thread-safe (InChI, depiction and embedding share global
# state), so all analyses are serialised. Individual analyses are sub-second;
# the HTTP layer stays concurrent for everything else.
_ANALYZE_LOCK = threading.Lock()


def analyze(smiles: str, with_3d: bool = True, n_conformers: int = 1) -> dict[str, Any]:
    with _ANALYZE_LOCK:
        return _analyze(smiles, with_3d, n_conformers)


def _analyze(smiles: str, with_3d: bool = True, n_conformers: int = 1) -> dict[str, Any]:
    mol, frag = normalize(smiles)
    orig_mol = mol
    r_count = sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() == 0)
    r_assumed = None
    if r_count:
        # Convention: undefined R groups are treated as methyls so that a 3D
        # conformer and descriptors can still be produced.
        try:
            mol = substitute_r_groups(orig_mol)
            frag = largest_fragment(mol)
            r_assumed = "methyl"
        except ChemError:
            mol, frag = orig_mol, largest_fragment(orig_mol)

    props = properties(mol)
    props["fragments"] = len(Chem.GetMolFrags(mol))
    props["wildcard"] = bool(r_count) and r_assumed is None
    props["r_groups"] = r_count
    props["r_assumed"] = r_assumed
    if r_assumed:
        props["markush_smiles"] = canonical_smiles(orig_mol)
    props["sa_score"] = sa_score(mol)
    if props["fragments"] > 1:
        props["largest_fragment_smiles"] = canonical_smiles(frag)

    alerts = structural_alerts(mol, props)
    abbreviations = find_abbreviations(smiles)
    if abbreviations:
        alerts.insert(0, {
            "level": "info",
            "text": f"缩写基团已展开：{', '.join(abbreviations)}",
        })
    if r_assumed:
        alerts.insert(0, {
            "level": "warn",
            "text": f"R 基未定义：{r_count} 个位置按甲基（CH3）代入计算 3D 与描述符",
        })

    out: dict[str, Any] = {
        "ok": True,
        "input": smiles.strip(),
        "properties": props,
        "alerts": alerts,
        "png_2d_b64": base64.b64encode(depict_2d_png(frag if props["fragments"] > 1 else mol)).decode(),
        "svg_2d": depict_2d_svg(frag if props["fragments"] > 1 else mol),
    }

    if r_count and r_assumed is None:
        # Substitution failed; keep a 2D-only representation.
        m2d = Chem.Mol(mol)
        rdDepictor.Compute2DCoords(m2d)
        out["molblock"] = Chem.MolToMolBlock(m2d)
        out["conformer_skipped"] = "markush"
        return out

    if with_3d:
        if n_conformers and n_conformers > 1:
            ensemble = embed_conformers(frag, n_conformers)
            n_atoms = frag.GetNumAtoms() + sum(a.GetTotalNumHs() for a in frag.GetAtoms())
            out["conformers"] = ensemble
            out["molblock"] = ensemble[0]["molblock"]
            out["conformer"] = {
                "energy_kcal": ensemble[0]["energy_kcal"],
                "method": ensemble[0]["method"],
                "atoms": n_atoms,
                "n_conformers": len(ensemble),
                "energy_range": [ensemble[0]["energy_kcal"],
                                 ensemble[-1]["energy_kcal"]],
            }
            return out

        conf = embed_3d(frag)
        out["molblock"] = conf.molblock
        out["conformer"] = {
            "energy_kcal": conf.energy_kcal,
            "method": conf.method,
            "atoms": conf.atoms,
            "warnings": conf.warnings,
        }
    return out
