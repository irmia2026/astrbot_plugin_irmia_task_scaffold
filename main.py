"""irmia_task_scaffold — LLM Agent 长任务方法论文本工作空间。"""
import json, os, asyncio
from datetime import datetime

from astrbot.api import logger, star
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.star.register import register_on_llm_request
from astrbot.core.agent.message import TextPart

from . import _constants
from ._paths import root, cur, load_persisted, save_persisted
from ._mode import get_mode
from ._state import is_active
from ._archive import do_archive
from ._tokens import record_usage
from ._tools import TaskListTool, TaskArchiveTool
from ._routes import register_routes
from ._activity import log as log_activity, clear_activity


def _read_ws_files():
    """同步读取工作区方法论文件状态（后续可考虑异步化）。"""
    cr = cur()
    empty_files = []
    for fn, label in [("01_research.md", "调研"), ("02_design.md", "设计"), ("04_note.md", "备忘")]:
        fp = os.path.join(cr, fn)
        if os.path.isfile(fp):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                # 检查是否还是空模板
                lines = [l.strip() for l in content.split("\n") if l.strip() and not l.strip().startswith(">")]
                if len(lines) <= 3:
                    empty_files.append(label)
            except Exception:
                pass
    return empty_files


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
        await log_activity(_constants._AGENT_NAME, "执行中", f"调用 {name}" if not ts else ts, tool=name, task_summary=detail)

    @filter.on_llm_response()
    async def _on_response(self, event: AstrMessageEvent, resp):
        text = str(resp.message) if hasattr(resp, 'message') else str(resp)
        preview = text[:30].replace("\n", " ") if text else ""
        await log_activity(_constants._AGENT_NAME, "回复中", f"回复{' · ' + preview if preview else '…'}")
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
        await log_activity(_constants._AGENT_NAME, "待命中", "—")

    @filter.on_llm_tool_respond()
    async def _on_tool_done(self, event: AstrMessageEvent, tool, tool_args, tool_result):
        name = tool.name if hasattr(tool, "name") else str(tool)
        if name in ("task_list", "task_archive"):
            return
        # 仅对成功的工具响应推进任务进度
        # 判断失败：工具返回本身是异常对象，或明确包含失败标记
        failed = False
        if tool_result is None:
            failed = False
        elif isinstance(tool_result, Exception):
            failed = True
        elif isinstance(tool_result, dict):
            failed = not tool_result.get("ok", True)
        else:
            tr_text = str(tool_result)
            # 仅对明确的失败提示敏感，避免正常 JSON 中的 error 字段误伤
            lowered = tr_text.lower()
            if ("failed" in lowered or "traceback" in lowered or
                "错误:" in tr_text or "失败:" in tr_text or
                "error:" in lowered or "exception:" in lowered):
                failed = True
        if failed:
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
                await log_activity(_constants._AGENT_NAME, "任务完成", f"全部 {len(tds)} 项任务完成，已自动归档", tool=name)
            except Exception as e:
                logger.error(f"自动归档失败: {e}")

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
        
        # 检查工作区方法论文件状态，用于提醒
        ws_hint = ""
        if is_active():
            try:
                empty_files = await asyncio.to_thread(_read_ws_files)
                if empty_files:
                    ws_hint = f"\n【工作区提醒】{', '.join(empty_files)}文件尚未记录内容。"
            except Exception:
                pass
        
        if mode != "plan":
            parts = getattr(request, 'extra_user_content_parts', None)
            if parts is not None:
                try:
                    hint = "\n[Build 模式] 所有工具可用。若已有活跃长任务，使用 update 更新进度，切勿重复 start。"
                    if ws_hint:
                        hint += ws_hint + "请在执行调研/设计/发现关键信息时，及时用 safe_edit 编辑 01_research.md / 02_design.md / 04_note.md 记录结论。"
                    part = TextPart(text=hint)
                    part.mark_as_temp()
                    parts.append(part)
                except Exception:
                    pass
            return
        
        # Plan 模式：提醒先读工作区文件
        funcs = getattr(request, 'functions', None) or getattr(request, 'tools', None) or getattr(request, 'func_tool', None)
        removed = []
        if funcs:
            keep = []
            for f in funcs:
                name = getattr(f, 'name', '') or (f.get('name', '') if isinstance(f, dict) else '')
                if name in _constants._EXEMPT_TOOLS:
                    keep.append(f)
                    continue
                if name in _constants._ALWAYS_WRITE:
                    removed.append(name)
                    continue
                # 1. 读工具名称安全词 — 工具名被拆分为单词后，任一单词是安全词则视为只读
                #    覆盖: read_file / file_read / readFile / safe_read_cache / code-search
                #    但如果同时包含写词（如 get_permission_and_write），以写词为准
                name_words = {w.lower() for w in _constants._NAME_SPLIT_RE.split(name) if len(w) > 1}
                has_safe = bool(name_words & _constants._SAFE_READ_WORDS)
                has_write = bool(name_words & _constants._WRITE_TOOL_WORDS)
                if has_write:
                    removed.append(name)
                    continue
                if has_safe:
                    keep.append(f)
                    continue
                desc = getattr(f, 'description', '') or (f.get('description', '') if isinstance(f, dict) else '') or ''
                # 2. 中文描述：子串匹配关键词（中文不适合单词边界）
                if any('\u4e00' <= c <= '\u9fff' for c in desc):
                    if any(kw in desc.lower() for kw in _constants._WRITE_KEYWORDS if not kw.isascii()):
                        removed.append(name)
                        continue
                # 3. 英文描述：正则单词边界匹配（防止 "run" 误伤 "runtime"）
                if _constants._EN_WRITE_RE.search(desc):
                    removed.append(name)
                    continue
                # 4. 以上都不命中 → 保留
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
                plan_hint = (
                    "\n[Plan 模式] 写操作与命令执行类工具已禁用，只能阅读和分析。"
                    "如需写入请告知用户切换到 Build。"
                )
                if is_active():
                    plan_hint += (
                        "\n当前有活跃长任务，建议先读取 01_research.md / 02_design.md / 04_note.md "
                        "了解已记录的调研结论和设计决策，避免重复工作。"
                    )
                if ws_hint:
                    plan_hint += ws_hint
                part = TextPart(text=plan_hint)
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
