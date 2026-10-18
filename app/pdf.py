"""Render PDF pages to PIL images for structure recognition."""
from __future__ import annotations

import io
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image


def _ink_ratio(img: Image.Image) -> float:
    gray = img.convert("L")
    hist = gray.histogram()
    dark = sum(hist[:200])
    return dark / max(1, img.width * img.height)


def figure_score(img: Image.Image) -> float:
    """Fraction of ink contained in long strokes (bonds, arrows, frame lines).

    Body-text pages are made of short glyphs, so their score is near zero;
    structure figures score high. Used to skip prose pages before recognition.
    """
    import cv2
    import numpy as np

    gray = np.array(img.convert("L"))
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    if mask.mean() > 127:
        mask = cv2.bitwise_not(mask)

    count, _labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    total = float(mask.sum()) / 255.0
    if total <= 0:
        return 0.0
    threshold = max(12, int(min(img.size) * 0.02))
    long_ink = 0.0
    for i in range(1, count):
        w, h, area = int(stats[i][2]), int(stats[i][3]), int(stats[i][4])
        if max(w, h) >= threshold:
            long_ink += area
    return long_ink / total


def render_pdf(source, dpi: int = 200, max_pages: int | None = None,
               skip_blank: bool = True, figure_only: bool = True
               ) -> tuple[list[dict], list[int]]:
    """Return ([page dicts], [skipped page numbers]).

    ``figure_only`` skips prose pages: full-text pages are made of short glyphs,
    and segmenting them produces dozens of meaningless "structures" that cost
    ~5 s each to reject.
    """
    if isinstance(source, (bytes, bytearray)):
        doc = fitz.open(stream=bytes(source), filetype="pdf")
    else:
        doc = fitz.open(str(source))

    if doc.needs_pass:
        doc.close()
        raise ValueError("PDF 已加密，无法读取")

    pages: list[dict] = []
    skipped: list[int] = []
    try:
        for i, page in enumerate(doc):
            if max_pages is not None and len(pages) >= max_pages:
                break

            if figure_only:
                chars = len(page.get_text())
                drawings = len(page.get_drawings())
                images = len(page.get_images(full=True))
                is_figure = (drawings >= 60
                             or (images >= 1 and chars < 2000)
                             or chars < 800)
                if not is_figure:
                    skipped.append(i + 1)
                    continue

            pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            if skip_blank and _ink_ratio(img) < 0.0008:
                skipped.append(i + 1)
                continue
            pages.append({"index": i, "image": img, "size": (pix.width, pix.height)})
    finally:
        doc.close()

    if not pages:
        raise ValueError("PDF 中没有可识别的内容页")
    return pages, skipped


def page_to_png(page: dict, max_side: int = 2400) -> bytes:
    """Downscale very large renders before recognition, return PNG bytes."""
    img = page["image"]
    if max(img.size) > max_side:
        scale = max_side / max(img.size)
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
