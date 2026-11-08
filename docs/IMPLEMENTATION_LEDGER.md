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
