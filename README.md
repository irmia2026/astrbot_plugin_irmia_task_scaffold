# irmia_task_scaffold

为 LLM Agent 提供**方法论文本工作空间**，解决多步骤任务中上下文窗口驱逐导致的"忘记要干什么"问题。

## 核心功能

| 功能 | 说明 |
|------|------|
| `task_list` 工具 | 全量覆写任务状态（start/update/complete/status），持久化到 `00_task_state.json` |
| 工作空间脚手架 | 首次调用自动生成 01_research.md / 02_design.md / 03_work_order.md / progress.log |
| 自动进度追踪 | `on_llm_tool_respond` 钩子自动逐项完成 todo + 提取 CWD |
| 自动归档 | 全部完成 → 自动移动到 `archive/<slug>/` |
| `task_archive` 工具 | list/read/search 已归档任务，LLM 按需召回历史 |
| Plan/Build 双模式 | Plan 模式全局屏蔽写工具（`on_llm_request` 过滤 function list），Build 恢复 |
| WebUI 仪表盘 | 三栏布局：当前长任务/实时活动流/文件浏览器/归档面板 + Plan/Build 滑动胶囊 |
| 系统托盘 | pystray 托盘图标，颜色区分模式，悬停显示进度，右键快捷操作 |
| `summary` 字段 | 自然语言进度描述 + 下一步提示 |

## 安装

将 `astrbot_plugin_irmia_task_scaffold/` 目录放入 AstrBot 的 `plugins/` 目录，重启即可。

```bash
git clone https://github.com/irmia2026/irmia_task_scaffold.git plugins/astrbot_plugin_irmia_task_scaffold
```

可选依赖：`pystray` + `Pillow`（系统托盘功能，未安装时静默跳过）。

## 工作空间结构

```
{home}/.astrbot/data/task_scaffolds/
├── current/                       ← 当前活跃工作空间
│   ├── 00_task_state.json         ← 任务进度 + 元数据（每次覆写）
│   ├── 01_research.md             ← 调研笔记（LLM 自主填充）
│   ├── 02_design.md               ← 设计文档（LLM 自主填充）
│   ├── 03_work_order.md           ← 自动生成的工单骨架
│   └── progress.log               ← ISO 时间戳事件日志
├── archive/
│   └── 2026-05-31_REV-008/        ← 已完成工作空间归档
└── state/
    ├── mode.json                  ← Plan/Build 模式状态
    └── activity.jsonl             ← 实时活动流
```

## 工具使用

### task_list

```python
# 启动任务
task_list(action="start", todos=[
  {"content": "调研 Markdown 渲染方案", "status": "pending", "priority": "high"},
  {"content": "设计插件架构", "status": "pending", "priority": "high"},
], title="文档渲染调研", cwd="D:/project")

# 更新进度（也可不调——钩子自动完成）
task_list(action="update", todos=[...])

# 查询状态
task_list(action="status")

# 生成汇报
task_list(action="complete")
```

### task_archive

```python
# 列出最近归档
task_archive(action="list")
# 搜索
task_archive(action="search", keyword="路径穿越")
# 读取
task_archive(action="read", slug="2026-05-31_REV-008", file="03_work_order.md")
```

## Plan/Build 模式

| 模式 | 行为 |
|------|------|
| Plan | `on_llm_request` 从 function list 中摘除写工具，LLM 看不到写工具。system_prompt 提示用户切换 |
| Build | 全部工具可用 |

WebUI 任务面板右下角滑动胶囊切换，或右键系统托盘图标。

## WebUI

浏览器打开 `http://localhost:6185/api/plug/task_scaffold/dashboard`

- **左栏**：导航（当前长任务 / 归档 / 标签分类）+ AstrBot 在线状态
- **中栏上**：当前工作目录横条 + 任务面板（进度圈 / todo 列表 / Plan-Build 胶囊）
- **中栏下**：实时活动流（增量追加 + 去重 + 滑入动画）
- **右栏**：工作区文件浏览器 + 文件内容预览
- **归档面板**：按月分组 / 标签筛选 / 全文搜索 / 点击展开详情

## 依赖

纯标准库（`json` + `os` + `shutil` + `datetime` + `threading` + `tkinter`）。

可选：`pystray` + `Pillow`（托盘图标）、`quart`（AstrBot 自带）。
