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
from ._state import is_active, _read_ws_files, _read_ws_summaries
from ._archive import do_archive
from ._tokens import record_usage
from ._tools import TaskListTool, TaskArchiveTool
from ._routes import register_routes
from ._activity import log as log_activity, clear_activity


class Main(star.Star):
    def __init__(self, context, config=None):
        super().__init__(context)
        if config and isinstance(config, dict) and config.get("data_root"):
            from . import _paths
            _paths.set_root(config["data_root"])
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
        text = resp.completion_text if hasattr(resp, 'completion_text') else str(resp)
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
        logger.debug(f"[_on_tool_done] tool={name} args={tool_args} result_type={type(tool_result).__name__}")
        if name in ("task_list", "task_archive"):
            logger.debug(f"[_on_tool_done] skip exempt tool {name}")
            return
        # 无活跃任务时不推进，避免读取不存在的状态文件
        if not is_active():
            logger.debug("[_on_tool_done] no active task, skip")
            return
        # 仅对明确失败的工具响应跳过推进
        failed = False
        fail_reason = ""

        def _extract_result_text(r):
            """从 AstrBot 的 CallToolResult 或原始返回值中提取可读的文本。"""
            if r is None:
                return ""
            if isinstance(r, Exception):
                return str(r)
            if isinstance(r, dict):
                return json.dumps(r, ensure_ascii=False)
            # 处理 mcp.types.CallToolResult
            if hasattr(r, "content") and isinstance(r.content, list):
                parts = []
                for c in r.content:
                    if hasattr(c, "text"):
                        parts.append(c.text)
                return "\n".join(parts)
            return str(r)

        if isinstance(tool_result, Exception):
            failed = True
            fail_reason = f"result is Exception: {tool_result}"
        elif isinstance(tool_result, dict):
            failed = not tool_result.get("ok", True)
            if failed:
                fail_reason = f"dict ok={tool_result.get('ok')}"
        elif tool_result is not None:
            # mcp.types.CallToolResult 显式标记错误
            if getattr(tool_result, "isError", False):
                failed = True
                fail_reason = "CallToolResult.isError=True"
            else:
                tr_text = _extract_result_text(tool_result)
                lowered = tr_text.lower()
                if ("failed" in lowered or "traceback" in lowered or
                    "错误:" in tr_text or "失败:" in tr_text or
                    "error:" in lowered or "exception:" in lowered):
                    failed = True
                    fail_reason = f"matched fail keyword in text: {tr_text[:120]}"
        # None 视为成功（工具无返回值但调用未抛异常）
        if failed:
            logger.info(f"[_on_tool_done] skip advance for {name}: {fail_reason}")
            return
        cr = cur()
        sp = os.path.join(cr, "00_task_state.json")
        try:
            state = await asyncio.to_thread(lambda: json.load(open(sp, "r", encoding="utf-8")))
        except Exception as e:
            logger.warning(f"[_on_tool_done] read state failed: {e}")
            return
        tds = state.get("todos", [])
        if not tds:
            logger.debug("[_on_tool_done] no todos, skip")
            return
        logger.debug(f"[_on_tool_done] before advance: {[t.get('status') for t in tds]}")
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
            await asyncio.to_thread(lambda: json.dump(state, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=2))
        except Exception as e:
            logger.error(f"[_on_tool_done] write state failed: {e}")
            return

        logger.info(f"[_on_tool_done] advanced {name}: {[t.get('status') for t in tds]}")
        if updated:
            now = datetime.now().isoformat(timespec="seconds")
            try:
                await asyncio.to_thread(lambda: open(os.path.join(cr, "progress.log"), "a", encoding="utf-8").write(f"[{now}] auto-advance via {name}\n"))
            except Exception:
                pass

        done = all(t.get("status") in ("completed", "cancelled") for t in tds)
        logger.info(f"[_on_tool_done] done={done} for {name}")
        if done:
            try:
                await asyncio.to_thread(do_archive)
                await log_activity(_constants._AGENT_NAME, "任务完成", f"全部 {len(tds)} 项任务完成，已自动归档", tool=name)
                logger.info(f"[_on_tool_done] archived {len(tds)} tasks")
            except Exception as e:
                logger.error(f"[_on_tool_done] auto-archive failed: {e}")

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

        # 上下文使用监控：超过阈值时注入告警，提示 LLM 注意上下文预算
        ctx_hint = ""
        if _constants._CONTEXT_LIMIT > 0 and _constants._LAST_CTX_SIZE > 0:
            pct = _constants._LAST_CTX_SIZE / _constants._CONTEXT_LIMIT
            if pct >= 0.85:
                ctx_hint = f"\n【上下文告警】当前上下文已使用 {int(pct*100)}%（{_constants._LAST_CTX_SIZE}/{_constants._CONTEXT_LIMIT} tokens），请优先读取工作区文件摘要，避免重复长篇输出。"
            elif pct >= 0.7:
                ctx_hint = f"\n【上下文提示】当前上下文已使用 {int(pct*100)}%，建议开始收尾或生成摘要。"

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
                    hint = "\n[Build 模式] 复杂任务用 task_list start/update；勿重复 start。"
                    if ws_hint:
                        hint += ws_hint + "请用 safe_edit 编辑 01_research/02_design/04_note 记录结论。"
                    if is_active():
                        try:
                            summaries = await asyncio.to_thread(_read_ws_summaries)
                            if summaries:
                                hint += "\n【已记录摘要】"
                                for label, s in summaries.items():
                                    hint += f" {label}: {s}"
                        except Exception:
                            pass
                    hint += ctx_hint
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
                    # 直接修改 ToolSet 内部列表，仅影响本次请求
                    funcs.tools = keep
                except Exception:
                    pass
                logger.info(f"plan 模式屏蔽 {len(removed)} 个写工具: {removed[:8]}{'...' if len(removed)>8 else ''}")
        parts = getattr(request, 'extra_user_content_parts', None)
        if parts is not None:
            try:
                plan_hint = (
                    "\n[Plan 模式] 写工具已禁用，只能阅读分析；需写入请切 Build。"
                )
                if is_active():
                    plan_hint += "\n当前有活跃任务，建议先读 01_research/02_design/04_note。"
                    try:
                        summaries = await asyncio.to_thread(_read_ws_summaries)
                        if summaries:
                            plan_hint += "\n【已记录摘要】"
                            for label, s in summaries.items():
                                plan_hint += f" {label}: {s}"
                    except Exception:
                        pass
                if ws_hint:
                    plan_hint += ws_hint
                plan_hint += ctx_hint
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
            if result is None:
                event.set_result(note)
            else:
                text = ""
                if result.chain:
                    try:
                        text = result.chain.get_plain_text()
                    except Exception:
                        pass
                event.set_result(text + note)
        except Exception as e:
            logger.debug(f"注入 plan 提示失败: {e}")
