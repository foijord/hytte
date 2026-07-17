"""Generate the new-cabin concept: web/newbuild.json (3D records for the viewer)
and docs/floorplan.svg (dimensioned concept floor plan).

Design intent (owner, 2026-07-17, revised to cut cost):
  - PRE-MADE catalog cabin (ferdighytte), ~80 m2 on one level with a hems
    (sleeping loft) over the road-end half, on a concrete slab.
  - Single rectangular volume, gable end with the window wall facing the sea,
    on the same sea-facing gable line and orientation as the old cabin.
  - Steeper roof (33 deg) than the old cabin to give the hems headroom;
    ridge lands ~1 m above the old one - flagged for the dispensation.
  - Deck 8 x 3 m arrangement stays; ONE combined concrete room below it
    (storage + technical, ~18 m2, single entrance on the sea side).

Derives placement from web/buildings.json records :1 and deck, so a
MANUAL_PART regeneration automatically carries into the concept.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

WALLS_L = 12.0             # m, catalog volume wall footprint (~80 m2 BYA)
WALLS_W = 6.8
PITCH = 33.0               # deg, hems-friendly roof
WALL_H = 2.9               # m, wall height at the wall face (raised for hems)
OVERHANG = 0.4
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

    # sea-facing gable line = the u- gable of the old main wing (deck beyond it)
    u_deck, v_deck = to_uv(deck['cE'], deck['cN'])
    assert u_deck < -w1['w'] / 2, 'deck expected off the u- gable end'
    u_sea_wall = -w1['w'] / 2                # keep the old sea-facade line

    roof_l = WALLS_L + 2 * OVERHANG
    roof_w = WALLS_W + 2 * OVERHANG
    u_c = u_sea_wall - OVERHANG + roof_l / 2
    v_c = v_deck                              # centered on the deck
    cE, cN = to_en(u_c, v_c)

    slope = math.tan(math.radians(PITCH))
    eave = WALL_H - slope * OVERHANG          # roof-edge height above base
    ridge = eave + slope * roof_w / 2
    base = w1['base']

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

    out = [rec('newbuild:cabin', cE, cN, round(roof_l, 2), round(roof_w, 2),
               base, eave, ridge, PITCH)]

    # one combined storage + technical room under the deck (deck top unchanged)
    out.append(rec('newbuild:storage', deck['cE'], deck['cN'],
                   deck['w'], deck['d'], deck['base'],
                   deck['ridge'], deck['ridge'], 0.0,
                   type='deck', flat=True, overhang=0.0))

    path = ROOT / 'web' / 'newbuild.json'
    path.write_text(json.dumps(out, indent=1), encoding='utf-8')
    print(f'wrote {path} ({len(out)} records, cabin ridge abs '
          f'{base + ridge:.2f} vs old {w1["base"] + w1["ridge"]:.2f} NN2000)')

    write_floorplan(deck)


# ---------------------------------------------------------------- floor plan

def write_floorplan(deck):
    """Concept plan of a typical ~80 m2 catalog cabin with hems; the real
    layout comes from the chosen manufacturer. X = across the gable facade
    (0 = roof edge on the old-wing-A side), Y = along the ridge
    (0 = sea-end roof edge, road end at the top)."""
    S = 40                                    # px per meter
    ROOF_W, ROOF_L = WALLS_W + 0.8, WALLS_L + 0.8

    x0, x1 = OVERHANG, OVERHANG + WALLS_W     # wall outer faces
    y0, y1 = OVERHANG, OVERHANG + WALLS_L
    ix0, ix1 = x0 + WALL_EXT, x1 - WALL_EXT   # interior
    iy0, iy1 = y0 + WALL_EXT, y1 - WALL_EXT

    rooms = []      # (x0, y0, x1, y1, label)

    def room(rx0, ry0, rx1, ry1, name):
        rooms.append((rx0, ry0, rx1, ry1, f'{name}|{(rx1 - rx0) * (ry1 - ry0):.1f} m²'))

    # sea -> road: living (window wall), open kitchen/dining, service band
    # (bath / stair to hems / entrance), two bedrooms under the hems
    y = iy0
    room(ix0, y, ix1, y + 4.00, 'Living room'); y += 4.00 + PART
    room(ix0, y, ix1, y + 2.80, 'Kitchen / dining'); y += 2.80 + PART
    band0 = y
    room(ix0, y, ix0 + 2.40, y + 1.80, 'Bath')
    room(ix0 + 2.40 + PART, y, ix0 + 3.90, y + 1.80, 'Stair')
    room(ix0 + 3.90 + PART, y, ix1, y + 1.80, 'Hall')
    y += 1.80 + PART
    beds0 = y
    bmid = (ix0 + ix1) / 2
    room(ix0, y, bmid - PART / 2, iy1, 'Bedroom 1')
    room(bmid + PART / 2, y, ix1, iy1, 'Bedroom 2')

    # svg canvas: x in [-2.2, 9.6] m, y in [-5.6, 14.4] m (+ title strip)
    MX0, MX1, MY0, MY1 = -2.2, 9.6, -5.6, 14.4
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
    text((ix0 + ix1) / 2, beds0 + 0.32,
         f'hems above · ~{(y1 - band0 + PART) * WALLS_W * 0.55:.0f} m²', 9.5, '#c2703e')

    # windows (light blue) and doors (brown)
    win = '#7fb2d9'
    rect(1.1, y0 - 0.02, 6.1, y0 + WALL_EXT + 0.02, win)              # sea window wall
    rect(2.9, y0 - 0.06, 3.9, y0 + WALL_EXT + 0.06, '#8a5a2b')        # deck slider
    rect(x0 - 0.02, 5.2, x0 + WALL_EXT + 0.02, 7.0, win)              # kitchen side
    rect(x1 - WALL_EXT - 0.02, 1.4, x1 + 0.02, 3.2, win)              # living side
    rect(1.2, y1 - 0.02 - WALL_EXT, 2.4, y1 + 0.02, win)              # bedroom 1
    rect(4.6, y1 - 0.02 - WALL_EXT, 5.8, y1 + 0.02, win)              # bedroom 2
    rect(x1 - WALL_EXT - 0.06, band0 + 0.35, x1 + 0.06, band0 + 1.35, '#8a5a2b')  # entry
    text(x1 + 0.75, band0 + 0.85, 'entrance', 10, '#6b5335', anchor='start')

    # deck + the combined concrete room below, at its true footprint position
    # relative to the cabin (deck is centered on the cabin axis, 0.61 m off
    # the sea wall face, so it spans 0.2 m past the roof edge on both sides)
    dy1 = 0.4 - 0.61
    dy0 = dy1 - deck['d']
    dx0 = ROOF_W / 2 - deck['w'] / 2
    rect(dx0, dy0, dx0 + deck['w'], dy1, '#e8d9be', 'stroke="#b59a6a"')
    dcx, dcy = dx0 + deck['w'] / 2, (dy0 + dy1) / 2
    text(dcx, dcy + 0.35, f'Deck {deck["w"]:.0f} × {deck["d"]:.0f} m', 11, '#6b5335')
    text(dcx, dcy - 0.25, f'Storage / tech room ~{(deck["w"] - 0.5) * (deck["d"] - 0.5):.0f} m² below', 10, '#8a7350')
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

    dimline(-1.3, 0, -1.3, ROOF_L, f'{ROOF_L:.1f} m roof', dx=-0.35)
    dimline(-0.75, y0, -0.75, y1, f'{WALLS_L:.1f} m', dx=0.38)
    dimline(0, 13.85, ROOF_W, 13.85, f'{ROOF_W:.1f} m roof', dy=0.35)
    dimline(x0, 13.35, x1, 13.35, f'{WALLS_W:.1f} m', dy=-0.42)
    dimline(dx0, dy0 - 1.2, dx0 + deck['w'], dy0 - 1.2, f'{deck["w"]:.1f} m', dy=-0.45)

    # orientation: sea side down (NNW); north arrow from the record angle
    bl = json.load(open(ROOT / 'web' / 'buildings.json', encoding='utf-8'))
    w1 = next(b for b in bl if b['id'] == '936839960:1')
    t = math.radians(w1['angleDeg'])
    ndx, ndy = -math.cos(t), math.sin(t)
    ax_, ay_ = 8.9, -4.4
    line(ax_, ay_, ax_ + ndx * 1.1, ay_ + ndy * 1.1, '#333', 'stroke-width="1.6"')
    svg.append(f'<circle cx="{px(ax_)}" cy="{py(ay_)}" r="2.5" fill="#333"/>')
    text(ax_ + ndx * 1.55, ay_ + ndy * 1.55, 'N', 12, '#333', extra='font-weight="700"')
    text(1.2, -5.3, '⌄ sea / fjord', 11, '#4d7ba6')
    text(7.6, 14.15, 'road side ⌃', 11, '#777')

    # title block
    svg.append(f'<text x="{px(MX0)+14}" y="{h_px-40}" font-size="16" font-weight="700" '
               f'fill="#222">Kalsneset 27 — catalog cabin concept (ferdighytte)</text>')
    svg.append(f'<text x="{px(MX0)+14}" y="{h_px-20}" font-size="11" fill="#666">'
               f'{WALLS_L:.0f} × {WALLS_W:.1f} m ≈ {WALLS_L * WALLS_W:.0f} m² + hems · '
               f'{PITCH:.0f}° roof · window wall to the sea · concrete slab · '
               f'combined storage/tech room ~19 m² below deck · layout indicative, final plan per '
               f'manufacturer · scale 1:100 @ {S}px/m</text>')
    svg.append('</svg>')

    out = ROOT / 'docs' / 'floorplan.svg'
    out.parent.mkdir(exist_ok=True)
    out.write_text('\n'.join(svg), encoding='utf-8')
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
