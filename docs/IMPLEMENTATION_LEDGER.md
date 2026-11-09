# RustDesk Server 开发实施台账

## 2026-11-09：设备登记及连接协议兼容

开发分支：`development/m1-device-management`。

关联 API 分支：`HSOS6Miyabi/rustdesk-api` 的 `development/m1-device-management`。本阶段草稿 PR：Server [#4](https://github.com/HSOS6Miyabi/rustdesk-server/pull/4)，API [#6](https://github.com/HSOS6Miyabi/rustdesk-api/pull/6)。

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

Rust 单元测试、程序编译、TCP/UDP/WebSocket 实际服务检查由草稿 PR 的 CI 执行。跨项目的设备 `--deploy` 和 `--assign` 需结合 API 测试，详细说明见 [HANDOFF.md](HANDOFF.md)。

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
- API 草稿 PR：[rustdesk-api #6](https://github.com/HSOS6Miyabi/rustdesk-api/pull/6)。
- Server 草稿 PR：[rustdesk-server #4](https://github.com/HSOS6Miyabi/rustdesk-server/pull/4)。

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
