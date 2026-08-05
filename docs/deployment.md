# DeepTutor 低成本单机生产部署指南

更新日期：2026-07-15

本文面向中国大陆家庭或小团队私有部署，目标是在一台低成本服务器上运行
DeepTutor Web 前端、FastAPI 后端、账号系统和教材知识库。主路径使用云端 LLM
和云端 Embedding，不在服务器上运行 Ollama、本地大模型或本地 Embedding 模型。

本文对应当前仓库代码。若部署的是未经修改的上游版本，可以直接使用官方 GHCR
镜像；若要保留当前分支的定制功能，必须先从当前代码构建自己的生产镜像。

## 1. 部署结论

### 1.1 最低可用配置

| 项目 | 最低配置 | 建议配置 | 说明 |
| --- | --- | --- | --- |
| CPU | 2 vCPU | 2–4 vCPU | 1 vCPU 在导入教材时容易长时间占满 |
| 内存 | 2 GB | 4 GB | 2 GB 必须配 2 GB Swap，且一次只导入一本教材 |
| 系统盘 | 40 GB SSD | 60 GB SSD | 保存容器镜像、教材、向量索引、会话和备份 |
| 公网带宽 | 3–5 Mbps | 5–10 Mbps | LLM 流量不大，教材上传速度主要受上行带宽影响 |
| 系统 | Ubuntu Server 24.04 LTS x86_64 | 同左 | Docker 官方支持，x86_64 依赖兼容性最稳妥 |
| GPU | 不需要 | 不需要 | 模型和 Embedding 均调用云服务 |
| 公网 IPv4 | 1 个 | 1 个固定 IPv4 | 用于 DNS、HTTPS 和 API Key IP 白名单 |

当前机器上的运行态测量仅用于说明量级：FastAPI 后端空闲约 312 MB，Next.js
production standalone 空闲约 109 MB。本地 `next dev` 曾占用约 2.6 GB，但它不是
生产部署方式。2 GB 服务器的剩余内存用于操作系统、Docker、教材解析和索引。

### 1.2 适用范围

最低配置适合：

- 1–3 名家庭用户；
- 同时 1 个主要对话请求；
- 一次导入一本数字版 PDF 教材；
- 使用阿里云百炼或其他云端 LLM；
- 使用阿里云 `text-embedding-v4` 等云端 Embedding；
- 使用默认单机 SQLite/JSON 状态和本地 FAISS 向量索引；
- 使用单个 DeepTutor 应用副本、单个 FastAPI worker。

最低配置不适合：

- 在服务器上运行 Ollama、vLLM、LM Studio 或任何大模型；
- 在服务器上运行本地 Embedding 模型；
- 本地运行 MinerU、Docling、GraphRAG、LightRAG 或 Manim 重任务；
- 同时导入多本大型扫描教材；
- 面向公众的大规模开放注册或商业 SaaS；
- 多副本、多 FastAPI worker 或跨机器部署。

### 1.3 不需要购买或部署的组件

这条低成本路径不需要 GPU、CUDA、Redis、PostgreSQL、Qdrant、Elasticsearch、
PocketBase、独立向量数据库或独立 Node/Python 运行环境。生产镜像已经包含
FastAPI、Next.js、Python 和 Node.js；默认 RAG 使用 LlamaIndex 与本地 FAISS。

## 2. 最终架构

```text
用户浏览器
    │ HTTPS :443
    ▼
Caddy（宿主机 TLS 和反向代理）
    │ http://127.0.0.1:3782
    ▼
DeepTutor 单容器
    ├── Next.js production :3782
    │       └── /api/*、/ws/* 转发到容器内 FastAPI
    ├── FastAPI :8001（不发布到宿主机公网）
    └── /app/data
            ├── SQLite/JSON：账号、会话、授权、用量
            ├── FAISS：教材向量索引
            ├── 教材、附件、笔记和记忆
            └── provider 配置与 API Key

FastAPI ──HTTPS──► 阿里云百炼 LLM
FastAPI ──HTTPS──► 阿里云 Embedding
FastAPI ──HTTPS──► 可选的 MinerU Cloud / 搜索服务
```

浏览器只访问前端域名。当前 [web/proxy.ts](../web/proxy.ts) 会在 Next.js
服务器端把 `/api/*` 和 `/ws/*` 转发给 FastAPI，因此公网不需要暴露 8001。

## 3. 外部依赖清单

### 3.1 必需依赖

| 依赖 | 用途 | 准备内容 |
| --- | --- | --- |
| 云服务器 | 运行 DeepTutor | 2 核 2 GB、40 GB SSD、Ubuntu 24.04、固定公网 IPv4 |
| Docker Engine | 运行生产镜像 | 使用 Docker 官方 Ubuntu APT 仓库安装 |
| Docker Compose plugin | 固化单容器配置和升级命令 | 与 Docker Engine 一同安装 |
| 域名 | HTTPS 和安全 Cookie | 例如 `learn.example.com` |
| DNS | 域名解析 | A 记录指向服务器公网 IPv4 |
| Caddy | HTTPS、证书自动续期、反向代理 | 安装在宿主机，不放进 DeepTutor 容器 |
| 生产镜像 | DeepTutor 程序 | 官方 GHCR 镜像或从当前代码构建的自有镜像 |
| LLM API | 聊天、出题、推理 | 阿里云百炼 API Key 和一个可用的 Qwen 模型 |
| Embedding API | 教材向量化和检索 | 阿里云百炼 API Key、`text-embedding-v4` |
| 异地备份位置 | 防止服务器或磁盘损坏 | OSS、另一台机器或加密对象存储 |

### 3.2 可选依赖

| 依赖 | 何时需要 | 说明 |
| --- | --- | --- |
| MinerU Cloud | 扫描 PDF、复杂公式、版面和表格解析 | 文档会上传到第三方服务，需单独评估隐私和费用 |
| 搜索 API | 使用联网搜索工具 | 不影响普通聊天和教材 RAG |
| 邮件服务 | 开放邮箱注册或通知 | 家庭私有部署不需要，建议由管理员创建账号 |
| 对象存储 | 教材和备份量显著增长 | 单机阶段不是前置依赖 |

### 3.3 网络访问清单

服务器入站规则：

| 端口 | 来源 | 用途 |
| --- | --- | --- |
| TCP 22 | 仅管理员固定 IP，或临时开放 | SSH 运维 |
| TCP 80 | `0.0.0.0/0`、`::/0` | Caddy ACME 校验和 HTTP 到 HTTPS 跳转 |
| TCP 443 | `0.0.0.0/0`、`::/0` | DeepTutor HTTPS |
| TCP 3782 | 不开放 | 只绑定宿主机 `127.0.0.1` |
| TCP 8001 | 不开放 | 只在容器内部使用 |
| TCP 8090 | 不开放 | 本方案不运行 PocketBase |

服务器至少需要允许出站 TCP 443，以访问：

- Docker APT 仓库和镜像仓库；
- `ghcr.io` 及其镜像下载域名；
- `dashscope.aliyuncs.com` 或百炼控制台给出的专属 API Host；
- ACME 证书机构；
- 可选的 `mineru.net`、搜索 API 或其他模型供应商。

## 4. 中国大陆地域、域名和备案

1. 中国内地服务器向公网提供网站服务时，需要先完成 ICP 备案。
2. 使用阿里云中国内地服务器时，应在阿里云备案系统办理；使用其他接入商时，
   应在实际接入商处办理。
3. 阿里云香港或海外节点不要求中国大陆 ICP 备案，但大陆访问延迟和网络稳定性
   可能不同。
4. 完成备案并上线后，还应根据适用要求办理公安联网备案，并在页面展示备案号。

参考：[阿里云 ICP 备案流程](https://help.aliyun.com/zh/icp-filing/basic-icp-service/user-guide/icp-filing-application-overview)。

域名添加 A 记录：

| DNS 字段 | 示例 |
| --- | --- |
| 类型 | `A` |
| 主机记录 | `learn` |
| 记录值 | 服务器公网 IPv4 |
| TTL | 600 秒 |

验证解析：

```bash
dig +short learn.example.com
```

返回值必须与服务器公网 IPv4 一致。参考：[阿里云添加 A 记录](https://help.aliyun.com/en/dns/pubz-add-parsing-record)。

## 5. 初始化服务器

以下命令假设使用具有 `sudo` 权限的 Ubuntu 用户。不要在尚未确认 SSH Key
可以登录前关闭密码登录，也不要删除云厂商默认管理用户。

### 5.1 更新系统和设置时区

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y ca-certificates curl gnupg dnsutils
sudo timedatectl set-timezone Asia/Shanghai
sudo reboot
```

重新连接服务器：

```bash
ssh <USER>@<SERVER_IP>
```

### 5.2 配置 2 GB Swap

2 GB 内存的服务器必须配置 Swap，避免教材解析瞬时内存增长直接触发 OOM：

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

如果 `/swapfile` 已存在，不要重复执行；先用 `swapon --show` 检查。

### 5.3 配置云防火墙和 UFW

先在阿里云轻量应用服务器防火墙中只保留 22、80、443。阿里云 Linux 轻量
服务器默认允许这些端口，但仍应检查实际规则。参考：[轻量应用服务器防火墙](https://help.aliyun.com/en/simple-application-server/user-guide/manage-the-firewall-of-a-server)。

宿主机可再启用 UFW：

```bash
sudo apt install -y ufw
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status verbose
```

Docker 发布的端口可能绕过部分 UFW 规则。因此本文仍把 3782 显式绑定到
`127.0.0.1`，并且完全不发布 8001；不能只依赖 UFW。参考：[Docker Ubuntu
安装文档中的防火墙说明](https://docs.docker.com/engine/install/ubuntu/)。

## 6. 安装 Docker Engine 与 Compose

使用 Docker 官方 APT 仓库，不使用仅面向测试环境的 `get.docker.com` 便利脚本。

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run --rm hello-world
sudo docker compose version
```

官方步骤：[Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)。

本文后续一直使用 `sudo docker`，不要求把运维用户加入 `docker` 组，因为
`docker` 组本质上拥有接近 root 的宿主机控制能力。

## 7. 安装 Caddy

Caddy 负责 HTTPS、证书自动签发和续期，并把公网请求转发给回环地址上的
DeepTutor 前端。

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
sudo chmod o+r /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

参考：[Caddy 官方安装文档](https://caddyserver.com/docs/install)。安装后服务会由
systemd 管理。证书签发要等 DNS 生效并且公网 80/443 可达。

## 8. 选择生产镜像

### 8.1 路线 A：未经修改的上游版本

使用上游发布镜像：

```text
ghcr.io/hkuds/deeptutor:<VERSION_OR_DIGEST>
```

首次验证可以临时使用 `latest`，确认版本后应固定版本标签或镜像 digest，避免
服务器重启时意外换到未经验证的新版本。

### 8.2 路线 B：当前定制项目，推荐

官方 GHCR 镜像不包含当前分支的本地修改。2 GB 服务器也不适合执行完整的
Next.js 和 Python 镜像构建，因此应在开发电脑或 CI 上构建，然后推送到 GHCR
或其他容器仓库。

开发电脑要求：

- Docker Desktop 或 Docker Engine + Buildx；
- 建议至少 8 GB 内存；
- 建议至少 15 GB 可用磁盘；
- 对目标容器仓库具有推送权限。

在当前仓库根目录执行，下面以 x86_64 服务器和 GHCR 为例：

```bash
docker login ghcr.io
docker buildx build \
  --platform linux/amd64 \
  --target production \
  -t ghcr.io/<GITHUB_USER>/deeptutor:<IMMUTABLE_TAG> \
  --push \
  .
```

建议把 `<IMMUTABLE_TAG>` 设置为 Git commit SHA 或明确版本号，不要只使用
`latest`。如果镜像为私有，服务器也需要登录：

```bash
sudo docker login ghcr.io -u <GITHUB_USER>
```

使用只具有 `read:packages` 权限的 token；不要把 token 写入 Compose 文件、Shell
历史或项目仓库。

## 9. 创建低成本单服务 Compose

仓库根目录的 [docker-compose.yml](../docker-compose.yml) 会额外启动 PocketBase
和内存上限 1 GB 的 sandbox runner，不适合 2 GB 最低配置。现有
[docker-compose.ghcr.yml](../docker-compose.ghcr.yml) 同时发布前后端端口，也不是
本文的公网最小暴露面。因此在服务器上单独创建一个只有 DeepTutor 的 Compose。

### 9.1 创建目录

```bash
sudo install -d -m 0750 -o "$USER" -g "$USER" /opt/deeptutor
sudo install -d -m 0750 -o 1000 -g 1000 /opt/deeptutor/data
cd /opt/deeptutor
```

容器内 DeepTutor 进程使用 UID/GID 1000 写入 `/app/data`，因此持久化目录必须
可由 1000:1000 写入。

### 9.2 创建 `/opt/deeptutor/compose.yml`

```yaml
name: deeptutor

services:
  deeptutor:
    image: ghcr.io/<OWNER>/deeptutor:<IMMUTABLE_TAG>
    container_name: deeptutor
    restart: unless-stopped
    ports:
      - "127.0.0.1:3782:3782"
    volumes:
      - ./data:/app/data
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    stop_grace_period: 30s
```

将 `image` 替换为第 8 节选择的真实镜像。不要添加 8001、8090 端口映射；不要
添加 `DEEPTUTOR_SANDBOX_RUNNER_URL`；不要把 API Key 写入该文件。

DeepTutor 的正式运行配置来自 `data/user/settings/*.json`。Compose 目录中的
`.env` 即便存在，也只是 Compose 自己的变量文件，不是 DeepTutor 配置来源。

### 9.3 校验并首次启动

```bash
cd /opt/deeptutor
sudo docker compose config
sudo docker compose pull
sudo docker compose up -d
sudo docker compose ps
sudo docker compose logs --tail=200 deeptutor
```

首次启动可能需要几十秒。确认前端和后端均启动后检查：

```bash
curl -fsS http://127.0.0.1:3782/ >/dev/null && echo 'frontend ok'
sudo docker exec deeptutor \
  curl -fsS http://127.0.0.1:8001/health
```

首次启动会在 `/opt/deeptutor/data/user/settings/` 创建默认配置文件。

## 10. 上线前配置 DeepTutor

此时 3782 只监听回环地址，公网尚不能访问。先停止应用并编辑配置：

```bash
cd /opt/deeptutor
sudo docker compose stop
sudo ls -la data/user/settings
```

### 10.1 `system.json`

编辑 `/opt/deeptutor/data/user/settings/system.json`：

```json
{
  "version": 1,
  "backend_port": 8001,
  "frontend_port": 3782,
  "next_public_api_base_external": "",
  "next_public_api_base": "",
  "cors_origin": "",
  "cors_origins": [
    "https://learn.example.com"
  ],
  "disable_ssl_verify": false,
  "chat_attachment_dir": "",
  "sandbox_allow_subprocess": false
}
```

必须替换域名。单容器模式下两个 API base 保持为空，Next.js 会使用容器内
`http://localhost:8001`。`disable_ssl_verify` 必须保持 `false`。

最低成本公网部署没有独立 sandbox runner，因此将
`sandbox_allow_subprocess=false`，避免模型生成的代码在主应用容器中执行。代价是
`exec`、`code_execution` 和依赖它们的 Office 文件生成能力不可用。如果以后确实
需要这些功能，应增加独立 sandbox runner 和更多内存，而不是重新打开公网主容器
中的子进程执行。

### 10.2 `auth.json`

编辑 `/opt/deeptutor/data/user/settings/auth.json`：

```json
{
  "version": 1,
  "enabled": true,
  "username": "admin",
  "password_hash": "",
  "token_expire_hours": 24,
  "cookie_secure": true,
  "public_registration_enabled": false,
  "registration_review_required": false,
  "require_terms_acceptance": true,
  "terms_version": "v1",
  "privacy_version": "v1",
  "csrf_protection_enabled": true,
  "max_users": 3
}
```

说明：

- `cookie_secure=true` 要求通过 HTTPS 访问；在纯 HTTP 下登录 Cookie 不会正常工作。
- `public_registration_enabled=false` 不会阻止第一个账号初始化。用户库为空时，
  `/register` 创建的第一个账号仍会成为管理员。
- 第一个管理员创建后，后续账号由管理员在 `/admin/users` 中创建。
- 家庭部署可把 `max_users` 设置为实际人数；`0` 表示不限制。
- 不要手工填写 `password_hash`，使用注册页面和管理员界面管理密码。

### 10.3 `integrations.json`

保持 PocketBase 关闭：

```json
{
  "version": 1,
  "pocketbase_url": "",
  "pocketbase_port": 8090,
  "pocketbase_external_url": "",
  "pocketbase_admin_email": "",
  "pocketbase_admin_password": ""
}
```

### 10.4 恢复权限并启动

```bash
sudo chown -R 1000:1000 /opt/deeptutor/data
cd /opt/deeptutor
sudo docker compose up -d
sudo docker compose logs --tail=100 deeptutor
```

## 11. 配置 HTTPS 反向代理

把 `learn.example.com` 替换为真实域名，编辑 `/etc/caddy/Caddyfile`：

```caddyfile
learn.example.com {
    encode zstd gzip
    reverse_proxy 127.0.0.1:3782
}
```

Caddy 的 `reverse_proxy` 原生支持 WebSocket 升级，不需要手工添加 Nginx 风格的
Upgrade 头。验证并重载：

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo systemctl status caddy --no-pager
sudo journalctl -u caddy -n 100 --no-pager
curl -I https://learn.example.com
```

Caddy 会自动申请、续期 TLS 证书并把 HTTP 重定向到 HTTPS。参考：
[Automatic HTTPS](https://caddyserver.com/docs/automatic-https) 和
[reverse_proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)。

如果证书签发失败，依次检查：DNS 是否已指向当前公网 IP、80/443 是否开放、域名
是否已备案并允许在当前中国内地节点接入、服务器时间是否准确。

## 12. 初始化管理员和家庭账号

1. 打开 `https://learn.example.com/register`。
2. 注册第一个邮箱账号；第一个账号会成为管理员。
3. 使用强密码并保存到密码管理器。
4. 登录后进入 `/admin/users`。
5. 为孩子创建普通用户账号，不要授予管理员角色。
6. 在授权页面只分配需要的模型、知识库、工具和额度。
7. 保持公开注册关闭。

如果首个管理员注册失败：

```bash
sudo docker compose -f /opt/deeptutor/compose.yml logs --tail=200 deeptutor
curl -fsS https://learn.example.com/api/v1/auth/is_first_user
```

不要通过直接修改 SQLite/JSON 文件来伪造管理员或密码哈希。

## 13. 配置阿里云百炼 LLM

### 13.1 创建 API Key

1. 在阿里云百炼控制台开通 Model Studio。
2. 选择与模型和 Endpoint 一致的地域/业务空间。
3. 创建单独用于 DeepTutor 的 API Key。
4. 创建后立即保存；新格式 Key 的明文可能只展示一次。
5. 建议把 API Key 的 IP 白名单限制为服务器公网 IPv4。
6. 建议把可访问模型范围限制为 DeepTutor 实际使用的模型。

参考：[阿里云百炼获取 API Key](https://help.aliyun.com/zh/model-studio/get-api-key)。

### 13.2 在 DeepTutor 中配置 LLM

管理员登录后进入 **设置 → 模型 → LLM**，新增配置：

| 字段 | 建议值 |
| --- | --- |
| Provider/Binding | `DashScope` |
| Base URL | `https://dashscope.aliyuncs.com/compatible-mode/v1`，或控制台给出的专属 API Host |
| API Key | 百炼 API Key |
| Model | 控制台中已开通且支持工具调用的 Qwen 模型 |

模型名称和价格可能变化，应以百炼控制台的当前模型列表为准。保存前点击连接测试，
测试成功后再设为 Active 并应用配置。阿里云支持 OpenAI-compatible 调用，参考：
[首次调用 Qwen](https://help.aliyun.com/en/model-studio/first-api-call-to-qwen)。

## 14. 配置阿里云 Embedding

进入 **设置 → 模型 → Embedding**，新增配置：

| 字段 | 建议值 |
| --- | --- |
| Provider/Binding | `OpenAI Compatible` |
| Endpoint | `https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings` |
| API Key | 百炼 API Key |
| Model | `text-embedding-v4` |
| Dimension | `1024` |
| Send dimensions | 关闭；若测试确认当前 Endpoint 支持也可开启 |

DeepTutor 当前 Embedding 适配器会把配置的 URL 当作完整 Endpoint 直接请求，因此
不要漏掉 `/embeddings`。点击连接测试，确认返回向量维度是 1024，然后保存、设为
Active 并应用。

阿里官方同步接口和定价见：[text embedding synchronous API](https://help.aliyun.com/en/model-studio/text-embedding-synchronous-api)。本部署继续使用实时同步
Embedding，不改为离线 Batch。

重要限制：Embedding 模型或维度变更后，已有知识库必须重新索引；不能把不同模型
或不同维度的旧向量与新向量混用。

API Key 最终保存在：

```text
/opt/deeptutor/data/user/settings/model_catalog.json
```

该文件和它的备份都属于敏感凭证，不能提交到 Git、发到聊天群或写入公开日志。

## 15. 教材与文档解析策略

2 GB 服务器应按教材类型选择解析方式：

| 教材类型 | 建议解析方式 | 资源与限制 |
| --- | --- | --- |
| 可复制文字的数字 PDF | `text_only` | 默认可用、占用最低，但版面和图片信息有限 |
| 数字 PDF，需要导出内嵌图形 | PyMuPDF4LLM | 轻量、无模型，但需要把可选依赖预装进自有镜像 |
| 扫描 PDF、复杂公式、表格和版面 | MinerU Cloud | 服务器负担低，但文档会上传到外部服务 |
| 本地 MinerU / Docling | 不建议 | 模型下载和峰值内存不适合 2 GB 机器 |

最低成本初次部署使用 `text_only`。如果人教版教材是扫描件，优先配置 MinerU
Cloud，而不是在 2 GB 服务器上下载本地解析模型。使用云解析前必须确认教材授权、
学生隐私、数据保留政策和服务费用。

数字版 PDF：管理员进入 **设置 → 知识库 → 文档解析**，选择 **Text-only**，保存
并应用。该模式不需要额外 API Key。

扫描版 PDF：管理员进入 **设置 → 知识库 → 文档解析 → MinerU**，配置：

| 字段 | 建议值 |
| --- | --- |
| Mode | `Cloud` |
| API Base URL | `https://mineru.net` |
| API Token | 从 MinerU API management 创建的 token |
| Language | `ch` 或先使用 `auto` |
| Formula | 开启 |
| Table | 按教材需要开启 |
| OCR | 扫描 PDF 开启；数字 PDF 通常关闭 |

先执行页面中的连接测试，再保存并应用。MinerU token 会写入
`data/user/settings/document_parsing.json`，同样必须作为敏感凭证保护。Cloud 模式
不需要在服务器安装 MinerU CLI，也不要开启本地模型下载。

导入建议：

1. 一次只导入一本教材。
2. 先用 10–20 页样本验证文字、公式和图片抽取质量。
3. 确认 Embedding 配置后再创建正式知识库。
4. 知识库使用默认 LlamaIndex/FAISS 路线。
5. 导入期间观察内存和磁盘；不要同时执行镜像升级或备份压缩。

## 16. 完整验收清单

### 16.1 服务检查

```bash
cd /opt/deeptutor
sudo docker compose ps
sudo docker compose logs --tail=200 deeptutor
sudo docker inspect --format '{{json .State.Health}}' deeptutor
curl -fsS http://127.0.0.1:3782/ >/dev/null
sudo docker exec deeptutor curl -fsS http://127.0.0.1:8001/health
curl -fsS https://learn.example.com/ >/dev/null
```

### 16.2 安全检查

```bash
sudo ss -lntp
sudo ufw status verbose
```

应满足：

- 公网只开放 22、80、443；
- `127.0.0.1:3782` 只在回环地址监听；
- 宿主机没有公开 `0.0.0.0:8001`、`0.0.0.0:8090`；
- 浏览器强制跳转到 HTTPS；
- 未登录用户被跳转到登录页；
- 普通用户看不到管理员 API Key 和其他用户数据；
- 公开注册关闭；
- `sandbox_allow_subprocess=false`；
- `disable_ssl_verify=false`。

### 16.3 功能检查

1. 管理员登录成功。
2. 创建普通家庭账号并登录成功。
3. LLM 连接测试成功并能回复一句普通问题。
4. Embedding 连接测试成功，返回维度正确。
5. 创建一个测试知识库并导入小型 PDF。
6. 在聊天中绑定该知识库并提出一个能从教材回答的问题。
7. 重启容器后账号、会话、配置和知识库仍然存在：

```bash
cd /opt/deeptutor
sudo docker compose restart
sudo docker compose ps
```

## 17. 备份

整个 `/opt/deeptutor/data` 都需要备份。它包含账号、密码哈希、JWT secret、API
Key、授权、审计、用量、会话、教材、附件、知识库和向量索引。

### 17.1 手工一致性备份

```bash
sudo install -d -m 0700 /var/backups/deeptutor
cd /opt/deeptutor
sudo docker compose stop
sudo tar --xattrs --acls -C /opt/deeptutor \
  -czf /var/backups/deeptutor/data-$(date -u +%Y%m%dT%H%M%SZ).tgz data
sudo docker compose start
sudo sha256sum /var/backups/deeptutor/data-*.tgz
```

随后把备份复制到另一台机器或加密对象存储。只留在同一块系统盘上的文件不算
灾备。备份含 API Key，远端必须加密并限制访问。

建议至少保留：最近 7 个日备份、4 个周备份；每月至少做一次恢复演练。家庭使用
可在低峰期停机几十秒换取一致性，避免边写入边压缩 SQLite/JSON 文件。

### 17.2 恢复

```bash
cd /opt/deeptutor
sudo docker compose stop
sudo mv data data.before-restore.$(date -u +%Y%m%dT%H%M%SZ)
sudo tar -xzf /var/backups/deeptutor/data-<TIMESTAMP>.tgz -C /opt/deeptutor
sudo chown -R 1000:1000 /opt/deeptutor/data
sudo docker compose up -d
sudo docker compose logs --tail=200 deeptutor
```

恢复时优先使用生成该备份时记录的同一镜像版本。恢复后验证管理员、普通用户、
模型配置、知识库和最近会话。

高级 PostgreSQL shared state 和多副本备份见
[SAAS_DEPLOYMENT_RUNBOOK.md](./SAAS_DEPLOYMENT_RUNBOOK.md)。

## 18. 升级与回滚

### 18.1 升级前

```bash
cd /opt/deeptutor
sudo docker inspect --format '{{.Config.Image}} {{.Image}}' deeptutor
sudo docker compose logs --tail=100 deeptutor
```

1. 记录当前镜像标签和 digest。
2. 按第 17 节备份 `data/`。
3. 阅读目标版本发布说明。
4. 若使用当前定制项目，在开发电脑/CI 构建新的不可变标签。

### 18.2 升级

修改 `/opt/deeptutor/compose.yml` 中的镜像标签，然后：

```bash
cd /opt/deeptutor
sudo docker compose config
sudo docker compose pull
sudo docker compose up -d
sudo docker compose ps
sudo docker compose logs --tail=200 deeptutor
```

完成第 16 节的服务和功能检查后再删除旧镜像。

### 18.3 回滚

1. 把 Compose 中的镜像恢复为旧标签或旧 digest。
2. 执行 `sudo docker compose up -d`。
3. 如果新版本修改了数据且旧版本无法读取，再按第 17 节恢复升级前备份。

不要执行 `docker system prune --volumes`，它可能删除仍有价值的卷。本文使用绑定
目录保存数据，但仍不应把破坏性清理作为常规升级步骤。

## 19. 运行监控和容量判断

常用检查：

```bash
sudo docker stats --no-stream
free -h
df -h / /opt/deeptutor
sudo du -sh /opt/deeptutor/data
sudo journalctl -k -g 'Out of memory\|Killed process' --since today
sudo journalctl -u caddy --since today --no-pager
```

建议在云监控中设置：

- CPU 连续 10 分钟超过 85%；
- 内存连续 10 分钟超过 85%；
- Swap 持续增长或频繁换入换出；
- 系统盘使用率超过 80%；
- 容器频繁重启；
- HTTPS 或首页健康检查失败。

出现以下任一情况时升级到 2 核 4 GB：

- 教材导入经常触发 Swap 或 OOM；
- 需要 5–10 名活跃用户；
- 需要更复杂的本地文档解析；
- 需要独立 sandbox runner；
- Node 和 Python 长期合计超过约 1.4 GB。

若需要本地模型、多人高并发或多副本，不应继续在本最低配置上堆组件，应重新做
容量规划。多副本至少需要 PostgreSQL shared state 和共享文件/对象存储。

## 20. 常见故障

### 20.1 域名返回 502

```bash
curl -v http://127.0.0.1:3782/
sudo docker compose -f /opt/deeptutor/compose.yml ps
sudo docker compose -f /opt/deeptutor/compose.yml logs --tail=200 deeptutor
```

回环地址不通说明 DeepTutor 未就绪；回环地址正常而域名 502，检查 Caddyfile 和
Caddy 日志。

### 20.2 页面正常但 LLM 没有响应

检查：

- LLM profile 是否 Active 并已 Apply；
- API Key 是否正确、是否欠费、IP 白名单是否包含服务器公网 IP；
- Base URL 与 API Key 地域/业务空间是否一致；
- 模型名称是否仍在百炼控制台可用；
- 服务器能否出站访问 443；
- 容器日志中是否有 401、403、429 或模型参数错误。

```bash
sudo docker compose -f /opt/deeptutor/compose.yml logs -f deeptutor
```

### 20.3 Embedding 返回 400 或维度错误

检查：

- Endpoint 必须以 `/compatible-mode/v1/embeddings` 结束；
- 模型名是 `text-embedding-v4`；
- 维度设置为 1024；
- 关闭 **Send dimensions** 后重新测试；
- 更换模型/维度后重建知识库。

### 20.4 HTTPS 下反复跳回登录页

检查：

- 必须访问 `https://` 而不是服务器 IP 或 `http://`；
- `auth.json` 中 `cookie_secure=true`；
- `system.json` 的 `cors_origins` 与浏览器地址完全一致，包括协议和端口；
- 修改 JSON 后是否重启了容器；
- 浏览器是否残留旧域名 Cookie。

### 20.5 数据目录 Permission denied

```bash
sudo chown -R 1000:1000 /opt/deeptutor/data
sudo chmod -R u+rwX /opt/deeptutor/data
sudo docker compose -f /opt/deeptutor/compose.yml restart
```

### 20.6 容器因内存不足退出

```bash
free -h
swapon --show
sudo journalctl -k -g 'Out of memory\|Killed process' --since today
sudo docker stats --no-stream
```

确认 Swap 已启用、没有运行本地 MinerU/Docling/模型、没有并行导入多本教材。
仍然 OOM 时升级到 4 GB，不要通过无限增加 Swap 掩盖持续内存不足。

### 20.7 重建容器后配置或教材丢失

检查 Compose 是否仍包含：

```yaml
volumes:
  - ./data:/app/data
```

并确认命令是在 `/opt/deeptutor` 目录执行。启动一个没有正确挂载 `/app/data` 的
新容器会生成一套空配置，看起来像数据丢失，但原目录可能仍在宿主机上。

### 20.8 `exec` 或 Office 文件生成不可用

这是最低成本公网配置中的预期行为，因为 `sandbox_allow_subprocess=false`。不要为
恢复这个功能直接打开主容器子进程执行；需要时增加仓库提供的隔离 sandbox runner
并把服务器升级到至少 4 GB。

## 21. 成本构成

固定成本：

- 2 核 2 GB 轻量应用服务器；
- 域名续费；
- 异地备份存储。

按量成本：

- Qwen LLM 输入/输出 token；
- `text-embedding-v4` 实时 Embedding；
- 可选 MinerU Cloud、搜索 API、语音或图片生成。

Docker Engine、Docker Compose、Caddy、SQLite 和 FAISS 不要求购买独立商业服务。
云服务器促销和续费价格经常变化，应以购买页为准，不应只看首年促销价。参考：
[阿里云轻量应用服务器计费说明](https://help.aliyun.com/zh/simple-application-server/product-overview/billing-faq)。

## 22. 最终上线检查表

- [ ] 服务器为 2 核 2 GB、40 GB SSD，已配置 2 GB Swap。
- [ ] DNS A 记录已指向服务器公网 IPv4。
- [ ] 中国内地节点已完成适用的 ICP/公安备案。
- [ ] 云防火墙和 UFW 只允许 22、80、443。
- [ ] SSH 22 尽可能限制到管理员 IP，使用 SSH Key。
- [ ] Docker 和 Compose 来自官方 APT 仓库。
- [ ] 使用 production 镜像，不在服务器运行 `next dev` 或现场构建镜像。
- [ ] 当前定制代码使用自有镜像，而不是误用上游 GHCR 镜像。
- [ ] Compose 只包含一个 DeepTutor 服务。
- [ ] 只映射 `127.0.0.1:3782:3782`，未发布 8001/8090。
- [ ] 完整挂载 `/opt/deeptutor/data:/app/data`。
- [ ] HTTPS 正常，Caddy 自动续期正常。
- [ ] `cookie_secure=true`，CORS 只允许真实 HTTPS 域名。
- [ ] 认证开启，首个管理员已创建，公开注册关闭。
- [ ] 普通家庭账号不是管理员。
- [ ] PocketBase 保持关闭。
- [ ] `sandbox_allow_subprocess=false`，`disable_ssl_verify=false`。
- [ ] 阿里百炼 API Key 已限制服务器 IP 和模型范围。
- [ ] LLM 和 Embedding 连接测试成功。
- [ ] 小型教材导入和 RAG 问答测试成功。
- [ ] 容器重启后数据仍存在。
- [ ] 已完成一次异地备份和恢复演练。
- [ ] 已记录当前镜像标签和 digest。

## 23. 项目内依据与官方资料

项目内关键依据：

- [Dockerfile](../Dockerfile)：production 镜像同时启动 FastAPI 和 Next.js standalone。
- [web/proxy.ts](../web/proxy.ts)：前端服务器代理 `/api/*` 与 `/ws/*`。
- [deeptutor/services/config/runtime_settings.py](../deeptutor/services/config/runtime_settings.py)：
  `system.json`、`auth.json`、`integrations.json` 的真实字段和默认值。
- [deeptutor/services/rag/pipelines/llamaindex/vector_store.py](../deeptutor/services/rag/pipelines/llamaindex/vector_store.py)：
  默认本地 FAISS/兼容 SimpleVectorStore 的持久化实现。
- [SAAS_DEPLOYMENT_RUNBOOK.md](./SAAS_DEPLOYMENT_RUNBOOK.md)：高级备份、多副本和
  PostgreSQL shared state 边界。

外部官方资料：

- [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [Caddy 安装](https://caddyserver.com/docs/install)
- [Caddy Automatic HTTPS](https://caddyserver.com/docs/automatic-https)
- [Caddy reverse_proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
- [阿里云轻量服务器防火墙](https://help.aliyun.com/en/simple-application-server/user-guide/manage-the-firewall-of-a-server)
- [阿里云 ICP 备案流程](https://help.aliyun.com/zh/icp-filing/basic-icp-service/user-guide/icp-filing-application-overview)
- [阿里云 DNS A 记录](https://help.aliyun.com/en/dns/pubz-add-parsing-record)
- [阿里云百炼获取 API Key](https://help.aliyun.com/zh/model-studio/get-api-key)
- [首次调用 Qwen](https://help.aliyun.com/en/model-studio/first-api-call-to-qwen)
- [阿里云文本 Embedding 同步接口](https://help.aliyun.com/en/model-studio/text-embedding-synchronous-api)
