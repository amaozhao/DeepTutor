# DeepTutor 规范治理 Top 20

本文档记录当前项目最值得优先治理的 20 个规范问题。它不是重构执行方案，也不是要求一次性大拆代码；目标是给后续治理排优先级，先处理风险最大、回报最高、最容易造成回归的位置。

审计范围基于当前仓库静态扫描和关键文件抽样阅读，重点查看了文件体量、职责边界、异常处理、异步任务生命周期、配置来源、认证授权、出网访问、密钥处理、前端状态组织和命名规范。

## 判定原则

- 优先处理会影响认证、数据隔离、密钥、出网访问、长任务稳定性的规范问题。
- 优先处理“单文件过大且承载多个职责”的位置，因为它们最容易在小改动中产生隐性回归。
- 不建议做全仓一次性重命名或大规模搬文件。历史命名先记录例外；新文件和被修改文件先执行规范。
- 每个治理项都应配套最小验证：单元测试、集成测试或手工回归说明，避免只做形式化调整。

## Top 20

### 1. 知识库 API 路由过大，职责边界不清

证据：`deeptutor/api/routers/knowledge.py` 原约 2737 行，是 API 层最大文件之一。当前已抽出上传/路径安全逻辑到 `deeptutor/knowledge/uploads.py`，抽出 raw 文件管理 helper 到 `deeptutor/knowledge/rawfiles.py`，抽出 Provider 校验到 `deeptutor/knowledge/providers.py`，抽出后台任务主体到 `deeptutor/knowledge/tasks.py`，并把 RAG 配置、KB 配置、外部知识源连接、已绑定 linked folder 管理、progress/task stream 分别挂到 `deeptutor/api/routers/rag.py`、`deeptutor/api/routers/knowledge_config.py`、`deeptutor/api/routers/knowledge_links.py`、`deeptutor/api/routers/knowledge_linked.py`、`deeptutor/api/routers/knowledge_progress.py`；主路由文件约 948 行，剩余职责已明显收敛但仍可继续细拆。抽样扫描显示它仍至少承担这些职责：

- 路由和响应模型：`KnowledgeBaseInfo`、`SupportedFileTypesInfo` 以及几十个 HTTP/WebSocket endpoint。
- 上传和文件系统写入：路由仍编排上传入口；zip 解压、目录上传、文件名清洗已经下沉到 `knowledge/uploads.py`。
- 知识库生命周期：创建、删除、默认知识库、详情、列表、retry、reindex。
- RAG Provider 配置：Provider/Pipeline 配置已下沉到 `api/routers/rag.py`，KB 自身 `/configs*` 已下沉到 `api/routers/knowledge_config.py`。
- 后台任务：初始化、上传处理、reindex 的主体逻辑已下沉到 `knowledge/tasks.py`，主路由只保留后台任务挂载入口。
- 多用户访问边界：`assert_writable()`、`resolve_kb()`、`current_kb_manager()` 等权限和资源解析入口。
- 外部/本地知识库连接：顶层连接入口已下沉到 `api/routers/knowledge_links.py`，已绑定 KB 的 linked folder 管理/同步已下沉到 `api/routers/knowledge_linked.py`。

问题：这不是单纯“文件长”的问题，而是 HTTP 适配、权限判断、后台任务编排和知识库业务规则曾集中在同一文件内互相引用。当前拆分已经降低了上传、raw 文件、配置、外部连接、progress/task stream、后台任务主体对主路由的污染；后续风险主要来自核心 CRUD/upload/reindex 入口仍共享多用户解析、Provider 绑定和状态更新 helper。

治理目标：继续把 `knowledge.py` 收敛成薄路由层。路由只做参数接收、权限依赖、HTTP 错误映射和调用应用服务；后续若继续治理，应优先把 lifecycle/raw/CRUD 入口拆到更窄 router 或应用服务中。

任务规划：

1. 已完成第一轮行为保护和低风险拆分：
   - 已运行 `tests/api/routers/test_knowledge.py`、`tests/api/routers/test_knowledge_config.py`、`tests/api/routers/test_knowledge_links.py`、`tests/api/routers/test_rag.py` 和 `tests/knowledge/test_uploads.py`。
   - 已抽出上传、zip 解压、目录上传、文件名清洗、重复文件校验到 `deeptutor/knowledge/uploads.py`。
   - 已抽出 raw 文件列表、创建文件夹、移动文件/文件夹到 `deeptutor/knowledge/rawfiles.py`。
   - 已抽出 Provider ready/format 校验到 `deeptutor/knowledge/providers.py`。
   - 已抽出 RAG Provider/Pipeline 配置路由到 `deeptutor/api/routers/rag.py`，保持 `/api/v1/knowledge/...` URL 不变。
   - 已抽出 KB 配置路由到 `deeptutor/api/routers/knowledge_config.py`，保持 `/api/v1/knowledge/...` URL 不变。
   - 已抽出顶层外部知识源连接路由到 `deeptutor/api/routers/knowledge_links.py`，保持 `/api/v1/knowledge/...` URL 不变。
   - 已抽出已绑定 linked folder 管理/同步路由到 `deeptutor/api/routers/knowledge_linked.py`，保持 `/api/v1/knowledge/...` URL 不变。
   - 已抽出 progress/WebSocket 和 task log 查询路由到 `deeptutor/api/routers/knowledge_progress.py`，保持 `/api/v1/knowledge/...` URL 不变。
   - 已抽出初始化、上传处理、reindex 后台任务主体到 `deeptutor/knowledge/tasks.py`，主路由保留同名导入入口以兼容现有调用和测试。
   - 已做第一轮测试归位：直接对应 `deeptutor/api/routers/*` 的 API router 测试移动到 `tests/api/routers/`，上传 helper 测试移动到 `tests/knowledge/test_uploads.py`。这不是全仓测试层级重组；历史测试仍按顶层包或行为域混合组织，后续只应随代码拆分增量归位。
2. 后续继续补行为保护，尤其覆盖：
   - 普通知识库列表、详情、创建、删除。
   - 多用户写权限：无权限用户不能上传、删除、reindex。
   - Provider 绑定：上传时请求 provider 与 KB provider 不一致要拒绝。
   - reindex/retry/background task 返回 task id 和进度状态。
3. 如继续治理，优先把剩余核心入口按 lifecycle/raw/CRUD 继续窄化；不要先改 URL，不要同时改前端调用。

验收标准：

- 对外 API 路径和响应字段保持兼容，前端无需同步大改。
- `deeptutor/api/routers/knowledge.py` 已不再包含 zip 解压、上传路径清洗、RAG Provider 配置、KB 配置、顶层外部连接主体逻辑、已绑定 linked folder 同步逻辑、progress/WebSocket/task stream 逻辑和后台任务主体逻辑。
- 多用户权限检查仍在每个写入口执行，不能因为拆模块绕过 `assert_writable()`。
- 文件路径安全测试覆盖 raw 文件浏览、预览、下载、移动和 zip 解压。
- 每轮迁移后运行知识库相关 API 测试，并至少手工验证创建 KB、上传文件、查看进度、预览文件、reindex。

### 2. TurnRuntime 过大，长任务生命周期和异常边界耦合

证据：`deeptutor/services/session/turn_runtime.py` 原约 2090 行，当前已把附件准备、stream event 解析、terminal event 合成、buffered event 落库、workspace event mirror、payload/title 归一化、follow-up 上下文处理拆到 `deeptutor/services/session/attachments.py`、`events.py`、`payloads.py`、`followup.py`，并把对应测试拆到 `tests/services/session/test_attachments.py`、`test_events.py`、`test_payloads.py`、`test_followup.py`。主 runtime 仍约 1519 行，并包含多处 `asyncio.create_task` 和宽泛 `except Exception`。

问题：会话 turn 执行、状态推送、取消、上下文构建、错误兜底、持久化更新集中在一个模块，导致失败路径难以验证。长任务一旦泄漏或吞错，用户侧表现会是“卡住”“结果丢失”“状态不一致”。

治理动作：已先拆出纯 helper 并归位测试，避免继续扩大 `turn_runtime.py`。下一轮再处理任务监督、事件推送、持久化更新等仍和长任务生命周期耦合的部分；每轮都要先补或保留取消、失败、断连、重试的回归测试。

### 3. 认证路由同时承担登录、注册、管理员和导入导出

证据：`deeptutor/api/routers/auth.py` 原约 1620 行，当前已把管理员邀请码管理拆到 `deeptutor/api/routers/invites.py`，把个人资料、头像上传/读取、自助导出/注销拆到 `deeptutor/api/routers/profile.py`，把管理员用户列表、创建、导入/导出、禁用、重置密码、强制登出、删除和角色变更拆到 `deeptutor/api/routers/users.py`；对应测试已归位到 `tests/api/routers/test_invites.py`、`tests/api/routers/test_profile.py` 和 `tests/api/routers/test_users.py`。`auth.router` 继续保持 `/api/v1/auth/invites`、`/api/v1/auth/profile...`、`/api/v1/auth/avatar/{user_id}`、`/api/v1/auth/users...` URL 不变。主 auth 路由约 760 行，继续覆盖认证依赖、状态、登录/登出和公开注册逻辑。

问题：认证和用户管理属于高风险边界，文件过大让权限判断、公开接口和管理员接口难以审计。后续增加 SaaS 能力时，最容易在这里产生越权或绕过。

治理动作：已完成 invites、profile/avatar 和 admin users 拆分，并补上新拆模块的镜像测试；后续如果继续治理，优先把公开注册 challenge/注册流程从 session/login 依赖中拆出。每个公开接口都要有权限测试，且保持 `/api/v1/auth/...` 路径兼容。

### 4. 前端聊天主页面和上下文过大

证据：
- `web/app/(workspace)/home/[[...sessionId]]/page.tsx` 原约 2193 行，当前约 755 行。
- `web/context/UnifiedChatContext.tsx` 原约 1885 行，当前约 654 行。
- `web/context/QuizFollowupContext.tsx` 当前约 465 行。
- `web/components/quiz/FollowupChatComposer.tsx` 当前约 370 行。

已完成拆分：
- 纯数据和 payload helper：capability/tool catalog、附件转换/筛选、session/message hydration、title、引用 payload、欢迎语、消息区样式、发送计划、保存到 Notebook、capability query/storage/mode/selection、默认 LLM 选择、connected agent、quiz follow-up 发送计划、可视化 prefill 事件解析。
- 页面 hook：菜单外部点击、session title 编辑、能力配置状态和自动打开 Activity、enabled tools 同步、欢迎语初始化、URL query 初始化、引用选择器、URL session 加载、附件/拖拽/预览、KB/LLM 资源加载、默认 LLM 选择、connected agent 选择、viewer panel、可视化 prefill 桥接。
- Context helper：chat state/reducer、transport runner action、runner/timer cleanup、draft session 初始化、start-turn request、ask_user/regenerate/cancel 命令、分支编辑/选择、session detail 归一化、Provider 副作用、selector、quiz follow-up thread 状态转换。
- 展示组件：顶部 header、空会话欢迎视图、引用选择器组、面板桥接组件、头部按钮。
- 测试：对应 helper 覆盖在 `web/tests/lib/chat/*`、`web/tests/context/chat/*`、`web/tests/context/quiz/followup.test.ts` 和 `web/tests/quiz-question-type.test.ts`。

问题：页面、状态管理、网络请求、流式事件和 UI 控制耦合，导致聊天页任何小改都可能影响登录后主流程。

治理动作：已先拆出可测试的纯 helper、页面 hook、Context reducer/action helper 和低风险展示组件，避免继续扩大聊天页和上下文。暂不强拆完整 runner hook；WebSocket 生命周期、重连和错误提示仍需要更细的回归覆盖后再动。

任务规划：

1. 已完成第一轮行为保护和低风险拆分：
   - 已把聊天页内的纯数据转换、发送 payload、标题、引用、保存 Notebook、欢迎语、样式计算等逻辑拆到 `web/lib/chat/*`。
   - 已把菜单、session route、引用选择器、资源加载、附件、viewer panel、prefill、欢迎语、connected agent 等页面副作用拆到 `web/hooks/chat/*`。
   - 已把聊天上下文中的 reducer/action、session hydration、runner 事件、命令、分支编辑、selector、初始化副作用拆到 `web/context/chat/*`。
   - 已把 quiz follow-up 的线程状态转换拆到 `web/context/quiz/followup.ts`。
   - 已把聊天页 header、欢迎区、引用选择器和面板桥接拆成 `web/components/chat/home/*` 展示组件。
   - 已补充对应 helper 测试，并运行前端 lint、typecheck 和 node 测试。
2. 后续如果继续治理，优先补 WebSocket 生命周期回归覆盖：
   - 连接失败、重试、关闭后的错误提示。
   - `done` 后延迟断开期间的 `session_meta` 更新。
   - regenerate 被后端拒绝时恢复上一个 assistant 消息。
   - session 切换、URL 加载和 draft session 初始化的边界情况。
3. 测试补足前不要继续强拆完整 runner hook；这部分风险高，当前保留在 Provider 内更容易验证行为一致。

验收标准：

- `web/app/(workspace)/home/[[...sessionId]]/page.tsx` 不再直接承载页面初始化和外部点击等副作用，主要负责组合 hook、上下文和展示组件。
- `web/context/UnifiedChatContext.tsx` 已不再包含 reducer、selector、session hydration、runner action、命令构造和分支计算的主体实现。
- `web/context/QuizFollowupContext.tsx` 已不再包含 follow-up 线程状态转换主体实现。
- 新拆出的 helper 都有对应测试覆盖，至少覆盖 payload/状态转换/命令构造/selector/runner action 等非 UI 逻辑。
- 前端 `lint`、`tsc --noEmit`、`test:node` 通过。

### 5. LLM 配置和进程环境变量写入分散

证据：`deeptutor/services/config/runtime_settings.py` 会统一导出非模型运行时环境。原先 `deeptutor/services/llm/client.py`、`deeptutor/services/llm/config.py`、`deeptutor/services/llm/executors.py`、`deeptutor/services/llm/provider_core/openai_compat_provider.py` 也会在 LLM 请求路径或 import-time 直接写入 `os.environ`；当前已移除这些 LLM 层写入，LLM 配置改为通过显式参数传给 Provider/SDK。

问题：项目已经明确运行时配置主要来自 `data/user/settings/*.json`。如果 LLM Provider 在多个位置隐式写进程环境，后续多用户、多 Provider、热切换模型时会出现串配置、脏状态和不可复现问题。

治理动作：已把“设置文件到 Provider 参数”的路径收敛到显式配置对象和 Provider 参数；Provider 内部不再修改全局环境变量。保留外部环境变量读取兼容入口，但不在 LLM 请求路径中反向写全局环境。

任务规划：

1. 先锁定边界：
   - `runtime_settings.export_runtime_settings_to_env()` 只负责非模型运行时配置导出，例如端口、认证、CORS、共享状态和解析/RAG 辅助配置。
   - LLM 运行时配置以 `resolve_llm_runtime_config()` / `get_llm_config()` 返回的显式参数为准。
   - `factory -> provider_factory -> Provider` 调用链通过参数传递 `api_key`、`base_url/effective_url`、`extra_headers`、`reasoning_effort` 和 `context_window`。
2. 第一轮治理只处理 LLM 层全局 env 写入：
   - 移除 `deeptutor/services/llm/config.py` 的 import-time / `initialize_environment()` OPENAI_* 写入。
   - 移除 `deeptutor/services/llm/client.py` 初始化时的 OPENAI_* 写入。
   - 移除 `deeptutor/services/llm/executors.py` 和 `deeptutor/services/llm/provider_core/openai_compat_provider.py` 的 provider env 写入。
   - 保留读取外部环境变量的兼容入口；只禁止 Provider 在请求路径中反向写全局环境。
3. 补最小回归测试：
   - `initialize_environment()` 不再写 `OPENAI_API_KEY` / `OPENAI_BASE_URL`。
   - `LLMClient(config)` 不再写 `OPENAI_*`。
   - OpenAI-compatible Provider 初始化不再写 provider env key / env extras。
   - SDK executor 完成调用时不再写 provider env key，同时仍把 key/base 显式传给 SDK client。

验收标准：

- `rg "os\\.environ\\[|os\\.environ\\.setdefault" deeptutor/services/llm` 不再出现 LLM 请求路径写入。
- `runtime_settings.py` 仍是进程环境导出的唯一配置边界。
- LLM Provider 构造和调用仍通过显式参数拿到 API key、base URL、headers 和模型参数。
- 相关 LLM/config 测试通过。

### 6. 宽泛异常处理过多，容易吞掉真实错误

证据：`deeptutor/services/session/turn_runtime.py`、`deeptutor/services/session/pocketbase_store.py`、`deeptutor/api/main.py`、`deeptutor/multi_user/identity.py`、多个 partner channel 文件中存在大量 `except Exception` 和部分空 `pass`。

问题：宽泛捕获在边界层可以存在，但业务层大量使用会把数据错误、权限错误、网络错误和代码 bug 混成“失败兜底”，排查成本高。

治理动作：按模块建立允许清单：边界层可以捕获并转换为领域错误；核心服务层应捕获具体异常并保留日志上下文。

任务规划：

1. 第一轮只治理“静默吞错”，不全仓机械替换 `except Exception`：
   - `except Exception: pass` 或 `except Exception: return fallback` 必须补日志、缩窄异常类型，或确认是边界容错。
   - 网络/第三方 SDK 边界允许宽泛捕获，但必须带模块、操作、资源 id 等上下文。
   - 核心业务层不要把数据损坏、权限错误、序列化错误伪装成空结果。
2. 优先级：
   - 认证/多用户：不能静默吞掉 auth secret、用户文件、锁文件错误。
   - 会话存储：不能把 PocketBase 查询失败静默当成 session 不存在。
   - turn runtime：取消、事件落库、状态更新失败要保留上下文。
   - partner channel：外部平台适配层保留容错，但要有日志，避免后台任务无声失败。
3. 第一轮代码治理范围：
   - 修复 `PocketBaseSessionStore.get_session()` 静默吞掉查询异常的问题。
   - 修复 `pocketbase_store._json_loads()` 静默吞掉无效 JSON 的问题。
   - 修复 `PocketBaseSessionStore.list_active_turns()` 静默吞掉查询异常的问题。
   - 修复 Postgres shared-state 启用时本地 auth secret seed 读取失败静默降级的问题。
   - 修复 turn runtime 中 question bank entry 和 enabled optional tools 读取失败静默降级的问题。
   - 先不动所有 partner channel；数量太大，后续按 channel 生命周期治理逐个处理。

验收标准：

- 被治理的吞错点有日志或具体异常处理，不再无上下文静默返回 fallback。
- 会话查询失败、active turn 查询失败、JSON 解析失败和 auth secret seed 读取失败有最小测试覆盖。
- 保持原有对外行为：PocketBase 查询失败仍返回 `None`，无效 JSON 仍使用默认值，但日志可见。
- 相关 session 测试通过。

### 7. Partner 多渠道任务生命周期分散

证据：`deeptutor/services/partners/manager.py` 约 1291 行；`deeptutor/partners/channels/weixin.py` 约 1564 行；`feishu.py`、`telegram.py`、`mochat.py`、`zulip.py` 等 channel 文件也较大，并存在多个后台 task。

问题：多渠道连接、轮询、keepalive、消息分发、fallback timer 分散在 channel 和 manager 中，缺少统一 task registry 和关闭语义时，部署后容易产生后台任务泄漏或重复消费。

治理边界：

- MVP 不做所有 channel 的协议重写；channel 内部的轮询、typing、fallback worker 暂时仍由各 channel 自己管理。
- 先治理 `PartnerManager` 自己创建的后台任务：runner、outbound router、channel listener、web live turn。
- 后续如果某个 channel 出现泄漏或重复消费，再按 channel 单独收敛，不提前设计全局 supervisor 框架。

治理动作：

- 将 `PartnerManager` 内部的 task 创建集中到 `_create_partner_task()`，避免新增 manager 级后台任务绕过 `PartnerInstance.tasks`。
- 将停止逻辑集中到 `_cancel_partner_tasks()`，统一 cancel / wait / timeout 日志。
- `start_web_turn()` 创建的 live turn task 必须纳入 `PartnerInstance.tasks`，确保 `stop_partner()` 会一起取消。
- `reload_channels()` 只重启 `partner:{id}:ch:*` listener task，runner/router/web turn 不被误杀。

验收标准：

- `PartnerManager` 中除 task helper 自身外，不再直接散落 manager 级 `asyncio.create_task()`。
- `stop_partner()` 会尝试取消 `PartnerInstance.tasks` 中全部 manager-owned task，并清空 registry。
- `reload_channels()` 只取消 channel listener task，并继续通过同一 task helper 启动新 listener。
- web live turn task 被 `PartnerInstance.tasks` 追踪，partner 停止时不会遗留独立运行的 web turn。
- partner runtime / reload 相关定向测试通过。

### 8. SQLite 会话存储模块过大

证据：`deeptutor/services/session/sqlite_store.py` 原约 1844 行，当前约 785 行；已新增 `deeptutor/services/session/schema.py` 承接 SQLite 建表和迁移逻辑，`deeptutor/services/session/turns.py` 承接 turns / turn_events 同步 SQL，`deeptutor/services/session/notebook.py` 承接 notebook entries / categories 同步 SQL，`deeptutor/services/session/messages.py` 承接 message / import / regenerate 相关同步 SQL。

问题：持久化层如果同时包含 schema、迁移、查询、导入导出、会话/消息/附件/笔记等逻辑，会让数据兼容性变更变得危险。

治理边界：

- MVP 不拆 `SQLiteSessionStore` 的公开 API，避免影响调用方和现有测试。
- 本轮只做函数级拆分，不拆 `SQLiteSessionStore` 的公开异步 API；连接、锁、同步/异步包装、session summary 和偏好更新仍留在 `SQLiteSessionStore`。
- 暂不建立 repository 基类或通用 SQL builder；当前函数模块已经覆盖主要聚合，后续只在新需求需要时继续细拆。

治理动作：

- 将建表 SQL、legacy sessions/messages 迁移、notebook entries 兼容迁移移动到 `deeptutor/services/session/schema.py`。
- `SQLiteSessionStore._initialize()` 只保留 schema 初始化入口调用。
- 将 turn 创建、状态更新、active turn 查询、turn event 追加和回放移动到 `deeptutor/services/session/turns.py`；`SQLiteSessionStore` 保留原异步方法作为兼容 wrapper。
- 将 notebook entry CRUD、筛选、category CRUD 和 entry/category 关联移动到 `deeptutor/services/session/notebook.py`；`SQLiteSessionStore` 保留原异步方法作为兼容 wrapper。
- 将 message 添加、import 会话、regenerate 删除、message path 和 context query 移动到 `deeptutor/services/session/messages.py`；`SQLiteSessionStore` 保留原异步方法作为兼容 wrapper。
- 补充 legacy schema 初始化回归测试，覆盖 message parent backfill、notebook `turn_id` / `user_answer_images_json` / `ai_judgment` 新列，以及旧 unique 约束升级后的同题多 turn 写入。

验收标准：

- schema 和 migration 逻辑不再内联在 `sqlite_store.py`。
- turn / turn_event 同步 SQL 不再内联在 `sqlite_store.py`。
- notebook entry / category 同步 SQL 不再内联在 `sqlite_store.py`。
- message / import / regenerate 同步 SQL 不再内联在 `sqlite_store.py`。
- `SQLiteSessionStore` 的公开导入路径和方法签名不变。
- legacy DB 初始化、notebook CRUD、turn event、import、unified websocket 相关测试通过。

### 9. 知识库 Manager 职责过宽

证据：`deeptutor/knowledge/manager.py` 曾约 1788 行，已降到约 1034 行。

问题：知识库生命周期、文件操作、元数据、索引 Provider、解析结果管理混在一起，后续接入新解析引擎或多用户隔离时容易扩大风险面。

治理动作：

- 已将 `kb_config.json` 读写、文件锁、provider/embedding 兼容迁移移动到 `deeptutor/knowledge/store.py`。
- 已将 `get_metadata()` / `get_info()` 的返回字段组装、状态投影和统计移动到 `deeptutor/knowledge/info.py`。
- 已将 connected KB 注册 entry 构造移动到 `deeptutor/knowledge/connections.py`。
- 已将 linked-folder metadata 同步移动到 `deeptutor/knowledge/folders.py`。
- `KnowledgeBaseManager` 的公开方法和导入路径保持不变，现阶段继续保留自动发现、删除和索引清理等生命周期入口。

验收标准：

- `KnowledgeBaseManager` 不再内联 config store、connected entry 构造、info projection、linked-folder metadata 同步。
- `KnowledgeBaseManager` 的公开导入路径和方法签名不变。
- 知识库 manager、connected KB、linked-folder、knowledge API 相关测试通过。

### 10. 内置工具集中在 `__init__.py`

证据：`deeptutor/tools/builtin/__init__.py` 曾约 1583 行，已降到约 69 行。

问题：`__init__.py` 同时承担导出和大量工具实现，会让工具发现、单测、依赖加载和代码阅读都变差。

治理动作：

- 已将 shared prompt-hint mixin 移动到 `deeptutor/tools/builtin/common.py`。
- 已将 RAG / read-source 上下文工具移动到 `deeptutor/tools/builtin/context.py`。
- 已将 code execution wrapper 移动到 `deeptutor/tools/builtin/execution.py`。
- 已将 web fetch / GitHub / cron 外部服务工具移动到 `deeptutor/tools/builtin/external.py`。
- 已将 ask-user 交互工具移动到 `deeptutor/tools/builtin/interaction.py`。
- 已将 memory 工具移动到 `deeptutor/tools/builtin/memory.py`。
- 已将 notebook 工具移动到 `deeptutor/tools/builtin/notes.py`。
- 已将 brainstorm / web search / reason / paper search 移动到 `deeptutor/tools/builtin/search.py`。
- 已将 read-skill / load-tools 移动到 `deeptutor/tools/builtin/skills.py`。
- 已将 GeoGebra analysis 移动到 `deeptutor/tools/builtin/vision.py`。
- 已将 `BUILTIN_TOOL_TYPES`、工具名集合、toggle/configurable 集合和 aliases 移动到 `deeptutor/tools/builtin/registry.py`。
- `deeptutor.tools.builtin` 保持原公开导入路径，只做轻量 re-export。

验收标准：

- `deeptutor/tools/builtin/__init__.py` 不再内联工具实现。
- `deeptutor.tools.builtin` 的公开类、常量和 `__all__` 继续可用。
- Built-in tool wrapper、tool registry alias、tools/settings API、cron registry 相关测试通过。

### 11. LLM Provider 错误分类和 fallback 规则需要收敛

证据：`deeptutor/services/llm/cloud_provider.py`、`deeptutor/services/llm/executors.py` 和 `deeptutor/services/llm/provider_core/openai_compat_provider.py` 原本各自维护 `response_format` / Responses API fallback 判断；`deeptutor/services/llm/error_mapping.py` 已经是 Provider SDK 异常到统一异常类型的入口。

问题：Provider 兼容逻辑复杂时，如果缺少统一错误类型，调用方无法区分“认证失败、模型不支持、限流、网络失败、响应格式不兼容、代码 bug”。

治理边界：

- 不新增完整 Provider 抽象层，不重写 SDK/aiohttp 请求流程。
- 保留现有调用点，只把重复的 fallback 判断移动到共享函数。
- 错误分类继续复用 `map_error()`；只补齐已有异常体系能表达的状态码分类。

治理动作：

- 新增 `deeptutor/services/llm/fallback.py`，集中处理两类能力降级判断：
  - `response_format` 不支持时，允许移除 `response_format` 后重试。
  - Responses API 形态不兼容时，允许降级到 Chat Completions。
- `cloud_provider.py`、`executors.py`、`provider_core/openai_compat_provider.py` 复用同一 fallback 判断，避免三处启发式漂移。
- `map_error()` 明确分类 401、429、404、408/504、网络连接失败、上下文窗口错误；未知错误仍保留为 `LLMAPIError`。
- 补充测试确保认证失败和限流不会被误判成“能力降级 fallback”。

验收标准：

- `response_format` fallback 规则只有一个实现入口。
- Responses API fallback 规则只有一个实现入口。
- 认证失败、限流、模型不存在、超时、网络连接失败、上下文窗口超限有明确统一异常分类。
- “模型能力降级”和“请求失败重试/报错”通过测试分开验证。

### 12. 服务端出网访问策略没有形成统一边界

证据：`deeptutor/tools/web_fetch.py` 已对 http/https、私网地址、重定向、大小上限有明确防护；但其他位置仍直接使用 `requests`/`httpx`/`aiohttp`，例如图片 URL 下载、图片/视频生成结果下载、MinerU 云解析结果下载、search provider、LLM/embedding/media provider API。

问题：不是说当前完全缺失 SSRF 防护，而是安全策略没有统一复用。只要新增一个“用户可控 URL”的入口，就可能绕过 `web_fetch` 已有的防护。

治理边界：

- 不重写全仓 HTTP client；固定 Provider/API endpoint 继续走原请求路径。
- 本轮只治理服务端会抓取“用户输入、模型输出或第三方响应中携带的任意 URL”的路径。
- `arxiv.org/e-print/{id}` 这类由代码固定域名构造的下载不是本轮 SSRF 高风险点，后续如治理应关注大小限制和解压安全。

治理动作：

- 新增 `deeptutor/services/outbound.py`，集中维护 http/https scheme、私网/loopback/link-local/reserved/multicast/未解析 host 的拒绝策略。
- `web_fetch.py` 复用共享 host policy，保留原可注入 validator 的测试形态。
- `tools/vision/image_utils.py` 的任意图片 URL 下载在请求前和重定向后复用同一 URL policy。
- `services/imagegen/adapters/{openai_compat,chat_completions}.py` 对 Provider 返回的图片 URL 下载复用同一 URL policy。
- `services/videogen/adapters/async_task.py` 对 Provider 返回的 `video_url` 下载复用同一 URL policy。
- `services/parsing/engines/mineru/cloud.py` 对 MinerU 返回的结果 archive URL 下载复用同一 URL policy。

验收标准：

- `web_fetch`、图片 URL 下载、图片/视频生成结果下载、MinerU 结果下载使用同一 outbound URL policy。
- 私网/loopback URL 不会进入实际 HTTP GET。
- 定向测试覆盖用户 URL、Provider 返回图片 URL、Provider 返回视频 URL、MinerU 返回 archive URL 的拒绝行为。
- 固定 Provider/API 请求不被误套 SSRF 策略，避免破坏本地或自定义 Provider 配置。

### 13. Admin Partner 接口可返回明文渠道密钥

证据：`deeptutor/api/routers/partners.py` 中 `include_secrets` 查询参数会返回 raw channel secrets；`web/components/partners/PartnerChannels.tsx` 的编辑表单会请求 `include_secrets=true` 来填充 schema-driven secret 字段。

问题：该接口当前应受 admin 依赖保护，但“通过 query 参数返回明文密钥”仍是高敏行为。日志、浏览器缓存、代理、错误上报都可能扩大暴露面。

治理边界：

- 本轮不移除明文编辑能力；否则现有 channel schema 表单无法无损编辑已保存密钥。
- 普通列表、创建、更新和默认详情接口继续返回 masked secrets。
- 只在显式 `include_secrets=true` 的编辑详情请求上允许 raw secrets。

治理动作：

- `GET /api/v1/partners/{partner_id}?include_secrets=true` 设置 `Cache-Control: no-store` 和 `Pragma: no-cache`。
- 明文 secret 请求写入 admin 审计日志，记录 partner id，不记录 secret 值。
- 前端 `PartnerChannels` 的明文详情请求设置 `cache: "no-store"`，避免浏览器普通缓存。
- 回归测试覆盖默认详情继续 mask、include_secrets 返回 raw 且带 no-store/no-cache headers。

验收标准：

- 默认 partner 详情不返回 raw channel secrets。
- 只有显式 `include_secrets=true` 返回 raw channel secrets。
- raw secret 响应带 no-store/no-cache header。
- 前端编辑表单只在加载 channel 编辑详情时请求 raw secrets，且请求禁用缓存。

### 14. SSL 校验关闭逻辑需要统一治理

证据：项目已有 `deeptutor/services/llm/openai_http_client.py` 作为 `DISABLE_SSL_VERIFY` 集中 helper；但此前 `deeptutor/core/agentic/client.py`、`deeptutor/services/llm/providers/open_ai.py` 和 `deeptutor/services/llm/cloud_provider.py` 仍存在直接读取设置并构造 `verify=False` / `ssl=False` 的路径；`OpenAICodexProvider` 还会在证书失败时自动 `verify=False` 重试。

问题：本地开发允许关闭 SSL 可以理解，但该能力必须保持单一入口和生产硬阻断，否则部署配置漂移时会产生安全风险。

任务拆解：

1. 盘点 `verify=False`、`ssl=False`、`DISABLE_SSL_VERIFY` 和 `CERTIFICATE_VERIFY_FAILED` 调用点。
2. 保留 `openai_http_client.disable_ssl_verify_enabled()` / `openai_client_kwargs()` 作为唯一配置判断入口。
3. 将 OpenAI SDK、agentic client、legacy OpenAI provider、aiohttp cloud provider 收敛到同一 helper。
4. 移除 Codex provider 未显式配置时的证书失败自动降级，避免绕过全局开关。
5. 用测试覆盖默认启用校验、显式关闭校验、生产环境阻断和 Codex 不自动降级。

治理动作：

- `deeptutor/core/agentic/client.py` 改为通过 `openai_client_kwargs()` 注入 SDK `http_client`。
- `deeptutor/services/llm/providers/open_ai.py` 改为通过 `openai_client_kwargs()` 注入 SDK `http_client`，不再直接读环境或自行构造 `verify=False`。
- `deeptutor/services/llm/cloud_provider.py` 的 aiohttp connector 改为通过 `disable_ssl_verify_enabled()` 判断，生产环境阻断复用同一入口。
- `deeptutor/services/llm/provider_core/openai_codex_provider.py` 不再在 `CERTIFICATE_VERIFY_FAILED` 后自动 `verify=False` 重试；只有显式 `DISABLE_SSL_VERIFY` 才会关闭校验。

验收标准：

- `verify=False` 只保留在集中 helper `openai_http_client.py` 中。
- aiohttp `ssl=False` 路径必须经过 `disable_ssl_verify_enabled()`。
- 生产环境设置 `DISABLE_SSL_VERIFY=true` 会被统一阻断。
- Codex provider 遇到证书失败不会自动关闭 SSL 校验。

### 15. Settings 相关前端组件和上下文过大

证据：`web/components/settings/SettingsContext.tsx` 原约 1253 行，当前约 1027 行；`web/components/settings/ServiceConfigEditor.tsx` 原约 1191 行，当前约 870 行；`MinerUEngineSettings.tsx` 当前约 745 行，仍接近需要继续拆分的阈值。

问题：设置页已经覆盖模型、网络、知识库、聊天、MCP、文档解析等多个域。继续集中会让配置联动、校验、保存状态和 UI 文案难以维护。

治理边界：

- 不重写 SettingsProvider 的保存、apply、诊断 SSE 和 extension dirty/save 注册流程；这些是跨设置页共享状态，强拆前需要更细 UI/集成覆盖。
- 不引入新的 settings store 或表单框架；现有 React state + helper 已能覆盖当前需求。
- 本轮先拆纯 catalog schema/helper 和模型服务编辑器里的 provider 字段区，保留 `SettingsContext` 原公开导出路径，避免一次性改动所有 settings 调用方。

治理动作：

- 新增 `web/components/settings/catalog.ts`，承接 settings catalog 类型、默认 catalog、active profile/model、service readiness、diagnostics 匹配和 model 命名 helper。
- `SettingsContext.tsx` 继续 re-export catalog 类型和 helper，兼容既有 `SettingsContext` 导入路径；Provider 文件只保留状态、API load/save/apply、诊断和 tour 控制主体。
- 新增 `web/components/settings/Profile.tsx`，把 provider/API key/base URL/extra headers 字段组从 `ServiceConfigEditor.tsx` 中拆出。
- 新增 `web/components/settings/format.ts`，承接模型 tab 上下文窗口、embedding dimension、voice badge 和本地时间格式化 helper。
- 补充 `web/tests/settings-catalog.test.ts` 和 `web/tests/settings-format.test.ts`，覆盖拆出的非 UI 逻辑。

验收标准：

- `SettingsContext.tsx` 不再内联 catalog 类型、默认 catalog、active profile/model 和 service readiness 主体逻辑。
- `ServiceConfigEditor.tsx` 不再内联 provider 连接字段区和模型 tab 格式化 helper。
- `SettingsContext` 的既有公开导出路径仍可用，避免全项目调用方迁移。
- `./node_modules/.bin/tsc --noEmit --pretty false` 通过。
- `npm run test:node` 通过。

### 16. Memory UI 和图谱组件体量偏大

证据：`web/components/memory/MemorySection.tsx` 原约 1522 行，当前约 662 行；已新增 `web/components/memory/MemoryL1View.tsx` 承接 L1 snapshot / changes / KB queries 视图，`web/components/memory/model.ts` 承接 memory 类型和纯 helper。`MemoryGraph.tsx` 当前约 989 行，`MemoryRunPanel.tsx` 当前约 942 行，仍是下一轮治理重点。

问题：记忆模块同时有数据列表、图谱、运行状态、分块预算、去重/引用策略等概念。大组件会让交互状态和数据规则互相污染。

治理边界：

- 本轮不重写 MemoryGraph 的 SVG 布局、pan/zoom、hover/selection 逻辑；图谱交互需要单独验证。
- 本轮不重写 MemoryRunPanel 的 run lifecycle、LLM 选择、reset/undo 和 event grouping；该面板已经依赖 `useMemoryRun`，继续拆前先补更细 run event 测试。
- 不引入状态管理库或 Storybook；先用现有 node tests 覆盖可拆纯逻辑。

治理动作：

- 新增 `web/components/memory/model.ts`，承接 `Surface` / `Layer` / `Tab` / `DocOverview` / snapshot/change/query DTO、实体 ref anchor、doc label、timestamp、shorten 和 deep-link helper。
- 新增 `web/components/memory/MemoryL1View.tsx`，把 L1 workspace snapshot、changes、KB queries、surface picker、pending badge 和 refresh 控制从 `MemorySection.tsx` 拆出。
- `MemoryL1Workbench.tsx` 改为直接依赖 `MemoryL1View.tsx` 和 shared `Surface` 类型，不再从 `MemorySection.tsx` 反向导入 L1 视图。
- `MemorySection.tsx` 现在只保留 Memory 入口、overview/doc 加载、L2/L3 doc list、doc pane 和旧 update stream 面板。
- 新增 `web/tests/memory-model.test.ts`，覆盖 entity anchor/linkify、label 映射、shorten、deep-link 和 timestamp fallback。

验收标准：

- `MemorySection.tsx` 不再内联 L1 snapshot / changes / KB queries 视图主体。
- `MemoryL1Workbench.tsx` 不再从 `MemorySection.tsx` 导入 `L1View`。
- memory entity ref、label、deep-link 等纯 helper 有最小测试覆盖。
- `./node_modules/.bin/tsc --noEmit --pretty false` 通过。
- `npm run test:node` 通过。
- `npm run lint` 通过。

### 17. Agent pipeline 文件过大，阶段边界需要显式化

证据：治理前 `deeptutor/agents/research/pipeline.py` 约 2844 行，`deeptutor/agents/question/pipeline.py` 约 2184 行，`deeptutor/agents/chat/agentic_pipeline.py` 约 1301 行。当前已先处理 `question` pipeline：新增 `deeptutor/agents/question/planning.py` 承接 Plan 阶段数据结构、输入规范化和 planner 响应解析，`deeptutor/agents/question/pipeline.py` 继续保留编排、LLM loop、工具调度和结果发射。

问题：Agent pipeline 很容易把 prompt、状态机、工具选择、引用处理、输出格式和错误处理混在一起。文件越大，越难保证每个阶段的输入输出契约。

治理边界：

- 不一次性拆完 research / question / chat 三条 pipeline；它们都是 LLM 编排核心路径，必须按已有测试覆盖逐步拆。
- 本轮只拆 `question` 的 Phase 2 Plan 边界，因为它以纯 JSON 解析和模板规范化为主，已有 `tests/agents/question/test_pipeline.py` 覆盖，回归风险最低。
- 保持旧 API 兼容：`QuizTemplate`、`QuizPlan`、`QuizHistoryEntry` 仍可从 `deeptutor.agents.question.pipeline` 导入；包级懒加载则改为优先从轻量 `planning.py` 暴露规划数据结构。

治理动作：

- 新增 `deeptutor/agents/question/planning.py`，承接 `QuestionType`、`QuizTemplate`、`QuizPlan`、`QuizHistoryEntry`、question type / per-type count 规范化、prompt directive 格式化和 `parse_quiz_plan()`。
- `QuestionPipeline._parse_plan()` 改为兼容 wrapper，委托 `parse_quiz_plan()`；pipeline 内部不再重复定义规划 helper。
- `deeptutor/agents/question/history.py` 和 `deeptutor/agents/question/mimic_source.py` 改为直接依赖 `planning.py`，避免为了数据结构导入完整 LLM pipeline。
- 测试新增对 `parse_quiz_plan()`、规划输入规范化和 prompt directive 格式化的直接覆盖；旧 `_parse_plan()` 测试继续保留，保证兼容入口未断。

后续规划：

- 下一轮如果继续治理 Agent pipeline，应优先选 `research` 中纯 stage helper 或引用/结果 envelope 逻辑，先补对应测试，再拆。
- `chat/agentic_pipeline.py` 目前相对较小且更接近实时交互主路径，除非有明确测试保护，不应先做大拆。
- 每拆一个 stage 都要保留旧外部导入路径或提供明确迁移，避免影响 capability、CLI、SDK 和测试。

验收标准：

- `deeptutor/agents/question/pipeline.py` 不再内联 Plan 阶段数据结构和 planner JSON 解析主体。
- `deeptutor/agents/question/planning.py` 的纯 helper 有最小测试覆盖。
- mimic/history 这类只需要规划数据结构的模块不再反向导入完整 pipeline。
- `pytest tests/agents/question/test_pipeline.py tests/agents/question/test_mimic_source.py -q` 通过。
- `python -m compileall -q deeptutor/agents/question` 通过。

### 18. 测试目录层级未严格镜像源码，且部分测试文件过大

证据：`AGENTS.md` 要求变更测试布局前先检查现有实现和测试，`standards/testing.md` 已明确“新增 Python 测试默认镜像 owning package path”。当前 `tests/` 只是部分按顶层包分组，并未严格镜像 `deeptutor/`：例如源码存在 `deeptutor/agents/vision_solver`、`deeptutor/agents/visualize`、`deeptutor/api/utils`、`deeptutor/services/settings`、`deeptutor/services/storage` 等目录，而测试侧没有完整对应层级；同时历史上存在 `tests/multi_user` 这种按行为域组织的目录。前端历史测试仍大量平铺在 `web/tests/` 根目录，但新增 `web/lib/*` 已逐步归位到 `web/tests/lib/*`，新增 `web/context/*` 已逐步归位到 `web/tests/context/*`。大文件问题也仍存在：`tests/api/routers/test_unified_ws.py` 约 921 行，`tests/services/partners/test_zulip_channel.py` 约 1261 行。`tests/agents/question/test_pipeline.py` 已降到约 764 行，后续仍可继续按行为拆分。

问题：目录层级不镜像源码会让“某个模块由哪些测试保护”变得不清楚。大测试文件本身不一定错误，但如果 fixture、场景和断言继续堆叠在行为域目录中，失败时很难判断是业务变更、测试假设过旧还是环境问题，也容易在拆模块时漏掉对应测试迁移。

治理动作：不要全仓一次性搬测试目录；历史行为域测试可以保留，但不能继续作为新拆模块的默认落点。新模块和被修改模块的测试必须优先归位到对应包路径，例如 `deeptutor/services/session/events.py` -> `tests/services/session/test_events.py`、`deeptutor/api/routers/invites.py` -> `tests/api/routers/test_invites.py`、`web/lib/chat/hydration.ts` -> `web/tests/lib/chat/hydration.test.ts`。确实跨多个包的行为测试可以留在行为域目录，但需要在测试模块或 review summary 中说明原因。继续按行为切分超大测试文件，把重 fixture 下沉到共享 fixture/helper，并对可选外部依赖加清晰 skip 条件。

本轮治理：

- 随第 17 项新增的 `deeptutor/agents/question/planning.py`，新增对应测试文件 `tests/agents/question/test_planning.py`。
- 将 Plan 阶段纯 helper 测试从 `tests/agents/question/test_pipeline.py` 迁出，只在 `test_pipeline.py` 保留 `_parse_plan()` 兼容 wrapper 的最小覆盖。
- 将 `deeptutor/agents/question/history.py` 的 quiz history loader 测试迁到 `tests/agents/question/test_history.py`。
- 将 `deeptutor/agents/question/mimic_source.py` 的 mimic adapter 测试迁到已有 `tests/agents/question/test_mimic_source.py`。
- 将新增前端 component helper 测试从 `web/tests/` 根目录迁到 `web/tests/components/memory/model.test.ts`、`web/tests/components/settings/catalog.test.ts`、`web/tests/components/settings/format.test.ts`。
- `tests/agents/question/test_pipeline.py` 从约 1018 行降到约 764 行，避免继续把新拆模块测试堆回 pipeline 大测试文件。

验收标准：

- 新增或拆出的 Python 模块优先有同包路径下的 `test_<module>.py`。
- `test_pipeline.py` 不再承载 `planning.py` 的完整 helper 测试。
- `test_pipeline.py` 不再承载 `history.py` 的 loader 测试。
- `test_pipeline.py` 不再承载 `mimic_source.py` 的 adapter 测试。
- `pytest tests/agents/question/test_history.py tests/agents/question/test_planning.py tests/agents/question/test_pipeline.py tests/agents/question/test_mimic_source.py -q` 通过。
- `npm run test:node` 通过，并能递归发现 `web/tests/components/**` 下的新增测试。

### 19. 多用户治理模块存在静默失败风险

证据：`deeptutor/multi_user/identity.py` 和 `audit.py` 的关键 fallback 已有日志；`deeptutor/multi_user/grants.py` 与 `deeptutor/multi_user/data_governance.py` 仍存在读取失败后直接返回默认值或跳过记录的路径。本轮已处理这些明确缺口。

问题：多用户场景下，身份、授权、审计、数据治理不应该静默失败。即使是 best-effort，也应至少可观测，否则商用部署时无法复盘权限和数据问题。

治理动作：

- `load_grant()` 读取本地 grant JSON 失败时仍 fail closed 到空 grant，但会记录 `WARNING`，包含 user id 和文件路径。
- `load_data_governance_settings()` 读取设置失败时仍回退默认设置，但会记录 `WARNING`。
- `_read_jsonl()` 遇到 malformed JSONL 行仍跳过该行，但会记录 `WARNING` 和文件路径。
- `_prune_jsonl()` 遇到 malformed JSONL 行仍保留该行，避免误删数据，同时记录 `WARNING`。
- `_prune_deleted_user_archives()` 遇到不可读 manifest 仍跳过该归档，但会记录 `WARNING` 和 manifest 路径。
- `auth_store_write_lock()`、`_grant_write_lock()`、`_audit_write_lock()` 在 `fcntl` 可用但加锁失败时仍降级继续执行，同时记录 `WARNING`。`fcntl` 不可用的平台保持静默兼容。
- auth secret 创建或迁移后权限收紧失败时仍保留 secret，但会记录 `WARNING`。

验收标准：

- 多用户 grant 读取失败不再无日志静默回退。
- data governance 设置、JSONL、deleted-user manifest 的读取失败不再无日志静默跳过。
- 本地 auth/grant/audit 写锁不可用不再无日志静默降级。
- auth secret 权限收紧失败不再无日志静默跳过。
- fallback 行为保持不变：损坏 grant 返回空 grant；损坏设置返回默认设置；损坏 JSONL 行不会导致 prune 删除；损坏归档不会导致 prune 删除。
- `pytest tests/multi_user/test_tool_access.py tests/multi_user/test_identity_and_paths.py tests/multi_user/test_data_governance.py -q` 通过。

### 20. 命名规范需要“增量治理”，不适合全仓一次性重命名

证据：仓库中同时存在 Python snake_case、Next.js 路由括号目录、React PascalCase、历史文档大写下划线、工具脚本下划线等多种命名风格。本轮扫描当前新增文件后，未发现需要立刻改名的非约定文件：

- Python 新增业务模块使用小写单词名，例如 `planning.py`、`fallback.py`、`schema.py`、`turns.py`、`registry.py`。
- Python 测试新增文件使用 pytest 约定 `test_*.py`，例如 `test_history.py`、`test_planning.py`。
- React 组件新增文件继续遵循现有组件目录 PascalCase 约定，例如 `ChatHeader.tsx`、`MemoryL1View.tsx`、`Profile.tsx`。
- Next.js 路由括号目录、React 组件 PascalCase、历史公开文档名和工具生态文件名不作为本轮重命名对象。

问题：命名不统一确实会降低可读性，但全仓重命名会制造巨大 diff，破坏 imports、路由路径、文档链接、测试引用和历史追踪。

治理动作：

- 不做全仓机械重命名；只治理当前改动范围内确实不符合所属生态约定的文件。
- 新增 Python 业务模块优先用简洁小写单词名；确需多词时只在已有包约定或公开含义需要时使用 snake_case。
- 新增 Python 测试文件保留 `test_*.py`，这是 pytest 发现规则，不按“单词名”强行改。
- 新增 React 组件文件保留 PascalCase；新增 hook/lib/test helper 使用现有目录约定的小写或 kebab/slug 风格。
- 框架约定和历史公共入口保留；改名必须同时做引用搜索、路径测试或类型检查。

验收标准：

- 当前新增文件没有需要立刻改名的非约定名称。
- 文档明确区分“需要治理的命名不一致”和“框架/工具链约定名称”。
- `git status --short | awk '$1=="??" {print $2}'` 的新增文件列表已按上述规则抽样检查。
- 继续使用增量治理：未来新增或实际修改文件时再顺手处理局部命名。

## 建议治理顺序

1. 先做安全和稳定边界：认证路由、密钥回显、出网 URL policy、SSL 禁用开关、TurnRuntime 任务生命周期。
2. 再做高频业务边界：知识库路由、会话存储、知识库 Manager、LLM Provider 错误分类。
3. 然后做前端高频页面：聊天页、UnifiedChatContext、Settings、Memory。
4. 最后做低风险结构整理：工具模块拆分、Agent pipeline 阶段化、测试文件切分、命名增量治理。

## 不建议立即做的事

- 不要一次性重命名全仓文件和目录。
- 不要在没有测试保护的情况下拆 `knowledge.py`、`turn_runtime.py`、`auth.py`、聊天主页面。
- 不要为了“看起来规范”新增抽象层；只有能减少职责混杂、降低回归风险或复用安全边界时才拆。
- 不要把历史 `.env`、settings、Provider 配置逻辑混在一起改。配置路径必须先画清楚，再收敛。

## 后续落地方式

每个治理项建议单独建任务，并要求包含：

- 当前行为说明。
- 改动前回归测试或手工验证步骤。
- 最小拆分范围。
- 修改后的验证结果。
- 是否影响部署、配置、用户数据或公开 API。

最小可执行起点建议选择第 12、13、14 项，因为它们范围相对窄、风险价值高；随后处理第 3 和第 2 项。
