import * as THREE from 'three';
import { OrbitControls } from '../vendor/OrbitControls.js';

export { THREE };

export const RAMP = [
  [0.17, 0.29, 1.0],
  [0.1, 0.76, 0.49],
  [1.0, 0.88, 0.29],
  [1.0, 0.23, 0.19],
];

export function ramp(t, out, o) {
  const x = Math.min(Math.max(t, 0), 1) * 3;
  const i = Math.min(Math.floor(x), 2);
  const f = x - i;
  for (let k = 0; k < 3; k++) out[o + k] = RAMP[i][k] + (RAMP[i + 1][k] - RAMP[i][k]) * f;
}

export const surfaceMat = (extra) => new THREE.MeshStandardMaterial({ roughness: 0.62, metalness: 0.08, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1, ...extra });

export const GROUP_COLORS = [0x9fb3c8, 0x8fc7b5, 0xc9b48f, 0xb39fc8, 0xc89f9f, 0x9fc8c3, 0xc8c29f];

export function createViewer(canvas, gizmo) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 1e7);
  camera.up.set(0, 0, 1);
  camera.position.set(300, -400, 250);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.12;
  scene.add(new THREE.HemisphereLight(0xffffff, 0x2a3442, 1.25));
  const sun = new THREE.DirectionalLight(0xffffff, 1.9);
  scene.add(sun);
  const fill = new THREE.DirectionalLight(0xbcd4ff, 0.7);
  scene.add(fill);
  const groups = {};
  const hooks = [];
  const V = { THREE, renderer, scene, camera, controls, groups, diag: 100, center: new THREE.Vector3() };

  V.group = (name) => {
    if (!groups[name]) {
      groups[name] = new THREE.Group();
      scene.add(groups[name]);
    }
    return groups[name];
  };

  V.clear = (g) => {
    while (g.children.length) {
      const c = g.children.pop();
      c.traverse((o) => {
        if (o.geometry) o.geometry.dispose();
        if (o.material) o.material.dispose();
      });
    }
  };

  V.resize = () => {
    const r = canvas.parentElement.getBoundingClientRect();
    renderer.setSize(r.width, r.height, false);
    camera.aspect = r.width / Math.max(r.height, 1);
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(V.resize).observe(canvas.parentElement);

  V.fitBox = (lo, hi) => {
    const b = new THREE.Box3(new THREE.Vector3(...lo), new THREE.Vector3(...hi));
    V.center = b.getCenter(new THREE.Vector3());
    V.diag = Math.max(b.getSize(new THREE.Vector3()).length(), 1e-6);
    controls.target.copy(V.center);
    camera.position.copy(V.center).add(new THREE.Vector3(0.9, -1.2, 0.75).multiplyScalar(V.diag));
    camera.near = V.diag / 500;
    camera.far = V.diag * 100;
    camera.updateProjectionMatrix();
  };

  V.fitPoints = (pts) => {
    if (!pts || !pts.length) return;
    const lo = [Infinity, Infinity, Infinity];
    const hi = [-Infinity, -Infinity, -Infinity];
    for (const p of pts) for (let k = 0; k < 3; k++) {
      lo[k] = Math.min(lo[k], p[k]);
      hi[k] = Math.max(hi[k], p[k]);
    }
    V.fitBox(lo, hi);
  };

  V.onFrame = (fn) => hooks.push(fn);

  function drawGizmo() {
    if (!gizmo) return;
    const x = gizmo.getContext('2d');
    x.clearRect(0, 0, 96, 96);
    const q = camera.quaternion.clone().invert();
    const axes = [
      ['X', new THREE.Vector3(1, 0, 0), '#ff5c5c'],
      ['Y', new THREE.Vector3(0, 1, 0), '#57d9a3'],
      ['Z', new THREE.Vector3(0, 0, 1), '#4cc2ff'],
    ].map(([n, v, col]) => [n, v.applyQuaternion(q), col]);
    axes.sort((a, b) => a[1].z - b[1].z);
    x.font = '11px sans-serif';
    x.textAlign = 'center';
    x.textBaseline = 'middle';
    for (const [n, v, col] of axes) {
      x.strokeStyle = col;
      x.fillStyle = col;
      x.lineWidth = 2;
      x.beginPath();
      x.moveTo(48, 48);
      x.lineTo(48 + v.x * 30, 48 - v.y * 30);
      x.stroke();
      x.fillText(n, 48 + v.x * 40, 48 - v.y * 40);
    }
  }

  function loop() {
    controls.update();
    const d = camera.position.distanceTo(controls.target);
    const cr = new THREE.Vector3().crossVectors(camera.getWorldDirection(new THREE.Vector3()), camera.up).normalize();
    sun.position.copy(camera.position).addScaledVector(cr, -0.45 * d).addScaledVector(camera.up, 0.5 * d);
    sun.target.position.copy(controls.target);
    sun.target.updateMatrixWorld();
    fill.position.copy(camera.position).addScaledVector(cr, 0.9 * d);
    fill.target.position.copy(controls.target);
    fill.target.updateMatrixWorld();
    for (const fn of hooks) fn();
    renderer.render(scene, camera);
    drawGizmo();
    requestAnimationFrame(loop);
  }

  V.start = () => {
    V.resize();
    loop();
  };

  V.snapshot = (maxW, hide = []) => {
    const vis = hide.map((g) => g.visible);
    hide.forEach((g) => (g.visible = false));
    renderer.render(scene, camera);
    hide.forEach((g, i) => (g.visible = vis[i]));
    const k = Math.min(1, maxW / canvas.width);
    const c = document.createElement('canvas');
    c.width = Math.round(canvas.width * k);
    c.height = Math.round(canvas.height * k);
    const x = c.getContext('2d');
    x.fillStyle = getComputedStyle(document.body).backgroundColor || '#0f141b';
    x.fillRect(0, 0, c.width, c.height);
    x.drawImage(canvas, 0, 0, c.width, c.height);
    return c.toDataURL('image/png');
  };

  V.drawGeometry = (view, opt = {}) => {
    const gm = V.group('model');
    const ge = V.group('edges');
    V.clear(gm);
    V.clear(ge);
    if (!view) return;
    const pos = new Float32Array(view.nodes.flat());
    if (view.tris.length) {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      g.setIndex(view.tris.flat());
      const flat = g.toNonIndexed();
      g.dispose();
      const col = new Float32Array(flat.attributes.position.count * 3);
      view.tri_group.forEach((gi, t) => {
        const c = new THREE.Color(GROUP_COLORS[gi % GROUP_COLORS.length]);
        for (let k = 0; k < 3; k++) c.toArray(col, (3 * t + k) * 3);
      });
      flat.setAttribute('color', new THREE.BufferAttribute(col, 3));
      flat.computeVertexNormals();
      gm.add(new THREE.Mesh(flat, surfaceMat({ vertexColors: true, transparent: opt.opacity < 1, opacity: opt.opacity ?? 1, depthWrite: !(opt.opacity < 1) })));
      let ed = (view.edges || []).flat();
      if (!ed.length) {
        const seen = new Set();
        for (const f of view.tris) for (let i = 0; i < 3; i++) {
          const a = f[i];
          const b = f[(i + 1) % 3];
          const k = a < b ? a * 1e7 + b : b * 1e7 + a;
          if (!seen.has(k)) {
            seen.add(k);
            ed.push(a, b);
          }
        }
      }
      const eg = new THREE.BufferGeometry();
      eg.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      eg.setIndex(ed);
      ge.add(new THREE.LineSegments(eg, new THREE.LineBasicMaterial({ color: 0x2c3948 })));
    }
    if (view.lines.length) {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      g.setIndex(view.lines.flat());
      gm.add(new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0xe8eef6 })));
    }
    const h = Object.values(view.hinges || {}).flat();
    if (h.length) {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      g.setIndex(h.flat());
      gm.add(new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0xff5fa8, depthTest: false })));
    }
  };

  V.boxLines = (lo, hi, color, dashed) => {
    const g = new THREE.BufferGeometry().setFromPoints([
      [0, 1], [1, 3], [3, 2], [2, 0], [4, 5], [5, 7], [7, 6], [6, 4], [0, 4], [1, 5], [2, 6], [3, 7],
    ].flatMap(([a, b]) => [a, b].map((i) => new THREE.Vector3(i & 1 ? hi[0] : lo[0], i & 2 ? hi[1] : lo[1], i & 4 ? hi[2] : lo[2]))));
    const m = dashed ? new THREE.LineDashedMaterial({ color, dashSize: V.diag / 80, gapSize: V.diag / 120 }) : new THREE.LineBasicMaterial({ color });
    const l = new THREE.LineSegments(g, m);
    if (dashed) l.computeLineDistances();
    return l;
  };

  V.points = (flat, colors, size = 3) => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(flat instanceof Float32Array ? flat : new Float32Array(flat), 3));
    if (colors) g.setAttribute('color', new THREE.BufferAttribute(colors instanceof Float32Array ? colors : new Float32Array(colors), 3));
    return new THREE.Points(g, new THREE.PointsMaterial({ size, sizeAttenuation: false, vertexColors: !!colors, color: colors ? 0xffffff : 0x4cc2ff }));
  };

  V.arrow = (from, dir, len, color) => {
    const d = new THREE.Vector3(...dir).normalize();
    const a = new THREE.ArrowHelper(d, new THREE.Vector3(...from), len, color, len * 0.25, len * 0.14);
    a.traverse((o) => {
      if (o.material) o.material.depthTest = false;
    });
    a.renderOrder = 3;
    return a;
  };

  return V;
}

export function setLegend(root, title, lo, hi, fmt) {
  if (!root) return;
  root.hidden = false;
  root.querySelector('#legendTitle').textContent = title;
  const ticks = root.querySelector('#legendTicks');
  ticks.innerHTML = '';
  for (let i = 4; i >= 0; i--) {
    const d = document.createElement('div');
    d.textContent = fmt(lo + ((hi - lo) * i) / 4);
    ticks.append(d);
  }
}
