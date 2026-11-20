import copy
import json
import os
import threading


from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import geometry, llm, progress

CORE_WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def fail(msg, code=400):
    raise HTTPException(status_code=code, detail=str(msg))


class Ops(BaseModel):
    ops: list


class Chat(BaseModel):
    text: str


class LLMCfg(BaseModel):
    url: str | None = None
    model: str | None = None
    key: str | None = None
    mode: str | None = None


class SpecIn(BaseModel):
    spec: dict


def create_app(plugin):
    app = FastAPI(title=plugin.title)
    lock = threading.Lock()
    S = {"geom": None, "spec": plugin.default_spec(None), "result": None, "stale": False, "chat": [], "llm": llm.defaults(), "undo": [], "progress": ""}
    progress.set_hook(lambda t: S.__setitem__("progress", t))
    app.state.S = S
    app.state.lock = lock
    app.state.plugin = plugin

    def llm_public():
        c = S["llm"]
        return {"url": c["url"], "model": c["model"], "mode": c["mode"], "has_key": bool(c.get("key"))}

    def state(view=True):
        g = S["geom"]
        out = {
            "app": {"name": plugin.name, "title": plugin.title, "version": getattr(plugin, "version", "")},
            "model": g.summary() if g is not None else None,
            "spec": S["spec"],
            "warnings": plugin.warnings(S["spec"], g),
            "can_undo": bool(S["undo"]),
            "stale": S["stale"],
            "llm": llm_public(),
            "tools": plugin.tools() if hasattr(plugin, "tools") else {},
        }
        if view and g is not None:
            out["view"] = g.to_view()
        out.update(plugin.state(S))
        return out

    def set_geom(g, spec=None):
        S["geom"] = g
        S["spec"] = spec if spec is not None else plugin.default_spec(g)
        S["undo"], S["result"], S["stale"], S["chat"] = [], None, False, []

    def apply(ops):
        spec, log = plugin.apply_ops(copy.deepcopy(S["spec"]), ops, S["geom"])
        S["undo"].append(S["spec"])
        del S["undo"][:-30]
        S["spec"] = spec
        S["stale"] = S["result"] is not None
        return log

    def check(ops):
        plugin.apply_ops(copy.deepcopy(S["spec"]), ops, S["geom"])

    @app.get("/api/state")
    def get_state():
        with lock:
            return state()

    @app.get("/api/progress")
    def get_progress():
        return {"text": S["progress"]}

    @app.get("/api/examples")
    def examples():
        return [{k: e[k] for k in ("name", "title", "note", "prompts") if k in e} for e in plugin.examples()]

    @app.post("/api/examples/{name}")
    def load_example(name: str, preset: int = 1):
        ex = {e["name"]: e for e in plugin.examples()}.get(name)
        if ex is None:
            fail("예제가 없습니다", 404)
        with lock:
            try:
                g = None
                if ex.get("file"):
                    path = os.path.join(plugin.examples_dir, ex["file"])
                    g = geometry.load(ex["file"], open(path, "rb").read(), ex.get("unit", "mm"))
                ops = ex.get("ops", []) if preset else [o for o in ex.get("ops", []) if o.get("op", "").startswith("set_")]
                spec, _ = plugin.apply_ops(plugin.default_spec(g), ops, g)
                set_geom(g, spec)
                return state()
            except HTTPException:
                raise
            except Exception as e:
                fail(e)

    @app.post("/api/upload")
    def upload(file: UploadFile = File(...), unit: str = Form("mm")):
        data = file.file.read()
        with lock:
            try:
                g = plugin.load_geometry(file.filename or "model", data, unit) if hasattr(plugin, "load_geometry") else geometry.load(file.filename or "model", data, unit)
                spec = plugin.on_geometry(copy.deepcopy(S["spec"]), g) if hasattr(plugin, "on_geometry") else plugin.default_spec(g)
                set_geom(g, spec)
                return state()
            except HTTPException:
                raise
            except Exception as e:
                fail(e)

    @app.post("/api/ops")
    def post_ops(body: Ops):
        with lock:
            try:
                log = apply(body.ops)
            except Exception as e:
                fail(e)
            out = state()
            out["log"] = log
            return out

    def ask(cfg, text):
        ctx = plugin.llm_context(S["geom"], S["spec"], S["result"])
        ops, reply = llm.ask_llm(cfg, plugin.llm_system, text, ctx, S["chat"])
        try:
            check(ops)
        except Exception as e:
            ops, reply = llm.ask_llm(cfg, plugin.llm_system, text, ctx, S["chat"], error=str(e))
        return ops, reply

    @app.post("/api/chat")
    def chat(body: Chat):
        with lock:
            cfg = S["llm"]
            text = body.text.strip()
            if not text:
                fail("내용이 비어 있습니다")
            mode = cfg["mode"] if llm.configured(cfg) else "rule"
            engine, note, action, error, log = "rule", "", None, None, []
            rops, rreply, info = plugin.rules(text, S["geom"], S["spec"])
            rule_ok = info.get("complete", False)
            if rule_ok and rops:
                try:
                    check(rops)
                except Exception as e:
                    rule_ok = False
                    rreply += f" (적용 검사 실패: {e})"
            direct = rule_ok or (info.get("ask") and not info.get("unknown")) or info.get("answered")
            use_llm = mode in ("auto", "llm") or (mode == "rule_first" and not direct)
            ops, reply = rops, rreply
            if use_llm:
                try:
                    ops, reply = ask(cfg, text)
                    engine = "llm"
                except llm.Cancelled:
                    fail("LLM 요청을 중단했습니다", 409)
                except Exception as e:
                    if mode == "llm":
                        fail(f"LLM 호출 실패: {e}")
                    note = f"LLM에 연결하지 못해 규칙 기반 해석 결과를 사용했습니다 ({str(e)[:120]})"
                    ops, reply = rops, rreply
            elif mode == "rule_first":
                note = "규칙으로 바로 처리했습니다" if rule_ok else ""
            elif not llm.configured(cfg) and info.get("unknown"):
                note = "LLM 이 연결되지 않아 규칙으로 이해한 부분만 처리했습니다. 오른쪽 위 LLM 칸에 엔드포인트·모델·API 키를 넣으면 나머지도 처리합니다"
            if engine == "rule" and info.get("undo"):
                if S["undo"]:
                    S["spec"] = S["undo"].pop()
                    S["stale"] = S["result"] is not None
                    reply = "직전 상태로 되돌렸습니다."
                else:
                    reply = "되돌릴 내용이 없습니다."
                ops = []
            elif ops:
                try:
                    log = apply(ops)
                except Exception as e:
                    error = str(e)
            if engine == "rule" and info.get("action") and not error and not info.get("ask") and not info.get("unknown"):
                action = info["action"]
            S["chat"].append({"role": "user", "content": text})
            S["chat"].append({"role": "assistant", "content": json.dumps({"ops": ops, "reply": reply}, ensure_ascii=False)})
            del S["chat"][:-12]
            out = state()
            out["chat"] = {"reply": reply, "ops": ops, "engine": engine, "model": cfg["model"] if engine == "llm" else None, "provider": llm.provider(cfg["url"]) if engine == "llm" else None, "note": note, "error": error, "log": log, "action": action}
            return out

    @app.post("/api/undo")
    def undo():
        with lock:
            if not S["undo"]:
                fail("되돌릴 내용이 없습니다")
            S["spec"] = S["undo"].pop()
            S["stale"] = S["result"] is not None
            return state()

    @app.post("/api/cancel/llm")
    def cancel_llm():
        return {"cancelled": llm.cancel()}

    @app.post("/api/llm")
    def set_llm(body: LLMCfg):
        with lock:
            for k in ("url", "model", "key", "mode"):
                v = getattr(body, k)
                if v is not None:
                    S["llm"][k] = v.strip()
            if S["llm"]["mode"] not in ("rule_first", "auto", "llm", "rule"):
                S["llm"]["mode"] = "rule_first"
            return {"llm": llm_public(), "status": llm.llm_status(S["llm"])}

    @app.post("/api/llm/test")
    def test_llm():
        return {"llm": llm_public(), "provider": llm.provider(S["llm"]["url"]), "test": llm.test_llm(dict(S["llm"]))}

    @app.get("/api/llm")
    def get_llm():
        return {"llm": llm_public(), "status": llm.llm_status(S["llm"])}

    @app.get("/api/export/spec")
    def export_spec():
        with lock:
            return JSONResponse(S["spec"], headers={"Content-Disposition": f"attachment; filename={plugin.name}_case.json"})

    @app.post("/api/import/spec")
    def import_spec(body: SpecIn):
        with lock:
            try:
                spec, _ = plugin.apply_ops(plugin.default_spec(S["geom"]), [{"op": "replace_spec", "spec": body.spec}], S["geom"])
            except Exception as e:
                fail(e)
            S["undo"].append(S["spec"])
            S["spec"], S["result"] = spec, None
            return state()

    @app.get("/api/geometry")
    def get_geometry():
        with lock:
            if S["geom"] is None:
                fail("불러온 지오메트리가 없습니다", 404)
            return S["geom"].to_dict()

    if hasattr(plugin, "routes"):
        plugin.routes(app, S, lock, state, fail)

    @app.get("/")
    def index():
        return FileResponse(os.path.join(plugin.web_dir, "index.html"), headers={"Cache-Control": "no-store"})

    app.mount("/core", StaticFiles(directory=CORE_WEB), name="core")
    if getattr(plugin, "examples_dir", None) and os.path.isdir(plugin.examples_dir):
        app.mount("/examples", StaticFiles(directory=plugin.examples_dir), name="examples")
    app.mount("/", StaticFiles(directory=plugin.web_dir), name="web")
    return app


def run(prog, app_path, port, argv=None):
    import argparse
    import webbrowser

    import uvicorn

    p = argparse.ArgumentParser(prog=prog)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=port)
    p.add_argument("--no-browser", action="store_true")
    a = p.parse_args(argv)
    url = f"http://{a.host}:{a.port}"
    print(f"{prog}: {url}")
    if not a.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app_path, host=a.host, port=a.port, log_level="warning")


