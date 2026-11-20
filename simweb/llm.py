import http.client
import json
import os
import re
import base64
import socket
import ssl
import threading
import urllib.parse
import urllib.request


class Cancelled(Exception):
    pass


ACTIVE = {"conn": None, "cancelled": False}
_alock = threading.Lock()


def cancel():
    with _alock:
        ACTIVE["cancelled"] = True
        c = ACTIVE["conn"]
    if c is not None:
        try:
            c.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            c.close()
        except Exception:
            pass
    return c is not None


def ssl_context():
    ca = env("CA_BUNDLE") or os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE") or None
    return ssl.create_default_context(cafile=ca)


def _proxy(u):
    if not u.hostname or u.hostname in ("localhost", "127.0.0.1", "::1") or urllib.request.proxy_bypass(u.hostname):
        return None
    px = urllib.request.getproxies().get(u.scheme)
    if not px:
        return None
    return urllib.parse.urlsplit(px if "://" in px else "http://" + px)


def _connect(url, timeout):
    u = urllib.parse.urlsplit(url)
    https = u.scheme == "https"
    port = u.port or (443 if https else 80)
    path = u.path + ("?" + u.query if u.query else "")
    p = _proxy(u)
    if p is None:
        if https:
            return http.client.HTTPSConnection(u.hostname, port, timeout=timeout, context=ssl_context()), path, {}
        return http.client.HTTPConnection(u.hostname, port, timeout=timeout), path, {}
    auth = {}
    if p.username:
        tok = base64.b64encode(f"{urllib.parse.unquote(p.username)}:{urllib.parse.unquote(p.password or '')}".encode()).decode()
        auth = {"Proxy-Authorization": "Basic " + tok}
    if https:
        c = http.client.HTTPSConnection(p.hostname, p.port or 8080, timeout=timeout, context=ssl_context())
        c.set_tunnel(u.hostname, port, headers=auth)
        return c, path, {}
    return http.client.HTTPConnection(p.hostname, p.port or 8080, timeout=timeout), url, auth


def _post(url, body, headers, timeout):
    c, path, extra = _connect(url, timeout)
    headers = {**headers, **extra}
    with _alock:
        if ACTIVE["cancelled"]:
            raise Cancelled()
        ACTIVE["conn"] = c
    try:
        c.request("POST", path, body=json.dumps(body).encode("utf-8"), headers=headers)
        r = c.getresponse()
        data = r.read()
        if r.status >= 400:
            raise RuntimeError(f"HTTP {r.status}: {data[:200].decode('utf-8', 'replace')}")
        return json.loads(data)
    except Exception as e:
        if ACTIVE["cancelled"]:
            raise Cancelled() from e
        raise
    finally:
        with _alock:
            ACTIVE["conn"] = None
        try:
            c.close()
        except Exception:
            pass

PREFIXES = ["SIMWEB"]


def env(name, default=""):
    for p in PREFIXES:
        v = os.environ.get(f"{p}_{name}")
        if v:
            return v
    return default


def defaults():
    url = env("LLM_URL")
    return {"url": url, "model": env("LLM_MODEL"), "key": env("LLM_KEY"), "mode": env("LLM_MODE", "rule_first" if url else "rule")}


def configured(cfg):
    return bool(str(cfg.get("url") or "").strip()) and bool(str(cfg.get("model") or "").strip())


def _extract(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    a, b = text.find("{"), text.rfind("}")
    if a >= 0 and b > a:
        return json.loads(text[a : b + 1])
    raise ValueError("LLM 응답에서 JSON을 찾지 못했습니다")


def ask_llm(cfg, system, text, ctx, history=None, error=None):
    with _alock:
        ACTIVE["cancelled"] = False
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": ctx}]
    for h in (history or [])[-6:]:
        msgs.append({"role": h["role"], "content": h["content"]})
    nothink = env("LLM_NOTHINK", "0") == "1"
    msgs.append({"role": "user", "content": text + (" /no_think" if nothink else "")})
    if error:
        msgs.append({"role": "user", "content": f"The previous ops failed validation: {error}\nReturn corrected JSON."})
    headers = {"Content-Type": "application/json"}
    if cfg.get("key"):
        headers["Authorization"] = "Bearer " + cfg["key"]
    body = {"model": cfg["model"], "messages": msgs, "temperature": 0, "stream": False, "response_format": {"type": "json_object"}}
    resp = _post(cfg["url"].rstrip("/") + "/chat/completions", body, headers, 900)
    data = _extract(resp["choices"][0]["message"]["content"])
    ops = data.get("ops", [])
    if not isinstance(ops, list):
        raise ValueError("ops 가 배열이 아닙니다")
    return ops, str(data.get("reply", ""))


def provider(url):
    u = urllib.parse.urlsplit(url or "")
    h = (u.hostname or "").lower()
    if not h:
        return "미설정"
    if h in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        if u.port == 11434:
            return "Ollama (이 컴퓨터)"
        if u.port == 1234:
            return "LM Studio (이 컴퓨터)"
        return "로컬 서버 (이 컴퓨터)"
    names = {
        "generativelanguage.googleapis.com": "Google Gemini API (클라우드)",
        "api.openai.com": "OpenAI API (클라우드)",
        "api.anthropic.com": "Anthropic API (클라우드)",
        "openrouter.ai": "OpenRouter (클라우드)",
    }
    return names.get(h, f"외부 서버 {h}")


def _norm(name):
    return str(name).split("/", 1)[1] if str(name).startswith("models/") else str(name)


def llm_status(cfg):
    import time

    import httpx

    u = urllib.parse.urlsplit(cfg["url"])
    base = {"provider": provider(cfg["url"]), "host": (u.hostname or "") + (f":{u.port}" if u.port else ""), "key_set": bool(cfg.get("key"))}
    if not configured(cfg):
        return {**base, "ok": False, "error": "LLM 이 설정되지 않았습니다 (엔드포인트와 모델 이름을 넣으면 연결합니다)", "models": []}
    try:
        t = time.time()
        r = httpx.get(cfg["url"].rstrip("/") + "/models", timeout=4, verify=ssl_context(), headers={"Authorization": "Bearer " + cfg["key"]} if cfg.get("key") else {})
        ms = round((time.time() - t) * 1000)
        r.raise_for_status()
        names = [_norm(m.get("id")) for m in r.json().get("data", [])]
        return {**base, "ok": True, "ms": ms, "models": names, "has_model": _norm(cfg["model"]) in names}
    except Exception as e:
        return {**base, "ok": False, "error": str(e)[:200], "models": []}


def test_llm(cfg):
    import time

    if not configured(cfg):
        return {"ok": False, "error": "LLM 이 설정되지 않았습니다"}
    nothink = env("LLM_NOTHINK", "0") == "1"
    msgs = [
        {"role": "system", "content": 'Reply with ONE JSON object only: {"ops": [], "reply": "<short Korean greeting>"}'},
        {"role": "user", "content": "안녕" + (" /no_think" if nothink else "")},
    ]
    headers = {"Content-Type": "application/json"}
    if cfg.get("key"):
        headers["Authorization"] = "Bearer " + cfg["key"]
    body = {"model": cfg["model"], "messages": msgs, "temperature": 0, "stream": False, "response_format": {"type": "json_object"}}
    with _alock:
        ACTIVE["cancelled"] = False
    t = time.time()
    try:
        resp = _post(cfg["url"].rstrip("/") + "/chat/completions", body, headers, 300)
        text = resp["choices"][0]["message"]["content"]
        try:
            data = _extract(text)
            json_ok = True
            reply = str(data.get("reply", ""))
        except Exception:
            json_ok = False
            reply = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
        return {"ok": True, "ms": round((time.time() - t) * 1000), "model": resp.get("model"), "json_ok": json_ok, "reply": reply[:160]}
    except Cancelled:
        return {"ok": False, "error": "중단했습니다"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
