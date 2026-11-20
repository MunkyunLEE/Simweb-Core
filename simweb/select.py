import numpy as np

AX = {"x": 0, "y": 1, "z": 2}


def _diag(p):
    if len(p) == 0:
        return 1.0
    d = float(np.linalg.norm(p.max(axis=0) - p.min(axis=0)))
    return d if d > 0 else 1.0


def resolve(points, sel, geom=None):
    p = np.asarray(points, dtype=float).reshape(-1, 3)
    n = len(p)
    if not sel or sel.get("all"):
        return np.arange(n)
    if "and" in sel:
        out = None
        for s in sel["and"]:
            r = set(resolve(p, s, geom).tolist())
            out = r if out is None else out & r
        return np.array(sorted(out or []), dtype=int)
    if "or" in sel:
        out = set()
        for s in sel["or"]:
            out |= set(resolve(p, s, geom).tolist())
        return np.array(sorted(out), dtype=int)
    parts = []
    if "group" in sel:
        if geom is None:
            raise ValueError("그룹 선택에는 지오메트리가 필요합니다")
        if sel["group"] not in geom.group_names():
            raise ValueError(f"그룹 '{sel['group']}' 이(가) 없습니다. 사용 가능: {', '.join(geom.group_names()) or '없음'}")
        parts.append(set(geom.group_vertices(sel["group"])))
    if "nodes" in sel:
        parts.append(set(int(i) for i in sel["nodes"] if 0 <= int(i) < n))
    if "plane" in sel:
        q = sel["plane"]
        a = AX[str(q.get("axis", "z")).lower()]
        c = p[:, a]
        at = q.get("at", "min")
        v = c.min() if at == "min" else c.max() if at == "max" else c.mean() if at in ("mid", "center") else float(at)
        tol = float(q.get("tol", _diag(p) * 1e-4))
        parts.append(set(np.where(np.abs(c - v) <= tol)[0].tolist()))
    if "box" in sel:
        lo = np.array(sel["box"]["min"], dtype=float)
        hi = np.array(sel["box"]["max"], dtype=float)
        tol = _diag(p) * 1e-6
        ok = np.all((p >= lo - tol) & (p <= hi + tol), axis=1)
        parts.append(set(np.where(ok)[0].tolist()))
    if sel.get("corners"):
        lo, hi = p.min(axis=0), p.max(axis=0)
        ids = set()
        for i in range(8):
            c = np.array([hi[k] if (i >> k) & 1 else lo[k] for k in range(3)])
            ids.add(int(np.argmin(np.linalg.norm(p - c, axis=1))))
        parts.append(ids)
    if "nearest" in sel:
        parts.append({int(np.argmin(np.linalg.norm(p - np.array(sel["nearest"], dtype=float), axis=1)))})
    if not parts:
        raise ValueError(f"선택 조건을 해석할 수 없습니다: {sel}")
    out = parts[0]
    for s in parts[1:]:
        out &= s
    return np.array(sorted(out), dtype=int)


def describe(sel):
    if not sel or sel.get("all"):
        return "전체"
    if "and" in sel:
        return " ∩ ".join(describe(s) for s in sel["and"])
    if "or" in sel:
        return " ∪ ".join(describe(s) for s in sel["or"])
    out = []
    if "group" in sel:
        out.append(f"그룹 {sel['group']}")
    if "plane" in sel:
        q = sel["plane"]
        out.append(f"{q.get('axis', 'z')}={q.get('at', 'min')}")
    if "box" in sel:
        out.append("박스 영역")
    if sel.get("corners"):
        out.append("모서리 점")
    if "nearest" in sel:
        out.append("점 (" + ", ".join(f"{float(v):g}" for v in sel["nearest"]) + ")")
    if "nodes" in sel:
        out.append(f"점 {len(sel['nodes'])}개")
    return " ∩ ".join(out)
