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
    from astrbot_plugin_irmia_task_scaffold._paths import root, cur, arc, mode_path, set_root
    r = root()
    assert r.endswith("task_scaffolds")
    assert cur().endswith("current")
    assert arc().endswith("archive")
    assert mode_path().endswith("mode.json")
    # 测试 set_root 覆盖
    set_root("/tmp/custom_task_scaffolds")
    assert root() == "/tmp/custom_task_scaffolds"
    assert cur().startswith("/tmp/custom_task_scaffolds")
    # 恢复默认值，避免影响其他测试
    set_root(r)
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


def test_safe_name():
    from astrbot_plugin_irmia_task_scaffold._paths import safe_name
    assert safe_name("2026-05-31_auto-1")
    assert safe_name("03_work_order.md")
    assert safe_name("slug_with.chars")
    assert not safe_name("")
    assert not safe_name("..")
    assert not safe_name("a/b")
    assert not safe_name("a\\b")
    assert not safe_name("a\x00b")
    assert not safe_name("a:b")
    print("  safe_name OK")


def test_workorder_width():
    from astrbot_plugin_irmia_task_scaffold._state import workorder, _display_width
    todos = [{"content": "中文任务内容测试", "status": "pending"}]
    wo = workorder(todos, "2026-05-31_test")
    lines = wo.split("\n")
    # 第一行和最后一行是边框，宽度应一致（均为 63 个字符：│ + 61 空格 + │）
    assert len(lines[0]) == len(lines[7]) == 63
    # 验证显示宽度计算
    assert _display_width("中文") == 4
    assert _display_width("ab") == 2
    print("  workorder width OK")


def test_token_stats_cached():
    from astrbot_plugin_irmia_task_scaffold._tokens import get_stats, token_fp, record_usage
    from astrbot_plugin_irmia_task_scaffold._paths import root, set_root
    import astrbot_plugin_irmia_task_scaffold._constants as _c
    tmp = tempfile.mkdtemp()
    original = root()
    set_root(tmp)
    # 重置 token_fp 缓存
    import astrbot_plugin_irmia_task_scaffold._tokens as _t
    _t._TOKEN_FILE = None
    # 保存旧值
    old_session = _c._SESSION_TOKENS
    old_in = _c._SESSION_TOKENS_IN
    old_cached = _c._SESSION_TOKENS_CACHED
    old_out = _c._SESSION_TOKENS_OUT
    old_ctx = _c._LAST_CTX_SIZE
    old_limit = _c._CONTEXT_LIMIT
    _c._SESSION_TOKENS = 0
    _c._SESSION_TOKENS_IN = 0
    _c._SESSION_TOKENS_CACHED = 0
    _c._SESSION_TOKENS_OUT = 0
    _c._LAST_CTX_SIZE = 0
    _c._CONTEXT_LIMIT = 200000
    # 写入本月数据
    record_usage(10, 5, 20)
    stats = get_stats()
    assert stats["month_total"] == 35  # i + c + o
    # session_* 由 main.py _on_response 维护，此处只验证 month_total 计入 cached
    # 清理
    shutil.rmtree(tmp, ignore_errors=True)
    _c._SESSION_TOKENS = old_session
    _c._SESSION_TOKENS_IN = old_in
    _c._SESSION_TOKENS_CACHED = old_cached
    _c._SESSION_TOKENS_OUT = old_out
    _c._LAST_CTX_SIZE = old_ctx
    _c._CONTEXT_LIMIT = old_limit
    set_root(original)
    _t._TOKEN_FILE = None
    print("  token stats cached OK")


def test_update_state_no_implicit_workspace():
    from astrbot_plugin_irmia_task_scaffold._state import update_state
    from astrbot_plugin_irmia_task_scaffold._paths import root, cur, set_root
    tmp = tempfile.mkdtemp()
    original = root()
    set_root(tmp)
    os.makedirs(cur(), exist_ok=True)
    # 未创建状态文件时调用 update_state 不应隐式创建工作区文件
    update_state([{"content": "a", "status": "pending"}])
    assert not os.path.isfile(os.path.join(cur(), "00_task_state.json"))
    # 创建状态文件后再 update 才允许
    with open(os.path.join(cur(), "00_task_state.json"), "w", encoding="utf-8") as f:
        json.dump({"slug": "test", "todos": [], "tags": [], "title": "", "cwd": ""}, f)
    update_state([{"content": "a", "status": "completed"}])
    assert os.path.isfile(os.path.join(cur(), "00_task_state.json"))
    # 恢复
    set_root(original)
    shutil.rmtree(tmp, ignore_errors=True)
    print("  update_state no implicit workspace OK")


def test_ws_summaries():
    from astrbot_plugin_irmia_task_scaffold._state import _summarize_ws_file, _read_ws_summaries
    from astrbot_plugin_irmia_task_scaffold._paths import root, cur, set_root
    tmp = tempfile.mkdtemp()
    original = root()
    set_root(tmp)
    os.makedirs(cur(), exist_ok=True)
    # 空文件应无摘要
    assert _summarize_ws_file("# 标题\n> 提示\n") == ""
    # 有实质内容
    content = "# 调研\n\n- 结论 A\n- 结论 B\n"
    assert "结论 A" in _summarize_ws_file(content)
    # 写入测试文件
    with open(os.path.join(cur(), "01_research.md"), "w", encoding="utf-8") as f:
        f.write(content)
    with open(os.path.join(cur(), "02_design.md"), "w", encoding="utf-8") as f:
        f.write("# 设计\n> 提示\n")  # 只有模板提示，无实质内容
    summaries = _read_ws_summaries(max_chars_per_file=80)
    assert "调研" in summaries
    assert "结论 A" in summaries["调研"]
    assert "设计" not in summaries
    # 恢复
    set_root(original)
    shutil.rmtree(tmp, ignore_errors=True)
    print("  ws summaries OK")

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

def test_plan_filter():
    from astrbot_plugin_irmia_task_scaffold._constants import (
        _EN_WRITE_RE, _SAFE_READ_WORDS, _NAME_SPLIT_RE, _WRITE_KEYWORDS, _WRITE_TOOL_WORDS
    )
    # 读工具不应被正则误伤
    safe_descs = [
        "Read a file from the filesystem",
        "Search the codebase for a pattern",
        "List all files in a directory",
        "Get the current weather",
        "Query the database",
        "Check if a package is installed",
        "Browse the web for information",
        "Fetch the latest news",
        "Look up a word definition",
        "This tool returns runtime information",
        "Get started with the tutorial",
        "Startup configuration check",
        "Sends a query to the API",
    ]
    for d in safe_descs:
        assert not _EN_WRITE_RE.search(d), f"regex falsely blocked: '{d}'"

    # 写工具应被正则捕获
    write_descs = [
        "Edit a file in place",
        "Write content to a file",
        "Delete a file permanently",
        "Modify the configuration",
        "Upload a file to server",
        "Install a new package",
        "Commit changes to git",
    ]
    for d in write_descs:
        assert _EN_WRITE_RE.search(d), f"regex missed write tool: '{d}'"

    # 工具名安全词拆分测试
    safe_names = [
        "read_file", "file_read", "search_code", "code-search",
        "readFile", "safeReadCache", "ReadCodeSearch", "dir_list",
        "ls_dir", "check_status",
    ]
    for name in safe_names:
        words = {w.lower() for w in _NAME_SPLIT_RE.split(name) if len(w) > 1}
        assert words & _SAFE_READ_WORDS, f"'{name}' should be safe"

    # 邪门工具名不应被误认为安全
    unsafe_names = [
        "write_file", "edit_code", "patch_dir", "deleteAll", "uploadFile",
    ]
    for name in unsafe_names:
        words = {w.lower() for w in _NAME_SPLIT_RE.split(name) if len(w) > 1}
        assert not (words & _SAFE_READ_WORDS), f"'{name}' should NOT be safe"

    # 写词优先于安全词
    mixed = "get_permission_and_write"
    words = {w.lower() for w in _NAME_SPLIT_RE.split(mixed) if len(w) > 1}
    assert (words & _WRITE_TOOL_WORDS), f"'{mixed}' should be blocked due to write word"

    # 高频误报词已移除
    for bad in ["run", "start", "send", "save", "create", "remove", "execute", "stop", "restart", "schedule"]:
        assert bad not in _WRITE_KEYWORDS, f"'{bad}' should not be in _WRITE_KEYWORDS"

    print("  plan filter OK")

if __name__ == "__main__":
    print("=== Running unit tests ===\n")
    test_constants()
    test_state_validate()
    test_state_cnt_ok_err()
    test_state_summary()
    test_state_gen_slug()
    test_paths_root()
    test_activity_trim()
    test_safe_name()
    test_workorder_width()
    test_token_stats_cached()
    test_update_state_no_implicit_workspace()
    test_ws_summaries()
    test_templates()
    test_templates_content()
    test_plan_filter()
    test_mode()
    print("\n=== All tests passed ===")
