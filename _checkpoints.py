"""检查点/回滚功能。"""
import json, os, shutil
from datetime import datetime

from ._paths import cur
from ._state import is_active, ok, err


def ckpt_dir():
    return os.path.join(cur(), "checkpoints")


def _copy_current(dst_dir):
    """拷贝整个 current/ 工作空间到目标目录。"""
    cr = cur()
    os.makedirs(dst_dir, exist_ok=True)
    for fn in os.listdir(cr):
        src = os.path.join(cr, fn)
        dst = os.path.join(dst_dir, fn)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
        elif os.path.isdir(src) and fn != "checkpoints":  # 不嵌套 checkpoints
            shutil.copytree(src, dst, dirs_exist_ok=True)


def do_checkpoint(name: str):
    if not name:
        return err("checkpoint 需要 checkpoint_name 参数")
    if not is_active():
        return err("无活跃任务，无法创建检查点")
    cd = ckpt_dir()
    os.makedirs(cd, exist_ok=True)
    dst = os.path.join(cd, name)
    try:
        _copy_current(dst)
        # 额外保存元数据
        meta = {
            "checkpoint_name": name,
            "checkpoint_at": datetime.now().isoformat(timespec="seconds"),
            "todos_count": len(json.load(open(os.path.join(dst, "00_task_state.json"), "r", encoding="utf-8")).get("todos", [])),
        }
        with open(os.path.join(dst, "_checkpoint_meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return json.dumps({"ok": True, "checkpoint": name, "todos_count": meta["todos_count"]}, ensure_ascii=False)
    except Exception as e:
        return err(f"创建检查点失败: {e}")


def do_rollback(name: str):
    if not name:
        return err("rollback 需要 checkpoint_name 参数")
    if not is_active():
        return err("无活跃任务，无法回滚")
    cd = ckpt_dir()
    src = os.path.join(cd, name)
    if not os.path.isdir(src):
        return err(f"检查点不存在: {name}")
    try:
        cr = cur()
        # 备份当前状态，防止回滚失败丢失
        backup = os.path.join(cd, f"_rollback_backup_{datetime.now().strftime('%H%M%S')}")
        _copy_current(backup)
        # 恢复检查点：先清空 current（保留 checkpoints 目录）
        for fn in os.listdir(cr):
            fp = os.path.join(cr, fn)
            if fn == "checkpoints":
                continue
            if os.path.isfile(fp):
                os.remove(fp)
            elif os.path.isdir(fp):
                shutil.rmtree(fp)
        # 从检查点复制回来
        for fn in os.listdir(src):
            if fn == "_checkpoint_meta.json":
                continue
            s = os.path.join(src, fn)
            d = os.path.join(cr, fn)
            if os.path.isfile(s):
                shutil.copy2(s, d)
            elif os.path.isdir(s):
                shutil.copytree(s, d)
        now = datetime.now().isoformat(timespec="seconds")
        with open(os.path.join(cr, "progress.log"), "a", encoding="utf-8") as f:
            f.write(f"[{now}] rolled back to checkpoint: {name}\n")
        state = json.load(open(os.path.join(cr, "00_task_state.json"), "r", encoding="utf-8"))
        return ok(state.get("todos", []), summary="已回滚到检查点 " + name, action="rolled_back")
    except Exception as e:
        return err(f"回滚失败: {e}")


def list_checkpoints():
    cd = ckpt_dir()
    if not os.path.isdir(cd):
        return json.dumps({"ok": True, "checkpoints": []}, ensure_ascii=False)
    cps = []
    for fn in sorted(os.listdir(cd)):
        fp = os.path.join(cd, fn)
        if not os.path.isdir(fp) or fn.startswith("_"):
            continue
        meta_fp = os.path.join(fp, "_checkpoint_meta.json")
        try:
            if os.path.isfile(meta_fp):
                with open(meta_fp, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            else:
                # 兼容旧版检查点（单个 json 文件）
                state = json.load(open(os.path.join(fp, "00_task_state.json"), "r", encoding="utf-8"))
                meta = {"checkpoint_name": fn, "checkpoint_at": "", "todos_count": len(state.get("todos", []))}
            cps.append({"name": meta.get("checkpoint_name", fn), "at": meta.get("checkpoint_at", ""),
                        "todos": meta.get("todos_count", 0)})
        except Exception:
            pass
    return json.dumps({"ok": True, "checkpoints": cps}, ensure_ascii=False)
