"""Generate the new-cabin concept: web/newbuild.json (3D records for the viewer)
and docs/floorplan.svg (dimensioned concept floor plan).

Design intent (owner, 2026-07-17; model chosen 2026-07-20; orientation
revised same day for deck sun):
  - Familiehytta FURUTANGEN 75 MED HEMS massing (published specs: BRA 74 m2,
    GUA 112 m2 incl. ~38 m2 hems, length 11.15 m, width 8.85 m incl.
    overhang, ridge 5.0 m, gesims 2.8 m, 30 deg roof, hems headroom 1.89 m;
    wall span 7.6 derived from ridge/gesims/pitch).
  - EAVE TOWARD THE SEA: the 11.15 m long side faces the deck on the old
    sea-facade line, ridge parallel to the shoreline. The deck then faces a
    ~6.35 m eave instead of an 8.54 m gable apex, roughly halving the midday
    shadow on the deck. Window band along the long sea wall (the actual
    catalog model would need a long-side-glass variant - massing study).
  - Slab top at deck surface + 0.06 (3.55 NN2000). Ridge abs 8.54 (+1.38 vs
    old cabin) - dispensation point; 25 deg fallback ~8.1.
  - Deck 8 x 3 m stays; ONE concrete room below, 1.9 m headroom
    (floor +1.59 NN2000), single entrance on the sea side.

Derives placement from web/buildings.json records :1 and deck, so a
MANUAL_PART regeneration automatically carries into the concept.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

WALLS_L = 11.15            # m, Furutangen 75 wall footprint (along the facade)
WALLS_W = 7.6              # m, depth (roof span)
PITCH = 30.0               # deg, Furutangen standard
WALL_H = 2.8               # m, gesims height
OVERHANG = 0.6
STORAGE_H = 1.9            # m, under-deck room headroom
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
    u_sea_wall = -w1['w'] / 2

    # eave orientation: depth (7.6) along u, length (11.15) along v,
    # ridge along v (record axis 'd')
    roof_u = WALLS_W + 2 * OVERHANG           # 8.8, across the ridge
    roof_v = WALLS_L + 2 * OVERHANG           # 12.35, along the ridge
    u_c = u_sea_wall - OVERHANG + roof_u / 2
    v_c = v_deck                              # centered on the deck
    cE, cN = to_en(u_c, v_c)

    slope = math.tan(math.radians(PITCH))
    eave = WALL_H - slope * OVERHANG          # roof-edge height above base
    ridge = eave + slope * roof_u / 2
    # slab top just above the deck surface (small step down to the deck)
    deck_top = deck['base'] + deck['ridge']
    base = deck_top + 0.06

    def rec(id_, cE_, cN_, w, d, b, eave_, ridge_, pitch, **kw):
        r = {'id': id_, 'type': kw.pop('type', 'cabin'), 'onParcel': True,
             'cE': cE_, 'cN': cN_, 'w': w, 'd': d, 'angleDeg': ang,
             'base': round(b, 2), 'height': round(ridge_, 2),
             'flat': kw.pop('flat', False),
             'eave': round(eave_, 2), 'ridge': round(ridge_, 2),
             'ridgeAxis': kw.pop('ridgeAxis', 'w'), 'pitchDeg': pitch,
             'overhang': kw.pop('overhang', OVERHANG),
             'open': False, 'backWall': None, 'footprint': []}
        r.update(kw)
        return r

    out = [rec('newbuild:cabin', cE, cN, round(roof_u, 2), round(roof_v, 2),
               base, eave, ridge, PITCH, ridgeAxis='d')]

    # one combined storage + technical room under the deck (deck top
    # unchanged, floor excavated for 1.9 m headroom); deck keeps its own
    # angle, which is 90 deg off the cabin's
    out.append(rec('newbuild:storage', deck['cE'], deck['cN'],
                   deck['w'], deck['d'], deck_top - STORAGE_H,
                   STORAGE_H, STORAGE_H, 0.0,
                   type='deck', flat=True, overhang=0.0,
                   angleDeg=deck['angleDeg']))

    path = ROOT / 'web' / 'newbuild.json'
    path.write_text(json.dumps(out, indent=1), encoding='utf-8')
    print(f'wrote {path} ({len(out)} records, cabin ridge abs '
          f'{base + ridge:.2f} vs old {w1["base"] + w1["ridge"]:.2f} NN2000, '
          f'eave toward sea at abs {base + WALL_H:.2f})')

    write_floorplan(deck)


# ---------------------------------------------------------------- floor plan

def write_floorplan(deck):
    """Concept plan, eave-to-sea orientation: X = along the facade
    (11.15 m side, sea at the bottom), Y = depth (7.6 m). Layout indicative -
    the real plan comes from the manufacturer's long-side-glass variant."""
    S = 40                                    # px per meter
    ROOF_X, ROOF_Y = WALLS_L + 2 * OVERHANG, WALLS_W + 2 * OVERHANG

    x0, x1 = OVERHANG, OVERHANG + WALLS_L     # wall outer faces
    y0, y1 = OVERHANG, OVERHANG + WALLS_W
    ix0, ix1 = x0 + WALL_EXT, x1 - WALL_EXT   # interior 10.65 x 7.1
    iy0, iy1 = y0 + WALL_EXT, y1 - WALL_EXT

    rooms = []      # (x0, y0, x1, y1, label)

    def room(rx0, ry0, rx1, ry1, name):
        rooms.append((rx0, ry0, rx1, ry1, f'{name}|{(rx1 - rx0) * (ry1 - ry0):.1f} m²'))

    # sea band: one long allrom with the window wall; road band under the
    # hems: two bedrooms, bath, entrance + stair
    sea_d = 3.60
    band0 = iy0 + sea_d + PART
    room(ix0, iy0, ix1, iy0 + sea_d, 'Allrom — stue / kjøkken')
    xx = ix0
    room(xx, band0, xx + 2.70, iy1, 'Bedroom 1'); xx += 2.70 + PART
    room(xx, band0, xx + 2.70, iy1, 'Bedroom 2'); xx += 2.70 + PART
    room(xx, band0, xx + 1.75, iy1, 'Bath'); xx += 1.75 + PART
    room(xx, band0, ix1, iy1, 'Entrance + stair')

    # svg canvas
    MX0, MX1, MY0, MY1 = -2.2, 14.2, -5.8, 10.9
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

    # roof outline (dashed) + ridge line (parallel to the facade)
    svg.append(f'<rect x="{px(0)}" y="{py(ROOF_Y)}" width="{ROOF_X*S}" height="{ROOF_Y*S}" '
               f'stroke="#b0a58f" stroke-dasharray="6 5" fill="none"/>')
    line(0, ROOF_Y / 2, ROOF_X, ROOF_Y / 2, '#b0a58f', 'stroke-dasharray="10 4 2 4"')

    # walls filled dark, room interiors punched out in white
    rect(x0, y0, x1, y1, '#4a4238')
    for rx0, ry0, rx1, ry1, _ in rooms:
        rect(rx0, ry0, rx1, ry1, '#ffffff')

    # hems overlay (loft over the road-side band)
    rect(x0 + 0.06, band0 - PART, x1 - 0.06, y1 - 0.06, 'none',
         'stroke="#c2703e" stroke-width="2" stroke-dasharray="9 6"')
    text((ix0 + ix1) / 2, band0 + 0.3, 'hems above · ~38 m² (GUA)', 9.5, '#c2703e')

    # windows (light blue) and doors (brown)
    win = '#7fb2d9'
    rect(1.4, y0 - 0.02, 10.4, y0 + WALL_EXT + 0.02, win)             # sea window band
    rect(5.4, y0 - 0.06, 6.4, y0 + WALL_EXT + 0.06, '#8a5a2b')        # deck slider
    rect(x0 - 0.02, 1.4, x0 + WALL_EXT + 0.02, 2.9, win)              # gable W
    rect(x1 - WALL_EXT - 0.02, 1.4, x1 + 0.02, 2.9, win)              # gable E
    rect(1.3, y1 - 0.02 - WALL_EXT, 2.5, y1 + 0.02, win)              # bedroom 1
    rect(4.2, y1 - 0.02 - WALL_EXT, 5.4, y1 + 0.02, win)              # bedroom 2
    rect(9.5, y1 - 0.06 - WALL_EXT, 10.5, y1 + 0.06, '#8a5a2b')       # entry door
    text(10.0, y1 + 0.35, 'entrance', 10, '#6b5335')

    # deck + the concrete room below, true footprint offset to the cabin
    # (deck centered on the facade, 0.61 m off the wall face)
    dy1 = y0 - 0.61
    dy0 = dy1 - deck['d']
    dx0 = ROOF_X / 2 - deck['w'] / 2
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

    dimline(-1.3, 0, -1.3, ROOF_Y, f'{ROOF_Y:.1f} m roof', dx=-0.35)
    dimline(-0.75, y0, -0.75, y1, f'{WALLS_W:.1f} m', dx=0.38)
    dimline(0, 10.35, ROOF_X, 10.35, f'{ROOF_X:.2f} m roof', dy=0.35)
    dimline(x0, 9.85, x1, 9.85, f'{WALLS_L:.2f} m', dy=-0.42)
    dimline(dx0, dy0 - 1.2, dx0 + deck['w'], dy0 - 1.2, f'{deck["w"]:.1f} m', dy=-0.45)

    # orientation: sea side down (NNW); north arrow from the record angle
    bl = json.load(open(ROOT / 'web' / 'buildings.json', encoding='utf-8'))
    w1 = next(b for b in bl if b['id'] == '936839960:1')
    t = math.radians(w1['angleDeg'])
    # drawing X = old-frame v axis, drawing Y = old-frame u axis
    ndx, ndy = -math.cos(t), math.sin(t)
    ax_, ay_ = 13.4, -4.6
    line(ax_, ay_, ax_ + ndx * 1.1, ay_ + ndy * 1.1, '#333', 'stroke-width="1.6"')
    svg.append(f'<circle cx="{px(ax_)}" cy="{py(ay_)}" r="2.5" fill="#333"/>')
    text(ax_ + ndx * 1.55, ay_ + ndy * 1.55, 'N', 12, '#333', extra='font-weight="700"')
    text(1.2, -5.5, '⌄ sea / fjord', 11, '#4d7ba6')
    text(12.9, 10.65, 'road side ⌃', 11, '#777')

    # title block
    svg.append(f'<text x="{px(MX0)+14}" y="{h_px-40}" font-size="16" font-weight="700" '
               f'fill="#222">Kalsneset 27 — Furutangen 75 massing, eave toward the sea (approx.)</text>')
    svg.append(f'<text x="{px(MX0)+14}" y="{h_px-20}" font-size="11" fill="#666">'
               f'walls {WALLS_L:.2f} × {WALLS_W:.1f} m · BRA 74 m² + hems ~38 m² · '
               f'{PITCH:.0f}° roof, ridge 5.0 / gesims 2.8 · window band on the long sea wall · '
               f'storage/tech ~19 m², h {STORAGE_H} m below deck · layout indicative, final plan per '
               f'manufacturer · scale 1:100 @ {S}px/m</text>')
    svg.append('</svg>')

    out = ROOT / 'docs' / 'floorplan.svg'
    out.parent.mkdir(exist_ok=True)
    out.write_text('\n'.join(svg), encoding='utf-8')
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
