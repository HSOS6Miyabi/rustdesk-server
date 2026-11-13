# RustDesk 自托管服务端

> **正式发行：** [Server v1.1.17-api.22](https://github.com/HSOS6Miyabi/rustdesk-server/releases/tag/v1.1.17-api.22) 和 [API v3.0.0-api.103](https://github.com/HSOS6Miyabi/rustdesk-api/releases/tag/v3.0.0-api.103)。组合 Docker 镜像：`ghcr.io/hsos6miyabi/rustdesk-server:v1.1.17-api.22`，内含 API v3.0.0-api.103。详细资料见[版本与维护说明](docs/HANDOFF_SNAPSHOT_2026-11-09.md)、[实施台账](docs/IMPLEMENTATION_LEDGER.md)和[22 项检查记录](https://github.com/HSOS6Miyabi/rustdesk-api/blob/master/docs/TASK_VERIFICATION_RECORD.md)。

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
- 服务端组合镜像（GHCR）：`ghcr.io/hsos6miyabi/rustdesk-server:latest`
- 服务端组合镜像（Docker Hub）：`kenvix/rustdesk-server:latest`
- 单独部署 API（GHCR）：`ghcr.io/hsos6miyabi/rustdesk-api:latest`
- 单独部署 API（Docker Hub）：`kenvix/rustdesk-api:latest`

正式版本通过自动化测试后，同时发布 GHCR 和 Docker Hub 镜像，均支持 Linux AMD64、ARM64，版本标签与 `latest` 标签保持一致。后续功能修改仍需通过自动化测试；维护者更新 `forapi` 分支中的 `.release-version` 后，发布工作流将创建版本标签并执行测试、编译和镜像发布。

可以从任一镜像仓库拉取相同版本的服务端组合镜像：

```bash
docker pull ghcr.io/hsos6miyabi/rustdesk-server:v1.1.17-api.22
docker pull kenvix/rustdesk-server:v1.1.17-api.22
docker pull kenvix/rustdesk-server:latest
```

## 使用组合 Docker 镜像

建议准备一个可供客户端访问的域名，例如 `desk.example.com`，并给 API 配置单独的 HTTPS 域名，例如 `api.example.com`。

在部署目录下创建 `data/server` 和 `data/api`，然后保存以下 `compose.yaml`：

```yaml
services:
  rustdesk:
    image: ${RUSTDESK_SERVER_IMAGE:-ghcr.io/hsos6miyabi/rustdesk-server:latest}
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

将域名与 JWT 密钥改成实际配置后运行。默认使用 GHCR 镜像；使用 Docker Hub 时，可以设置镜像地址，其他配置保持不变：

```bash
RUSTDESK_SERVER_IMAGE=kenvix/rustdesk-server:v1.1.17-api.22 docker compose up -d
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

## 多中继服务器

开发分支支持与 API 管理界面配合使用多台 hbbr 中继服务器。管理员可设置每个节点的 IP 网络偏好和优先级；hbbs 定期读取节点列表，检查连通性并选择合适的中继。节点断开后可以改选其他活动节点，动态配置清空时恢复原有中继地址。

只需单台中继时，可以继续使用 `hbbs -r relay.example.com:21117`。多中继的配置方法见 [环境变量说明](docs/environment-variables.md)；自动化测试和维护信息见 [开发实施台账](docs/IMPLEMENTATION_LEDGER.md)。

## GeoLite2 国家级中继选择

多中继管理可以使用 GeoLite2 Country MMDB 文件或 CSV 数据判断客户端 IP 所属国家，再按 Web 管理界面设置的国家代码选择中继。精确 CIDR 网络规则优先。未提供国家数据库时，保留现有中继选择方式。

GeoLite2 数据由部署者自行获取。配置环境变量 `RUSTDESK_GEOIP_MMDB_FILE` 指向 MMDB 文件，或使用 `RUSTDESK_GEOIP_CSV_DIR` 指向 CSV 目录。也可以同时配置两种格式，优先查询 MMDB，并用 CSV 补充未识别的地址。更新数据文件后可以在本地管理端口运行 `reload-geo`，无需重启 hbbs。

具体配置见 [环境变量说明](docs/environment-variables.md)。

## 远程控制角色

当前版本支持通过配套 API 为设备、用户或设备组指定远程控制角色。管理员可以管理键盘、剪贴板、文件传输、摄像头、远程终端、录制、USB 等 14 项权限。

设置 `RUSTDESK_API_CONTROL_ROLE_URL` 和 `RUSTDESK_API_INTERNAL_KEY` 后，hbbs 会在连接协商时把权限传给官方客户端。未配置控制角色时保留原有功能。详情见 [环境变量说明](docs/environment-variables.md) 和 [实施台账](docs/IMPLEMENTATION_LEDGER.md)。

## 可选的服务器连接访问规则

当前版本可以从配套 API 检查远程连接请求，允许管理员指定哪些用户和用户组可以访问哪些设备。启用后，新的普通连接和中继连接都需要通过账户登录和规则检查。默认不启用，普通服务器使用方式保持不变。详情见 [环境变量说明](docs/environment-variables.md)。
