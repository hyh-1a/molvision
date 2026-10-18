"""Minimal HTTP server for MolVision.

Stdlib only (no FastAPI/Flask) so the demo starts in one command and has
nothing to break. Serves the static front-end and two JSON endpoints:

    POST /api/analyze    {"smiles": "..."}   -> full analysis
    POST /api/recognize  {"image": "<b64>"}  -> {"smiles": "..."} (needs DECIMER)
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

sys.path.insert(0, str(ROOT))

from app.chem import ChemError, analyze  # noqa: E402


def _recognizer():
    """Lazy import: the server still works if DECIMER is missing."""
    try:
        from app.recognize import recognize_image
        return recognize_image
    except Exception as exc:  # pragma: no cover - depends on env
        print(f"[warn] recognizer unavailable: {exc}", file=sys.stderr)
        return None


def _model_loaded() -> bool:
    """True only once the weights are actually in memory."""
    try:
        from app.recognize import model_loaded
        return bool(model_loaded())
    except Exception:  # pragma: no cover - depends on env
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = "MolVision/0.2"

    # -- helpers ---------------------------------------------------------- #
    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > 40 * 1024 * 1024:
            raise ValueError("payload too large")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def log_message(self, fmt: str, *args) -> None:  # quieter logs
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # -- routes ----------------------------------------------------------- #
    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)

        if path == "/api/health":
            return self._json(200, {
                "ok": True,
                "recognizer": _recognizer() is not None,
                "model_loaded": _model_loaded(),
            })

        if path in ("/", "/index.html"):
            return self._serve(WEB / "index.html", "text/html; charset=utf-8")

        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            target = (WEB / rel).resolve()
            if not str(target).startswith(str(WEB.resolve())):
                return self._json(403, {"ok": False, "error": "forbidden"})
            return self._serve(target, None)

        if path.startswith("/samples/"):
            rel = path[len("/samples/"):]
            base = (ROOT / "samples").resolve()
            target = (base / rel).resolve()
            if not str(target).startswith(str(base)):
                return self._json(403, {"ok": False, "error": "forbidden"})
            return self._serve(target, None)

        return self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._body()
        except Exception as exc:
            return self._json(400, {"ok": False, "error": f"bad request: {exc}"})

        if path == "/api/analyze":
            smiles = (payload.get("smiles") or "").strip()
            try:
                n_conf = int(payload.get("n_conformers", 1) or 1)
            except (TypeError, ValueError):
                n_conf = 1
            n_conf = max(1, min(20, n_conf))
            try:
                result = analyze(smiles, n_conformers=n_conf)
            except ChemError as exc:
                return self._json(422, {"ok": False, "error": str(exc)})
            except Exception as exc:
                return self._json(500, {"ok": False, "error": f"internal error: {exc}"})
            return self._json(200, result)

        if path == "/api/pdf":
            fn = _recognizer()
            if fn is None:
                return self._json(503, {"ok": False, "error": "识别模块未就绪"})
            pdf_b64 = payload.get("pdf") or ""
            if not pdf_b64:
                return self._json(400, {"ok": False, "error": "no pdf"})
            try:
                raw = base64.b64decode(pdf_b64.split(",")[-1])
                from app.pdf import page_to_png, render_pdf

                pages, skipped = render_pdf(
                    raw,
                    dpi=int(payload.get("dpi", 200)),
                    max_pages=int(payload.get("max_pages", 20)),
                    figure_only=bool(payload.get("figure_only", True)),
                )
            except ValueError as exc:
                return self._json(422, {"ok": False, "error": str(exc)})
            except Exception as exc:
                return self._json(500, {"ok": False, "error": f"PDF 解析失败: {exc}"})

            results = []
            for page in pages:
                try:
                    out = fn(page_to_png(page))
                    results.append({"index": page["index"] + 1,
                                    "structures": out["structures"]})
                except Exception as exc:  # noqa: BLE001
                    results.append({"index": page["index"] + 1,
                                    "structures": [], "error": str(exc)})
            total = sum(len(r["structures"]) for r in results)
            return self._json(200, {"ok": True, "pages": results,
                                    "count": total, "skipped_pages": skipped})

        if path == "/api/recognize":
            fn = _recognizer()
            if fn is None:
                return self._json(
                    503,
                    {"ok": False, "error": "识别模块未就绪（DECIMER 加载失败）。可先直接输入 SMILES。"},
                )
            image_b64 = payload.get("image") or ""
            if not image_b64:
                return self._json(400, {"ok": False, "error": "no image"})
            try:
                raw = base64.b64decode(image_b64.split(",")[-1])
                out = fn(raw, single=bool(payload.get("single", False)))
            except ChemError as exc:
                return self._json(422, {"ok": False, "error": str(exc)})
            except Exception as exc:
                return self._json(500, {"ok": False, "error": f"识别失败: {exc}"})
            return self._json(200, out)

        return self._json(404, {"ok": False, "error": "not found"})

    def _serve(self, path: Path, content_type: str | None) -> None:
        if not path.is_file():
            return self._json(404, {"ok": False, "error": "not found"})
        data = path.read_bytes()
        ctype = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"MolVision running: http://{args.host}:{args.port}", flush=True)

    # Cold-loading DECIMER takes ~90 s; warm it up ahead of a demo.
    if os.environ.get("MOLVISION_PRELOAD", "").lower() in ("1", "true", "yes"):
        import threading

        def _warm() -> None:
            print("[preload] loading recognizer...", flush=True)
            try:
                from app.recognize import _get_model, recognize_smiles
                _get_model()
                # The first TF inference costs ~80 s of graph warm-up; burn it
                # on a bundled sample so the live demo's first upload is fast.
                sample = ROOT / "samples" / "aspirin.png"
                if sample.exists():
                    recognize_smiles(sample.read_bytes())
                print("[preload] recognizer ready", flush=True)
            except Exception as exc:  # pragma: no cover - env dependent
                print(f"[preload] recognizer unavailable: {exc}", flush=True)

        threading.Thread(target=_warm, daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
