"""PDF -> per-page structure recognition -> validation report (CSV / SDF / JSON).

Pages are rendered locally and POSTed one at a time, so progress is visible and
a slow page cannot hide the rest. Requires the MolVision server:

    python app/server.py --port 8765
    python scripts/run_pdf.py paper.pdf --out data/pdf_out
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.pdf import page_to_png, render_pdf  # noqa: E402

BASE = "http://127.0.0.1:8765"
COLS = [
    "source", "page", "ok", "smiles", "inchikey", "formula", "mw", "logp", "tpsa",
    "hbd", "hba", "rotatable", "rings", "charge", "stereo",
    "undefined_stereo", "sa_score", "alerts", "duplicate", "error",
]


def post(path: str, payload: dict, timeout: float = 900.0) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--out", default="data/pdf_out")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--max-pages", type=int, default=20)
    ap.add_argument("--all-pages", action="store_true",
                    help="also process prose pages (slow, mostly noise)")
    ap.add_argument("--pages", default="",
                    help="comma separated page numbers, e.g. 4,6,8")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    t_all = time.time()
    pages, skipped = render_pdf(
        args.pdf, dpi=args.dpi, max_pages=args.max_pages,
        figure_only=not args.all_pages,
    )
    if args.pages:
        wanted = {int(x) for x in args.pages.split(",") if x.strip()}
        pages = [p for p in pages if p["index"] + 1 in wanted]
        if not pages:
            raise SystemExit(f"指定页 {sorted(wanted)} 中没有可处理页")
    print(f"pages={len(pages)} skipped={len(skipped)} skipped_ids={skipped}", flush=True)

    rows: list[dict] = []
    seen: dict[str, str] = {}
    for page in pages:
        t0 = time.time()
        png = page_to_png(page)
        try:
            data = post("/api/recognize", {
                "image": "data:image/png;base64," + base64.b64encode(png).decode()
            })
        except Exception as exc:  # noqa: BLE001
            print(f"p{page['index'] + 1}: PAGE FAILED ({exc})", flush=True)
            rows.append({"source": f"p{page['index'] + 1}", "page": page["index"] + 1,
                         "ok": False, "error": str(exc)})
            continue

        print(f"p{page['index'] + 1}: {data.get('count', 0)} structures "
              f"({time.time() - t0:.1f}s)", flush=True)

        for i, s in enumerate(data.get("structures", [])):
            tag = f"p{page['index'] + 1}-{i + 1}"
            if not s.get("ok"):
                rows.append({"source": tag, "page": page["index"] + 1, "ok": False,
                             "error": s.get("error", "recognition failed")})
                print(f"    {tag}: failed ({s.get('error')})", flush=True)
                continue
            try:
                a = post("/api/analyze", {"smiles": s["smiles"]})
            except Exception as exc:  # noqa: BLE001
                rows.append({"source": tag, "page": page["index"] + 1, "ok": False,
                             "smiles": s["smiles"], "error": str(exc)})
                print(f"    {tag}: analysis failed ({exc})", flush=True)
                continue

            p = a["properties"]
            dup = p["canonical_smiles"] in seen
            seen.setdefault(p["canonical_smiles"], tag)
            rows.append({
                "source": tag,
                "page": page["index"] + 1,
                "ok": True,
                "smiles": p["canonical_smiles"],
                "inchikey": p.get("inchikey", ""),
                "formula": p["formula"],
                "mw": p["mw"],
                "logp": p["logp"],
                "tpsa": p["tpsa"],
                "hbd": p["hbd"],
                "hba": p["hba"],
                "rotatable": p["rotatable_bonds"],
                "rings": p["rings"],
                "charge": p["formal_charge"],
                "stereo": p["stereocenters"],
                "undefined_stereo": p["unspecified_stereocenters"],
                "sa_score": p.get("sa_score"),
                "alerts": " | ".join(x["text"] for x in a.get("alerts", [])),
                "duplicate": dup,
                "molblock": a.get("molblock", ""),
            })
            print(f"    {tag}: {p['canonical_smiles']}" + ("  [dup]" if dup else ""), flush=True)

    rows.sort(key=lambda r: (int(r.get("page", 0)),
                             int(str(r.get("source", "p0-0")).split("-")[-1] or 0)))
    with open(out / "results.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    blocks = []
    for r in rows:
        if not r.get("ok") or r.get("duplicate") or not r.get("molblock"):
            continue
        block = r["molblock"].rstrip() + f"\n> <SOURCE>\n{r['source']}\n"
        if r.get("undefined_stereo"):
            block += f"> <STEREO>\nunspecified ({r['undefined_stereo']} centre(s))\n"
        blocks.append(block + "\n$$$$\n")
    (out / "structures.sdf").write_text("".join(blocks), encoding="utf-8")

    ok_rows = [r for r in rows if r.get("ok")]
    summary = {
        "pdf": str(args.pdf),
        "pages": len(pages),
        "skipped_pages": skipped,
        "structures": len(rows),
        "recognised": len(ok_rows),
        "failed": len(rows) - len(ok_rows),
        "unique": len({r["smiles"] for r in ok_rows}),
        "with_alerts": sum(1 for r in ok_rows if r.get("alerts")),
        "seconds": round(time.time() - t_all, 1),
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"CSV: {out / 'results.csv'}\nSDF: {out / 'structures.sdf'}", flush=True)


if __name__ == "__main__":
    main()
