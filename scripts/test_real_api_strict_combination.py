#!/usr/bin/env python3
"""Test strict JWT, access rules and control permissions with real API and hbbs."""

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen

from test_connection_access import (
    must_not_forward, recv_registered_target, websocket_request,
)
from test_control_roles import require_permissions
from test_device_deployment import register_device, wait_for_port
from test_native_stack import available_tcp_port, start_process, stop_process
from test_real_api_registration import post_json, wait_for_api
from test_runtime import find_ports
from test_webrtc_rendezvous import integer_field, raw_field, text_field


DEVICE = "strict-real-device-001"
PERMISSIONS = (1 << 0) | (2 << 4) | (1 << 6) | (2 << 26)


def jwt(user_id, secret):
    def encode(value):
        payload = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")

    message = encode({"alg": "HS256", "typ": "JWT"}) + "." + encode({
        "user_id": user_id, "exp": int(time.time()) + 3600,
    })
    signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()
    return message + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()


def seed_sessions(db_path, jwt_secret):
    with sqlite3.connect(db_path, timeout=15) as db:
        db.execute("PRAGMA busy_timeout = 10000")
        admin = db.execute(
            "SELECT id FROM users WHERE username = 'admin'"
        ).fetchone()
        version = db.execute(
            "SELECT version FROM versions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if admin is None or version is None or version[0] < 282:
            raise AssertionError("API administrator or required database schema is missing")
        admin_id = admin[0]
        viewer_id = db.execute(
            "INSERT INTO users (username, status, is_admin) VALUES (?, 1, 0)",
            ("integration-viewer",),
        ).lastrowid
        admin_token, viewer_token = jwt(admin_id, jwt_secret), jwt(viewer_id, jwt_secret)
        invalid_signature = jwt(viewer_id, secrets.token_urlsafe(32))
        for user_id, token in (
            (admin_id, admin_token), (viewer_id, viewer_token),
            (viewer_id, invalid_signature),
        ):
            db.execute(
                "INSERT INTO user_tokens (user_id, token, expired_at) VALUES (?, ?, ?)",
                (user_id, token, int(time.time()) + 1800),
            )
    return admin_id, viewer_id, admin_token, viewer_token, invalid_signature


def set_viewer_rule(db_path, viewer_id, effect):
    with sqlite3.connect(db_path, timeout=15) as db:
        db.execute(
            "INSERT INTO access_rules "
            "(name, source_type, source_id, target_type, target_id, effect, enabled) "
            "VALUES (?, 'user', ?, 'device', ?, ?, 1)",
            (f"Viewer {effect}", viewer_id, DEVICE, effect),
        )


def assign_control_role(db_path):
    with sqlite3.connect(db_path, timeout=15) as db:
        role_id = db.execute(
            "INSERT INTO control_roles (name, keyboard, clipboard, file, usb) "
            "VALUES (?, 1, 2, 1, 2)",
            ("Integration restrictions",),
        ).lastrowid
        db.execute(
            "INSERT INTO control_role_assignments (target_type, target_id, role_id) "
            "VALUES ('device', ?, ?)", (DEVICE, role_id),
        )


def verify_internal_control_api(base, key):
    request = Request(
        base + "/internal/v1/control/permissions?device_id=" + DEVICE,
        headers={"X-RustDesk-Internal-Key": key},
    )
    with urlopen(request, timeout=5) as response:
        data = json.load(response)
    if not data.get("assigned") or data.get("permissions") != PERMISSIONS:
        raise AssertionError(f"Actual API returned unexpected control permissions: {data}")


def main():
    if len(sys.argv) != 3:
        raise SystemExit(
            "Usage: test_real_api_strict_combination.py /path/to/apimain /path/to/hbbs"
        )
    api_binary, hbbs_binary = [Path(value).resolve() for value in sys.argv[1:]]
    if not api_binary.is_file() or not hbbs_binary.is_file():
        raise FileNotFoundError("Compiled API and hbbs binaries are required")
    api_source = api_binary.parents[1]
    port, hbbs_port = available_tcp_port(), find_ports()
    base = f"http://127.0.0.1:{port}"
    jwt_secret, internal_key = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    uuid_bytes, public_key_bytes = os.urandom(16), os.urandom(32)
    payload = {
        "id": DEVICE,
        "uuid": base64.b64encode(uuid_bytes).decode(),
        "pk": base64.b64encode(public_key_bytes).decode(),
    }

    with tempfile.TemporaryDirectory(prefix="rustdesk-real-strict-combination-") as directory:
        root = Path(directory)
        api_work, server_work = root / "api", root / "server"
        api_work.mkdir()
        server_work.mkdir()
        shutil.copytree(api_source / "conf", api_work / "conf")
        shutil.copytree(
            api_source / "resources", api_work / "resources",
            ignore=shutil.ignore_patterns("node_modules", ".git", "coverage"),
        )
        (api_work / "data").mkdir()
        (api_work / "runtime").mkdir()
        config_file = api_work / "conf/config.yaml"
        text = config_file.read_text(encoding="utf-8")
        standard_address = 'api-addr: "0.0.0.0:21114"'
        if standard_address not in text:
            raise AssertionError("API configuration has a different default listen address")
        config_file.write_text(
            text.replace(standard_address, f'api-addr: "127.0.0.1:{port}"'),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env.update({
            "TEST_HBBS": "no",
            "MUST_LOGIN": "Y",
            "REQUIRE_DEVICE_DEPLOYMENT": "Y",
            "RUSTDESK_API_INTERNAL_KEY": internal_key,
            "RUSTDESK_API_JWT_KEY": jwt_secret,
            "RUSTDESK_API_INTERNAL_URL": base + "/internal/v1/device/authorize",
            "RUSTDESK_API_CONNECTION_ACCESS_URL":
                base + "/internal/v1/connection/authorize",
            "RUSTDESK_API_CONTROL_ROLE_URL":
                base + "/internal/v1/control/permissions",
            "RUSTDESK_API_CONTROL_CACHE_SECONDS": "0",
        })
        processes = {}
        streams = []
        try:
            api, log = start_process(
                api_binary, ["--config", "./conf/config.yaml"],
                api_work, root / "api.log", env,
            )
            processes["api"] = api
            streams.append(log)
            wait_for_api(base, api)
            db_path = api_work / "data/rustdeskapi.db"
            _, viewer_id, admin_token, viewer_token, invalid_token = seed_sessions(
                db_path, jwt_secret,
            )
            status, response = post_json(
                base, "/api/devices/deploy", payload, token=admin_token,
            )
            if status != 200 or response.get("result") != "OK":
                raise AssertionError(f"Authenticated API deployment rejected: {status}/{response}")

            assign_control_role(db_path)
            verify_internal_control_api(base, internal_key)

            server, log = start_process(
                hbbs_binary,
                ["--bind=127.0.0.1", f"--port={hbbs_port}"],
                server_work, root / "hbbs.log", env,
            )
            processes["hbbs"] = server
            streams.append(log)
            wait_for_port(hbbs_port, server)
            if register_device(hbbs_port, "strict-unknown-device", uuid_bytes, public_key_bytes) != 8:
                raise AssertionError("Unknown device was registered while strict mode was active")

            key = (server_work / "id_ed25519.pub").read_text().strip()
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
                receiver.bind(("127.0.0.1", 0))
                receiver.settimeout(8)
                receiver.sendto(
                    raw_field(6, text_field(1, DEVICE)),
                    ("127.0.0.1", hbbs_port),
                )
                recv_registered_target(receiver, 7)
                register = (
                    text_field(1, DEVICE) + raw_field(2, uuid_bytes) +
                    raw_field(3, public_key_bytes)
                )
                receiver.sendto(
                    raw_field(15, register),
                    ("127.0.0.1", hbbs_port),
                )
                registered = recv_registered_target(receiver, 16)
                if registered.get(1, [0])[0] != 0:
                    raise AssertionError(f"API-approved device registration failed: {registered}")

                def punch(token):
                    return (
                        text_field(1, DEVICE) + integer_field(2, 2) +
                        text_field(3, key) + text_field(5, token)
                    )

                def relay(token):
                    return (
                        text_field(1, DEVICE) + text_field(2, "actual-api-relay") +
                        text_field(8, token)
                    )

                websocket_request(hbbs_port, 8, punch(admin_token))
                require_permissions(recv_registered_target(receiver, 9), 8, PERMISSIONS)

                websocket_request(hbbs_port, 18, relay(admin_token))
                require_permissions(recv_registered_target(receiver, 18), 9, PERMISSIONS)

                websocket_request(hbbs_port, 8, punch(viewer_token), denied=True)
                must_not_forward(receiver)

                set_viewer_rule(db_path, viewer_id, "allow")
                websocket_request(hbbs_port, 8, punch(viewer_token))
                require_permissions(recv_registered_target(receiver, 9), 8, PERMISSIONS)

                websocket_request(hbbs_port, 18, relay(viewer_token))
                require_permissions(recv_registered_target(receiver, 18), 9, PERMISSIONS)

                set_viewer_rule(db_path, viewer_id, "deny")
                websocket_request(hbbs_port, 8, punch(viewer_token), denied=True)
                must_not_forward(receiver)
                websocket_request(hbbs_port, 18, relay(viewer_token), denied=True)
                must_not_forward(receiver)

                websocket_request(hbbs_port, 8, punch(invalid_token), denied=True)
                must_not_forward(receiver)

                with sqlite3.connect(db_path, timeout=15) as db:
                    db.execute("DELETE FROM user_tokens WHERE token = ?", (admin_token,))
                websocket_request(hbbs_port, 8, punch(admin_token), denied=True)
                must_not_forward(receiver)

                with sqlite3.connect(db_path, timeout=15) as db:
                    db.execute(
                        "INSERT INTO user_tokens (user_id, token, expired_at) "
                        "SELECT id, ?, ? FROM users WHERE username = 'admin'",
                        (admin_token, int(time.time()) + 1800),
                    )
                websocket_request(hbbs_port, 8, punch(admin_token))
                require_permissions(recv_registered_target(receiver, 9), 8, PERMISSIONS)

                with sqlite3.connect(db_path, timeout=15) as db:
                    db.execute(
                        "UPDATE device_deployments SET status = 'revoked' WHERE device_id = ?",
                        (DEVICE,),
                    )
                if register_device(hbbs_port, DEVICE, uuid_bytes, public_key_bytes) != 3:
                    raise AssertionError("Revoked deployment remained registered")
                stop_process(api)
                websocket_request(hbbs_port, 8, punch(admin_token), denied=True)
                must_not_forward(receiver)

            print(
                "Real RustDesk API and hbbs passed strict deployment, JWT signature, "
                "session revocation, allow/deny rules, control permissions, relay "
                "requests, device revocation and API outage."
            )
        except Exception:
            for stream in streams:
                stream.flush()
            for name in ("api", "hbbs"):
                logpath = root / f"{name}.log"
                if logpath.is_file():
                    output = logpath.read_text(errors="replace")
                    filtered = "\n".join(
                        line for line in output.splitlines()
                        if "Admin Password Is:" not in line
                    )
                    print(f"\n{name} output:\n{filtered[-3500:]}", file=sys.stderr)
            raise
        finally:
            for process in processes.values():
                stop_process(process)
            for stream in streams:
                stream.close()


if __name__ == "__main__":
    main()
