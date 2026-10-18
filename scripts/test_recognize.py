"""Round-trip test: rendered structure image -> DECIMER -> SMILES."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.recognize import recognize_smiles  # noqa: E402

EXPECTED = {
    "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
    "caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
    "ibuprofen": "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    "alanine": "C[C@@H](N)C(=O)O",
    "paracetamol": "CC(=O)Nc1ccc(O)cc1",
    "glucose": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
}


def main() -> None:
    from rdkit import Chem

    hits = 0
    total = 0
    for name, expected in EXPECTED.items():
        path = Path(__file__).resolve().parent.parent / "samples" / f"{name}.png"
        if not path.exists():
            continue
        total += 1
        t0 = time.time()
        try:
            out = recognize_smiles(path.read_bytes())
            got = out["smiles"]
            want = Chem.MolToSmiles(Chem.MolFromSmiles(expected), canonical=True)
            ok = got == want
            hits += int(ok)
            print(f"[{'OK' if ok else 'BAD'}] {name:12s} {time.time()-t0:5.1f}s  {got}")
            if not ok:
                print(f"      expected: {want}")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERR] {name:12s} {exc}")
    print(f"\n{hits}/{total} exact match")


if __name__ == "__main__":
    main()
