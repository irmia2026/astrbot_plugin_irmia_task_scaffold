# 架构设计

## 目录结构

```
astrbot_plugin_irmia_task_scaffold/
├── main.py                  # 插件入口 + Filter 钩子 + 模式管理 + 方法论文件提醒
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
                      → 01_research.md (模板，带"使用时机"引导)
                      → 02_design.md (模板，带"使用时机"引导)
                      → 03_work_order.md (ASCII 工单)
                      → 04_note.md (模板，带"使用时机"引导)
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
WebUI toggle → POST /api/mode → _set_mode()
                                              ↓
                              写入 mode.json
                                              ↓
下次 LLM 请求 → register_on_llm_request()
              → 读取 mode.json
              → plan: 从 request.functions 摘除写工具
              → build: 保留全部工具
              → 注入 user_prompt 提示（含工作区文件状态）
```

**核心机制**：`on_llm_request` 中直接修改 `request.functions` 列表，
通过工具描述关键词匹配（`write`, `edit`, `patch`, `modify`, `delete`, `commit`, `push`, `deploy`, `upload`, `publish`, `release`, `merge`, `install`, `uninstall`, `rollback`, `unzip` 等英文关键词 + 中文写入关键词）摘除写工具。

**模式提醒**：每次 LLM 请求时，自动检测工作区方法论文件（01_research/02_design/04_note）是否为空，
在 user_prompt 中注入针对性提醒：
- Plan 模式："建议先读取 01_research.md / 02_design.md 了解已有结论"
- Build 模式："请及时用 safe_edit 编辑方法论文件记录关键结论"

**禁用清单**（关键词匹配 + 工具名安全词）：
- 英文关键词（按单词边界匹配）：`write`, `edit`, `patch`, `modify`, `delete`, `commit`, `push`, `deploy`, `upload`, `publish`, `release`, `merge`, `install`, `uninstall`, `rollback`, `unzip`
- 中文关键词（子串匹配）：`部署`, `安装`, `删除`, `写入`, `创建`, `修改`, `编辑`, `执行`, `运行`, `下载`, `上传`, `提交`, `推送`, `发布`, `合并`, `卸载`, `回滚`, `解压`, `压缩`, `重启`
- 工具名安全词（保留读工具）：`read`, `search`, `list`, `get`, `query`, `find`, `show`, `browse`, `preview`, `check`, `fetch`, `dump`, `cat`, `echo`, `lookup`, `print`, `stat`, `describe`, `explain`, `inspect`, `peek`, `view`, `glob`, `grep`, `ls`, `walk`, `scan`, `trace`
- 强制禁用：`astrbot_execute_shell`, `astrbot_execute_python`
- 豁免：`task_list`, `task_archive`

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
| `@register_on_llm_request()` | **模式同步+文件提醒**：检测 mode.json + 检查工作区方法论文件空状态 + 注入针对性提示 |

### WebUI (dashboard.html)

三栏布局（220px | flex | 300px），137.5% 缩放，零外部前端依赖。

```
┌─ 左栏 ────┬─ 中栏 ─────────────────┬─ 右栏 ────┐
│ 长任务     │ 🟢 当前工作目录: D:/...│ 工作区文件 │
│ 当前长任务 │ ┌─ 当前长任务 ────────┐│ 工单      │
│ 归档       │ │ hero + 进度圈       ││ 设计      │
│            │ │ todos 列表          ││ 调研      │
│ 归档分类   │ │         [Plan|Build]││ 备忘      │
│ 全部       │ └────────────────────┘│ 状态      │
│ devkit     │ ┌─ 实时活动 ─────────┐│ 日志      │
│            │ │ ...                ││           │
│ 🟢 在线    │ └────────────────────┘│ 文件预览  │
└───────────┴───────────────────────┴───────────┘
```


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
| 实时活动流 | 1s | fetch `/api/activity` + 增量追加 + 去重 |
| Plan/Build 模式 | 3s | fetch `/api/mode` |
| 归档列表 | 手动/切换视图时 | fetch `/api/archives` |
