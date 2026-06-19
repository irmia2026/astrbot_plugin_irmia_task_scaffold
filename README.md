# irmia_task_scaffold

AstrBot 插件：给 LLM Agent 搭一个**文本工作区**，把多步骤任务的状态、调研、设计、备忘落到文件里，降低上下文被挤掉后“忘记在干什么”的概率。

## 它能做什么

| 能力 | 说明 |
|------|------|
| `task_list` | 启动 / 更新 / 查询 / 完成任务列表，状态写入 `00_task_state.json` |
| 工作区文件 | 自动生成 `01_research.md`、`02_design.md`、`04_note.md`，LLM 可在对应阶段写入 |
| 自动推进 | 普通工具执行成功后，自动把当前 `in_progress` 标记为 `completed` 并开启下一项 |
| 自动归档 | 全部 todo 完成时，自动把 `current/` 移动到 `archive/<slug>/` |
| `task_archive` | LLM 按需搜索 / 读取历史归档 |
| Plan/Build 模式 | Plan 模式从本次请求中移除写工具；Build 模式恢复 |
| WebUI 仪表盘 | 当前任务、实时活动、工作区文件、归档管理 |
| 上下文监控 | 记录 token 使用量，接近上下文上限时提示 LLM 收尾 |

## 安装

把本仓库放到 AstrBot 的 `plugins/` 目录下，重启 AstrBot：

```bash
git clone https://github.com/irmia2026/irmia_task_scaffold.git plugins/astrbot_plugin_irmia_task_scaffold
```

## 工作区结构

```
~/.astrbot/data/task_scaffolds/
├── current/                    # 当前活跃工作区
│   ├── 00_task_state.json      # 任务进度 + 元数据
│   ├── 01_research.md          # 调研笔记（LLM 手动写入）
│   ├── 02_design.md            # 设计文档（LLM 手动写入）
│   ├── 03_work_order.md        # 自动生成的工单
│   ├── 04_note.md              # 备忘（LLM 手动写入）
│   └── progress.log            # 事件日志
├── archive/                    # 已归档工作区
│   └── 2026-05-31_REV-008/
└── state/
    ├── mode.json               # Plan/Build 模式
    ├── activity.jsonl          # 实时活动流
    └── summary.jsonl           # 会话级统计
```

## 工具示例

```python
# 启动一个长任务
task_list(
    action="start",
    title="路径穿越修复",
    cwd="D:/opencode/myproj",
    todos=[
        {"content": "审计所有用户输入路径", "status": "in_progress", "priority": "high"},
        {"content": "增加 safe_name 白名单校验", "status": "pending", "priority": "high"},
        {"content": "补充单元测试", "status": "pending", "priority": "medium"},
    ],
)

# 后续普通工具执行成功会自动推进；也可手动更新
task_list(action="update", todos=[...])

# 查询当前状态
task_list(action="status")

# 全部完成（或钩子自动完成）后归档
task_archive(action="list")
task_archive(action="search", keyword="路径穿越")
task_archive(action="read", slug="2026-05-31_REV-008", file="03_work_order.md")
```

## Plan / Build 模式

- **Plan**：只保留读工具，LLM 只能分析、搜索、查看，不能写入。适合先读代码再动手。
- **Build**：全部工具可用，正常执行。

切换方式：WebUI 右上角滑动胶囊；或手动改 `state/mode.json`。

## WebUI 仪表盘

AstrBot Dashboard 侧边栏会出现插件页入口：**弥亚长任务系统**。点击即可打开。

也支持直接访问：

```
http://localhost:6185/api/plug/task_scaffold/dashboard
```

页面包含：

- 当前任务面板：进度、todo 列表、Plan/Build 切换
- 实时活动流：工具调用与 LLM 回复
- 工作区文件：快速预览 / 用途标签
- 归档面板：年/月/周/日折叠、标签筛选、全文搜索、分页加载

## 配置

`config.yaml` 放在 `~/.astrbot/data/task_scaffolds/config.yaml`：

```yaml
# data_root: "~/.astrbot/data/task_scaffolds"  # 数据根目录
context_limit: 200000          # 上下文上限（首次响应后自动从 provider 读取真实值）
archive_list_limit: 50         # 归档每页最大条目
ws_summary_max_chars: 240      # 注入 prompt 的工作区文件摘要长度
activity_max_lines: 200
summary_max_lines: 100
tokens_max_lines: 500
recent_summary_count: 5
```

## 依赖

纯 Python 标准库。AstrBot 已自带 `quart`。

## 已知限制

- 自动推进只认 `in_progress` → `completed` 的状态跃迁；如果一个工具失败，不会推进。
- Plan 模式靠工具名 / 描述关键词过滤，可能有漏网或误伤，必要时把工具名加入 `extra_exempt_tools` 或 `extra_write_keywords`。
- 工作区文件摘要仅在 Build 模式下注入 prompt，Plan 模式下只提醒读取。
