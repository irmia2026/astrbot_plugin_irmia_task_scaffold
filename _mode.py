"""Plan/Build 模式管理。"""
import json, os

from astrbot.api import logger
from ._paths import root, mode_path


def get_mode():
    mp = mode_path()
    try:
        if os.path.isfile(mp):
            with open(mp, "r", encoding="utf-8") as f:
                return json.load(f).get("mode", "build")
    except Exception:
        pass
    return "build"


def set_mode(mode: str):
    os.makedirs(os.path.dirname(mode_path()), exist_ok=True)
    with open(mode_path(), "w", encoding="utf-8") as f:
        json.dump({"mode": mode}, f, ensure_ascii=False)
    logger.info(f"模式切换 \u2192 {mode}")
    return True
