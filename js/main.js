import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { TransformControls } from 'three/addons/controls/TransformControls.js';

// Scene axes: x = east, y = up (meters, NN2000), z = south.
// Origin = address point (E 71428.47, N 6458099.03), see data/README.md.
//
// Buildings are parametric groups: walls (pentagon prism with gable ends,
// inset by the roof overhang — footprints trace the roof edge) + saddle-roof
// planes. rec fields: w, d (roof rect), eave, ridge (heights above base),
// ridgeAxis 'w'|'d', overhang, flat.

const status = document.getElementById('status');
const selInfo = document.getElementById('selinfo');

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
document.getElementById('app').appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b1420);
scene.fog = new THREE.Fog(0x0b1420, 800, 2500);

const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.5, 5000);
camera.position.set(16, 13, -62);   // from the sea, north-east of the cabin

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(-2, 5, 0);
controls.maxPolarAngle = Math.PI / 2 - 0.02;
controls.enableDamping = true;

// optional overrides: ?cam=x,y,z&tgt=x,y,z&labels=off&cut=off
const q = new URLSearchParams(location.search);
if (q.has('cam')) camera.position.fromArray(q.get('cam').split(',').map(Number));
if (q.has('tgt')) controls.target.fromArray(q.get('tgt').split(',').map(Number));

scene.add(new THREE.HemisphereLight(0xbfd7ff, 0x5c4f3d, 0.9));
const sun = new THREE.DirectionalLight(0xfff1da, 1.8);
sun.position.set(-150, 260, 180);
scene.add(sun);
scene.add(sun.target);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.left = -130; sun.shadow.camera.right = 130;
sun.shadow.camera.top = 130; sun.shadow.camera.bottom = -130;
sun.shadow.camera.near = 150; sun.shadow.camera.far = 700;
sun.shadow.bias = -0.0004;
sun.shadow.normalBias = 2;

// ------------------------------------------------ sun simulation (58.056N)
// solar-time position for the property; month is fractional (6.5 = mid-June)
const LAT = THREE.MathUtils.degToRad(58.056);
const SOLAR_TO_CEST = 2 - 7.729 / 15;     // ~+1.5 h from solar to local summer time

function sunDirection(month, hour) {
  const n = Math.floor((month - 1) * 30.44 + 15);
  const decl = THREE.MathUtils.degToRad(23.45) * Math.sin(2 * Math.PI * (284 + n) / 365);
  const H = THREE.MathUtils.degToRad((hour - 12) * 15);
  const el = Math.asin(Math.sin(LAT) * Math.sin(decl) + Math.cos(LAT) * Math.cos(decl) * Math.cos(H));
  const azS = Math.atan2(Math.sin(H), Math.cos(H) * Math.sin(LAT) - Math.tan(decl) * Math.cos(LAT));
  const azN = azS + Math.PI;              // from north, clockwise (east = 90)
  return { el, x: Math.sin(azN) * Math.cos(el), y: Math.sin(el), z: -Math.cos(azN) * Math.cos(el) };
}

let sunSimOn = true, sunMonth = 6.5, sunHour = 15;

function updateSun() {
  if (!sunSimOn) {
    sun.position.set(-150, 260, 180);
    sun.intensity = 1.8;
    sun.castShadow = false;
  } else {
    const d = sunDirection(sunMonth, sunHour);
    sun.position.set(d.x * 400, Math.max(d.y, 0.02) * 400, d.z * 400);
    sun.intensity = d.el > 0 ? 1.8 : 0.05;
    sun.castShadow = d.el > 0;
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const local = sunHour + SOLAR_TO_CEST;
    const hm = h => `${Math.floor(h)}:${String(Math.round((h % 1) * 60)).padStart(2, '0')}`;
    document.getElementById('sunlabel').textContent =
      `${months[Math.min(11, Math.floor(sunMonth - 1))]} · ${hm(sunHour)} solar (≈${hm(local)} CEST)` +
      (d.el > 0 ? ` · sun ${THREE.MathUtils.radToDeg(d.el).toFixed(0)}°` : ' · below horizon');
  }
}

let terrainMeta = null;
let terrainMesh = null;
let heightGrid = null;      // original heights, used for draping the parcel line
let terrainGeo = null;
let originalHeights = null;
let excavateOn = true;
let labelsOn = false;
// new build: an on/off toggle plus a selected design from the list in
// web/newbuild.json (records tagged with variant/variantLabel)
let newBuildOn = true;
let newVariant = null;       // chosen design key; defaults to the first found
let variantList = [];        // [{key, label}] discovered from newbuild.json
// records replaced by the new-build concept (web/newbuild.json):
// main cabin, outdoor wing, the small attached storage (:3) and the deck
const OLD_CABIN_IDS = new Set(['936839960:1', '936839960:2', '936839960:3', 'deck']);
const qNew = q.get('new');
if (qNew === 'off') newBuildOn = false;
else if (qNew && qNew !== '1') newVariant = qNew.toUpperCase();
if (q.get('labels') === 'on') {
  labelsOn = true;
  document.getElementById('labels').textContent = 'labels: on';
}
if (q.get('cut') === 'off') {
  excavateOn = false;
  document.getElementById('excav').textContent = 'terrain cut: off';
}
const qSun = q.get('sun');          // ?sun=month,hour (solar time) or ?sun=off
if (qSun === 'off') {
  sunSimOn = false;
  document.getElementById('sun').textContent = 'sun: off';
  document.getElementById('sunctl').style.display = 'none';
} else if (qSun) {
  const [m, h] = qSun.split(',').map(Number);
  if (Number.isFinite(m)) sunMonth = m;
  if (Number.isFinite(h)) sunHour = h;
  document.getElementById('sunmonth').value = sunMonth;
  document.getElementById('sunhour').value = sunHour;
}
updateSun();

function heightAt(e, n) {
  const m = terrainMeta;
  const fx = Math.min(Math.max((e - m.e0) / m.res, 0), m.cols - 1.001);
  const fz = Math.min(Math.max((m.n0 - n) / m.res, 0), m.rows - 1.001);
  const j = Math.floor(fx), i = Math.floor(fz);
  const dx = fx - j, dz = fz - i;
  const g = heightGrid, w = m.cols;
  return (g[i * w + j] * (1 - dx) + g[i * w + j + 1] * dx) * (1 - dz)
       + (g[(i + 1) * w + j] * (1 - dx) + g[(i + 1) * w + j + 1] * dx) * dz;
}

async function buildTerrain() {
  const meta = await (await fetch('web/meta.json')).json();
  const buf = await (await fetch('web/heights.bin')).arrayBuffer();
  const heights = new Float32Array(buf);
  terrainMeta = meta;
  heightGrid = heights;

  const { cols, rows, res, e0, n0, originE, originN } = meta;
  status.textContent = `building mesh ${cols}×${rows}…`;
  await new Promise(r => setTimeout(r));

  const positions = new Float32Array(cols * rows * 3);
  const uvs = new Float32Array(cols * rows * 2);
  let p = 0, t = 0;
  for (let i = 0; i < rows; i++) {
    const n = n0 - i * res;
    const z = originN - n;
    const v = 1 - i / (rows - 1);
    for (let j = 0; j < cols; j++) {
      positions[p++] = (e0 + j * res) - originE;
      positions[p++] = heights[i * cols + j];
      positions[p++] = z;
      uvs[t++] = j / (cols - 1);
      uvs[t++] = v;
    }
  }

  const indices = new Uint32Array((rows - 1) * (cols - 1) * 6);
  let k = 0;
  for (let i = 0; i < rows - 1; i++) {
    for (let j = 0; j < cols - 1; j++) {
      const a = i * cols + j, b = a + 1, c = a + cols, d = c + 1;
      indices[k++] = a; indices[k++] = c; indices[k++] = b;
      indices[k++] = b; indices[k++] = c; indices[k++] = d;
    }
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
  geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(cols * rows * 3).fill(1), 3));
  geo.setIndex(new THREE.BufferAttribute(indices, 1));
  geo.computeVertexNormals();
  terrainGeo = geo;
  originalHeights = heights.slice();

  let tex = null;
  for (let attempt = 0; attempt < 3 && !tex; attempt++) {
    try {
      tex = await new THREE.TextureLoader().loadAsync('data/ortho_16cm.jpg');
    } catch {
      await new Promise(r => setTimeout(r, 400));
    }
  }
  const mat = new THREE.MeshStandardMaterial({ roughness: 1.0, metalness: 0.0, vertexColors: true });
  if (tex) {
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
    mat.map = tex;
  } else {
    mat.color.setHex(0x76705f);
    console.warn('orthophoto failed to load, rendering untextured');
  }
  terrainMesh = new THREE.Mesh(geo, mat);
  terrainMesh.castShadow = true;
  terrainMesh.receiveShadow = true;
  scene.add(terrainMesh);
}

function addWater() {
  const geo = new THREE.PlaneGeometry(3000, 3000);
  geo.rotateX(-Math.PI / 2);
  const mat = new THREE.MeshStandardMaterial({
    color: 0x18456b, roughness: 0.25, metalness: 0.0,
    transparent: true, opacity: 0.62,
  });
  const water = new THREE.Mesh(geo, mat);
  water.position.y = -0.45;
  scene.add(water);
}

async function addParcel() {
  const gj = await (await fetch('data/property_437_109.geojson')).json();
  const m = terrainMeta;
  for (const f of gj.features) {
    for (const ring of f.geometry.coordinates) {
      // resample each edge so the line drapes onto the terrain between
      // the polygon vertices instead of cutting through knolls and dips
      const pts = [];
      for (let i = 0; i < ring.length - 1; i++) {
        const [e0, n0] = ring[i], [e1, n1] = ring[i + 1];
        const steps = Math.max(1, Math.ceil(Math.hypot(e1 - e0, n1 - n0) / 0.75));
        for (let s = 0; s < steps; s++) {
          const e = e0 + (e1 - e0) * s / steps;
          const n = n0 + (n1 - n0) * s / steps;
          pts.push(new THREE.Vector3(e - m.originE, heightAt(e, n) + 0.35, m.originN - n));
        }
      }
      pts.push(pts[0].clone());
      const geo = new THREE.BufferGeometry().setFromPoints(pts);
      scene.add(new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0xffe95c })));
    }
  }
}

// ---------------------------------------------------------------- buildings

const buildingsGroup = new THREE.Group();
scene.add(buildingsGroup);
let buildingsSource = 'generated';

function normalizeRec(b) {
  const rec = {
    overhang: 0, open: false, backWall: null, variant: null, mono: false,
    eave2: null, ridgeOff: 0, noCut: false, ...b,
  };
  if (!Array.isArray(rec.cutExt) || rec.cutExt.length !== 4) rec.cutExt = [0, 0, 0, 0];
  if (rec.ridge == null || rec.flat == null) {   // legacy plain-box record
    rec.flat = true;
    rec.ridge = rec.height ?? 2.5;
    rec.eave = rec.ridge;
    rec.ridgeAxis = 'w';
    rec.overhang = 0;
  }
  rec.footprint = rec.footprint ?? [];
  return rec;
}

function wallColor(rec) {
  if (rec.type === 'slab') return 0xaeb2b5;   // concrete
  return rec.type === 'deck' ? 0xb5885e : (rec.onParcel ? 0xe8913a : 0x9fb2c4);
}

function pitchDeg(rec, sy = 1, sx = 1, sz = 1) {
  if (rec.flat) return 0;
  if (rec.mono) return THREE.MathUtils.radToDeg(Math.atan((rec.ridge - rec.eave) * sy / (rec.w * sx)));
  const span = (rec.ridgeAxis === 'd' ? rec.w * sx : rec.d * sz) / 2;
  return THREE.MathUtils.radToDeg(Math.atan((rec.ridge - rec.eave) * sy / span));
}

function wallsGeometry(rec) {
  if (rec.flat) {
    const g = new THREE.BoxGeometry(rec.w, rec.ridge, rec.d);
    g.translate(0, rec.ridge / 2, 0);
    return g;
  }
  if (rec.mono) {
    // pulttak: high roof edge at local w- (ridge), low at w+ (eave);
    // wall tops follow the roof plane, inset by the overhang
    const ov = rec.overhang;
    const hw = Math.max(rec.w / 2 - ov, 0.2);
    const hd = Math.max(rec.d / 2 - ov, 0.2);
    const slope = (rec.ridge - rec.eave) / rec.w;
    const hHigh = Math.max(rec.ridge - slope * ov, 0.3);
    const hLow = Math.max(rec.eave + slope * ov, 0.3);
    const shape = new THREE.Shape([
      new THREE.Vector2(-hw, 0),
      new THREE.Vector2(hw, 0),
      new THREE.Vector2(hw, hLow),
      new THREE.Vector2(-hw, hHigh),
    ]);
    const g = new THREE.ExtrudeGeometry(shape, { depth: 2 * hd, bevelEnabled: false });
    g.translate(0, 0, -hd);
    return g;
  }
  // build with ridge along local x; W = extent along ridge, D across.
  // eave2 (far side) and ridgeOff support asymmetric saddles.
  const [W, D] = rec.ridgeAxis === 'd' ? [rec.d, rec.w] : [rec.w, rec.d];
  const ov = rec.overhang;
  const hw = Math.max(W / 2 - ov, 0.2);
  const hd = Math.max(D / 2 - ov, 0.2);
  const e1 = rec.eave;
  const e2 = rec.eave2 ?? rec.eave;
  const off = THREE.MathUtils.clamp(rec.ridgeOff ?? 0, -hd + 0.1, hd - 0.1);
  const s1 = (rec.ridge - e1) / Math.max(D / 2 - off, 0.1);
  const s2 = (rec.ridge - e2) / Math.max(D / 2 + off, 0.1);
  const t1 = Math.max(e1 + s1 * ov, 0.3);
  const t2 = Math.max(e2 + s2 * ov, 0.3);
  const shape = new THREE.Shape([
    new THREE.Vector2(-hd, 0),
    new THREE.Vector2(hd, 0),
    new THREE.Vector2(hd, t1),
    new THREE.Vector2(off, Math.max(rec.ridge - 0.02, Math.max(t1, t2))),
    new THREE.Vector2(-hd, t2),
  ]);
  const g = new THREE.ExtrudeGeometry(shape, { depth: 2 * hw, bevelEnabled: false });
  g.translate(0, 0, -hw);
  if (rec.ridgeAxis !== 'd') g.rotateY(Math.PI / 2);  // profile to (z,y), extrusion to x
  return g;
}

function roofGeometry(rec) {
  if (rec.mono) {
    const W = rec.w, D = rec.d, e = rec.eave, r = rec.ridge;
    const verts = new Float32Array([
      -W / 2, r, -D / 2,   W / 2, e, -D / 2,   W / 2, e, D / 2,
      -W / 2, r, -D / 2,   W / 2, e, D / 2,   -W / 2, r, D / 2,
    ]);
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(verts, 3));
    g.computeVertexNormals();
    return g;
  }
  const [W, D] = rec.ridgeAxis === 'd' ? [rec.d, rec.w] : [rec.w, rec.d];
  const e = rec.eave, r = rec.ridge;
  const e2 = rec.eave2 ?? e;
  const off = THREE.MathUtils.clamp(rec.ridgeOff ?? 0, -D / 2 + 0.1, D / 2 - 0.1);
  const verts = new Float32Array([
    // plane on the + side (eave)
    -W / 2, e, D / 2,   W / 2, e, D / 2,   W / 2, r, off,
    -W / 2, e, D / 2,   W / 2, r, off,    -W / 2, r, off,
    // plane on the - side (eave2)
    -W / 2, r, off,     W / 2, r, off,     W / 2, e2, -D / 2,
    -W / 2, r, off,     W / 2, e2, -D / 2, -W / 2, e2, -D / 2,
  ]);
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(verts, 3));
  g.computeVertexNormals();
  if (rec.ridgeAxis === 'd') g.rotateY(Math.PI / 2);
  return g;
}

function rebuildBuilding(group) {
  const rec = group.userData.rec;
  for (const child of [...group.children]) {
    if (!child.userData.part) continue;
    group.remove(child);
    child.geometry?.dispose();
    child.material?.dispose();
  }
  const color = wallColor(rec);
  const emissive = group.userData.selected ? 0x2a4d10 : 0x000000;

  if (rec.type === 'pad') {
    // terraform pad: translucent marker; its base elevation terraforms
    // the ground (cut AND fill) in applyExcavation
    const h = Math.max(rec.ridge, 0.05);
    const g = new THREE.BoxGeometry(rec.w, h, rec.d);
    g.translate(0, h / 2, 0);
    const mesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({
      color: 0x58c470, roughness: 0.9, transparent: true, opacity: 0.35,
      depthWrite: false, emissive,
    }));
    mesh.userData.part = true;
    group.add(mesh);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(g),
      new THREE.LineBasicMaterial({ color: 0x2e7d44 }));
    edges.userData.part = true;
    group.add(edges);
    return;                              // pads cast no shadows
  }

  if (rec.open && !rec.flat) {
    // outdoor roofed wing: corner posts instead of walls
    const [W, D] = rec.ridgeAxis === 'd' ? [rec.d, rec.w] : [rec.w, rec.d];
    const ov = rec.overhang;
    const hw = Math.max(W / 2 - ov, 0.2);
    const hd = Math.max(D / 2 - ov, 0.2);
    const slope = (rec.ridge - rec.eave) / (D / 2);
    const wallTop = Math.max(rec.eave + slope * ov, 0.3);
    const postMat = new THREE.MeshStandardMaterial({
      color, roughness: 0.85, metalness: 0.0, emissive,
    });
    for (const [px, pz] of [[-hw, -hd], [hw, -hd], [hw, hd], [-hw, hd]]) {
      const post = new THREE.Mesh(new THREE.BoxGeometry(0.15, wallTop, 0.15), postMat);
      const x = rec.ridgeAxis === 'd' ? pz : px;
      const z = rec.ridgeAxis === 'd' ? -px : pz;
      post.position.set(x, wallTop / 2, z);
      post.userData.part = true;
      group.add(post);
    }
    if (rec.backWall === 'ridge-' || rec.backWall === 'ridge+') {
      // gable-end wall (full pentagon profile, thin slab)
      const shape = new THREE.Shape([
        new THREE.Vector2(-hd, 0),
        new THREE.Vector2(hd, 0),
        new THREE.Vector2(hd, wallTop),
        new THREE.Vector2(0, Math.max(rec.ridge - 0.02, wallTop)),
        new THREE.Vector2(-hd, wallTop),
      ]);
      const g = new THREE.ExtrudeGeometry(shape, { depth: 0.15, bevelEnabled: false });
      if (rec.ridgeAxis !== 'd') g.rotateY(Math.PI / 2);   // slab thickness along the ridge axis
      const off = rec.backWall === 'ridge-' ? -hw : hw - 0.15;
      if (rec.ridgeAxis !== 'd') g.translate(off, 0, 0);
      else g.translate(0, 0, off);
      const wall = new THREE.Mesh(g, postMat.clone());
      wall.userData.part = true;
      group.add(wall);
      const we = new THREE.LineSegments(
        new THREE.EdgesGeometry(g), new THREE.LineBasicMaterial({ color: 0x1c2733 }));
      we.userData.part = true;
      group.add(we);
    }
  } else {
    const walls = new THREE.Mesh(wallsGeometry(rec), new THREE.MeshStandardMaterial({
      color, roughness: 0.85, metalness: 0.0, emissive,
    }));
    walls.userData.part = true;
    group.add(walls);
    const wallEdges = new THREE.LineSegments(
      new THREE.EdgesGeometry(walls.geometry),
      new THREE.LineBasicMaterial({ color: 0x1c2733 }));
    wallEdges.userData.part = true;
    group.add(wallEdges);
  }

  if (!rec.flat) {
    const roofColor = new THREE.Color(color).multiplyScalar(0.72);
    const roof = new THREE.Mesh(roofGeometry(rec), new THREE.MeshStandardMaterial({
      color: roofColor, roughness: 0.9, metalness: 0.0, side: THREE.DoubleSide, emissive,
    }));
    roof.userData.part = true;
    group.add(roof);
    const roofEdges = new THREE.LineSegments(
      new THREE.EdgesGeometry(roof.geometry, 10),
      new THREE.LineBasicMaterial({ color: 0x1c2733 }));
    roofEdges.userData.part = true;
    group.add(roofEdges);
  }
  for (const child of group.children) {
    if (child.isMesh && child.userData.part) {
      child.castShadow = true;
      child.receiveShadow = true;
    }
  }
}

function makeBuildingGroup(rec) {
  const m = terrainMeta;
  const group = new THREE.Group();
  group.userData = { rec, isBuilding: true, label: null, selected: false };
  group.position.set(rec.cE - m.originE, rec.base, m.originN - rec.cN);
  group.rotation.y = THREE.MathUtils.degToRad(rec.angleDeg);
  rebuildBuilding(group);
  buildingsGroup.add(group);
  return group;
}

async function addBuildings() {
  let list = null;
  const edited = await fetch('web/buildings_edited.json');
  if (edited.ok) {
    list = await edited.json();
    buildingsSource = 'edited';
  } else {
    list = await (await fetch('web/buildings.json')).json();
  }
  try {
    // new-build concept records; skip ids already present (saved edits)
    const have = new Set(list.map(b => String(b.id)));
    const nb = await fetch('web/newbuild.json');
    if (nb.ok) for (const b of await nb.json()) {
      if (b.variant && !variantList.some(v => v.key === b.variant)) {
        variantList.push({ key: b.variant, label: b.variantLabel ?? b.variant });
      }
      if (!have.has(String(b.id))) list.push(b);
    }
  } catch { /* optional */ }
  if (!variantList.some(v => v.key === newVariant)) newVariant = variantList[0]?.key ?? null;
  const sel = document.getElementById('nbsel');
  sel.innerHTML = '';
  for (const v of variantList) {
    const o = document.createElement('option');
    o.value = v.key;
    o.textContent = v.label;
    sel.appendChild(o);
  }
  if (newVariant) sel.value = newVariant;
  for (const b of list) makeBuildingGroup(normalizeRec(b));
  applyNewBuild();
  return list.length;
}

// swap the existing cabin + deck for the selected new-build design (and back)
function applyNewBuild() {
  const showNew = newBuildOn && newVariant !== null;
  for (const group of buildingsGroup.children) {
    const rec = group.userData.rec;
    const id = String(rec.id);
    if (OLD_CABIN_IDS.has(id)) group.visible = !showNew;
    else if (id.startsWith('newbuild:')) {
      group.visible = showNew && (rec.variant == null || rec.variant === newVariant);
    }
  }
  if (selected && !selected.visible) select(null);
  document.getElementById('newb').textContent = `new build: ${showNew ? 'on' : 'off'}`;
}

// -------------------------------------------------- terrain excavation

// Carve the terrain down to each building's base inside its wall footprint,
// with a smoothstep-graded falloff outward so the cut blends into the
// slope instead of a vertical cliff. Carved vertices get a grey-brown
// tint so the excavation extent is visible on the ortho.
const EXC_FALLOFF = 1.5;    // m, graded transition beyond building cuts
const SLAB_FALLOFF = 0.6;   // m, concrete slabs/rooms cut nearly vertical
const PAD_FALLOFF = 6.0;    // m, wide smooth auto-leveling around terraform pads
// existing buildings that sit on natural ground - never carve under them
const NO_CUT_IDS = new Set(['936839961', '936840733']);   // boathouse, annex
function applyExcavation() {
  if (!terrainGeo) return;
  const m = terrainMeta;
  const pos = terrainGeo.attributes.position;
  const arr = pos.array;
  const col = terrainGeo.attributes.color.array;
  for (let k = 0; k < originalHeights.length; k++) {
    arr[k * 3 + 1] = originalHeights[k];
    col[k * 3] = col[k * 3 + 1] = col[k * 3 + 2] = 1;
  }
  if (excavateOn) {
    const x0 = m.e0 - m.originE;
    const z0 = m.originN - m.n0;
    // terraform pads first (they raise AND lower), buildings cut afterwards
    const ordered = [...buildingsGroup.children].sort((a, b) =>
      (a.userData.rec.type === 'pad' ? 0 : 1) - (b.userData.rec.type === 'pad' ? 0 : 1));
    for (const group of ordered) {
      const rec = group.userData.rec;
      const isPad = rec.type === 'pad';
      const R = isPad ? PAD_FALLOFF : (rec.type === 'slab' ? SLAB_FALLOFF : EXC_FALLOFF);
      if (!group.visible) continue;     // hidden variant (old/new build toggle)
      if (rec.open) continue;           // outdoor roofs keep the natural ground
      if (rec.noCut) continue;          // e.g. stepped cabins: their slabs cut
      if (NO_CUT_IDS.has(String(rec.id))) continue;   // sits on natural ground
      const ov = rec.flat ? 0 : rec.overhang;
      const hw = Math.max((rec.w * group.scale.x) / 2 - ov, 0.2) + m.res / 2;
      const hd = Math.max((rec.d * group.scale.z) / 2 - ov, 0.2) + m.res / 2;
      const base = group.position.y;
      const cos = Math.cos(group.rotation.y), sin = Math.sin(group.rotation.y);
      const cx = group.position.x, cz = group.position.z;
      const ce = rec.cutExt;            // extra cut extent per local side [w+, w-, d+, d-]
      const me = Math.max(0, ...ce);
      const r = Math.hypot(hw + me + R, hd + me + R);
      const jmin = Math.max(0, Math.floor((cx - r - x0) / m.res));
      const jmax = Math.min(m.cols - 1, Math.ceil((cx + r - x0) / m.res));
      const imin = Math.max(0, Math.floor((cz - r - z0) / m.res));
      const imax = Math.min(m.rows - 1, Math.ceil((cz + r - z0) / m.res));
      for (let i = imin; i <= imax; i++) {
        const dz = z0 + i * m.res - cz;
        for (let j = jmin; j <= jmax; j++) {
          const dx = x0 + j * m.res - cx;
          const u = dx * cos - dz * sin;
          const v = dx * sin + dz * cos;
          const up = Math.max(hw + ce[0], 0.1), um = Math.max(hw + ce[1], 0.1);
          const vp = Math.max(hd + ce[2], 0.1), vm = Math.max(hd + ce[3], 0.1);
          const du = Math.max(u - up, -um - u, 0);
          const dv = Math.max(v - vp, -vm - v, 0);
          const dist = Math.hypot(du, dv);
          if (dist > R) continue;
          const kk = i * m.cols + j;
          const t = dist / R;
          const s = t * t * (3 - 2 * t);                 // smoothstep
          const target = base + (originalHeights[kk] - base) * s;
          if (isPad) arr[kk * 3 + 1] = target;           // cut and fill
          else if (arr[kk * 3 + 1] > target) arr[kk * 3 + 1] = target;
        }
      }
    }
    for (let k = 0; k < originalHeights.length; k++) {
      const cut = originalHeights[k] - arr[k * 3 + 1];
      if (cut > 0.03) {
        const f = Math.min(cut / 1.5, 1) * 0.35;         // deeper cut = stronger tint
        col[k * 3] = 1 - 0.6 * f;
        col[k * 3 + 1] = 1 - 0.7 * f;
        col[k * 3 + 2] = 1 - 0.8 * f;
      } else if (cut < -0.03) {                          // fill: warm earthy tint
        const f = Math.min(-cut / 1.5, 1) * 0.3;
        col[k * 3] = 1 - 0.15 * f;
        col[k * 3 + 1] = 1 - 0.25 * f;
        col[k * 3 + 2] = 1 - 0.5 * f;
      }
    }
  }
  pos.needsUpdate = true;
  terrainGeo.attributes.color.needsUpdate = true;
  terrainGeo.computeVertexNormals();
}

// -------------------------------------------------- dimension labels

const labelGroup = new THREE.Group();
scene.add(labelGroup);

function labelText(group) {
  const rec = group.userData.rec;
  const w = rec.w * group.scale.x;
  const d = rec.d * group.scale.z;
  if (rec.flat) return `${w.toFixed(1)} × ${d.toFixed(1)} m · h ${(rec.ridge * group.scale.y).toFixed(1)}`;
  const pitch = pitchDeg(rec, group.scale.y, group.scale.x, group.scale.z);
  return `${w.toFixed(1)} × ${d.toFixed(1)} m · ridge ${(rec.ridge * group.scale.y).toFixed(1)}` +
         ` · eave ${(rec.eave * group.scale.y).toFixed(1)} · ${pitch.toFixed(0)}°`;
}

function positionLabel(group) {
  const s = group.userData.label;
  if (s) {
    s.position.set(group.position.x,
      group.position.y + group.userData.rec.ridge * group.scale.y + 1.2,
      group.position.z);
  }
}

function refreshLabel(group) {
  const old = group.userData.label;
  if (old) {
    labelGroup.remove(old);
    old.material.map.dispose();
    old.material.dispose();
    group.userData.label = null;
  }
  if (!labelsOn || !group.userData.rec.onParcel || !group.visible) return;
  const text = labelText(group);
  const c = document.createElement('canvas');
  let ctx = c.getContext('2d');
  ctx.font = '600 30px system-ui, sans-serif';
  c.width = Math.ceil(ctx.measureText(text).width) + 28;
  c.height = 48;
  ctx = c.getContext('2d');
  ctx.font = '600 30px system-ui, sans-serif';
  ctx.fillStyle = 'rgba(8, 18, 30, 0.78)';
  ctx.beginPath();
  ctx.roundRect(0, 0, c.width, c.height, 10);
  ctx.fill();
  ctx.fillStyle = '#ffe95c';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, 14, c.height / 2 + 1);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: tex, depthTest: false, transparent: true,
  }));
  sprite.renderOrder = 10;
  const h = 1.3;
  sprite.scale.set(h * c.width / c.height, h, 1);
  group.userData.label = sprite;
  labelGroup.add(sprite);
  positionLabel(group);
}

function refreshAllLabels() {
  for (const g of buildingsGroup.children) refreshLabel(g);
}

// ------------------------------------------------------- selection / editing

const tc = new TransformControls(camera, renderer.domElement);
tc.setSize(0.8);
tc.setSpace('local');     // gizmo axes follow the building's rotation
scene.add(tc);

// ridge handle: the roof-angle gizmo — drag vertically to change the pitch
const ridgeHandle = new THREE.Mesh(
  new THREE.SphereGeometry(0.35, 20, 14),
  new THREE.MeshBasicMaterial({ color: 0xffe95c, depthTest: false, transparent: true, opacity: 0.95 }));
ridgeHandle.renderOrder = 11;
ridgeHandle.userData.isHandle = true;
const tcRoof = new TransformControls(camera, renderer.domElement);
tcRoof.setSize(0.55);
tcRoof.showX = false;
tcRoof.showZ = false;
scene.add(tcRoof);

let selected = null;
const raycaster = new THREE.Raycaster();
const downPos = new THREE.Vector2();

function setEmissive(group, on) {
  group.userData.selected = on;
  for (const child of group.children) {
    if (child.isMesh && child.userData.part) child.material.emissive.setHex(on ? 0x2a4d10 : 0x000000);
  }
}

function attachRoofGizmo(group) {
  const rec = group.userData.rec;
  if (rec.flat) {
    tcRoof.detach();
    ridgeHandle.removeFromParent();
    return;
  }
  ridgeHandle.position.set(rec.mono ? -(rec.w / 2 - rec.overhang) : 0, rec.ridge, 0);
  group.add(ridgeHandle);
  tcRoof.attach(ridgeHandle);
}

function select(group) {
  if (selected) setEmissive(selected, false);
  selected = group;
  if (group) {
    setEmissive(group, true);
    tc.attach(group);
    attachRoofGizmo(group);
  } else {
    tc.detach();
    tcRoof.detach();
    ridgeHandle.removeFromParent();
  }
  updateSelInfo();
}

function updateSelInfo() {
  document.getElementById('editrow').style.display = selected ? '' : 'none';
  if (!selected) {
    selInfo.textContent = 'click a building to select · t/r/s: mode · g: gable · e/E: eave · o/O: overhang · d: duplicate · del: remove';
    return;
  }
  const r = selected.userData.rec;
  document.getElementById('in_w').value = (r.w * selected.scale.x).toFixed(2);
  document.getElementById('in_d').value = (r.d * selected.scale.z).toFixed(2);
  document.getElementById('in_eave').value = (r.eave * selected.scale.y).toFixed(2);
  document.getElementById('in_ridge').value = (r.ridge * selected.scale.y).toFixed(2);
  document.getElementById('in_ang').value = THREE.MathUtils.radToDeg(selected.rotation.y).toFixed(1);
  for (let i = 0; i < 4; i++) {
    document.getElementById(`in_ce${i}`).value = r.cutExt[i].toFixed(1);
  }
  const m = terrainMeta;
  const rec = selected.userData.rec;
  const e = (selected.position.x + m.originE).toFixed(1);
  const n = (m.originN - selected.position.z).toFixed(1);
  const dims = labelText(selected);
  const roof = rec.flat ? '' : ` · overhang ${rec.overhang.toFixed(2)}`;
  selInfo.textContent =
    `#${rec.id} ${rec.type}${rec.onParcel ? ' (on parcel)' : ''} · ${dims}${roof} · ` +
    `E ${e} N ${n} · ${THREE.MathUtils.radToDeg(selected.rotation.y).toFixed(0)}°`;
}

function setMode(mode) {
  tc.setMode(mode);
  const rot = mode === 'rotate';        // buildings only rotate about the vertical axis
  tc.showX = !rot;
  tc.showZ = !rot;
  tc.showY = true;
  for (const [id, m] of [['mode_t', 'translate'], ['mode_r', 'rotate'], ['mode_s', 'scale']]) {
    document.getElementById(id).style.background = m === mode ? '#3c6ea5' : '';
  }
}
setMode('translate');
document.getElementById('mode_t').addEventListener('click', () => setMode('translate'));
document.getElementById('mode_r').addEventListener('click', () => setMode('rotate'));
document.getElementById('mode_s').addEventListener('click', () => setMode('scale'));
document.getElementById('in_ang').addEventListener('change', e => {
  if (!selected) return;
  const v = parseFloat(e.target.value);
  if (!Number.isFinite(v)) { updateSelInfo(); return; }
  selected.rotation.y = THREE.MathUtils.degToRad(v);
  applyExcavation();
  refreshLabel(selected);
  updateSelInfo();
  markDirty();
});

tc.addEventListener('dragging-changed', e => {
  controls.enabled = !e.value;
  if (!e.value) {                       // drag finished
    if (tc.mode === 'scale' && selected) {   // bake scale into the parameters
      const rec = selected.userData.rec;
      rec.w = Math.max(rec.w * selected.scale.x, 0.5);
      rec.d = Math.max(rec.d * selected.scale.z, 0.5);
      rec.eave = Math.max(rec.eave * selected.scale.y, 0.3);
      rec.ridge = Math.max(rec.ridge * selected.scale.y, rec.eave + (rec.flat ? 0 : 0.1));
      selected.scale.set(1, 1, 1);
      rebuildBuilding(selected);
      attachRoofGizmo(selected);
    }
    applyExcavation();
    if (selected) refreshLabel(selected);
  }
});
tc.addEventListener('objectChange', () => {
  markDirty();
  updateSelInfo();
  if (selected) {
    refreshLabel(selected);             // live measurements while adjusting
  }
});

tcRoof.addEventListener('dragging-changed', e => { controls.enabled = !e.value; });
tcRoof.addEventListener('objectChange', () => {
  if (!selected) return;
  const rec = selected.userData.rec;
  const span = rec.mono ? rec.w : (rec.ridgeAxis === 'd' ? rec.w : rec.d) / 2;
  rec.ridge = THREE.MathUtils.clamp(ridgeHandle.position.y, rec.eave + 0.1, rec.eave + span * 1.8);
  ridgeHandle.position.set(rec.mono ? -(rec.w / 2 - rec.overhang) : 0, rec.ridge, 0);
  rebuildBuilding(selected);
  refreshLabel(selected);
  updateSelInfo();
  markDirty();
});

renderer.domElement.addEventListener('pointerdown', e => downPos.set(e.clientX, e.clientY));
renderer.domElement.addEventListener('pointerup', e => {
  if (walker.on) return;                                                  // walking
  if (tc.dragging || tc.axis || tcRoof.dragging || tcRoof.axis) return;   // gizmo interaction
  if (downPos.distanceTo(new THREE.Vector2(e.clientX, e.clientY)) > 5) return; // orbit drag
  const ndc = new THREE.Vector2(
    (e.clientX / window.innerWidth) * 2 - 1,
    -(e.clientY / window.innerHeight) * 2 + 1,
  );
  raycaster.setFromCamera(ndc, camera);
  const hits = raycaster.intersectObjects(buildingsGroup.children, true);
  let group = null;
  for (const h of hits) {
    if (h.object.userData.isHandle) return;   // clicked the roof gizmo
    let o = h.object;
    while (o && !o.userData.isBuilding) o = o.parent;
    if (o && o.visible) { group = o; break; }
  }
  select(group);
});

// double-click terrain or a building to move the orbit point there
renderer.domElement.addEventListener('dblclick', e => {
  if (walker.on) return;
  const ndc = new THREE.Vector2(
    (e.clientX / window.innerWidth) * 2 - 1,
    -(e.clientY / window.innerHeight) * 2 + 1,
  );
  raycaster.setFromCamera(ndc, camera);
  const targets = terrainMesh ? [terrainMesh, ...buildingsGroup.children] : buildingsGroup.children;
  for (const h of raycaster.intersectObjects(targets, true)) {
    if (h.object.userData.isHandle) continue;
    let o = h.object;
    while (o && !o.userData.isBuilding) o = o.parent;
    if (o && !o.visible) continue;              // hidden old/new-build variant
    controls.target.copy(h.point);
    break;
  }
});

// ------------------------------------------------------------- walk mode
// first-person view 1.7 m above the feet of a 1.8 m character; the figure
// stays behind as a scale reference when leaving walk mode
const walker = {
  on: false, yaw: 0, pitch: 0, foot: 0,
  pos: new THREE.Vector3(), keys: new Set(),
  movePtr: null, moveStart: null, moveVec: { x: 0, y: 0 },
  lookPtr: null, lastLook: null,
};
const person = new THREE.Group();
{
  const pmat = new THREE.MeshStandardMaterial({ color: 0xd9534f, roughness: 0.7 });
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.26, 1.4, 12), pmat);
  body.position.y = 0.75;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.16, 12, 10), pmat);
  head.position.y = 1.63;
  person.add(body, head);
  person.visible = false;
  person.traverse(o => { if (o.isMesh) o.castShadow = true; });
  scene.add(person);
}

function terrainYAt(x, z) {
  const m = terrainMeta;
  if (!m) return 0;
  const arr = terrainGeo.attributes.position.array;
  const e = x + m.originE, n = m.originN - z;
  const fx = Math.min(Math.max((e - m.e0) / m.res, 0), m.cols - 1.001);
  const fz = Math.min(Math.max((m.n0 - n) / m.res, 0), m.rows - 1.001);
  const j = Math.floor(fx), i = Math.floor(fz);
  const dx = fx - j, dz = fz - i;
  const h = (a, b) => arr[(a * m.cols + b) * 3 + 1];
  return (h(i, j) * (1 - dx) + h(i, j + 1) * dx) * (1 - dz)
       + (h(i + 1, j) * (1 - dx) + h(i + 1, j + 1) * dx) * dz;
}

// walkable floor: terrain, plus tops of flat boxes (decks, slabs) that are
// within stepping height of the current feet
function floorAt(x, z, prevFoot) {
  let f = terrainYAt(x, z);
  for (const g of buildingsGroup.children) {
    const rec = g.userData.rec;
    if (!g.visible || !rec.flat) continue;
    const cos = Math.cos(g.rotation.y), sin = Math.sin(g.rotation.y);
    const dx = x - g.position.x, dz = z - g.position.z;
    const u = dx * cos - dz * sin, v = dx * sin + dz * cos;
    if (Math.abs(u) <= (rec.w * g.scale.x) / 2 && Math.abs(v) <= (rec.d * g.scale.z) / 2) {
      const top = g.position.y + rec.ridge * g.scale.y;
      if (top <= prevFoot + 0.55 && top > f) f = top;
    }
  }
  return f;
}

function setWalk(on) {
  walker.on = on;
  document.getElementById('walk').textContent = `walk: ${on ? 'on' : 'off'}`;
  controls.enabled = !on;
  if (on) {
    select(null);
    walker.pos.set(controls.target.x, 0, controls.target.z);
    walker.foot = floorAt(walker.pos.x, walker.pos.z, Infinity);
    const d = new THREE.Vector3();
    camera.getWorldDirection(d);
    walker.yaw = Math.atan2(-d.x, -d.z);
    walker.pitch = 0;
    person.visible = false;
  } else {
    walker.keys.clear();
    walker.moveVec.x = walker.moveVec.y = 0;
    person.position.set(walker.pos.x, walker.foot, walker.pos.z);
    person.visible = true;
    controls.target.set(walker.pos.x, walker.foot + 1.2, walker.pos.z);
    camera.position.set(walker.pos.x + 9, walker.foot + 7, walker.pos.z + 9);
    camera.rotation.set(0, 0, 0);
  }
}

renderer.domElement.addEventListener('pointerdown', e => {
  if (!walker.on) return;
  if (e.pointerType === 'touch' && e.clientX < window.innerWidth * 0.35 && walker.movePtr === null) {
    walker.movePtr = e.pointerId;                 // virtual joystick (left)
    walker.moveStart = { x: e.clientX, y: e.clientY };
  } else if (walker.lookPtr === null) {
    walker.lookPtr = e.pointerId;
    walker.lastLook = { x: e.clientX, y: e.clientY };
  }
});
window.addEventListener('pointermove', e => {
  if (!walker.on) return;
  if (e.pointerId === walker.movePtr) {
    walker.moveVec.x = THREE.MathUtils.clamp((e.clientX - walker.moveStart.x) / 60, -1, 1);
    walker.moveVec.y = THREE.MathUtils.clamp((e.clientY - walker.moveStart.y) / 60, -1, 1);
  } else if (e.pointerId === walker.lookPtr) {
    walker.yaw -= (e.clientX - walker.lastLook.x) * 0.005;
    walker.pitch = THREE.MathUtils.clamp(
      walker.pitch - (e.clientY - walker.lastLook.y) * 0.005, -1.35, 1.35);
    walker.lastLook = { x: e.clientX, y: e.clientY };
  }
});
window.addEventListener('pointerup', e => {
  if (e.pointerId === walker.movePtr) {
    walker.movePtr = null;
    walker.moveVec.x = walker.moveVec.y = 0;
  }
  if (e.pointerId === walker.lookPtr) walker.lookPtr = null;
});
window.addEventListener('keyup', e => walker.keys.delete(e.code));

let customCount = 0;
let dirty = false;

function markDirty() {
  dirty = true;
  document.getElementById('save').textContent = 'save*';
}

function serialize() {
  const m = terrainMeta;
  return buildingsGroup.children.map(group => {
    const rec = group.userData.rec;
    return {
      id: rec.id,
      type: rec.type,
      onParcel: rec.onParcel,
      cE: +(group.position.x + m.originE).toFixed(2),
      cN: +(m.originN - group.position.z).toFixed(2),
      w: +rec.w.toFixed(2),
      d: +rec.d.toFixed(2),
      angleDeg: +THREE.MathUtils.radToDeg(group.rotation.y).toFixed(1),
      base: +group.position.y.toFixed(2),
      height: +rec.ridge.toFixed(2),
      flat: rec.flat,
      eave: +rec.eave.toFixed(2),
      ridge: +rec.ridge.toFixed(2),
      ridgeAxis: rec.ridgeAxis,
      pitchDeg: +pitchDeg(rec).toFixed(1),
      overhang: +rec.overhang.toFixed(2),
      open: rec.open,
      backWall: rec.backWall,
      mono: rec.mono,
      eave2: rec.eave2 ?? null,
      ridgeOff: rec.ridgeOff ?? 0,
      noCut: rec.noCut,
      variant: rec.variant ?? null,
      variantLabel: rec.variantLabel ?? null,
      cutExt: rec.cutExt,
      footprint: rec.footprint,
    };
  });
}

async function save() {
  const btn = document.getElementById('save');
  try {
    const res = await fetch('api/save', { method: 'POST', body: JSON.stringify(serialize()) });
    if (!res.ok) throw new Error((await res.json()).error ?? res.status);
    dirty = false;
    buildingsSource = 'edited';
    btn.textContent = 'saved ✓';
    setTimeout(() => { btn.textContent = dirty ? 'save*' : 'save'; }, 1500);
  } catch (err) {
    // no save server (e.g. static hosting) — download the JSON instead
    console.warn('save API unavailable, downloading instead', err);
    const blob = new Blob([JSON.stringify(serialize(), null, 1)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'buildings_edited.json';
    a.click();
    URL.revokeObjectURL(a.href);
    dirty = false;
    btn.textContent = 'downloaded ↓';
    setTimeout(() => { btn.textContent = dirty ? 'save*' : 'save'; }, 2500);
  }
}

function duplicateSelected() {
  if (!selected) return;
  const m = terrainMeta;
  const rec = structuredClone(selected.userData.rec);
  rec.id = `custom:${++customCount}:${rec.id}`;
  rec.footprint = [];
  rec.cE = selected.position.x + m.originE + 3;
  rec.cN = m.originN - selected.position.z - 3;
  rec.base = selected.position.y;
  rec.angleDeg = THREE.MathUtils.radToDeg(selected.rotation.y);
  const group = makeBuildingGroup(rec);
  refreshLabel(group);
  applyExcavation();
  select(group);
  markDirty();
}

function nudgeOverhang(delta) {
  if (!selected || selected.userData.rec.flat) return;
  const rec = selected.userData.rec;
  rec.overhang = THREE.MathUtils.clamp(rec.overhang + delta, 0, 1.5);
  rebuildBuilding(selected);
  applyExcavation();
  refreshLabel(selected);
  updateSelInfo();
  markDirty();
}

function nudgeEave(delta) {
  if (!selected || selected.userData.rec.flat) return;
  const rec = selected.userData.rec;
  rec.eave = THREE.MathUtils.clamp(rec.eave + delta, 0.3, rec.ridge - 0.1);
  rebuildBuilding(selected);
  refreshLabel(selected);
  updateSelInfo();
  markDirty();
}

function toggleGable() {
  if (!selected) return;
  const rec = selected.userData.rec;
  if (rec.type === 'deck' || rec.mono) return;
  if (rec.flat) {
    rec.flat = false;
    rec.ridgeAxis = rec.w >= rec.d ? 'w' : 'd';
    const span = (rec.ridgeAxis === 'd' ? rec.w : rec.d) / 2;
    rec.eave = rec.ridge;                              // old box top becomes the eave
    rec.ridge = rec.eave + span * Math.tan(THREE.MathUtils.degToRad(25));
    if (!rec.overhang) rec.overhang = 0.4;
  } else {
    rec.flat = true;
    rec.eave = rec.ridge;
  }
  rebuildBuilding(selected);
  attachRoofGizmo(selected);
  applyExcavation();
  refreshLabel(selected);
  updateSelInfo();
  markDirty();
}

// numeric editing of the selected building's dimensions
function bindDim(id, apply) {
  document.getElementById(id).addEventListener('change', e => {
    if (!selected) return;
    const v = parseFloat(e.target.value);
    if (!Number.isFinite(v)) { updateSelInfo(); return; }
    selected.scale.set(1, 1, 1);          // typed values are absolute
    apply(selected.userData.rec, v);
    rebuildBuilding(selected);
    attachRoofGizmo(selected);
    applyExcavation();
    refreshLabel(selected);
    updateSelInfo();
    markDirty();
  });
}
bindDim('in_w', (r, v) => { r.w = Math.max(v, 0.5); });
bindDim('in_d', (r, v) => { r.d = Math.max(v, 0.5); });
bindDim('in_eave', (r, v) => {
  if (r.flat) { r.eave = r.ridge = Math.max(v, 0.2); }
  else r.eave = Math.min(Math.max(v, 0.3), r.ridge - 0.1);
});
bindDim('in_ridge', (r, v) => {
  if (r.flat) { r.eave = r.ridge = Math.max(v, 0.2); }
  else r.ridge = Math.max(v, r.eave + 0.1);
});
for (let i = 0; i < 4; i++) {
  bindDim(`in_ce${i}`, (r, v) => { r.cutExt[i] = v; });   // negative shrinks the cut
}

window.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') return;   // typing in a dimension field
  if (walker.on) {
    if (e.key === 'Escape') { setWalk(false); return; }
    walker.keys.add(e.code);
    if (e.code.startsWith('Arrow')) e.preventDefault();
    return;
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); save(); return; }
  if (e.key === 't') setMode('translate');
  if (e.key === 'r') setMode('rotate');
  if (e.key === 's') setMode('scale');
  if (e.key === 'd') duplicateSelected();
  if (e.key === 'g') toggleGable();
  if (e.key === 'o') nudgeOverhang(-0.05);
  if (e.key === 'O') nudgeOverhang(0.05);
  if (e.key === 'e') nudgeEave(-0.1);
  if (e.key === 'E') nudgeEave(0.1);
  if (e.key === 'Escape') select(null);
  if ((e.key === 'Delete' || e.key === 'Backspace') && selected) {
    const dead = selected;
    select(null);
    dead.userData.rec.onParcel = false;   // drop its label
    refreshLabel(dead);
    buildingsGroup.remove(dead);
    applyExcavation();
    markDirty();
  }
});

document.getElementById('save').addEventListener('click', save);
document.getElementById('walk').addEventListener('click', () => setWalk(!walker.on));

// terraform pad: level the ground to the pad's base elevation (cut + fill)
document.getElementById('addpad').addEventListener('click', () => {
  const m = terrainMeta;
  if (!m) return;
  let n = 1;
  const ids = new Set(buildingsGroup.children.map(g => String(g.userData.rec.id)));
  while (ids.has(`custom:pad:${n}`)) n++;
  const x = controls.target.x, z = controls.target.z;
  const rec = normalizeRec({
    id: `custom:pad:${n}`, type: 'pad', onParcel: false,
    cE: +(x + m.originE).toFixed(2), cN: +(m.originN - z).toFixed(2),
    w: 6, d: 6, angleDeg: 0, base: +terrainYAt(x, z).toFixed(2),
    height: 0.05, flat: true, eave: 0.05, ridge: 0.05, ridgeAxis: 'w',
    pitchDeg: 0, overhang: 0,
  });
  const group = makeBuildingGroup(rec);
  applyExcavation();
  select(group);
  setMode('translate');
  markDirty();
});

document.getElementById('reset').addEventListener('click', async () => {
  if (!confirm('Discard all edits and reload the generated buildings?')) return;
  try { await fetch('api/save', { method: 'DELETE' }); } catch { /* static hosting */ }
  location.reload();
});

document.getElementById('excav').addEventListener('click', e => {
  excavateOn = !excavateOn;
  e.target.textContent = `terrain cut: ${excavateOn ? 'on' : 'off'}`;
  applyExcavation();
});

document.getElementById('sun').addEventListener('click', e => {
  sunSimOn = !sunSimOn;
  e.target.textContent = `sun: ${sunSimOn ? 'on' : 'off'}`;
  document.getElementById('sunctl').style.display = sunSimOn ? '' : 'none';
  updateSun();
});
document.getElementById('sunmonth').addEventListener('input', e => {
  sunMonth = +e.target.value;
  updateSun();
});
document.getElementById('sunhour').addEventListener('input', e => {
  sunHour = +e.target.value;
  updateSun();
});

document.getElementById('newb').addEventListener('click', () => {
  newBuildOn = !newBuildOn;
  applyNewBuild();
  applyExcavation();
  refreshAllLabels();
});
document.getElementById('nbsel').addEventListener('change', e => {
  newVariant = e.target.value;
  newBuildOn = true;
  applyNewBuild();
  applyExcavation();
  refreshAllLabels();
});

document.getElementById('labels').addEventListener('click', e => {
  labelsOn = !labelsOn;
  e.target.textContent = `labels: ${labelsOn ? 'on' : 'off'}`;
  refreshAllLabels();
});

window.addEventListener('beforeunload', e => {
  if (dirty) e.preventDefault();
});

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

const clock = new THREE.Clock();
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.1);
  if (walker.on && terrainMeta) {
    let f = 0, s = 0;
    const k = walker.keys;
    if (k.has('KeyW') || k.has('ArrowUp')) f += 1;
    if (k.has('KeyS') || k.has('ArrowDown')) f -= 1;
    if (k.has('KeyA') || k.has('ArrowLeft')) s -= 1;
    if (k.has('KeyD') || k.has('ArrowRight')) s += 1;
    f += -walker.moveVec.y;
    s += walker.moveVec.x;
    if (f || s) {
      const sp = 3.0 * dt / Math.max(1, Math.hypot(f, s));
      const sy = Math.sin(walker.yaw), cy = Math.cos(walker.yaw);
      walker.pos.x += (-sy * f + cy * s) * sp;
      walker.pos.z += (-cy * f - sy * s) * sp;
    }
    const fl = floorAt(walker.pos.x, walker.pos.z, walker.foot);
    walker.foot += (fl - walker.foot) * Math.min(1, dt * 10);
    camera.position.set(walker.pos.x, walker.foot + 1.7, walker.pos.z);
    camera.rotation.set(walker.pitch, walker.yaw, 0, 'YXZ');
  } else {
    controls.update();
  }
  renderer.render(scene, camera);
});

try {
  await buildTerrain();
  addWater();
  await addParcel();
  const nb = await addBuildings();
  applyExcavation();
  refreshAllLabels();
  updateSelInfo();
  status.textContent =
    `terrain ${terrainMeta.cols}×${terrainMeta.rows} @ ${terrainMeta.res} m · ` +
    `${nb} buildings (${buildingsSource}, orange = on parcel)`;
  if (q.get('walk') === '1') setWalk(true);
} catch (err) {
  const desc = err?.message ?? `${err?.type ?? 'unknown'} on ${err?.target?.src ?? err?.target?.tagName ?? '?'}`;
  status.textContent = `error: ${desc}`;
  console.error('load failed:', desc, err);
  throw err;
}
