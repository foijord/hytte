import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { TransformControls } from 'three/addons/controls/TransformControls.js';

// Scene axes: x = east, y = up (meters, NN2000), z = south.
// Origin = address point (E 71428.47, N 6458099.03), see data/README.md.

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
camera.position.set(65, 45, 95);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(-10, 5, -5);
// optional overrides: ?cam=x,y,z&tgt=x,y,z&labels=off&cut=off
const q = new URLSearchParams(location.search);
if (q.has('cam')) camera.position.fromArray(q.get('cam').split(',').map(Number));
if (q.has('tgt')) controls.target.fromArray(q.get('tgt').split(',').map(Number));
controls.maxPolarAngle = Math.PI / 2 - 0.02;
controls.enableDamping = true;

scene.add(new THREE.HemisphereLight(0xbfd7ff, 0x5c4f3d, 0.9));
const sun = new THREE.DirectionalLight(0xfff1da, 1.8);
sun.position.set(-150, 260, 180);
scene.add(sun);

let terrainMeta = null;
let heightGrid = null;      // original heights, used for draping the parcel line
let terrainGeo = null;
let originalHeights = null;
let excavateOn = true;
let labelsOn = true;
if (q.get('labels') === 'off') {
  labelsOn = false;
  document.getElementById('labels').textContent = 'labels: off';
}
if (q.get('cut') === 'off') {
  excavateOn = false;
  document.getElementById('excav').textContent = 'terrain cut: off';
}

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
    mat.color.setHex(0x76705f);   // ortho unavailable — untextured terrain
    console.warn('orthophoto failed to load, rendering untextured');
  }
  scene.add(new THREE.Mesh(geo, mat));
}

function addWater() {
  const geo = new THREE.PlaneGeometry(3000, 3000);
  geo.rotateX(-Math.PI / 2);
  const mat = new THREE.MeshStandardMaterial({
    color: 0x18456b, roughness: 0.25, metalness: 0.0,
    transparent: true, opacity: 0.62,
  });
  const water = new THREE.Mesh(geo, mat);
  water.position.y = 0.05;
  scene.add(water);
}

async function addParcel() {
  const gj = await (await fetch('data/property_437_109.geojson')).json();
  const m = terrainMeta;
  for (const f of gj.features) {
    for (const ring of f.geometry.coordinates) {
      const pts = ring.map(([e, n]) => new THREE.Vector3(
        e - m.originE, heightAt(e, n) + 0.35, m.originN - n,
      ));
      const geo = new THREE.BufferGeometry().setFromPoints(pts);
      scene.add(new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0xffe95c })));
    }
  }
}

// ---------------------------------------------------------------- buildings

const buildingsGroup = new THREE.Group();
scene.add(buildingsGroup);
const unitBox = new THREE.BoxGeometry(1, 1, 1);
const unitEdges = new THREE.EdgesGeometry(unitBox);

let buildingsSource = 'generated';

async function addBuildings() {
  let list = null;
  const edited = await fetch('web/buildings_edited.json');
  if (edited.ok) {
    list = await edited.json();
    buildingsSource = 'edited';
  } else {
    list = await (await fetch('web/buildings.json')).json();
  }
  const m = terrainMeta;
  for (const b of list) {
    const color = b.type === 'deck' ? 0xb5885e : (b.onParcel ? 0xe8913a : 0x9fb2c4);
    const mat = new THREE.MeshStandardMaterial({
      color, roughness: 0.85, metalness: 0.0, transparent: true, opacity: 0.92,
    });
    const mesh = new THREE.Mesh(unitBox, mat);
    mesh.scale.set(b.w, b.height, b.d);
    mesh.position.set(b.cE - m.originE, b.base + b.height / 2, m.originN - b.cN);
    mesh.rotation.y = THREE.MathUtils.degToRad(b.angleDeg);
    mesh.userData = { id: b.id, type: b.type, onParcel: b.onParcel, footprint: b.footprint ?? [] };
    const edges = new THREE.LineSegments(
      unitEdges, new THREE.LineBasicMaterial({ color: 0x1c2733 }));
    mesh.add(edges);
    buildingsGroup.add(mesh);
  }
  return list.length;
}

// -------------------------------------------------- terrain excavation

// Carve the terrain down to each box's base inside its footprint, so
// buildings (and the under-deck storage) read as built into the slope.
function applyExcavation() {
  if (!terrainGeo) return;
  const m = terrainMeta;
  const pos = terrainGeo.attributes.position;
  const arr = pos.array;
  for (let k = 0; k < originalHeights.length; k++) arr[k * 3 + 1] = originalHeights[k];
  if (excavateOn) {
    const x0 = m.e0 - m.originE;
    const z0 = m.originN - m.n0;
    for (const mesh of buildingsGroup.children) {
      const hw = mesh.scale.x / 2 + m.res / 2;
      const hd = mesh.scale.z / 2 + m.res / 2;
      const base = mesh.position.y - mesh.scale.y / 2;
      const cos = Math.cos(mesh.rotation.y), sin = Math.sin(mesh.rotation.y);
      const cx = mesh.position.x, cz = mesh.position.z;
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

function labelText(mesh) {
  return `${mesh.scale.x.toFixed(1)} × ${mesh.scale.z.toFixed(1)} m · h ${mesh.scale.y.toFixed(1)}`;
}

function positionLabel(mesh) {
  const s = mesh.userData.label;
  if (s) s.position.set(mesh.position.x, mesh.position.y + mesh.scale.y / 2 + 1.1, mesh.position.z);
}

function refreshLabel(mesh) {
  const old = mesh.userData.label;
  if (old) {
    labelGroup.remove(old);
    old.material.map.dispose();
    old.material.dispose();
    mesh.userData.label = null;
  }
  if (!labelsOn || !mesh.userData.onParcel) return;
  const text = labelText(mesh);
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
  mesh.userData.label = sprite;
  labelGroup.add(sprite);
  positionLabel(mesh);
}

function refreshAllLabels() {
  for (const mesh of buildingsGroup.children) refreshLabel(mesh);
}

// ------------------------------------------------------- selection / editing

const tc = new TransformControls(camera, renderer.domElement);
tc.setSize(0.8);
tc.addEventListener('dragging-changed', e => {
  controls.enabled = !e.value;
  if (!e.value) {                       // drag finished
    applyExcavation();
    if (selected) refreshLabel(selected);
  }
});
tc.addEventListener('objectChange', () => {
  updateSelInfo();
  if (selected) positionLabel(selected);
});
scene.add(tc);

function setMode(mode) {
  tc.setMode(mode);
  const rot = mode === 'rotate';        // buildings only rotate about the vertical axis
  tc.showX = !rot;
  tc.showZ = !rot;
  tc.showY = true;
}

let selected = null;
const raycaster = new THREE.Raycaster();
const downPos = new THREE.Vector2();

function select(mesh) {
  if (selected) selected.material.emissive.setHex(0x000000);
  selected = mesh;
  if (mesh) {
    mesh.material.emissive.setHex(0x2a4d10);
    tc.attach(mesh);
  } else {
    tc.detach();
  }
  updateSelInfo();
}

function updateSelInfo() {
  if (!selected) { selInfo.textContent = 'click a box to select · t/r/s: mode · d: duplicate · del: remove · esc: deselect'; return; }
  const m = terrainMeta;
  const u = selected.userData;
  const e = (selected.position.x + m.originE).toFixed(1);
  const n = (m.originN - selected.position.z).toFixed(1);
  selInfo.textContent =
    `#${u.id} ${u.type}${u.onParcel ? ' (on parcel)' : ''} · ` +
    `${selected.scale.x.toFixed(1)}×${selected.scale.z.toFixed(1)}×${selected.scale.y.toFixed(1)} m · ` +
    `E ${e} N ${n} · ${THREE.MathUtils.radToDeg(selected.rotation.y).toFixed(0)}°`;
}

renderer.domElement.addEventListener('pointerdown', e => downPos.set(e.clientX, e.clientY));
renderer.domElement.addEventListener('pointerup', e => {
  if (tc.dragging || tc.axis) return;                       // interacting with gizmo
  if (downPos.distanceTo(new THREE.Vector2(e.clientX, e.clientY)) > 5) return; // orbit drag
  const ndc = new THREE.Vector2(
    (e.clientX / window.innerWidth) * 2 - 1,
    -(e.clientY / window.innerHeight) * 2 + 1,
  );
  raycaster.setFromCamera(ndc, camera);
  const hits = raycaster.intersectObjects(buildingsGroup.children, false);
  select(hits.length ? hits[0].object : null);
});

let customCount = 0;
let dirty = false;

function markDirty() {
  dirty = true;
  document.getElementById('save').textContent = 'save*';
}
tc.addEventListener('objectChange', markDirty);

function serialize() {
  const m = terrainMeta;
  return buildingsGroup.children.map(mesh => ({
    id: mesh.userData.id,
    type: mesh.userData.type,
    onParcel: mesh.userData.onParcel,
    cE: +(mesh.position.x + m.originE).toFixed(2),
    cN: +(m.originN - mesh.position.z).toFixed(2),
    w: +mesh.scale.x.toFixed(2),
    d: +mesh.scale.z.toFixed(2),
    height: +mesh.scale.y.toFixed(2),
    base: +(mesh.position.y - mesh.scale.y / 2).toFixed(2),
    angleDeg: +THREE.MathUtils.radToDeg(mesh.rotation.y).toFixed(1),
    footprint: mesh.userData.footprint,
  }));
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
  const copy = selected.clone();
  copy.material = selected.material.clone();
  copy.userData = {
    ...selected.userData,
    id: `custom:${++customCount}:${selected.userData.id}`,
    footprint: [],
    label: null,
  };
  copy.position.x += 3;
  copy.position.z += 3;
  buildingsGroup.add(copy);
  refreshLabel(copy);
  applyExcavation();
  select(copy);
  markDirty();
}

window.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); save(); return; }
  if (e.key === 't') setMode('translate');
  if (e.key === 'r') setMode('rotate');
  if (e.key === 's') setMode('scale');
  if (e.key === 'd') duplicateSelected();
  if (e.key === 'Escape') select(null);
  if ((e.key === 'Delete' || e.key === 'Backspace') && selected) {
    const dead = selected;
    select(null);
    dead.userData.onParcel = false;     // drop its label
    refreshLabel(dead);
    buildingsGroup.remove(dead);
    dead.material.dispose();
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
