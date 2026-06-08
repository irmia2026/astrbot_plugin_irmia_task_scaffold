"""irmia_task_scaffold — LLM Agent 长任务方法论文本工作空间。"""
import json, os
from datetime import datetime

from astrbot.api import logger, star
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.star.register import register_on_llm_request
from astrbot.core.agent.message import TextPart

from . import _constants
from ._paths import root, cur, load_persisted, save_persisted
from ._mode import get_mode, set_mode
from ._state import is_active
from ._archive import do_archive
from ._tokens import record_usage
from ._tools import TaskListTool, TaskArchiveTool
from ._routes import register_routes
from ._activity import log as log_activity, clear_activity


class Main(star.Star):
    def __init__(self, context, config=None):
        super().__init__(context)
        _constants.apply_config_extras()
        tl = TaskListTool()
        ta = TaskArchiveTool()
        context.add_llm_tools(tl, ta)
        register_routes(context)
        clear_activity()
        load_persisted()
        if get_mode() == "plan":
            set_mode("build")
            logger.info("启动时检测到 plan 模式残留，已强制重置为 build")
        self._tray_stop = None
        logger.info("系统托盘已禁用")
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
        log_activity(_constants._AGENT_NAME, "执行中", f"调用 {name}" if not ts else ts, tool=name, task_summary=detail)

    @filter.on_llm_response()
    async def _on_response(self, event: AstrMessageEvent, resp):
        text = str(resp.message) if hasattr(resp, 'message') else str(resp)
        preview = text[:30].replace("\n", " ") if text else ""
        log_activity(_constants._AGENT_NAME, "回复中", f"回复{' · ' + preview if preview else '…'}")
        usage = getattr(resp, 'usage', None)
        if usage:
            i = usage.input_other
            c = usage.input_cached
            o = usage.output
            _constants._SESSION_TOKENS += i + c + o
            _constants._SESSION_TOKENS_IN += i
            _constants._SESSION_TOKENS_CACHED += c
            _constants._SESSION_TOKENS_OUT += o
            _constants._LAST_CTX_SIZE = i + c
            save_persisted()
            record_usage(i, c, o)
        if not _constants._LLM_PROVIDER:
            raw = getattr(resp, 'raw_completion', None)
            if raw:
                model = getattr(raw, 'model', '') or ''
                if model:
                    _constants._LLM_PROVIDER = model
                    save_persisted()
        if _constants._CONTEXT_LIMIT == 200000:
            try:
                prov = self.context.get_using_provider()
                if prov:
                    limit = prov.provider_config.get("max_context_tokens", 0)
                    if limit > 0:
                        _constants._CONTEXT_LIMIT = limit
                        save_persisted()
            except Exception:
                pass

    @filter.on_agent_done()
    async def _on_done(self, event: AstrMessageEvent, run_context, resp):
        log_activity(_constants._AGENT_NAME, "待命中", "—")

    @filter.on_llm_tool_respond()
    async def _on_tool_done(self, event: AstrMessageEvent, tool, tool_args, tool_result):
        name = tool.name if hasattr(tool, "name") else str(tool)
        if name in ("task_list", "task_archive"):
            return
        cr = cur()
        sp = os.path.join(cr, "00_task_state.json")
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
        try:
            with open(sp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception:
            return

        if updated:
            now = datetime.now().isoformat(timespec="seconds")
            try:
                with open(os.path.join(cr, "progress.log"), "a", encoding="utf-8") as f:
                    f.write(f"[{now}] auto-advance via {name}\n")
            except Exception:
                pass

        done = all(t.get("status") in ("completed", "cancelled") for t in tds)
        if done:
            try:
                do_archive()
                log_activity(_constants._AGENT_NAME, "任务完成", f"全部 {len(tds)} 项任务完成，已自动归档", tool=name)
            except Exception:
                pass

    @register_on_llm_request()
    async def _on_llm_req(self, event, request) -> None:
        if not _constants._AGENT_NAME:
            try:
                pm = getattr(self.context, 'persona_manager', None)
                if pm and pm.personas_v3:
                    sel = pm.selected_default_persona_v3
                    name = sel.get("name", "") if sel else ""
                    if name and name not in ("default", "_chatui_default_"):
                        _constants._AGENT_NAME = name
                    elif pm.personas_v3:
                        for p in pm.personas_v3:
                            n = p.get("name", "")
                            if n and n not in ("default", "_chatui_default_"):
                                _constants._AGENT_NAME = n
                                break
            except Exception:
                pass
            if not _constants._AGENT_NAME:
                _constants._AGENT_NAME = "Agent"
        mode = get_mode()
        if mode != "plan":
            parts = getattr(request, 'extra_user_content_parts', None)
            if parts is not None:
                try:
                    part = TextPart(text="\n[Build 模式] 所有工具可用。若已有活跃长任务，使用 update 更新进度，切勿重复 start。")
                    part.mark_as_temp()
                    parts.append(part)
                except Exception:
                    pass
            return
        funcs = getattr(request, 'functions', None) or getattr(request, 'tools', None) or getattr(request, 'func_tool', None)
        removed = []
        if funcs:
            keep = []
            for f in funcs:
                name = getattr(f, 'name', '') or (f.get('name', '') if isinstance(f, dict) else '')
                if name in _constants._EXEMPT_TOOLS:
                    keep.append(f)
                    continue
                desc = getattr(f, 'description', '') or (f.get('description', '') if isinstance(f, dict) else '')
                if name in _constants._ALWAYS_WRITE or any(kw in (desc.lower() if desc else '') for kw in _constants._WRITE_KEYWORDS):
                    removed.append(name)
                else:
                    keep.append(f)
            if removed:
                try:
                    if hasattr(request, 'functions'):
                        request.functions = keep
                    if hasattr(request, 'tools'):
                        request.tools = keep
                    if hasattr(request, 'func_tool') and hasattr(request.func_tool, 'remove_tool'):
                        for name in removed:
                            try:
                                request.func_tool.remove_tool(name)
                            except Exception:
                                pass
                except Exception:
                    pass
                logger.info(f"plan 模式屏蔽 {len(removed)} 个写工具: {removed[:8]}{'...' if len(removed)>8 else ''}")
        parts = getattr(request, 'extra_user_content_parts', None)
        if parts is not None:
            try:
                part = TextPart(text=(
                    "\n[Plan 模式] 写操作与命令执行类工具已禁用，只能阅读和分析。"
                    "如需写入请告知用户切换到 Build。"
                ))
                part.mark_as_temp()
                parts.append(part)
            except Exception:
                pass

    @filter.on_decorating_result()
    async def _on_decorating_result(self, event):
        if get_mode() != "plan":
            return
        note = "\n\n[系统] 当前处于 plan（只读）模式，写工具已禁用。需要执行写入操作请在 WebUI 切换为 Build。"
        try:
            result = event.get_result()
            event.set_result(result + note)
        except Exception as e:
            logger.debug(f"注入 plan 提示失败: {e}")
