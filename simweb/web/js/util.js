export const $ = (id) => document.getElementById(id);

export const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};

export const fmt = (v) => {
  if (v === null || v === undefined) return '-';
  if (typeof v !== 'number') return String(v);
  if (v === 0) return '0';
  const a = Math.abs(v);
  return a >= 1e5 || a < 1e-3 ? v.toExponential(3) : String(+v.toPrecision(5));
};

export async function api(path, opts = {}) {
  const o = { ...opts };
  if (o.json !== undefined) {
    o.method = o.method || 'POST';
    o.headers = { 'Content-Type': 'application/json' };
    o.body = JSON.stringify(o.json);
  }
  const r = await fetch(path, o);
  let data = null;
  try {
    data = await r.json();
  } catch (e) {
    data = null;
  }
  if (!r.ok) throw new Error((data && data.detail) || `요청 실패 (${r.status})`);
  return data;
}

export function download(url, name) {
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
}
