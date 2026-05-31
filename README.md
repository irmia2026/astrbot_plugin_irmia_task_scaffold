# irmia_task_scaffold

为 LLM Agent 提供**方法论文本工作空间**，解决多步骤任务中上下文窗口驱逐导致的"忘记要干什么"问题。

## 核心功能

| 功能 | 说明 |
|------|------|
| `task_list` 工具 | 全量覆写任务状态，持久化到 `00_task_state.json` |
| 工作空间脚手架 | 首次调用自动生成调研区 / 设计区 / 工单区 / 进度日志 |
| 单 in_progress 约束 | 同时最多一个进行中任务，多则报错 |
| 自动归档 | 全部完成 / 取消 / 清空 → 移动到 `archive/<slug>/` |
| summary 字段 | 自然语言进度描述 + 下一步提示 |

## 工作空间结构

```
data/task_scaffolds/
├── current/                       ← 当前活跃工作空间
│   ├── 00_task_state.json         ← 任务进度（每次覆写）
│   ├── 01_research.md             ← 调研笔记（LLM 自主填充）
│   ├── 02_design.md               ← 设计文档（LLM 自主填充）
│   ├── 03_work_order.md           ← 自动生成的工单骨架
│   └── progress.log               ← ISO 时间戳事件日志
└── archive/
    └── 2026-05-31_auto-1/         ← 已完成工作空间归档
```

## LLM 触发示例

### 创建任务

```
调用 task_list(todos=[
  {"content": "调研 Markdown 渲染方案", "status": "pending", "priority": "high"},
  {"content": "设计插件架构", "status": "pending", "priority": "high"},
  {"content": "实现 report 工具", "status": "pending", "priority": "medium"},
])
```

→ 自动生成 `current/` 目录 + 5 个脚手架文件

### 开始工作

```
调用 task_list(todos=[
  {"content": "调研 Markdown 渲染方案", "status": "in_progress", "priority": "high"},
  {"content": "设计插件架构", "status": "pending", "priority": "high"},
  {"content": "实现 report 工具", "status": "pending", "priority": "medium"},
])
```

→ 更新 `00_task_state.json` + 追加 `progress.log`

### 标记完成

```
调用 task_list(todos=[
  {"content": "调研 Markdown 渲染方案", "status": "completed", "priority": "high"},
  {"content": "设计插件架构", "status": "in_progress", "priority": "high"},
  {"content": "实现 report 工具", "status": "pending", "priority": "medium"},
])
```

### 全部完成后自动归档

→ `current/` → `archive/2026-05-31_auto-1/`

### 清空并归档

```
调用 task_list(todos=[])
```

### 指定工作空间名

```
调用 task_list(todos=[...], workspace_slug="2026-05-31_REV-008")
```

## 返回值

```json
{
  "ok": true,
  "count": 3,
  "pending": 1,
  "in_progress": 1,
  "completed": 1,
  "cancelled": 0,
  "summary": "已完成 1/3 | 当前: 设计插件架构 | 待办 1 项",
  "workspace": "task_scaffolds/current/",
  "action": "state_updated"
}
```

## 安装

将 `irmia_task_scaffold/` 目录放入 AstrBot 的 `plugins/` 目录，重启即可。

## 依赖

零外部依赖 — 纯 `json` + `os` + `shutil` 标准库。
