"""Token 追踪与统计。"""
import json, os
from datetime import datetime

from . import _constants
from ._paths import root
from ._activity import trim_line_file

_TOKEN_FILE = None


def token_fp():
    global _TOKEN_FILE
    if _TOKEN_FILE is None:
        _TOKEN_FILE = os.path.join(root(), "state", "tokens.jsonl")
    return _TOKEN_FILE


def record_usage(input_new: int, input_cached: int, output_tokens: int):
    from ._config import get as config_get
    fp = token_fp()
    sd = os.path.dirname(fp)
    os.makedirs(sd, exist_ok=True)
    line = json.dumps({"ts": datetime.now().isoformat(timespec="seconds"),
                       "i": input_new, "c": input_cached, "o": output_tokens,
                       "p": _constants._LLM_PROVIDER or "-"}, ensure_ascii=False)
    with open(fp, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    trim_line_file(fp, config_get("tokens_max_lines", 500))


def get_stats():
    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_total = 0
    fp = token_fp()
    if os.path.isfile(fp):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            if entry.get("ts", "") >= month_start.isoformat(timespec="seconds"):
                                month_total += entry.get("i", 0) + entry.get("o", 0)
                        except Exception:
                            pass
        except Exception:
            pass
    return {"session_total": _constants._SESSION_TOKENS, "session_in": _constants._SESSION_TOKENS_IN,
            "session_cached": _constants._SESSION_TOKENS_CACHED, "session_out": _constants._SESSION_TOKENS_OUT,
            "month_total": month_total, "context_limit": _constants._CONTEXT_LIMIT,
            "ctx_size": _constants._LAST_CTX_SIZE}
