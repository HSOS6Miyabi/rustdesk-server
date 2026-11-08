# RustDesk 服务端维护说明

本仓库从 RustDesk 官方 `rustdesk/rustdesk-server` 合并源代码更新，并保留了与本项目 API 配合使用的功能。

## 已包含的功能

- RustDesk 客户端通过 API 登录后仍能正常完成设备会话协商。
- 可通过 `MUST_LOGIN=Y` 或 `--must-login=Y` 要求客户端登录。
- 可通过 `RUSTDESK_API_JWT_KEY` 为会话令牌提供校验密钥。使用强随机密钥，并保证 API 和服务端配置相同。
- 客户端 WebSocket 连接与加密 TCP 连接兼容。
- 采用官方截至 2026 年 11 月 7 日的服务器更新，包括 UDP 请求限制、消息大小限制、中继请求验证、WebSocket 握手时限和转发超时处理。

## 更新官方版本

1. 读取官方主分支的更改和发布说明。
2. 重点检查 `src/rendezvous_server.rs`、`src/relay_server.rs`、`src/jwt.rs` 与 `libs/hbb_common`。
3. 合并官方代码时保留 API 验证、连接协商与加密传输。
4. 在 GitHub Actions 中执行 Rust 单元测试及三个可执行程序的编译。
5. 测试通过后才能创建版本标签并发布。

## 配置与兼容性

服务器的公共端口、`MUST_LOGIN` 和 `RUSTDESK_API_JWT_KEY` 与原作者的使用方式兼容。实际连接时，客户端提供的设备 ID 仍由 RustDesk 服务端处理。用户分组与联系人控制的是 API 返回的设备可见范围。

## 组合镜像包含的 API 版本

服务端 Docker 镜像包含 RustDesk API 和 `hbbs`、`hbbr`。当前组合镜像使用 RustDesk API `v3.0.0-api.102`，以确保 WebClient v2 的 HTTPS/WSS 支持和管理界面能够正常使用。

如果需要更新组合镜像中的 API 版本，请先确认对应的 `ghcr.io/hsos6miyabi/rustdesk-api` 镜像已经发布，再修改 `docker/Dockerfile` 中的 `API_IMAGE_TAG` 默认值，以及 `.github/workflows/release-server.yml` 的同名构建参数。提交后由 GitHub Actions 测试并发布新镜像。

## 连接通信测试

在 Linux 系统中安装 Rust 及项目依赖后，执行：

```bash
cargo test --locked --lib --tests
cargo build --locked --bins
python3 scripts/test_runtime.py target/debug/hbbs target/debug/hbbr
```

测试程序启动实际的 `hbbs` 和 `hbbr` 进程，检查 TCP、WebSocket 和 UDP 服务。WebRTC 测试位于 `scripts/test_webrtc_rendezvous.py`，会通过 WebSocket 发起 SDP Offer，模拟被控设备返回 SDP Answer，并发送 ICE 候选地址，检查服务器能否将这些消息转发至正确的设备。

GitHub Actions 在发布组合 Docker 镜像后还会启动镜像内的 API、`hbbs` 和 `hbbr`，检查监听端口和 HTTP 响应。桌面画面、键盘、鼠标及真实设备的长期连接仍需在安装 RustDesk 客户端的运行环境中检查。
