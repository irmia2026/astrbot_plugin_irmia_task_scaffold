# Changelog

## v0.5.1 (Unreleased)

### Added
- **AstrBot 内置 Plugin Page**：新增 `pages/dashboard/index.html`，在 AstrBot Dashboard 侧边栏直接显示“弥亚长任务系统”入口。
- **归档视图增强**：年/月/周/日折叠、分组展开/收起、分页加载、服务端搜索。
- **工作区文件摘要**：Build/Plan 模式下自动读取 `01_research.md` / `02_design.md` / `04_note.md` 的实质内容并注入 prompt。
- **上下文监控**：token 使用接近 70%/85% 上下文上限时分别给出提示/告警。
- **data_root 配置生效**：支持插件 `config` 中的 `data_root` 覆盖默认数据根目录。

### Fixed
- **Plan 模式兼容性**：与 AstrBot v4.24.2 源码核对，`ProviderRequest.func_tool` 是 `ToolSet` 对象，改为取 `.tools` 过滤并写回，不再全局 `remove_tool`。
- **Plan 模式误伤读工具**：改用工具名安全词 + 英文单词边界正则 + 中文子串关键词三层过滤，只屏蔽本次请求。
- **`_on_tool_done` 无活跃任务报错**：增加 `is_active()` 前置检查，避免读取不存在的 `current/00_task_state.json`。
- **工具响应失败误判**：`tool_result` 为 `None` 视为成功；显式检测 `CallToolResult.isError`；仅对明确失败跳过推进。
- **路径安全**：slug/file/name 增加字符白名单，拦截 Windows 特殊字符与空字符串。
- **异步 IO**：Web API 热点路径与活动日志写入使用 `asyncio.to_thread`。
- **Token 统计**：`month_total` 计入 cached token，与 `session_total` 口径一致。
- **工单排版**：用显示宽度（wcwidth fallback）计算 ASCII 边框，解决中文错位。
- **title 校验**：JSON Schema 与工具描述一致，`title` 改为可选，移除与首任务内容相同的无效校验。
- **轮询频率**：实时活动流改为 1s，与文档一致。

### Changed
- **工具描述压缩**：`_TASK_LIST_DESC` 从约 370 字压缩到约 120 字，减少每次请求消耗的上下文。
- **过滤词表文档**：ARCHITECTURE 禁用清单补充 `remove`/`create`/`save`。
- **文档务实化**：README / CHANGELOG / ARCHITECTURE 移除过度承诺，明确已知限制。

### Removed
- **系统托盘**：README/CHANGELOG/metadata 中移除未兑现的系统托盘描述；代码中无实际实现。

## v0.5.0 (2026-06-02)

### Added
- Plan/Build 双模式
- `on_llm_tool_respond` 自动推进 todo + 提取 CWD
- 自动归档
- WebUI 仪表盘（三栏布局）
- `task_archive` 工具
- 实时活动流

### Changed
- 术语统一为 Plan/Build
- 任务面板显示当前工作目录

## v0.4.0 (2026-06-01)

### Added
- `task_list` 状态机：start / update / complete / status
- title / tags / cwd 参数
- WebUI 仪表盘初版
- 自动归档

## v0.3.0 (2026-05-31)

### Added
- 工作区脚手架：自动生成 01~04 + progress.log
- summary / tags 字段
- `_validate` 单 in_progress 约束
- `_gen_slug` 自动生成 slug

## v0.1.0 (2026-05-31)

- 初始版本：`task_list` + JSON 持久化 + 脚手架 + 自动归档
