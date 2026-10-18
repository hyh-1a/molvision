"""Split a figure containing several structures into individual crops.

Trained segmentation models (e.g. DECIMER-Segmentation) pin old TensorFlow
versions; for figure-style layouts a projection profile split is deterministic
and fast:

    ink mask -> horizontal whitespace bands (rows of panels)
             -> vertical whitespace bands within each row
             -> trim each cell to its ink bounding box

This handles the common 1xN / NxM grids found in papers, including compound
labels, without needing a model.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

MAX_STRUCTURES = 12


def _ink_mask(image: Image.Image) -> np.ndarray:
    gray = np.array(image.convert("L"))
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    # A photo of a dark screen would invert the meaning of "ink"; normalise so
    # that the mask always marks the drawing.
    if mask.mean() > 127:
        mask = cv2.bitwise_not(mask)
    return mask


def _bands(profile: np.ndarray, gap_ratio: float = 0.012,
           min_ratio: float = 0.03) -> list[list[int]]:
    """Contiguous ink bands along one axis, with small gaps and thin bands merged."""
    size = len(profile)
    ink = profile > max(1, int(size * 0.0005))

    bands: list[list[int]] = []
    i = 0
    while i < size:
        if ink[i]:
            j = i
            while j < size and ink[j]:
                j += 1
            bands.append([i, j])
            i = j
        else:
            i += 1

    if not bands:
        return [[0, size]]

    merged: list[list[int]] = [bands[0]]
    for b in bands[1:]:
        if b[0] - merged[-1][1] <= max(2, size * gap_ratio):
            merged[-1][1] = b[1]
        else:
            merged.append(b)

    # Labels ("1", "a", ...) often form their own thin band; glue them to the
    # neighbouring panel instead of emitting a separate crop.
    out: list[list[int]] = []
    for b in merged:
        if out and (b[1] - b[0]) < size * min_ratio:
            out[-1][1] = b[1]
        else:
            out.append(b)
    if len(out) > 1 and (out[0][1] - out[0][0]) < size * min_ratio:
        out[1][0] = out[0][0]
        out.pop(0)
    return out


def _has_table_rules(mask) -> bool:
    """True if the crop contains several near-full-width/height straight rules.

    Table borders survive the structure check and make DECIMER degenerate into
    hundreds of repeated fragments, so they must be rejected first.
    """
    h, w = mask.shape
    hk = max(20, int(w * 0.6))
    vk = max(20, int(h * 0.6))
    horiz = cv2.erode(mask, np.ones((1, hk), np.uint8))
    vert = cv2.erode(mask, np.ones((vk, 1), np.uint8))
    rows = int(np.count_nonzero(horiz.sum(axis=1)))
    cols = int(np.count_nonzero(vert.sum(axis=0)))
    # A table/grid has many rules in both directions; a framed figure has a
    # handful. Solid logos also trip the counter, which is fine — they are not
    # structures either.
    return rows >= 8 or cols >= 8


def looks_like_structure(img: Image.Image, min_stroke: int = 40,
                         min_ratio: float = 0.15) -> bool:
    """Cheap pre-check: does this crop contain bond-length strokes or only glyphs?

    Text crops make DECIMER decode up to its 302-token ceiling without ever
    emitting EOS (minutes per crop on CPU), so they must be rejected before
    inference.
    """
    gray = np.array(img.convert("L"))
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    if mask.mean() > 127:
        mask = cv2.bitwise_not(mask)

    if _has_table_rules(mask):
        return False

    total = float(mask.sum())
    if total <= 0:
        return False
    # Arrows / long straight lines put >15% of their ink on a single row or
    # column; molecular drawings spread ink over many rows/columns (<3%).
    peak = max(float(mask.sum(axis=1).max()), float(mask.sum(axis=0).max())) / total
    if peak > 0.15:
        return False

    count, _labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    total = float(mask.sum()) / 255.0
    if total <= 0:
        return False
    long_ink = 0.0
    for i in range(1, count):
        w, h, area = int(stats[i][2]), int(stats[i][3]), int(stats[i][4])
        if max(w, h) >= min_stroke:
            long_ink += area
    return long_ink / total >= min_ratio


def segment_image(image: Image.Image, max_structures: int = MAX_STRUCTURES) -> list[dict]:
    """Return [{'image': PIL.Image, 'bbox': [x, y, w, h]}] in reading order."""
    rgb = image.convert("RGB")
    w, h = rgb.size
    mask = _ink_mask(rgb)

    rows = _bands(mask.sum(axis=1))
    cells: list[list[int]] = []
    stroke_thresh = max(16, int(min(w, h) * 0.035))
    for r0, r1 in rows:
        row_mask = mask[r0:r1, :]
        for c0, c1 in _bands(row_mask.sum(axis=0)):
            cell = mask[r0:r1, c0:c1]
            ys, xs = np.nonzero(cell)
            if len(xs) == 0:
                continue
            x0, x1 = c0 + int(xs.min()), c0 + int(xs.max()) + 1
            y0, y1 = r0 + int(ys.min()), r0 + int(ys.max()) + 1
            if (x1 - x0) < w * 0.04 or (y1 - y0) < h * 0.04:
                continue

            # Refine: compound labels ("1", "3a") are short glyphs; bonds are
            # long strokes. Union only the long components so labels fall
            # outside the crop (DECIMER reads "1" as iodine otherwise).
            sub = mask[y0:y1, x0:x1]
            n, _labels, stats, _ = cv2.connectedComponentsWithStats(sub, 8)
            longs = [stats[i] for i in range(1, n)
                     if max(int(stats[i][2]), int(stats[i][3])) >= stroke_thresh]
            if longs:
                lx0 = min(int(b[0]) for b in longs)
                ly0 = min(int(b[1]) for b in longs)
                lx1 = max(int(b[0] + b[2]) for b in longs)
                ly1 = max(int(b[1] + b[3]) for b in longs)
                # Re-attach atom labels (O, N, H...) sitting on the strokes.
                # Horizontal margin is generous (labels like "HO" stick out to
                # the side); vertical margin is tight so compound numbers above
                # the structure are not pulled back in.
                mx = max(10, int((lx1 - lx0) * 0.08))
                my = max(8, int((ly1 - ly0) * 0.05))
                for i in range(1, n):
                    bx, by, bw, bh, _area = (int(v) for v in stats[i])
                    if (bx + bw >= lx0 - mx and bx <= lx1 + mx
                            and by + bh >= ly0 - my and by <= ly1 + my):
                        lx0, ly0 = min(lx0, bx), min(ly0, by)
                        lx1, ly1 = max(lx1, bx + bw), max(ly1, by + bh)
                x0, y0, x1, y1 = x0 + lx0, y0 + ly0, x0 + lx1, y0 + ly1
            cells.append([x0, y0, x1 - x0, y1 - y0])

    if not cells:
        return [{"image": rgb, "bbox": [0, 0, w, h]}]

    cells = cells[:max_structures]
    pad = max(6, int(min(w, h) * 0.012))
    crops = []
    for x, y, bw, bh in cells:
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(w, x + bw + pad), min(h, y + bh + pad)
        crops.append({
            "image": rgb.crop((x0, y0, x1, y1)),
            "bbox": [x0, y0, x1 - x0, y1 - y0],
        })
    return crops
