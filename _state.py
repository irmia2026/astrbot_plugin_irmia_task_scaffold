"""状态读写、校验、工作空间初始化、计数、工具函数。"""
import json, os
from datetime import datetime

from ._constants import _VS
from ._paths import root, cur, arc


def is_active():
    sp = os.path.join(cur(), "00_task_state.json")
    if not os.path.isfile(sp):
        return False
    try:
        with open(sp, "r", encoding="utf-8") as f:
            st = json.load(f)
        return bool(st.get("todos"))
    except Exception:
        return False


def validate(todos):
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


def gen_slug(slug):
    if slug:
        return slug
    d = datetime.now().strftime("%Y-%m-%d")
    a = arc()
    n = 1
    if os.path.isdir(a):
        for x in os.listdir(a):
            if x.startswith(d) and os.path.isdir(os.path.join(a, x)):
                n += 1
    return f"{d}_auto-{n}"


def summary(todos):
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


def cnt(todos):
    return {s: sum(1 for t in todos if t.get("status") == s) for s in _VS}


def ok(todos, **ex):
    c = cnt(todos)
    return json.dumps({"ok": True, "count": len(todos),
                       "pending": c["pending"], "in_progress": c["in_progress"],
                       "completed": c["completed"], "cancelled": c["cancelled"], **ex},
                      ensure_ascii=False)


def err(msg):
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


def workorder(todos, slug):
    tp = todos[0]["content"][:60] if todos else "空任务列表"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    w = 61
    L = []
    L.append("\u250c" + "\u2500" * w + "\u2510")
    L.append("\u2502           任务脚手架 \u00b7 工单" + " " * (w - 20) + "\u2502")
    L.append("\u2502" + " " * w + "\u2502")
    L.append(f"\u2502  编号: {slug}" + " " * (w - 10 - len(slug)) + "\u2502")
    L.append(f"\u2502  主题: {tp[:45]}" + " " * (w - 10 - len(tp[:45])) + "\u2502")
    L.append("\u2502  生成: 自动（irmia_task_scaffold）" + " " * (w - 28) + "\u2502")
    L.append(f"\u2502  时间: {ts}" + " " * (w - 10 - len(ts)) + "\u2502")
    L.append("\u2514" + "\u2500" * w + "\u2518\n\n## 约束\n")
    has = False
    S = {"pending": "待执行", "in_progress": "进行中", "completed": "已完成", "cancelled": "已取消"}
    for i, t in enumerate(todos):
        c = t["content"].strip()
        if len(c) > 5:
            L.append(f"\u2502 M{i+1} \u00b7 {c[:55]}")
            has = True
    if not has:
        L.append("\u2502 （无特殊约束）")
    L.append("\n## 交付清单\n\n| # | 内容 | 状态 |\n|---|------|------|")
    for i, t in enumerate(todos):
        L.append(f"| {i+1} | {t['content'][:45]} | {S.get(t.get('status', 'pending'), '待执行')} |")
    L.append(f"\n{'\u2500' * w}\n弥亚 \u00b7 {ts}")
    return "\n".join(L) + "\n"


def init_ws(todos, slug, tags=None, title="", cwd=""):
    from ._constants import _RT, _DT, _NT

    cr = cur()
    os.makedirs(cr, exist_ok=True)
    now = datetime.now().isoformat(timespec="seconds")
    st = {"slug": slug, "updated_at": now, "todos": todos, "tags": tags or [],
          "title": title, "cwd": cwd}
    with open(os.path.join(cr, "00_task_state.json"), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    with open(os.path.join(cr, "01_research.md"), "w", encoding="utf-8") as f:
        f.write(_RT)
    with open(os.path.join(cr, "02_design.md"), "w", encoding="utf-8") as f:
        f.write(_DT)
    with open(os.path.join(cr, "03_work_order.md"), "w", encoding="utf-8") as f:
        f.write(workorder(todos, slug))
    with open(os.path.join(cr, "04_note.md"), "w", encoding="utf-8") as f:
        f.write(_NT)
    with open(os.path.join(cr, "progress.log"), "w", encoding="utf-8") as f:
        f.write(f"[{now}] TASK mode started \u2014 {len(todos)} tasks\n")
    return ["00_task_state.json", "01_research.md", "02_design.md", "03_work_order.md", "04_note.md", "progress.log"]


def update_state(todos):
    cr = cur()
    sp = os.path.join(cr, "00_task_state.json")
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
            ch.append(f"#{i+1}({oc[:30]}) {old[i].get('status')}\u2192{t.get('status')}")
    state["todos"] = todos
    state["updated_at"] = now
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    ln = (f"[{now}] status change: {', '.join(ch)}\n" if ch
          else f"[{now}] state refreshed \u2014 {len(todos)} tasks\n")
    with open(os.path.join(cr, "progress.log"), "a", encoding="utf-8") as f:
        f.write(ln)
    return state
