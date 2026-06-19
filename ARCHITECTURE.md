# 架构说明

## 目录结构

```
astrbot_plugin_irmia_task_scaffold/
├── main.py                  # 插件入口 + AstrBot Filter/Request 钩子
├── _tools.py                # task_list / task_archive 工具实现
├── _state.py                # 状态读写、校验、工单、工作区摘要
├── _paths.py                # 路径解析、safe_name、数据根目录覆盖
├── _routes.py               # WebUI HTTP API（Quart）
├── _archive.py              # 自动归档逻辑
├── _checkpoints.py          # 检查点保存/回滚
├── _activity.py             # 实时活动流写入
├── _tokens.py               # Token 使用统计
├── _mode.py                 # Plan/Build 模式读取
├── _templates.py            # 工作区文件模板
├── _constants.py            # 常量、过滤词表、配置注入
├── _config.py               # 配置读取与默认值
├── pages/
│   └── dashboard/
│       └── index.html       # AstrBot 内置 Plugin Page 入口（也支持独立访问）
└── README.md / CHANGELOG.md / ARCHITECTURE.md
```

## 数据流

```
LLM 调用 task_list(action="start")
       ↓
TaskListTool.call() ──→ current/00_task_state.json
                      → current/01_research.md (模板)
                      → current/02_design.md   (模板)
                      → current/04_note.md     (模板)
                      → current/03_work_order.md (ASCII 工单)
                      → current/progress.log
```

```
LLM 下一轮请求
       ↓
register_on_llm_request()
       ↓
读取 mode.json
       ↓
plan  → 从 request.func_tool.tools 中移除写工具
      → user_prompt 注入模式提醒 + 工作区文件摘要
build → 注入工作区文件摘要 + 上下文监控提示
```

```
工具执行完成
       ↓
filter.on_llm_tool_respond()
       ↓
跳过 task_list / task_archive
       ↓
无活跃任务？直接返回
       ↓
判断 tool_result 是否明确失败
       ↓
未失败 → 当前 todo 标 completed，下一项 pending 标 in_progress
      → 更新 00_task_state.json
      → 全部完成 → do_archive()
```

## 核心组件

### TaskListTool

```python
@dataclass
class TaskListTool(FunctionTool):
    actions: start | update | complete | status | load_template | list_templates | checkpoint | rollback | list_checkpoints
    params: todos[], workspace_slug?, title?, tags?, cwd?
```

状态机约束：
- 最多一条 `in_progress`
- `start` 只能在无活跃任务时使用
- `update` 全量覆写 todos
- `complete` 生成汇报文本

### TaskArchiveTool

```python
@dataclass
class TaskArchiveTool(FunctionTool):
    actions: list | read | search
```

只读工具，遍历 `archive/` 目录。

### Plan/Build 模式

```
WebUI 切换 → POST /api/mode → 写入 mode.json
                    ↓
下次 LLM 请求 → register_on_llm_request() → 读取 mode.json
```

Plan 模式过滤逻辑：
1. 豁免 `task_list`、`task_archive`
2. 强制移除 `astrbot_execute_shell`、`astrbot_execute_python`
3. 工具名安全词（`read`、`search`、`list`、`get`、`grep` 等）优先保留
4. 工具名含写词（`write`、`edit`、`delete`、`save` 等）移除
5. 中文描述子串匹配写关键词
6. 英文描述按单词边界正则匹配写关键词

**只修改 `request.func_tool.tools` 列表，不影响其它请求。**

### HTTP 路由

AstrBot 自动加 `/api/plug/` 前缀。

| 路由 | 方法 | 说明 |
|------|------|------|
| `/task_scaffold/dashboard` | GET | WebUI HTML（Plugin Page 也支持独立访问） |
| `/task_scaffold/api/current` | GET | 当前任务 JSON |
| `/task_scaffold/api/current/file/<name>` | GET | 当前工作区文件内容 |
| `/task_scaffold/api/archives` | GET | 归档列表（分页 + 搜索） |
| `/task_scaffold/api/archive/<slug>/summary` | GET | 归档详情 |
| `/task_scaffold/api/archive/<slug>/file/<name>` | GET | 归档文件内容 |
| `/task_scaffold/api/activity` | GET | 实时活动流 |
| `/task_scaffold/api/mode` | GET/POST | Plan/Build 模式 |

### Filter 钩子

| 钩子 | 用途 |
|------|------|
| `@filter.on_using_llm_tool()` | 记录工具调用到活动流 |
| `@filter.on_llm_response()` | 记录 LLM 回复、token 使用、上下文上限 |
| `@filter.on_agent_done()` | 重置活动流为待命 |
| `@filter.on_llm_tool_respond()` | 自动推进 todo / 归档 |
| `@register_on_llm_request()` | Plan/Build 过滤 + 工作区摘要注入 |

### 工作区摘要注入

`_read_ws_summaries()` 读取 `01_research.md` / `02_design.md` / `04_note.md`：
- 跳过空模板提示行（以 `>` 开头）
- 跳过 Markdown 标题行
- 取前若干条实质内容
- 受 `ws_summary_max_chars` 限制

Plan 模式：提示 LLM “建议先读已有记录”。  
Build 模式：把摘要直接拼进 `extra_user_content_parts`。

### WebUI

`templates/dashboard.html`：独立入口，零前端框架，纯 HTML/CSS/JS。  
`pages/dashboard/index.html`：AstrBot 内置 Plugin Page，JS 同时兼容 `AstrBotPluginPage` bridge 与直连 fallback。

布局：
- 左栏：导航（当前长任务 / 归档 / 标签分类）
- 中栏：当前工作目录 + 任务面板 + Plan-Build 胶囊 + 实时活动流
- 右栏：工作区文件列表 + 文件预览

刷新策略：

| 组件 | 间隔 | 方式 |
|------|------|------|
| 当前任务面板 | 3s | fetch `/api/current` + 缓存比对 |
| 实时活动流 | 1s | fetch `/api/activity` + 增量追加 |
| Plan/Build 模式 | 3s | fetch `/api/mode` |
| 归档列表 | 手动/切换视图/搜索 | fetch `/api/archives` |

### 路径安全

- `safe_name(name)`: 白名单 `^[A-Za-z0-9_\-\.]+$`
- `_safe_path(root, parts)`: 先 `safe_name` 预检，再 `Path.resolve()` + `relative_to` 校验
- 禁止空字符串、Windows 保留名、路径穿越

### 数据文件

#### 00_task_state.json

```json
{
  "slug": "2026-05-31_REV-008",
  "title": "路径穿越修复",
  "cwd": "D:/opencode/myproj",
  "tags": ["security"],
  "updated_at": "2026-05-31T17:00:00",
  "todos": [
    {"content": "审计所有用户输入路径", "status": "completed", "priority": "high"},
    {"content": "增加 safe_name 白名单校验", "status": "in_progress", "priority": "high"}
  ]
}
```

#### activity.jsonl

```json
{"ts": "17:42:15", "agent": "Miria", "status": "执行中", "detail": "调用 safe_edit", "tool": "safe_edit", "task_summary": "D:/opencode"}
{"ts": "17:42:18", "agent": "Miria", "status": "回复中", "detail": "回复 · 381 chars"}
```

## 已知限制

- Plan 模式过滤基于启发式关键词，可能误伤或漏过个别工具，需通过 `extra_exempt_tools` / `extra_write_keywords` 手动修正。
- 自动推进不处理并行多工具结果；只要任一工具明确失败就不推进。
- 工作区文件摘要只取前 N 条非空行，不会自动结构化。
- 系统托盘未实现，已从文档中移除。
