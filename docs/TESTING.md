# RustDesk Server 自动化测试

本仓库持续检查 Rust 单元测试、实际通信接口与可选设备登记。

## 构建与测试

```bash
git submodule update --init --recursive
cargo test --locked --lib --tests
cargo build --locked --bins
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
