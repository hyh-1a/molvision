"""Multi-structure check: a 2x2 figure should yield four correct molecules."""
from __future__ import annotations

import base64
import json
import time
import urllib.request
from pathlib import Path

from rdkit import Chem

BASE = "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parent.parent

EXPECTED = [
    "CC(=O)Oc1ccccc1C(=O)O",
    "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
    "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    "CC(=O)Nc1ccc(O)cc1",
]


def post(path: str, payload: dict, timeout: float = 300.0) -> tuple[dict, float]:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read()), time.time() - t0


def main() -> None:
    img = "data:image/png;base64," + base64.b64encode(
        (ROOT / "samples" / "multi_4.png").read_bytes()
    ).decode()
    data, dt = post("/api/recognize", {"image": img})
    print(f"count={data['count']} in {dt:.1f}s cached={data.get('cached')}")
    assert data["count"] == 4, data

    wants = [Chem.MolToSmiles(Chem.MolFromSmiles(s), canonical=True) for s in EXPECTED]
    got = [s.get("smiles") for s in data["structures"]]
    for i, (g, w) in enumerate(zip(got, wants)):
        print(f"  #{i} {'OK ' if g == w else 'BAD'} {g}")
        assert g == w, f"#{i}: got {g}, want {w}"
    print("\nMULTI OK")


if __name__ == "__main__":
    main()
