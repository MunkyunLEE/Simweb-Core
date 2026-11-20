import time

HOOK = {"fn": None, "last": 0.0, "ctx": ""}


def set_hook(fn):
    HOOK["fn"] = fn
    HOOK["last"] = 0.0
    HOOK["ctx"] = ""


def context(text):
    HOOK["ctx"] = text
    stage(text, force=True)


def stage(text, force=False):
    fn = HOOK["fn"]
    if fn is None:
        return
    now = time.time()
    if not force and now - HOOK["last"] < 0.25:
        return
    HOOK["last"] = now
    try:
        fn(text)
    except Exception:
        pass


def detail(text):
    stage((HOOK["ctx"] + " · " if HOOK["ctx"] else "") + text)
