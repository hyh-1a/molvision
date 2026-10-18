"""End-to-end self-check for MolVision.

Run with the server up:

    python app/server.py --port 8765
    python scripts/selfcheck.py

Covers: health truthfulness, single/multi recognition, Markush handling,
cache behaviour, and concurrent analyses (RDKit lock).
"""
from __future__ import annotations

import base64
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parent.parent

PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def post(path: str, payload: dict, timeout: float = 300.0) -> tuple[int, dict]:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return json.loads(r.read())


def img_b64(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def main() -> None:
    from rdkit import Chem

    print("health")
    h = get("/api/health")
    check("recognizer available", h.get("recognizer") is True, str(h))
    check("model loaded", h.get("model_loaded") is True, str(h))

    print("analysis")
    code, a = post("/api/analyze", {"smiles": "Cn1cnc2c1c(=O)n(C)c(=O)n2C"})
    check("caffeine 200", code == 200 and a.get("ok"), str(a)[:200])
    check("caffeine formula", a["properties"]["formula"] == "C8H10N4O2", a["properties"].get("formula"))
    check("caffeine MW", abs(a["properties"]["mw"] - 194.194) < 0.01, a["properties"].get("mw"))
    check("conformer present", "conformer" in a)

    code, m = post("/api/analyze", {"smiles": "*c1nnc(OCC)o1"})
    check("markush parses", code == 200 and m.get("ok"), str(m)[:200])
    check("markush r assumed methyl", m["properties"].get("r_assumed") == "methyl")
    check("markush 3d present", "conformer" in m)
    check("markush keeps original smiles",
          m["properties"].get("markush_smiles") == "*c1nnc(OCC)o1")
    check("markush substituted to methyl",
          m["properties"]["canonical_smiles"] == "CCOc1nnc(C)o1",
          m["properties"].get("canonical_smiles"))
    check("markush has 3d molblock", "M  END" in m.get("molblock", ""))

    code, ab = post("/api/analyze", {"smiles": "C[Ph]"})
    check("abbrev Ph expands",
          code == 200 and ab["properties"]["canonical_smiles"] == "Cc1ccccc1",
          str(ab)[:200])
    code, ab2 = post("/api/analyze", {"smiles": "CC(=O)Nc1ccc([Me])cc1"})
    check("abbrev Me expands",
          code == 200 and ab2["properties"]["canonical_smiles"] == "CC(=O)Nc1ccc(C)cc1",
          str(ab2)[:200])

    code, bad = post("/api/analyze", {"smiles": "C1CC"})
    check("bad smiles rejected", code == 422 and not bad.get("ok"), f"{code} {bad}")

    print("single-image recognition")
    code, s = post("/api/recognize", {"image": img_b64(ROOT / "samples" / "aspirin.png")})
    check("aspirin recognised", code == 200 and s["count"] == 1 and s["structures"][0]["ok"], str(s)[:200])
    got = Chem.MolToSmiles(Chem.MolFromSmiles(s["structures"][0]["smiles"])) if s.get("count") else ""
    check("aspirin smiles", got == "CC(=O)Oc1ccccc1C(=O)O", got)
    check("inchikey present", bool(s["structures"][0].get("inchikey")))

    print("multi-structure recognition")
    code, mm = post("/api/recognize", {"image": img_b64(ROOT / "samples" / "multi_4.png")})
    check("4 structures", code == 200 and mm["count"] == 4, str(mm.get("count")))
    got = {Chem.MolToInchiKey(Chem.MolFromSmiles(x["smiles"]))
           for x in mm["structures"] if x.get("ok")}
    want = {Chem.MolToInchiKey(Chem.MolFromSmiles(s)) for s in [
        "CC(=O)Oc1ccccc1C(=O)O",
        "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
        "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
        "CC(=O)Nc1ccc(O)cc1",
    ]}
    check("all four correct (InChIKey)", got == want, str(got ^ want))

    print("cache")
    t0 = time.time()
    _, c1 = post("/api/recognize", {"image": img_b64(ROOT / "samples" / "multi_4.png")})
    dt = time.time() - t0
    check("cache hit", c1.get("cached") is True, str(c1.get("cached")))
    check("cache fast", dt < 1.0, f"{dt:.2f}s")

    print("concurrency (RDKit analysis lock)")
    smiles_list = ["CCO", "c1ccccc1", "CC(=O)O", "Cn1cnc2c1c(=O)n(C)c(=O)n2C"] * 3

    def one(smi: str):
        code, data = post("/api/analyze", {"smiles": smi}, timeout=120)
        return code == 200 and data.get("ok")

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(one, smiles_list))
    check("12 parallel analyses", all(results), f"{sum(results)}/12")
    print(f"        ({time.time() - t0:.1f}s wall)")

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
