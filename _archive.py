"""归档、报告、统计、摘要。"""
import json, os, shutil
from datetime import datetime, timedelta

from astrbot.api import logger
from . import _constants
from ._paths import root, cur, arc
from ._activity import trim_line_file


def gen_report(todos, slug):
    P = {"high": "高", "medium": "中", "low": "低"}
    lines = [f"任务汇报 \u2014 {slug}", "\u2500" * 40]
    for i, t in enumerate(todos):
        icon = "\u2705" if t.get("status") == "completed" else "\u274c" if t.get("status") == "cancelled" else "\u2b1c"
        lines.append(f"{icon} #{i+1} {t['content'][:50]:<50} [{P.get(t.get('priority',''),'medium')}]")
    comp = sum(1 for t in todos if t.get("status") in ("completed", "cancelled"))
    total = len(todos)
    dur = ""
    lp = os.path.join(cur(), "progress.log")
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
    lines.append("\u2500" * 40)
    lines.append(f"总计: {comp}/{total} 完成" + (f" | 耗时: ~{dur}" if dur else ""))
    lines.append(f"工作空间已归档至: archive/{slug}/")
    return "\n".join(lines)


def do_archive():
    cr = cur()
    sp = os.path.join(cr, "00_task_state.json")
    if not os.path.exists(sp):
        return None
    if not os.path.isdir(cr):
        return None
    with open(sp, "r", encoding="utf-8") as f:
        state = json.load(f)
    slug = state.get("slug", "unknown")
    d = os.path.join(arc(), slug)
    os.makedirs(arc(), exist_ok=True)
    if os.path.isdir(d):
        slug = f"{slug}_{datetime.now().strftime('%H%M%S')}"
        d = os.path.join(arc(), slug)
        state["slug"] = slug
    now = datetime.now().isoformat(timespec="seconds")
    with open(os.path.join(cr, "progress.log"), "a", encoding="utf-8") as f:
        f.write(f"[{now}] TASK mode ended\n")
    if not os.path.isdir(cr):
        logger.warning(f"归档时 current/ 目录已不存在，可能被并发归档移除")
        return state
    shutil.move(cr, d)
    with open(os.path.join(d, "progress.log"), "a", encoding="utf-8") as f:
        f.write(f"[{now}] workspace archived \u2014 {len(state.get('todos', []))} tasks\n")
    record_summary(state)
    return state


def record_summary(state):
    from ._config import get as config_get
    tds = state.get("todos", [])
    if not tds:
        return
    done = sum(1 for t in tds if t.get("status") == "completed")
    cn = sum(1 for t in tds if t.get("status") == "cancelled")
    first = tds[0].get("content", "")[:40] if tds else ""
    now = datetime.now().isoformat(timespec="seconds")
    title = state.get("title", first) or first
    line = json.dumps({"ts": now, "slug": state.get("slug", ""), "total": len(tds),
                       "done": done, "cancelled": cn, "title": title[:60]}, ensure_ascii=False)
    sd = os.path.join(root(), "state")
    os.makedirs(sd, exist_ok=True)
    fp = os.path.join(sd, "summary.jsonl")
    with open(fp, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    trim_line_file(fp, config_get("summary_max_lines", 100))


def get_recent_summaries(n=None):
    if n is None:
        from ._config import get as config_get
        n = config_get("recent_summary_count", 5)
    fp = os.path.join(root(), "state", "summary.jsonl")
    if not os.path.isfile(fp):
        return []
    lines = []
    try:
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        lines.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        return []
    return lines[-n:]


def get_stats():
    sw = os.path.join(root(), "state", "summary.jsonl")
    total = 0
    week_completed = 0
    week_start = (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                  - timedelta(days=datetime.now().weekday()))
    if os.path.isfile(sw):
        try:
            with open(sw, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            total += 1
                            ts = entry.get("ts", "")
                            if ts >= week_start.isoformat(timespec="seconds"):
                                # 统计本周归档中真正完成的 task 数，而不是归档批次
                                week_completed += entry.get("done", 0)
                        except Exception:
                            pass
        except Exception:
            pass
    return {"total_archived": total, "this_week": week_completed}
