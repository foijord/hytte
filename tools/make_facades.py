"""Crop real facade bands from the manufacturers' elevation drawings and
save them as wall textures (web/tex/fac_*.jpg), auto-calibrated so the
crop aspect matches the true wall dimensions.

For each elevation quadrant the building's pixel extent is detected from
dark pixels (windows/roof lines vs the pale background), pixels-per-meter
follows from the known envelope width, and each band is cut from the
building's baseline upward by its true height. Windows and doors then land
at their real positions without horizontal squeeze.

Sources (session scratchpad): falstad2.jpg, spangereid_ext.jpg.
"""
import os
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'web' / 'tex'
OUT.mkdir(parents=True, exist_ok=True)
SCRATCH = Path(os.environ.get('LOCALAPPDATA', '')) / 'Temp' / 'claude' / \
    'C--Users-foeijord-Code-hytte' / 'df508fcc-9c6d-4069-b80b-9d512890f5b8' / 'scratchpad'


def quadrant(src, qc, qr):
    im = Image.open(SCRATCH / src)
    w, h = im.size
    return im.crop((qc * w // 2, qr * h // 2, (qc + 1) * w // 2, (qr + 1) * h // 2))


def building_extent(q, dark=120):
    """(x0, x1, y_bottom) of the drawn building via dark-pixel columns/rows."""
    g = np.asarray(q.convert('L'), dtype=float)
    cols = (g < dark).sum(axis=0)
    rows = (g < dark).sum(axis=1)
    xs = np.where(cols > 2)[0]
    ys = np.where(rows > 2)[0]
    return xs[0], xs[-1], ys[-1]


# (source, quadrant, envelope width m, bands: (name, y0_m, y1_m, inset_m))
# y measured up from the building baseline; inset trims overhang ends
SHEETS = [
    ('falstad2.jpg', (0, 0), 10.8, [
        ('fac_falstad_sea', 0.05, 3.45, 0.25),
        ('fac_falstad_cler', 5.10, 6.50, 0.25),
    ]),
    ('falstad2.jpg', (0, 1), 10.8, [
        ('fac_falstad_road', 0.05, 3.40, 0.25),
    ]),
    ('spangereid_ext.jpg', (0, 0), 10.6, [
        ('fac_spang_sea', 0.05, 2.70, 0.1),
        ('fac_spang_upper', 2.80, 5.65, 0.1),
    ]),
    ('spangereid_ext.jpg', (0, 1), 10.6, [
        ('fac_spang_road', 0.05, 5.45, 0.1),
    ]),
]

for src, (qc, qr), env_w, bands in SHEETS:
    q = quadrant(src, qc, qr)
    x0, x1, yb = building_extent(q)
    ppm = (x1 - x0 + 1) / env_w
    print(f'{src} q{qc}{qr}: building x {x0}..{x1}, baseline y {yb}, {ppm:.1f} px/m')
    for name, m0, m1, inset in bands:
        cx0 = int(x0 + inset * ppm)
        cx1 = int(x1 - inset * ppm)
        cy0 = int(yb - m1 * ppm)
        cy1 = int(yb - m0 * ppm)
        band = q.crop((cx0, max(0, cy0), cx1, cy1))
        band = band.resize((band.width * 3, band.height * 3), Image.LANCZOS)
        band.save(OUT / f'{name}.jpg', quality=88)
        print(f'  {name}: {band.size} ({(cx1-cx0)/ppm:.1f} x {m1-m0:.2f} m, '
              f'aspect {(cx1-cx0)/(cy1-max(0,cy0)):.2f} vs true '
              f'{((cx1-cx0)/ppm)/(m1-m0):.2f})')
print('done ->', OUT)
