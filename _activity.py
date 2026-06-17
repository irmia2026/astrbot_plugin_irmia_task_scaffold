"""活动日志记录、裁剪、清理。"""
import json, os
from datetime import datetime

from ._paths import root

_ACTIVITY_WRITE_COUNT = 0

try:
    import asyncio
except ImportError:
    asyncio = None

_ACTIVITY_LOCK = asyncio.Lock() if asyncio else None


def _log_debug(msg):
    try:
        from astrbot.api import logger
        logger.debug(msg)
    except Exception:
        pass


def clear_activity():
    fp = os.path.join(root(), "state", "activity.jsonl")
    if os.path.isfile(fp):
        try:
            os.remove(fp)
        except Exception:
            pass


async def log(agent: str, status: str, detail: str, tool: str = None, task_summary: str = None):
    global _ACTIVITY_WRITE_COUNT
    agent = agent or "Agent"
    state_dir = os.path.join(root(), "state")
    os.makedirs(state_dir, exist_ok=True)
    entry = {"ts": datetime.now().strftime("%H:%M:%S"), "agent": agent, "status": status,
             "detail": detail, "tool": tool, "task_summary": task_summary}
    fp = os.path.join(state_dir, "activity.jsonl")
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    async with _ACTIVITY_LOCK:
        try:
            with open(fp, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            _log_debug(f"log_activity 写入失败: {e}")
            return
        _ACTIVITY_WRITE_COUNT += 1
        if _ACTIVITY_WRITE_COUNT % 50 == 0:
            from ._config import get
            trim_line_file(fp, get("activity_max_lines", 200))


def trim_line_file(fp: str, max_lines: int):
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
