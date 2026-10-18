"""Evaluate the running server against the golden set.

    python scripts/evaluate.py [--out data/eval_report.json]

Compares recognised structures with the expected answers by InChIKey
(canonical SMILES for wildcard/Markush structures, where InChIKey is empty).
"""
from __future__ import annotations

import argparse
import base64
import json
import time
import urllib.request
from pathlib import Path

from rdkit import Chem

BASE = "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "samples" / "golden"


def molkey(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return "INVALID:" + smiles
    try:
        ik = Chem.MolToInchiKey(mol)
        if ik:
            return ik
    except Exception:
        pass
    return "SMI:" + Chem.MolToSmiles(mol, canonical=True)


def conn_key(smiles: str) -> str:
    """InChIKey with stereo removed: catches E/Z over-specification separately."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return "INVALID:" + smiles
    m = Chem.Mol(mol)
    Chem.RemoveStereochemistry(m)
    try:
        ik = Chem.MolToInchiKey(m)
        if ik:
            return ik
    except Exception:
        pass
    return "SMI:" + Chem.MolToSmiles(m, canonical=True)


def post(path: str, payload: dict, timeout: float = 600.0) -> dict:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "eval_report.json"))
    ap.add_argument("--only", default="", help="comma separated case names")
    args = ap.parse_args()

    expected = json.loads((GOLDEN / "expected.json").read_text(encoding="utf-8"))
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    if only:
        expected = {k: v for k, v in expected.items() if k in only}

    rows = []
    tp = fp = fn = 0
    strict_total = strict_exact = 0
    conn_strict_exact = 0
    t_all = 0.0

    for name, spec in expected.items():
        img = (GOLDEN / name).read_bytes()
        b64 = "data:image/png;base64," + base64.b64encode(img).decode()
        t0 = time.time()
        try:
            data = post("/api/recognize", {"image": b64})
        except Exception as exc:  # noqa: BLE001
            rows.append({"case": name, "error": str(exc)})
            print(f"{name:28s} ERROR {exc}")
            continue
        dt = time.time() - t0
        t_all += dt

        got_smiles = [s["smiles"] for s in data.get("structures", []) if s.get("ok")]
        got = {molkey(s) for s in got_smiles}
        want = {molkey(s) for s in spec["expect"]}
        conn_got = {conn_key(s) for s in got_smiles}
        conn_want = {conn_key(s) for s in spec["expect"]}
        tp += len(got & want)
        fp += len(got - want)
        fn += len(want - got)
        exact = got == want
        conn_exact = conn_got == conn_want
        if spec.get("strict", True):
            strict_total += 1
            strict_exact += int(exact)
            conn_strict_exact += int(conn_exact)

        rows.append({
            "case": name,
            "expect": spec["expect"],
            "got": got_smiles,
            "count": data.get("count", 0),
            "exact": exact,
            "connectivity_exact": conn_exact,
            "strict": spec.get("strict", True),
            "cached": data.get("cached", False),
            "seconds": round(dt, 2),
            "note": spec.get("note", ""),
        })
        flag = "OK " if exact else ("CONN" if conn_exact else "BAD")
        print(f"{flag} {name:28s} n={data.get('count', 0)} "
              f"{'cached' if data.get('cached') else f'{dt:.1f}s'}  "
              f"got={got_smiles}")

    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    report = {
        "cases": len(rows),
        "strict_cases": strict_total,
        "strict_exact": strict_exact,
        "strict_accuracy": round(strict_exact / strict_total, 3) if strict_total else 0,
        "connectivity_exact": conn_strict_exact,
        "connectivity_accuracy": round(conn_strict_exact / strict_total, 3) if strict_total else 0,
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(2 * precision * recall / (precision + recall), 3)
              if precision + recall else 0.0,
        "avg_seconds": round(t_all / max(1, len(rows)), 2),
        "rows": rows,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"strict exact: {strict_exact}/{strict_total} "
          f"({report['strict_accuracy'] * 100:.0f}%)")
    print(f"connectivity exact (stereo stripped): {conn_strict_exact}/{strict_total} "
          f"({report['connectivity_accuracy'] * 100:.0f}%)")
    print(f"structures: TP={tp} FP={fp} FN={fn}  "
          f"precision={precision:.2f} recall={recall:.2f} f1={report['f1']:.2f}")
    print(f"avg latency: {report['avg_seconds']}s")
    print(f"report: {out}")


if __name__ == "__main__":
    main()
