import struct

import numpy as np

UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "inch": 25.4, "in": 25.4}


class Geometry:
    def __init__(self):
        self.vertices = np.zeros((0, 3))
        self.faces = []
        self.face_group = []
        self.lines = []
        self.line_group = []
        self.hinges = {}
        self.source = ""
        self.kind = "obj"
        self.unit = "mm"

    def copy(self):
        g = Geometry()
        g.vertices = self.vertices.copy()
        g.faces = [list(f) for f in self.faces]
        g.face_group = list(self.face_group)
        g.lines = [tuple(e) for e in self.lines]
        g.line_group = list(self.line_group)
        g.hinges = {k: [tuple(e) for e in v] for k, v in self.hinges.items()}
        g.source, g.kind, g.unit = self.source, self.kind, self.unit
        return g

    def bbox(self):
        if len(self.vertices) == 0:
            return np.zeros(3), np.zeros(3)
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    def diag(self):
        lo, hi = self.bbox()
        d = float(np.linalg.norm(hi - lo))
        return d if d > 0 else 1.0

    def triangles(self):
        out, grp = [], []
        for f, g in zip(self.faces, self.face_group):
            for i in range(1, len(f) - 1):
                out.append([f[0], f[i], f[i + 1]])
                grp.append(g)
        return np.array(out, dtype=int).reshape(-1, 3), grp

    def group_names(self):
        return sorted(set(self.face_group) | set(self.line_group) | set(self.hinges))

    def group_vertices(self, name):
        ids = set()
        for f, g in zip(self.faces, self.face_group):
            if g == name:
                ids.update(f)
        for e, g in zip(self.lines, self.line_group):
            if g == name:
                ids.update(e)
        for e in self.hinges.get(name, []):
            ids.update(e)
        return sorted(ids)

    def edges(self):
        out = {}
        for k, f in enumerate(self.faces):
            for i in range(len(f)):
                a, b = f[i], f[(i + 1) % len(f)]
                out.setdefault((min(a, b), max(a, b)), []).append(k)
        return out

    def feature_edges(self, angle=20.0):
        if not self.faces:
            return []
        v = self.vertices
        n = []
        for f in self.faces:
            p = v[f]
            c = np.cross(p[1] - p[0], p[2] - p[0]) if len(f) == 3 else np.cross(p[2] - p[0], p[3] - p[1])
            n.append(c / (np.linalg.norm(c) or 1.0))
        n = np.array(n)
        cos = np.cos(np.radians(angle))
        out = []
        for e, fs in self.edges().items():
            if len(fs) != 2 or self.face_group[fs[0]] != self.face_group[fs[1]] or abs(float(n[fs[0]] @ n[fs[1]])) < cos:
                out.append(list(e))
        return out

    def closed(self):
        e = self.edges()
        if not e:
            return {"closed": False, "open_edges": 0, "nonmanifold_edges": 0}
        cnt = np.array([len(v) for v in e.values()])
        return {"closed": bool((cnt == 2).all()), "open_edges": int((cnt == 1).sum()), "nonmanifold_edges": int((cnt > 2).sum())}

    def bodies(self):
        n = len(self.vertices)
        par = list(range(n))

        def find(i):
            while par[i] != i:
                par[i] = par[par[i]]
                i = par[i]
            return i

        for f in self.faces:
            for v in f[1:]:
                a, b = find(f[0]), find(v)
                if a != b:
                    par[a] = b
        roots = {}
        out = []
        for k, f in enumerate(self.faces):
            r = find(f[0])
            if r not in roots:
                roots[r] = len(out)
                out.append([])
            out[roots[r]].append(k)
        return out

    def summary(self):
        lo, hi = self.bbox()
        c = self.closed()
        groups = {}
        for g in self.group_names():
            groups[g] = {"faces": int(sum(1 for x in self.face_group if x == g)), "lines": int(sum(1 for x in self.line_group if x == g)), "hinge_edges": len(self.hinges.get(g, []))}
        return {
            "source": self.source,
            "kind": self.kind,
            "unit": "mm",
            "file_unit": self.unit,
            "counts": {"vertices": int(len(self.vertices)), "faces": len(self.faces), "lines": len(self.lines), "hinge_edges": int(sum(len(v) for v in self.hinges.values())), "bodies": len(self.bodies())},
            "bbox": [lo.round(6).tolist(), hi.round(6).tolist()],
            "closed": c["closed"],
            "open_edges": c["open_edges"],
            "nonmanifold_edges": c["nonmanifold_edges"],
            "groups": groups,
        }

    def to_view(self):
        tris, grp = self.triangles()
        names = self.group_names()
        gi = {g: i for i, g in enumerate(names)}
        return {
            "nodes": self.vertices.round(6).tolist(),
            "tris": tris.tolist(),
            "tri_group": [gi[g] for g in grp],
            "edges": self.feature_edges(),
            "lines": [list(e) for e in self.lines],
            "line_group": [gi[g] for g in self.line_group],
            "hinges": {k: [list(e) for e in v] for k, v in self.hinges.items()},
            "groups": names,
        }

    def to_dict(self):
        return {"vertices": self.vertices.tolist(), "faces": self.faces, "face_group": self.face_group, "lines": [list(e) for e in self.lines], "line_group": self.line_group, "hinges": {k: [list(e) for e in v] for k, v in self.hinges.items()}, "source": self.source, "kind": self.kind, "unit": self.unit}

    @staticmethod
    def from_dict(d):
        g = Geometry()
        g.vertices = np.array(d["vertices"], dtype=float).reshape(-1, 3)
        g.faces = [list(map(int, f)) for f in d["faces"]]
        g.face_group = list(d["face_group"])
        g.lines = [tuple(map(int, e)) for e in d.get("lines", [])]
        g.line_group = list(d.get("line_group", []))
        g.hinges = {k: [tuple(map(int, e)) for e in v] for k, v in d.get("hinges", {}).items()}
        g.source, g.kind, g.unit = d.get("source", ""), d.get("kind", "obj"), d.get("unit", "mm")
        return g


def _idx(tok, n):
    i = int(tok.split("/")[0])
    return i - 1 if i > 0 else n + i


def _weld(v, tol):
    key = np.round(v / tol).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = np.asarray(inv).reshape(-1)
    order = np.argsort(first)
    rank = np.empty(len(order), dtype=int)
    rank[order] = np.arange(len(order))
    return v[first[order]], rank[inv]


def _split_on_nodes(nodes, a, b, tol):
    pa, pb = nodes[a], nodes[b]
    d = pb - pa
    L = np.linalg.norm(d)
    if L == 0:
        return []
    t = (nodes - pa) @ d / (L * L)
    dist = np.linalg.norm(nodes - (pa + np.outer(t, d)), axis=1)
    on = np.where((dist < tol) & (t > -1e-9) & (t < 1 + 1e-9))[0]
    on = on[np.argsort(t[on])]
    return [(int(min(i, j)), int(max(i, j))) for i, j in zip(on[:-1], on[1:])]


def read_obj(text, name="model.obj", unit="mm"):
    s0 = UNIT_TO_MM[unit]
    verts, lines, faces = [], [], []
    group = "default"
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s[0] == "#":
            continue
        p = s.split()
        k = p[0]
        if k == "v" and len(p) >= 4:
            verts.append([float(p[1]), float(p[2]), float(p[3])])
        elif k in ("g", "o"):
            group = "_".join(p[1:]) if len(p) > 1 else "default"
        elif k == "l" and len(p) >= 3:
            ids = [_idx(t, len(verts)) for t in p[1:]]
            for a, b in zip(ids[:-1], ids[1:]):
                lines.append((a, b, group))
        elif k == "f" and len(p) >= 4:
            ids = [_idx(t, len(verts)) for t in p[1:]]
            if len(ids) <= 4:
                faces.append((ids, group))
            else:
                for i in range(1, len(ids) - 1):
                    faces.append(([ids[0], ids[i], ids[i + 1]], group))
    if not verts:
        raise ValueError("OBJ에 정점(v)이 없습니다")
    v = np.array(verts, dtype=float) * s0
    span = float(np.linalg.norm(v.max(axis=0) - v.min(axis=0))) or 1.0
    tol = span * 1e-6
    nodes, remap = _weld(v, tol)
    g = Geometry()
    g.vertices, g.source, g.kind, g.unit = nodes, name, "obj", unit
    hinge_lines, seen = [], set()
    for a, b, gr in lines:
        a, b = int(remap[a]), int(remap[b])
        if a == b:
            continue
        if gr.lower().startswith("hinge"):
            hinge_lines.append((a, b, gr))
            continue
        for e in _split_on_nodes(nodes, a, b, tol * 100):
            if e not in seen:
                seen.add(e)
                g.lines.append(e)
                g.line_group.append(gr)
    for ids, gr in faces:
        clean = []
        for i in (int(remap[i]) for i in ids):
            if i not in clean:
                clean.append(i)
        if len(clean) >= 3:
            g.faces.append(clean)
            g.face_group.append(gr)
    if hinge_lines:
        edges = g.edges()
        for a, b, gr in hinge_lines:
            for e in _split_on_nodes(nodes, a, b, tol * 100):
                if e in edges:
                    lst = g.hinges.setdefault(gr, [])
                    if e not in lst:
                        lst.append(e)
    if not g.faces and not g.lines:
        raise ValueError("OBJ에 선(l)이나 면(f) 요소가 없습니다")
    return _compact(g)


def _compact(g):
    used = set()
    for f in g.faces:
        used.update(f)
    for e in g.lines:
        used.update(e)
    if len(used) == len(g.vertices):
        return g
    keep = sorted(used)
    m = {o: n for n, o in enumerate(keep)}
    g.vertices = g.vertices[keep]
    g.faces = [[m[i] for i in f] for f in g.faces]
    g.lines = [(m[a], m[b]) for a, b in g.lines]
    g.hinges = {k: [(min(m[a], m[b]), max(m[a], m[b])) for a, b in v] for k, v in g.hinges.items()}
    return g


def stl_triangles(data):
    if len(data) >= 84:
        n = struct.unpack("<I", data[80:84])[0]
        if 84 + 50 * n == len(data):
            a = np.frombuffer(data, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]), count=n, offset=84)
            return a["v"].astype(float)
    vs = []
    for line in data.decode("utf-8", "ignore").splitlines():
        s = line.split()
        if len(s) == 4 and s[0] == "vertex":
            vs.append([float(s[1]), float(s[2]), float(s[3])])
    if len(vs) < 3 or len(vs) % 3:
        raise ValueError("STL 형식을 읽을 수 없습니다")
    return np.array(vs).reshape(-1, 3, 3)


def read_stl(data, name="model.stl", unit="mm"):
    tris = stl_triangles(data) * UNIT_TO_MM[unit]
    flat = tris.reshape(-1, 3)
    span = float(np.linalg.norm(flat.max(axis=0) - flat.min(axis=0))) or 1.0
    nodes, remap = _weld(flat, span * 1e-6)
    f = remap.reshape(-1, 3)
    f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
    g = Geometry()
    g.vertices, g.source, g.kind, g.unit = nodes, name, "stl", unit
    g.faces = f.tolist()
    g.face_group = ["default"] * len(g.faces)
    bodies = g.bodies()
    if len(bodies) > 1:
        for k, fs in enumerate(bodies):
            for i in fs:
                g.face_group[i] = f"body_{k + 1}"
    return _compact(g)


def load(name, data, unit="mm"):
    low = name.lower()
    if unit not in UNIT_TO_MM:
        raise ValueError(f"지원하는 파일 단위: {', '.join(UNIT_TO_MM)}")
    if low.endswith(".obj"):
        return read_obj(data.decode("utf-8", "ignore") if isinstance(data, bytes) else data, name, unit)
    if low.endswith(".stl"):
        return read_stl(data if isinstance(data, bytes) else data.encode(), name, unit)
    raise ValueError("지원 형식: .obj, .stl")


def write_stl(path, vertices, tris, name="simweb"):
    v = np.asarray(vertices, dtype=float)
    t = np.asarray(tris, dtype=int)
    p = v[t]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    rec = np.zeros(len(t), np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
    rec["n"], rec["v"] = n, p
    with open(path, "wb") as f:
        f.write(name.encode()[:80].ljust(80, b" "))
        f.write(struct.pack("<I", len(t)))
        f.write(rec.tobytes())


def box_mesh(lo, hi):
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    v = np.array([[hi[k] if (i >> k) & 1 else lo[k] for k in range(3)] for i in range(8)])
    q = [[0, 2, 3, 1], [4, 5, 7, 6], [0, 1, 5, 4], [2, 6, 7, 3], [0, 4, 6, 2], [1, 3, 7, 5]]
    t = []
    for a, b, c, d in q:
        t += [[a, b, c], [a, c, d]]
    return v, np.array(t)
