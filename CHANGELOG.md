# Changelog

## v0.5.1 (Unreleased)

### Added
- **归档视图增强**：年/月/周/日折叠 + 分组展开/收起 + 分页加载 + 服务端搜索
- **data_root 配置生效**：支持插件配置与环境变量覆盖数据根目录

### Fixed
- **系统托盘**：移除 README/CHANGELOG/metadata 中未兑现的系统托盘描述
- **title 校验**：JSON Schema 与工具描述一致，`title` 改为可选，移除与首任务内容相同的无效校验
- **工单排版**：中文字符显示宽度计算，避免 ASCII 边框错位
- **Token 统计**：`month_total` 计入缓存 token，与 `session_total` 口径一致
- **Plan 模式**：不再调用全局 `remove_tool`，仅修改本次请求副本，避免误杀读工具后无法恢复
- **路径安全**：增加 slug/file/name 字符白名单，拦截 Windows 特殊字符与空字符串
- **异步 IO**：Web API 热点路径与活动日志写入使用 `asyncio.to_thread`，避免阻塞事件循环
- **轮询频率**：实时活动流改为 1s，与文档一致

### Changed
- **过滤词表文档**：ARCHITECTURE 禁用清单补充 `remove`/`create`/`save`

## v0.5.0 (2026-06-02)

### Added
- **Plan/Build 双模式**：`on_llm_request` 全局过滤写工具 + user_prompt 提示 + 滑动胶囊切换
- **自动进度追踪**：`on_llm_tool_respond` 钩子逐项完成 todo + 提取 CWD
- **cwd 横条**：任务面板上方常驻显示当前工作目录
- **归档详情**：点击归档项展开 todos 列表 + 文件链接预览
- **WebUI 动效**：进度圈跳变 / todo 划入 / 骨架屏 shimmer / 活动流 slideIn
- **125%→137.5% 缩放**：紧凑但不溢出

### Changed
- **术语统一**：任务→长任务、规划/施工→Plan/Build
- **实时活动流**：全量替换→增量追加 + 去重
- **空状态**：纯 CSS 插画 + 垂直居中
- **任务/活动面板**：flex 比例从 2:1 调至 137:63（31.5%）

### Removed
- `_apply_mode` / `_get_tool_map` / `_TOOL_MAP_CACHE` / `_WRITE_TOOL_NAMES` — 被 `on_llm_request` 全局过滤替代
- `event.stop_event()` — 无效，拦不住工具执行
- `deactivate_llm_tool` — Web context 不可达
- **系统托盘** — 原计划实现但未交付，避免文档过度承诺

## v0.4.0 (2026-06-01)

### Added
- **task_list action 参数**：start / update / complete / status 状态机
- **title / tags / cwd 参数**：任务标题 / 标签分类 / 工作目录
- **task_archive 工具**：list / read / search 已归档任务
- **WebUI 仪表盘**：三栏布局 + API 路由 + 实时活动流
- **自动归档**：100% 完成自动 `_do_archive()`
- **stale 缓存展示**：归档后前端保留已完成卡片，不跳空状态
- **活动日志**：`register_on_llm_response` + `on_using_llm_tool` 钩子写 `activity.jsonl`

### Changed
- 工具描述改为行为指令式
- `_root()` 从 `StarTools.get_data_dir()` 改为 `~/.astrbot/data/task_scaffolds`
- Dashboard 从奶油苏打双标签升级为蓝白三栏

## v0.3.0 (2026-05-31)

### Added
- **工作空间脚手架**：`_init_workspace` 自动生成 01~03 + progress.log
- **自动归档**：空列表 [] 或全部完成 → 移动到 archive/
- **summary 字段**：自然语言进度描述
- **tags 字段**：任务标签分类
- **`_validate`**：单 in_progress 约束 + content 检查
- **`_gen_slug`**：自动生成 YYYY-MM-DD_auto-N

### Changed
- 工具描述改为行为指令式
- 首次调用自动生成脚手架
- 返回值增加 `summary` / `files` / `action` 字段

## v0.1.0 (2026-05-31)

- 初始版本：`task_list` 工具 + JSON 持久化 + 脚手架 + 自动归档
- 零外部依赖（纯 `json` + `os` + `shutil`）
- 单文件 `main.py` ~300 行
