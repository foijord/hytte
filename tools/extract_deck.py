"""Extract the deck in front of the main cabin from the LiDAR surface model.

Deck criteria: locally flat DOM surface at roughly cabin-floor elevation,
elevated above the bare-earth DTM, connected to the cabin footprint.
Fits oriented rectangle(s) aligned with the cabin and writes
data/extra_structures.json; run tools/extract_buildings.py afterwards to
merge into web/buildings.json. Pass --diag to write a verification overlay.
"""
import json
import math
import os
import sys
from collections import deque

import numpy as np
import tifffile
from PIL import Image, ImageDraw

from extract_buildings import (
    ROOT, RES, XMIN, YMAX, largest_rectangle, dominant_angle,
    point_in_poly, parcel_ring,
)

CABIN_ID = 936839960
SEARCH_R = 18            # analysis window radius around cabin, m
ABOVE_GROUND = (0.10, 2.6)   # DOM-DTM range, m (deck can be tall on the downhill side)
FLOOR_TOL = (-0.45, 0.9)     # accepted DOM offset from cabin floor, m
FLAT_MAX_RANGE = 0.30        # max DOM max-min in a 3x3 (0.75 m) window, m
MIN_PART_M2 = 5.0
MAX_PARTS = 3

dtm = tifffile.imread(os.path.join(ROOT, "data", "dtm_25cm.tif"))
dom = tifffile.imread(os.path.join(ROOT, "data", "dom_25cm.tif"))

buildings = json.load(open(os.path.join(ROOT, "web", "buildings.json"), encoding="utf-8"))
cabin_parts = [b for b in buildings if str(b["id"]).startswith(str(CABIN_ID))]
cabin_fp = np.array(cabin_parts[0]["footprint"])
floor = min(b["base"] for b in cabin_parts)
cE, cN = cabin_fp[:, 0].mean(), cabin_fp[:, 1].mean()
print(f"cabin floor ~{floor:.2f} m")

# analysis window on the 0.25 m grid
j0 = int((cE - SEARCH_R - XMIN) / RES); j1 = int((cE + SEARCH_R - XMIN) / RES)
i0 = int((YMAX - cN - SEARCH_R) / RES); i1 = int((YMAX - cN + SEARCH_R) / RES)
wdom = dom[i0:i1, j0:j1]
wdtm = dtm[i0:i1, j0:j1]
H, W = wdom.shape

# local flatness: max-min of DOM in a 3x3 neighborhood
mx = wdom.copy()
mn = wdom.copy()
for di in (-1, 0, 1):
    for dj in (-1, 0, 1):
        s = np.roll(np.roll(wdom, di, 0), dj, 1)
        mx = np.maximum(mx, s)
        mn = np.minimum(mn, s)
flat = (mx - mn) < FLAT_MAX_RANGE

above = wdom - wdtm
band = (above > ABOVE_GROUND[0]) & (above < ABOVE_GROUND[1])
level = (wdom > floor + FLOOR_TOL[0]) & (wdom < floor + FLOOR_TOL[1])
cand = band & level & flat

# cabin footprint mask + 1.25 m dilation ring as seeds
fp_px = [((e - XMIN) / RES - j0, (YMAX - n) / RES - i0) for e, n in cabin_fp]
fpimg = Image.new("L", (W, H), 0)
ImageDraw.Draw(fpimg).polygon(fp_px, fill=1)
fp = np.array(fpimg, dtype=bool)
r = int(1.25 / RES)
dil = np.zeros_like(fp)
for di in range(-r, r + 1):
    for dj in range(-r, r + 1):
        if di * di + dj * dj <= r * r:
            dil |= np.roll(np.roll(fp, di, 0), dj, 1)
seeds = cand & dil & ~fp

# flood fill (8-connected) from seeds through the candidate mask
comp = seeds.copy()
q = deque(zip(*np.nonzero(seeds)))
while q:
    i, j = q.popleft()
    for ni in (i - 1, i, i + 1):
        for nj in (j - 1, j, j + 1):
            if 0 <= ni < H and 0 <= nj < W and cand[ni, nj] and not comp[ni, nj] and not fp[ni, nj]:
                comp[ni, nj] = True
                q.append((ni, nj))

area = comp.sum() * RES * RES
print(f"deck component: {area:.0f} m2")
if area < MIN_PART_M2:
    sys.exit("no significant platform found next to the cabin")

top = float(np.median(wdom[comp]))
ground = float(np.percentile(wdtm[comp], 10))
print(f"deck top {top:.2f} m, ground under deck {ground:.2f} m")

# decompose the component mask into rectangles in the cabin-aligned frame
ang = dominant_angle(cabin_fp)
c, s = np.cos(-ang), np.sin(-ang)
ii, jj = np.nonzero(comp)
pts = np.column_stack([XMIN + (jj + j0 + 0.5) * RES, YMAX - (ii + i0 + 0.5) * RES])
rot = pts @ np.array([[c, -s], [s, c]]).T
rx0, ry0 = rot[:, 0].min(), rot[:, 1].min()
gx = ((rot[:, 0] - rx0) / RES).astype(int)
gy = ((rot[:, 1] - ry0) / RES).astype(int)
grid = np.zeros((gy.max() + 1, gx.max() + 1), dtype=bool)
grid[gy, gx] = True
# close 1-cell gaps so the greedy rectangles span the plank surface
g2 = grid.copy()
for di in (-1, 0, 1):
    for dj in (-1, 0, 1):
        g2 |= np.roll(np.roll(grid, di, 0), dj, 1)

total = grid.sum()
work = g2.copy()
rects = []
cb, sb = np.cos(ang), np.sin(ang)
while len(rects) < MAX_PARTS and work.sum() > 0.12 * total:
    a, r0, c0, r1, c1 = largest_rectangle(work)
    if a * RES * RES < MIN_PART_M2:
        break
    work[r0:r1, c0:c1] = False
    rxc = rx0 + (c0 + c1) / 2 * RES
    ryc = ry0 + (r0 + r1) / 2 * RES
    rw = (c1 - c0) * RES
    rd = (r1 - r0) * RES
    ra = ang
    if rd > rw:
        rw, rd, ra = rd, rw, ra + np.pi / 2
    ra = (ra + np.pi / 2) % np.pi - np.pi / 2
    center = (rxc * cb - ryc * sb, rxc * sb + ryc * cb)
    rects.append((center, rw, rd, ra))

extras = []
for k, (rc, rw, rd, ra) in enumerate(rects):
    extras.append({
        "id": f"deck:{k+1}" if len(rects) > 1 else "deck",
        "type": "deck",
        "cE": round(float(rc[0]), 2),
        "cN": round(float(rc[1]), 2),
        "w": round(float(rw), 2),
        "d": round(float(rd), 2),
        "angleDeg": round(float(np.degrees(ra)), 1),
        "base": round(ground, 2),
        "height": round(top - ground, 2),
        "onParcel": bool(point_in_poly(rc[0], rc[1], parcel_ring)),
        "footprint": [],
    })
    print(f"  {extras[-1]['id']}: {extras[-1]['w']}x{extras[-1]['d']} m, "
          f"h={extras[-1]['height']} m, angle={extras[-1]['angleDeg']}")

with open(os.path.join(ROOT, "data", "extra_structures.json"), "w", encoding="utf-8") as f:
    json.dump(extras, f, indent=1)
print(f"wrote {len(extras)} record(s) to data/extra_structures.json")

if "--diag" in sys.argv:
    ores = 0.165283203125
    ortho = Image.open(os.path.join(ROOT, "data", "ortho_16cm.jpg")).convert("RGB")
    m = Image.fromarray((comp * 255).astype(np.uint8)).resize(
        (int(W * RES / ores), int(H * RES / ores)), Image.NEAREST)
    full = Image.new("L", ortho.size, 0)
    full.paste(m, (int(j0 * RES / ores), int(i0 * RES / ores)))
    blue = Image.new("RGB", ortho.size, (30, 130, 255))
    out = Image.composite(Image.blend(ortho, blue, 0.5), ortho, full)
    dr = ImageDraw.Draw(out)
    def to_px(e, n): return ((e - XMIN) / ores, (YMAX - n) / ores)
    for b in extras:
        a = math.radians(b["angleDeg"]); ca, sa = math.cos(a), math.sin(a)
        hw, hd = b["w"] / 2, b["d"] / 2
        cs = [to_px(b["cE"] + dx * ca - dy * sa, b["cN"] + dx * sa + dy * ca)
              for dx, dy in ((-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd))]
        dr.line(cs + [cs[0]], fill=(255, 235, 0), width=3)
    cx, cy = to_px(cE, cN)
    half = int(22 / ores)
    crop = out.crop((int(cx - half), int(cy - half), int(cx + half), int(cy + half)))
    crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
    diag = os.path.join(os.environ.get("DIAG_DIR", ROOT), "deck_fit.jpg")
    crop.save(diag, quality=90)
    print("diag:", diag)
