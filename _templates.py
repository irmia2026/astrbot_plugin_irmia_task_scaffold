"""任务模板管理。"""
import json, os

from ._constants import _BUILTIN_TEMPLATES
from ._paths import root
from ._state import err

_TEMPLATE_DIR = None


def tmpl_dir():
    global _TEMPLATE_DIR
    if _TEMPLATE_DIR is None:
        _TEMPLATE_DIR = os.path.join(root(), "templates")
    return _TEMPLATE_DIR


def list_templates():
    td = tmpl_dir()
    if not os.path.isdir(td):
        return json.dumps({"ok": True, "templates": [], "hint": "无自定义模板，使用预置模板: feature_impl, bug_fix, code_review"}, ensure_ascii=False)
    items = sorted([f for f in os.listdir(td) if f.endswith(".json")])
    return json.dumps({"ok": True, "templates": [i.rsplit(".", 1)[0] for i in items]}, ensure_ascii=False)


def load_template(name: str):
    if not name:
        return err("load_template 需要 template 参数")
    td = tmpl_dir()
    from pathlib import Path
    base = Path(td).resolve()
    try:
        fp = (base / f"{name}.json").resolve()
        fp.relative_to(base)
    except (ValueError, RuntimeError):
        return err(f"模板名不合法: {name}")
    if os.path.isfile(fp):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            return json.dumps({"ok": True, "template": name, "source": "custom",
                               "title": data.get("title", ""),
                               "todos": data.get("todos", [])}, ensure_ascii=False)
        except Exception as e:
            return err(f"模板解析失败: {e}")
    if name in _BUILTIN_TEMPLATES:
        tmpl = _BUILTIN_TEMPLATES[name]
        return json.dumps({"ok": True, "template": name, "source": "builtin",
                           "title": tmpl["title"],
                           "todos": tmpl["todos"]}, ensure_ascii=False)
    return err(f"模板不存在: {name}（可用: {', '.join(_BUILTIN_TEMPLATES)}）")
