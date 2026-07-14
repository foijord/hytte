"""Stitch Norge i bilder WMTS tiles into a georeferenced orthophoto (EPSG:25833)."""
import io
import math
import time
import urllib.request

from PIL import Image

TOKEN = open(r"C:\Users\foeijord\AppData\Local\Temp\nib_token.txt").read().strip()
BASE = "https://tilecache.norgeibilder.no/arcgis/rest/services/Nibcache_UTM33_EUREF89_v2/MapServer/tile"
LEVEL = 17
RES = 0.165283203125
TILE = 256
ORIGIN_X, ORIGIN_Y = -2500000.0, 9045984.0
SPAN = RES * TILE

XMIN, YMIN, XMAX, YMAX = 71128.0, 6457799.0, 71728.0, 6458399.0

c0 = math.floor((XMIN - ORIGIN_X) / SPAN)
c1 = math.floor((XMAX - ORIGIN_X) / SPAN)
r0 = math.floor((ORIGIN_Y - YMAX) / SPAN)
r1 = math.floor((ORIGIN_Y - YMIN) / SPAN)
ncols, nrows = c1 - c0 + 1, r1 - r0 + 1
print(f"tiles: {ncols} x {nrows} = {ncols*nrows}")

mosaic = Image.new("RGB", (ncols * TILE, nrows * TILE))
fail = 0
for r in range(r0, r1 + 1):
    for c in range(c0, c1 + 1):
        url = f"{BASE}/{LEVEL}/{r}/{c}?token={TOKEN}"
        req = urllib.request.Request(url, headers={"Referer": "https://norgeibilder.no/"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = resp.read()
                img = Image.open(io.BytesIO(data)).convert("RGB")
                mosaic.paste(img, ((c - c0) * TILE, (r - r0) * TILE))
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  FAILED {r}/{c}: {e}")
                    fail += 1
                else:
                    time.sleep(1)
print(f"downloaded, {fail} failures")

# crop to exact bbox
mosaic_xmin = ORIGIN_X + c0 * SPAN
mosaic_ymax = ORIGIN_Y - r0 * SPAN
px0 = round((XMIN - mosaic_xmin) / RES)
py0 = round((mosaic_ymax - YMAX) / RES)
px1 = round((XMAX - mosaic_xmin) / RES)
py1 = round((mosaic_ymax - YMIN) / RES)
crop = mosaic.crop((px0, py0, px1, py1))
print(f"cropped: {crop.size}")

out = r"C:\Users\foeijord\Code\hytte\data\ortho_16cm.jpg"
crop.save(out, quality=92)
# world file for georeferencing
with open(r"C:\Users\foeijord\Code\hytte\data\ortho_16cm.jgw", "w") as f:
    f.write(f"{RES}\n0.0\n0.0\n-{RES}\n{XMIN + RES/2}\n{YMAX - RES/2}\n")
print("saved", out)
