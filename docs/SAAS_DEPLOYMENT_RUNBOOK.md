# DeepTutor SaaS Deployment Runbook

日期：2026-06-30

本文只覆盖当前代码可支持的受控 beta / 私有多用户部署。正式公开 SaaS 仍需要外部用户库、强一致 quota store 和完整合规治理；当前文件型限流和带文件锁的 usage ledger 只适合受控 beta。账单/支付本轮不纳入。

## 当前推荐拓扑

- 单 FastAPI worker / 单应用副本。
- 使用默认 JSON/SQLite 多用户路径，保持 `pocketbase_url` 为空。
- Docker volume 必须完整挂载 `./data:/app/data`。
- HTTPS 反向代理在外层终止 TLS。
- 生产公网开启 auth 时必须配置 `cookie_secure=true` 和显式 CORS origin。

## 需要备份的数据

完整备份项目运行目录下的 `data/`：

- `data/system/auth/`：用户、JWT secret、头像。
- `data/system/grants/`：用户资源授权和 quota。
- `data/system/audit/`：管理员操作和资源访问审计 JSONL。
- `data/system/usage/`：LLM usage/quota 账本。
- `data/users/<uid>/`：普通用户 workspace、会话、知识库、memory、notebook。
- `data/user/`：管理员 workspace 和 provider/settings 配置。
- `data/partners/`：伙伴/synthetic user workspace。

`data/user/settings/model_catalog.json` 含 provider API key，备份介质必须按密钥处理。

## 备份流程

1. 暂停应用写入，或先停止容器。
2. 归档整个 `data/` 目录。
3. 将归档上传到加密存储。
4. 记录应用版本、镜像 tag、备份时间和恢复目标。

示例：

```bash
docker compose stop deeptutor
tar -czf deeptutor-data-$(date -u +%Y%m%dT%H%M%SZ).tgz data
docker compose start deeptutor
```

## 恢复流程

1. 停止应用。
2. 将现有 `data/` 移走保留，不要覆盖。
3. 解压备份为新的 `data/`。
4. 启动应用。
5. 用 admin 登录验证用户列表、grants、usage、知识库和最近会话。

示例：

```bash
docker compose stop deeptutor
mv data data.before-restore.$(date -u +%Y%m%dT%H%M%SZ)
tar -xzf deeptutor-data-YYYYMMDDTHHMMSSZ.tgz
docker compose up -d
```

## 多副本前置条件

不要在当前文件型状态下直接水平扩容。多副本前至少需要：

- 外部用户库或数据库事务，替代 `data/system/auth/users.json`。
- 共享 token revocation/session store，替代本地 `token_version` 文件。
- 强一致 quota store，替代 JSONL usage 账本；文件型限流和带文件锁的 usage ledger 只能作为受控 beta 过渡方案。
- 对象存储或共享文件系统，承载 attachments、knowledge bases、exports。
- 可查询审计存储和备份恢复演练。
