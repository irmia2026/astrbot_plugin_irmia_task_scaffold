"""TaskListTool 与 TaskArchiveTool。"""
import json, os, asyncio
from dataclasses import dataclass, field

from astrbot.api import FunctionTool as _FT
from ._constants import _TASK_LIST_DESC, _TASK_LIST_PARAMS, _TASK_ARCHIVE_DESC, _TASK_ARCHIVE_PARAMS
from ._paths import cur, arc
from ._mode import get_mode
from ._state import is_active, validate, gen_slug, summary, ok, err, init_ws, update_state
from ._archive import gen_report, do_archive, get_recent_summaries
from ._templates import load_template as _load_tpl, list_templates as _list_tpl
from ._checkpoints import do_checkpoint, do_rollback, list_checkpoints


@dataclass
class TaskListTool(_FT):
    func_type: str = "tool"
    name: str = "task_list"
    description: str = _TASK_LIST_DESC
    parameters: dict = field(default_factory=lambda: _TASK_LIST_PARAMS)

    async def call(self, context, action: str, todos: list = None, workspace_slug: str = "", tags: list = None, title: str = "", cwd: str = "", template: str = "", checkpoint_name: str = "") -> str:
        try:
            active = is_active()
            mode = get_mode()
            if action in ("start", "update", "complete") and mode == "plan":
                return err("当前为 Plan 模式，写操作已锁定。请在 WebUI 中将 Plan 切换为 Build 后重试。")
            if action == "status":
                if not active:
                    rec = get_recent_summaries(5)
                    rpt = {"ok": True, "status": "idle", "summary": "IDLE — 未进入长任务模式"}
                    if rec:
                        rpt["recent"] = rec
                        rpt["summary"] += f" （最近完成 {len(rec)} 项归档）"
                    return json.dumps(rpt, ensure_ascii=False)
                sp = os.path.join(cur(), "00_task_state.json")
                try:
                    st = await asyncio.to_thread(lambda: json.load(open(sp, "r", encoding="utf-8")))
                except Exception as e:
                    return err(f"读取状态失败: {e}")
                tds = st.get("todos", [])
                return ok(tds, summary=summary(tds), workspace="task_scaffolds/current/",
                          status="active", slug=st.get("slug"),
                          hint="使用 update 更新进度，切勿重复 start")

            if action == "start":
                if active:
                    return err("已有活跃任务，请使用 update 更新当前任务进度，不要重复 start。用 task_list(action='status') 查看当前任务。")
                if not todos:
                    return err("start 需要提供 todos 列表")
                e = validate(todos)
                if e:
                    return err(e)
                slug = gen_slug(workspace_slug or None)
                fs = await asyncio.to_thread(init_ws, todos, slug, tags, title or f"任务工单 · {slug}", cwd)
                return ok(todos, summary=summary(todos), workspace="task_scaffolds/current/",
                          files=fs, action="workspace_created", slug=slug)

            if action == "update":
                if not todos:
                    return err("update 需要提供 todos 列表")
                e = validate(todos)
                if e:
                    return err(e)
                if not active:
                    return err("无活跃任务，无法 update。请先调用 task_list(action='start') 启动任务。")
                state = await asyncio.to_thread(update_state, todos)
                if state is None:
                    return err("无活跃任务或状态文件丢失，无法 update")
                done = all(t.get("status") in ("completed", "cancelled") for t in todos)
                if done:
                    arc_result = await asyncio.to_thread(do_archive)
                    sl = arc_result.get("slug", "unknown") if arc_result else "unknown"
                    return ok(todos, summary=f"全部完成 — 已归档到 archive/{sl}/",
                              workspace=f"task_scaffolds/archive/{sl}/", action="archived")
                return ok(todos, summary=summary(todos), workspace="task_scaffolds/current/", action="state_updated")

            if action == "complete":
                if not active:
                    return err("未进入长任务模式，无需 complete。查看历史归档请用 task_archive(action='list')")
                sp = os.path.join(cur(), "00_task_state.json")
                try:
                    st = await asyncio.to_thread(lambda: json.load(open(sp, "r", encoding="utf-8")))
                except Exception as e:
                    return err(f"读取状态失败: {e}")
                tds = st.get("todos", [])
                slug = st.get("slug", "unknown")
                report = gen_report(tds, slug)
                await asyncio.to_thread(do_archive)
                return json.dumps({"ok": True, "report": report, "archive_path": f"task_scaffolds/archive/{slug}/",
                                   "summary": f"已归档: {slug}", "action": "completed"}, ensure_ascii=False)

            if action == "load_template":
                return _load_tpl(template)
            if action == "list_templates":
                return _list_tpl()
            if action == "checkpoint":
                return do_checkpoint(checkpoint_name)
            if action == "rollback":
                return do_rollback(checkpoint_name)
            if action == "list_checkpoints":
                return list_checkpoints()

            return err(f"未知 action: {action}")
        except Exception as e:
            return err(str(e))


@dataclass
class TaskArchiveTool(_FT):
    func_type: str = "tool"
    name: str = "task_archive"
    description: str = _TASK_ARCHIVE_DESC
    parameters: dict = field(default_factory=lambda: _TASK_ARCHIVE_PARAMS)

    async def call(self, context, action: str, slug: str = "", file: str = "", keyword: str = "") -> str:
        try:
            a = arc()
            if action == "list":
                offset = max(0, int(slug) if slug else 0)
                page_limit = max(1, min(100, int(file) if file else 20))
                items = []
                dirs = []
                if os.path.isdir(a):
                    dirs = sorted([d for d in os.listdir(a) if os.path.isdir(os.path.join(a, d))], reverse=True)
                total = len(dirs)
                for d in dirs[offset:offset + page_limit]:
                    sp = os.path.join(a, d, "00_task_state.json")
                    if not os.path.isfile(sp):
                        continue
                    try:
                        st = await asyncio.to_thread(lambda: json.load(open(sp, "r", encoding="utf-8")))
                    except Exception:
                        continue
                    tds = st.get("todos", [])
                    items.append({"slug": d, "count": len(tds),
                                  "completed": sum(1 for t in tds if t.get("status") in ("completed", "cancelled")),
                                  "tags": st.get("tags", []),
                                  "summary": tds[0]["content"][:60] if tds else ""})
                return json.dumps({"ok": True, "archives": items, "total": total,
                                   "has_more": offset + len(items) < total}, ensure_ascii=False)

            if action == "read":
                if not slug or not file:
                    return err("read 需要 slug 和 file 参数")
                from pathlib import Path
                from ._paths import safe_name
                if not safe_name(slug) or not safe_name(file):
                    return err("slug 或 file 包含非法字符")
                base = Path(arc()).resolve()
                try:
                    fp = (base / slug / file).resolve()
                    fp.relative_to(base)
                except (ValueError, RuntimeError):
                    return err(f"文件不存在: {slug}/{file}")
                if not fp.is_file():
                    return err(f"文件不存在: {slug}/{file}")
                content = await asyncio.to_thread(fp.read_text, encoding="utf-8")
                return json.dumps({"ok": True, "slug": slug, "file": file,
                                   "content": content[:5000],
                                   "truncated": len(content) > 5000}, ensure_ascii=False)

            if action == "search":
                if not keyword:
                    return err("search 需要 keyword 参数")
                matches = []
                if os.path.isdir(a):
                    for d in os.listdir(a):
                        dp = os.path.join(a, d)
                        if not os.path.isdir(dp):
                            continue
                        for fn in ["00_task_state.json", "01_research.md", "02_design.md", "03_work_order.md", "04_note.md", "progress.log"]:
                            fp = os.path.join(dp, fn)
                            if not os.path.isfile(fp):
                                continue
                            try:
                                txt = await asyncio.to_thread(lambda: open(fp, "r", encoding="utf-8").read())
                            except Exception:
                                continue
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

            return err(f"未知 action: {action}")
        except Exception as e:
            return err(str(e))
