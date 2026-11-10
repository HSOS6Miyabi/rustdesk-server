# RustDesk Server 正式版本与维护说明

更新时间：2026 年 11 月 10 日。本文件记录当前正式版本、自动化测试和仍需实际环境检查的项目。完整的 **F01–F20 功能清单及 T001–T022 工作事项**集中维护在配套 API 仓库：[开发交接总览](https://github.com/HSOS6Miyabi/rustdesk-api/blob/master/docs/HANDOFF_SNAPSHOT_2026-11-09.md)、[统一实施台账](https://github.com/HSOS6Miyabi/rustdesk-api/blob/master/docs/IMPLEMENTATION_LEDGER.md)、[逐项测试记录](https://github.com/HSOS6Miyabi/rustdesk-api/blob/master/docs/TASK_VERIFICATION_RECORD.md)。

## 一、当前仓库状态

| 项目 | 当前内容 |
| --- | --- |
| Server 仓库与分支 | [HSOS6Miyabi/rustdesk-server](https://github.com/HSOS6Miyabi/rustdesk-server) · `forapi` |
| Server 已发布代码提交 | [`2d0896ecea4cf147f6fb4d2cdadf3278ab390851`](https://github.com/HSOS6Miyabi/rustdesk-server/commit/2d0896ecea4cf147f6fb4d2cdadf3278ab390851) |
| API 已发布代码提交 | [`a6d338821cfba2daffa34f9cc3b06605ea1edf03`](https://github.com/HSOS6Miyabi/rustdesk-api/commit/a6d338821cfba2daffa34f9cc3b06605ea1edf03) |
| 已合并的拉取请求 | [Server #4](https://github.com/HSOS6Miyabi/rustdesk-server/pull/4) 和 [API #6](https://github.com/HSOS6Miyabi/rustdesk-api/pull/6) |
| 正式发行版本 | [Server v1.1.17-api.21](https://github.com/HSOS6Miyabi/rustdesk-server/releases/tag/v1.1.17-api.21) 和 [API v3.0.0-api.103](https://github.com/HSOS6Miyabi/rustdesk-api/releases/tag/v3.0.0-api.103) |
| 配套 API 数据库迁移版本 | **282** |

两个 PR 已合并并发布正式 Release。Server 组合镜像使用 API v3.0.0-api.103，提供 Linux AMD64、ARM64 及 `latest` 标签。真实设备与正式业务环境仍需单独检查。

## 二、已验证的代码与部署方式

Server 现有代码支持：`hbbs` 设备登记与连接协商、`hbbr` 中继、可选严格设备预先登记、`MUST_LOGIN` JWT 校验、API 集中连接许可、远程控制角色与 Protobuf 权限转发、动态中继节点选择、GeoLite2 Country MMDB/CSV 和 `reload-geo`，以及 WebSocket、WebRTC 信令兼容。

| 测试范围 | 已成功运行 |
| --- | --- |
| Rust 单元与二进制编译，实际 hbbs/hbbr、严格登记、JWT、访问许可和控制角色测试 | [#42690542191](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42690542191) |
| AMD64/ARM64 实际 API、hbbs 联合授权与严格模式、组合镜像、普通进程、容器重新创建及数据保持 | [#42689263400](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42689263400) |
| 配套 API Go/浏览器/WebClient 及自动化检查 | [#42689275371](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42689275371) |
| 官方 RustDesk 1.5.1 Windows、Linux、macOS 启动及 Android 模拟器 | [#42688060138](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42688060138) |
| 官方 Linux 1.5.1 `--deploy`、`--assign` 对实际 API 的部署及直接分配 | [#42688060407](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42688060407) |
| SQLite、MySQL 8.4、PostgreSQL 16 模拟升级与恢复 | [#42688060078](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42688060078) |

[Server 正式发行工作流 #42690556784](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42690556784) 完成 Linux AMD64、ARM64 程序构建、GitHub Release 与 Docker 镜像发布，并检查 API、`hbbs`、`hbbr` 和 WebSocket。组合镜像使用 API v3.0.0-api.103。

最新严格模式联合检查同时使用实际 API 签发的 JWT、真实登录与登出接口，以及 WebRTC SDP、ICE 信令。重新登录取得新令牌后，原已撤销的会话保持失效。测试已在 AMD64 和 ARM64 通过。移动管理页面的窄屏顶部导航也通过 Chromium 检查。

## 三、主要文件与对应测试

| 模块 | 关键实现 | 自动化测试 |
| --- | --- | --- |
| 严格设备登记和撤销 | `src/device_deployment.rs`、`src/rendezvous_server.rs` | `scripts/test_device_deployment.py`、`scripts/test_real_api_registration.py` |
| 登录 JWT 与集中连接许可 | `src/jwt.rs`、`src/connection_access.rs` | `scripts/test_connection_access.py`、`scripts/test_strict_combination.py`、`scripts/test_real_api_strict_combination.py` |
| 远程会话控制角色 | `src/control_roles.rs`、`src/rendezvous_server.rs` | `scripts/test_control_roles.py`、`scripts/test_strict_combination.py` |
| 中继节点与国家判断 | `src/relay_policy.rs`、`src/geoip_country.rs` | `scripts/test_managed_relays.py` |
| TCP、UDP、WebSocket、WebRTC | `src/rendezvous_server.rs`、`src/relay_server.rs` | `scripts/test_runtime.py`、`scripts/test_webrtc_rendezvous.py` |
| 普通服务器进程与组合容器 | `docker/`、`.github/workflows/milestone-preflight.yml` | `scripts/test_native_stack.py`、`scripts/test_container_image.py`、`scripts/test_persistent_container.py` |

日常开发先执行：

```bash
git submodule update --init --recursive
cargo test --lib --tests
cargo build --bins
python3 scripts/test_runtime.py target/debug/hbbs target/debug/hbbr
python3 scripts/test_device_deployment.py target/debug/hbbs
python3 scripts/test_managed_relays.py target/debug/hbbs
python3 scripts/test_control_roles.py target/debug/hbbs
python3 scripts/test_connection_access.py target/debug/hbbs
python3 scripts/test_strict_combination.py target/debug/hbbs
```

在 GitHub Actions 使用 `.github/workflows/verify-server.yml` 及 `.github/workflows/milestone-preflight.yml`；两个工作流分别运行 Server 通信检查和双架构组合部署检查。

## 四、仍需完成的服务端真实环境工作

1. **T001、T004**：实际 API 与 `hbbs` 的设备登记、撤销后的新连接拒绝、账户登录、JWT、WebRTC SDP/ICE、访问规则和控制权限信令已通过双架构联合测试；两台实际终端的远程操作仍需检查。
2. **T003、T014**：API 已检查严格登记设备的心跳许可及撤销后的策略拒绝；继续用两台真实设备检查十四项控制角色权限及客户端策略的实际效果。
3. **T005、T018**：准备不同地区的真实公网中继节点与获授权 GeoLite2 Country 数据，检查选路、不可用节点的替代选择与 `reload-geo`。
4. **T006、T008**：在实际部署主机做数据库与 Server 私钥备份恢复、普通进程/Docker 系统重启、端口和反向代理检查。正式 API 数据库应当保留版本 282 的新增表；备份还应覆盖客户端安装文件目录。
5. **T002、T007、T009、T010、T013、T019、T020、T022**：实际 API 的密码登录、登出与 JWT 唯一性检查，以及移动管理页面的截图检查已经通过；其余真实客户端、外部邮箱、目标服务器与团队使用测试按 API 逐项记录执行。
6. **T011、T012、T015–T017、T021**：对应构建预演、发行批准、独立管理令牌与批量管理、官方版本持续研究；具体状态以配套 API 22 项逐项记录为准。

没有可访问的正式服务器、真实外部 SMTP、跨地区测试网络和业务数据库备份时，应保留对应项目为实际环境待检查。测试数据使用独立密钥，不将密码、身份令牌或服务器私钥写入 GitHub。

## 五、接手顺序与配置提醒

先读取 [Server 环境变量说明](environment-variables.md)、[部署说明](../README.md)、[Server 测试说明](TESTING.md) 和配套 [API 交接快照](https://github.com/HSOS6Miyabi/rustdesk-api/blob/master/docs/HANDOFF_SNAPSHOT_2026-11-09.md)。首次启用可选严格功能时，确保 API 和 Server 的 `RUSTDESK_API_INTERNAL_KEY` 一致，设置 `RUSTDESK_API_JWT_KEY`、`MUST_LOGIN` 和 `REQUIRE_DEVICE_DEPLOYMENT`，并先创建允许连接的设备和访问规则。初始迁移应使用专门的测试环境。

交接人更新代码后，应重新运行 Server 的 Rust 检查和两个架构的组合预演，将新的两个仓库的实际提交 SHA、测试运行号和真实环境结果同时写入这份快照、[Server 实施台账](IMPLEMENTATION_LEDGER.md) 和配套 [22 项任务记录](https://github.com/HSOS6Miyabi/rustdesk-api/blob/master/docs/TASK_VERIFICATION_RECORD.md)。发布由维护者另行明确批准。


## 六、配套 API 设备所有者转移与会话处理

配套 API 的设备分配命令及管理页面在变更设备所有者时，均同步设备所属用户与部署记录，并撤销与该设备编号或有效 UUID 关联的旧会话。相关 Go 测试及官方 Linux 客户端检查已经完成：

- [API 代码提交 e898985f](https://github.com/HSOS6Miyabi/rustdesk-api/commit/e898985f8b2242e0a4f5e28c1eed2a6ced17b37e)
- [API 综合测试 #42670400984](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42670400984)
- [官方 Linux 客户端测试 #42666929312](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42666929312)

Server 的联合部署工作流持续检查严格登记与连接许可。正式组合镜像使用 API v3.0.0-api.103。实际设备远程控制仍需使用独立终端测试。


## 七、设备撤销后的新连接检查

严格设备登记与集中连接授权同时启用时，API 在每次授权新连接前检查设备的批准状态、UUID 及所属账户。撤销设备许可后，`hbbs` 对该设备的新连接请求和中继请求均予以拒绝。API 的设备心跳也会检查部署记录与设备所属账户的一致性。

- API 实现：`service/connection_access.go`、`http/controller/api/index.go`；检查记录：[API #42670400984](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42670400984)。
- Server 实际联合测试：`scripts/test_real_api_strict_combination.py`；AMD64、ARM64 结果：[Server #42669744598](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42669744598)。

需要通过 `RUSTDESK_API_CONNECTION_ACCESS_URL` 启用集中连接授权，才能对连接请求逐次查询最新设备许可。实际终端的远程控制及公网连接继续按统一任务记录检查。
