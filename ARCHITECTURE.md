# 架构设计

## 目录结构

```
astrbot_plugin_irmia_task_scaffold/
├── main.py                  # 插件入口 + 工具类 + HTTP 路由 + filter 钩子
├── tray.py                  # pystray 系统托盘（独立线程）
├── metadata.yaml            # AstrBot 插件元数据
├── templates/
│   └── dashboard.html       # WebUI 仪表盘（单文件 HTML/CSS/JS，零前端框架）
└── README.md / CHANGELOG.md / ARCHITECTURE.md
```

## 数据流

```
LLM 调用 task_list
       ↓
TaskListTool.call() ──→ 00_task_state.json (current/)
                      → 01_research.md (模板)
                      → 02_design.md (模板)
                      → 03_work_order.md (ASCII 工单)
                      → progress.log (追加)
       ↓
WebUI poll (3s) ←─ GET /api/plug/task_scaffold/api/current
       ↓
dashboard.html render
```

```
LLM 下一轮请求
       ↓
register_on_llm_request() ──→ 检查 _get_mode()
                              plan → 从 request.functions 摘除写工具
                                   → user_prompt 注入提示
```

```
工具执行完成
       ↓
filter.on_llm_tool_respond() ──→ 自动完成当前 todo
                                → 提取 CWD
                                → 检查全部完成 → 自动归档
```

## 核心组件

### TaskListTool (main.py:423)

```python
@dataclass
class TaskListTool(_FT):
    actions: start | update | complete | status
    params: todos[], workspace_slug?, title?, tags?, cwd?
```

状态机：
```
IDLE ──(start)→ TASK ──(update)→ ... ──(complete)→ IDLE
                    ↓ (全部完成)
                自动归档 → IDLE
```

### TaskArchiveTool (main.py:511)

```python
@dataclass  
class TaskArchiveTool(_FT):
    actions: list | read | search
```

纯读操作，遍历 `archive/` 目录。

### Plan/Build 模式

```
WebUI toggle → POST /api/mode → _set_mode() → mode.json
                                              ↓
下次 LLM 请求 → register_on_llm_request()
              → 遍历 request.functions
              → 命中 _WRITE_KEYWORDS 或 _ALWAYS_WRITE → 摘除
              → 跳过 _EXEMPT_TOOLS
              → user_prompt 注入提示
```

工具识别：`_WRITE_KEYWORDS` = 语义关键词（write/edit/delete/execute...），匹配 `tool.description`，不硬编码工具名。

强制封堵：`_ALWAYS_WRITE = {"astrbot_execute_shell", "astrbot_execute_python"}` — 描述漏了也永禁。

本插件豁免：`_EXEMPT_TOOLS = {"task_list", "task_archive"}` — 自身工具在 plan 模式仍可用。

### HTTP 路由

| 路由 | 方法 | 说明 |
|------|------|------|
| `/task_scaffold/dashboard` | GET | WebUI 仪表盘 HTML |
| `/task_scaffold/api/current` | GET | 当前任务 JSON |
| `/task_scaffold/api/current/file/<name>` | GET | 当前工作空间文件内容 |
| `/task_scaffold/api/archives` | GET | 归档列表 JSON |
| `/task_scaffold/api/archive/<slug>/summary` | GET | 归档详情 JSON |
| `/task_scaffold/api/archive/<slug>/file/<name>` | GET | 归档文件内容 |
| `/task_scaffold/api/activity` | GET | 实时活动流（最近 20 条） |
| `/task_scaffold/api/mode` | GET/POST | 读取/切换 Plan/Build 模式 |

AstrBot 自动添加 `/api/plug/` 前缀。

### Filter 钩子

| 钩子 | 用途 |
|------|------|
| `@filter.on_using_llm_tool()` | 活动日志（记录每次工具调用） |
| `@filter.on_llm_response()` | 活动日志（记录 LLM 回复） |
| `@filter.on_agent_done()` | 活动日志（记录待命状态） |
| `@filter.on_llm_tool_respond()` | **自动进度**：完成当前 todo + 提取 CWD + 自动归档 |
| `@register_on_llm_request()` | **Plan 模式**：过滤写工具 + 注入提示 |

### WebUI (dashboard.html)

三栏布局（220px | flex | 300px），137.5% 缩放，零外部前端依赖。

```
┌─ 左栏 ────┬─ 中栏 ─────────────────┬─ 右栏 ────┐
│ 长任务     │ 🟢 当前工作目录: D:/...│ 工作区文件 │
│ 当前长任务 │ ┌─ 当前长任务 ────────┐│ 03_work.. │
│ 归档       │ │ hero + 进度圈       ││ 02_design │
│            │ │ todos 列表          ││ 01_res..  │
│ 归档分类   │ │         [Plan|Build]││ progress  │
│ 全部       │ └────────────────────┘│           │
│ devkit     │ ┌─ 实时活动 ─────────┐│ 文件预览  │
│            │ │ ...                ││           │
│ 🟢 在线    │ └────────────────────┘│           │
└───────────┴───────────────────────┴───────────┘
```

### 系统托盘 (tray.py)

- pystray 32px 实心圆图标（Pillow 绘制）
- 颜色：plan=蓝 / build=绿 / 空闲=灰
- 2 秒轮询 `mode.json` + `00_task_state.json`
- 悬停 tooltip：`Build · 3/7 · safe_edit`
- 右键菜单：切换 Plan/Build / 打开仪表板 / 退出

## 数据文件

### 00_task_state.json

```json
{
  "slug": "2026-05-31_REV-008",
  "title": "文档渲染调研",
  "cwd": "D:/opencode",
  "tags": ["devkit", "debug"],
  "updated_at": "2026-05-31T17:00:00",
  "todos": [
    {"content": "调研 Markdown 方案", "status": "completed", "priority": "high"},
    {"content": "设计架构", "status": "in_progress", "priority": "high"}
  ]
}
```

### activity.jsonl

```json
{"ts": "17:42:15", "agent": "Miria", "status": "执行中", "detail": "调用 safe_edit", "tool": "safe_edit", "task_summary": "D:/opencode"}
{"ts": "17:42:18", "agent": "Miria", "status": "回复中", "detail": "回复 · 381 chars"}
```

### mode.json

```json
{"mode": "plan"}
```

## 刷新周期

| 组件 | 间隔 | 方式 |
|------|------|------|
| 当前任务面板 | 3s | fetch `/api/current` + JSON 缓存比对 |
| 实时活动流 | 3s | fetch `/api/activity` + 增量追加 + 去重 |
| Plan/Build 模式 | 3s | fetch `/api/mode` |
| 系统托盘 | 2s | 读文件 |
