"""P0 checks: health truthfulness, result cache, concurrent inference safety."""
from __future__ import annotations

import base64
import io
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

BASE = "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parent.parent


def _post(path: str, payload: dict, timeout: float = 300.0) -> tuple[dict, float]:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read()), time.time() - t0


def health() -> dict:
    with urllib.request.urlopen(BASE + "/api/health", timeout=10) as r:
        return json.loads(r.read())


def b64(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def variant(path: Path, angle: float) -> str:
    """Same molecule, different bytes, so the cache misses."""
    img = Image.open(path).convert("RGB").rotate(angle, fillcolor=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    print("health:", health())

    # 1) cache: same bytes twice
    img = b64(ROOT / "samples" / "caffeine.png")
    first, t1 = _post("/api/recognize", {"image": img})
    second, t2 = _post("/api/recognize", {"image": img})
    print(f"cache: first={t1:.2f}s cached={first.get('cached')} | "
          f"second={t2:.2f}s cached={second.get('cached')}")
    assert first["ok"] and second["ok"]
    assert second.get("cached") is True, "second call should hit the cache"
    assert t2 < 1.0, f"cached call too slow: {t2:.2f}s"

    # 2) concurrency: distinct images, four at once
    files = ["alanine.png", "glucose.png", "ibuprofen.png", "paracetamol.png"]
    payloads = [variant(ROOT / "samples" / f, 0.3 * (i + 1)) for i, f in enumerate(files)]

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda p: _post("/api/recognize", {"image": p})[0], payloads))
    wall = time.time() - t0
    print(f"concurrency: {len(results)} requests, wall={wall:.1f}s")
    for r in results:
        print("  ", r.get("ok"), "count=", r.get("count"))
        assert r.get("ok") and r.get("count", 0) >= 1, r

    # 3) health still truthful after load
    h = health()
    print("health after load:", h)
    assert h["recognizer"] is True and h["model_loaded"] is True
    print("\nP0 OK")


if __name__ == "__main__":
    main()
