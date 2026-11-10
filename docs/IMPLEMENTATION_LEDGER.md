# RustDesk Server 开发实施台账

> **正式发行：** [Server v1.1.17-api.21](https://github.com/HSOS6Miyabi/rustdesk-server/releases/tag/v1.1.17-api.21) 和 [API v3.0.0-api.103](https://github.com/HSOS6Miyabi/rustdesk-api/releases/tag/v3.0.0-api.103)。GitHub Actions 已通过 [Server 发行测试 #42690556784](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42690556784) 和 [API 发行测试 #42689275371](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42689275371)。详细资料见[版本与维护说明](HANDOFF_SNAPSHOT_2026-11-09.md)、[统一实施台账](https://github.com/HSOS6Miyabi/rustdesk-api/blob/master/docs/IMPLEMENTATION_LEDGER.md)与[22 项检查记录](https://github.com/HSOS6Miyabi/rustdesk-api/blob/master/docs/TASK_VERIFICATION_RECORD.md)。

本文件继续保留各项服务端功能的原始提交和测试记录，全部任务的当前状态、优先级与发布条件统一从上述总账查阅。

## 当前正式版本与安装信息

Server v1.1.17-api.21 和 API v3.0.0-api.103 已发布 GitHub Release。正式 Docker 镜像分别为 `ghcr.io/hsos6miyabi/rustdesk-server:v1.1.17-api.21` 和 `ghcr.io/hsos6miyabi/rustdesk-api:v3.0.0-api.103`，均支持 Linux AMD64 和 ARM64。Server 组合容器使用 API v3.0.0-api.103。

发行文件、容器内服务启动、JWT、WebRTC 信令与 API 联合通信已通过 GitHub Actions。真实终端的远程控制、跨地区公网中继、真实 SMTP 和正式业务数据库恢复仍需实际环境检查。具体状态见[22 项检查记录](https://github.com/HSOS6Miyabi/rustdesk-api/blob/master/docs/TASK_VERIFICATION_RECORD.md)。

## 2026-11-09：设备登记及连接协议兼容

开发分支：`development/m1-device-management`。

配套 API 的正式分支为 `master`；已合并变更见 Server [#4](https://github.com/HSOS6Miyabi/rustdesk-server/pull/4)和 API [#6](https://github.com/HSOS6Miyabi/rustdesk-api/pull/6)。

### 提交记录

| 提交 | 修改内容 |
| --- | --- |
| [b4e1fb6](https://github.com/HSOS6Miyabi/rustdesk-server/commit/b4e1fb6ec93c74196cd91461b710176c07f0a8cc) | 只有明确确认的里程碑发布工作流能够创建 Release 和发行镜像 |
| [33a6108](https://github.com/HSOS6Miyabi/rustdesk-server/commit/33a6108638d7cbc7bb240fd03768355a4bb6b105) | 在 `RegisterPk` 增加可选设备登记验证；`MUST_LOGIN=Y` 时验证 `RequestRelay` 令牌并要求有效 JWT 密钥 |

### 具体文件

- `src/device_deployment.rs`：根据 API 部署记录核准设备 ID、UUID、公钥，区分允许、未部署、ID 冲突和服务错误。
- `src/rendezvous_server.rs`：按环境设置调用登记验证，在连接协商中增加令牌检查。
- `src/lib.rs`：注册内部模块。

### 配置说明

| 环境变量 | 用途 | 默认值 |
| --- | --- | --- |
| `REQUIRE_DEVICE_DEPLOYMENT` | 是否强制预先登记设备 | 未启用 |
| `RUSTDESK_API_INTERNAL_KEY` | API 与 Server 的内部认证密钥 | 空 |
| `RUSTDESK_API_INTERNAL_URL` | 内部设备登记查询接口 | `http://127.0.0.1:21114/internal/v1/device/authorize` |
| `MUST_LOGIN` | 是否强制登录后连接 | 原有配置 |
| `RUSTDESK_API_JWT_KEY` | 连接方 JWT 验证密钥 | 原有配置 |

严格设备登记默认不启用；启用时必须同时配置 API、Server 和相同的内部访问密钥。

### 测试安排

Rust 单元测试、程序编译和 TCP/UDP/WebSocket 实际服务检查已经由 GitHub Actions 执行。跨项目的设备 `--deploy` 和 `--assign` 需结合 API 测试，详细说明见 [HANDOFF.md](HANDOFF.md)。

发布条件：两个仓库完成相同里程碑后，在 `v*` 标签上手动执行工作流，勾选 `milestone_release`。日常提交不创建 Release。

### 后续功能与测试记录

| 提交 | 修改内容与验证 |
| --- | --- |
| [8995074](https://github.com/HSOS6Miyabi/rustdesk-server/commit/89950741e6c156d6ed7cb24c348a97441f3c0ce0) | 更新维护与接手文档 |
| [cd67739](https://github.com/HSOS6Miyabi/rustdesk-server/commit/cd6773901134fd38ca566af73de906e014257637) | 增加实际运行 `hbbs` 的严格设备登记测试 |
| [ec48c9b](https://github.com/HSOS6Miyabi/rustdesk-server/commit/ec48c9bb5414d93d9b486cc158cbc42216fb8199) | 严格登记模式下，设备恢复连接时再次检查登记状态 |
| [bfd1d8e](https://github.com/HSOS6Miyabi/rustdesk-server/commit/bfd1d8e2ca3f7d513e7686f42ead026826606b95) | 仅在 API 也启用严格登记时接受登记许可 |

对应的服务端 CI：[Rust 测试、程序编译及实际服务通信检查](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42519807127)，已通过。

实际运行测试由 `scripts/test_device_deployment.py` 执行，创建本地测试 API，启动真实 `hbbs` 进程，并验证以下情况：

- 尚未登记的设备收到 `NOT_DEPLOYED`。
- 获得许可的设备可以完成 `RegisterPk`。
- ID 冲突的设备被拒绝。
- 已登记设备撤销许可后，再次注册被拒绝。
- API 返回的 UUID 与公钥在传输过程中保持一致。

该测试使用真实服务进程与模拟 API。完整的实际桌面连接和 `rustdesk --deploy` 操作需要结合配套 API 与 RustDesk 客户端测试。

## 2026-11-09：多中继服务器动态选择

在配套 API 的“中继节点管理”页面维护中继地址、优先级和优先使用的 IP 网络范围。hbbs 可以定期读取管理界面保存的节点配置，检查节点是否可连接，并根据两个客户端的 IP 网络选择合适的中继。

### 修改记录

| 提交 | 内容 |
| --- | --- |
| [6183fb1](https://github.com/HSOS6Miyabi/rustdesk-server/commit/6183fb15f9969fc64cd2868d2ed48a6fb4306c15) | 解析 API 中继列表、CIDR 网络匹配、优先级与 IPv4/IPv6 选择 |
| [cf3b616](https://github.com/HSOS6Miyabi/rustdesk-server/commit/cf3b6162831416e4af2ed2086f3e117f5c9b5d54) | hbbs 定期同步 API 节点列表，更新现有中继服务器管理 |
| [1a82c2c](https://github.com/HSOS6Miyabi/rustdesk-server/commit/1a82c2c3668ae4c8057466f25cbd853246f68a41) | 启动真实 hbbs、临时 API、模拟中继服务器，测试同步与原有设置恢复 |
| [1dd7c0e](https://github.com/HSOS6Miyabi/rustdesk-server/commit/1dd7c0e85c10bf71f2bcfe86eebead8e09d4c495) | 在线检查发现节点不可用后改选其他中继，保留原有备用地址 |

### 配套 API

- API 开发分支：`development/m1-device-management`。
- API 对应提交：[fc6d7ba](https://github.com/HSOS6Miyabi/rustdesk-api/commit/fc6d7ba1c0b87e304940b0e38197814cb16512a3)。
- API PR：[rustdesk-api #6](https://github.com/HSOS6Miyabi/rustdesk-api/pull/6)。
- Server PR：[rustdesk-server #4](https://github.com/HSOS6Miyabi/rustdesk-server/pull/4)。

API 在数据库的 `relay_nodes` 表保存配置，通过 `GET /internal/v1/relay/nodes` 向 hbbs 返回已启用的节点。请求使用 `X-RustDesk-Internal-Key` 验证。接口需要 API 和 Server 使用相同的内部通信密钥。

### 环境配置

```bash
export RUSTDESK_API_RELAY_NODES_URL="http://127.0.0.1:21114/internal/v1/relay/nodes"
export RUSTDESK_API_INTERNAL_KEY="与 API 相同的内部通信密钥"
export RUSTDESK_API_RELAY_SYNC_SECONDS=30
```

- `RUSTDESK_API_RELAY_NODES_URL` 留空时，继续使用 `hbbs -r` 或 `relay-servers` 配置。
- `RUSTDESK_API_RELAY_SYNC_SECONDS` 默认 30 秒，可设置 10 至 3600 秒。
- API 返回空节点列表时，恢复启动时指定的原有中继地址。
- 连接双方的 IP 均处于某节点配置的网络范围时，优先选择该节点；如果只匹配一方，则其次选择。相同匹配程度使用较小的优先级数字；无匹配时在可用节点之间轮流选择。
- 继续使用原来的 TCP 连通性检查。没有有效中继时，尝试原有中继地址。

### 已通过的测试

- [Rust 单元测试与编译](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42564566978)。
- [多中继功能与真实 hbbs 测试](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42564891450)。
- [中继不可达时的替代选择测试](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42565263648)。

以上工作流均完成且通过，没有创建 Release。后续可进一步增加 GeoLite2 地理位置数据库支持，让管理员无须手动填写地区 IP 网络范围。

## 2026-11-09：GeoLite2 Country CSV 自动识别客户端国家

GeoLite2 国家级数据库为中继选择增加了可选的地理位置规则。管理员在 API 中为中继节点填写两位国家代码。hbbs 从本地 GeoLite2 Country CSV 文件读取 IP 网络和国家对应关系，根据连接双方的 IP 地址选择符合国家偏好的中继。

| 提交 | 修改内容 |
| --- | --- |
| [fc0b3ce](https://github.com/HSOS6Miyabi/rustdesk-server/commit/fc0b3ce3831981c47984f10120b1abe70aa7196f) | 读取 GeoLite2 Country Locations-en 与 IPv4、IPv6 Blocks CSV 文件，解析国家代码 |
| [f3b67c0](https://github.com/HSOS6Miyabi/rustdesk-server/commit/f3b67c0aac07007f7eaf13ae3a28b626968946e6) | 国家代码与精确 CIDR 规则的综合选择，支持 IPv4 和 IPv6 |
| [ab61a6f](https://github.com/HSOS6Miyabi/rustdesk-server/commit/ab61a6f9f7ef574cdd48930ffaf2865dd14aa26d) | 启动时加载国家数据，本地控制命令 `reload-geo` 重新读取文件 |
| [9429bda](https://github.com/HSOS6Miyabi/rustdesk-server/commit/9429bda97a5c07b8b2539fc413512f4109928bef) | 实际进程检查国家匹配、数据重新载入与中继断开后的替代选择 |

### 配套 API

- API 通过 `relay_nodes.countries` 保存国家代码，查询接口在原有 `subnets` 外增加 `countries` 数组。
- 关联 API 功能提交：[e986914](https://github.com/HSOS6Miyabi/rustdesk-api/commit/e986914be9379d5d36d7c77eb5f4532898fc7a1a)。
- 数据库迁移版本 277：[ec007b5](https://github.com/HSOS6Miyabi/rustdesk-api/commit/ec007b5030664a01f2e0962d05dcaae9333080d4)。
- 对应 API 文档提交：[14aaf18](https://github.com/HSOS6Miyabi/rustdesk-api/commit/14aaf18c161f36219fe664880ef42a9d982afb6b)。

### 配置

从 [MaxMind 官方文档](https://dev.maxmind.com/geoip/docs/databases/city-and-country/)获取 GeoLite2 Country CSV，解压后将三个文件置于 hbbs 能读取的同一目录：

- `GeoLite2-Country-Locations-en.csv`：GeoNames ID 与 ISO 国家代码。
- `GeoLite2-Country-Blocks-IPv4.csv`：IPv4 网络与 GeoNames ID。
- `GeoLite2-Country-Blocks-IPv6.csv`：IPv6 网络与 GeoNames ID。

设置 `RUSTDESK_GEOIP_CSV_DIR` 指向该目录。未设置此变量时，原有 IP 网络和中继轮流选择方式继续有效。更新 Country CSV 文件后，在 hbbs 本地控制端口发送 `reload-geo` 重新读取数据。

本功能不随程序分发 GeoLite2 数据文件。使用者自行取得并按 MaxMind 授权要求更新数据库。

### 测试

- [GeoLite2 CSV 解析和国家级匹配](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42567365799)，通过。
- [实际 hbbs 的国家级中继选择、配置刷新与节点替代测试](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42567610418)，通过。
- [API 国家代码管理和内部配置接口](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42567027724)，通过。

具体执行命令与测试内容见 [TESTING.md](TESTING.md)。

## 2026-11-09：远程控制角色与官方客户端会话权限

本阶段继续面向小型团队增加可选的控制角色。管理员可在 API 网页创建角色，逐项设置 RustDesk 官方协议支持的 14 种权限，按设备、设备所有者、设备组分配。默认未分配角色的设备继续采用原有客户端设置。

### Server 修改

| 提交 | 变更 |
| --- | --- |
| [85bdbab](https://github.com/HSOS6Miyabi/rustdesk-server/commit/85bdbab7e14e852115787085b095bb143afa6bbd) | 查询 API 控制角色权限，验证 14 项状态编码，短暂缓存查询结果 |
| [c97ba9d](https://github.com/HSOS6Miyabi/rustdesk-server/commit/c97ba9de6144eee27e45e8d37d5b3c7c0a98ca94) | 在连接协商的 `PunchHole`、`FetchLocalAddr`、`RequestRelay` 中携带控制权限 |
| [ee9ff73](https://github.com/HSOS6Miyabi/rustdesk-server/commit/ee9ff73be768677f24ee883e33bca59cfe21c48d) | 运行真实 hbbs，验证普通连接、局域网连接、中继连接的权限消息 |

### 配套 API

- 开发分支：`HSOS6Miyabi/rustdesk-api:development/m1-device-management`。
- 功能与文档提交：[e850b81](https://github.com/HSOS6Miyabi/rustdesk-api/commit/e850b81dce8f39468cf43cb5d1adb81d79bf65dc)。
- API 数据库迁移版本：278，增加 `control_roles` 和 `control_role_assignments`。
- API PR：[rustdesk-api #6](https://github.com/HSOS6Miyabi/rustdesk-api/pull/6)。

API 内部接口 `GET /internal/v1/control/permissions?device_id=...` 返回对应设备生效的 `assigned`、`permissions` 和 `source`。Server 使用 `X-RustDesk-Internal-Key` 请求头读取。权限位编码由官方 `ControlPermissions` 定义，每项使用两个二进制位，值 `0` 代表沿用设备自身设置，`1` 代表禁止，`2` 代表允许。

### 环境配置

```bash
export RUSTDESK_API_CONTROL_ROLE_URL="http://127.0.0.1:21114/internal/v1/control/permissions"
export RUSTDESK_API_INTERNAL_KEY="与 API 使用相同的内部通信密钥"
export RUSTDESK_API_CONTROL_CACHE_SECONDS=5
```

`RUSTDESK_API_CONTROL_ROLE_URL` 不设置时，保持现有会话行为。缓存默认 5 秒，允许设置为 0 至 60 秒。角色在管理界面修改后，后续连接请求将读取新的权限。

### 自动化测试

- [Server Rust 编译与单元测试](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42569499247)：通过。
- [Server 实际进程协议转发测试](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42569942719)：通过。
- [配套 API Go 与 Chromium 浏览器测试](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42570243157)：通过。

Protobuf 控制权限编码已通过测试。Windows、macOS、Linux 和移动设备的实际远程控制仍需检查。两个仓库均已正式发布。

## 2026-11-09：可选的服务器连接访问规则

本功能与 API 的“连接访问规则”配合。管理员可以为某个已登录用户、用户组、设备或设备组配置远程访问许可。只有在配置 `RUSTDESK_API_CONNECTION_ACCESS_URL` 后，hbbs 才会对普通连接及中继请求执行授权检查。

### 代码提交

| 提交 | 修改内容 |
| --- | --- |
| [8aff47f](https://github.com/HSOS6Miyabi/rustdesk-server/commit/8aff47fbf25227078821ff2058cdf161b30368a1) | 增加按设备和登录令牌查询 API 授权的模块 |
| [3ceef25](https://github.com/HSOS6Miyabi/rustdesk-server/commit/3ceef2570694ca8d2e78467d0147b375a3647dab) | 对 `PunchHoleRequest`、`RequestRelay` 进行可选授权检查 |
| [0fa1e56](https://github.com/HSOS6Miyabi/rustdesk-server/commit/0fa1e56e873f000bf13e88b9a31dfaab37c17a50) | 真实 hbbs 进程、模拟内部 API 和普通/中继连接测试 |
| [4ba02a9](https://github.com/HSOS6Miyabi/rustdesk-server/commit/4ba02a96a0b4eca0aab7bd77ed5c4bafe6d2d0b7) | 使用官方协议消息检查被拒绝的连接及完整运行测试 |

### 配套 API

- API PR：[rustdesk-api #6](https://github.com/HSOS6Miyabi/rustdesk-api/pull/6)。
- API 授权规则接口与模型：[146ab63](https://github.com/HSOS6Miyabi/rustdesk-api/commit/146ab634d546185ad6e1ee91343c2188ce1bddee)。
- API 数据库迁移：280，新增 `access_rules`。
- API 内部接口：`POST /internal/v1/connection/authorize`。
- API 代码及运行记录可在 [API 实施台账](https://github.com/HSOS6Miyabi/rustdesk-api/blob/master/docs/IMPLEMENTATION_LEDGER.md) 查看。

### 配置和工作方式

默认未启用严格连接许可；普通部署仍按原有方式协商远程连接。启用时设置：

```bash
export RUSTDESK_API_CONNECTION_ACCESS_URL="http://127.0.0.1:21114/internal/v1/connection/authorize"
export RUSTDESK_API_INTERNAL_KEY="与 API 相同的内部通信密钥"
```

启用后，新的普通连接和中继请求通过客户端账户令牌验证，并按 API 中的规则判断。目标设备须在 API 中登记。设备所有者可访问自己的设备，其他账户需要与至少一条允许规则匹配；匹配禁止规则时拒绝访问。

API 无法访问、令牌失效或连接不符合规则时，严格模式会拒绝新的连接。此功能影响 hbbs 协商的连接，不改变客户端直连设备 IP 的处理方式。

### 测试

- [Server Rust 编译及严格模式协议测试](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42578682536)：通过。
- [API 规则验证和 SQLite 测试](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42577911849)：通过。
- [API 管理控制台浏览器测试](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42578812266)：通过。

真实客户端的多平台登录、直接连接与严格模式兼容性仍需在里程碑发布前检查。


## 2026-11-09：组合容器构建与 GeoLite2 MMDB 数据读取

### 双架构部署预演

新增 `.github/workflows/milestone-preflight.yml`，在 Linux AMD64 和 ARM64 运行器上获取两个开发仓库代码，构建配套 API、RustDesk Server 与组合容器镜像，并通过 `scripts/test_container_image.py` 实际启动容器检查 API、hbbs、hbbr、WebSocket 和管理页面。组合镜像不推送到正式仓库。

- [组合容器预演 CI 42585097640](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42585097640)：两个架构均通过。
- 与配套 API 的设备登记、自动化管理、角色和批量功能使用相同开发分支。正式部署时仍需进行真实设备及网络环境测试。

### GeoLite2 Country MMDB 与 CSV

| 位置 | 内容 |
| --- | --- |
| `Cargo.toml` | 增加 `maxminddb` 读取依赖 |
| `src/geoip_country.rs` | 支持 MMDB Country 读取和 IPv4/IPv6 国家识别，同时保留原有 CSV 查询 |
| `src/rendezvous_server.rs` | 启动和 `reload-geo` 时加载两类文件；刷新失败时保留已有有效数据 |
| `tests/fixtures/GeoLite2-Country-Test.mmdb` | MaxMind 公开的示例国家数据库及来源说明，供自动测试使用 |
| `docs/environment-variables.md` | 记录 MMDB 和 CSV 的使用方法及 `reload-geo` 操作 |

使用 `RUSTDESK_GEOIP_MMDB_FILE` 指向单个数据库文件，也可以继续使用 `RUSTDESK_GEOIP_CSV_DIR` 指向原有 CSV 目录。两项同时配置时，先查询 MMDB，未取得国家代码时再查 CSV。未设置时沿用已有的中继选择方式。

- [Server Rust 单元测试、真实服务和协议检查 42588361437](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42588361437)：通过。
- 示例数据库来自 [MaxMind-DB 公开测试数据](https://github.com/maxmind/MaxMind-DB)，与商业或正式 GeoLite2 分发数据分开存放。
- 正式数据库由实际部署者自行获取。多地区公网的连接质量仍需在发布前验证。

本阶段源代码已合并到两个仓库的主分支，正式发行完成。后续代码修改按常规方式测试，新版本另行申请发行批准。


## 2026-11-09：普通服务器部署与 Docker 重启测试

Server 与 API 的开发分支已完成两种部署方式的自动化运行检查，检查项目包括程序启动、通信端口、WebClient 页面、数据库保持和服务器密钥保持。

| 部署方式 | 运行方式及检查内容 | 运行结果 |
| --- | --- | --- |
| 普通服务器进程 | 在临时目录运行配套 API、`hbbs`、`hbbr`；检查 TCP、UDP、WebSocket、管理页面、WebClient；重新启动后复查账户、数据库版本和服务端公钥 | [双架构组合检查 #42618003889](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42618003889)，成功 |
| Docker | 在 AMD64、ARM64 上分别创建组合镜像和容器；挂载 API、Server 两个独立数据卷，删除容器并重新创建，检查上述关键数据保持一致 | [双架构组合检查 #42618003889](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42618003889)，成功 |
| RustDesk Server 单独运行 | 编译并检查 `hbbs`、`hbbr`，以及 TCP、UDP、WebSocket 和相关协议 | [Rust 测试 #42618004098](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42618004098)，成功 |

相关文件为 `scripts/test_native_stack.py`、`scripts/test_persistent_container.py`、`scripts/test_container_image.py` 和 `.github/workflows/milestone-preflight.yml`。测试所用的 API 由同一工作流读取配套开发分支进行编译。镜像仅保存在临时运行环境中，测试结束后清理容器和测试数据卷。

正式环境仍需检查公网连接、系统服务自动启动、备份恢复、客户端登录及远程控制。本阶段的正式版本已获得维护者批准。


## 2026-11-09：与配套 API 版本 282 的兼容性检查

配套 API 当前开发分支的数据库迁移版本为 282，已支持六种桌面系统与架构的官方安装文件、邮件事件通知及数据库备份恢复检查。

Server 的 `.github/workflows/milestone-preflight.yml` 在运行时从配套 API 的 `development/m1-device-management` 获取代码，并在 AMD64、ARM64 上编译两个项目及启动组合容器。此工作流包含普通进程与 Docker 两种部署方式的服务检查，以及重启后 API 数据和 RustDesk 服务端公钥的保持检查。API 数据库备份与恢复说明可通过 [统一实施台账](https://github.com/HSOS6Miyabi/rustdesk-api/blob/master/docs/IMPLEMENTATION_LEDGER.md) 查阅。

以上自动化测试已在 GitHub Actions 临时环境运行。多平台远程控制、真实 SMTP、跨地区中继及业务数据库恢复仍需在实际环境中检查。


## 2026-11-09：实际 API、hbbs 的设备登记与严格访问许可

在 `scripts/test_real_api_registration.py` 中同时启动实际 API 和 `hbbs`，使用独立数据库验证设备登记、内部认证密钥、设备标识与公钥冲突、重复部署、撤销和恢复许可，以及 API 停止运行后的设备登记行为。

在 `scripts/test_real_api_strict_combination.py` 中同时启用 `MUST_LOGIN=Y`、`REQUIRE_DEVICE_DEPLOYMENT=Y`、JWT、实际 API 连接许可和控制角色。使用临时账户和数据库检查设备所有者访问、其他账户的允许及禁止规则、无效 JWT 签名、失效登录会话、WebSocket 连接协商、中继请求与控制权限，以及 API 中断时的连接拒绝。测试密钥在每次运行时独立生成。

| 项目 | 验证结果 |
| --- | --- |
| API 配套功能提交 | [dc0a9983](https://github.com/HSOS6Miyabi/rustdesk-api/commit/dc0a998369d0d1cee8d9daba7a837b9a2ba966f0) |
| Server 实现及测试提交 | [eb4b586f](https://github.com/HSOS6Miyabi/rustdesk-server/commit/eb4b586f9c65a1060dea8ce56b4809dec746c788) |
| Rust 编译、单元测试及实际通信 | [GitHub Actions #42647450900](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42647450900)：成功 |
| AMD64 与 ARM64 的联合授权、容器启动、重启和数据保持 | [GitHub Actions #42647450607](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42647450607)：成功 |
| 官方 Linux 1.5.1 与实际 API 部署及直接分配 | [API #42646358750](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42646358750)：成功 |

相关流程位于 `.github/workflows/milestone-preflight.yml`；执行命令见 [Server 测试说明](TESTING.md)。实际双终端远程会话、公网与跨地区中继、正式 GeoLite2 数据及主机部署仍按统一 T001–T022 清单执行。发布工作流保持人工明确批准的要求。


## 2026-11-10：设备转移后的登录会话管理

配套 API 的 `--assign` 与管理页面设备所有者转移均使用同一设备会话撤销方法。设备所属账户、部署许可和原设备登录会话随所有者变更进行更新；其他设备的有效会话继续保留。

| 位置 | 说明 |
| --- | --- |
| 配套 API 代码 | [e898985f](https://github.com/HSOS6Miyabi/rustdesk-api/commit/e898985f8b2242e0a4f5e28c1eed2a6ced17b37e) |
| Go 与浏览器测试 | [API #42652681801](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42652681801)：成功 |
| 官方 Linux 客户端与实际 API | [API #42652682083](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42652682083)：成功 |
| SQLite、MySQL、PostgreSQL | [API #42652681804](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42652681804)：成功 |

Server 的联合测试通过 `.github/workflows/milestone-preflight.yml` 检查设备登记、JWT、访问许可、控制角色及容器数据保存；正式版本已经发布。


## 2026-11-10：当前配套 API 与 Server 双架构验证

使用 API 提交 [5b96e930](https://github.com/HSOS6Miyabi/rustdesk-api/commit/5b96e93055c8a5b7b9779e74bcc46adeb1dc1305) 和 Server 开发分支进行组合检查。对应 API 代码已包含设备所有者转移与会话撤销功能，数据库迁移版本维持 282。

| 验证项目 | GitHub Actions 结果 |
| --- | --- |
| Server Rust 编译、单元和协议测试 | [#42666030849](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42666030849)：成功 |
| AMD64 与 ARM64 的实际 API、hbbs、hbbr、Docker、设备权限及数据保存 | [#42666031144](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42666031144)：成功 |
| API Go 综合、管理页面和 WebClient | [#42653315805](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42653315805)：成功 |
| API 官方 Linux 客户端部署与分配 | [#42653315702](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42653315702)：成功 |
| API SQLite、MySQL、PostgreSQL 数据库检查 | [#42653315887](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42653315887)：成功 |

正式发行的 API 源代码提交为 `a6d338821cfba2daffa34f9cc3b06605ea1edf03`，Server 源代码提交为 `2d0896ecea4cf147f6fb4d2cdadf3278ab390851`。对应版本分别为 API v3.0.0-api.103 和 Server v1.1.17-api.21。


## 2026-11-10：配套 API 严格登记心跳与许可检查

API 代码提交 [3d5f4db1](https://github.com/HSOS6Miyabi/rustdesk-api/commit/3d5f4db168d6182ffcca103eb5bfa37388920df3) 为设备心跳增加部署许可核查。严格登记模式中，设备的登记记录、身份与许可状态需要同时有效，才能收到策略或会话管理指令。已撤销许可的设备得到空响应。

代码：API `http/controller/api/index.go`；测试：`http/controller/api/device_policy_heartbeat_test.go`。

- [API Go 与浏览器综合测试 #42655936250](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42655936250)：成功。
- [官方 Linux 客户端与实际 API #42655936037](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42655936037)：成功。
- [数据库迁移及恢复 #42655936179](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42655936179)：成功。

Server 的 `.github/workflows/milestone-preflight.yml` 将配套 API 的 Go 检查与实际 API、`hbbs` 联合测试一起执行，持续核对两个开发分支的兼容情况。真实两终端远程控制仍在 T001、T003、T004、T014 的实际设备测试范围内。


## 2026-11-10：实际登录、会话撤销与 WebRTC 联合测试

Server 的 `scripts/test_real_api_strict_combination.py` 在临时环境中运行实际 API、数据库和 `hbbs`，通过 API 的登录接口取得签名 JWT，然后测试账户访问许可、控制权限、WebRTC SDP 应答与 ICE 信息转发、设备撤销以及 API 服务中断时的拒绝行为。退出登录后，测试再次登录同一账户，检查新旧 JWT 不同，并确认旧令牌依旧无法建立连接。

对应 API 已为每次签发的 JWT 生成独立随机标识，保留既有签名算法及客户端使用方式。测试使用独立生成的账户凭据和临时服务器密钥。

| 检查范围 | 已完成的检查 |
| --- | --- |
| 实际 API 登录、JWT 唯一性、Go 与浏览器检查 | [API #42666929269](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42666929269)：成功 |
| Server Rust 单元与协议检查 | [Server #42666030849](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42666030849)：成功 |
| AMD64 和 ARM64 的实际 API、`hbbs`、WebRTC 与组合容器运行 | [Server #42666031144](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42666031144)：成功 |
| Windows、Linux、macOS 与 Android 模拟器客户端启动 | [API #42666929318](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42666929318)：成功 |

真实多终端的远程操作、账户双重认证、跨地区公网中继、外部 SMTP、生产业务数据恢复，以及目标服务器部署仍按 [T001–T022 逐项任务记录](https://github.com/HSOS6Miyabi/rustdesk-api/blob/master/docs/TASK_VERIFICATION_RECORD.md) 检查。本阶段的两个 PR 已合并，正式版本已发布。


## 2026-11-10：撤销设备许可后的连接拒绝

Server 的实际 API 联合测试已增加许可撤销后的连接检查。在严格设备登记与集中连接授权同时启用的情况下，设备撤销许可后，`hbbs` 拒绝向该设备转发新的连接协商与中继请求。配套 API 查询设备批准状态、UUID 和所属账户，设备身份不一致时拒绝连接请求。

- [API Go 综合检查 #42670400984](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42670400984)：通过。
- [Server Rust 综合检查 #42669744309](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42669744309)：通过。
- [AMD64、ARM64 联合部署和撤销后连接检查 #42669744598](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42669744598)：通过。

这些自动化测试使用临时账户和本地服务器进程。实际客户端、正式公网中继及生产环境检查仍按 T001–T022 逐项记录执行，未完成的正式环境项目继续保留待检查状态。
