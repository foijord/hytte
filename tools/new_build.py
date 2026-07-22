"""Generate the new-cabin design list: web/newbuild.json (3D records) and
docs/floorplan.svg (dimensioned concept plan of the Furutangen layout).

Each design in DESIGNS gets, auto-fitted to its cabin:
  - a grey concrete slab (0.35 m plinth flush with the walls),
  - the deck/storage: same width as the slab, connected to the sea wall,
    deck surface GROUND_STEP below slab top, concrete storage room below
    (STORAGE_H headroom).
No auto-leveling pad: natural rock meets the slab (minst mulig
terrenginngrep for the dispensation); place manual pads in the viewer
where targeted leveling is wanted.
Gable window wall toward the sea on the old sea-facade line, centered on
the old deck position. Slab top at 3.55 NN2000 (old deck top + 0.06).
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# selectable designs (first = default). Dimensions are wall footprints;
# published widths/lengths are consistent with ridge/gesims/pitch geometry.
DESIGNS = [
    dict(key='A', label='Saltdalshytta Frem 80 · 27°',      # saltdalshytta.no/frem-80:
         form='gable', walls_l=11.7, walls_w=6.3,           # BYA 80, BRA 67.5, no hems,
         pitch=27.0, wall_h=2.90, overhang=0.5),            # monehoyde 4.5
    dict(key='B', label='Familiehytta Furutangen 75 · 30°', # BRA 74 + hems ~38,
         form='gable', walls_l=11.15, walls_w=7.6,          # ridge 5.0 / gesims 2.8
         pitch=30.0, wall_h=2.8, overhang=0.6),
    dict(key='C', label='Saltdalshytta Frem 95 · asym 22°',  # saltdalshytta.no/frem-95 +
         form='asym', depth=9.3, width=9.9, pitch=22.0,     # owner's drawings: BYA 96,
         gesims=2.79, overhang=0.5,                         # BRA 79.2, gesims 2.79 over the
         step=0.97, mone=4.34, front_depth=3.9),            # local floor BOTH sides, trappet
                                                            # step 0.97; monehoyde 4.34 over
                                                            # the upper floor (drawing)
                                                            # saddle, ridge parallel to the
                                                            # long window facade (to the sea),
                                                            # long low plane over the veranda
]
DESIGNS.append(
    dict(key='E', label='Drømmehytten Falstad · split roof', # drommehytten.no/hytter/falstad:
         form='split', width=10.8, depth=8.3,               # BYA 81.6, BRA 71.8 + loft 38.4,
         lean_depth=3.3, front_eave=3.52, attach=5.06,      # gesims 3.52 / gesims2 6.56 (page);
         high=6.56, back_eave=3.44, overhang=0.4))          # attach/back derived ~25/32 deg
DESIGNS.append(
    dict(key='F', label='Drømmehytten Spangereid · funkis', # drommehytten.no/hytter/spangereid:
         form='stack', width=10.4, depth=8.0,               # BYA 85.2, BRA 130.85 (2 floors),
         ground_h=2.75, terrace_depth=2.2,                  # loft 55.2, takterrasse 21.1,
         gesims=5.49, mone=5.94, overhang=0.35))            # gesims 5.49 / mone 5.94, funkis
WALLS_L = 11.15            # floor-plan drawing (Furutangen) only
WALLS_W = 7.6
PITCH = 30.0
WALL_H = 2.8
OVERHANG = 0.6
STORAGE_H = 1.9            # m, under-deck room headroom
GROUND_STEP = 0.06         # m, the deck surface sits this far below slab top
DECK_D = 3.0               # m, deck depth in front of the sea wall
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
    # owner 2026-07-20: whole new build pulled 2.5 m back toward the road
    # from the old sea-facade line (increases distance from the sea)
    u_sea = -w1['w'] / 2 + 2.5
    # owner 2026-07-20: whole new build 0.5 m to the right (~ENE) as seen
    # looking toward the sea = -0.5 in the local across-axis
    v_deck -= 0.5
    deck_top = deck['base'] + deck['ridge']
    base = deck_top + 0.06                    # slab just above the old deck top

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

    def gable_cabin(id_, variant, label, L, W, pitch, wall_h, ov, setback=0.0):
        roof_l, roof_w = L + 2 * ov, W + 2 * ov
        slope = math.tan(math.radians(pitch))
        eave = wall_h - slope * ov
        ridge = eave + slope * roof_w / 2
        u_c = u_sea + setback - ov + roof_l / 2
        cE_, cN_ = to_en(u_c, v_deck)
        return rec(id_, cE_, cN_, round(roof_l, 2), round(roof_w, 2),
                   base, eave, ridge, pitch, overhang=ov,
                   variant=variant, variantLabel=label)

    def fit_deck(cabin, W, setback=0.0):
        """Deck/storage auto-fit: same width as the slab, connected to the
        sea wall, deck surface GROUND_STEP below slab top, STORAGE_H concrete
        room below."""
        wall_face = u_sea + setback
        elev = round(cabin['base'] - GROUND_STEP, 2)
        eD, nD = to_en(wall_face - DECK_D / 2, v_deck)
        return rec(f'{cabin["id"]}:deck', eD, nD, DECK_D, round(W + 0.05, 2),
                   elev - STORAGE_H, STORAGE_H, STORAGE_H, 0.0,
                   type='slab', flat=True, overhang=0.0,
                   variant=cabin['variant'], variantLabel=cabin['variantLabel'])

    def mono_cabin(id_, variant, label, depth, width, pitch, high_wall, ov):
        """Pulttak: high wall (window side) toward the sea, roof sloping
        down toward the road. eave/ridge are the low/high ROOF edges."""
        slope = math.tan(math.radians(pitch))
        roof_u, roof_v = depth + 2 * ov, width + 2 * ov
        ridge = high_wall + slope * ov          # sea-side roof edge
        eave = ridge - slope * roof_u           # road-side roof edge
        u_c = u_sea - ov + roof_u / 2
        cE_, cN_ = to_en(u_c, v_deck)
        return rec(id_, cE_, cN_, round(roof_u, 2), round(roof_v, 2),
                   base, eave, ridge, pitch, overhang=ov, mono=True,
                   variant=variant, variantLabel=label)

    def asym_cabin(id_, variant, label, depth, width, pitch, gesims, ov,
                   step=0.0, mone=None):
        """Asymmetric saddle from drawing values: gesims (wall height over
        the LOCAL floor) on both sides, equal pitch, trappet step - the
        living (sea) half at the normal slab level, back half stepped up.
        Ridge position and height are derived from where the planes meet.
        Record base = living floor; ridge along the facade (ridgeAxis 'd')."""
        slope = math.tan(math.radians(pitch))
        roof_u, roof_v = depth + 2 * ov, width + 2 * ov
        e_sea = gesims - slope * ov                  # sea roof edge over base
        e_road = step + gesims - slope * ov          # road roof edge over base
        if mone is not None:                         # drawing monehoyde over the upper floor
            ridge = step + mone
        else:
            ridge = (e_sea + e_road + slope * roof_u) / 2
        off = round((ridge - e_sea) / slope - roof_u / 2, 2)   # apex, + = road
        off = min(off, roof_u / 2 - 0.3)
        u_c = u_sea - ov + roof_u / 2
        cE_, cN_ = to_en(u_c, v_deck)
        return rec(id_, cE_, cN_, round(roof_u, 2), round(roof_v, 2), base,
                   round(e_road, 2), round(ridge, 2), pitch,
                   overhang=ov, ridgeAxis='d', ridgeOff=off,
                   eave2=round(e_sea, 2), noCut=True,
                   variant=variant, variantLabel=label)

    def stepped_slabs(cabin, depth, W, step, front_d):
        """Trappet slab: living (sea) half at the normal slab level, back
        half a step up into the rising terrain. The cabin volume is noCut,
        so these two slabs define the stepped excavation."""
        lo = cabin['base']
        e1, n1 = to_en(u_sea + front_d / 2, v_deck)
        e2, n2 = to_en(u_sea + front_d + (depth - front_d) / 2, v_deck)
        front = rec(f'{cabin["id"]}:slab', e1, n1,
                    round(front_d + 0.05, 2), round(W + 0.05, 2),
                    lo - 0.35, 0.35, 0.35, 0.0,
                    type='slab', flat=True, overhang=0.0, onParcel=False,
                    variant=cabin['variant'], variantLabel=cabin['variantLabel'])
        back = rec(f'{cabin["id"]}:slab2', e2, n2,
                   round(depth - front_d + 0.05, 2), round(W + 0.05, 2),
                   lo, step, step, 0.0,
                   type='slab', flat=True, overhang=0.0, onParcel=False,
                   variant=cabin['variant'], variantLabel=cabin['variantLabel'])
        return [front, back]

    def split_cabin(d):
        """Falstad-style split roof: front lean-to (low eave toward the sea,
        rising to a clerestory band) + tall back volume whose mono roof peaks
        at the clerestory wall (high, sea side) and falls toward the road.
        Two mono records; the lean-to is rotated 180 so its high edge faces
        the road."""
        ov = d['overhang']
        W, DEP, LD = d['width'], d['depth'], d['lean_depth']
        key, label = d['key'], d['label']
        # lean-to: u_sea .. u_sea+LD, high edge at the road side (attach);
        # 3 cm short of the junction so the abutting wall faces are not
        # coplanar with the tall volume (z-fighting)
        LDe = LD - 0.03
        u_c1 = u_sea - ov + (LDe + 2 * ov) / 2
        e1, n1 = to_en(u_c1, v_deck)
        lean = rec(f'newbuild:{key}', e1, n1, round(LDe + 2 * ov, 2),
                   round(W + 2 * ov, 2), base,
                   d['front_eave'], d['attach'], 25.0,
                   overhang=ov, mono=True, angleDeg=ang + 180,
                   variant=key, variantLabel=label)
        # tall volume: u_sea+LD .. u_sea+DEP, high edge at the sea side (clerestory)
        u_c2 = u_sea + LD - ov + (DEP - LD + 2 * ov) / 2
        e2, n2 = to_en(u_c2, v_deck)
        tall = rec(f'newbuild:{key}:tall', e2, n2, round(DEP - LD + 2 * ov, 2),
                   round(W + 2 * ov, 2), base,
                   d['back_eave'], d['high'], 32.0,
                   overhang=ov, mono=True,
                   variant=key, variantLabel=label)
        # one slab under the whole footprint
        eS, nS = to_en(u_sea + DEP / 2, v_deck)
        sl = rec(f'newbuild:{key}:slab', eS, nS, round(DEP + 0.05, 2),
                 round(W + 0.05, 2), base - 0.35, 0.35, 0.35, 0.0,
                 type='slab', flat=True, overhang=0.0, onParcel=False,
                 variant=key, variantLabel=label)
        return [lean, tall, sl, fit_deck(lean, W)]

    def stack_cabin(d):
        """Spangereid-style funkis: full-footprint ground floor with a flat
        roof (the sea-side part becomes the roof terrace), set-back upper
        floor with a near-flat mono roof, high edge toward the sea."""
        ov = d['overhang']
        W, DEP, TD = d['width'], d['depth'], d['terrace_depth']
        key, label = d['key'], d['label']
        gh = d['ground_h']
        eG, nG = to_en(u_sea + DEP / 2, v_deck)
        ground = rec(f'newbuild:{key}', eG, nG, round(DEP, 2), round(W, 2),
                     base, gh, gh, 0.0, flat=True, overhang=0.0,
                     variant=key, variantLabel=label)
        ud = DEP - TD                             # upper volume depth
        u_c = u_sea + TD - ov + (ud + 2 * ov) / 2
        eU, nU = to_en(u_c, v_deck)
        upper = rec(f'newbuild:{key}:upper', eU, nU, round(ud + 2 * ov, 2),
                    round(W + 2 * ov, 2), base + gh + 0.02,
                    round(d['gesims'] - gh, 2), round(d['mone'] - gh, 2), 3.2,
                    overhang=ov, mono=True, noCut=True,
                    variant=key, variantLabel=label)
        eS, nS = to_en(u_sea + DEP / 2, v_deck)
        sl = rec(f'newbuild:{key}:slab', eS, nS, round(DEP + 0.05, 2),
                 round(W + 0.05, 2), base - 0.35, 0.35, 0.35, 0.0,
                 type='slab', flat=True, overhang=0.0, onParcel=False,
                 variant=key, variantLabel=label)
        return [ground, upper, sl, fit_deck(ground, W)]

    out = []
    for d in DESIGNS:
        if d.get('form') == 'stack':
            out += stack_cabin(d)
            print(f"  {d['label']}: {d['width']}x{d['depth']}, top abs "
                  f"{base + d['mone']:.2f} (funkis, roof terrace)")
            continue
        if d.get('form') == 'split':
            out += split_cabin(d)
            print(f"  {d['label']}: {d['width']}x{d['depth']}, top abs "
                  f"{base + d['high']:.2f} (clerestory)")
            continue
        if d.get('form') == 'asym':
            cabin = asym_cabin(f'newbuild:{d["key"]}', d['key'], d['label'],
                               d['depth'], d['width'], d['pitch'],
                               d['gesims'], d['overhang'],
                               step=d.get('step', 0.0), mone=d.get('mone'))
            L, W = d['depth'], d['width']
            out += [cabin] + stepped_slabs(cabin, L, W, d.get('step', 0.0),
                                           d.get('front_depth', L / 2))
            out.append(fit_deck(cabin, W))
            print(f"  {d['label']}: walls {L}x{W}, high point abs "
                  f"{cabin['base'] + cabin['ridge']:.2f} (trappet; monehoyde over "
                  f"upper floor = {cabin['ridge'] - d['step']:.2f})")
            continue
        elif d.get('form') == 'mono':
            cabin = mono_cabin(f'newbuild:{d["key"]}', d['key'], d['label'],
                               d['depth'], d['width'], d['pitch'],
                               d['high_wall'], d['overhang'])
            L, W = d['depth'], d['width']
        else:
            cabin = gable_cabin(f'newbuild:{d["key"]}', d['key'], d['label'],
                                d['walls_l'], d['walls_w'], d['pitch'],
                                d['wall_h'], d['overhang'])
            L, W = d['walls_l'], d['walls_w']
        out += [cabin, slab(cabin, L, W), fit_deck(cabin, W)]
        print(f"  {d['label']}: walls {L}x{W}, high point abs {base + cabin['ridge']:.2f}")

    path = ROOT / 'web' / 'newbuild.json'
    path.write_text(json.dumps(out, indent=1), encoding='utf-8')
    print(f'wrote {path} ({len(out)} records; old cabin ridge abs '
          f'{w1["base"] + w1["ridge"]:.2f})')

    write_floorplan()


# ---------------------------------------------------------------- floor plan

def write_floorplan():
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

    # the connected deck/storage: same width as the slab, on the sea wall
    padW = WALLS_W
    px0 = x0
    dy1 = y0
    dy0 = dy1 - DECK_D
    dx0 = px0
    rect(dx0, dy0, dx0 + padW, dy1, '#e8d9be', 'stroke="#b59a6a"')
    dcx, dcy = dx0 + padW / 2, (dy0 + dy1) / 2
    text(dcx, dcy + 0.35, f'Deck {padW:.1f} × {DECK_D:.0f} m', 11, '#6b5335')
    text(dcx, dcy - 0.25, f'Storage / tech room ~{(padW - 0.5) * (DECK_D - 0.5):.0f} m² · h {STORAGE_H} m below', 10, '#8a7350')
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
    dimline(dx0, dy0 - 1.2, dx0 + padW, dy0 - 1.2, f'{padW:.1f} m', dy=-0.45)

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
