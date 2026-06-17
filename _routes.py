"""HTTP 路由注册。"""
import json, os
from pathlib import Path

from astrbot.api import logger
from ._paths import root, cur, arc
from ._mode import get_mode, set_mode
from ._archive import get_stats as archive_stats
from ._tokens import get_stats as token_stats
from . import _constants
from ._activity import log as log_activity

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dashboard():
    fp = os.path.join(_PLUGIN_DIR, "templates", "dashboard.html")
    with open(fp, "r", encoding="utf-8") as f:
        return f.read()


def _safe_path(base, *parts):
    """严格的路径安全检查：返回 Path 或 None。"""
    try:
        base = Path(base).resolve()
        target = base.joinpath(*parts).resolve()
        target.relative_to(base)
        return target
    except (ValueError, RuntimeError):
        return None


def register_routes(context):
    from quart import Response, jsonify, request as qr

    try:
        _DASHBOARD_HTML = _load_dashboard()
    except Exception as e:
        _DASHBOARD_HTML = "<h1>Dashboard Load Error</h1>"
        logger.warning(f"dashboard.html 加载失败，使用兜底页面: {e}")

    logger.info(f"[task_scaffold] data_root = {root()}")

    async def dashboard():
        return Response(_DASHBOARD_HTML, content_type="text/html; charset=utf-8")

    _last_no_state_logged = False

    async def api_current():
        nonlocal _last_no_state_logged
        sp = os.path.join(cur(), "00_task_state.json")
        if not os.path.isfile(sp):
            if not _last_no_state_logged:
                logger.debug("[task_scaffold] api_current: no active task")
                _last_no_state_logged = True
            return jsonify({"active": False})
        _last_no_state_logged = False
        with open(sp, "r", encoding="utf-8") as f:
            st = json.load(f)
        tds = st.get("todos", [])
        if not tds:
            return jsonify({"active": False})
        actual = [n for n in os.listdir(cur()) if os.path.isfile(os.path.join(cur(), n))]
        return jsonify({"active": True, "slug": st.get("slug"), "title": st.get("title", ""), "cwd": st.get("cwd", ""), "tags": st.get("tags", []),
                        "count": len(tds), "completed": sum(1 for t in tds if t.get("status") in ("completed", "cancelled")),
                        "todos": tds, "files": sorted(actual, key=lambda x: (
                            {"00_task_state.json":0,"03_work_order.md":1,"02_design.md":2,"01_research.md":3,"04_note.md":4,"progress.log":5}
                        ).get(x, 99))})

    async def api_current_file(name):
        fp = _safe_path(cur(), name)
        if not fp or not fp.is_file():
            return Response("file not found", status=404)
        content = fp.read_text(encoding="utf-8")
        return Response(content[:5000], content_type="text/plain; charset=utf-8")

    async def api_archives():
        from ._config import get as config_get
        items = []
        a = arc()
        limit = config_get("archive_list_limit", 50)
        if os.path.isdir(a):
            dirs = sorted([d for d in os.listdir(a) if os.path.isdir(os.path.join(a, d))], reverse=True)
            for d in dirs[:limit]:
                sp = os.path.join(a, d, "00_task_state.json")
                if os.path.isfile(sp):
                    with open(sp, "r", encoding="utf-8") as f:
                        st = json.load(f)
                    tds = st.get("todos", [])
                    comp = sum(1 for t in tds if t.get("status") in ("completed", "cancelled"))
                    completed_at = ""
                    lp = os.path.join(a, d, "progress.log")
                    if os.path.isfile(lp):
                        with open(lp, "r", encoding="utf-8") as f:
                            for line in f:
                                if "archived" in line and line.startswith("["):
                                    completed_at = line[1:20]
                    items.append({"slug": d, "completed_at": completed_at, "count": len(tds),
                                  "completed": comp, "tags": st.get("tags", []),
                                  "title": st.get("title", "") or (tds[0]["content"][:60] if tds else ""),
                                  "summary": tds[0]["content"][:60] if tds else ""})
        return jsonify(items[:50])

    async def api_archive_summary(slug):
        fp = _safe_path(arc(), slug, "00_task_state.json")
        if not fp or not fp.is_file():
            return jsonify({"ok": False, "error": "not found"})
        with open(fp, "r", encoding="utf-8") as f:
            st = json.load(f)
        arc_dir = _safe_path(arc(), slug)
        actual = [n for n in os.listdir(arc_dir) if os.path.isfile(os.path.join(arc_dir, n))]
        st["files"] = sorted(actual, key=lambda x: (
            {"00_task_state.json": 0, "03_work_order.md": 1, "02_design.md": 2, "01_research.md": 3, "04_note.md": 4, "progress.log": 5}
        ).get(x, 99))
        return jsonify(st)

    async def api_archive_file(slug, name):
        fp = _safe_path(arc(), slug, name)
        if not fp or not fp.is_file():
            return Response("file not found", status=404)
        content = fp.read_text(encoding="utf-8")
        return Response(content[:5000], content_type="text/plain; charset=utf-8")

    async def api_activity():
        fp = os.path.join(root(), "state", "activity.jsonl")
        if not os.path.isfile(fp):
            return jsonify([])
        lines = []
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        lines.append(json.loads(line))
                    except Exception:
                        pass
        return jsonify(lines[-20:])

    async def api_mode_get():
        return jsonify({"mode": get_mode()})

    async def api_stats():
        return jsonify(archive_stats())

    async def api_status():
        return jsonify({
            "provider": _constants._LLM_PROVIDER or "—",
            "tokens": token_stats(),
        })

    async def api_ping():
        return jsonify({"ok": True})

    async def api_mode_set():
        try:
            body = await qr.get_json()
            m = body.get("mode", "") if body else ""
        except Exception:
            m = ""
        if m not in ("plan", "build"):
            return jsonify({"ok": False, "error": "mode 必须是 plan 或 build"})
        set_mode(m)
        await log_activity("System", "系统", f"模式切换 \u2192 {m}")
        return jsonify({"ok": True, "mode": m})

    _ROUTES = [
        ("/task_scaffold/dashboard", dashboard, ["GET"], "任务工作台 HTML"),
        ("/task_scaffold/api/current", api_current, ["GET"], "当前任务 JSON"),
        ("/task_scaffold/api/current/file/<name>", api_current_file, ["GET"], "当前任务文件内容"),
        ("/task_scaffold/api/archives", api_archives, ["GET"], "归档列表 JSON"),
        ("/task_scaffold/api/activity", api_activity, ["GET"], "实时活动 JSONL"),
        ("/task_scaffold/api/mode", api_mode_get, ["GET"], "当前模式 JSON"),
        ("/task_scaffold/api/mode", api_mode_set, ["POST"], "切换模式"),
        ("/task_scaffold/api/archive/<slug>/summary", api_archive_summary, ["GET"], "归档摘要 JSON"),
        ("/task_scaffold/api/archive/<slug>/file/<name>", api_archive_file, ["GET"], "归档文件内容"),
        ("/task_scaffold/api/stats", api_stats, ["GET"], "统计 JSON"),
        ("/task_scaffold/api/status", api_status, ["GET"], "运行状态 JSON"),
        ("/task_scaffold/api/ping", api_ping, ["GET"], "心跳检测"),
    ]

    for path, handler, methods, desc in _ROUTES:
        context.register_web_api(path, handler, methods, desc)

    logger.info(f"WebUI 路由已注册: {' | '.join(p for p,_,_,_ in _ROUTES)}")
