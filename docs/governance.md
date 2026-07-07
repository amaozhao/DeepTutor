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
   - 已同步拆分测试：直接对应 `deeptutor/api/routers/*` 的 API router 测试移动到 `tests/api/routers/`，`tests/api/` 仅保留 `api/main.py`、`api/security.py`、访问日志这类 API 层边界测试；上传 helper 测试移动到 `tests/knowledge/test_uploads.py`。
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

证据：`deeptutor/services/session/turn_runtime.py` 约 2090 行，并包含多处 `asyncio.create_task` 和大量宽泛 `except Exception`。

问题：会话 turn 执行、状态推送、取消、上下文构建、错误兜底、持久化更新集中在一个模块，导致失败路径难以验证。长任务一旦泄漏或吞错，用户侧表现会是“卡住”“结果丢失”“状态不一致”。

治理动作：先为取消、失败、断连、重试建立回归测试；再把任务监督、事件推送、持久化更新拆成明确子模块。

### 3. 认证路由同时承担登录、注册、管理员和导入导出

证据：`deeptutor/api/routers/auth.py` 约 1620 行，覆盖注册、登录、用户管理、邀请、CSV、导出、自助账户等逻辑。

问题：认证和用户管理属于高风险边界，文件过大让权限判断、公开接口和管理员接口难以审计。后续增加 SaaS 能力时，最容易在这里产生越权或绕过。

治理动作：拆成 `session`、`registration`、`admin users`、`invites` 等窄路由；每个公开接口都要有权限测试。

### 4. 前端聊天主页面和上下文过大

证据：`web/app/(workspace)/home/[[...sessionId]]/page.tsx` 约 2193 行，`web/context/UnifiedChatContext.tsx` 约 1885 行。

问题：页面、状态管理、网络请求、流式事件和 UI 控制耦合，导致聊天页任何小改都可能影响登录后主流程。

治理动作：优先拆出稳定 hook、状态 reducer、transport 层和纯展示组件；先补流式消息、重连、取消、错误提示的回归测试。

### 5. LLM 配置和进程环境变量写入分散

证据：`deeptutor/services/config/runtime_settings.py` 会统一导出运行时环境；但 `deeptutor/services/llm/client.py`、`deeptutor/services/llm/config.py`、`deeptutor/services/llm/executors.py`、`deeptutor/services/llm/provider_core/openai_compat_provider.py` 等位置也存在直接写入 `os.environ` 的逻辑。

问题：项目已经明确运行时配置主要来自 `data/user/settings/*.json`。如果 LLM Provider 在多个位置隐式写进程环境，后续多用户、多 Provider、热切换模型时会出现串配置、脏状态和不可复现问题。

治理动作：把“设置文件到 Provider 参数”的路径收敛到一个边界；Provider 内部不要再修改全局环境变量，除非有明确兼容层和测试。

### 6. 宽泛异常处理过多，容易吞掉真实错误

证据：`deeptutor/services/session/turn_runtime.py`、`deeptutor/services/session/pocketbase_store.py`、`deeptutor/api/main.py`、`deeptutor/multi_user/identity.py`、多个 partner channel 文件中存在大量 `except Exception` 和部分空 `pass`。

问题：宽泛捕获在边界层可以存在，但业务层大量使用会把数据错误、权限错误、网络错误和代码 bug 混成“失败兜底”，排查成本高。

治理动作：按模块建立允许清单：边界层可以捕获并转换为领域错误；核心服务层应捕获具体异常并保留日志上下文。

### 7. Partner 多渠道任务生命周期分散

证据：`deeptutor/services/partners/manager.py` 约 1291 行；`deeptutor/partners/channels/weixin.py` 约 1564 行；`feishu.py`、`telegram.py`、`mochat.py`、`zulip.py` 等 channel 文件也较大，并存在多个后台 task。

问题：多渠道连接、轮询、keepalive、消息分发、fallback timer 分散在 channel 和 manager 中，缺少统一 task registry 和关闭语义时，部署后容易产生后台任务泄漏或重复消费。

治理动作：建立统一任务监督和 shutdown 协议；每个 channel 只实现协议适配，不直接扩散生命周期管理。

### 8. SQLite 会话存储模块过大

证据：`deeptutor/services/session/sqlite_store.py` 约 1844 行。

问题：持久化层如果同时包含 schema、迁移、查询、导入导出、会话/消息/附件/笔记等逻辑，会让数据兼容性变更变得危险。

治理动作：先按表或聚合拆 repository/query 文件；迁移和兼容处理保持集中，避免在业务代码里散落 SQL。

### 9. 知识库 Manager 职责过宽

证据：`deeptutor/knowledge/manager.py` 约 1788 行。

问题：知识库生命周期、文件操作、元数据、索引 Provider、解析结果管理混在一起，后续接入新解析引擎或多用户隔离时容易扩大风险面。

治理动作：拆成元数据仓储、文件存储、索引任务、Provider 编排四个边界；先保持公开 API 不变。

### 10. 内置工具集中在 `__init__.py`

证据：`deeptutor/tools/builtin/__init__.py` 约 1583 行。

问题：`__init__.py` 同时承担导出和大量工具实现，会让工具发现、单测、依赖加载和代码阅读都变差。

治理动作：把每个工具或工具族移动到独立模块，`__init__.py` 只保留轻量导出和注册映射。

### 11. LLM Provider 错误分类和 fallback 规则需要收敛

证据：`deeptutor/services/llm/cloud_provider.py` 约 921 行，`deeptutor/services/llm/provider_core/openai_compat_provider.py` 约 856 行；Provider 层存在宽泛兜底、运行时禁用能力、HTTP/SSE 解析和重试逻辑。

问题：Provider 兼容逻辑复杂时，如果缺少统一错误类型，调用方无法区分“认证失败、模型不支持、限流、网络失败、响应格式不兼容、代码 bug”。

治理动作：定义 Provider 错误分类和 fallback 决策表；把“模型能力降级”与“请求失败重试”分开测试。

### 12. 服务端出网访问策略没有形成统一边界

证据：`deeptutor/tools/web_fetch.py` 对 http/https、私网地址、重定向、大小上限有明确防护；但其他位置仍直接使用 `requests`/`httpx`/`aiohttp`，例如 `deeptutor/tools/tex_downloader.py:83`、多个 search provider、图片/视频/解析/LLM adapter。

问题：不是说当前完全缺失 SSRF 防护，而是安全策略没有统一复用。只要新增一个“用户可控 URL”的入口，就可能绕过 `web_fetch` 已有的防护。

治理动作：建立统一 outbound client 或 URL policy；凡是用户输入可影响 URL 的路径必须显式调用同一策略。

### 13. Admin Partner 接口可返回明文渠道密钥

证据：`deeptutor/api/routers/partners.py` 中 `include_secrets` 查询参数会返回 raw channel secrets，注释说明这是编辑表单需要。

问题：该接口当前应受 admin 依赖保护，但“通过 query 参数返回明文密钥”仍是高敏行为。日志、浏览器缓存、代理、错误上报都可能扩大暴露面。

治理动作：优先评估是否必须回显明文；如果必须，增加审计日志、禁止缓存、前端只在编辑瞬间请求，并避免将密钥写入普通状态快照。

### 14. SSL 校验关闭逻辑需要统一治理

证据：`deeptutor/services/llm/providers/open_ai.py:61` 会在非生产环境允许 `verify=False`；`deeptutor/services/llm/openai_http_client.py` 也提供禁用 SSL 的客户端。

问题：本地开发允许关闭 SSL 可以理解，但该能力必须保持单一入口和生产硬阻断，否则部署配置漂移时会产生安全风险。

治理动作：保留一个集中开关；所有 Provider 只调用统一 helper；测试覆盖生产环境禁止禁用 SSL。

### 15. Settings 相关前端组件和上下文过大

证据：`web/components/settings/SettingsContext.tsx` 约 1253 行，`web/components/settings/ServiceConfigEditor.tsx` 约 1191 行，多个 settings 页面接近或超过 800 行。

问题：设置页已经覆盖模型、网络、知识库、聊天、MCP、文档解析等多个域。继续集中会让配置联动、校验、保存状态和 UI 文案难以维护。

治理动作：按设置域拆 schema、校验、保存 hook 和展示组件；共用“脏状态/保存中/错误”模式。

### 16. Memory UI 和图谱组件体量偏大

证据：`web/components/memory/MemorySection.tsx` 约 1522 行，`MemoryGraph.tsx`、`MemoryRunPanel.tsx` 接近 1000 行。

问题：记忆模块同时有数据列表、图谱、运行状态、分块预算、去重/引用策略等概念。大组件会让交互状态和数据规则互相污染。

治理动作：拆数据查询、图布局、详情面板、运行面板；为关键交互补 Story 或组件测试。

### 17. Agent pipeline 文件过大，阶段边界需要显式化

证据：`deeptutor/agents/research/pipeline.py` 约 2844 行，`deeptutor/agents/question/pipeline.py` 约 2184 行，`deeptutor/agents/chat/agentic_pipeline.py` 约 1301 行。

问题：Agent pipeline 很容易把 prompt、状态机、工具选择、引用处理、输出格式和错误处理混在一起。文件越大，越难保证每个阶段的输入输出契约。

治理动作：按 pipeline stage 拆文件；每个 stage 明确输入、输出、可失败类型和可观测事件。

### 18. 测试文件过大，回归定位成本高

证据：`tests/api/routers/test_knowledge.py` 仍超过 1000 行，`tests/api/test_unified_ws_turn_runtime.py` 约 921 行，`tests/agents/question/test_pipeline.py` 约 986 行，`tests/services/partners/test_zulip_channel.py` 约 1261 行。

问题：大测试文件本身不一定错误，但如果 fixture、场景和断言堆叠，失败时很难判断是业务变更、测试假设过旧还是环境问题。

治理动作：按行为切分测试文件；把重 fixture 下沉到 helper；对可选外部依赖加清晰 skip 条件。

### 19. 多用户治理模块存在静默失败风险

证据：`deeptutor/multi_user/identity.py`、`audit.py`、`grants.py`、`data_governance.py` 中存在宽泛捕获和空 `pass`。

问题：多用户场景下，身份、授权、审计、数据治理不应该静默失败。即使是 best-effort，也应至少可观测，否则商用部署时无法复盘权限和数据问题。

治理动作：把 best-effort 路径标记清楚；审计失败、授权读取失败、身份状态异常都应产生日志或指标。

### 20. 命名规范需要“增量治理”，不适合全仓一次性重命名

证据：仓库中同时存在 Python snake_case、Next.js 路由括号目录、React PascalCase、历史文档大写下划线、工具脚本下划线等多种命名风格。

问题：命名不统一确实会降低可读性，但全仓重命名会制造巨大 diff，破坏 imports、路由路径、文档链接、测试引用和历史追踪。

治理动作：新文件优先使用当前规范要求的简洁 ASCII 命名；框架约定和历史公共入口保留；被实际修改的内部文件再顺手治理，且必须跑引用搜索和测试。

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
