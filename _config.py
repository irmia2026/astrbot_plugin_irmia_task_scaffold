"""配置加载。从 config.yaml 读取，缺失时使用默认值。"""
import os

try:
    import yaml
    _has_yaml = True
except ImportError:
    _has_yaml = False

_DEFAULTS = {
    "data_root": "",
    "context_limit": 200000,
    "activity_max_lines": 200,
    "summary_max_lines": 100,
    "tokens_max_lines": 500,
    "recent_summary_count": 5,
    "archive_list_limit": 50,
    "extra_write_keywords": [],
    "extra_exempt_tools": [],
}

_cfg = None


def _load():
    global _cfg
    if _cfg is not None:
        return
    from ._paths import root as data_root_func
    d = dict(_DEFAULTS)
    fp = os.path.join(data_root_func(), "config.yaml")
    if not os.path.isfile(fp):
        fp = os.path.join(data_root_func(), "config.json")
    if os.path.isfile(fp):
        try:
            import json
            with open(fp, "r", encoding="utf-8") as f:
                if fp.endswith(".yaml"):
                    if _has_yaml:
                        user = yaml.safe_load(f) or {}
                    else:
                        user = {}
                else:
                    user = json.load(f)
            d.update({k: v for k, v in user.items() if k in d})
        except Exception:
            pass
    _cfg = d


def get(key, default=None):
    _load()
    return _cfg.get(key, _DEFAULTS.get(key, default))
