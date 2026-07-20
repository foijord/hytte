"""Generate the new-cabin concept variants: web/newbuild.json (3D records)
and docs/floorplan.svg (dimensioned concept floor plan of the baseline).

Base model: Familiehytta FURUTANGEN 75 MED HEMS (published: BRA 74 m2,
GUA 112 m2 incl. ~38 m2 hems, length 11.15 m, width 8.85 m incl. overhang,
ridge 5.0 m, gesims 2.8 m, 30 deg roof; wall span 7.6 derived from the roof
geometry). Gable window wall toward the sea on the old sea-facade line,
centered on the deck. Slab top at deck surface + 0.06 (3.55 NN2000).

Variants (deck-sun study; the viewer's "new build" button cycles them):
  A  gable front, 30 deg (baseline; ridge abs 8.54)
  B  gable front, 30 deg, set back 2.5 m from the facade line
  C  gable front, 25 deg (ridge abs ~8.1 - dispensation fallback)
  D  low pulttak ~7 deg a la Saltdalshytta Nova, approximated as a flat
     3.5 m volume (no hems at this height - needs a bigger footprint)
  E  as A plus a 3.5x4.5 m west sun-deck for afternoon/evening sun

All variants share the under-deck storage/tech room (1.9 m headroom,
floor +1.59 NN2000) and the unchanged 8x3 deck surface.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

WALLS_L = 11.15            # m, Furutangen 75 wall footprint
WALLS_W = 7.6
PITCH = 30.0               # deg, Furutangen standard
WALL_H = 2.8               # m, gesims height
OVERHANG = 0.6
STORAGE_H = 1.9            # m, under-deck room headroom
SETBACK = 2.5              # m, variant B
WALL_EXT = 0.25            # exterior wall thickness (floor plan)
PART = 0.15                # interior partition thickness (floor plan)


def unit_vectors(angle_deg):
    """(w_unit, d_unit) in (E, N) for a record angle, matching the viewer's
    rotation convention (verified against wings :1/:2 offsets)."""
    t = math.radians(angle_deg)
    return (math.cos(t), math.sin(t)), (math.sin(t), -math.cos(t))


def main():
    bl = json.load(open(ROOT / 'web' / 'buildings.json', encoding='utf-8'))
    w1 = next(b for b in bl if b['id'] == '936839960:1')
    deck = next(b for b in bl if b['id'] == 'deck')

    ang = w1['angleDeg']
    wu, du = unit_vectors(ang)

    def to_en(u, v):
        return (round(w1['cE'] + u * wu[0] + v * du[0], 2),
                round(w1['cN'] + u * wu[1] + v * du[1], 2))

    def to_uv(e, n):
        de, dn = e - w1['cE'], n - w1['cN']
        return de * wu[0] + dn * wu[1], de * du[0] + dn * du[1]

    # sea-facing facade line = the u- gable line of the old main wing
    u_deck, v_deck = to_uv(deck['cE'], deck['cN'])
    assert u_deck < -w1['w'] / 2, 'deck expected off the u- gable end'
    u_sea = -w1['w'] / 2
    deck_top = deck['base'] + deck['ridge']
    base = deck_top + 0.06                    # slab just above the deck

    def rec(id_, cE_, cN_, w, d, b, eave_, ridge_, pitch, **kw):
        r = {'id': id_, 'type': kw.pop('type', 'cabin'), 'onParcel': True,
             'cE': cE_, 'cN': cN_, 'w': w, 'd': d, 'angleDeg': ang,
             'base': round(b, 2), 'height': round(ridge_, 2),
             'flat': kw.pop('flat', False),
             'eave': round(eave_, 2), 'ridge': round(ridge_, 2),
             'ridgeAxis': 'w', 'pitchDeg': pitch,
             'overhang': kw.pop('overhang', OVERHANG),
             'open': False, 'backWall': None, 'footprint': []}
        r.update(kw)
        return r

    def slab(cabin, walls_l, walls_w):
        """Grey concrete slab flush under the walls, 0.35 m visible plinth."""
        return rec(f'{cabin["id"]}:slab', cabin['cE'], cabin['cN'],
                   round(walls_l + 0.05, 2), round(walls_w + 0.05, 2),
                   cabin['base'] - 0.35, 0.35, 0.35, 0.0,
                   type='slab', flat=True, overhang=0.0, onParcel=False,
                   variant=cabin['variant'], variantLabel=cabin['variantLabel'])

    def gable_cabin(id_, variant, label, pitch=PITCH, setback=0.0):
        roof_l, roof_w = WALLS_L + 2 * OVERHANG, WALLS_W + 2 * OVERHANG
        slope = math.tan(math.radians(pitch))
        eave = WALL_H - slope * OVERHANG
        ridge = eave + slope * roof_w / 2
        u_c = u_sea + setback - OVERHANG + roof_l / 2
        cE_, cN_ = to_en(u_c, v_deck)
        return rec(id_, cE_, cN_, round(roof_l, 2), round(roof_w, 2),
                   base, eave, ridge, pitch, variant=variant, variantLabel=label)

    out = []
    for cabin in (gable_cabin('newbuild:A', 'A', 'A · gable 30°'),
                  gable_cabin('newbuild:B', 'B', 'B · setback 2.5 m', setback=SETBACK),
                  gable_cabin('newbuild:C', 'C', 'C · gable 25°', pitch=25.0)):
        out += [cabin, slab(cabin, WALLS_L, WALLS_W)]

    # D: low pulttak (Nova-like) approximated as a flat volume; same
    # footprint for comparability - the real thing needs ~15 m2 more
    # floor to compensate for the lost hems
    roof_l = WALLS_L + 2 * OVERHANG
    u_c = u_sea - OVERHANG + roof_l / 2
    cE_, cN_ = to_en(u_c, v_deck)
    cab_d = rec('newbuild:D', cE_, cN_, round(WALLS_L, 2), round(WALLS_W, 2),
                base, 3.5, 3.5, 0.0, flat=True, overhang=0.0,
                variant='D', variantLabel='D · low pulttak (approx.)')
    out += [cab_d, slab(cab_d, WALLS_L, WALLS_W)]

    # E: baseline + west sun-deck at the sea corner (afternoon/evening sun)
    cab_e = gable_cabin('newbuild:E', 'E', 'E · gable 30° + west deck')
    out += [cab_e, slab(cab_e, WALLS_L, WALLS_W)]
    v_west = v_deck + (WALLS_W + 2 * OVERHANG) / 2 + 1.75
    eW, nW = to_en(u_sea - 1.5, v_west)
    out.append(rec('newbuild:E:westdeck', eW, nW, 3.5, 4.5,
                   deck_top - 0.35, 0.35, 0.35, 0.0,
                   type='deck', flat=True, overhang=0.0,
                   variant='E', variantLabel='E · gable 30° + west deck'))

    # shared: the under-deck storage/tech room (variant: null = all variants);
    # deck keeps its own angle, 90 deg off the cabin's
    out.append(rec('newbuild:storage', deck['cE'], deck['cN'],
                   deck['w'], deck['d'], deck_top - STORAGE_H,
                   STORAGE_H, STORAGE_H, 0.0,
                   type='deck', flat=True, overhang=0.0,
                   angleDeg=deck['angleDeg'], variant=None,
                   variantLabel=None))

    path = ROOT / 'web' / 'newbuild.json'
    path.write_text(json.dumps(out, indent=1), encoding='utf-8')
    slope = math.tan(math.radians(PITCH))
    ridge_abs = base + WALL_H - slope * OVERHANG + slope * (WALLS_W + 2 * OVERHANG) / 2
    print(f'wrote {path} ({len(out)} records, variants A-E; '
          f'A ridge abs {ridge_abs:.2f} vs old {w1["base"] + w1["ridge"]:.2f})')

    write_floorplan(deck)


# ---------------------------------------------------------------- floor plan

def write_floorplan(deck):
    """Concept plan of the baseline (gable front): X = across the gable
    facade, Y = along the ridge (0 = sea-end roof edge, road at the top)."""
    S = 40                                    # px per meter
    ROOF_W, ROOF_L = WALLS_W + 2 * OVERHANG, WALLS_L + 2 * OVERHANG

    x0, x1 = OVERHANG, OVERHANG + WALLS_W     # wall outer faces
    y0, y1 = OVERHANG, OVERHANG + WALLS_L
    ix0, ix1 = x0 + WALL_EXT, x1 - WALL_EXT   # interior
    iy0, iy1 = y0 + WALL_EXT, y1 - WALL_EXT

    rooms = []      # (x0, y0, x1, y1, label)

    def room(rx0, ry0, rx1, ry1, name):
        rooms.append((rx0, ry0, rx1, ry1, f'{name}|{(rx1 - rx0) * (ry1 - ry0):.1f} m²'))

    # sea -> road: open allrom at the window gable, service band
    # (bath / stair to hems / entrance), two bedrooms under the hems
    y = iy0
    room(ix0, y, ix1, y + 5.35, 'Allrom — stue / kjøkken'); y += 5.35 + PART
    band0 = y
    room(ix0, y, ix0 + 2.40, y + 1.80, 'Bath')
    room(ix0 + 2.40 + PART, y, ix0 + 3.90, y + 1.80, 'Stair')
    room(ix0 + 3.90 + PART, y, ix1, y + 1.80, 'Hall')
    y += 1.80 + PART
    beds0 = y
    bmid = (ix0 + ix1) / 2
    room(ix0, y, bmid - PART / 2, iy1, 'Bedroom 1')
    room(bmid + PART / 2, y, ix1, iy1, 'Bedroom 2')

    # svg canvas
    MX0, MX1, MY0, MY1 = -2.2, 10.4, -5.8, 14.6
    def px(x): return round((x - MX0) * S, 1)
    def py(yy): return round((MY1 - yy) * S, 1)
    w_px, h_px = px(MX1), py(MY0) + 70
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w_px} {h_px}" '
           f'font-family="system-ui, sans-serif">',
           f'<rect width="{w_px}" height="{h_px}" fill="#fbf9f4"/>']

    def rect(rx0, ry0, rx1, ry1, fill, extra=''):
        svg.append(f'<rect x="{px(rx0)}" y="{py(ry1)}" width="{round((rx1-rx0)*S,1)}" '
                   f'height="{round((ry1-ry0)*S,1)}" fill="{fill}" {extra}/>')

    def line(lx0, ly0, lx1, ly1, stroke, extra=''):
        svg.append(f'<line x1="{px(lx0)}" y1="{py(ly0)}" x2="{px(lx1)}" y2="{py(ly1)}" '
                   f'stroke="{stroke}" {extra}/>')

    def text(tx, ty, s, size=11, fill='#333', anchor='middle', extra=''):
        svg.append(f'<text x="{px(tx)}" y="{py(ty)}" font-size="{size}" fill="{fill}" '
                   f'text-anchor="{anchor}" {extra}>{s}</text>')

    # roof outline (dashed) + ridge line
    svg.append(f'<rect x="{px(0)}" y="{py(ROOF_L)}" width="{ROOF_W*S}" height="{ROOF_L*S}" '
               f'stroke="#b0a58f" stroke-dasharray="6 5" fill="none"/>')
    line(ROOF_W / 2, 0, ROOF_W / 2, ROOF_L, '#b0a58f', 'stroke-dasharray="10 4 2 4"')

    # walls filled dark, room interiors punched out in white
    rect(x0, y0, x1, y1, '#4a4238')
    for rx0, ry0, rx1, ry1, _ in rooms:
        rect(rx0, ry0, rx1, ry1, '#ffffff')

    # hems overlay (loft over service band + bedrooms)
    rect(x0 + 0.06, band0 - PART, x1 - 0.06, y1 - 0.06, 'none',
         'stroke="#c2703e" stroke-width="2" stroke-dasharray="9 6"')
    text((ix0 + ix1) / 2, beds0 + 0.32, 'hems above · ~38 m² (GUA)', 9.5, '#c2703e')

    # windows (light blue) and doors (brown)
    win = '#7fb2d9'
    rect(1.1, y0 - 0.02, 6.9, y0 + WALL_EXT + 0.02, win)              # sea window wall
    rect(3.5, y0 - 0.06, 4.5, y0 + WALL_EXT + 0.06, '#8a5a2b')        # deck slider
    rect(x0 - 0.02, 5.2, x0 + WALL_EXT + 0.02, 7.0, win)              # allrom side
    rect(x1 - WALL_EXT - 0.02, 1.4, x1 + 0.02, 3.2, win)              # allrom side
    rect(1.2, y1 - 0.02 - WALL_EXT, 2.4, y1 + 0.02, win)              # bedroom 1
    rect(5.2, y1 - 0.02 - WALL_EXT, 6.4, y1 + 0.02, win)              # bedroom 2
    rect(x1 - WALL_EXT - 0.06, band0 + 0.35, x1 + 0.06, band0 + 1.35, '#8a5a2b')  # entry
    text(x1 + 0.75, band0 + 0.85, 'entrance', 10, '#6b5335', anchor='start')

    # deck + the concrete room below, true footprint offset to the cabin
    dy1 = y0 - 0.61
    dy0 = dy1 - deck['d']
    dx0 = ROOF_W / 2 - deck['w'] / 2
    rect(dx0, dy0, dx0 + deck['w'], dy1, '#e8d9be', 'stroke="#b59a6a"')
    dcx, dcy = dx0 + deck['w'] / 2, (dy0 + dy1) / 2
    text(dcx, dcy + 0.35, f'Deck {deck["w"]:.0f} × {deck["d"]:.0f} m', 11, '#6b5335')
    text(dcx, dcy - 0.25, f'Storage / tech room ~{(deck["w"] - 0.5) * (deck["d"] - 0.5):.0f} m² · h {STORAGE_H} m below', 10, '#8a7350')
    rect(dcx - 0.45, dy0 - 0.06, dcx + 0.45, dy0 + 0.06, '#8a5a2b')   # door below
    text(dcx, dy0 - 0.5, 'door to the room on the lower (sea) side', 9, '#999')

    # room labels
    for rx0, ry0, rx1, ry1, label in rooms:
        name, area = label.split('|')
        cx, cy = (rx0 + rx1) / 2, (ry0 + ry1) / 2
        small = (rx1 - rx0) < 2.0
        text(cx, cy + 0.16, name, 9.5 if small else 11.5, '#222', extra='font-weight="600"')
        text(cx, cy - 0.38, area, 9 if small else 10, '#777')

    # dimension lines
    dim = '#8a6d3b'
    def dimline(lx0, ly0, lx1, ly1, label, dx=0, dy=0):
        line(lx0, ly0, lx1, ly1, dim)
        for (tx, ty) in ((lx0, ly0), (lx1, ly1)):
            line(tx - 0.12 * (0 if lx0 != lx1 else 1), ty - 0.12 * (0 if ly0 != ly1 else 1),
                 tx + 0.12 * (0 if lx0 != lx1 else 1), ty + 0.12 * (0 if ly0 != ly1 else 1), dim)
        mx, my = (lx0 + lx1) / 2 + dx, (ly0 + ly1) / 2 + dy
        rot = f'transform="rotate(-90 {px(mx)} {py(my)})"' if lx0 == lx1 else ''
        text(mx, my, label, 10.5, dim, extra=rot)

    dimline(-1.3, 0, -1.3, ROOF_L, f'{ROOF_L:.2f} m roof', dx=-0.35)
    dimline(-0.75, y0, -0.75, y1, f'{WALLS_L:.2f} m', dx=0.38)
    dimline(0, 14.05, ROOF_W, 14.05, f'{ROOF_W:.1f} m roof', dy=0.35)
    dimline(x0, 13.55, x1, 13.55, f'{WALLS_W:.1f} m', dy=-0.42)
    dimline(dx0, dy0 - 1.2, dx0 + deck['w'], dy0 - 1.2, f'{deck["w"]:.1f} m', dy=-0.45)

    # orientation: sea side down (NNW); north arrow from the record angle
    bl = json.load(open(ROOT / 'web' / 'buildings.json', encoding='utf-8'))
    w1 = next(b for b in bl if b['id'] == '936839960:1')
    t = math.radians(w1['angleDeg'])
    ndx, ndy = -math.cos(t), math.sin(t)
    ax_, ay_ = 9.6, -4.6
    line(ax_, ay_, ax_ + ndx * 1.1, ay_ + ndy * 1.1, '#333', 'stroke-width="1.6"')
    svg.append(f'<circle cx="{px(ax_)}" cy="{py(ay_)}" r="2.5" fill="#333"/>')
    text(ax_ + ndx * 1.55, ay_ + ndy * 1.55, 'N', 12, '#333', extra='font-weight="700"')
    text(1.2, -5.5, '⌄ sea / fjord', 11, '#4d7ba6')
    text(8.2, 14.35, 'road side ⌃', 11, '#777')

    # title block
    svg.append(f'<text x="{px(MX0)+14}" y="{h_px-40}" font-size="16" font-weight="700" '
               f'fill="#222">Kalsneset 27 — Familiehytta Furutangen 75 med hems (approx.)</text>')
    svg.append(f'<text x="{px(MX0)+14}" y="{h_px-20}" font-size="11" fill="#666">'
               f'walls {WALLS_L:.2f} × {WALLS_W:.1f} m · BRA 74 m² + hems ~38 m² · '
               f'{PITCH:.0f}° roof, ridge 5.0 / gesims 2.8 · window wall to the sea · '
               f'storage/tech ~19 m², h {STORAGE_H} m below deck · variants A–E in the 3D viewer · '
               f'layout indicative, final plan per manufacturer · scale 1:100 @ {S}px/m</text>')
    svg.append('</svg>')

    out = ROOT / 'docs' / 'floorplan.svg'
    out.parent.mkdir(exist_ok=True)
    out.write_text('\n'.join(svg), encoding='utf-8')
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
