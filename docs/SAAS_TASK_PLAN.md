# DeepTutor SaaS Task Plan

规划日期：2026-07-07

目标：把当前“受控私有多用户部署”推进到“可开放注册、可运营”的 SaaS 基础。注册方案限定为邮箱 + 密码；不做手机号/SMS 验证码注册。本轮不实现账单/支付。

当前状态（2026-07-07）：Milestone 0-4 的最小闭环已完成，其中 TTS/STT/search/embedding 已按调用次数纳入 usage/quota；Milestone 5 已完成管理员用户操作、停用原因、全局 `auth.max_users` 账号上限、grant、skill 安装、模型目录、MCP 配置、用户导出、用户清单 CSV 导出、邮箱密码批量导入普通用户、用户自助导出、账号自助注销、覆盖 workspace/grant/avatar 的删除数据策略、审计查询、注册审核开关、注册协议版本同意记录、保留期配置和管理员手动保留期清理入口的文件型 beta 闭环；Milestone 6 已修复 GHCR compose 的多用户持久化挂载，补充备份/恢复 runbook，并接入 PostgreSQL shared_state 覆盖 auth secret、用户记录/token_version、注册邀请码、rate limit、grant quota 和 usage ledger。PocketBase 明确标为非 SaaS 多用户底座。仍不建议直接公开商用 SaaS；后续重点是对象存储、审计查询存储、运营监控和完整合规治理。

## 原则

- 先做可控 beta，再做公开 SaaS。
- 先堵认证、额度、数据隔离这些会导致事故的洞，再做增长功能。
- 保持默认 JSON/SQLite 路径可用于私有部署；公开 SaaS 应使用 PostgreSQL shared_state，并继续补对象存储、审计存储和运营治理。
- PocketBase 要么完成多用户支持矩阵，要么在 SaaS 路径中明确禁用。

## Milestone 0：基线确认

状态：已完成。

目标：确认当前结论和部署边界无误。

任务：

1. 固化 SaaS readiness 文档。
2. 明确当前推荐部署：单 FastAPI worker、完整 `./data:/app/data` 挂载、`pocketbase_url` 为空。
3. 已修复 `docker-compose.ghcr.yml` 的多用户持久化坑，改为完整 `./data:/app/data` 挂载。

验收：

- `docs/SAAS_READINESS_REVIEW.md` 与代码证据一致。
- 文档明确不建议当前代码直接开放公众 SaaS。

## Milestone 1：认证与账号生命周期

状态：已完成。文件模式使用本地 token_version；PostgreSQL shared_state 模式下用户记录和 token_version 进入数据库，可跨多副本共享撤销状态。

目标：让“用户状态变化”能被系统即时执行。

任务：

1. 登录校验拒绝 `disabled=true` 用户。
2. `decode_token()` / `require_auth()` 校验用户仍存在、未 disabled、当前 role 与服务端记录一致。
3. 增加 token version 或 revocation 表，用于删除、停用、降权、重置密码后的强制失效。
4. 增加用户修改密码接口。
5. 增加管理员重置密码接口。
6. 增加管理员停用/启用用户接口和 UI，并记录停用原因。
7. 保留首个 admin bootstrap；后续账号仍可由 admin 创建。

主要代码区域：

- `deeptutor/services/auth.py`
- `deeptutor/api/routers/auth.py`
- `deeptutor/multi_user/identity.py`
- `web/app/(admin)/admin/users/page.tsx`
- `web/app/(utility)/profile/page.tsx`

验收：

- disabled 用户不能登录。
- 已登录用户被停用后，下一次 API 请求失败。
- 停用用户可保存原因，重新启用后原因清空。
- 用户被降权后，旧 admin token 不再能访问 admin API。
- 用户修改密码或管理员重置密码后，旧 token 失效。

## Milestone 2：邮箱密码注册

状态：已完成最小闭环；公开注册默认关闭。当前方案只有邮箱 + 密码，不使用手机号/SMS 验证码。

目标：支持公开或受控的邮箱 + 密码注册，不做手机号/SMS 注册。

任务：

1. 新增普通用户邮箱密码注册开关，默认关闭。
2. 注册字段限定为 email + password；首个 admin bootstrap、公开注册、邀请码注册和管理员创建普通用户都不使用手机号/SMS 验证码。
3. 增加邮箱唯一性校验。
4. 增加基础密码策略。
5. 已完成 beta：增加用户协议/隐私政策同意字段，并在公开注册提交同意时持久化 `terms_accepted` / `terms_accepted_at` / `terms_version` / `privacy_version`。
6. 已完成 beta：公开邮箱注册使用注册限流 + 服务端签名 proof-of-work challenge 作为同等反机器人保护；不使用手机号验证码。正式公开注册仍建议接入 CAPTCHA/风控服务。
7. 可选：邮件确认链接。若早期 beta 不做邮件确认，必须限制注册开关和限流。
8. 保留首个 admin bootstrap 逻辑，避免公开注册创建 admin。
9. 已完成 beta：管理员可生成一次性注册邀请码；公开注册关闭时，用户仍可凭邀请码用邮箱 + 密码注册普通账号。
10. 已完成 beta：`auth.max_users` 可设置全局账号上限，公开注册、邀请码注册、管理员创建和 CSV 导入都会在创建前拦截；0 表示不限。
11. 已完成 beta：`auth.registration_review_required` 可要求公开自助注册用户先进入 disabled 待审核状态，由管理员启用；邀请码注册视为管理员预审，不进入待审核。

主要代码区域：

- `deeptutor/api/routers/auth.py`
- `deeptutor/services/auth.py`
- `deeptutor/multi_user/identity.py`
- `web/app/(auth)/register/page.tsx`
- `web/lib/auth.ts`

验收：

- 第一个 admin 仍通过邮箱密码 bootstrap 创建。
- 普通邮箱注册只能创建 `role=user`。
- 不存在手机号、短信验证码、SMS provider 配置。
- 注册接口有速率限制和反机器人 challenge 保护。
- 需要审核时，公开自助注册用户会被创建为 disabled，并带有待审核原因。
- `auth.max_users` 大于 0 时，超过账号上限的注册/创建/CSV 导入会被拒绝且不会部分创建。
- 公开注册提交同意后会持久化用户协议/隐私政策同意记录和当前协议版本。
- 公开注册关闭时，有效邀请码只能被邮箱密码注册使用一次。

## Milestone 3：安全边界和限流

状态：已完成。文件模式提供单副本 beta 限流；PostgreSQL shared_state 模式下限流 bucket 进入数据库，可跨多副本共享。

目标：公开网络下不容易被撞库、CSRF、滥用拖垮。

任务：

1. 登录失败限流：按 IP + email 双维度。
2. 注册限流：按 IP + email。
3. 主要 LLM WebSocket turn、上传、STT/TTS/其他写接口限流：按 user_id + IP。
4. Cookie 写接口增加 CSRF token 或 Origin/Referer 校验。
5. 生产配置校验：auth enabled 时要求 HTTPS、`cookie_secure=true`、显式 CORS origins。
6. 附件下载增加 session ownership 校验；后续可升级 signed URL。

主要代码区域：

- `deeptutor/api/main.py`
- `deeptutor/api/routers/auth.py`
- `deeptutor/api/routers/attachments.py`
- `deeptutor/api/routers/voice.py`
- `deeptutor/services/session/*`

验收：

- 连续错误登录会被限流。
- 跨站 POST 写接口被拒绝。
- 用户不能通过猜 session_id 下载别人附件。
- 生产配置缺失时启动或健康检查给出明确失败/告警。

## Milestone 4：用量、额度和成本控制

状态：已完成。LLM turn 会记录 `cost_summary`；TTS、STT、search、embedding 已按调用次数纳入同一 usage/quota。文件模式适合单副本 beta；PostgreSQL shared_state 模式下 grant quota 和 usage ledger 进入数据库，可跨多副本共享。当前实现仍不是支付/订阅账单系统；embedding 目前按返回向量数量计调用，不估算真实 token 成本。

目标：每个用户的模型成本可记录、可查询、可限制。

任务：

1. 已完成：持久化 LLM turn 的 usage/cost 到 `data/system/usage/llm_usage.jsonl`。
2. 已完成：usage 绑定 user_id、username、session_id、turn_id、capability、provider、model。
3. 已完成：grant 增加每日/月度 token、调用次数、成本 hard quota；0 表示不限额。
4. 已完成 beta：TTS、STT、search、embedding 已按调用次数纳入 usage 和 quota。
5. 已完成：管理后台授权编辑器展示今日调用/token/cost，并可编辑用户 quota。
6. 已完成：非管理员超额时在 turn 开始前返回明确错误，不再调用 provider。

主要代码区域：

- `deeptutor/core/agentic/usage.py`
- `deeptutor/agents/_shared/capability_result.py`
- `deeptutor/services/llm/*`
- `deeptutor/api/routers/voice.py`
- `deeptutor/multi_user/grants.py`
- `deeptutor/multi_user/usage.py`
- `deeptutor/services/session/turn_runtime.py`
- `web/app/(admin)/admin/users/page.tsx`
- `web/features/multi-user/components/GrantEditor.tsx`

验收：

- 每次 emit `cost_summary` 的 LLM turn 都有可追踪 usage 记录。
- 用户超额后无法继续消耗模型成本。
- 管理员能看到用户维度的用量和成本。

## Milestone 5：审计和数据治理

状态：已完成文件型 beta 闭环。管理员用户 CRUD、用户停用原因、全局账号上限、grant 变更、skill 安装、模型目录变更、MCP 配置变更、用户导出、用户清单 CSV 导出和邮箱密码批量导入普通用户已写入审计或纳入创建约束；管理员可查询审计 JSONL；用户数据可由管理员或用户自己导出 zip；普通用户可在个人资料页用当前密码注销账号；删除用户支持 `keep` / `archive` / `delete` 数据策略，覆盖 workspace、grant 和本地头像文件；注册同意会记录当前协议版本；数据治理设置包含 audit/usage/deleted-user 保留天数和管理员手动清理入口。仍缺不可篡改审计存储、审批流、法务文本快照和完整合规流程。

目标：关键操作可追踪，用户数据可保留、导出、删除。

任务：

1. 已完成：用户创建、删除、停用、停用原因、启用、角色变更、重置密码写入审计。
2. 已完成 beta：grant 变更、skill 安装、模型配置变更、MCP 配置变更写入审计。
3. 已完成：用户删除增加数据策略，默认 `keep`，可显式 `archive` 或 `delete` 用户 workspace/grant/avatar。
4. 已完成：增加管理员用户数据导出 zip。
5. 已完成 beta：增加普通用户自助导出 zip 和用当前密码确认的账号自助注销；管理员账号仍需由另一个管理员处理。
6. 已完成 beta：增加 audit、usage、deleted user 的保留天数配置和管理员手动清理入口；0 表示永久保留，当前不包含后台定时任务。
7. 已完成 beta：审计 JSONL 可通过管理员 API 查询；生产级仍需不可篡改/可检索审计存储。
8. 已完成 beta：管理员可导出用户清单 CSV；可导入 `email,password` CSV 批量创建普通用户，CSV 内手机号或非邮箱账号会被拒绝且不会部分创建。
9. 已完成 beta：全局 `auth.max_users` 可限制账号总数；正式 SaaS 仍需组织/团队/席位模型。

主要代码区域：

- `deeptutor/multi_user/audit.py`
- `deeptutor/multi_user/data_governance.py`
- `deeptutor/api/routers/auth.py`
- `deeptutor/multi_user/router.py`
- `deeptutor/multi_user/paths.py`
- `web/lib/admin-api.ts`
- `web/app/(admin)/admin/users/page.tsx`

验收：

- 管理员用户操作都有审计记录。
- 管理员可导出用户清单 CSV，并可用邮箱密码 CSV 批量导入普通用户。
- 全局账号上限会在创建前生效，CSV 导入不会部分创建。
- 删除用户默认保留数据，并可显式归档或硬删除 workspace/grant/avatar。
- 用户数据可按 user_id 导出。
- 普通用户可自助导出自己的数据，并可用当前密码注销自己的账号。
- 管理员可查询审计事件，并可配置保留期策略、手动触发过期数据清理。

## Milestone 6：部署和外部存储

状态：底座完成。`docker-compose.ghcr.yml` 已改为完整 `./data:/app/data` 挂载，已补充 `docs/SAAS_DEPLOYMENT_RUNBOOK.md`。默认文件模式仍是 `single_replica_beta`；配置 `shared_state.provider=postgres` / `DEEPTUTOR_SHARED_STATE_PROVIDER=postgres` 和 `DEEPTUTOR_DATABASE_URL` 后，auth secret、用户记录/token_version、注册邀请码、rate limit、grant quota 和 usage ledger 会进入 PostgreSQL，系统状态会把 auth/token/rate/quota 标为 `postgres` 并允许多 worker 通过 `/health`。PocketBase 保留为单用户集成，启用时会在生产告警和部署状态里标记为不支持多用户/SaaS。附件、知识库和导出文件仍依赖共享 `data/` volume 或后续对象存储。

目标：支持正式 SaaS 的多 worker / 多副本部署。

任务：

1. 已完成：选择并接入 PostgreSQL 共享状态，覆盖 auth secret、用户记录/token_version、注册邀请码、rate limit、grant quota 和 usage ledger。
2. 已完成 beta：文件模式保留为单副本 beta；用户文件写路径使用本机文件锁，普通鉴权读取不加锁；限流状态放入文件型共享存储，usage ledger 使用本机文件锁。
3. 已完成：修复 `docker-compose.ghcr.yml`，改成单一 `./data:/app/data` volume。
4. 已完成 beta：明确 PocketBase 路线。当前保留单用户集成；SaaS 多用户路径在生产告警和部署状态中标记为 unsupported。
5. 已完成：增加备份/恢复文档。
6. 已完成：系统状态已包含 auth/CORS/cookie/PocketBase/多 worker 告警、provider 配置状态、storage/auth/quota/rate store 或 PostgreSQL shared-state store 健康检查；PostgreSQL 模式下 `multi_replica_ready=true`，文件模式下保持 `multi_replica_ready=false`。

验收：

- 多副本部署不会出现首个 admin 竞态。
- token 撤销、限流、quota 在多副本间一致。
- compose 模板不会丢失多用户数据。

## 暂不纳入：商业化/账单/支付

状态：暂不实现。本轮明确排除账单/支付；后续等商业化、provider、税务和运营方案确定后再单独设计。

当前只保留受控 beta 所需的全局账号上限和 per-user quota，不设计套餐、支付 provider、webhook、账单页、发票或订阅状态。

## 最短可控 beta 路线

如果只想尽快给少量用户试用：

1. 不开放公众注册，继续 admin 创建用户。
2. Milestone 1、3、4 的最小闭环已完成，继续保持单副本和用户 quota。
3. 单副本部署，完整备份 `data/`。
4. 若要开放 beta 自助注册，只开启邮箱 + 密码注册开关，保留限流和人工运营监控。
