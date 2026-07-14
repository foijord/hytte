"""Fit oriented boxes to OSM building footprints, heighted from DOM-DTM.

Simple footprints get one min-area box. Footprints that a single box fits
poorly (L/Z/T-shapes) are decomposed into several boxes: the footprint is
rasterized in its dominant-angle frame and greedily covered with maximal
rectangles. Part ids are "<osmid>:<n>".

Reads data/osm_buildings.json (Overpass, WGS84), data/dtm_25cm.tif,
data/dom_25cm.tif and data/property_437_109.geojson.
Writes web/buildings.json.
"""
import json
import os

import numpy as np
import tifffile
from PIL import Image, ImageDraw
from pyproj import Transformer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = 0.25
XMIN, YMIN, XMAX, YMAX = 71128.0, 6457799.0, 71728.0, 6458399.0
GRID = 0.1          # raster resolution for footprint analysis, meters
IOU_SINGLE = 0.82   # min IoU for accepting a single-box fit
MIN_PART_M2 = 4.0   # discard decomposition parts smaller than this
MAX_PARTS = 6

dtm = tifffile.imread(os.path.join(ROOT, "data", "dtm_25cm.tif"))
dom = tifffile.imread(os.path.join(ROOT, "data", "dom_25cm.tif"))
tr = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)

parcel = json.load(open(os.path.join(ROOT, "data", "property_437_109.geojson"), encoding="utf-8"))
parcel_ring = np.array(parcel["features"][0]["geometry"]["coordinates"][0])


def point_in_poly(x, y, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def convex_hull(pts):
    pts = sorted(set(map(tuple, pts)))
    if len(pts) <= 2:
        return np.array(pts)
    def half(points):
        h = []
        for p in points:
            while len(h) >= 2:
                ax, ay = h[-1][0] - h[-2][0], h[-1][1] - h[-2][1]
                bx, by = p[0] - h[-2][0], p[1] - h[-2][1]
                if ax * by - ay * bx > 0:
                    break
                h.pop()
            h.append(p)
        return h
    lower, upper = half(pts), half(reversed(pts))
    return np.array(lower[:-1] + upper[:-1])


def min_area_rect(pts):
    hull = convex_hull(pts)
    best = None
    for i in range(len(hull)):
        edge = hull[(i + 1) % len(hull)] - hull[i]
        ang = np.arctan2(edge[1], edge[0])
        c, s = np.cos(-ang), np.sin(-ang)
        rot = pts @ np.array([[c, -s], [s, c]]).T
        w = rot[:, 0].max() - rot[:, 0].min()
        d = rot[:, 1].max() - rot[:, 1].min()
        if best is None or w * d < best[0]:
            cx = (rot[:, 0].max() + rot[:, 0].min()) / 2
            cy = (rot[:, 1].max() + rot[:, 1].min()) / 2
            cb, sb = np.cos(ang), np.sin(ang)
            center = np.array([cx * cb - cy * sb, cx * sb + cy * cb])
            best = (w * d, center, w, d, ang)
    _, center, w, d, ang = best
    if d > w:
        w, d, ang = d, w, ang + np.pi / 2
    ang = (ang + np.pi / 2) % np.pi - np.pi / 2
    return center, w, d, ang


def dominant_angle(pts):
    """Angle of the longest footprint edge, radians."""
    best_len, best_ang = 0.0, 0.0
    for i in range(len(pts)):
        d = pts[(i + 1) % len(pts)] - pts[i]
        l = np.hypot(*d)
        if l > best_len:
            best_len, best_ang = l, np.arctan2(d[1], d[0])
    return best_ang


def poly_area(pts):
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def rasterize(pts, grid=GRID, pad=2):
    """Rasterize polygon; returns (mask, xmin, ymin) of the raster frame."""
    x0, y0 = pts[:, 0].min() - pad * grid, pts[:, 1].min() - pad * grid
    w = int(np.ceil((pts[:, 0].max() - x0) / grid)) + pad
    h = int(np.ceil((pts[:, 1].max() - y0) / grid)) + pad
    img = Image.new("L", (w, h), 0)
    ImageDraw.Draw(img).polygon([((x - x0) / grid, (y - y0) / grid) for x, y in pts], fill=1)
    return np.array(img, dtype=bool), x0, y0


def largest_rectangle(mask):
    """Largest all-True axis-aligned rectangle. Returns (area, r0, c0, r1, c1) exclusive end."""
    rows, cols = mask.shape
    heights = np.zeros(cols, dtype=int)
    best = (0, 0, 0, 0, 0)
    for r in range(rows):
        heights = np.where(mask[r], heights + 1, 0)
        stack = []  # (start_col, height)
        for c in range(cols + 1):
            h = heights[c] if c < cols else 0
            start = c
            while stack and stack[-1][1] >= h:
                sc, sh = stack.pop()
                area = sh * (c - sc)
                if area > best[0]:
                    best = (area, r - sh + 1, sc, r + 1, c)
                start = sc
            if not stack or h > 0:
                stack.append((start, h))
    return best


def decompose(pts):
    """Greedy rectangle cover of a footprint in its dominant-angle frame.
    Returns list of (center_EN, w, d, angle)."""
    ang = dominant_angle(pts)
    c, s = np.cos(-ang), np.sin(-ang)
    rot = pts @ np.array([[c, -s], [s, c]]).T
    mask, x0, y0 = rasterize(rot)
    total = mask.sum()
    parts = []
    work = mask.copy()
    cb, sb = np.cos(ang), np.sin(ang)
    while len(parts) < MAX_PARTS and work.sum() > 0.06 * total:
        area, r0, c0, r1, c1 = largest_rectangle(work)
        if area * GRID * GRID < MIN_PART_M2:
            break
        work[r0:r1, c0:c1] = False
        # raster frame: cols = rotated x, rows = rotated y
        rx = x0 + (c0 + c1) / 2 * GRID
        ry = y0 + (r0 + r1) / 2 * GRID
        w = (c1 - c0) * GRID
        d = (r1 - r0) * GRID
        a = ang
        if d > w:
            w, d, a = d, w, a + np.pi / 2
        a = (a + np.pi / 2) % np.pi - np.pi / 2
        center = np.array([rx * cb - ry * sb, rx * sb + ry * cb])
        parts.append((center, w, d, a))
    return parts


def rect_iou(pts, center, w, d, ang):
    """IoU between footprint polygon and an oriented rect, on a raster."""
    c, s = np.cos(ang), np.sin(ang)
    hw, hd = w / 2, d / 2
    corners = np.array([
        center + [dx * c - dy * s, dx * s + dy * c]
        for dx, dy in ((-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd))
    ])
    allpts = np.vstack([pts, corners])
    x0, y0 = allpts[:, 0].min() - GRID, allpts[:, 1].min() - GRID
    W = int((allpts[:, 0].max() - x0) / GRID) + 2
    H = int((allpts[:, 1].max() - y0) / GRID) + 2
    def rast(poly):
        img = Image.new("L", (W, H), 0)
        ImageDraw.Draw(img).polygon([((x - x0) / GRID, (y - y0) / GRID) for x, y in poly], fill=1)
        return np.array(img, dtype=bool)
    a, b = rast(pts), rast(corners)
    return (a & b).sum() / max((a | b).sum(), 1)


def sample_terrain(poly_en):
    """base, height sampled from DTM/DOM inside a polygon (EN coords)."""
    px = [((e - XMIN) / RES, (YMAX - n) / RES) for e, n in poly_en]
    mimg = Image.new("L", (2400, 2400), 0)
    ImageDraw.Draw(mimg).polygon(px, fill=1)
    m = np.array(mimg, dtype=bool)
    if m.sum() < 4:
        return None
    base = float(np.percentile(dtm[m], 10))
    roof = float(np.percentile(dom[m], 95))
    return base, max(roof - base, 2.2)


def rect_corners(center, w, d, ang):
    c, s = np.cos(ang), np.sin(ang)
    hw, hd = w / 2, d / 2
    return [
        [center[0] + dx * c - dy * s, center[1] + dx * s + dy * c]
        for dx, dy in ((-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd))
    ]


def main():
    osm = json.load(open(os.path.join(ROOT, "data", "osm_buildings.json"), encoding="utf-8"))
    out = []
    skipped = 0
    n_multi = 0
    for el in osm.get("elements", []):
        geom = el.get("geometry", [])
        if len(geom) < 4:
            skipped += 1
            continue
        lons = [g["lon"] for g in geom[:-1]]
        lats = [g["lat"] for g in geom[:-1]]
        es, ns = tr.transform(lons, lats)
        pts = np.column_stack([es, ns])
        cE, cN = pts[:, 0].mean(), pts[:, 1].mean()
        if not (XMIN + 5 < cE < XMAX - 5 and YMIN + 5 < cN < YMAX - 5):
            skipped += 1
            continue

        center, w, d, ang = min_area_rect(pts)
        iou = rect_iou(pts, center, w, d, ang)
        if iou >= IOU_SINGLE:
            rects = [(center, w, d, ang)]
        else:
            rects = decompose(pts) or [(center, w, d, ang)]
            if len(rects) > 1:
                n_multi += 1

        tags = el.get("tags", {})
        whole = sample_terrain(pts)
        for k, (rc, rw, rd, ra) in enumerate(rects):
            corners = rect_corners(rc, rw, rd, ra)
            st = sample_terrain(corners) or whole
            if st is None:
                continue
            base, height = st
            out.append({
                "id": f"{el['id']}:{k+1}" if len(rects) > 1 else el["id"],
                "type": tags.get("building", "yes"),
                "cE": round(float(rc[0]), 2),
                "cN": round(float(rc[1]), 2),
                "w": round(float(rw), 2),
                "d": round(float(rd), 2),
                "angleDeg": round(float(np.degrees(ra)), 1),
                "base": round(base, 2),
                "height": round(height, 2),
                "onParcel": point_in_poly(rc[0], rc[1], parcel_ring),
                "footprint": [[round(float(e), 2), round(float(n), 2)] for e, n in pts],
            })

    # manually curated / derived structures (decks etc.) survive regeneration
    extras_path = os.path.join(ROOT, "data", "extra_structures.json")
    if os.path.exists(extras_path):
        extras = json.load(open(extras_path, encoding="utf-8"))
        out.extend(extras)
        print(f"merged {len(extras)} extra structure(s)")

    with open(os.path.join(ROOT, "web", "buildings.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)

    on_parcel = [b for b in out if b["onParcel"]]
    print(f"{len(out)} boxes written ({n_multi} buildings decomposed, {skipped} skipped)")
    print(f"on parcel 437/109: {len(on_parcel)}")
    for b in on_parcel:
        print(f"  {b['id']} {b['type']}: {b['w']}x{b['d']} m, h={b['height']} m, "
              f"base={b['base']} m, angle={b['angleDeg']}")


if __name__ == "__main__":
    main()
