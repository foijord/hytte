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
// new-build variant cycling: null = existing buildings, else 'A'..'E'
let newVariant = 'A';
let variantList = [];        // [{key, label}] discovered from newbuild.json
// records replaced by the new-build concept (web/newbuild.json):
// main cabin, outdoor wing, the small attached storage (:3) and the deck
const OLD_CABIN_IDS = new Set(['936839960:1', '936839960:2', '936839960:3', 'deck']);
const qNew = q.get('new');
if (qNew) newVariant = qNew === 'off' ? null : (qNew === '1' ? 'A' : qNew.toUpperCase());
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
  const mat = new THREE.MeshStandardMaterial({ roughness: 1.0, metalness: 0.0 });
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
  const rec = { overhang: 0, open: false, backWall: null, variant: null, ...b };
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
  const span = (rec.ridgeAxis === 'd' ? rec.w * sx : rec.d * sz) / 2;
  return THREE.MathUtils.radToDeg(Math.atan((rec.ridge - rec.eave) * sy / span));
}

function wallsGeometry(rec) {
  if (rec.flat) {
    const g = new THREE.BoxGeometry(rec.w, rec.ridge, rec.d);
    g.translate(0, rec.ridge / 2, 0);
    return g;
  }
  // build with ridge along local x; W = extent along ridge, D across
  const [W, D] = rec.ridgeAxis === 'd' ? [rec.d, rec.w] : [rec.w, rec.d];
  const ov = rec.overhang;
  const hw = Math.max(W / 2 - ov, 0.2);
  const hd = Math.max(D / 2 - ov, 0.2);
  const slope = (rec.ridge - rec.eave) / (D / 2);
  const wallTop = Math.max(rec.eave + slope * ov, 0.3);
  const shape = new THREE.Shape([
    new THREE.Vector2(-hd, 0),
    new THREE.Vector2(hd, 0),
    new THREE.Vector2(hd, wallTop),
    new THREE.Vector2(0, Math.max(rec.ridge - 0.02, wallTop)),
    new THREE.Vector2(-hd, wallTop),
  ]);
  const g = new THREE.ExtrudeGeometry(shape, { depth: 2 * hw, bevelEnabled: false });
  g.translate(0, 0, -hw);
  if (rec.ridgeAxis !== 'd') g.rotateY(Math.PI / 2);  // profile to (z,y), extrusion to x
  return g;
}

function roofGeometry(rec) {
  const [W, D] = rec.ridgeAxis === 'd' ? [rec.d, rec.w] : [rec.w, rec.d];
  const e = rec.eave, r = rec.ridge;
  const verts = new Float32Array([
    // south-facing plane
    -W / 2, e, D / 2,   W / 2, e, D / 2,   W / 2, r, 0,
    -W / 2, e, D / 2,   W / 2, r, 0,      -W / 2, r, 0,
    // north-facing plane
    -W / 2, r, 0,       W / 2, r, 0,       W / 2, e, -D / 2,
    -W / 2, r, 0,       W / 2, e, -D / 2, -W / 2, e, -D / 2,
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
  if (newVariant && !variantList.some(v => v.key === newVariant)) newVariant = null;
  for (const b of list) makeBuildingGroup(normalizeRec(b));
  applyNewBuild();
  return list.length;
}

// swap the existing cabin + deck for a new-build variant (and back)
function applyNewBuild() {
  for (const group of buildingsGroup.children) {
    const rec = group.userData.rec;
    const id = String(rec.id);
    if (OLD_CABIN_IDS.has(id)) group.visible = newVariant === null;
    else if (id.startsWith('newbuild:')) {
      group.visible = newVariant !== null && (rec.variant == null || rec.variant === newVariant);
    }
  }
  if (selected && !selected.visible) select(null);
  const label = newVariant === null ? 'off'
    : (variantList.find(v => v.key === newVariant)?.label ?? newVariant);
  document.getElementById('newb').textContent = `new build: ${label}`;
}

// -------------------------------------------------- terrain excavation

// Carve the terrain down to each building's base inside its wall footprint,
// so buildings (and the under-deck storage) read as built into the slope.
function applyExcavation() {
  if (!terrainGeo) return;
  const m = terrainMeta;
  const pos = terrainGeo.attributes.position;
  const arr = pos.array;
  for (let k = 0; k < originalHeights.length; k++) arr[k * 3 + 1] = originalHeights[k];
  if (excavateOn) {
    const x0 = m.e0 - m.originE;
    const z0 = m.originN - m.n0;
    for (const group of buildingsGroup.children) {
      const rec = group.userData.rec;
      if (!group.visible) continue;     // hidden variant (old/new build toggle)
      if (rec.open) continue;           // outdoor roofs keep the natural ground
      const ov = rec.flat ? 0 : rec.overhang;
      const hw = Math.max((rec.w * group.scale.x) / 2 - ov, 0.2) + m.res / 2;
      const hd = Math.max((rec.d * group.scale.z) / 2 - ov, 0.2) + m.res / 2;
      const base = group.position.y;
      const cos = Math.cos(group.rotation.y), sin = Math.sin(group.rotation.y);
      const cx = group.position.x, cz = group.position.z;
      const r = Math.hypot(hw, hd);
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
          if (Math.abs(u) <= hw && Math.abs(v) <= hd) {
            const k = (i * m.cols + j) * 3 + 1;
            if (arr[k] > base) arr[k] = base;
          }
        }
      }
    }
  }
  pos.needsUpdate = true;
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
  ridgeHandle.position.set(0, rec.ridge, 0);
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
  if (!selected) {
    selInfo.textContent = 'click a building to select · t/r/s: mode · g: gable · e/E: eave · o/O: overhang · d: duplicate · del: remove';
    return;
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
}

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
  const span = (rec.ridgeAxis === 'd' ? rec.w : rec.d) / 2;
  rec.ridge = THREE.MathUtils.clamp(ridgeHandle.position.y, rec.eave + 0.1, rec.eave + span * 1.8);
  ridgeHandle.position.set(0, rec.ridge, 0);
  rebuildBuilding(selected);
  refreshLabel(selected);
  updateSelInfo();
  markDirty();
});

renderer.domElement.addEventListener('pointerdown', e => downPos.set(e.clientX, e.clientY));
renderer.domElement.addEventListener('pointerup', e => {
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
      variant: rec.variant ?? null,
      variantLabel: rec.variantLabel ?? null,
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
  if (rec.type === 'deck') return;
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

window.addEventListener('keydown', e => {
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
  const keys = variantList.map(v => v.key);
  const i = newVariant === null ? -1 : keys.indexOf(newVariant);
  newVariant = i + 1 < keys.length ? keys[i + 1] : null;
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

renderer.setAnimationLoop(() => {
  controls.update();
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
} catch (err) {
  const desc = err?.message ?? `${err?.type ?? 'unknown'} on ${err?.target?.src ?? err?.target?.tagName ?? '?'}`;
  status.textContent = `error: ${desc}`;
  console.error('load failed:', desc, err);
  throw err;
}
