"""常量、模板、工具描述、全局可变变量。零依赖（不 import 本项目其他模块）。"""

_VS = {"pending", "in_progress", "completed", "cancelled"}

_SESSION_TOKENS = 0
_SESSION_TOKENS_IN = 0
_SESSION_TOKENS_CACHED = 0
_SESSION_TOKENS_OUT = 0
_LLM_PROVIDER = ""
_AGENT_NAME = ""
_CONTEXT_LIMIT = 200000  # 首次运行时从 config.yaml 或自动检测覆盖


def apply_config_extras():
    """将 config.yaml 的扩展关键词/豁免工具合并到常量列表。"""
    global _CONTEXT_LIMIT
    from ._config import get as cfg
    extra_kw = cfg("extra_write_keywords", [])
    extra_ex = cfg("extra_exempt_tools", [])
    limit = cfg("context_limit", 0)
    if limit > 0:
        _CONTEXT_LIMIT = limit
    for kw in extra_kw:
        if kw and kw.strip() and kw not in _WRITE_KEYWORDS:
            _WRITE_KEYWORDS.append(kw)
    # 如果有新加英文词，也更新正则
    new_en = [kw for kw in extra_kw if kw and kw.strip() and kw.isascii() and kw not in (
        "write", "edit", "patch", "modify", "delete",
        "commit", "push", "deploy",
        "upload", "publish", "release", "merge",
        "install", "uninstall", "rollback", "unzip",
    )]
    if new_en:
        global _EN_WRITE_RE
        _EN_WRITE_RE = re.compile(
            r'\b(?:write|edit|patch|modify|delete|commit|push|deploy|'
            r'upload|publish|release|merge|install|uninstall|rollback|unzip'
            + '|' + '|'.join(re.escape(w) for w in new_en) + r')\b',
            re.IGNORECASE
        )
    for t in extra_ex:
        if t not in _EXEMPT_TOOLS:
            _EXEMPT_TOOLS.add(t)
_LAST_CTX_SIZE = 0

_WRITE_KEYWORDS = [
    # 强写入信号（保留）
    "write", "edit", "patch", "modify", "delete",
    "commit", "push", "deploy",
    "upload", "publish", "release", "merge",
    "install", "uninstall", "rollback", "unzip",
    # 中文写入关键词
    "部署", "安装", "删除", "写入", "创建", "修改", "编辑",
    "执行", "运行", "下载", "上传", "提交", "推送", "发布",
    "合并", "卸载", "回滚", "解压", "压缩", "重启",
]

# 正则匹配（单词边界），用于 main.py 过滤
# 仅匹配英文关键词以避免子串误伤（如 "run" 匹配 "runtime"）
import re
_EN_WRITE_RE = re.compile(
    r'\b(?:' + '|'.join([
        "write", "edit", "patch", "modify", "delete",
        "commit", "push", "deploy",
        "upload", "publish", "release", "merge",
        "install", "uninstall", "rollback", "unzip",
    ]) + r')\b',
    re.IGNORECASE
)

# 写工具名称关键词 — 如果工具名包含这些词，即使同时有安全词，也视为写工具
_WRITE_TOOL_WORDS = {
    "write", "edit", "patch", "delete", "modify", "upload",
    "commit", "push", "deploy", "install", "uninstall",
    "rollback", "unzip", "remove", "create", "save",
}

# 读工具名称安全词 — 工具名任意位置包含这些词（作为独立单词）视为只读
# 支持前缀 (read_file)、后缀 (file_read)、中缀 (safe_read_cache)、驼峰 (readFile)
_SAFE_READ_WORDS = {
    "read", "search", "list", "get", "query", "find",
    "show", "browse", "preview", "check", "fetch",
    "dump", "cat", "echo", "lookup", "print", "stat",
    "describe", "explain", "inspect", "peek", "view",
    "glob", "grep", "ls", "walk", "scan", "trace",
}

# 用于将工具名拆分为单词的正则
_NAME_SPLIT_RE = re.compile(r'[_-]+|\.|(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])')
_ALWAYS_WRITE = {"astrbot_execute_shell", "astrbot_execute_python"}
_EXEMPT_TOOLS = {"task_list", "task_archive"}

_RT = """# 调研笔记

> 使用时机：当子任务涉及"调研技术方案、对比选型、查阅文档"时，将关键结论记录在此。
> 记录方式：使用 safe_edit 或 file_write 直接编辑此文件。

## 参考来源
- 

## 技术对比
- 

## 决策记录
- 
"""

_DT = """# 设计文档

> 使用时机：当子任务涉及"架构设计、接口定义、数据流规划"时，将设计决策记录在此。
> 记录方式：使用 safe_edit 或 file_write 直接编辑此文件。

## 架构决策
- 

## 接口定义
- 

## 数据流
- 
"""

_NT = """# 备忘

> 使用时机：当发现"关键 bug 根因、重要 workaround、易遗忘的配置细节"时，立即记录在此。
> 记录方式：使用 safe_edit 或 file_write 直接编辑此文件。
> 价值：这些信息在上下文被截断后极易丢失，写入文件可永久保留。

## 关键发现
- 

## 避坑记录
- 

## 临时配置
- 
"""

_TASK_LIST_DESC = (
    "长任务进度追踪。仅在预计多轮、多文件修改的复杂任务时调用。"
    "start 成功后用 update 更新进度，不要重复 start；全部完成会自动归档。"
    "\n工作区文件：01_research.md（调研）、02_design.md（设计）、04_note.md（备忘）——用 safe_edit 编辑记录关键结论。"
    "\ntitle 可选，省略时自动生成。"
)

_TASK_LIST_PARAMS = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["start", "update", "complete", "status", "load_template", "list_templates", "checkpoint", "rollback", "list_checkpoints"],
            "description": "操作模式",
        },
        "todos": {
            "type": "array",
            "description": "任务列表，全量覆写。start/update时必填",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "任务描述"},
                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]},
                    "priority": {"type": "string", "enum": ["high", "medium", "low"], "description": "优先级，可选"},
                },
                "required": ["content", "status"],
            },
        },
        "workspace_slug": {"type": "string", "description": "工作空间目录名，可选"},
        "title": {"type": "string", "description": "任务标题，可选"},
        "cwd": {"type": "string", "description": "当前工作目录，可选"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "标签，start时可选"},
        "template": {"type": "string", "description": "模板名，load_template时必填"},
        "checkpoint_name": {"type": "string", "description": "检查点名，checkpoint/rollback时必填"},
    },
    "required": ["action"],
}

_TASK_ARCHIVE_DESC = (
    "已归档长任务查询。当需要召回历史任务细节、搜索过往决策或查看过往任务列表时调用。"
    "action: list(列出最近归档)/read(读取指定归档文件，slug和file必填)/search(全文搜索关键词)"
)

_TASK_ARCHIVE_PARAMS = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["list", "read", "search"]},
        "slug": {"type": "string", "description": "归档标识，read时必填"},
        "file": {"type": "string", "description": "文件名，read时必填"},
        "keyword": {"type": "string", "description": "搜索词，search时必填"},
    },
    "required": ["action"],
}

_BUILTIN_TEMPLATES = {
    "feature_impl": {
        "title": "功能实现",
        "todos": [
            {"content": "调研技术方案与参考实现", "status": "pending", "priority": "high"},
            {"content": "设计架构与接口", "status": "pending", "priority": "high"},
            {"content": "编写核心实现代码", "status": "pending", "priority": "high"},
            {"content": "编写单元测试", "status": "pending", "priority": "medium"},
            {"content": "集成测试与文档更新", "status": "pending", "priority": "medium"},
        ]
    },
    "bug_fix": {
        "title": "Bug 修复",
        "todos": [
            {"content": "复现 Bug 并确认根因", "status": "pending", "priority": "high"},
            {"content": "定位问题代码", "status": "pending", "priority": "high"},
            {"content": "实施修复", "status": "pending", "priority": "high"},
            {"content": "回归验证", "status": "pending", "priority": "medium"},
        ]
    },
    "code_review": {
        "title": "代码审查",
        "todos": [
            {"content": "通读源码理解整体结构", "status": "pending", "priority": "high"},
            {"content": "识别潜在问题与改进点", "status": "pending", "priority": "high"},
            {"content": "编写审查报告", "status": "pending", "priority": "medium"},
            {"content": "实施修复与优化", "status": "pending", "priority": "medium"},
            {"content": "最终验证", "status": "pending", "priority": "medium"},
        ]
    },
}
