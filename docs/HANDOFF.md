# RustDesk Server 接手说明

本项目与 [配套 API](https://github.com/HSOS6Miyabi/rustdesk-api) 共同维护，主要面向小型团队的 OSS 自托管需求。

## 正在开发

- Server 分支 `development/m1-device-management`，草稿 PR [#4](https://github.com/HSOS6Miyabi/rustdesk-server/pull/4)。
- API 分支 `development/m1-device-management`，草稿 PR [#6](https://github.com/HSOS6Miyabi/rustdesk-api/pull/6)。
- 当前内容包括设备预先登记检查及登录令牌验证。

## 接手步骤

1. `git clone --recurse-submodules` 本仓库，切换开发分支并检查最新提交。
2. 阅读 [IMPLEMENTATION_LEDGER.md](IMPLEMENTATION_LEDGER.md) 和 API 的 [功能清单](https://github.com/HSOS6Miyabi/rustdesk-api/blob/development/m1-device-management/docs/FEATURE_MATRIX.md)。
3. 检查两个草稿 PR 的 CI 测试结果。
4. 运行 `cargo test --locked --lib --tests`、`cargo build --locked --bins` 和服务通信测试。
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
