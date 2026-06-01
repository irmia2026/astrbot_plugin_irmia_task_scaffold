"""tray.py — tkinter 无边框悬浮窗，固定在任务栏上方。独立线程，纯读文件。"""
import json
import os
import threading
import webbrowser

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


def _toggle_mode_file():
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


def start():
    import tkinter as tk

    stop_event = threading.Event()
    root = None

    def _create():
        nonlocal root
        root = tk.Tk()
        root.title("长任务")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg="#1e293b")

        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        w, h = 280, 36
        root.geometry(f"{w}x{h}+{sw - w - 8}+{sh - h - 44}")

        frm = tk.Frame(root, bg="#1e293b")
        frm.pack(fill="both", expand=True, padx=1, pady=1)

        mode_label = tk.Label(frm, text="●", font=("Segoe UI", 10, "bold"), fg="#3b82f6", bg="#1e293b")
        mode_label.pack(side="left", padx=(8, 4))
        mode_label.bind("<Button-1>", lambda e: _on_click())

        info_label = tk.Label(frm, text="加载中...", font=("Segoe UI", 9), fg="#94a3b8", bg="#1e293b",
                              anchor="w", padx=0)
        info_label.pack(side="left", fill="x", expand=True)
        info_label.bind("<Button-1>", lambda e: _on_click())

        frm.bind("<Button-1>", lambda e: _on_click())

        menu = tk.Menu(root, tearoff=0, bg="#1e293b", fg="#e2e8f0", font=("Segoe UI", 9))
        menu.add_command(label="切换 Plan/Build", command=_toggle_mode_file)
        menu.add_command(label="打开仪表板", command=lambda: webbrowser.open(
            "http://localhost:6185/api/plug/task_scaffold/dashboard"))
        menu.add_separator()
        menu.add_command(label="退出", command=lambda: _stop())

        def _on_click():
            webbrowser.open("http://localhost:6185/api/plug/task_scaffold/dashboard")

        def _on_right(event):
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        frm.bind("<Button-3>", _on_right)
        mode_label.bind("<Button-3>", _on_right)
        info_label.bind("<Button-3>", _on_right)

        def _stop():
            stop_event.set()
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", _stop)

        def _refresh():
            if stop_event.is_set():
                return
            mode = _read_mode()
            cur = _read_current()
            color = {"plan": "#3b82f6", "build": "#10b981"}.get(mode, "#94a3b8")
            if cur["active"]:
                mode_label.config(text="●", fg=color)
                ip = f"   ⏳ {cur['current']}" if cur["current"] else ""
                info_label.config(text=f"{cur['completed']}/{cur['total']}{ip}")
            else:
                mode_label.config(text="●", fg="#64748b")
                info_label.config(text="空闲 · 未进入长任务模式")
            root.after(2000, _refresh)

        root.after(100, _refresh)
        root.mainloop()

    t = threading.Thread(target=_create, daemon=True)
    t.start()
    return stop_event
