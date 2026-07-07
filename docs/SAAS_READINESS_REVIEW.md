# DeepTutor SaaS Readiness Review

审查日期：2026-07-07

本文是对“当前代码是否能直接开放为商业 SaaS”的代码复核结论。范围只包括当前仓库可见逻辑与当前本地配置，不覆盖法律合规、商业定价策略、账单/支付方案或第三方服务合同。

更新说明：截至 2026-07-07，本仓库已补齐任务规划中的 Milestone 0-4 最小闭环：账号状态会进入鉴权链路，注册方案限定为邮箱 + 密码，不做手机号/SMS/OTP 注册；支持默认关闭的邮箱 + 密码公开注册，也支持管理员创建一次性邮箱注册邀请码；公开注册提交同意时会持久化基础同意记录和当前协议版本，可配置公开自助注册先进入 disabled 待审核状态，增加基础限流、Origin/Referer 防护、附件 session ownership 校验，以及 LLM usage/quota；TTS/STT/search/embedding 也已按调用次数纳入同一 quota ledger。PostgreSQL shared_state 可让 auth secret、用户/token_version、注册邀请码、rate limit、grant quota 和 usage ledger 跨多副本共享。管理员用户操作、停用原因、全局 `auth.max_users` 账号上限、用户清单 CSV 导出/导入、grant、skill 安装、模型目录、邀请码和 MCP 配置写操作已进入审计或创建约束，管理员可查询审计 JSONL；管理员和普通用户均可导出用户数据 zip，普通用户可用当前密码自助注销，删除用户可选择保留、归档或删除 workspace/grant/avatar，并可配置基础保留期策略、手动清理过期 audit/usage/deleted-user 数据。PocketBase 已明确保留为单用户集成，启用时会在生产告警和部署状态里标记为不支持多用户/SaaS。下文结论按当前代码状态更新。

## 总结论

原结论的主方向是正确的：当前 DeepTutor 可以用于受控的私有化 / 内部多用户部署，但不建议直接开放成面向公众注册、付费、规模化运营的商业 SaaS。

更准确地说：

- 支持“管理员初始化 + 管理员添加用户 + 授权模型/知识库/工具”的受控多用户模式。
- 支持“可配置开启的邮箱 + 密码普通用户注册”和“管理员一次性邀请码 + 邮箱密码注册”；公开自助注册可配置为先进入 disabled 待审核状态；管理员也可用邮箱密码创建普通用户，或通过 CSV 批量导入普通用户；`auth.max_users` 可做受控 beta 的全局账号上限；支持 LLM turn 用量和 hard quota，TTS/STT/search/embedding 已按调用次数纳入同一额度；默认文件模式适合单副本 beta，PostgreSQL shared_state 模式可支撑多副本共享状态；支持普通用户自助导出和自助注销的 beta 闭环；不支持邮箱验证、忘记密码、多租户组织等开放 SaaS 产品闭环。账单/支付本轮明确不纳入。
- 默认 JSON/SQLite 多用户路径是当前被文档和代码共同支持的路径；PocketBase 相关代码存在部分 `user_id` 隔离实现，但项目文档、生产告警和部署状态仍把 PocketBase 标为单用户集成，不能作为 SaaS 多用户底座直接依赖。

## 已修正的结论

| 项目 | 复核后结论 |
| --- | --- |
| 自定义 LLM / MiniMax | 可以主要通过配置实现。代码已有 `custom`、`custom_anthropic`、`minimax`、`minimax_anthropic` provider 注册。当前本地配置已切到 `minimax_anthropic`、`https://api.minimaxi.com/anthropic`、`MiniMax-M3`、`context_window=1000000`。注意不要把 `model_catalog.json` 里的真实 API key 提交或外泄。 |
| 1M 上下文 | 当前运行时会把字符串形式的 `context_window` 转成整数，并且全局上限正好是 `1_000_000`，所以 M3 的 1M 配置可以生效。 |
| `.env` | 项目根 `.env` 已不存在，而且项目文档明确说根 `.env` 会被忽略；运行时配置在 `data/user/settings/*.json`。`.env.example` 是部署样例，不建议删除。 |
| 中文化 | 当前有 `zh` i18n、中文 capability prompt、界面语言配置；一般切中文不需要改代码。若要“商业级中文化”，还需要做全量文案缺失检查和业务术语统一。 |
| `/admin/users` 和注册 | `/register` 保留首个管理员邮箱密码 bootstrap；首个用户创建完成后，普通自注册默认关闭，可通过 `auth.public_registration_enabled` 开启邮箱 + 密码注册。后续账号也可由管理员通过 `/api/v1/auth/users` 创建，或通过 `email,password` CSV 批量导入普通用户；`auth.max_users` 大于 0 时会限制账号总数。 |
| PocketBase | 不能简单说“当前代码完全没有 user_id 过滤”：`pocketbase_store.py` 里已有 session 的 `user_id` 过滤。但 `multi_user/__init__.py`、README、生产告警和系统部署状态均明确要求多用户/SaaS 部署保持 `pocketbase_url` 为空，PocketBase 仍按单用户集成处理。 |
| Token / 会话 | 标准模式仍是 JWT，但已加入服务端用户状态校验和 `token_version`。删除、停用、降权、重置密码、管理员强制登出后旧 token 会失效；`logout` 仍只是清当前 cookie，没有独立服务端 session/revocation 表。 |

## 当前已经具备的能力

### LLM 配置能力

- Provider 注册包含 `custom`、`custom_anthropic`、`minimax`、`minimax_anthropic`：`deeptutor/services/provider_registry.py:80`、`deeptutor/services/provider_registry.py:112`、`deeptutor/services/provider_registry.py:303`。
- 当前本地 LLM 配置为 MiniMax M3：`data/user/settings/model_catalog.json:11`、`data/user/settings/model_catalog.json:12`、`data/user/settings/model_catalog.json:19`、`data/user/settings/model_catalog.json:21`。
- 运行时会解析 `context_window`：`deeptutor/services/config/provider_runtime.py:642`，模型列表展示也会转成整数：`deeptutor/services/model_selection/llm.py:99`。
- 有效上下文窗口上限为 1M：`deeptutor/services/llm/context_window.py:8`、`deeptutor/services/llm/context_window.py:60`。

### 认证和受控多用户

- 认证默认关闭，但当前本地配置已打开：`data/user/settings/auth.json:3`。
- 当前 PocketBase 为空，符合默认 JSON/SQLite 多用户路径：`data/user/settings/integrations.json:3`。
- `/register` 仍是首个管理员邮箱密码 bootstrap 入口；普通自注册只有在 `public_registration_enabled=true` 时开放，并限定 email + password，创建 `role=user`：`deeptutor/api/routers/auth.py:90` 到 `deeptutor/api/routers/auth.py:114`，`deeptutor/api/routers/auth.py:632` 到 `deeptutor/api/routers/auth.py:746`。
- 公开注册开关默认关闭，且默认要求用户协议确认：`deeptutor/services/config/runtime_settings.py:32` 到 `deeptutor/services/config/runtime_settings.py:42`。
- 管理员创建用户接口存在，且新用户默认 `role=user`；用户清单 CSV 导出不会包含密码或 hash，CSV 导入只接受邮箱密码并固定创建普通用户；`auth.max_users` 大于 0 时会在公开注册、邀请码注册、管理员创建和 CSV 导入前拦截：`deeptutor/api/routers/auth.py:354` 到 `deeptutor/api/routers/auth.py:366`，`deeptutor/api/routers/auth.py:1054` 到 `deeptutor/api/routers/auth.py:1136`，`deeptutor/api/routers/auth.py:1171` 到 `deeptutor/api/routers/auth.py:1242`。
- 已支持用户自助改密码、普通用户自助导出和用当前密码自助注销；管理员重置密码、停用/启用用户、停用原因、强制登出仍走后台：`deeptutor/api/routers/auth.py:848` 到 `deeptutor/api/routers/auth.py:948`，`deeptutor/api/routers/auth.py:1245` 到 `deeptutor/api/routers/auth.py:1333`。
- 标准 JWT 已带 `token_version`，解码时会重新检查用户存在、未 disabled、user id 匹配和 token version 匹配，并使用服务端当前 role：`deeptutor/services/auth.py:251` 到 `deeptutor/services/auth.py:320`。
- 主业务 HTTP router 基本都挂了认证依赖：`deeptutor/api/main.py:384` 到 `deeptutor/api/main.py:477`。
- 认证开启时 CORS 从宽松模式切到显式 origin：`deeptutor/api/main.py:110` 到 `deeptutor/api/main.py:120`。
- Cookie 写接口有 Origin/Referer 防护；主要非 auth 写接口有文件型按 IP + principal 的基础限流：`deeptutor/api/main.py:262` 到 `deeptutor/api/main.py:293`。
- 主要 WebSocket LLM turn 入口也有限流：统一 `/api/v1/ws` 在 start/regenerate 前限流，旧 `/chat` 和 partner WebSocket 在启动模型 turn 前限流：`deeptutor/api/routers/unified_ws.py:81` 到 `deeptutor/api/routers/unified_ws.py:151`，`deeptutor/api/routers/chat.py:93` 到 `deeptutor/api/routers/chat.py:102`，`deeptutor/api/routers/partners.py:1091` 到 `deeptutor/api/routers/partners.py:1101`。
- 附件下载会先在当前用户 session store 里确认 session 存在，再解析本地附件路径：`deeptutor/api/routers/attachments.py:54` 到 `deeptutor/api/routers/attachments.py:97`。

### 用户隔离和授权

- 数据布局按 `data/user`、`data/users/<uid>`、`data/system` 区分：`deeptutor/multi_user/paths.py:1` 到 `deeptutor/multi_user/paths.py:10`。
- 非管理员用户会落到独立 workspace：`deeptutor/multi_user/paths.py:98` 到 `deeptutor/multi_user/paths.py:121`。
- SQLite session store 按当前 path service 取不同 chat DB，并按 DB path 缓存实例：`deeptutor/services/session/sqlite_store.py:99`、`deeptutor/services/session/sqlite_store.py:1836`。
- 非管理员只能看到管理员授权的 LLM：`deeptutor/multi_user/model_access.py:77` 到 `deeptutor/multi_user/model_access.py:96`。
- 非管理员选择未授权 LLM 会被拒绝：`deeptutor/multi_user/model_access.py:115` 到 `deeptutor/multi_user/model_access.py:125`。
- 知识库支持普通用户自己的 KB，以及管理员分配的只读 KB：`deeptutor/multi_user/knowledge_access.py:68` 到 `deeptutor/multi_user/knowledge_access.py:150`。
- MCP 工具默认对非管理员关闭，需显式授权：`deeptutor/multi_user/tool_access.py:51` 到 `deeptutor/multi_user/tool_access.py:65`。
- MCP 配置本身是管理员专属：`deeptutor/api/routers/mcp_settings.py:8` 到 `deeptutor/api/routers/mcp_settings.py:34`。

### 执行工具和审计雏形

- `exec` 对普通用户只在系统级隔离后端可用：`deeptutor/services/sandbox/config.py:7` 到 `deeptutor/services/sandbox/config.py:16`。
- `exec` 有用户维度的进程内并发和分钟级次数限制：`deeptutor/services/sandbox/quota.py:1` 到 `deeptutor/services/sandbox/quota.py:13`。
- 审计文件存在，是 best-effort JSONL；管理员可按 action/actor/target 查询最新审计事件。用户自助导出/注销、管理员用户创建、CSV 批量导入、重置密码、停用/启用、停用原因、强制登出、删除、角色变更会写审计；grant 变更也会记录 quota 摘要：`deeptutor/multi_user/audit.py:13` 到 `deeptutor/multi_user/audit.py:105`，`deeptutor/api/routers/auth.py:873` 到 `deeptutor/api/routers/auth.py:948`，`deeptutor/api/routers/auth.py:1127` 到 `deeptutor/api/routers/auth.py:1394`，`deeptutor/multi_user/router.py:143` 到 `deeptutor/multi_user/router.py:209`。

### LLM usage、quota 和数据治理

- 用户 grant 已包含每日/月度 token、调用次数、成本 quota；0 表示不限额：`deeptutor/multi_user/grants.py:17` 到 `deeptutor/multi_user/grants.py:83`。
- LLM turn 开始前会检查当前用户 quota，超额会阻断 provider 调用：`deeptutor/services/session/turn_runtime.py:1400` 到 `deeptutor/services/session/turn_runtime.py:1408`。
- Turn result 中的 `cost_summary` 会被提取、合并，并在回答保存后记录到 usage ledger：`deeptutor/services/session/turn_runtime.py:105` 到 `deeptutor/services/session/turn_runtime.py:130`，`deeptutor/services/session/turn_runtime.py:1692` 到 `deeptutor/services/session/turn_runtime.py:1768`。
- 文件型 usage ledger 支持今日/月度/累计聚合，并用本机文件锁保护追加、读取和保留期清理；PostgreSQL shared_state 模式会把 usage events 写入数据库：`deeptutor/multi_user/usage.py`、`deeptutor/multi_user/shared_state.py`、`deeptutor/multi_user/data_governance.py`。
- 管理员可通过 multi-user API 查询用户 usage/quota，并导出用户数据 zip：`deeptutor/multi_user/router.py:212` 到 `deeptutor/multi_user/router.py:230`。
- 管理后台授权编辑器可展示今日用量并编辑 quota：`web/features/multi-user/components/GrantEditor.tsx:21` 到 `web/features/multi-user/components/GrantEditor.tsx:57`，`web/features/multi-user/components/GrantEditor.tsx:165` 到 `web/features/multi-user/components/GrantEditor.tsx:205`，`web/features/multi-user/components/GrantEditor.tsx:638` 到 `web/features/multi-user/components/GrantEditor.tsx:660`。
- 用户数据导出包含 workspace、账号元数据、grant、头像文件、该用户 usage 和相关 audit；普通用户可在个人资料页自助导出，也可用当前密码注销自己的普通用户账号；删除用户默认保留数据，也可显式归档或删除 workspace/grant/avatar：`deeptutor/multi_user/data_governance.py`，`deeptutor/api/routers/auth.py`。
- 数据治理设置包含 audit、usage、deleted user 保留天数；0 表示永久保留。管理员可手动触发保留期清理，清理过期 audit JSONL、usage JSONL 和 deleted-user 归档；当前仍没有后台定时任务：`deeptutor/multi_user/data_governance.py:13` 到 `deeptutor/multi_user/data_governance.py:122`，`deeptutor/multi_user/router.py:161` 到 `deeptutor/multi_user/router.py:181`。
- TTS/STT 路由会在调用 provider 前执行当前用户 quota 检查，并在成功后记录一次 `total_calls`：`deeptutor/api/routers/voice.py:78` 到 `deeptutor/api/routers/voice.py:156`。
- Web search 会在调用 provider 前执行当前用户 quota 检查，并在成功后记录一次 `total_calls`：`deeptutor/services/search/__init__.py:73` 到 `deeptutor/services/search/__init__.py:193`。
- Embedding client 会在调用 provider 前执行当前用户 quota 检查，并在成功后按返回向量数量记录 `total_calls`：`deeptutor/services/embedding/client.py:17` 到 `deeptutor/services/embedding/client.py:254`。
- 系统状态会暴露本地 storage 和 quota store 可写性，非管理员不会看到服务器路径：`deeptutor/api/routers/system.py:25` 到 `deeptutor/api/routers/system.py:127`。

## 开放 SaaS 缺口清单

### P0：上线前必须补齐

1. 自助注册体系不完整

当前代码已支持默认关闭的普通用户邮箱 + 密码注册，不做手机号/SMS/OTP 验证码；首个管理员 bootstrap 也要求邮箱 + 密码；公开注册提交同意时会持久化 `terms_accepted` / `terms_accepted_at` / `terms_version` / `privacy_version`；公开邮箱注册需要通过注册限流和服务端签名 proof-of-work challenge；`auth.registration_review_required=true` 时，公开自助注册用户会先进入 disabled 待审核状态；管理员可生成一次性邀请码，公开注册关闭时用户也可凭邀请码用邮箱 + 密码注册普通账号；管理员手动创建和 CSV 批量导入普通用户也只走邮箱密码；`auth.max_users` 可作为受控 beta 的全局账号上限。它适合受控 beta，但离公开 SaaS 仍缺邮件确认、忘记密码、真实 CAPTCHA/风控服务，以及法务文本快照等更完整的同意证明。

证据：默认开关在 `deeptutor/services/config/runtime_settings.py:32` 到 `deeptutor/services/config/runtime_settings.py:42`；邮箱注册、注册 challenge、邀请码和同意记录路径在 `deeptutor/api/routers/auth.py`，邀请存储在 `deeptutor/multi_user/invites.py`，用户记录字段在 `deeptutor/multi_user/identity.py`，CSV 导入导出在 `deeptutor/api/routers/auth.py`，全局账号上限配置在 `deeptutor/services/config/runtime_settings.py` 和 `deeptutor/api/routers/auth.py`。

2. 账号生命周期不完整

已经有用户自己改密码、普通用户自助导出、普通用户用当前密码自助注销、管理员重置密码、管理员停用/启用用户，以及管理员强制用户全端登出。仍缺忘记密码、邮件确认、绑定/更换邮箱、MFA、OAuth/SSO 登录、注销冷静期和恢复流程。仓库里的 `oauth-cli-kit` 是 provider 登录/CLI 授权相关依赖，不等于 Web 用户 OAuth/SSO 登录能力。

证据：已实现改密码、自助导出、自助注销和管理员重置/停用/强制登出：`deeptutor/api/routers/auth.py:848` 到 `deeptutor/api/routers/auth.py:948`，`deeptutor/api/routers/auth.py:1245` 到 `deeptutor/api/routers/auth.py:1333`。

3. Token 撤销已支持文件模式和 PostgreSQL shared_state

账号状态和角色变更已经进入认证链路：disabled 用户不能登录，JWT 解码会重新检查用户存在、disabled、user id 和 token version，角色以服务端当前记录为准；改密码、停用、角色变更会 bump token version。默认文件模式下，用户文件写路径有本机文件锁和原子替换，适合单副本 beta；配置 PostgreSQL shared_state 后，auth secret、用户记录和 token_version 进入数据库，所有实例会看到同一份撤销状态。`logout` 仍只是删除当前浏览器 cookie，没有独立服务端 session 表。

证据：JWT 生成/校验在 `deeptutor/services/auth.py:251` 到 `deeptutor/services/auth.py:320`；token version bump 和用户文件写锁在 `deeptutor/multi_user/identity.py`；logout 只删 cookie：`deeptutor/api/routers/auth.py:518` 到 `deeptutor/api/routers/auth.py:522`。

4. 删除用户已有数据策略，但不是完整合规删除

删除用户默认仍保留 `data/users/<uid>` 和本地头像文件，但管理员删除接口、`/admin/users` 删除确认和普通用户自助注销均已支持 `data_action=keep|archive|delete`：`keep` 保留 workspace/grant/avatar，`archive` 移动到 `data/system/deleted_users/`，`delete` 删除 workspace/grant/avatar。数据治理设置已能配置 audit/usage/deleted-user 保留天数，并可由管理员手动触发清理。剩余问题是保留期当前没有后台定时任务，也没有法务审批、注销冷静期或恢复流程。

证据：普通用户自助注销路由 `deeptutor/api/routers/auth.py:908` 到 `deeptutor/api/routers/auth.py:948`；管理员删除路由 `deeptutor/api/routers/auth.py:1336` 到 `deeptutor/api/routers/auth.py:1365`；数据策略实现：`deeptutor/multi_user/data_governance.py:159` 到 `deeptutor/multi_user/data_governance.py:192`。

5. 有 LLM、语音、search 和 embedding usage/quota；账单/支付本轮不纳入

代码现在会把 LLM turn 的 `cost_summary` 持久化到用户维度 usage ledger，并支持每日/月度 token、调用次数和成本 hard quota。TTS/STT/search/embedding 已按调用次数接入同一 quota ledger；文件模式下 usage ledger 仍是带本机文件锁的单副本 beta，PostgreSQL shared_state 模式下 grant quota 和 usage ledger 进入数据库，可跨多副本共享。embedding 目前按返回向量数量计调用，不估算真实 token 成本。本轮明确不设计套餐、余额、超额扣费、支付回调、发票或订阅状态。

证据：usage/quota 实现在 `deeptutor/multi_user/usage.py`；turn runtime 调用在 `deeptutor/services/session/turn_runtime.py:1400` 到 `deeptutor/services/session/turn_runtime.py:1768`；语音路由调用在 `deeptutor/api/routers/voice.py:78` 到 `deeptutor/api/routers/voice.py:156`；search 调用在 `deeptutor/services/search/__init__.py:73` 到 `deeptutor/services/search/__init__.py:193`；embedding 调用在 `deeptutor/services/embedding/client.py:17` 到 `deeptutor/services/embedding/client.py:254`。代码搜索仍没有发现真实支付/账单模块，`stripe|checkout|billing|invoice|payment` 只命中非支付语义的 subscription 文本；该模块不作为本轮目标。

6. 生产级限流和登录保护不足

已加入滑动窗口限流：登录按 IP + username，注册按 IP + email，非 auth 写接口按 IP + principal，WebSocket 认证入口也有限流。文件模式 bucket 可在同一 `data/system/rate` 挂载下跨本机 worker 共享；PostgreSQL shared_state 模式下 bucket 进入数据库，可跨多副本共享。剩余问题是没有账号锁定策略、真实 CAPTCHA 服务、风控评分和租户级限流。

证据：限流器在 `deeptutor/api/security.py`；登录/注册限流在 `deeptutor/api/routers/auth.py`；API 写限流在 `deeptutor/api/main.py`；WebSocket 连接和 turn 限流在 `deeptutor/api/routers/auth.py`、`deeptutor/api/routers/unified_ws.py`、`deeptutor/api/routers/chat.py`、`deeptutor/api/routers/question.py`、`deeptutor/api/routers/book.py`、`deeptutor/api/routers/quiz_judge.py` 和 `deeptutor/api/routers/partners.py`。

7. Cookie 写接口已有 Origin/Referer 防护，但还不是完整 CSRF 体系

后端登录会设置 `dt_token` HTTP-only cookie；当前写接口会校验 Origin/Referer，bearer-token 客户端绕过该检查。对可控 beta 这足够简单；正式 SaaS 若需要复杂跨域 cookie、嵌入式客户端或第三方集成，仍应补 CSRF token/双提交 cookie、明确的 bearer-token 策略和安全测试矩阵。

证据：SameSite/secure 选择在 `deeptutor/api/routers/auth.py:28` 到 `deeptutor/api/routers/auth.py:33`；Origin/Referer 检查在 `deeptutor/api/security.py:94` 到 `deeptutor/api/security.py:118`；中间件调用在 `deeptutor/api/main.py:262` 到 `deeptutor/api/main.py:293`。

8. 当前安全 cookie 配置还不是生产值

默认 `auth.cookie_secure=false`，方便本地开发。公网 HTTPS 且跨站 cookie 场景需要设为 true，并精确配置 CORS origin。

证据：默认值在 `deeptutor/services/config/runtime_settings.py:32` 到 `deeptutor/services/config/runtime_settings.py:42`；CORS 认证模式要求显式 origin：`deeptutor/api/main.py:110` 到 `deeptutor/api/main.py:120`。

9. 文件型用户存储不适合直接作为正式多副本用户库

当前用户文件写路径有本机进程锁和原子替换，可避免同一台机器上的注册、停用、改角色、改密码等写操作互相覆盖；普通鉴权读取不加锁。它仍不是外部共享用户库，跨机器多副本应使用 PostgreSQL shared_state。该模式用数据库事务锁保护用户写路径，避免多副本首个 admin 竞态，并把用户记录/token_version 作为共享撤销状态。

证据：`deeptutor/multi_user/identity.py`。

10. 多租户组织模型缺失

当前角色只有 `admin` / `user`，scope 也只有 `admin` / `user`；已补的 `auth.max_users` 只是全局账号上限，不是 organization、team、workspace、seat、owner、manager、member 等 SaaS 常见模型。

证据：`deeptutor/multi_user/models.py:9` 到 `deeptutor/multi_user/models.py:10`。

### P1：商业化前应补齐

1. PocketBase 已明确不是 SaaS 多用户底座

当前 `pocketbase_store.py` 已经有 session `user_id` 过滤，但 `multi_user/__init__.py` 和 README 仍声明 PocketBase 单用户，并指出 PocketBase `users` collection 默认没有 `role` 字段。生产安全告警和系统部署状态也会在 `pocketbase_url` 非空时提示 PocketBase 不支持多用户/SaaS。公开 SaaS 不能依赖 PocketBase 路径，除非后续重新统一 schema、role、session/message/turn 查询、测试和文档。

证据：PocketBase session 过滤：`deeptutor/services/session/pocketbase_store.py:68` 到 `deeptutor/services/session/pocketbase_store.py:99`；支持矩阵仍写单用户：`deeptutor/multi_user/__init__.py:13` 到 `deeptutor/multi_user/__init__.py:18`，README 也要求多用户保持 PocketBase 为空：`README.md:625`；生产告警和部署状态：`deeptutor/api/security.py:78` 到 `deeptutor/api/security.py:103`，`deeptutor/api/routers/system.py:44` 到 `deeptutor/api/routers/system.py:66`。

2. 审计日志仍不是生产级审计系统

审计仍是 JSONL 追加；写入或读取失败不会阻断业务请求，但会记录服务端日志。当前已经覆盖管理员用户 CRUD、CSV 批量导入、grant 变更、skill 安装、模型目录变更、MCP 配置变更和用户导出，并提供管理员查询 API 和基础保留期配置；但仍缺管理员查看/导出敏感数据的审批、不可篡改存储和生产级查询/留存系统。

证据：审计文件读写和失败日志：`deeptutor/multi_user/audit.py`；当前用户操作审计：`deeptutor/api/routers/auth.py`；grant、用户导出和审计查询 API：`deeptutor/multi_user/router.py`；模型目录和 MCP 配置审计：`deeptutor/api/routers/settings.py`，`deeptutor/api/routers/mcp_settings.py`。

3. 附件访问边界仍偏弱

附件下载路由会先用当前用户的 session store 确认 session 存在，已经能挡住跨用户猜 session_id 的直接下载。剩余问题是文件 URL 仍是长期静态路径，没有短期签名 URL、对象存储访问策略和下载审计；正式 SaaS 仍建议升级 signed URL。

证据：session ownership 检查和 serve 逻辑在 `deeptutor/api/routers/attachments.py:54` 到 `deeptutor/api/routers/attachments.py:97`。

4. 共享能力已有调用次数额度，但缺少真实成本计量

TTS/STT/search/embedding 已按调用次数接入用户 quota，但还没有按真实 token/秒数/供应商成本计量。embedding 仍按部署 active profile 解析，不走 per-user embedding model grant。开放 SaaS 要继续把这些共享能力统一纳入精确成本、审计和功能权限。

证据：voice quota 和记录：`deeptutor/api/routers/voice.py:78` 到 `deeptutor/api/routers/voice.py:156`；search quota 和记录：`deeptutor/services/search/__init__.py:73` 到 `deeptutor/services/search/__init__.py:193`；embedding quota 和记录：`deeptutor/services/embedding/client.py:17` 到 `deeptutor/services/embedding/client.py:254`；grant 的模型授权仍只保存 LLM，不包含 per-user embedding model grant：`deeptutor/multi_user/model_access.py:1` 到 `deeptutor/multi_user/model_access.py:6`。

5. Secret 管理仍是本地配置文件形态

Provider API key 存在 `data/user/settings/model_catalog.json`。私有部署可接受，但 SaaS 需要密钥管理、加密、轮换、权限分离、备份脱敏和禁止下载/暴露策略。

证据：项目文档说明配置和 API keys 持久化在 data volume：`README.md:279`；设置文件是 `data/user/settings/*.json`：`README.md:604`。

6. 部署模板和共享状态底座已补，文件资产仍需共享存储

`docker-compose.ghcr.yml` 已改为完整挂载 `./data:/app/data`，不会再漏掉 `data/system`、`data/users`、`data/partners`、`data/system/usage`。默认文件模式仍明确为 `single_replica_beta`：auth/token-version revocation、限流、usage/quota 都是文件型 beta。配置 `data/user/settings/shared_state.json` 或环境变量 `DEEPTUTOR_SHARED_STATE_PROVIDER=postgres`、`DEEPTUTOR_DATABASE_URL=...` 后，auth secret、用户记录/token_version、注册邀请码、rate limit、grant quota 和 usage ledger 会使用 PostgreSQL；系统状态会把 auth/token/rate/quota/invites 标为 `postgres`，多 worker 不再触发健康检查失败，并会探测共享状态库连接。启用 PocketBase 时仍会额外标记 `pocketbase_multi_user_supported=false`。附件、知识库、导出文件等仍依赖共享 `data/` volume 或后续对象存储。

证据：GHCR compose 挂载和 shared-state env：`docker-compose.ghcr.yml:49` 到 `docker-compose.ghcr.yml:61`；共享状态实现：`deeptutor/multi_user/shared_state.py`；健康检查和部署状态字段：`deeptutor/api/routers/system.py:25` 到 `deeptutor/api/routers/system.py:170`。

7. 管理后台能力仍不够 SaaS 化

当前 `/admin/users` 支持邮箱密码创建、删除、改角色、停用/启用、记录停用原因、重置密码、强制登出、分配资源、单用户数据 zip 导出、用户清单 CSV 导出、邮箱密码 CSV 批量导入普通用户、删除数据策略选择、创建一次性注册邀请码，并可在授权编辑器查看今日用量和编辑 quota；`auth.max_users` 可限制全局账号总数；页面也提供最近审计事件查看。普通用户可在 `/profile` 导出自己的数据并用当前密码注销账号。仍缺组织/团队批量导入、批量 grant 分配、导入预览/错误报告等生产级运营能力。

证据：后端用户管理接口覆盖 list/export CSV/import CSV/create/reset password/disable/revoke/delete/role：`deeptutor/api/routers/auth.py:354` 到 `deeptutor/api/routers/auth.py:366`，`deeptutor/api/routers/auth.py:1054` 到 `deeptutor/api/routers/auth.py:1394`；管理前端 CSV 导入导出和邮箱创建入口在 `web/lib/admin-api.ts:22` 到 `web/lib/admin-api.ts:60`，`web/app/(admin)/admin/users/page.tsx:307` 到 `web/app/(admin)/admin/users/page.tsx:440`，`web/app/(admin)/admin/users/page.tsx:1159` 到 `web/app/(admin)/admin/users/page.tsx:1169`；profile 自助入口在 `web/lib/profile-api.ts:95` 到 `web/lib/profile-api.ts:130` 和 `web/app/(utility)/profile/page.tsx:511` 到 `web/app/(utility)/profile/page.tsx:605`。

8. 数据合规能力缺失

当前已有管理员用户数据导出 zip、普通用户自助导出 zip、普通用户当前密码确认注销、删除用户时的 `keep` / `archive` / `delete` workspace/grant/avatar 策略、公开注册基础同意记录、协议版本记录、停用原因、基础保留期配置和管理员手动保留期清理。仍缺管理员访问用户数据的审批、区域化存储、后台定时执行的 usage/audit 清理或留存流程、法务文本快照、注销冷静期和恢复流程等完整 SaaS 合规能力。

证据：数据治理设置、导出和删除策略在 `deeptutor/multi_user/data_governance.py:13` 到 `deeptutor/multi_user/data_governance.py:209`；自助导出/注销在 `deeptutor/api/routers/auth.py:873` 到 `deeptutor/api/routers/auth.py:948`；管理员删除接口调用策略在 `deeptutor/api/routers/auth.py:1336` 到 `deeptutor/api/routers/auth.py:1365`；审计仍不是生产级审计系统，见上文。

### P2：成熟 SaaS 需要补齐

1. 可观测性和运营后台

需要指标、日志聚合、错误追踪、慢请求、LLM provider 成功率/延迟/成本、队列积压、用户行为漏斗、告警和运营 dashboard。当前代码有局部 logger 和 response metadata，但不是 SaaS 运营体系。

2. 备份、迁移和灾备

当前设计强调一个 `data/` tree 需要挂载和备份，但公开 SaaS 还需要自动备份、恢复演练、schema migration、版本兼容、数据校验和灾备 RPO/RTO。

证据：数据树说明：`deeptutor/multi_user/paths.py:3` 到 `deeptutor/multi_user/paths.py:10`。

3. 内容安全和滥用治理

开放 SaaS 需要内容安全策略、文件安全扫描、提示注入防护策略、恶意代码执行审计、用户封禁、投诉处理、模型输出风险提示等。当前 sandbox 和上传校验有基础防护，但不是完整运营治理。

4. 测试矩阵

需要覆盖公开注册、登录失败、CSRF、防越权、用户数据隔离、管理员授权、计费扣量、限流、多 worker 竞态、备份恢复、升级迁移、Docker 模板等端到端测试。

## 建议部署边界

### 可以现在做的部署

可以作为“私有受控多用户”部署，前提是：

- 使用默认 JSON/SQLite 多用户路径，保持 `data/user/settings/integrations.json` 里的 `pocketbase_url` 为空。
- 默认文件模式保持单 FastAPI worker / 单应用副本；如需多副本，配置 PostgreSQL shared_state，并确保附件、知识库和导出文件走共享 `data/` volume 或对象存储。
- 使用 `docker-compose.yml`、`docker-compose.ghcr.yml` 或等价的完整 `./data:/app/data` 挂载。
- 通过 HTTPS 反向代理暴露 frontend，backend 只内网访问。
- 设置 `auth.cookie_secure=true`，并在 `data/user/settings/system.json` 里精确配置公网 frontend origin。
- 启动后只开放 `/register` 用邮箱密码创建首个 admin，然后由 admin 添加用户、CSV 批量导入用户和授权资源；受控 beta 可设置 `auth.max_users` 控制账号总数。
- 如果要做受控 beta 自助注册，优先由 admin 发一次性邮箱邀请码；也可以开启 `auth.public_registration_enabled`，但只使用邮箱 + 密码注册，并保留限流、用户协议确认和人工运营监控；不要加入手机号/SMS 验证码注册。
- 建立 `data/` 备份策略，并把 `data/user/settings/model_catalog.json` 当作敏感密钥文件处理。

### 不建议现在做的部署

不建议直接开放成公众 SaaS，尤其不建议：

- 允许陌生用户自助注册。
- 多副本/多 worker 直接共享当前 JSON 用户文件，而不是配置 PostgreSQL shared_state。
- 多副本部署时仍依赖单机 JSON 里的 `token_version`，没有启用 PostgreSQL shared_state 来处理用户停用、删除、改密、强制登出或管理员降权。
- 把 PocketBase 当作已完成的多用户后端。
- 没有配置用户 quota、运营监控和共享 quota store 就开放高成本模型。
- 没有 CSRF/登录限流/密钥治理就暴露到公网。

## 最小改造路线

如果目标是尽快上线一个可控 beta，而不是完整 SaaS，建议最小路线是：

1. 已完成：账号停用执行、管理员重置密码、用户修改密码。
2. 已完成：鉴权链路校验用户存在、disabled、当前 role 和 token version。
3. 已完成：登录/注册/API 写接口/WebSocket 入口的基础限流。
4. 已完成：cookie 写接口 Origin/Referer 校验。
5. 已完成：持久化每个用户的 LLM usage/cost，并加 hard quota；TTS/STT/search/embedding 已按调用次数纳入同一 quota ledger。
6. 已完成 beta：用户数据导出，以及删除用户时保留/归档/删除 workspace/grant/avatar 的策略。
7. 已完成 beta：PocketBase 保留单用户集成，并在生产告警/部署状态里明确禁用多用户/SaaS 路径。
8. 已完成：修正 `docker-compose.ghcr.yml` 的多用户持久化挂载。
9. 已完成 beta：管理员一次性邮箱邀请码；若开放 beta 注册，继续保持邮箱 + 密码方案，不引入手机号/SMS 验证码。
10. 已完成 beta：管理员用户清单 CSV 导出和邮箱密码 CSV 批量导入普通用户；正式 SaaS 仍需导入预览、错误报告、批量授权和席位约束。
11. 已完成 beta：全局 `auth.max_users` 账号上限；正式 SaaS 仍需组织/团队/席位模型。

如果目标是正式开放 SaaS，还需要在上述基础上继续补：

- 邮箱密码注册、一次性邀请码、邮箱密码 CSV 导入 beta 已有；正式 SaaS 仍需可选邮件确认、忘记密码、注册审核、MFA/OAuth/SSO。明确不做手机号/SMS/OTP 验证码注册。
- 组织/团队/席位/租户模型；当前只有全局 `auth.max_users`。
- 账单/支付本轮明确不纳入，后续需要具体商业化方案后再单独规划。
- 外部数据库和共享身份存储。
- 不可抵赖审计、用户数据导出/删除、合规记录。
- 生产可观测性、告警、备份恢复和安全测试矩阵。
