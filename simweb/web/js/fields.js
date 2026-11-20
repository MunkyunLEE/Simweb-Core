export const FIELDS = {
  umag: { label: '속도 크기 |u|', unit: 'mm/s', kind: 'seq' },
  ux: { label: 'uₓ', unit: 'mm/s', kind: 'div' },
  uy: { label: 'u_y', unit: 'mm/s', kind: 'div' },
  uz: { label: 'u_z', unit: 'mm/s', kind: 'div' },
  p: { label: '압력 p', unit: 'MPa', kind: 'seq' },
  vort: { label: '단면 수직 와도 ωₙ', unit: '1/s', kind: 'div' },
  q: { label: 'Q-criterion', unit: '1/s²', kind: 'div' },
};

const N = 253;

function turbo(x) {
  const r = 0.13572138 + x * (4.6153926 + x * (-42.66032258 + x * (132.13108234 + x * (-152.94239396 + x * 59.28637943))));
  const g = 0.09140261 + x * (2.19418839 + x * (4.84296658 + x * (-14.18503333 + x * (4.27729857 + x * 2.82956604))));
  const b = 0.1066733 + x * (12.64194608 + x * (-60.58204836 + x * (110.36276771 + x * (-89.90310912 + x * 27.34824973))));
  return [r, g, b].map((v) => Math.min(1, Math.max(0, v)));
}

function diverging(x) {
  const lo = [0.23, 0.3, 0.75];
  const mid = [0.95, 0.95, 0.95];
  const hi = [0.71, 0.02, 0.15];
  return x < 0.5 ? lo.map((v, i) => v + (mid[i] - v) * (x / 0.5)) : mid.map((v, i) => v + (hi[i] - v) * ((x - 0.5) / 0.5));
}

const LUTS = {};
export function lut(kind) {
  if (!LUTS[kind]) {
    const out = [];
    for (let k = 0; k < N; k++) out.push((kind === 'seq' ? turbo : diverging)(k / (N - 1)));
    LUTS[kind] = out;
  }
  return LUTS[kind];
}

export const kindOf = (field) => (FIELDS[field] || FIELDS.umag).kind;

function percentile(values, q) {
  const n = values.length;
  if (!n) return 0;
  const stride = Math.max(1, Math.ceil(n / 65536));
  const a = [];
  for (let i = 0; i < n; i += stride) if (Number.isFinite(values[i])) a.push(values[i]);
  if (!a.length) return 0;
  a.sort((x, y) => x - y);
  const pos = (q / 100) * (a.length - 1);
  const lo = Math.floor(pos);
  const hi = Math.min(lo + 1, a.length - 1);
  return a[lo] + (a[hi] - a[lo]) * (pos - lo);
}

export function autoRange(field, values) {
  const k = kindOf(field);
  if (field === 'p') {
    const hi = percentile(values, 99);
    const lo = hi > 0 ? 0 : percentile(values, 1);
    return [lo, Math.max(hi, lo + 1e-12)];
  }
  if (k === 'seq') return [0, Math.max(percentile(values, 99.7), 1e-9)];
  const abs = new Float32Array(values.length);
  for (let i = 0; i < values.length; i++) abs[i] = Math.abs(values[i]);
  const m = Math.max(percentile(abs, 99.0), 1e-12);
  return [-m, m];
}

export function colorize(values, field, lo, hi, out) {
  const L = lut(kindOf(field));
  const s = (L.length - 1) / (hi - lo || 1);
  const o = out || new Float32Array(values.length * 3);
  for (let i = 0; i < values.length; i++) {
    const c = L[Math.max(0, Math.min(L.length - 1, Math.round((values[i] - lo) * s)))];
    o[3 * i] = c[0];
    o[3 * i + 1] = c[1];
    o[3 * i + 2] = c[2];
  }
  return o;
}

export function legendGradient(field, lo, hi) {
  const L = lut(kindOf(field));
  const stops = [];
  for (let i = 0; i <= 10; i++) {
    const c = L[Math.round((i / 10) * (L.length - 1))];
    stops.push(`rgb(${c.map((v) => Math.round(v * 255)).join(',')}) ${i * 10}%`);
  }
  return `linear-gradient(to top, ${stops.join(',')})`;
}

const AX = { X: 0, Y: 1, Z: 2 };
const INPLANE = { X: [1, 2], Y: [0, 2], Z: [0, 1] };

export function gridIndex(G, i, j, k) {
  return i + G.n[0] * (j + G.n[1] * k);
}

export function planeDims(G, P) {
  const [a, b] = INPLANE[P];
  return [G.n[a], G.n[b]];
}

function planeCell(G, P, s, a, b) {
  const c = [0, 0, 0];
  c[AX[P]] = s;
  c[INPLANE[P][0]] = a;
  c[INPLANE[P][1]] = b;
  return gridIndex(G, c[0], c[1], c[2]);
}

export function sliceIndex(G, P, f) {
  const n = G.n[AX[P]];
  return Math.max(0, Math.min(n - 1, Math.round(f * (n - 1))));
}

export function planeField(G, P, s, field, Q) {
  const [w, h] = planeDims(G, P);
  const n = w * h;
  const val = new Float32Array(n);
  const solid = new Uint8Array(n);
  const [ia, ib] = INPLANE[P];
  const idx = new Int32Array(n);
  for (let b = 0; b < h; b++) for (let a = 0; a < w; a++) {
    const k = a + w * b;
    const g = planeCell(G, P, s, a, b);
    idx[k] = g;
    if (!G.occ[g]) solid[k] = 1;
  }
  const u = (g, c) => G.u[3 * g + c];
  for (let b = 0; b < h; b++) for (let a = 0; a < w; a++) {
    const k = a + w * b;
    if (solid[k]) continue;
    const g = idx[k];
    if (field === 'umag') val[k] = Math.hypot(u(g, 0), u(g, 1), u(g, 2));
    else if (field === 'ux' || field === 'uy' || field === 'uz') val[k] = u(g, { ux: 0, uy: 1, uz: 2 }[field]);
    else if (field === 'p') val[k] = G.p[g];
    else if (field === 'q') val[k] = Q ? Q[g] : 0;
    else if (field === 'vort') {
      const l = a > 0 && !solid[k - 1];
      const r = a < w - 1 && !solid[k + 1];
      const dn = b > 0 && !solid[k - w];
      const up = b < h - 1 && !solid[k + w];
      const dA = (c) => (l && r ? (u(idx[k + 1], c) - u(idx[k - 1], c)) / 2 : r ? u(idx[k + 1], c) - u(g, c) : l ? u(g, c) - u(idx[k - 1], c) : 0);
      const dB = (c) => (dn && up ? (u(idx[k + w], c) - u(idx[k - w], c)) / 2 : up ? u(idx[k + w], c) - u(g, c) : dn ? u(g, c) - u(idx[k - w], c) : 0);
      val[k] = ((P === 'Y' ? -1 : 1) * (dA(ib) - dB(ia))) / G.h;
    }
  }
  return { w, h, val, solid };
}

export function planeRGBA(pf, field, lo, hi, solidRGBA = [0, 0, 0, 0]) {
  const L = lut(kindOf(field));
  const s = (L.length - 1) / (hi - lo || 1);
  const out = new Uint8Array(4 * pf.val.length);
  for (let k = 0; k < pf.val.length; k++) {
    if (pf.solid[k]) {
      out.set(solidRGBA, 4 * k);
      continue;
    }
    const c = L[Math.max(0, Math.min(L.length - 1, Math.round((pf.val[k] - lo) * s)))];
    out[4 * k] = c[0] * 255;
    out[4 * k + 1] = c[1] * 255;
    out[4 * k + 2] = c[2] * 255;
    out[4 * k + 3] = 235;
  }
  return out;
}

export function toWorld(G, P, s, a, b) {
  const c = [0, 0, 0];
  c[AX[P]] = s;
  c[INPLANE[P][0]] = a;
  c[INPLANE[P][1]] = b;
  return c.map((v, d) => G.origin[d] + G.h * v);
}

export function planeCorners(G, P, s) {
  const [w, h] = planeDims(G, P);
  return [toWorld(G, P, s, -0.5, -0.5), toWorld(G, P, s, w - 0.5, -0.5), toWorld(G, P, s, w - 0.5, h - 0.5), toWorld(G, P, s, -0.5, h - 0.5)];
}

export function planeVectors(G, P, s, stride) {
  const [w, h] = planeDims(G, P);
  const [ia, ib] = INPLANE[P];
  const out = [];
  let um = 0;
  const cells = [];
  for (let b = Math.floor(stride / 2); b < h; b += stride) for (let a = Math.floor(stride / 2); a < w; a += stride) {
    const g = planeCell(G, P, s, a, b);
    if (!G.occ[g]) continue;
    const ua = G.u[3 * g + ia];
    const ub = G.u[3 * g + ib];
    um = Math.max(um, Math.hypot(ua, ub));
    cells.push([a, b, ua, ub]);
  }
  if (um <= 0) return out;
  const L = stride * 0.95;
  for (const [a, b, va, vb] of cells) {
    const ua = va / um;
    const ub = vb / um;
    const m = Math.hypot(ua, ub);
    if (m < 0.03) continue;
    const x1 = a + ua * L;
    const y1 = b + ub * L;
    const hl = Math.min(0.35 * m * L, 0.45 * stride);
    const ex = ua / m;
    const ey = ub / m;
    out.push(...toWorld(G, P, s, a, b), ...toWorld(G, P, s, x1, y1));
    out.push(...toWorld(G, P, s, x1, y1), ...toWorld(G, P, s, x1 - hl * (ex * 0.87 - ey * 0.5), y1 - hl * (ey * 0.87 + ex * 0.5)));
    out.push(...toWorld(G, P, s, x1, y1), ...toWorld(G, P, s, x1 - hl * (ex * 0.87 + ey * 0.5), y1 - hl * (ey * 0.87 - ex * 0.5)));
  }
  return out;
}

function sample2(ux, uy, solid, w, h, x, y) {
  const i = Math.floor(x);
  const j = Math.floor(y);
  if (i < 0 || j < 0 || i >= w - 1 || j >= h - 1) return null;
  const ax = x - i;
  const ay = y - j;
  const k = j * w + i;
  if (solid[k] && solid[k + 1] && solid[k + w] && solid[k + w + 1]) return null;
  const w00 = (1 - ax) * (1 - ay);
  const w10 = ax * (1 - ay);
  const w01 = (1 - ax) * ay;
  const w11 = ax * ay;
  return [w00 * ux[k] + w10 * ux[k + 1] + w01 * ux[k + w] + w11 * ux[k + w + 1], w00 * uy[k] + w10 * uy[k + 1] + w01 * uy[k + w] + w11 * uy[k + w + 1]];
}

function trace(ux, uy, solid, w, h, x0, y0, dir, step, maxSteps, occ, oc, ocw, och, umin) {
  const pts = [];
  let x = x0;
  let y = y0;
  const d = (v) => {
    const s = Math.hypot(v[0], v[1]) || 1;
    return [(dir * v[0]) / s, (dir * v[1]) / s];
  };
  for (let n = 0; n < maxSteps; n++) {
    const v1 = sample2(ux, uy, solid, w, h, x, y);
    if (!v1 || Math.hypot(v1[0], v1[1]) < umin) break;
    const k1 = d(v1);
    const v2 = sample2(ux, uy, solid, w, h, x + 0.5 * step * k1[0], y + 0.5 * step * k1[1]);
    if (!v2) break;
    const k2 = d(v2);
    const v3 = sample2(ux, uy, solid, w, h, x + 0.5 * step * k2[0], y + 0.5 * step * k2[1]);
    if (!v3) break;
    const k3 = d(v3);
    const v4 = sample2(ux, uy, solid, w, h, x + step * k3[0], y + step * k3[1]);
    if (!v4) break;
    const k4 = d(v4);
    x += (step * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])) / 6;
    y += (step * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])) / 6;
    const ci = Math.floor(x / oc);
    const cj = Math.floor(y / oc);
    if (ci < 0 || cj < 0 || ci >= ocw || cj >= och || occ[cj * ocw + ci] === 2) break;
    pts.push([x, y]);
  }
  return pts;
}

export function planeStreams(G, P, s, density = 4) {
  const [w, h] = planeDims(G, P);
  const [ia, ib] = INPLANE[P];
  const n = w * h;
  const ux = new Float32Array(n);
  const uy = new Float32Array(n);
  const solid = new Uint8Array(n);
  let umax = 0;
  for (let b = 0; b < h; b++) for (let a = 0; a < w; a++) {
    const k = a + w * b;
    const g = planeCell(G, P, s, a, b);
    if (!G.occ[g]) {
      solid[k] = 1;
      continue;
    }
    ux[k] = G.u[3 * g + ia];
    uy[k] = G.u[3 * g + ib];
    umax = Math.max(umax, Math.hypot(ux[k], uy[k]));
  }
  const spacing = Math.max(1, (Math.max(w, h) / 10) * Math.pow(Math.min(1, 12 / Math.max(w, h)), (density - 1) / 9));
  const oc = Math.max(1, spacing / 2);
  const ocw = Math.ceil(w / oc);
  const och = Math.ceil(h / oc);
  const occ = new Uint8Array(ocw * och);
  const out = [];
  const maxSteps = 4 * (w + h);
  for (let sy = spacing / 2; sy < h; sy += spacing) for (let sx = spacing / 2; sx < w; sx += spacing) {
    if (occ[Math.floor(sy / oc) * ocw + Math.floor(sx / oc)]) continue;
    if (!sample2(ux, uy, solid, w, h, sx, sy)) continue;
    const back = trace(ux, uy, solid, w, h, sx, sy, -1, 0.5, maxSteps, occ, oc, ocw, och, umax * 0.01);
    const fwd = trace(ux, uy, solid, w, h, sx, sy, 1, 0.5, maxSteps, occ, oc, ocw, och, umax * 0.01);
    const line = [...back.reverse(), [sx, sy], ...fwd];
    if (line.length < 8) continue;
    for (const [x, y] of line) {
      const a = Math.floor(x / oc);
      const b = Math.floor(y / oc);
      if (a >= 0 && b >= 0 && a < ocw && b < och) occ[b * ocw + a] = 2;
    }
    for (let q = 0; q + 1 < line.length; q++) out.push(...toWorld(G, P, s, line[q][0], line[q][1]), ...toWorld(G, P, s, line[q + 1][0], line[q + 1][1]));
  }
  return out;
}

export function qField(G) {
  const [nx, ny, nz] = G.n;
  const nxy = nx * ny;
  const Q = new Float32Array(nx * ny * nz);
  const u = G.u;
  const inv = 1 / G.h;
  for (let z = 0; z < nz; z++) for (let y = 0; y < ny; y++) for (let x = 0; x < nx; x++) {
    const k = x + nx * y + nxy * z;
    if (!G.occ[k]) continue;
    const d = (off, i, n, c) => {
      const kp = i < n - 1 && G.occ[k + off] ? k + off : k;
      const km = i > 0 && G.occ[k - off] ? k - off : k;
      const den = (kp !== k) + (km !== k);
      return den ? ((u[3 * kp + c] - u[3 * km + c]) / den) * inv : 0;
    };
    const uxx = d(1, x, nx, 0);
    const uxy = d(nx, y, ny, 0);
    const uxz = d(nxy, z, nz, 0);
    const uyx = d(1, x, nx, 1);
    const uyy = d(nx, y, ny, 1);
    const uyz = d(nxy, z, nz, 1);
    const uzx = d(1, x, nx, 2);
    const uzy = d(nx, y, ny, 2);
    const uzz = d(nxy, z, nz, 2);
    Q[k] = -0.5 * (uxx * uxx + uyy * uyy + uzz * uzz) - (uxy * uyx + uxz * uzx + uyz * uzy);
  }
  return Q;
}

export function qLevel(Q, frac) {
  const pos = [];
  const st = Math.max(1, Math.floor(Q.length / 200000));
  for (let k = 0; k < Q.length; k += st) if (Q[k] > 0) pos.push(Q[k]);
  if (!pos.length) return Infinity;
  pos.sort((a, b) => a - b);
  return pos[Math.floor(0.995 * (pos.length - 1))] * frac;
}

const TETS = [[0, 5, 1, 6], [0, 1, 2, 6], [0, 2, 3, 6], [0, 3, 7, 6], [0, 7, 4, 6], [0, 4, 5, 6]];
const CORNER = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]];

export function isosurface(G, V, level, maxTris = 600000) {
  const [nx, ny, nz] = G.n;
  const pos = [];
  const spd = [];
  const P = new Float32Array(24);
  const val = new Float32Array(8);
  const sp = new Float32Array(8);
  const emit = (a, b) => {
    const t = (level - val[a]) / (val[b] - val[a] || 1e-30);
    for (let c = 0; c < 3; c++) pos.push(G.origin[c] + G.h * (P[3 * a + c] + t * (P[3 * b + c] - P[3 * a + c])));
    spd.push(sp[a] + t * (sp[b] - sp[a]));
  };
  for (let z = 0; z < nz - 1; z++) for (let y = 0; y < ny - 1; y++) for (let x = 0; x < nx - 1; x++) {
    let lo = Infinity;
    let hi = -Infinity;
    for (let c = 0; c < 8; c++) {
      const [dx, dy, dz] = CORNER[c];
      const g = x + dx + nx * (y + dy + ny * (z + dz));
      val[c] = V[g];
      sp[c] = Math.hypot(G.u[3 * g], G.u[3 * g + 1], G.u[3 * g + 2]);
      lo = Math.min(lo, val[c]);
      hi = Math.max(hi, val[c]);
      P[3 * c] = x + dx;
      P[3 * c + 1] = y + dy;
      P[3 * c + 2] = z + dz;
    }
    if (lo > level || hi < level) continue;
    for (const t of TETS) {
      const ins = t.filter((c) => val[c] > level);
      const out = t.filter((c) => val[c] <= level);
      if (ins.length === 1) {
        emit(ins[0], out[0]);
        emit(ins[0], out[1]);
        emit(ins[0], out[2]);
      } else if (ins.length === 3) {
        emit(out[0], ins[0]);
        emit(out[0], ins[2]);
        emit(out[0], ins[1]);
      } else if (ins.length === 2) {
        const [a, b] = ins;
        const [c, d] = out;
        emit(a, c);
        emit(a, d);
        emit(b, c);
        emit(b, c);
        emit(a, d);
        emit(b, d);
      }
    }
    if (pos.length > 9 * maxTris) break;
  }
  return { pos: new Float32Array(pos), spd: new Float32Array(spd) };
}

export function decodeFrame(buf) {
  const dv = new DataView(buf);
  const hl = dv.getUint32(0, true);
  const head = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, hl)));
  let off = 4 + hl;
  off = Math.ceil(off / 4) * 4;
  const out = { head };
  for (const [name, len, type] of head.arrays) {
    const T = type === 'u8' ? Uint8Array : type === 'i32' ? Int32Array : Float32Array;
    out[name] = new T(buf, off, len);
    off += len * T.BYTES_PER_ELEMENT;
    off = Math.ceil(off / 4) * 4;
  }
  return out;
}
