# Configuration & Environment Variables

This document is the single reference for every option that the open‑source
RustDesk server binaries (`hbbs`, `hbbr`) understand: command‑line flags,
environment variables, and configuration files.

> **TL;DR** — For most people the command‑line flags shown by `hbbs --help` /
> `hbbr --help` are all you need. Environment variables are an alternative way to
> set the same options, plus a handful of extra tuning knobs that have no flag.

---

## How configuration is loaded

Both servers read their configuration from the following sources. For
**`hbbs`** the order of precedence, from highest to lowest, is:

1. **Command‑line flag** (e.g. `-p 21116`, `-k mykey`)
2. **`--config <file>`** — an INI file passed with `-c`/`--config`
3. **`.env`** — an INI file named `.env` in the working directory
4. **Inherited process environment** — variables exported before launch

A value set by a higher source overrides the same value from a lower one. Under
the hood every source is turned into a process environment variable, and the
code then reads that variable — so "flag", "config file" and "env var" are just
three ways to set the same thing.

For **`hbbr`** the precedence is: **flag** (`-b`, `-p`, `-k`) → **`.env`** →
**inherited environment**.

`RUST_LOG` is an exception to these rules. Both binaries initialize logging
before loading `.env` (or `hbbs`'s `--config` file), so `RUST_LOG` must be set
in the inherited process environment.

---

## `hbbs` — ID / rendezvous server

| Variable | CLI flag | Default | Description |
|---|---|---|---|
| `KEY` | `-k`, `--key` | `-` | Public key clients must use, a base64 secret key, or `-` / `_` to load or generate a key pair (`id_ed25519`, `id_ed25519.pub`). `-` and `_` have the same behavior, so explicitly passing `-k _` to `hbbs` is unnecessary. An explicitly empty value disables key validation; see [Keys](#keys-and-encryption). |
| `BIND` | `-b`, `--bind` | all interfaces | **Available since 1.1.17.** Local IPv4 or IPv6 address on which all `hbbs` TCP, UDP, and WebSocket listeners bind. This does not change the addresses advertised to clients. Supported by `--config`, `.env`, and the inherited environment. |
| `PORT` | `-p`, `--port` | `21116` | Main TCP/UDP listening port. `hbbs` also binds `PORT-1` (NAT type test) and `PORT+2` (WebSocket). |
| `RELAY-SERVERS` | `-r`, `--relay-servers` | *(empty)* | Optional relay server override handed to clients, as comma-separated `host` or `host:port` values. Leave empty when `hbbr` uses the same address as `hbbs` and the standard port `21117`; clients derive it automatically. Set this only when the relay uses a different IP/hostname or a non-standard port. |
| `RMEM` | `-M`, `--rmem` | `0` (system default) | UDP receive‑buffer size in bytes. Raise the OS limit first: `sudo sysctl -w net.core.rmem_max=52428800`. |
| *(config file)* | `-c`, `--config` | *(none)* | Path to an extra INI config file (see precedence above). |
| `TEST_HBBS` 🅴 | *(none)* | *(auto)* | UDP self‑test target checked at start‑up. Set to `no` to skip the check (useful behind some NATs/proxies), or to an explicit `host:port`. |
| `ALWAYS_USE_RELAY` 🅴 | *(none)* | `N` | `Y` forces every session through a relay (disables direct/hole‑punched connections). At runtime, send `always-use-relay Y` or `always-use-relay N` to the `hbbs` [loopback console](#runtime-console). |
| `DB_URL` 🅴 | *(none)* | `./db_v2.sqlite3` | Path/URL of the SQLite database file. See [Database](#database). |
| `MAX_DATABASE_CONNECTIONS` 🅴 | *(none)* | `1` | Size of the SQLite connection pool. |
| `MAX_PUNCH_REQUESTS` 🅴 | *(none)* | `100000` | Number of punch-request records kept in memory for the `punch-requests` [console](#runtime-console) command; the oldest is dropped when full. `0` disables recording. |
| `MAX_MESSAGE_KB` 🅴 | *(none)* | `64` | Largest message, in KiB, that `hbbs` accepts on its TCP and WebSocket listeners; a connection that sends a bigger one is dropped. Capped at `65536`. The default fits an online-status query for about 5000 standard 9–10 digit IDs, fewer with long custom IDs; a client whose query is too big shows no online status. |

🅴 = set through the inherited process environment.

> `PORT_FOR_API` / `KEY_FOR_API` are only used by RustDesk Server **Pro** and its
> API; they have no effect in the open‑source server.

---

## `hbbr` — relay server

| Variable | CLI flag | Default | Description |
|---|---|---|---|
| `KEY` | `-k`, `--key` | *(empty)* | The empty default intentionally disables relay key validation, avoiding key-pair setup and mismatch failures. To enable relay key validation, use the same non-empty key as `hbbs`; `-` / `_` have the same behavior and load or generate a key pair. An empty key allows clients without a matching key to use the relay, so choose this tradeoff deliberately on an exposed server. |
| `BIND` | `-b`, `--bind` | all interfaces | **Available since 1.1.17.** Local IPv4 or IPv6 address on which the relay TCP and WebSocket listeners bind. Supported by `.env` and the inherited environment; `hbbr` does not support `--config`. |
| `PORT` | `-p`, `--port` | `21117` | Relay listening port. `hbbr` also binds `PORT+2` for WebSocket relay. **Note:** when set via the `PORT` env var (not `-p`), `hbbr` listens on `PORT + 1`, so a shared `PORT=21116` makes `hbbs`=21116 and `hbbr`=21117. |

### Relay bandwidth / QoS

These have no CLI flag and can also be changed through the `hbbr`
[loopback console](#runtime-console) (`tb`, `sb`, `ls`, `dt`, `t`, …; send `h`
for help).

| Variable | Default | Unit | Description |
|---|---|---|---|
| `SINGLE_BANDWIDTH` | `128` | Mb/s | Normal maximum bandwidth for each relay connection. |
| `TOTAL_BANDWIDTH` | `1024` | Mb/s | Aggregate bandwidth cap shared by all relay connections. |
| `LIMIT_SPEED` | `32` | Mb/s | Per-connection cap applied after a connection is downgraded, and to IPs in `blacklist.txt`. |
| `DOWNGRADE_THRESHOLD` | `0.66` | ratio (0–1) | Fraction of `SINGLE_BANDWIDTH` that a connection's lifetime-average throughput must exceed to trigger downgrade. |
| `DOWNGRADE_START_CHECK` | `1800` | seconds | Delay before a connection becomes eligible for the lifetime-average downgrade check. |

Downgrade is decided independently for each connection; it does **not** check
aggregate relay congestion. After `DOWNGRADE_START_CHECK`, a connection is
capped to `LIMIT_SPEED` once its average throughput since it started exceeds
`SINGLE_BANDWIDTH * DOWNGRADE_THRESHOLD`. A lone transfer can therefore be
downgraded even when the relay is otherwise idle. `TOTAL_BANDWIDTH` is a
separate aggregate cap.

These may also be placed in `.env` using the uppercase spellings shown above
(e.g. `SINGLE_BANDWIDTH=256`).

### Blocklists / blacklists (files, not env vars)

`hbbr` reads two optional files from its working directory at start‑up:

* **`blacklist.txt`** — IPs that are **bandwidth‑limited** (one IP per line;
  anything after the first space on a line is ignored).
* **`blocklist.txt`** — IPs that are **refused** outright.

Both can also be edited live through the `hbbr` loopback console (`ba`/`br`,
`Ba`/`Br`).

### Runtime console

The runtime consoles are TCP command transports built into the services; they
are not `rustdesk-utils` commands or interactive standard-input consoles. A
connection from a loopback address is treated as a single console command:

```bash
# hbbs: toggle forced relay on PORT-1 (21115 by default)
printf 'always-use-relay Y' | nc 127.0.0.1 21115

# hbbr: list commands on its relay PORT (21117 by default)
printf 'h' | nc 127.0.0.1 21117
```

Use the corresponding configured ports if you changed `PORT`.

---

## Database

At runtime the database location comes from **`DB_URL`** (default
`./db_v2.sqlite3`). If unset, `hbbs` creates the SQLite file in its working
directory.

> **Do not confuse `DB_URL` with `DATABASE_URL`.** The `DATABASE_URL` entry in
> the repository's `.env` is used **only at compile time** by `sqlx` to check SQL
> queries; it is **not** read by the running server. Setting `DATABASE_URL` on a
> running server has no effect — use `DB_URL`.

---

## Logging

Both binaries use `flexi_logger`, which honours the standard **`RUST_LOG`**
environment variable (default level `info`). Set it in the process environment
before launching the binary. A value in `.env` or `hbbs`'s `--config` file is
loaded too late and has no effect on logging.

```bash
RUST_LOG=debug hbbs
```

---

## Keys and encryption

The `KEY` / `-k` value can be:

* a **public key** string — clients must present the matching key;
* a **base64‑encoded 64‑byte secret key** — the server derives the public key
  from it;
* **`-` or `_`** — the server loads a key pair from the working directory or
  generates one on first start, writing `id_ed25519` (private) and
  `id_ed25519.pub` (public);
* **empty** — key validation is disabled. `hbbs` still loads or generates key
  files for signing but deliberately leaves its active validation key empty;
  `hbbr` neither loads nor generates a key. Both services then accept clients
  without validating a key. This is the intentional `hbbr` default; use a
  non-empty value when relay key validation is required.

`hbbs` defaults to `-`, so it already loads or generates a key pair without an
explicit `-k _`. `hbbr` intentionally defaults to an empty key to avoid
key-pair setup and mismatch failures. Leave it empty for the default mode
without key validation. To enable relay key validation, give it the same
non-empty key as `hbbs`; both services can reuse key material from a shared
working directory. The `_` value is not a stricter mode than `-` in the current
implementation.

To supply your own key pair, place `id_ed25519` and `id_ed25519.pub` in the
process's **current working directory** before first start. That directory may
differ from the directory containing the executable. For the supervisor Docker
image, the working directory is `/data`.

---

## Docker image variables

The supervisor image (`rustdesk/rustdesk-server-s6`) starts both binaries with
s6 and adds a few convenience variables handled by its service scripts, **not**
by `hbbs`/`hbbr` directly:

| Variable | Default | Description |
|---|---|---|
| `RELAY` | `relay.example.com` | Passed to `hbbs` as `-r $RELAY` (your public address). |
| `ENCRYPTED_ONLY` | `0` | `1` adds `-k _` to both servers. This is redundant for `hbbs`, whose default is `-`, and opts `hbbr` into key validation instead of its intentional empty default. |
| `KEY_PUB` | *(unset)* | If set, written to `/data/id_ed25519.pub` on first start. |
| `KEY_PRIV` | *(unset)* | If set, written to `/data/id_ed25519` on first start. Provide **both** `KEY_PUB` and `KEY_PRIV`, or neither. |

Any variable from the tables above can also be passed straight through the
container's environment (e.g. `-e ALWAYS_USE_RELAY=Y`, `-e RUST_LOG=debug`).

The classic scratch image (`rustdesk/rustdesk-server`) contains only the
binaries and does **not** implement `RELAY`, `ENCRYPTED_ONLY`, `KEY_PUB`, or
`KEY_PRIV`; those variables are ignored by that image.

---

## Examples

### Command line — non-standard ports

```bash
# Tell clients where the relay listens because it is not using port 21117.
hbbs -p 22116 -r rustdesk.example.com:22117
hbbr -p 22117
```

### `.env` file (working directory)

```ini
# Non-standard ports shared by both binaries; hbbr listens on PORT+1.
relay-servers=rustdesk.example.com:22117
PORT=22116
```

### docker-compose

```yaml
services:
  rustdesk-server:
    image: rustdesk/rustdesk-server-s6:latest
    environment:
      - RELAY=rustdesk.example.com:21117
      - ALWAYS_USE_RELAY=Y
      - RUST_LOG=info
      - SINGLE_BANDWIDTH=256
    ports:
      - "21115:21115"
      - "21116:21116"
      - "21116:21116/udp"
      - "21117:21117"
      - "21118:21118"
      - "21119:21119"
    volumes: ["./data:/data"]
    restart: unless-stopped
```

### systemd

```ini
[Service]
Environment=ALWAYS_USE_RELAY=Y
Environment=RUST_LOG=info
ExecStart=/usr/bin/hbbs
```

---

## Port reference

| Port | Proto | Server | Purpose |
|---|---|---|---|
| 21115 | TCP | hbbs | NAT type test (`PORT-1`) |
| 21116 | TCP + UDP | hbbs | ID registration / rendezvous / hole punching (`PORT`) |
| 21117 | TCP | hbbr | Relay (`hbbr PORT`) |
| 21118 | TCP | hbbs | WebSocket rendezvous (`PORT+2`) |
| 21119 | TCP | hbbr | WebSocket relay (`hbbr PORT+2`) |

Ports 21118/21119 are only needed for the web client; you can omit them
otherwise.

## 与 RustDesk API 配合使用的设备登记

以下环境变量用于可选的设备预先登记功能。默认不启用，适合小型团队沿用原来的设备注册方式。

| 环境变量 | 作用 | 示例 |
| --- | --- | --- |
| `REQUIRE_DEVICE_DEPLOYMENT` | 设置为 `Y` 后，设备注册前必须获得 API 许可 | `N` |
| `RUSTDESK_API_INTERNAL_KEY` | API 与服务端之间的内部访问密钥 | 使用随机生成的长字符串 |
| `RUSTDESK_API_INTERNAL_URL` | 服务端查询设备登记结果的内部接口地址 | `http://127.0.0.1:21114/internal/v1/device/authorize` |
| `RUSTDESK_API_JWT_KEY` | 要求用户登录时验证会话令牌的密钥 | 与 API 使用相同的密钥 |

组合容器中可以用 `REQUIRE_DEVICE_DEPLOYMENT=Y` 和 `RUSTDESK_API_INTERNAL_KEY` 同时配置 API 与 `hbbs`。API 支持使用相同名称的环境变量。

分开部署时，需要让 `RUSTDESK_API_INTERNAL_URL` 指向 API 的内部服务地址，并限制该接口的网络访问。跨服务器通信建议使用 HTTPS 或可信任的内部网络。

当 `MUST_LOGIN=Y` 时，必须配置 `RUSTDESK_API_JWT_KEY`。不需要限制账户登录时可以继续使用 `MUST_LOGIN=N`。

## 多中继服务器与 API 自动同步

只有希望通过 API Web 管理界面配置多个 hbbr 节点时，才需要启用此功能。单中继部署可以继续使用现有的 `hbbs -r`、`relay-servers` 参数。

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `RUSTDESK_API_RELAY_NODES_URL` | 空 | API 内部节点列表地址，例如 `http://127.0.0.1:21114/internal/v1/relay/nodes`。留空时不启用自动同步 |
| `RUSTDESK_API_INTERNAL_KEY` | 空 | 与 API 配置一致的内部访问密钥 |
| `RUSTDESK_API_RELAY_SYNC_SECONDS` | `30` | 两次配置同步之间的秒数，支持 10 至 3600 |

例如：

```bash
export RUSTDESK_API_RELAY_NODES_URL="http://127.0.0.1:21114/internal/v1/relay/nodes"
export RUSTDESK_API_INTERNAL_KEY="替换为与 API 一致的内部通信密钥"
export RUSTDESK_API_RELAY_SYNC_SECONDS=30
hbbs -r relay-backup.example.com:21117
```

管理员在 API 管理界面中增加中继节点，填写公开的 `host:port` 地址，并可设置 IPv4/IPv6 的 CIDR 网络范围。hbbs 按当前在线节点和连接双方的 IP 网络选择中继。没有匹配范围时，采用原有的轮流选择方法。没有配置托管中继或 API 返回空节点时，使用 `-r` 中指定的原有中继。

内部节点列表应通过本地网络、受信任的私有网络或 HTTPS 访问。如果使用 Docker，API 与 hbbs 必须能够通过配置的地址相互通信；不能无条件使用宿主机的 `127.0.0.1`。

## 使用 GeoLite2 Country CSV 识别客户端国家

如果希望按国家自动选择中继，在运行 hbbs 的服务器上下载并解压 MaxMind GeoLite2 Country CSV。

需要以下三个文件放置在同一目录：

```text
/opt/rustdesk/geoip/
  GeoLite2-Country-Locations-en.csv
  GeoLite2-Country-Blocks-IPv4.csv
  GeoLite2-Country-Blocks-IPv6.csv
```

启动 hbbs 前设置：

```bash
export RUSTDESK_GEOIP_CSV_DIR="/opt/rustdesk/geoip"
```

GeoLite2 文件获取方式和 CSV 字段说明见 [MaxMind 开发者文档](https://dev.maxmind.com/geoip/docs/databases/city-and-country/)。

使用 API 的“中继节点管理”，在国家代码字段填写两位 ISO 国家代码，例如 `JP,US`。hbbs 会根据客户端 IP 的国家归属优先选择指定节点。如果管理员还设置了精确 CIDR 网络范围，精确网络规则将优先使用。

CSV 文件更新后，在 hbbs 的本地管理端口发送 `reload-geo`：

```bash
printf 'reload-geo' | nc 127.0.0.1 21115
```

如果使用自定义 ID 服务端端口，请将 21115 改成 `PORT-1`。

没有提供 `RUSTDESK_GEOIP_CSV_DIR` 或 Country CSV 文件时，其他中继设置仍然有效。GeoLite2 数据不包含在仓库和 Docker 镜像中，需要管理员自行准备。在 Docker 中使用时，将目录挂载到容器并设置容器内的路径。

## 从 API 获取远程控制角色

管理员可在 API 网页为设备、用户、设备组分配远程控制角色。要让 hbbs 在连接时向官方 RustDesk 客户端发送这些权限，设置以下变量：

| 环境变量 | 默认值 | 作用 |
| --- | --- | --- |
| `RUSTDESK_API_CONTROL_ROLE_URL` | 空 | 内部控制权限接口地址，例如 `http://127.0.0.1:21114/internal/v1/control/permissions`，不配置时保持原有权限 |
| `RUSTDESK_API_INTERNAL_KEY` | 空 | 与 API 配置一致的内部通信密钥 |
| `RUSTDESK_API_CONTROL_CACHE_SECONDS` | `5` | 按设备缓存权限结果的时间，允许 0 至 60 秒 |

示例：

```bash
export RUSTDESK_API_CONTROL_ROLE_URL="http://127.0.0.1:21114/internal/v1/control/permissions"
export RUSTDESK_API_INTERNAL_KEY="替换为与 API 一致的内部通信密钥"
export RUSTDESK_API_CONTROL_CACHE_SECONDS=5
```

当管理员在 API 中为设备分配角色后，hbbs 会在下一次连接协商时向被控客户端传送生效的 `ControlPermissions`。所有权限状态均按官方协议执行：`0` 沿用设备设置，`1` 禁止，`2` 允许。未分配角色时，客户端继续使用自己的权限设置。

API 与 hbbs 分别部署时，要把内部接口地址设置为 hbbs 实际能够访问的地址。Docker 容器中的 `127.0.0.1` 指向该容器自身，跨容器部署需要使用实际的内部服务名称或 IP 地址。
