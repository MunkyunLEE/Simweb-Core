import { el, fmt } from './util.js';

export const COLORS = ['#4cc2ff', '#ff5fa8', '#57d9a3', '#ffc857', '#c792ea', '#ff8a5c'];
export const REFC = ['#ffffff', '#b0bec5', '#ffd54f', '#80cbc4'];

export function chart(p) {
  const W = 420;
  const H = 230;
  const m = { l: 58, r: 12, t: 8, b: 34 };
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  let x0 = Infinity;
  let x1 = -Infinity;
  let y0 = Infinity;
  let y1 = -Infinity;
  for (const s of p.series.concat(p.refs || [])) {
    for (const v of s.x) {
      x0 = Math.min(x0, v);
      x1 = Math.max(x1, v);
    }
    for (const v of s.y) {
      y0 = Math.min(y0, v);
      y1 = Math.max(y1, v);
    }
  }
  if (!isFinite(x0)) return svg;
  if (x0 === x1) x1 = x0 + 1;
  if (y0 === y1) {
    y0 -= Math.abs(y0) * 0.1 || 1;
    y1 += Math.abs(y1) * 0.1 || 1;
  }
  const py = (y1 - y0) * 0.06;
  y0 -= py;
  y1 += py;
  const X = (v) => m.l + ((v - x0) / (x1 - x0)) * (W - m.l - m.r);
  const Y = (v) => H - m.b - ((v - y0) / (y1 - y0)) * (H - m.t - m.b);
  const mk = (tag, attrs, text) => {
    const e = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (text !== undefined) e.textContent = text;
    svg.append(e);
    return e;
  };
  for (let i = 0; i <= 4; i++) {
    const yv = y0 + ((y1 - y0) * i) / 4;
    const xv = x0 + ((x1 - x0) * i) / 4;
    mk('line', { x1: m.l, x2: W - m.r, y1: Y(yv), y2: Y(yv), stroke: '#2a3340', 'stroke-width': 1 });
    mk('text', { x: m.l - 6, y: Y(yv) + 3, 'text-anchor': 'end', 'font-size': 10, fill: '#8492a6' }, fmt(yv));
    mk('text', { x: X(xv), y: H - m.b + 14, 'text-anchor': 'middle', 'font-size': 10, fill: '#8492a6' }, fmt(xv));
  }
  mk('text', { x: (m.l + W - m.r) / 2, y: H - 4, 'text-anchor': 'middle', 'font-size': 10, fill: '#8492a6' }, p.xlabel || '');
  p.series.forEach((s, k) => {
    const pts = s.x.map((v, i) => `${X(v).toFixed(1)},${Y(s.y[i]).toFixed(1)}`).join(' ');
    mk('polyline', { points: pts, fill: 'none', stroke: COLORS[k % COLORS.length], 'stroke-width': 1.8 });
    if (s.x.length <= 40) s.x.forEach((v, i) => mk('circle', { cx: X(v), cy: Y(s.y[i]), r: 2.2, fill: COLORS[k % COLORS.length] }));
  });
  (p.refs || []).forEach((s) => {
    const pts = s.x.map((v, i) => `${X(v).toFixed(1)},${Y(s.y[i]).toFixed(1)}`).join(' ');
    mk('polyline', { points: pts, fill: 'none', stroke: REFC[0], 'stroke-width': 1.8, 'stroke-dasharray': '5 3' });
  });
  return svg;
}

export function plotCard(p, onRemove) {
  const d = el('div', 'plot');
  const t = el('div', 'ptitle');
  t.append(el('span', '', p.id ? `${p.id} · ${p.title}` : p.title));
  if (onRemove) {
    const x = el('button', '', '✕');
    x.onclick = () => onRemove(p);
    t.append(x);
  }
  d.append(t);
  if (p.error) {
    d.append(el('div', 'perr', p.error));
    return d;
  }
  d.append(chart(p));
  const lg = el('div', 'legend');
  p.series.forEach((s, k) => {
    const sp = el('span');
    const i = el('i');
    i.style.background = COLORS[k % COLORS.length];
    sp.append(i, document.createTextNode(s.name || ''));
    lg.append(sp);
  });
  d.append(lg);
  return d;
}
