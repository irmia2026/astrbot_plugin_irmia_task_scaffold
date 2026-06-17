"""路径工具、持久化状态读写。"""
import json, os, re

from . import _constants

_ROOT_CACHE = None
_ROOT_OVERRIDE = None

# 文件名/目录名安全检查：拒绝路径分隔符、父目录引用、Windows 保留字符、控制字符
_INVALID_NAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]|^\.\.?$')


def set_root(path: str):
    """由 Main 在初始化时根据插件配置覆盖数据根目录。"""
    global _ROOT_OVERRIDE, _ROOT_CACHE
    if path and isinstance(path, str):
        path = os.path.expanduser(path)
        if path:
            _ROOT_OVERRIDE = path
            _ROOT_CACHE = path


def safe_name(name: str) -> bool:
    """校验 slug/file/dirname 是否只包含合法文件名字符。"""
    return bool(name) and isinstance(name, str) and not _INVALID_NAME_RE.search(name)


def root():
    global _ROOT_CACHE
    if _ROOT_CACHE is None:
        env = os.environ.get("IRMIA_TASK_SCAFFOLD_DATA_ROOT", "")
        if env:
            _ROOT_CACHE = os.path.expanduser(env)
        else:
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
