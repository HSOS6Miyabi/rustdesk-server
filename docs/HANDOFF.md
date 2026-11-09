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
cargo test --locked --lib --tests
cargo build --locked --bins
python3 scripts/test_runtime.py target/debug/hbbs target/debug/hbbr
python3 scripts/test_managed_relays.py target/debug/hbbs
```

最后一个测试会创建临时 HTTP API 和模拟 TCP 中继，验证 hbbs 读取节点、IPv4 网络偏好、节点断开后的替代选择和空配置时恢复原有地址。

配套版本：Server [1dd7c0e](https://github.com/HSOS6Miyabi/rustdesk-server/commit/1dd7c0e85c10bf71f2bcfe86eebead8e09d4c495)，API [fc6d7ba](https://github.com/HSOS6Miyabi/rustdesk-api/commit/fc6d7ba1c0b87e304940b0e38197814cb16512a3)。这两个提交是已通过相应 CI 的版本组合。

相关测试记录：[Server CI](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42565263648)、[API CI](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42565425669)。

**下一阶段：**继续补充 GeoLite2 地理位置数据库、更多客户端策略和设备管理功能，新增模块时更新台账及测试说明。

## GeoLite2 Country CSV 功能接手

- `src/geoip_country.rs`：按 MaxMind 官方 Country CSV 字段读取数据。使用 IPv4/IPv6 网络前缀查找国家代码。
- `src/relay_policy.rs`：节点国家代码与精确 CIDR 的选择策略，CIDR 规则优先。
- `src/rendezvous_server.rs`：读取 `RUSTDESK_GEOIP_CSV_DIR`，并支持 `reload-geo` 重新载入。
- `scripts/test_managed_relays.py`：内置小规模 Country CSV 测试数据，用真实 hbbs 进程验证国家偏好和服务配置变化。

配置示例：

```bash
export RUSTDESK_GEOIP_CSV_DIR="/opt/rustdesk/geoip"
export RUSTDESK_API_RELAY_NODES_URL="http://127.0.0.1:21114/internal/v1/relay/nodes"
export RUSTDESK_API_INTERNAL_KEY="与 API 一致的密钥"
```

确保配套 API 已更新国家代码字段，关联 API 迁移版本为 277。继续开发时检查 Server 和 API 两个草稿 PR 中的最新 CI。
