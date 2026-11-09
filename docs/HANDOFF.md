# RustDesk Server 接手说明

> **统一交接入口：[两仓库完整实施台账与任务清单](https://github.com/HSOS6Miyabi/rustdesk-api/blob/development/m1-device-management/docs/IMPLEMENTATION_LEDGER.md)。** 其中记录了当前 API 与 Server 的兼容提交、各模块状态、22 项待办事项及 P0 发布前检查。本文保存服务端模块和测试的详细说明。

本项目与 [配套 API](https://github.com/HSOS6Miyabi/rustdesk-api) 共同维护，主要面向小型团队的 OSS 自托管需求。

## 正在开发

- Server 分支 `development/m1-device-management`，草稿 PR [#4](https://github.com/HSOS6Miyabi/rustdesk-server/pull/4)。
- API 分支 `development/m1-device-management`，草稿 PR [#6](https://github.com/HSOS6Miyabi/rustdesk-api/pull/6)。
- 当前内容包括设备预先登记检查及登录令牌验证。

## 接手步骤

1. `git clone --recurse-submodules` 本仓库，切换开发分支并检查最新提交。
2. 阅读 [IMPLEMENTATION_LEDGER.md](IMPLEMENTATION_LEDGER.md) 和 API 的 [功能清单](https://github.com/HSOS6Miyabi/rustdesk-api/blob/development/m1-device-management/docs/FEATURE_MATRIX.md)。
3. 检查两个草稿 PR 的 CI 测试结果。
4. 运行 `cargo test --lib --tests`、`cargo build --bins` 和服务通信测试。
5. 将 API 与 `hbbs` 放在同一测试网络，检查严格登记启停、客户端 `--deploy`、`RegisterPk`。
6. 测试原有 `MUST_LOGIN=N` 与 `MUST_LOGIN=Y` 的设备连接和中继连接。
7. 每次独立功能完成后更新实施台账、测试说明及两个仓库之间的对应提交。

## 主要目录

- `src/rendezvous_server.rs`：设备注册、连接协商、令牌验证。
- `src/device_deployment.rs`：通过内部 API 检查可选设备登记。
- `src/relay_server.rs`：连接中继。
- `scripts/test_runtime.py`：启动真实服务检查端口和连接协议。
- `scripts/test_webrtc_rendezvous.py`：验证 WebRTC 信令。

## 发布要求

日常开发不生成 Release，也不推送发行版 Docker 镜像。达到里程碑并完成测试后，才可使用 `v*` 标签和手动工作流的 `milestone_release` 选项。

## 当前测试通过的提交

- Server：[bfd1d8e](https://github.com/HSOS6Miyabi/rustdesk-server/commit/bfd1d8e2ca3f7d513e7686f42ead026826606b95)。
- CI：[测试结果](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42519807127)。
- 配套 API 的最新开发分支会继续更新，接手时应读取 API 草稿 PR #6 的最新提交。

## 本阶段增加的测试

```bash
python3 scripts/test_device_deployment.py target/debug/hbbs
```

该脚本会启动临时 HTTP 服务并运行真实 `hbbs`，检查设备许可、冲突、撤销及设备身份信息。

如果严格登记模式已启用，但 API 尚未启用对应设置或暂时无法访问，`hbbs` 将拒绝新的设备登记。未启用严格登记时保留原有设备注册方式。

## 多中继服务器动态管理

本阶段新增 `src/relay_policy.rs`，并在 `src/rendezvous_server.rs` 中增加动态同步与中继选择。配套 API 通过 `relay_nodes` 表管理节点，并提供受保护的 `GET /internal/v1/relay/nodes` 接口。

配置和启用方法见 [环境变量说明](environment-variables.md)。如果不需要集中管理多个中继，保持 `RUSTDESK_API_RELAY_NODES_URL` 未设置即可。

```bash
cargo test --lib --tests
cargo build --bins
python3 scripts/test_runtime.py target/debug/hbbs target/debug/hbbr
python3 scripts/test_managed_relays.py target/debug/hbbs
```

最后一个测试会创建临时 HTTP API 和模拟 TCP 中继，验证 hbbs 读取节点、IPv4 网络偏好、节点断开后的替代选择和空配置时恢复原有地址。

配套版本：Server [1dd7c0e](https://github.com/HSOS6Miyabi/rustdesk-server/commit/1dd7c0e85c10bf71f2bcfe86eebead8e09d4c495)，API [fc6d7ba](https://github.com/HSOS6Miyabi/rustdesk-api/commit/fc6d7ba1c0b87e304940b0e38197814cb16512a3)。这两个提交是已通过相应 CI 的版本组合。

相关测试记录：[Server CI](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42565263648)、[API CI](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42565425669)。

**下一阶段：**在真实客户端和不同网络环境中检查设备管理、会话权限及中继选择，新增功能时更新台账与测试说明。

## GeoLite2 Country MMDB 与 CSV 功能接手

- `src/geoip_country.rs`：支持 MaxMind Country MMDB 文件和 Country CSV 数据，均可用于识别 IPv4/IPv6 国家代码。MMDB 数据优先，未识别时尝试 CSV。
- `src/relay_policy.rs`：节点国家代码与精确 CIDR 的选择策略，CIDR 规则优先。
- `src/rendezvous_server.rs`：读取 `RUSTDESK_GEOIP_MMDB_FILE` 或 `RUSTDESK_GEOIP_CSV_DIR`，并支持 `reload-geo` 重新读取。
- `scripts/test_managed_relays.py`：内置小规模 Country CSV 测试数据，用真实 hbbs 进程验证国家偏好和服务配置变化。

配置示例：

```bash
export RUSTDESK_GEOIP_MMDB_FILE="/opt/rustdesk/geoip/GeoLite2-Country.mmdb"
# 也可以配置 RUSTDESK_GEOIP_CSV_DIR="/opt/rustdesk/geoip"
export RUSTDESK_API_RELAY_NODES_URL="http://127.0.0.1:21114/internal/v1/relay/nodes"
export RUSTDESK_API_INTERNAL_KEY="与 API 一致的密钥"
```

确保配套 API 已更新国家代码字段，关联 API 迁移版本为 277。继续开发时检查 Server 和 API 两个草稿 PR 中的最新 CI。

## 远程控制角色

Server 代码分布：

- `src/control_roles.rs`：查询 API 内部权限接口、验证位编码、缓存已查到的角色。
- `src/rendezvous_server.rs`：把角色权限写入 `PunchHole`、`FetchLocalAddr`、`RequestRelay` 消息。
- `scripts/test_control_roles.py`：启动 hbbs 和本地模拟 API，验证三种连接消息和未分配角色时的协议行为。

API 提供管理页面、设备／用户／设备组角色分配，以及 `GET /internal/v1/control/permissions?device_id=...`。

```bash
cargo test --lib --tests
cargo build --bins
python3 scripts/test_control_roles.py target/debug/hbbs
```

对应版本：Server [ee9ff73](https://github.com/HSOS6Miyabi/rustdesk-server/commit/ee9ff73be768677f24ee883e33bca59cfe21c48d)，API [e850b81](https://github.com/HSOS6Miyabi/rustdesk-api/commit/e850b81dce8f39468cf43cb5d1adb81d79bf65dc)。当前均已通过 CI。

使用本功能时需要配置 `RUSTDESK_API_CONTROL_ROLE_URL` 和内部通信密钥，具体见 [环境变量说明](environment-variables.md)。尚未分配控制角色的设备继续使用原有设置。

## 可选的服务器连接访问许可

Server 的 `src/connection_access.rs` 通过受内部密钥保护的 HTTP 请求向 API 查询访问许可，`src/rendezvous_server.rs` 在普通连接和中继连接协商前使用此结果。

`scripts/test_connection_access.py` 启动真实 hbbs、模拟 API 及目标设备注册，检查获得许可的连接可以发送到目标设备、未获许可的请求无法转发、API 无响应时严格模式拒绝新连接。

启用该功能需要：

```bash
export RUSTDESK_API_CONNECTION_ACCESS_URL="http://127.0.0.1:21114/internal/v1/connection/authorize"
export RUSTDESK_API_INTERNAL_KEY="与 API 相同的内部通信密钥"
```

未配置时保留原有连接行为。配套 API 当前数据库迁移版本为 282；集中连接访问规则首次引入于版本 280。启用严格权限检查前，应先在管理界面创建相应的允许规则。严格模式要求登录令牌及 API 中已登记的目标设备。

```bash
cargo test --lib --tests
cargo build --bins
python3 scripts/test_connection_access.py target/debug/hbbs
```

对应 Server 代码提交 [4ba02a9](https://github.com/HSOS6Miyabi/rustdesk-server/commit/4ba02a96a0b4eca0aab7bd77ed5c4bafe6d2d0b7)，[CI 测试通过](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42578682536)。


## 普通进程和 Docker 的组合测试

配套 API 的开发分支现包括客户端安装文件、通知及自动化管理。Server 的 `.github/workflows/milestone-preflight.yml` 会在 AMD64 和 ARM64 上获取当时的 API 开发分支，启动 API、`hbbs` 和 `hbbr`，检查服务、WebClient、通信端口、数据库和服务器身份密钥的保存情况。

普通服务器进程测试使用 `scripts/test_native_stack.py`，Docker 重建测试使用 `scripts/test_persistent_container.py`。备份、恢复与 API 数据库 282 的相关操作见 [配套 API 数据库备份恢复说明](https://github.com/HSOS6Miyabi/rustdesk-api/blob/development/m1-device-management/docs/DATABASE_BACKUP_RESTORE.md)。正式环境中的客户端远程操作、公网中继与 SMTP 仍需独立完成测试。
