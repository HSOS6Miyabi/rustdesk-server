# RustDesk 自托管服务端

本仓库在 [RustDesk Server](https://github.com/rustdesk/rustdesk-server) 与 [lejianwen/rustdesk-server](https://github.com/lejianwen/rustdesk-server) 的基础上持续维护，提供与 [本项目 RustDesk API](https://github.com/HSOS6Miyabi/rustdesk-api) 配合使用的服务器程序。

包含三个主要程序：`hbbs` 负责设备注册与连接协商，`hbbr` 负责中继，`rustdesk-utils` 提供辅助命令。

## 主要功能

- 支持官方 RustDesk 1.5.x 的共用协议、设备注册、TCP/UDP 连接及 WebSocket 中继。
- 支持 WebRTC 连接所需的 SDP 与 ICE 消息转发，WebRTC 无法建立连接时可以使用客户端原有的中继方式。信令处理设有限制消息长度、尝试次数及超时时间的保护措施。
- 保留 lejianwen 添加的 API 账户登录、JWT 验证及 `MUST_LOGIN` 设置。
- 支持加密 TCP 和通过 WebSocket 连接的客户端。
- 提供 Linux amd64、Linux arm64 程序压缩包，以及 amd64、arm64 Docker 镜像。
- 组合 Docker 镜像同时运行 API、`hbbs` 与 `hbbr`，由 s6-overlay 管理三个服务的运行。

## 下载地址

- [服务端 Releases](https://github.com/HSOS6Miyabi/rustdesk-server/releases)
- [API Releases](https://github.com/HSOS6Miyabi/rustdesk-api/releases)
- Docker 镜像：`ghcr.io/hsos6miyabi/rustdesk-server:latest`
- 仅使用 API 时的镜像：`ghcr.io/hsos6miyabi/rustdesk-api:latest`

开发分支和主分支提交会执行自动化测试。只有在里程碑完成后，从 `v*` 版本标签手动启动工作流并勾选 `milestone_release`，才会生成发行程序、组合镜像并更新 `latest` 标签。

## 使用组合 Docker 镜像

建议准备一个可供客户端访问的域名，例如 `desk.example.com`，并给 API 配置单独的 HTTPS 域名，例如 `api.example.com`。

在部署目录下创建 `data/server` 和 `data/api`，然后保存以下 `compose.yaml`：

```yaml
services:
  rustdesk:
    image: ghcr.io/hsos6miyabi/rustdesk-server:latest
    container_name: rustdesk-server
    ports:
      - "21114:21114"
      - "21115:21115"
      - "21116:21116"
      - "21116:21116/udp"
      - "21117:21117"
      - "21118:21118"
      - "21119:21119"
    environment:
      RELAY: desk.example.com:21117
      MUST_LOGIN: "N"
      ENCRYPTED_ONLY: "0"
      RUSTDESK_API_JWT_KEY: "请替换为长度足够的随机密钥"
      RUSTDESK_API_RUSTDESK_ID_SERVER: desk.example.com:21116
      RUSTDESK_API_RUSTDESK_RELAY_SERVER: desk.example.com:21117
      RUSTDESK_API_RUSTDESK_API_SERVER: https://api.example.com
    volumes:
      - ./data/server:/data
      - ./data/api:/app/data
    restart: unless-stopped
```

将域名与 JWT 密钥改成实际配置后运行：

```bash
docker compose up -d
docker compose logs -f rustdesk
```

API 默认使用 `21114/tcp`。为管理界面配置 HTTPS 反向代理后，访问 `https://api.example.com/_admin/` 登录。管理员初始密码会写入 API 首次启动日志，请在首次登录后修改密码。

`MUST_LOGIN=N` 时按 RustDesk 原有方式连接；设置为 `Y` 时，要求连接方先通过 API 登录，并使用 `RUSTDESK_API_JWT_KEY` 验证登录令牌。如果 API 与服务端分开部署，必须使用相同的 JWT 密钥。

`21118` 提供 ID 服务器的 WebSocket，`21119` 提供中继 WebSocket。使用 HTTPS 访问 WebClient v2 时，请将两个 WebSocket 入口通过反向代理配置为 WSS。详细配置见 [API 部署说明](https://github.com/HSOS6Miyabi/rustdesk-api/blob/master/docs/DEPLOYMENT.md)。

## 单独运行 hbbs 和 hbbr

从服务端 Releases 下载对应平台的压缩包并解压，或者在安装 Rust 工具链的环境中编译：

```bash
git clone --recurse-submodules https://github.com/HSOS6Miyabi/rustdesk-server.git
cd rustdesk-server
git checkout forapi
git submodule update --init --recursive
cargo build --release --locked
```

在两个终端中分别启动：

```bash
./target/release/hbbs -r desk.example.com:21117
./target/release/hbbr
```

初次启动会生成服务器身份密钥，请保管好并在重新部署时保留。需要限制账户登录时，为服务端配置 `RUSTDESK_API_JWT_KEY` 和 `MUST_LOGIN=Y`。

单独运行这两个程序不需要 API。需要账户管理、地址簿、联系人共享、连接审计和设备策略等功能时，请部署配套 API。

## RustDesk 1.5.x 与 WebRTC

本项目已升级 RustDesk 共用协议库，能够解析并转发 WebRTC 的 SDP Offer、SDP Answer 和 ICE 候选地址。WebRTC 会话由客户端协商建立，服务端仍可提供传统连接及中继。

在官方 RustDesk 1.5.x 客户端中，可以通过本地设置启用 `enable-webrtc=Y`。WebClient v2 有独立的 WebRTC 连接选项。需要使用能够建立 WebRTC 会话的双方客户端，以及允许必要 UDP 流量的网络。浏览器使用 HTTPS 或本机安全环境。

GitHub Actions 已启动实际的 RustDesk 服务进程，验证 TCP、WebSocket、UDP 连接，以及 WebRTC 的 SDP 和 ICE 候选地址转发。Rust 单元测试、跨架构编译和组合容器测试也已经通过。桌面画面、输入与长时间稳定连接还需要使用真实设备测试。

## 更新、维护和安全

服务器会持续检查 RustDesk 官方更新，并保留本项目需要的 JWT 登录、加密连接和 WebSocket 定制。修改后运行：

```bash
cargo test --locked
cargo build --release --locked
```

在包含 API 的组合镜像中，API 版本由 `docker/Dockerfile` 和发布工作流中的 `API_IMAGE_TAG` 决定。升级时先确认新 API 的 Release 与多架构 Docker 镜像发布成功，再更新该版本。

需要查看服务端的同步与测试说明，可阅读 [项目维护文档](docs/MAINTENANCE.md)。

### 相关项目

- [RustDesk 客户端](https://github.com/rustdesk/rustdesk)
- [RustDesk 官方服务器](https://github.com/rustdesk/rustdesk-server)
- [原 lejianwen 服务端](https://github.com/lejianwen/rustdesk-server)
- [本项目 RustDesk API](https://github.com/HSOS6Miyabi/rustdesk-api)

本仓库遵循源代码中的开源许可证，并保留上游项目的版权声明。
