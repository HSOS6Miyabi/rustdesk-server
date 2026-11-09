# RustDesk Server 开发交接快照

更新时间：2026 年 11 月 9 日。本文件是 RustDesk Server 仓库的当前交接入口。完整的 **F01–F20 功能清单及 T001–T022 工作事项**集中维护在配套 API 仓库：[开发交接总览](https://github.com/HSOS6Miyabi/rustdesk-api/blob/development/m1-device-management/docs/HANDOFF_SNAPSHOT_2026-11-09.md)、[统一实施台账](https://github.com/HSOS6Miyabi/rustdesk-api/blob/development/m1-device-management/docs/IMPLEMENTATION_LEDGER.md)、[逐项测试记录](https://github.com/HSOS6Miyabi/rustdesk-api/blob/development/m1-device-management/docs/TASK_VERIFICATION_RECORD.md)。

## 一、当前仓库状态

| 项目 | 当前内容 |
| --- | --- |
| Server 仓库与分支 | [HSOS6Miyabi/rustdesk-server](https://github.com/HSOS6Miyabi/rustdesk-server) · `development/m1-device-management` |
| Server 已核实功能提交 | [`eb4b586f9c65a1060dea8ce56b4809dec746c788`](https://github.com/HSOS6Miyabi/rustdesk-server/commit/eb4b586f9c65a1060dea8ce56b4809dec746c788) |
| 配套 API 已核实功能提交 | [`e898985f8b2242e0a4f5e28c1eed2a6ced17b37e`](https://github.com/HSOS6Miyabi/rustdesk-api/commit/e898985f8b2242e0a4f5e28c1eed2a6ced17b37e) |
| 草稿拉取请求 | [Server #4](https://github.com/HSOS6Miyabi/rustdesk-server/pull/4) 和 [API #6](https://github.com/HSOS6Miyabi/rustdesk-api/pull/6) |
| 原有正式发行 | Server `v1.1.17-api.9`；API `v3.0.0-api.96` |
| 配套 API 数据库迁移版本 | **282** |

两个 PR 均保持 Draft。开发阶段不合并默认分支、不生成正式 Release、不更新正式 Docker 镜像。维护者完成里程碑审核并明确批准前，继续运行测试和维护开发文档。

## 二、已验证的代码与部署方式

Server 现有代码支持：`hbbs` 设备登记与连接协商、`hbbr` 中继、可选严格设备预先登记、`MUST_LOGIN` JWT 校验、API 集中连接许可、远程控制角色与 Protobuf 权限转发、动态中继节点选择、GeoLite2 Country MMDB/CSV 和 `reload-geo`，以及 WebSocket、WebRTC 信令兼容。

| 测试范围 | 已成功运行 |
| --- | --- |
| Rust 单元与二进制编译，实际 hbbs/hbbr、严格登记、JWT、访问许可和控制角色测试 | [Server #42647450900](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42647450900) |
| AMD64/ARM64 实际 API、hbbs 联合授权与严格模式、组合镜像、普通进程、容器重新创建及数据保持 | [Server #42647450607](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42647450607) |
| 配套 API Go/浏览器/WebClient 及自动化检查 | [API #42652681801](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42652681801) |
| 官方 RustDesk 1.5.1 Windows、Linux、macOS 启动及 Android 模拟器 | [API #42646358634](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42646358634) |
| 官方 Linux 1.5.1 `--deploy`、`--assign` 对实际 API 的部署及直接分配 | [API #42652682083](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42652682083) |
| SQLite、MySQL 8.4、PostgreSQL 16 模拟升级与恢复 | [API #42652681804](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42652681804) |

组合检查 #42634291214 当时检出的 API 提交为 [`1c896cd8facbc0f73270a3cefe03923bda3b5a05`](https://github.com/HSOS6Miyabi/rustdesk-api/commit/1c896cd8facbc0f73270a3cefe03923bda3b5a05)，Server PR 合并测试提交为 `019ce9ea88f07aa7af1a41383a8fadfa0c9137ed`（包含 Server 功能提交 `66a20931`）。最新双架构组合预演 [#42647450607](https://github.com/HSOS6Miyabi/rustdesk-server/actions/runs/42647450607) 已读取配套 API 功能提交 `dc0a9983`，同时运行实际 API 与 hbbs 的设备登记及严格访问许可测试，完成 Docker 部署和数据保持检查。后续修改仍需使用最新两个开发分支复查。

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

1. **T001、T004**：实际 API 与 `hbbs` 的设备登记、JWT、访问规则及权限信令已通过双架构联合测试；继续使用至少两台正式客户端和 `hbbr` 检查远程控制、直连、中继及 WebRTC 的实际会话效果。
2. **T003、T014**：用两台真实设备检查十四项控制角色权限、客户端心跳策略的允许、禁止、清除和默认设置效果。
3. **T005、T018**：准备不同地区的真实公网中继节点与获授权 GeoLite2 Country 数据，检查选路、不可用节点的替代选择与 `reload-geo`。
4. **T006、T008**：在实际部署主机做数据库与 Server 私钥备份恢复、普通进程/Docker 系统重启、端口和反向代理检查。正式 API 数据库应当保留版本 282 的新增表；备份还应覆盖客户端安装文件目录。
5. **T002、T007、T009、T010、T013、T019、T020、T022**：由 API 交接文档统一安排真实客户端、账户登录、邮箱、管理界面、客户端安装及团队使用测试。
6. **T011、T012、T015–T017、T021**：对应构建预演、发行批准、独立管理令牌与批量管理、官方版本持续研究；具体状态以配套 API 22 项逐项记录为准。

没有可访问的正式服务器、真实外部 SMTP、跨地区测试网络和业务数据库备份时，应保留对应项目为实际环境待检查。测试数据使用独立密钥，不将密码、身份令牌或服务器私钥写入 GitHub。

## 五、接手顺序与配置提醒

先读取 [Server 环境变量说明](environment-variables.md)、[部署说明](../README.md)、[Server 测试说明](TESTING.md) 和配套 [API 交接快照](https://github.com/HSOS6Miyabi/rustdesk-api/blob/development/m1-device-management/docs/HANDOFF_SNAPSHOT_2026-11-09.md)。首次启用可选严格功能时，确保 API 和 Server 的 `RUSTDESK_API_INTERNAL_KEY` 一致，设置 `RUSTDESK_API_JWT_KEY`、`MUST_LOGIN` 和 `REQUIRE_DEVICE_DEPLOYMENT`，并先创建允许连接的设备和访问规则。初始迁移应使用专门的测试环境。

交接人更新代码后，应重新运行 Server 的 Rust 检查和两个架构的组合预演，将新的两个仓库的实际提交 SHA、测试运行号和真实环境结果同时写入这份快照、[Server 实施台账](IMPLEMENTATION_LEDGER.md) 和配套 [22 项任务记录](https://github.com/HSOS6Miyabi/rustdesk-api/blob/development/m1-device-management/docs/TASK_VERIFICATION_RECORD.md)。发布由维护者另行明确批准。


## 六、配套 API 设备所有者转移与会话处理

配套 API 的设备分配命令及管理页面在变更设备所有者时，均同步设备所属用户与部署记录，并撤销与该设备编号或有效 UUID 关联的旧会话。相关 Go 测试及官方 Linux 客户端检查已经完成：

- [API 代码提交 e898985f](https://github.com/HSOS6Miyabi/rustdesk-api/commit/e898985f8b2242e0a4f5e28c1eed2a6ced17b37e)
- [API 综合测试 #42652681801](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42652681801)
- [官方 Linux 客户端测试 #42652682083](https://github.com/HSOS6Miyabi/rustdesk-api/actions/runs/42652682083)

Server 的联合部署工作流持续读取配套 API 开发分支，检查严格登记与访问许可。本项目实际设备端的远程操作仍需使用独立终端测试。
