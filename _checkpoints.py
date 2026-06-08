"""检查点/回滚功能。"""
import json, os
from datetime import datetime

from ._paths import cur
from ._state import is_active, ok, err


def ckpt_dir():
    return os.path.join(cur(), "checkpoints")


def do_checkpoint(name: str):
    if not name:
        return err("checkpoint 需要 checkpoint_name 参数")
    if not is_active():
        return err("无活跃任务，无法创建检查点")
    cd = ckpt_dir()
    os.makedirs(cd, exist_ok=True)
    src = os.path.join(cur(), "00_task_state.json")
    dst = os.path.join(cd, f"{name}.json")
    try:
        with open(src, "r", encoding="utf-8") as f:
            state = json.load(f)
        state["checkpoint_name"] = name
        state["checkpoint_at"] = datetime.now().isoformat(timespec="seconds")
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return json.dumps({"ok": True, "checkpoint": name, "todos_count": len(state.get("todos", []))}, ensure_ascii=False)
    except Exception as e:
        return err(f"创建检查点失败: {e}")


def do_rollback(name: str):
    if not name:
        return err("rollback 需要 checkpoint_name 参数")
    if not is_active():
        return err("无活跃任务，无法回滚")
    cd = ckpt_dir()
    fp = os.path.join(cd, f"{name}.json")
    if not os.path.isfile(fp):
        return err(f"检查点不存在: {name}")
    try:
        with open(fp, "r", encoding="utf-8") as f:
            ckpt = json.load(f)
        ckpt.pop("checkpoint_name", None)
        ckpt.pop("checkpoint_at", None)
        now = datetime.now().isoformat(timespec="seconds")
        ckpt["updated_at"] = now
        cr = cur()
        with open(os.path.join(cr, "00_task_state.json"), "w", encoding="utf-8") as f:
            json.dump(ckpt, f, ensure_ascii=False, indent=2)
        with open(os.path.join(cr, "progress.log"), "a", encoding="utf-8") as f:
            f.write(f"[{now}] rolled back to checkpoint: {name}\n")
        return ok(ckpt.get("todos", []), summary="已回滚到检查点 " + name, action="rolled_back")
    except Exception as e:
        return err(f"回滚失败: {e}")


def list_checkpoints():
    cd = ckpt_dir()
    if not os.path.isdir(cd):
        return json.dumps({"ok": True, "checkpoints": []}, ensure_ascii=False)
    cps = []
    for fn in sorted(os.listdir(cd)):
        if fn.endswith(".json"):
            fp = os.path.join(cd, fn)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    ckpt = json.load(f)
                cps.append({"name": fn[:-5], "at": ckpt.get("checkpoint_at", ""),
                            "todos": len(ckpt.get("todos", []))})
            except Exception:
                pass
    return json.dumps({"ok": True, "checkpoints": cps}, ensure_ascii=False)
