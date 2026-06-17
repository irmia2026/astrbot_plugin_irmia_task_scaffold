"""路径工具、持久化状态读写。"""
import json, os

from . import _constants

_ROOT_CACHE = None


def root():
    global _ROOT_CACHE
    if _ROOT_CACHE is None:
        _ROOT_CACHE = os.path.join(os.path.expanduser("~"), ".astrbot", "data", "task_scaffolds")
    return _ROOT_CACHE


def cur():
    return os.path.join(root(), "current")


def arc():
    return os.path.join(root(), "archive")


def mode_path():
    return os.path.join(root(), "state", "mode.json")


def load_persisted():
    fp = os.path.join(root(), "state", "context.json")
    try:
        if os.path.isfile(fp):
            with open(fp, "r", encoding="utf-8") as f:
                d = json.load(f)
            _constants._LAST_CTX_SIZE = d.get("ctx", 0)
            if d.get("limit", 0) > 0:
                _constants._CONTEXT_LIMIT = d["limit"]
            if d.get("provider"):
                _constants._LLM_PROVIDER = d["provider"]
    except Exception:
        pass


def save_persisted():
    fp = os.path.join(root(), "state", "context.json")
    sd = os.path.dirname(fp)
    os.makedirs(sd, exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump({"ctx": _constants._LAST_CTX_SIZE, "limit": _constants._CONTEXT_LIMIT, "provider": _constants._LLM_PROVIDER}, f, ensure_ascii=False)
