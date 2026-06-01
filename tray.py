"""tray.py — Windows 系统托盘，显示长任务状态。独立线程，纯读文件。"""
import json
import os
import threading
import webbrowser

from PIL import Image, ImageDraw
import pystray

_ROOT = os.path.join(os.path.expanduser("~"), ".astrbot", "data", "task_scaffolds")


def _read_mode():
    try:
        mp = os.path.join(_ROOT, "state", "mode.json")
        if os.path.isfile(mp):
            with open(mp, "r", encoding="utf-8") as f:
                return json.load(f).get("mode", "build")
    except Exception:
        pass
    return "build"


def _read_current():
    try:
        sp = os.path.join(_ROOT, "current", "00_task_state.json")
        if os.path.isfile(sp):
            with open(sp, "r", encoding="utf-8") as f:
                st = json.load(f)
            tds = st.get("todos", [])
            comp = sum(1 for t in tds if t.get("status") in ("completed", "cancelled"))
            ip = next((t for t in tds if t.get("status") == "in_progress"), None)
            return {"active": True, "total": len(tds), "completed": comp,
                    "current": ip["content"][:40] if ip else "", "slug": st.get("slug", "")}
    except Exception:
        pass
    return {"active": False, "total": 0, "completed": 0, "current": "", "slug": ""}


def _make_icon(color: tuple):
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 28, 28), fill=color)
    return img


_BLUE = (59, 130, 246, 255)
_GREEN = (16, 185, 129, 255)
_GRAY = (148, 163, 184, 180)


def start():
    stop_event = threading.Event()

    def toggle_mode():
        try:
            mp = os.path.join(_ROOT, "state", "mode.json")
            cur = "build"
            if os.path.isfile(mp):
                with open(mp, "r", encoding="utf-8") as f:
                    cur = json.load(f).get("mode", "build")
            nxt = "plan" if cur == "build" else "build"
            os.makedirs(os.path.dirname(mp), exist_ok=True)
            with open(mp, "w", encoding="utf-8") as f:
                json.dump({"mode": nxt}, f, ensure_ascii=False)
        except Exception:
            pass

    def open_dashboard():
        webbrowser.open("http://localhost:6185/api/plug/task_scaffold/dashboard")

    def on_exit(_icon):
        stop_event.set()
        _icon.stop()

    icon = pystray.Icon(
        "task_scaffold",
        _make_icon(_GRAY),
        "长任务 · 加载中",
        menu=pystray.Menu(
            pystray.MenuItem("切换 Plan/Build", lambda: toggle_mode()),
            pystray.MenuItem("打开仪表板", lambda: open_dashboard()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出托盘", on_exit),
        ),
    )

    def _refresh():
        mode = _read_mode()
        cur = _read_current()
        if cur["active"]:
            color = _BLUE if mode == "plan" else _GREEN
            ip = f" · {cur['current']}" if cur["current"] else ""
            tip = f"{'Plan' if mode=='plan' else 'Build'} · {cur['completed']}/{cur['total']}{ip}"
        else:
            color = _GRAY
            tip = "空闲 · 未进入长任务模式"
        icon.icon = _make_icon(color)
        icon.title = "长任务"
        icon.tooltip = tip
        if not stop_event.is_set():
            threading.Timer(2, _refresh).start()

    def _run():
        _refresh()
        icon.run()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return stop_event
