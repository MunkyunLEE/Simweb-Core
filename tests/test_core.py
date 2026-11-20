import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest
from fastapi.testclient import TestClient

from simweb import app as sapp
from simweb import geometry, llm, select, units

OBJ = """v 0 0 0
v 100 0 0
v 100 100 0
v 0 100 0
v 200 0 0
v 200 100 0
g panel_a
f 1 2 3 4
g panel_b
f 2 5 6 3
g hinge_1
l 2 3
"""


def test_obj_groups_and_hinge():
    g = geometry.read_obj(OBJ)
    assert len(g.vertices) == 6
    assert sorted(g.group_names()) == ["hinge_1", "panel_a", "panel_b"]
    assert g.hinges["hinge_1"] == [(1, 2)]
    assert not g.closed()["closed"]


def test_obj_unit_scale():
    g = geometry.read_obj(OBJ, unit="m")
    assert np.isclose(g.bbox()[1][0], 200000.0)


def test_stl_roundtrip_box(tmp_path):
    v, t = geometry.box_mesh([0, 0, 0], [10, 20, 30])
    p = tmp_path / "b.stl"
    geometry.write_stl(p, v, t)
    g = geometry.read_stl(p.read_bytes())
    s = g.summary()
    assert s["closed"] and s["counts"]["vertices"] == 8 and s["counts"]["faces"] == 12
    tri = g.vertices[np.array(g.faces)]
    vol = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6
    assert np.isclose(abs(vol), 6000.0)
    assert vol > 0


def test_stl_two_bodies(tmp_path):
    v1, t1 = geometry.box_mesh([0, 0, 0], [1, 1, 1])
    v2, t2 = geometry.box_mesh([5, 0, 0], [6, 1, 1])
    p = tmp_path / "two.stl"
    geometry.write_stl(p, np.vstack([v1, v2]), np.vstack([t1, t2 + 8]))
    g = geometry.read_stl(p.read_bytes())
    assert sorted(g.group_names()) == ["body_1", "body_2"]


def test_dict_roundtrip():
    g = geometry.read_obj(OBJ)
    h = geometry.Geometry.from_dict(json.loads(json.dumps(g.to_dict())))
    assert h.summary() == g.summary()


def test_select():
    g = geometry.read_obj(OBJ)
    p = g.vertices
    assert select.resolve(p, {"plane": {"axis": "x", "at": "max"}}).tolist() == [4, 5]
    assert select.resolve(p, {"group": "hinge_1"}, g).tolist() == [1, 2]
    assert select.resolve(p, {"and": [{"box": {"min": [0, 0, 0], "max": [100, 50, 0]}}, {"plane": {"axis": "y", "at": "min"}}]}).tolist() == [0, 1]
    with pytest.raises(ValueError):
        select.resolve(p, {"group": "nope"}, g)


def test_units():
    assert units.to_internal(1000, "kg/m3", "density")[0] == pytest.approx(1e-9)
    assert units.to_internal(2, "m/s")[0] == pytest.approx(2000)
    assert units.to_internal(1e-3, "Pa·s", "dynamic_viscosity")[0] == pytest.approx(1e-9)
    assert units.find("입자 간격 5 mm, 높이 0.4 m", "length") == [5.0, 400.0]
    rho, g, h = 1e-9, units.G, 1000.0
    assert units.to_si(rho * g * h, "stress") == pytest.approx(1000 * 9.81 * 1.0)


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"data": [{"id": "mock-1"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        req = json.loads(self.rfile.read(n))
        Mock.last = req
        txt = json.dumps({"ops": [{"op": "set_value", "value": 7}], "reply": "값을 7로 바꿨습니다"}, ensure_ascii=False)
        body = json.dumps({"model": req["model"], "choices": [{"message": {"content": txt}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def mock_llm():
    srv = HTTPServer(("127.0.0.1", 0), Mock)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield f"http://127.0.0.1:{srv.server_port}/v1"
    srv.shutdown()


class Plugin:
    name = "demo"
    title = "demo"
    llm_system = "SYSTEM-DEMO"

    def __init__(self, tmp):
        self.web_dir = str(tmp)
        (tmp / "index.html").write_text("<html>demo</html>")

    def default_spec(self, g):
        return {"value": 0}

    def apply_ops(self, spec, ops, g):
        log = []
        for o in ops:
            if o["op"] == "set_value":
                spec["value"] = int(o["value"])
                log.append(f"value={spec['value']}")
            elif o["op"] == "replace_spec":
                spec = dict(o["spec"])
            else:
                raise ValueError(f"모르는 수정 지시: {o['op']}")
        return spec, log

    def warnings(self, spec, g):
        return []

    def rules(self, text, g, spec):
        if text.startswith("값 "):
            return [{"op": "set_value", "value": int(text.split()[1])}], "값을 바꿨습니다", {"complete": True}
        return [], "", {"complete": False, "unknown": [text]}

    def llm_context(self, g, spec, result):
        return "SPEC: " + json.dumps(spec)

    def state(self, S):
        return {}

    def examples(self):
        return []


def test_app_rules_llm_undo(tmp_path, mock_llm):
    c = TestClient(sapp.create_app(Plugin(tmp_path)))
    assert c.get("/").status_code == 200
    assert c.get("/core/js/viewer.js").status_code == 200
    r = c.post("/api/chat", json={"text": "값 3"}).json()
    assert r["spec"]["value"] == 3 and r["chat"]["engine"] == "rule"
    r = c.post("/api/chat", json={"text": "어려운 문장"}).json()
    assert r["spec"]["value"] == 3 and r["chat"]["engine"] == "rule"
    st = c.post("/api/llm", json={"url": mock_llm, "model": "mock-1", "key": "k", "mode": "rule_first"}).json()
    assert st["status"]["ok"] and st["status"]["has_model"]
    r = c.post("/api/chat", json={"text": "어려운 문장"}).json()
    assert r["chat"]["engine"] == "llm" and r["spec"]["value"] == 7
    assert Mock.last["messages"][0]["content"] == "SYSTEM-DEMO"
    assert c.post("/api/llm/test").json()["test"]["ok"]
    r = c.post("/api/undo").json()
    assert r["spec"]["value"] == 3
    with pytest.raises(Exception):
        llm.ask_llm({"url": "http://127.0.0.1:9/v1", "model": "x"}, "s", "t", "c")


def test_upload(tmp_path):
    c = TestClient(sapp.create_app(Plugin(tmp_path)))
    r = c.post("/api/upload", files={"file": ("p.obj", OBJ.encode())}, data={"unit": "mm"}).json()
    assert r["model"]["counts"]["faces"] == 2 and len(r["view"]["tris"]) == 4
    assert c.post("/api/upload", files={"file": ("p.txt", b"x")}).status_code == 400
