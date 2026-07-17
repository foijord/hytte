"""Generate the new-cabin concept: web/newbuild.json (3D records for the viewer)
and docs/floorplan.svg (dimensioned concept floor plan).

Design intent (owner, 2026-07-17):
  - ~90 m2 BRA on ONE level, concrete slab on grade.
  - Same placement/orientation/heights as the existing cabin; total roofed
    footprint kept equal to today's (both wings + annex :3 = ~127 m2) to
    support the strandsone "erstatningshytte, same footprint" dispensation.
  - Wing A = existing main wing envelope (14.1 x 5.4 roof), fully enclosed.
  - Wing B strip alongside (5.4 wide, roofs meet at the shared eave line):
    roof extended to 9.4 m; sea end 2.8 m stays an OPEN covered terrace,
    the remaining 6.6 m is enclosed (entrance + 2 bedrooms).
  - Deck 8 x 3 m in front of the sea-facing gable facade, with two concrete
    rooms below: storage (5.3 m) + technical room (2.7 m, separate entrance).

Derives all placement from web/buildings.json records :1, :2 and deck, so a
MANUAL_PART regeneration automatically carries into the new-build concept.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STRIP_B_ROOF_LEN = 9.4     # m, new wing B roof length (was 5.81)
OUTDOOR_LEN = 2.8          # m, covered open terrace at the sea end of wing B
STORAGE_LEN = 5.3          # m of the 8 m deck over the storage room
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
    w2 = next(b for b in bl if b['id'] == '936839960:2')
    deck = next(b for b in bl if b['id'] == 'deck')

    ang = w1['angleDeg']
    wu, du = unit_vectors(ang)

    def to_en(u, v):
        return (round(w1['cE'] + u * wu[0] + v * du[0], 2),
                round(w1['cN'] + u * wu[1] + v * du[1], 2))

    def to_uv(e, n):
        de, dn = e - w1['cE'], n - w1['cN']
        return de * wu[0] + dn * wu[1], de * du[0] + dn * du[1]

    # local frame sanity: wing 2 sits one wing-width off in +v, flush at the
    # sea (deck) gable end, which is the u- end.
    u2, v2 = to_uv(w2['cE'], w2['cN'])
    v_strip = w1['d'] if v2 > 0 else -w1['d']
    u_deck, _ = to_uv(deck['cE'], deck['cN'])
    assert u_deck < -w1['w'] / 2, 'deck expected off the u- gable end'
    u_sea = -w1['w'] / 2                       # flush sea-facing gable line

    base = w1['base']                          # one shared slab level
    eave_abs = w1['base'] + w1['eave']         # 6.29 NN2000
    ridge_a_abs = w1['base'] + w1['ridge']     # 7.16
    ridge_b_abs = w2['base'] + w2['ridge']     # 6.95

    enclosed_len = STRIP_B_ROOF_LEN - OUTDOOR_LEN
    uB = u_sea + OUTDOOR_LEN + enclosed_len / 2
    uC = u_sea + OUTDOOR_LEN / 2
    eB, nB = to_en(uB, v_strip)
    eC, nC = to_en(uC, v_strip)

    def rec(id_, cE, cN, w, d, b, eave, ridge, pitch, **kw):
        r = {'id': id_, 'type': kw.pop('type', 'cabin'), 'onParcel': True,
             'cE': cE, 'cN': cN, 'w': w, 'd': d, 'angleDeg': ang,
             'base': round(b, 2), 'height': round(ridge, 2),
             'flat': kw.pop('flat', False),
             'eave': round(eave, 2), 'ridge': round(ridge, 2),
             'ridgeAxis': 'w', 'pitchDeg': pitch,
             'overhang': kw.pop('overhang', 0.4),
             'open': kw.pop('open', False), 'backWall': None, 'footprint': []}
        r.update(kw)
        return r

    pitch_b = round(math.degrees(math.atan((ridge_b_abs - eave_abs) / (w1['d'] / 2))), 1)
    out = [
        rec('newbuild:A', w1['cE'], w1['cN'], w1['w'], w1['d'], base,
            eave_abs - base, ridge_a_abs - base, w1['pitchDeg']),
        rec('newbuild:B', eB, nB, round(enclosed_len, 2), w1['d'], base,
            eave_abs - base, ridge_b_abs - base, pitch_b),
        rec('newbuild:C', eC, nC, OUTDOOR_LEN, w1['d'], w2['base'],
            eave_abs - w2['base'], ridge_b_abs - w2['base'], pitch_b, open=True),
    ]

    # deck split into the two concrete rooms below (deck top = old deck top)
    dwu, _ = unit_vectors(deck['angleDeg'])
    tech_len = deck['w'] - STORAGE_LEN
    # deck w+ points toward the wing A side of the facade: storage there,
    # technical room at the other (wing B / covered terrace) end.
    for name, length, off in (('storage', STORAGE_LEN, (deck['w'] - STORAGE_LEN) / 2),
                              ('tech', tech_len, -(deck['w'] - tech_len) / 2)):
        out.append(rec(f'newbuild:{name}',
                       round(deck['cE'] + off * dwu[0], 2),
                       round(deck['cN'] + off * dwu[1], 2),
                       round(length, 2), deck['d'], deck['base'],
                       deck['ridge'], deck['ridge'], 0.0,
                       type='deck', flat=True, overhang=0.0))

    path = ROOT / 'web' / 'newbuild.json'
    path.write_text(json.dumps(out, indent=1), encoding='utf-8')
    roof_area = w1['w'] * w1['d'] + STRIP_B_ROOF_LEN * w1['d']
    print(f'wrote {path} ({len(out)} records, roofed {roof_area:.1f} m2)')

    write_floorplan(w1, deck)


# ---------------------------------------------------------------- floor plan

def write_floorplan(w1, deck):
    """Concept plan in the cabin's local frame. X = across the wings
    (0 = wing A outer roof edge, 10.8 = wing B outer roof edge),
    Y = along the ridge (0 = sea/deck gable line, 14.1 = road end)."""
    S = 40                                    # px per meter
    W_A, W_B = w1['d'], w1['d']               # 5.4 each
    LEN = w1['w']                             # 14.1
    X_B0 = W_A                                # roof valley line
    ENC0, ENC1 = OUTDOOR_LEN, STRIP_B_ROOF_LEN  # wing B enclosed roof span

    # exterior wall envelopes (outer faces), walls inset 0.4 from roof edges
    A = (0.4, W_A, 0.4, LEN - 0.4)            # x0, x1(valley), y0, y1
    B = (X_B0, X_B0 + W_B - 0.4, ENC0, ENC1 - 0.4)

    ax0, ax1 = A[0] + WALL_EXT, A[1] - 0.2    # wing A interior x (to spine)
    bx0, bx1 = B[0] + 0.2, B[1] - WALL_EXT    # wing B interior x
    ay0, ay1 = A[2] + WALL_EXT, A[3] - WALL_EXT
    by0, by1 = B[2] + WALL_EXT, B[3] - WALL_EXT

    corr_w = 1.0
    rooms = []      # (x0, y0, x1, y1, label)

    def room(x0, y0, x1, y1, name):
        rooms.append((x0, y0, x1, y1, f'{name}|{(x1 - x0) * (y1 - y0):.1f} m²'))

    # wing A, sea -> road
    y = ay0
    room(ax0, y, ax1, y + 4.95, 'Living room'); y += 4.95 + PART
    room(ax0, y, ax1, y + 3.65, 'Kitchen / dining'); y += 3.65 + PART
    room(ax0, y, ax1, y + 2.50, 'Master bedroom'); y += 2.50 + PART
    room(ax0, y, ax1, ay1, 'Bathroom')
    # wing B: corridor along the spine, rooms outboard, hall at the road end
    hall0 = by1 - 1.20
    room(bx0, hall0, bx1, by1, 'Entrance hall')
    room(bx0, by0, bx0 + corr_w, hall0 - PART, 'Corr.')
    rx = bx0 + corr_w + PART
    mid = by0 + (hall0 - PART - by0) / 2
    room(rx, by0, bx1, mid - PART / 2, 'Bedroom 3')
    room(rx, mid + PART / 2, bx1, hall0 - PART, 'Bedroom 2')

    # svg canvas: x in [-2.2, 12.6] m, y in [-5.6, 15.6] m (+ title strip)
    MX0, MX1, MY0, MY1 = -2.2, 12.6, -5.6, 15.6
    def px(x): return round((x - MX0) * S, 1)
    def py(y): return round((MY1 - y) * S, 1)
    w_px, h_px = px(MX1), py(MY0) + 70
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w_px} {h_px}" '
           f'font-family="system-ui, sans-serif">',
           f'<rect width="{w_px}" height="{h_px}" fill="#fbf9f4"/>']

    def rect(x0, y0, x1, y1, fill, extra=''):
        svg.append(f'<rect x="{px(x0)}" y="{py(y1)}" width="{round((x1-x0)*S,1)}" '
                   f'height="{round((y1-y0)*S,1)}" fill="{fill}" {extra}/>')

    def line(x0, y0, x1, y1, stroke, extra=''):
        svg.append(f'<line x1="{px(x0)}" y1="{py(y0)}" x2="{px(x1)}" y2="{py(y1)}" '
                   f'stroke="{stroke}" {extra}/>')

    def text(x, y, s, size=11, fill='#333', anchor='middle', extra=''):
        svg.append(f'<text x="{px(x)}" y="{py(y)}" font-size="{size}" fill="{fill}" '
                   f'text-anchor="{anchor}" {extra}>{s}</text>')

    # roof outlines (dashed) + ridges + valley
    dash = 'stroke-dasharray="6 5" fill="none"'
    svg.append(f'<rect x="{px(0)}" y="{py(LEN)}" width="{W_A*S}" height="{LEN*S}" '
               f'stroke="#b0a58f" {dash}/>')
    svg.append(f'<rect x="{px(X_B0)}" y="{py(STRIP_B_ROOF_LEN)}" width="{W_B*S}" '
               f'height="{STRIP_B_ROOF_LEN*S}" stroke="#b0a58f" {dash}/>')
    line(W_A / 2, 0, W_A / 2, LEN, '#b0a58f', 'stroke-dasharray="10 4 2 4"')
    line(X_B0 + W_B / 2, 0, X_B0 + W_B / 2, STRIP_B_ROOF_LEN, '#b0a58f',
         'stroke-dasharray="10 4 2 4"')

    # walls: envelopes filled dark, room interiors punched out in white
    rect(A[0], A[2], A[1], A[3], '#4a4238')
    rect(B[0], B[2], B[1], B[3], '#4a4238')
    for x0, y0, x1, y1, _ in rooms:
        rect(x0, y0, x1, y1, '#ffffff')

    # spine opening kitchen->hall, and living->covered terrace door
    rect(ax1, hall0 - 0.1, bx0, by1 - 0.3, '#ffffff')
    rect(ax1, 1.3, bx0, 2.2, '#ffffff')

    # windows (light blue on exterior walls) and doors (gaps + swing arcs)
    win = '#7fb2d9'
    rect(1.0, A[2] - 0.02, 4.6, A[2] + WALL_EXT + 0.02, win)          # sea glass
    rect(3.5, A[2] - 0.06, 4.5, A[2] + WALL_EXT + 0.06, '#8a5a2b')    # deck slider
    rect(A[0] - 0.02, 6.0, A[0] + WALL_EXT + 0.02, 8.4, win)          # kitchen
    rect(A[0] - 0.02, 10.0, A[0] + WALL_EXT + 0.02, 11.6, win)        # master
    rect(1.4, A[3] - 0.02 - WALL_EXT, 2.9, A[3] + 0.02, win)          # bath/road
    rect(B[1] - WALL_EXT - 0.02, 3.6, B[1] + 0.02, 4.7, win)          # bed 3
    rect(B[1] - WALL_EXT - 0.02, 5.9, B[1] + 0.02, 7.0, win)          # bed 2
    rect(6.9, B[3] - 0.02 - WALL_EXT, 7.9, B[3] + 0.02, '#8a5a2b')    # entry door
    text(7.4, B[3] + 0.35, 'entrance', 10, '#6b5335')

    # covered terrace (open, posts) at the sea end of wing B
    for (cx, cy) in ((X_B0 + 0.45, 0.45), (X_B0 + W_B - 0.45, 0.45),
                     (X_B0 + W_B - 0.45, ENC0 - 0.2)):
        svg.append(f'<rect x="{px(cx)-3}" y="{py(cy)-3}" width="6" height="6" '
                   f'fill="#4a4238"/>')
    text(X_B0 + W_B / 2, 1.5, 'Covered terrace', 11, '#555')
    text(X_B0 + W_B / 2, 1.0, f'{(W_B - 0.8) * ENC0:.0f} m² · open', 10, '#777')

    # deck + concrete rooms below (deck sits just off the sea gable line)
    dy1 = -0.61
    dy0 = dy1 - deck['d']
    dx0 = 0.96
    split = dx0 + STORAGE_LEN
    rect(dx0, dy0, dx0 + deck['w'], dy1, '#e8d9be', 'stroke="#b59a6a"')
    line(split, dy0, split, dy1, '#b59a6a', 'stroke-dasharray="5 4"')
    text((dx0 + split) / 2, (dy0 + dy1) / 2 + 0.35, f'Deck {deck["w"]:.0f} × {deck["d"]:.0f} m', 11, '#6b5335')
    text((dx0 + split) / 2, (dy0 + dy1) / 2 - 0.25, 'Storage 12 m² below', 10, '#8a7350')
    text((split + dx0 + deck['w']) / 2, (dy0 + dy1) / 2 + 0.1, 'Tech 5.5 m²', 10, '#8a7350')
    text((split + dx0 + deck['w']) / 2, (dy0 + dy1) / 2 - 0.4, 'below', 10, '#8a7350')
    for cx in ((dx0 + split) / 2, (split + dx0 + deck['w']) / 2):   # doors below
        rect(cx - 0.45, dy0 - 0.06, cx + 0.45, dy0 + 0.06, '#8a5a2b')
    text(dx0 + deck['w'] / 2, dy0 - 0.5, 'doors to storage / tech on the lower (sea) side', 9, '#999')

    # room labels
    for x0, y0, x1, y1, label in rooms:
        name, area = label.split('|')
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if name == 'Corr.':
            text(cx, cy, 'corr.', 9, '#888', extra=f'transform="rotate(-90 {px(cx)} {py(cy)})"')
            continue
        text(cx, cy + 0.18, name, 11.5, '#222', extra='font-weight="600"')
        text(cx, cy - 0.42, area, 10, '#777')

    # dimension lines
    dim = '#8a6d3b'
    def dimline(x0, y0, x1, y1, label, dx=0, dy=0):
        line(x0, y0, x1, y1, dim)
        for (tx, ty) in ((x0, y0), (x1, y1)):
            line(tx - 0.12 * (0 if x0 != x1 else 1), ty - 0.12 * (0 if y0 != y1 else 1),
                 tx + 0.12 * (0 if x0 != x1 else 1), ty + 0.12 * (0 if y0 != y1 else 1), dim)
        mx, my = (x0 + x1) / 2 + dx, (y0 + y1) / 2 + dy
        rot = f'transform="rotate(-90 {px(mx)} {py(my)})"' if x0 == x1 else ''
        text(mx, my, label, 10.5, dim, extra=rot)

    dimline(-1.3, 0, -1.3, LEN, f'{LEN:.1f} m', dx=-0.35)
    dimline(11.9, 0, 11.9, STRIP_B_ROOF_LEN, f'{STRIP_B_ROOF_LEN:.1f} m', dx=0.4)
    dimline(0, 15.0, W_A + W_B, 15.0, f'{W_A + W_B:.1f} m', dy=0.35)
    dimline(0, 14.55, W_A, 14.55, f'{W_A:.1f}', dy=-0.42)
    dimline(W_A, 14.55, W_A + W_B, 14.55, f'{W_B:.1f}', dy=-0.42)
    dimline(dx0, dy0 - 1.2, dx0 + deck['w'], dy0 - 1.2, f'{deck["w"]:.1f} m', dy=-0.45)

    # orientation: sea side down (NNW), road side up; computed north arrow
    # north in drawing coords: (N . d_unit, N . w_unit)
    t = math.radians(w1['angleDeg'])
    ndx, ndy = -math.cos(t), math.sin(t)
    ax_, ay_ = 11.9, -4.4
    line(ax_, ay_, ax_ + ndx * 1.1, ay_ + ndy * 1.1, '#333', 'stroke-width="1.6"')
    svg.append(f'<circle cx="{px(ax_)}" cy="{py(ay_)}" r="2.5" fill="#333"/>')
    text(ax_ + ndx * 1.55, ay_ + ndy * 1.55, 'N', 12, '#333', extra='font-weight="700"')
    text(1.9, -5.3, '⌄ sea / fjord', 11, '#4d7ba6')
    text(7.9, 15.25, 'road side ⌃', 11, '#777', anchor='middle')

    # title block
    svg.append(f'<text x="{px(MX0)+14}" y="{h_px-40}" font-size="16" font-weight="700" '
               f'fill="#222">Kalsneset 27 — new cabin concept</text>')
    svg.append(f'<text x="{px(MX0)+14}" y="{h_px-20}" font-size="11" fill="#666">'
               f'~90 m² BRA on one level · concrete slab · roofed footprint '
               f'{w1["w"] * w1["d"] + STRIP_B_ROOF_LEN * w1["d"]:.0f} m² (= existing cabin + annex) · '
               f'storage 12 m² + tech 5.5 m² in concrete below deck · scale 1:100 @ {S}px/m</text>')
    svg.append('</svg>')

    out = ROOT / 'docs' / 'floorplan.svg'
    out.parent.mkdir(exist_ok=True)
    out.write_text('\n'.join(svg), encoding='utf-8')
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
