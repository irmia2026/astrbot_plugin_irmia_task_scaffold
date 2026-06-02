import json, os, shutil
import atexit
from dataclasses import dataclass, field
from datetime import datetime

from astrbot.api import FunctionTool as _FT, logger, star
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.star.register import register_on_llm_request

_VS = {"pending", "in_progress", "completed", "cancelled"}

_PLAN_DISABLED_TOOLS = (
    "safe_edit", "file_patch", "file_write", "file_remove",
    "git_commit", "git_push", "safe_rollback",
    "file_zip", "file_unzip",
    "future_task",
    "astrbot_execute_shell", "astrbot_execute_python",
)

_RT = "# 调研\n\n*（在此记录参考来源、竞品分析、技术决策依据）*\n\n## 参考来源\n- \n\n## 技术对比\n- \n\n## 决策记录\n- \n"
_DT = "# 设计\n\n*（在此记录架构决策、接口定义、数据流图）*\n\n## 架构决策\n- \n\n## 接口定义\n- \n\n## 数据流\n- \n"


_ROOT_CACHE = None

def _root():
    global _ROOT_CACHE
    if _ROOT_CACHE is None:
        _ROOT_CACHE = os.path.join(os.path.expanduser("~"), ".astrbot", "data", "task_scaffolds")
    return _ROOT_CACHE


def _cur():
    return os.path.join(_root(), "current")


def _arc():
    return os.path.join(_root(), "archive")


def _mode_path():
    return os.path.join(_root(), "state", "mode.json")


_MODE_CACHE = ("build", 0.0)

def _get_mode():
    global _MODE_CACHE
    mp = _mode_path()
    try:
        mtime = os.path.getmtime(mp)
        if mtime == _MODE_CACHE[1]:
            return _MODE_CACHE[0]
        if os.path.isfile(mp):
            with open(mp, "r", encoding="utf-8") as f:
                mode = json.load(f).get("mode", "build")
            _MODE_CACHE = (mode, mtime)
            return mode
    except OSError:
        pass
    return _MODE_CACHE[0]


_LAST_APPLIED_MODE = None


def _switch_to_plan(ctx):
    for name in _PLAN_DISABLED_TOOLS:
        try:
            ctx.deactivate_llm_tool(name)
        except Exception as e:
            logger.debug(f"停用 {name} 失败: {e}")
    logger.info(f"plan 模式：已停用 {len(_PLAN_DISABLED_TOOLS)} 个写工具")


def _switch_to_build(ctx):
    for name in _PLAN_DISABLED_TOOLS:
        try:
            ctx.activate_llm_tool(name)
        except Exception as e:
            logger.debug(f"激活 {name} 失败: {e}")
    logger.info(f"build 模式：已激活 {len(_PLAN_DISABLED_TOOLS)} 个写工具")


def _set_mode(mode: str, context=None):
    os.makedirs(os.path.dirname(_mode_path()), exist_ok=True)
    with open(_mode_path(), "w", encoding="utf-8") as f:
        json.dump({"mode": mode}, f, ensure_ascii=False)
    if context is not None:
        if mode == "plan":
            _switch_to_plan(context)
        else:
            _switch_to_build(context)
        global _LAST_APPLIED_MODE
        _LAST_APPLIED_MODE = mode
    logger.info(f"模式切换 → {mode}")
    return True


def _is_active():
    sp = os.path.join(_cur(), "00_task_state.json")
    if not os.path.isfile(sp):
        return False
    try:
        with open(sp, "r", encoding="utf-8") as f:
            st = json.load(f)
        return bool(st.get("todos"))
    except Exception:
        return False


def _validate(todos):
    if not isinstance(todos, list):
        return "todos 必须是 list"
    ip = 0
    for i, t in enumerate(todos):
        if not isinstance(t, dict):
            return f"todos[{i}] 必须是 object"
        if "content" not in t or "status" not in t:
            return f"todos[{i}] 缺少 content 或 status"
        if t["status"] not in _VS:
            return f"todos[{i}].status 无效: {t['status']}"
        if not isinstance(t.get("content", ""), str) or not t["content"].strip():
            return f"todos[{i}].content 不能为空"
        if t["status"] == "in_progress":
            ip += 1
    if ip > 1:
        return f"同时最多一个 in_progress，当前 {ip} 个"
    return None


def _gen_slug(slug):
    if slug:
        return slug
    d = datetime.now().strftime("%Y-%m-%d")
    a = _arc()
    n = 1
    if os.path.isdir(a):
        for x in os.listdir(a):
            if x.startswith(d) and os.path.isdir(os.path.join(a, x)):
                n += 1
    return f"{d}_auto-{n}"


def _summary(todos):
    n = len(todos)
    if n == 0:
        return "IDLE"
    c = {s: sum(1 for t in todos if t.get("status") == s) for s in _VS}
    d = c["completed"] + c["cancelled"]
    p = [f"已完成 {d}/{n}"]
    ip = next((t for t in todos if t.get("status") == "in_progress"), None)
    if ip:
        p.append(f"当前: {ip['content'][:50]}")
    pd = [t for t in todos if t.get("status") == "pending"]
    if pd:
        p.append(f"待办 {len(pd)} 项")
    if d == n and n > 0:
        if c["cancelled"] == n:
            p.append("全部取消")
        else:
            p.append("全部完成")
    return " | ".join(p)


def _workorder(todos, slug):
    tp = todos[0]["content"][:60] if todos else "空任务列表"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    w = 61
    L = []
    L.append("┌" + "─" * w + "┐")
    L.append("│           任务脚手架 · 工单" + " " * (w - 20) + "│")
    L.append("│" + " " * w + "│")
    L.append(f"│  编号: {slug}" + " " * (w - 10 - len(slug)) + "│")
    L.append(f"│  主题: {tp[:45]}" + " " * (w - 10 - len(tp[:45])) + "│")
    L.append("│  生成: 自动（irmia_task_scaffold）" + " " * (w - 28) + "│")
    L.append(f"│  时间: {ts}" + " " * (w - 10 - len(ts)) + "│")
    L.append("└" + "─" * w + "┘\n\n## 约束\n")
    has = False
    S = {"pending": "待执行", "in_progress": "进行中", "completed": "已完成", "cancelled": "已取消"}
    for i, t in enumerate(todos):
        c = t["content"].strip()
        if len(c) > 5:
            L.append(f"│ M{i+1} · {c[:55]}")
            has = True
    if not has:
        L.append("│ （无特殊约束）")
    L.append("\n## 交付清单\n\n| # | 内容 | 状态 |\n|---|------|------|")
    for i, t in enumerate(todos):
        L.append(f"| {i+1} | {t['content'][:45]} | {S.get(t.get('status', 'pending'), '待执行')} |")
    L.append(f"\n{'─' * w}\n弥亚 · {ts}")
    return "\n".join(L) + "\n"


def _init_ws(todos, slug, tags=None, title="", cwd=""):
    cur = _cur()
    os.makedirs(cur, exist_ok=True)
    now = datetime.now().isoformat(timespec="seconds")
    st = {"slug": slug, "updated_at": now, "todos": todos, "tags": tags or [], "title": title or (todos[0]["content"][:60] if todos else ""), "cwd": cwd}
    with open(os.path.join(cur, "00_task_state.json"), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    with open(os.path.join(cur, "01_research.md"), "w", encoding="utf-8") as f:
        f.write(_RT)
    with open(os.path.join(cur, "02_design.md"), "w", encoding="utf-8") as f:
        f.write(_DT)
    with open(os.path.join(cur, "03_work_order.md"), "w", encoding="utf-8") as f:
        f.write(_workorder(todos, slug))
    with open(os.path.join(cur, "progress.log"), "w", encoding="utf-8") as f:
        f.write(f"[{now}] TASK mode started — {len(todos)} tasks\n")
    return ["00_task_state.json", "01_research.md", "02_design.md", "03_work_order.md", "progress.log"]


def _update_state(todos):
    cur = _cur()
    sp = os.path.join(cur, "00_task_state.json")
    try:
        with open(sp, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        state = {"slug": "unknown", "todos": [], "tags": [], "title": "", "cwd": ""}
    old = state.get("todos", [])
    now = datetime.now().isoformat(timespec="seconds")
    ch = []
    for i, t in enumerate(todos):
        if i < len(old) and old[i].get("status") != t.get("status"):
            oc = old[i].get("content", f"#{i+1}")
            ch.append(f"#{i+1}({oc[:30]}) {old[i].get('status')}→{t.get('status')}")
    state["todos"] = todos
    state["updated_at"] = now
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    ln = (f"[{now}] status change: {', '.join(ch)}\n" if ch
          else f"[{now}] state refreshed — {len(todos)} tasks\n")
    with open(os.path.join(cur, "progress.log"), "a", encoding="utf-8") as f:
        f.write(ln)
    return state


def _gen_report(todos, slug):
    P = {"high": "高", "medium": "中", "low": "低"}
    lines = [f"任务汇报 — {slug}", "─" * 40]
    for i, t in enumerate(todos):
        icon = "✅" if t.get("status") == "completed" else "❌" if t.get("status") == "cancelled" else "⬜"
        lines.append(f"{icon} #{i+1} {t['content'][:50]:<50} [{P.get(t.get('priority',''),'medium')}]")
    comp = sum(1 for t in todos if t.get("status") in ("completed", "cancelled"))
    total = len(todos)
    dur = ""
    lp = os.path.join(_cur(), "progress.log")
    if os.path.isfile(lp):
        try:
            with open(lp, "r", encoding="utf-8") as f:
                log = f.read()
            ts_list = [ln[1:20] for ln in log.replace("\r", "").split("\n") if ln.startswith("[") and "T" in ln[1:20]]
            if len(ts_list) >= 2:
                try:
                    t1 = datetime.fromisoformat(ts_list[0])
                    t2 = datetime.fromisoformat(ts_list[-1])
                    secs = int((t2 - t1).total_seconds())
                    dur = f"{secs//60}min" if secs < 3600 else f"{secs//3600}h{(secs%3600)//60}min"
                except Exception:
                    logger.debug(f"计算耗时失败: {ts_list[:2]}")
        except Exception:
            logger.debug("读取 progress.log 失败，跳过耗时计算")
    lines.append("─" * 40)
    lines.append(f"总计: {comp}/{total} 完成" + (f" | 耗时: ~{dur}" if dur else ""))
    lines.append(f"工作空间已归档至: archive/{slug}/")
    return "\n".join(lines)


def _do_archive():
    cur = _cur()
    sp = os.path.join(cur, "00_task_state.json")
    if not os.path.exists(sp):
        return None
    if not os.path.isdir(cur):
        return None
    with open(sp, "r", encoding="utf-8") as f:
        state = json.load(f)
    slug = state.get("slug", "unknown")
    d = os.path.join(_arc(), slug)
    os.makedirs(_arc(), exist_ok=True)
    if os.path.isdir(d):
        slug = f"{slug}_{datetime.now().strftime('%H%M%S')}"
        d = os.path.join(_arc(), slug)
        state["slug"] = slug
    now = datetime.now().isoformat(timespec="seconds")
    with open(os.path.join(cur, "progress.log"), "a", encoding="utf-8") as f:
        f.write(f"[{now}] TASK mode ended\n")
    if not os.path.isdir(cur):
        logger.warning(f"归档时 current/ 目录已不存在，可能被并发归档移除")
        return state
    shutil.move(cur, d)
    with open(os.path.join(d, "progress.log"), "a", encoding="utf-8") as f:
        f.write(f"[{now}] workspace archived — {len(state.get('todos', []))} tasks\n")
    return state


def _cnt(todos):
    return {s: sum(1 for t in todos if t.get("status") == s) for s in _VS}


def _ok(todos, **ex):
    c = _cnt(todos)
    return json.dumps({"ok": True, "count": len(todos),
                       "pending": c["pending"], "in_progress": c["in_progress"],
                       "completed": c["completed"], "cancelled": c["cancelled"], **ex},
                      ensure_ascii=False)


def _err(msg):
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


_TASK_LIST_DESC = (
    "长任务进度追踪。遇 3+步/多文件/预计超5轮对话的复杂任务时调用。"
    "日常闲聊切勿调用。状态查询零副作用（只读磁盘，不修改任何内容）。"
    "action: start(创建多步骤任务)/update(更新进度)/complete(核实全部完成后生成汇报)/status(纯读取进度)"
)

_TASK_LIST_PARAMS = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["start", "update", "complete", "status"],
            "description": "操作模式",
        },
        "todos": {
            "type": "array",
            "description": "任务列表，全量覆写。start/update时必填",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "任务描述"},
                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]},
                    "priority": {"type": "string", "enum": ["high", "medium", "low"], "description": "优先级，可选"},
                },
                "required": ["content", "status"],
            },
        },
        "workspace_slug": {"type": "string", "description": "工作空间目录名，可选"},
        "title": {"type": "string", "description": "任务标题，可选"},
        "cwd": {"type": "string", "description": "当前工作目录，可选"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "标签，start时可选"},
    },
    "required": ["action"],
}

_TASK_ARCHIVE_DESC = (
    "已归档长任务查询。当需要召回历史任务细节、搜索过往决策或查看过往任务列表时调用。"
    "action: list(列出最近归档)/read(读取指定归档文件，slug和file必填)/search(全文搜索关键词)"
)

_TASK_ARCHIVE_PARAMS = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["list", "read", "search"]},
        "slug": {"type": "string", "description": "归档标识，read时必填"},
        "file": {"type": "string", "description": "文件名，read时必填"},
        "keyword": {"type": "string", "description": "搜索词，search时必填"},
    },
    "required": ["action"],
}


@dataclass
class TaskListTool(_FT):
    func_type: str = "tool"
    name: str = "task_list"
    description: str = _TASK_LIST_DESC
    parameters: dict = field(default_factory=lambda: _TASK_LIST_PARAMS)

    async def call(self, context, action: str, todos: list = None, workspace_slug: str = "", tags: list = None, title: str = "", cwd: str = "") -> str:
        try:
            active = _is_active()
            mode = _get_mode()
            if action in ("start", "update", "complete") and mode == "plan":
                return _err("当前为 Plan 模式，写操作已锁定。请在 WebUI 中将 Plan 切换为 Build 后重试。")
            if action == "status":
                if not active:
                    return json.dumps({"ok": True, "status": "idle", "summary": "IDLE — 未进入长任务模式"}, ensure_ascii=False)
                sp = os.path.join(_cur(), "00_task_state.json")
                with open(sp, "r", encoding="utf-8") as f:
                    st = json.load(f)
                tds = st.get("todos", [])
                return _ok(tds, summary=_summary(tds), workspace="task_scaffolds/current/",
                           status="active", slug=st.get("slug"))

            if action == "start":
                if active:
                    return _err("已有活跃任务，请先 complete 或清空后重试")
                if not todos:
                    return _err("start 需要提供 todos 列表")
                e = _validate(todos)
                if e:
                    return _err(e)
                slug = _gen_slug(workspace_slug or None)
                fs = _init_ws(todos, slug, tags, title, cwd)
                return _ok(todos, summary=_summary(todos), workspace="task_scaffolds/current/",
                           files=fs, action="workspace_created", slug=slug)

            if action == "update":
                if not todos:
                    return _err("update 需要提供 todos 列表")
                e = _validate(todos)
                if e:
                    return _err(e)
                if not active:
                    slug = _gen_slug(workspace_slug or None)
                    fs = _init_ws(todos, slug, cwd=cwd)
                    return _ok(todos, summary=_summary(todos), workspace="task_scaffolds/current/",
                               files=fs, action="workspace_created_implicit", slug=slug)
                _update_state(todos)
                done = all(t.get("status") in ("completed", "cancelled") for t in todos)
                if done:
                    arc = _do_archive()
                    sl = arc.get("slug", "unknown") if arc else "unknown"
                    return _ok(todos, summary=f"全部完成 — 已归档到 archive/{sl}/",
                               workspace=f"task_scaffolds/archive/{sl}/", action="archived")
                return _ok(todos, summary=_summary(todos), workspace="task_scaffolds/current/", action="state_updated")

            if action == "complete":
                if not active:
                    return _err("未进入长任务模式，无需 complete。查看历史归档请用 task_archive(action='list')")
                sp = os.path.join(_cur(), "00_task_state.json")
                with open(sp, "r", encoding="utf-8") as f:
                    st = json.load(f)
                tds = st.get("todos", [])
                slug = st.get("slug", "unknown")
                report = _gen_report(tds, slug)
                _do_archive()
                return json.dumps({"ok": True, "report": report, "archive_path": f"task_scaffolds/archive/{slug}/",
                                   "summary": f"已归档: {slug}", "action": "completed"}, ensure_ascii=False)

            return _err(f"未知 action: {action}")
        except Exception as e:
            return _err(str(e))


@dataclass
class TaskArchiveTool(_FT):
    func_type: str = "tool"
    name: str = "task_archive"
    description: str = _TASK_ARCHIVE_DESC
    parameters: dict = field(default_factory=lambda: _TASK_ARCHIVE_PARAMS)

    async def call(self, context, action: str, slug: str = "", file: str = "", keyword: str = "") -> str:
        try:
            arc = _arc()
            if action == "list":
                items = []
                dirs = []
                if os.path.isdir(arc):
                    dirs = sorted([d for d in os.listdir(arc) if os.path.isdir(os.path.join(arc, d))], reverse=True)
                    for d in dirs[:50]:
                        sp = os.path.join(arc, d, "00_task_state.json")
                        if os.path.isfile(sp):
                            with open(sp, "r", encoding="utf-8") as f:
                                st = json.load(f)
                            tds = st.get("todos", [])
                            items.append({"slug": d, "count": len(tds),
                                          "completed": sum(1 for t in tds if t.get("status") in ("completed", "cancelled")),
                                          "tags": st.get("tags", []),
                                          "summary": tds[0]["content"][:60] if tds else ""})
                total = len(dirs)
                return json.dumps({"ok": True, "archives": items[:20], "total": total,
                                   "has_more": len(items) > 20}, ensure_ascii=False)

            if action == "read":
                if not slug or not file:
                    return _err("read 需要 slug 和 file 参数")
                fp = os.path.join(arc, slug, file)
                if not os.path.isfile(fp) or not fp.startswith(os.path.abspath(arc)):
                    return _err(f"文件不存在: {slug}/{file}")
                with open(fp, "r", encoding="utf-8") as f:
                    content = f.read()
                return json.dumps({"ok": True, "slug": slug, "file": file,
                                   "content": content[:5000],
                                   "truncated": len(content) > 5000}, ensure_ascii=False)

            if action == "search":
                if not keyword:
                    return _err("search 需要 keyword 参数")
                matches = []
                if os.path.isdir(arc):
                    for d in os.listdir(arc):
                        dp = os.path.join(arc, d)
                        if not os.path.isdir(dp):
                            continue
                        for fn in ["00_task_state.json", "01_research.md", "02_design.md", "03_work_order.md", "progress.log"]:
                            fp = os.path.join(dp, fn)
                            if not os.path.isfile(fp):
                                continue
                            with open(fp, "r", encoding="utf-8") as f:
                                txt = f.read()
                            idx = txt.lower().find(keyword.lower())
                            if idx >= 0:
                                start = max(0, idx - 40)
                                end = min(len(txt), idx + len(keyword) + 80)
                                matches.append({"slug": d, "file": fn,
                                                "snippet": txt[start:end].replace("\n", " ")})
                            if len(matches) >= 30:
                                break
                        if len(matches) >= 30:
                            break
                return json.dumps({"ok": True, "matches": matches, "keyword": keyword}, ensure_ascii=False)

            return _err(f"未知 action: {action}")
        except Exception as e:
            return _err(str(e))


# ═══════════════════════════════════════
# HTTP 路由
# ═══════════════════════════════════════

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


_ACTIVITY_WRITE_COUNT = 0

def _log_activity(agent: str, status: str, detail: str, tool: str = None, task_summary: str = None):
    global _ACTIVITY_WRITE_COUNT
    state_dir = os.path.join(_root(), "state")
    os.makedirs(state_dir, exist_ok=True)
    entry = {"ts": datetime.now().strftime("%H:%M:%S"), "agent": agent, "status": status,
             "detail": detail, "tool": tool, "task_summary": task_summary}
    fp = os.path.join(state_dir, "activity.jsonl")
    with open(fp, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _ACTIVITY_WRITE_COUNT += 1
    if _ACTIVITY_WRITE_COUNT % 50 == 0:
        _trim_line_file(fp, 200)


def _trim_line_file(fp: str, max_lines: int):
    if not os.path.exists(fp):
        return
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        lines = []
    if len(lines) > max_lines:
        tmp = fp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(lines[-max_lines:])
        os.replace(tmp, fp)


def _load_dashboard():
    fp = os.path.join(_PLUGIN_DIR, "templates", "dashboard.html")
    with open(fp, "r", encoding="utf-8") as f:
        return f.read()


def _register_routes(context):
    from quart import Response, jsonify, request as qr

    _DASHBOARD_HTML = _load_dashboard()

    logger.info(f"[task_scaffold] _root() = {_root()}")
    logger.info(f"[task_scaffold] _cur()  = {_cur()}")
    logger.info(f"[task_scaffold] _arc()  = {_arc()}")
    logger.info(f"[task_scaffold] state exists = {os.path.isfile(os.path.join(_cur(), '00_task_state.json'))}")

    async def dashboard():
        return Response(_DASHBOARD_HTML, content_type="text/html; charset=utf-8")

    _last_no_state_logged = False

    async def api_current():
        nonlocal _last_no_state_logged
        sp = os.path.join(_cur(), "00_task_state.json")
        if not os.path.isfile(sp):
            if not _last_no_state_logged:
                logger.debug(f"[task_scaffold] api_current: no active task (expected after cleanup)")
                _last_no_state_logged = True
            return jsonify({"active": False})
        _last_no_state_logged = False
        with open(sp, "r", encoding="utf-8") as f:
            st = json.load(f)
        tds = st.get("todos", [])
        logger.debug(f"[task_scaffold] api_current → active=True, slug={st.get('slug')}, todos={len(tds)}")
        if not tds:
            return jsonify({"active": False})
        actual = [n for n in os.listdir(_cur()) if os.path.isfile(os.path.join(_cur(), n))]
        return jsonify({"active": True, "slug": st.get("slug"), "title": st.get("title", ""), "cwd": st.get("cwd", ""), "tags": st.get("tags", []),
                        "count": len(tds), "completed": sum(1 for t in tds if t.get("status") in ("completed", "cancelled")),
                        "todos": tds, "files": sorted(actual, key=lambda x: (
                            {"00_task_state.json":0,"03_work_order.md":1,"02_design.md":2,"01_research.md":3,"progress.log":4}
                        ).get(x, 99))})

    async def api_current_file(name):
        fp = os.path.join(_cur(), name)
        if not os.path.isfile(fp) or not fp.startswith(os.path.abspath(_cur())):
            return Response("file not found", status=404)
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(content[:5000], content_type="text/plain; charset=utf-8")

    async def api_archives():
        logger.info("[task_scaffold] api_archives() called")
        items = []
        a = _arc()
        if os.path.isdir(a):
            dirs = sorted([d for d in os.listdir(a) if os.path.isdir(os.path.join(a, d))], reverse=True)
            for d in dirs[:50]:
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
                                  "summary": tds[0]["content"][:60] if tds else ""})
        logger.info(f"[task_scaffold] api_archives → {len(items)} items")
        return jsonify(items[:50])

    async def api_archive_summary(slug):
        a = _arc()
        fp = os.path.join(a, slug, "00_task_state.json")
        if not os.path.isfile(fp) or not fp.startswith(os.path.abspath(a)):
            return jsonify({"ok": False, "error": "not found"})
        with open(fp, "r", encoding="utf-8") as f:
            st = json.load(f)
        arc_dir = os.path.join(_arc(), slug)
        actual = [n for n in os.listdir(arc_dir) if os.path.isfile(os.path.join(arc_dir, n))]
        st["files"] = sorted(actual, key=lambda x: (
            {"00_task_state.json": 0, "03_work_order.md": 1, "02_design.md": 2, "01_research.md": 3, "progress.log": 4}
        ).get(x, 99))
        return jsonify(st)

    async def api_archive_file(slug, name):
        a = _arc()
        fp = os.path.join(a, slug, name)
        if not os.path.isfile(fp) or not fp.startswith(os.path.abspath(a)):
            return Response("file not found", status=404)
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(content[:5000], content_type="text/plain; charset=utf-8")

    async def api_activity():
        fp = os.path.join(_root(), "state", "activity.jsonl")
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
        return jsonify({"mode": _get_mode()})

    async def api_mode_set():
        try:
            body = await qr.get_json()
            m = body.get("mode", "") if body else ""
        except Exception:
            m = ""
        if m not in ("plan", "build"):
            return jsonify({"ok": False, "error": "mode 必须是 plan 或 build"})
        _set_mode(m, context)
        _log_activity("System", "系统", f"模式切换 → {m}")
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
    ]

    for path, handler, methods, desc in _ROUTES:
        context.register_web_api(path, handler, methods, desc)

    try:
        app = getattr(context, 'app', None) or getattr(context, '_app', None) or getattr(context, 'web_app', None)
        if app:
            for path, handler, methods, desc in _ROUTES:
                if "<" not in path:
                    app.add_url_rule(path, path.replace("/", "_"), handler, methods=methods)
            logger.info(f"已通过 Quart app 注册 {len(_ROUTES)} 条路由")
    except Exception as e:
        logger.debug(f"Quart app 路由注册跳过: {e}")

    logger.info(f"WebUI 路由已注册: {' | '.join(p for p,_,_,_ in _ROUTES)}")


class Main(star.Star):
    def __init__(self, context, config=None):
        super().__init__(context)
        self.ctx = context
        tl = TaskListTool()
        ta = TaskArchiveTool()
        context.add_llm_tools(tl, ta)
        _register_routes(context)
        if _get_mode() == "plan":
            _set_mode("build", context)
            logger.info("启动时检测到 plan 模式残留，已强制重置为 build")
        self._tray_stop = None
        try:
            from . import tray
            self._tray_stop = tray.start()
            if self._tray_stop:
                atexit.register(lambda s=self._tray_stop: s.set())
            logger.info("系统托盘已启动")
        except Exception as e:
            logger.warning(f"系统托盘启动失败（可能缺少 pystray）: {e}")
        logger.info("irmia_task_scaffold 已就绪 — task_list + task_archive + WebUI 仪表盘")

    @filter.on_using_llm_tool()
    async def _on_tool_call(self, event: AstrMessageEvent, tool, tool_args):
        name = tool.name if hasattr(tool, "name") else str(tool)
        detail = str(tool_args)[:80] if isinstance(tool_args, dict) else ""
        ts = ""
        if name == "task_list":
            act = tool_args.get("action", "") if isinstance(tool_args, dict) else ""
            if act == "complete":
                ts = "任务完成汇报"
            elif act == "start":
                ts = f"启动 {len(tool_args.get('todos',[]))} 项任务" if isinstance(tool_args, dict) else ""
        _log_activity("Miria", "执行中", f"调用 {name}" if not ts else ts, tool=name, task_summary=detail)

    @filter.on_llm_response()
    async def _on_response(self, event: AstrMessageEvent, resp):
        text = str(resp.message) if hasattr(resp, 'message') else str(resp)
        preview = text[:30].replace("\n", " ") if text else ""
        _log_activity("Miria", "回复中", f"回复{' · ' + preview if preview else '…'}")

    @filter.on_agent_done()
    async def _on_done(self, event: AstrMessageEvent, run_context, resp):
        _log_activity("Miria", "待命中", "—")

    @filter.on_llm_tool_respond()
    async def _on_tool_done(self, event: AstrMessageEvent, tool, tool_args, tool_result):
        name = tool.name if hasattr(tool, "name") else str(tool)
        if name in ("task_list", "task_archive"):
            return
        cur = _cur()
        sp = os.path.join(cur, "00_task_state.json")
        try:
            with open(sp, "r", encoding="utf-8") as f:
                state = json.load(f)
            tds = state.get("todos", [])
            if not tds:
                return
        except Exception:
            return

        cwd = ""
        if isinstance(tool_args, dict):
            for k in ("filepath", "path", "cwd", "file", "directory", "dir"):
                v = tool_args.get(k, "")
                if v and isinstance(v, str):
                    d = os.path.dirname(v) if os.path.sep in v else v
                    if os.path.isdir(d):
                        cwd = d
                        break
        if cwd:
            state["cwd"] = cwd

        updated = False
        for i, t in enumerate(tds):
            if t.get("status") == "in_progress":
                tds[i]["status"] = "completed"
                updated = True
                for j in range(i + 1, len(tds)):
                    if tds[j].get("status") == "pending":
                        tds[j]["status"] = "in_progress"
                        break
                break
        if not updated:
            for i, t in enumerate(tds):
                if t.get("status") == "pending":
                    tds[i]["status"] = "in_progress"
                    updated = True
                    break

        state["todos"] = tds
        state["updated_at"] = datetime.now().isoformat(timespec="seconds")
        with open(sp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        if updated:
            now = datetime.now().isoformat(timespec="seconds")
            with open(os.path.join(cur, "progress.log"), "a", encoding="utf-8") as f:
                f.write(f"[{now}] auto-advance via {name}\n")

        done = all(t.get("status") in ("completed", "cancelled") for t in tds)
        if done:
            _do_archive()
            _log_activity("Miria", "任务完成", f"全部 {len(tds)} 项任务完成，已自动归档", tool=name)

    @register_on_llm_request()
    async def _on_llm_req(self, event, request) -> None:
        mode = _get_mode()
        global _LAST_APPLIED_MODE
        if mode != _LAST_APPLIED_MODE:
            if mode == "plan":
                _switch_to_plan(self.ctx)
            else:
                _switch_to_build(self.ctx)
            _LAST_APPLIED_MODE = mode
        if mode == "plan":
            ft = getattr(request, 'func_tool', None)
            if ft and hasattr(ft, 'remove_tool'):
                for name in _PLAN_DISABLED_TOOLS:
                    try:
                        ft.remove_tool(name)
                    except Exception:
                        pass

    @filter.on_decorating_result()
    async def _on_decorating_result(self, event):
        if _get_mode() != "plan":
            return
        note = "\n\n[系统] 当前处于 plan（只读）模式，写工具已禁用。需要执行写入操作请在 WebUI 切换为 Build。"
        try:
            result = event.get_result()
            event.set_result(result + note)
        except Exception as e:
            logger.debug(f"注入 plan 提示失败: {e}")
