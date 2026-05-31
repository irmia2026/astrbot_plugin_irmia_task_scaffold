import json, os, shutil
from dataclasses import dataclass, field
from datetime import datetime

from astrbot.api import FunctionTool as _FT, logger, star
from astrbot.api.star import StarTools

_VS = {"pending", "in_progress", "completed", "cancelled"}

_RT = "# 调研\n\n*（在此记录参考来源、竞品分析、技术决策依据）*\n\n## 参考来源\n- \n\n## 技术对比\n- \n\n## 决策记录\n- \n"
_DT = "# 设计\n\n*（在此记录架构决策、接口定义、数据流图）*\n\n## 架构决策\n- \n\n## 接口定义\n- \n\n## 数据流\n- \n"


def _root():
    return os.path.join(str(StarTools.get_data_dir()), "task_scaffolds")


def _cur():
    return os.path.join(_root(), "current")


def _arc():
    return os.path.join(_root(), "archive")


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
        p.append("全部完成，将自动归档")
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


def _init_ws(todos, slug, tags=None):
    cur = _cur()
    os.makedirs(cur, exist_ok=True)
    now = datetime.now().isoformat(timespec="seconds")
    st = {"slug": slug, "updated_at": now, "todos": todos, "tags": tags or []}
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
    with open(sp, "r", encoding="utf-8") as f:
        state = json.load(f)
    old = state.get("todos", [])
    now = datetime.now().isoformat(timespec="seconds")
    ch = []
    for i, t in enumerate(todos):
        if i < len(old) and old[i].get("status") != t.get("status"):
            oc = old[i].get("content", f"#{i+1}")[:30]
            ch.append(f"#{i+1}({oc}) {old[i].get('status')}→{t.get('status')}")
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
    P = {"high": "high", "medium": "medium", "low": "low"}
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
            ts_list = [ln[1:20] for ln in log.split("\n") if ln.startswith("[") and "T" in ln[1:20]]
            if len(ts_list) >= 2:
                try:
                    t1 = datetime.fromisoformat(ts_list[0])
                    t2 = datetime.fromisoformat(ts_list[-1])
                    secs = int((t2 - t1).total_seconds())
                    dur = f"{secs//60}min" if secs < 3600 else f"{secs//3600}h{(secs%3600)//60}min"
                except Exception:
                    pass
        except Exception:
            pass
    lines.append("─" * 40)
    lines.append(f"总计: {comp}/{total} 完成" + (f" | 耗时: ~{dur}" if dur else ""))
    lines.append(f"工作空间已归档至: archive/{slug}/")
    return "\n".join(lines)


def _do_archive():
    cur = _cur()
    sp = os.path.join(cur, "00_task_state.json")
    if not os.path.exists(sp):
        return None
    with open(sp, "r", encoding="utf-8") as f:
        state = json.load(f)
    slug = state.get("slug", "unknown")
    d = os.path.join(_arc(), slug)
    os.makedirs(_arc(), exist_ok=True)
    if os.path.exists(d):
        d = os.path.join(_arc(), f"{slug}_{datetime.now().strftime('%H%M%S')}")
    now = datetime.now().isoformat(timespec="seconds")
    with open(os.path.join(cur, "progress.log"), "a", encoding="utf-8") as f:
        f.write(f"[{now}] TASK mode ended\n")
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
    "你的方法论文本工作空间。使用 action 参数控制模式。\n\n"
    "【IDLE → TASK】\n"
    "当用户任务需要 3+ 步 / 多文件 / 预计超 5 轮对话时，\n"
    "调用 task_list(action='start', todos=[...]) 进入 TASK 模式。\n\n"
    "【TASK 模式中】\n"
    "- 每完成一步：task_list(action='update', todos=[...])\n"
    "- 不确定进度：task_list(action='status')\n"
    "- 被打断后恢复：task_list(action='status') 先看进度\n\n"
    "【退出】\n"
    "全部完成后：task_list(action='complete')\n"
    "→ 生成汇报发给用户 → 回到 IDLE\n\n"
    "【日常聊天无需调用】——IDLE 模式下不参与对话。\n\n"
    "【上下文丢失恢复】\n"
    "如果你的历史消息中看不到最近的 task_list 调用结果，\n"
    "或你不确定当前任务进度，立即调用 task_list(action='status')。\n"
    "状态查询零副作用——它只读取磁盘，不修改任何东西。"
)

_TASK_LIST_PARAMS = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["start", "update", "complete", "status"],
            "description": "操作模式：start(创建)/update(更新)/complete(完成汇报)/status(纯读取)",
        },
        "todos": {
            "type": "array",
            "description": "任务列表（start/update 时必填）。全量覆写。格式: [{'content':..., 'status':..., 'priority':...}]",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "任务描述"},
                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"], "description": "任务状态"},
                    "priority": {"type": "string", "enum": ["high", "medium", "low"], "description": "优先级（可选）"},
                },
                "required": ["content", "status"],
            },
        },
        "workspace_slug": {"type": "string", "description": "可选。start 时指定工作空间目录名，如 '2026-05-31_REV-008'"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "可选。标签列表，仅 start 时生效。如 ['devkit','debug']"},
    },
    "required": ["action"],
}

_TASK_ARCHIVE_DESC = (
    "查阅已归档的任务历史。日常聊天无需调用——仅在用户明确询问过往任务时使用。\n\n"
    "action:\n"
    "- list: 列出最近归档\n"
    "- read: 读取指定归档的文件（slug + file 必填）\n"
    "- search: 全文搜索关键词（在归档目录内搜索）"
)

_TASK_ARCHIVE_PARAMS = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["list", "read", "search"], "description": "list/read/search"},
        "slug": {"type": "string", "description": "归档 slug（read 时必填）"},
        "file": {"type": "string", "description": "文件名（read 时必填）"},
        "keyword": {"type": "string", "description": "搜索关键词（search 时必填）"},
    },
    "required": ["action"],
}


@dataclass
class TaskListTool(_FT):
    func_type: str = "tool"
    name: str = "task_list"
    description: str = _TASK_LIST_DESC
    parameters: dict = field(default_factory=lambda: _TASK_LIST_PARAMS)

    async def call(self, context, action: str, todos: list = None, workspace_slug: str = "", tags: list = None) -> str:
        try:
            active = _is_active()
            if action == "status":
                if not active:
                    return json.dumps({"ok": True, "status": "idle", "summary": "IDLE — 无活跃任务"}, ensure_ascii=False)
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
                fs = _init_ws(todos, slug, tags)
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
                    fs = _init_ws(todos, slug)
                    return _ok(todos, summary=_summary(todos), workspace="task_scaffolds/current/",
                               files=fs, action="workspace_created_implicit", slug=slug)
                _update_state(todos)
                done = all(t.get("status") in ("completed", "cancelled") for t in todos)
                if done:
                    arc = _do_archive()
                    sl = arc.get("slug", "unknown") if arc else "unknown"
                    return _ok(todos, summary="全部完成 — 请调用 action='complete' 生成汇报",
                               workspace="task_scaffolds/current/", action="all_done", slug=sl)
                return _ok(todos, summary=_summary(todos), workspace="task_scaffolds/current/", action="state_updated")

            if action == "complete":
                if not active:
                    return _err("无活跃任务")
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
                total = len(items)
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


def _load_dashboard():
    fp = os.path.join(_PLUGIN_DIR, "templates", "dashboard.html")
    with open(fp, "r", encoding="utf-8") as f:
        return f.read()


def _register_routes(context):
    from quart import Response, jsonify

    _DASHBOARD_HTML = _load_dashboard()

    async def dashboard():
        return Response(_DASHBOARD_HTML, content_type="text/html; charset=utf-8")

    async def api_current():
        sp = os.path.join(_cur(), "00_task_state.json")
        if not os.path.isfile(sp):
            return jsonify({"active": False})
        with open(sp, "r", encoding="utf-8") as f:
            st = json.load(f)
        tds = st.get("todos", [])
        if not tds:
            return jsonify({"active": False})
        return jsonify({"active": True, "slug": st.get("slug"), "tags": st.get("tags", []),
                        "count": len(tds), "completed": sum(1 for t in tds if t.get("status") in ("completed", "cancelled")),
                        "todos": tds, "files": ["00_task_state.json", "01_research.md", "02_design.md",
                                                 "03_work_order.md", "progress.log"]})

    async def api_current_file(name):
        fp = os.path.join(_cur(), name)
        if not os.path.isfile(fp) or not fp.startswith(os.path.abspath(_cur())):
            return Response("file not found", status=404)
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(content[:5000], content_type="text/plain; charset=utf-8")

    async def api_archives():
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
        return jsonify(items[:50])

    async def api_archive_summary(slug):
        fp = os.path.join(_arc(), slug, "00_task_state.json")
        if not os.path.isfile(fp):
            return jsonify({"ok": False, "error": "not found"})
        with open(fp, "r", encoding="utf-8") as f:
            st = json.load(f)
        st["files"] = ["00_task_state.json", "01_research.md", "02_design.md",
                       "03_work_order.md", "progress.log"]
        return jsonify(st)

    async def api_archive_file(slug, name):
        a = _arc()
        fp = os.path.join(a, slug, name)
        if not os.path.isfile(fp) or not fp.startswith(os.path.abspath(a)):
            return Response("file not found", status=404)
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(content[:5000], content_type="text/plain; charset=utf-8")

    context.register_web_api("/task_scaffold/dashboard", dashboard, ["GET"], "任务工作台 HTML")
    context.register_web_api("/task_scaffold/api/current", api_current, ["GET"], "当前任务 JSON")
    context.register_web_api("/task_scaffold/api/current/file/<name>", api_current_file, ["GET"], "当前任务文件内容")
    context.register_web_api("/task_scaffold/api/archives", api_archives, ["GET"], "归档列表 JSON")
    context.register_web_api("/task_scaffold/api/archive/<slug>/summary", api_archive_summary, ["GET"], "归档摘要 JSON")
    context.register_web_api("/task_scaffold/api/archive/<slug>/file/<name>", api_archive_file, ["GET"], "归档文件内容")


class Main(star.Star):
    def __init__(self, context, config=None):
        super().__init__(context)
        context.add_llm_tools(TaskListTool(), TaskArchiveTool())
        _register_routes(context)
        logger.info("irmia_task_scaffold 已就绪 — task_list + task_archive + WebUI 仪表盘")
