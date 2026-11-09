# RustDesk Server 自动化测试

本仓库持续检查 Rust 单元测试、实际通信接口与可选设备登记。

## 构建与测试

```bash
git submodule update --init --recursive
cargo test --lib --tests
cargo build --bins
python3 scripts/test_runtime.py target/debug/hbbs target/debug/hbbr
python3 scripts/test_device_deployment.py target/debug/hbbs
```

`test_runtime.py` 启动真实的 `hbbs`、`hbbr`，验证 TCP、UDP、WebSocket 以及 WebRTC SDP 和 ICE 信令转发。

`test_device_deployment.py` 配合一个临时 HTTP 测试服务，检查 `RegisterPk` 的设备身份与登记许可，以及取消许可后再次注册的行为。

## 与 API 的配合测试

API 开发仓库：[rustdesk-api](https://github.com/HSOS6Miyabi/rustdesk-api)，对应开发分支 `development/m1-device-management`。两个仓库的 API、Server 版本要配合使用。

验证以下场景：

1. 默认模式允许原有设备注册和连接。
2. 严格模式下，未登记设备被拒绝。
3. 使用管理令牌和客户端 `--deploy` 后，指定设备完成登记并可以重新连接。
4. 已撤销部署许可的设备无法在严格模式下重新登记。
5. `MUST_LOGIN=Y` 时，不完整或无效的连接令牌不能通过连接协商。

## CI 运行记录

- [Server 第一次集成测试通过](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42519426664)
- [Server 现行严格登记测试通过](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42519807127)

正式 Release 仅在里程碑完成后手动启动。

## 多中继配置与网络偏好

```bash
cargo test --lib --tests
cargo build --bins
python3 scripts/test_managed_relays.py target/debug/hbbs
```

`test_managed_relays.py` 启动一个真实 hbbs 进程、两个临时 TCP 中继节点、一个原有配置的备用节点和模拟 API。脚本检查以下行为：

1. hbbs 从内部 API 取得两个已启用节点；
2. 双方 IP 地址落入指定网络范围时，优先使用对应中继；
3. 一个中继断开后，自动选择仍可连接的节点；
4. API 清空动态节点列表后，恢复启动时配置的中继地址。

[2026-11-09 Server CI 运行记录](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42565263648)显示测试通过。需要对真实多地区客户端的延迟和连接质量进行进一步检查。

## GeoLite2 国家级中继识别

执行：

```bash
cargo test --lib --tests
cargo build --bins
python3 scripts/test_managed_relays.py target/debug/hbbs
```

单元测试读取 GeoLite2 Country Locations-en、Blocks-IPv4、Blocks-IPv6 的示例数据，并使用 `tests/fixtures/GeoLite2-Country-Test.mmdb` 检查 MMDB 的 IPv4/IPv6 国家代码与 CSV 补充查询。示例 MMDB 来源和授权信息见该目录 README。

`test_managed_relays.py` 启动真实 hbbs、模拟 API、中继服务器，依次测试：根据国家代码选择中继、精确 CIDR 优先、运行时 `reload-geo`、节点断开后的替代选择、恢复原有中继地址。

[GitHub Actions 测试记录](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42567610418)：通过。

## 官方会话控制权限

```bash
cargo test --lib --tests
cargo build --bins
python3 scripts/test_control_roles.py target/debug/hbbs
```

`test_control_roles.py` 会启动真实 hbbs 和临时 HTTP 服务，建立 UDP、TCP、WebSocket 连接，验证 `PunchHole.control_permissions`、`FetchLocalAddr.control_permissions`、`RequestRelay.control_permissions` 的 Protobuf 编码。

测试还检查未分配角色时保留原有协议消息。配套 API 需要执行 `go test ./service -run TestControl -count=1` 及 `go test ./http/controller/api -run TestInternalControl -count=1`。

[本阶段 Server CI](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42569942719)已通过。

## 可选的服务器连接访问许可

```bash
cargo test --lib --tests
cargo build --bins
python3 scripts/test_connection_access.py target/debug/hbbs
```

运行测试将启动 hbbs 和本地模拟 API，验证有效授权令牌、未获授权的客户端、缺少令牌的普通连接、中继连接以及 API 无法访问的情况。无授权的连接请求不会发送给目标设备。

[Server CI 运行记录](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42578682536)：通过。

## 双架构组合镜像预演

`.github/workflows/milestone-preflight.yml` 在 AMD64 和 ARM64 上分别读取 API 与 Server 的开发分支，运行 Go、Rust 和 WebClient 测试，构建本地 API 镜像、Server 程序与组合容器镜像，并用 `scripts/test_container_image.py` 启动容器检查真实服务。镜像仅保留在 GitHub Actions 运行器上，不上传正式仓库，也不创建 Release。

已通过的组合检查：[42585097640](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42585097640)。新增 MMDB 的 Rust 单元和实际服务检查：[42588361437](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42588361437)。


## 普通服务器进程及数据保持测试

在 API 编译文件和 WebClient 文件均已准备好后，执行以下测试：

```bash
python3 scripts/test_native_stack.py /path/to/apimain target/release/hbbs target/release/hbbr
python3 scripts/test_container_image.py rustdesk-combined:dev-preflight
python3 scripts/test_persistent_container.py rustdesk-combined:dev-preflight
```

`test_native_stack.py` 在同一临时目录运行 API、`hbbs`、`hbbr`，验证 TCP、UDP、WebSocket、WebClient、重启后的账户、数据库版本及公钥保持一致。

`test_persistent_container.py` 挂载独立的 API 与 Server 数据卷，重新创建 Docker 容器，检查账户、数据库和 RustDesk 身份文件保持一致。整个过程使用测试数据和临时容器，不创建正式发行镜像。

对应 [AMD64、ARM64 组合部署检查 #42620496807](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42620496807)，成功。配套 API 的 SQLite、MySQL 和 PostgreSQL 备份恢复方法见 [数据库备份恢复说明](https://github.com/HSOS6Miyabi/rustdesk-api/blob/development/m1-device-management/docs/DATABASE_BACKUP_RESTORE.md)。


## 最新严格模式组合检查

一次真实的 hbbs 运行中同时测试严格登记、MUST_LOGIN、JWT、集中连接许可和控制角色：

```bash
python3 scripts/test_strict_combination.py target/debug/hbbs
```

此测试使用临时内部 HTTP API，检查已登记设备的允许与撤销、有效和无效令牌、无连接权限、API 暂时不可用及控制角色消息。对应 [Server Rust CI #42634291061](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42634291061) 已成功；[AMD64、ARM64 双架构组合部署 #42634291214](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42634291214) 也已成功。未来结合真实 API、客户端与公网环境时，仍需单独记录实际操作结果。

新接手人员请先查看 [Server 开发交接快照](HANDOFF_SNAPSHOT_2026-11-09.md)，以及配套 [API 22 项任务记录](https://github.com/HSOS6Miyabi/rustdesk-api/blob/development/m1-device-management/docs/TASK_VERIFICATION_RECORD.md)。


## 使用实际 API 的设备登记与严格模式联合测试

在 API 源代码目录将 `cmd/apimain.go` 编译为 `docker-bin/apimain`，然后在 Server 仓库编译 `hbbs`、`hbbr`。联合测试会创建自己的临时数据库、配置文件和通信密钥：

```bash
python3 scripts/test_real_api_registration.py /path/to/rustdesk-api/docker-bin/apimain target/release/hbbs
python3 scripts/test_real_api_strict_combination.py /path/to/rustdesk-api/docker-bin/apimain target/release/hbbs
```

第一项检查实际 API 对设备部署的响应、重复登记、冲突、撤销及 API 中断；第二项在同一实际 API 与 hbbs 中检查 JWT、登录令牌、访问许可、控制角色与中继信令。两项已经纳入 `.github/workflows/milestone-preflight.yml`，并在 AMD64、ARM64 上通过。

[两架构联合测试 #42653555800](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42653555800) 同时完成普通进程、组合 Docker 容器、服务通信、重启及数据保持检查。正式多设备和公网测试仍需配置实际终端及网络环境。


## 最新配套 API 的复查要求

配套 API 开发分支的设备所属用户转移功能已经更新；在 Server 分支运行 `.github/workflows/milestone-preflight.yml` 时，需要读取 API 当前代码并记录实际 Git 提交。组合测试继续检查真实 API 与 `hbbs`、JWT、设备许可、控制角色和容器重启后的数据库保存结果。


## 配套 API 的设备心跳测试

在 API 的 `development/m1-device-management` 分支，执行：

```bash
go test ./http/controller/api -run '^TestManagedHeartbeatChecksApprovedDeployment$' -count=1
```

检查已批准、未登记和撤销许可后的心跳策略响应，并保持现有普通设备心跳行为。该测试已包含在本仓库双架构联合工作流运行的 API Go 检查中。


## 实际 API 登录及 WebRTC 严格模式联合检查

完成 API 与 Server 编译后，在 Server 源代码目录执行：

```bash
python3 scripts/test_real_api_strict_combination.py /path/to/rustdesk-api/docker-bin/apimain target/release/hbbs
```

测试启动实际 API 与 `hbbs`，创建临时账户并通过真实 HTTP 登录和登出接口验证 JWT、旧令牌撤销后的拒绝、再次登录签发不同令牌、设备访问规则、控制角色、WebRTC SDP/ICE 和 API 中断时的处理。

[AMD64 和 ARM64 联合检查 #42666031144](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42666031144) 已成功。实际终端与公网网络检查按统一任务记录执行。


## 设备许可撤销后的连接拒绝

在 Server 的 `scripts/test_real_api_strict_combination.py` 中，同一实际 API 与 `hbbs` 环境会先验证正常连接，然后撤销设备部署许可并再次发起连接和中继请求。后续请求应被拒绝，目标设备也不应收到未经授权的连接消息。

此检查已纳入双架构测试：[Server #42669744598](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42669744598)。配套 API 的严格授权单元测试位于 `service/connection_access_deployment_test.go`，设备心跳测试位于 `http/controller/api/device_policy_heartbeat_test.go`。
