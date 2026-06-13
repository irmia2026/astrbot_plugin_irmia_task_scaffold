"""单元测试 — 核心纯函数（不依赖 AstrBot 运行时）。"""
import json, os, sys, tempfile, shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Test _constants
def test_constants():
    from astrbot_plugin_irmia_task_scaffold._constants import _VS, _WRITE_KEYWORDS, _ALWAYS_WRITE, _EXEMPT_TOOLS
    assert _VS == {"pending", "in_progress", "completed", "cancelled"}
    assert "write" in _WRITE_KEYWORDS
    assert "部署" in _WRITE_KEYWORDS
    assert "astrbot_execute_shell" in _ALWAYS_WRITE
    assert "task_list" in _EXEMPT_TOOLS
    print("  constants OK")

# Test _state functions
def test_state_validate():
    from astrbot_plugin_irmia_task_scaffold._state import validate
    valid = [{"content": "a", "status": "pending"}]
    assert validate(valid) is None
    assert validate([]) is None
    assert validate("not_list") == "todos 必须是 list"
    assert validate([{"content": "", "status": "pending"}]) is not None
    assert validate([{"content": "a", "status": "invalid"}]) is not None
    # Two in_progress
    two = [{"content": "a", "status": "in_progress"}, {"content": "b", "status": "in_progress"}]
    assert "同时最多一个" in validate(two)
    print("  state.validate OK")

def test_state_cnt_ok_err():
    from astrbot_plugin_irmia_task_scaffold._state import cnt, ok, err
    todos = [{"content": "a", "status": "completed"}, {"content": "b", "status": "pending"}]
    c = cnt(todos)
    assert c["completed"] == 1
    assert c["pending"] == 1
    r = ok(todos, summary="done")
    d = json.loads(r)
    assert d["ok"] is True
    assert d["count"] == 2
    assert d["summary"] == "done"
    r = err("test error")
    d = json.loads(r)
    assert d["ok"] is False
    assert d["error"] == "test error"
    print("  state.cnt/ok/err OK")

def test_state_summary():
    from astrbot_plugin_irmia_task_scaffold._state import summary
    assert summary([]) == "IDLE"
    todos = [{"content": "a", "status": "completed"}, {"content": "b", "status": "pending"}]
    s = summary(todos)
    assert "已完成 1/2" in s
    print("  state.summary OK")

def test_state_gen_slug():
    from astrbot_plugin_irmia_task_scaffold._state import gen_slug
    s = gen_slug("my_slug")
    assert s == "my_slug"
    # Auto slug
    auto = gen_slug(None)
    assert auto.startswith(datetime.now().strftime("%Y-%m-%d"))
    assert "_auto-" in auto
    print("  state.gen_slug OK")

# Test _paths
def test_paths_root():
    from astrbot_plugin_irmia_task_scaffold._paths import root, cur, arc, mode_path
    r = root()
    assert r.endswith("task_scaffolds")
    assert cur().endswith("current")
    assert arc().endswith("archive")
    assert mode_path().endswith("mode.json")
    print("  paths OK")

# Test activity
def test_activity_trim():
    from astrbot_plugin_irmia_task_scaffold._activity import trim_line_file
    tmp = os.path.join(tempfile.gettempdir(), "test_trim.jsonl")
    with open(tmp, "w") as f:
        for i in range(10):
            f.write(f"line {i}\n")
    trim_line_file(tmp, 5)
    with open(tmp) as f:
        lines = f.readlines()
    assert len(lines) == 5
    assert lines[0].strip() == "line 5"
    os.remove(tmp)
    print("  activity.trim_line_file OK")

# Test templates
def test_templates():
    from astrbot_plugin_irmia_task_scaffold._templates import load_template, list_templates
    r = load_template("feature_impl")
    d = json.loads(r)
    assert d["ok"] is True
    assert d["source"] == "builtin"
    assert d["title"] == "功能实现"
    assert len(d["todos"]) == 5
    r = load_template("nonexistent")
    d = json.loads(r)
    assert d["ok"] is False
    print("  templates OK")

# Test _mode
def test_mode():
    # _mode imports astrbot.api which is not available in test env
    # Just verify the module structure
    print("  mode OK (skipped — requires astrbot runtime)")

# Test constants templates
def test_templates_content():
    from astrbot_plugin_irmia_task_scaffold._constants import _RT, _DT, _NT
    assert "使用时机" in _RT
    assert "使用时机" in _DT
    assert "使用时机" in _NT
    assert "safe_edit" in _RT
    assert "safe_edit" in _DT
    assert "safe_edit" in _NT
    print("  template content OK")

if __name__ == "__main__":
    print("=== Running unit tests ===\n")
    test_constants()
    test_state_validate()
    test_state_cnt_ok_err()
    test_state_summary()
    test_state_gen_slug()
    test_paths_root()
    test_activity_trim()
    test_templates()
    test_templates_content()
    test_mode()
    print("\n=== All tests passed ===")
