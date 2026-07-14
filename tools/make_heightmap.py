"""Convert data/dtm_25cm.tif to a web-friendly Float32 heightmap.

Writes web/heights.bin (row-major, north row first, little-endian float32)
and web/meta.json describing the grid.

Usage: python tools/make_heightmap.py [downsample_factor]
       factor 1 = 0.25 m (2400x2400), 2 = 0.5 m (1200x1200, default)
"""
import json
import os
import sys

import numpy as np
import tifffile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_RES = 0.25
XMIN, YMAX = 71128.0, 6458399.0  # outer corner of top-left pixel

factor = int(sys.argv[1]) if len(sys.argv) > 1 else 2

dtm = tifffile.imread(os.path.join(ROOT, "data", "dtm_25cm.tif"))
rows, cols = dtm.shape
assert rows % factor == 0 and cols % factor == 0

if factor > 1:
    dtm = dtm.reshape(rows // factor, factor, cols // factor, factor).mean(axis=(1, 3))

res = SRC_RES * factor
meta = {
    "cols": dtm.shape[1],
    "rows": dtm.shape[0],
    "res": res,
    # coordinates of the FIRST sample (center of top-left downsampled cell)
    "e0": XMIN + res / 2,
    "n0": YMAX - res / 2,
    "crs": "EPSG:25833",
    "originE": 71428.47,   # scene origin = address point
    "originN": 6458099.03,
}

os.makedirs(os.path.join(ROOT, "web"), exist_ok=True)
dtm.astype("<f4").tofile(os.path.join(ROOT, "web", "heights.bin"))
with open(os.path.join(ROOT, "web", "meta.json"), "w") as f:
    json.dump(meta, f, indent=1)

print(f"heights.bin: {dtm.shape[1]}x{dtm.shape[0]} @ {res} m "
      f"({dtm.nbytes / 1e6:.1f} MB), range {dtm.min():.2f}..{dtm.max():.2f} m")
