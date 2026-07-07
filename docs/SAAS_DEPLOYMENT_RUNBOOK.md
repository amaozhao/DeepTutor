# DeepTutor SaaS Deployment Runbook

日期：2026-07-07

本文覆盖当前代码可支持的受控 beta / 私有多用户部署，以及 PostgreSQL shared_state 支撑的多副本基础。当前已有 MVP 数据治理底线：best-effort 审计 JSONL、用户数据导出、删除数据策略和管理员手动保留期清理。正式公开 SaaS 仍需要对象存储、生产级审计存储、运营监控，以及审批流、法务文本快照、区域化存储等合规增强；当前文件型限流、用户文件写锁和带文件锁的 usage ledger 只适合单副本 beta。账单/支付本轮不纳入。

## 当前推荐拓扑

- 单 FastAPI worker / 单应用副本。
- 使用默认 JSON/SQLite 多用户路径，保持 `pocketbase_url` 为空。
- Docker volume 必须完整挂载 `./data:/app/data`。
- HTTPS 反向代理在外层终止 TLS。
- 生产公网开启 auth 时必须配置 `cookie_secure=true` 和显式 CORS origin。

## 需要备份的数据

文件模式下，完整备份项目运行目录下的 `data/`：

- `data/system/auth/`：用户、JWT secret、头像。
- `data/system/grants/`：用户资源授权和 quota。
- `data/system/audit/`：管理员操作和资源访问审计 JSONL。
- `data/system/usage/`：LLM usage/quota 账本。
- `data/users/<uid>/`：普通用户 workspace、会话、知识库、memory、notebook。
- `data/user/`：管理员 workspace 和 provider/settings 配置。
- `data/partners/`：伙伴/synthetic user workspace。

`data/user/settings/model_catalog.json` 含 provider API key，备份介质必须按密钥处理。

PostgreSQL shared_state 模式下，还必须备份 `DEEPTUTOR_DATABASE_URL`
指向的数据库；auth secret、用户记录/token_version、注册邀请码、grant
quota 和 usage ledger 已进入 PostgreSQL，不能只备份 `data/`。

## 备份流程

1. 暂停应用写入，或先停止容器。
2. 归档整个 `data/` 目录。
3. 如果启用 PostgreSQL shared_state，同时导出数据库。
4. 将归档上传到加密存储。
5. 记录应用版本、镜像 tag、备份时间和恢复目标。

示例：

```bash
docker compose stop deeptutor
tar -czf deeptutor-data-$(date -u +%Y%m%dT%H%M%SZ).tgz data
pg_dump "$DEEPTUTOR_DATABASE_URL" -Fc -f deeptutor-shared-state-$(date -u +%Y%m%dT%H%M%SZ).dump
docker compose start deeptutor
```

## 恢复流程

1. 停止应用。
2. 将现有 `data/` 移走保留，不要覆盖。
3. 解压备份为新的 `data/`。
4. 如果启用 PostgreSQL shared_state，先恢复数据库备份。
5. 启动应用。
6. 用 admin 登录验证用户列表、grants、usage、知识库和最近会话。

示例：

```bash
docker compose stop deeptutor
mv data data.before-restore.$(date -u +%Y%m%dT%H%M%SZ)
tar -xzf deeptutor-data-YYYYMMDDTHHMMSSZ.tgz
pg_restore --clean --if-exists -d "$DEEPTUTOR_DATABASE_URL" deeptutor-shared-state-YYYYMMDDTHHMMSSZ.dump
docker compose up -d
```

## 多副本前置条件

不要在默认文件型状态下直接水平扩容。多副本前至少需要：

- 配置 `DEEPTUTOR_SHARED_STATE_PROVIDER=postgres` 和 `DEEPTUTOR_DATABASE_URL=...`，让 auth secret、用户记录/token_version、注册邀请码、rate limit、grant quota 和 usage ledger 进入 PostgreSQL。
- 对象存储或共享文件系统，承载 attachments、knowledge bases、exports。
- 生产级可查询审计存储和备份恢复演练；当前 JSONL 审计只作为受控 beta 的追踪底线。

也可以通过 `data/user/settings/shared_state.json` 持久化同样配置。配置为 `postgres` 后，`/health` 会初始化并探测共享状态库；连接失败会返回 503。保持 `file` 时只适合单副本 beta。

从文件模式切到 PostgreSQL 时，如果共享用户表为空，启动后的首次用户读取会把现有 `data/system/auth/users.json` 导入 PostgreSQL；已有 `data/system/auth/auth_secret` 也会作为 PostgreSQL JWT secret 初始值，避免切换后立刻让现有 token 全部失效。
