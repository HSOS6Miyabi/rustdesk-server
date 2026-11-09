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
