#!/usr/bin/env python3
"""Check deployed-device registration against real RustDesk API and hbbs processes."""

import base64
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from test_device_deployment import register_device, wait_for_port
from test_native_stack import available_tcp_port, start_process, stop_process
from test_runtime import find_ports


def post_json(base, path, payload, token=None, internal_key=None):
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    if internal_key is not None:
        headers["X-RustDesk-Internal-Key"] = internal_key
    request = Request(
        base + path, data=json.dumps(payload).encode("utf-8"),
        headers=headers, method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        with error:
            return error.code, json.load(error)


def require_result(base, path, payload, expected_status, expected_result,
                   token=None, internal_key=None):
    status, response = post_json(base, path, payload, token, internal_key)
    if status != expected_status or response.get("result") != expected_result:
        raise AssertionError(
            f"{path}: expected HTTP {expected_status}/{expected_result}, "
            f"received HTTP {status}/{response}"
        )


def wait_for_api(base, process):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("RustDesk API exited while starting")
        try:
            with urlopen(base + "/_admin/", timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.25)
    raise TimeoutError("RustDesk API did not become ready")


def create_login_session(db_path):
    # The token is inserted into an isolated, newly migrated SQLite database.
    # This exercises the real session authorization middleware without any external credentials.
    token = secrets.token_urlsafe(36)
    with sqlite3.connect(db_path, timeout=15) as db:
        db.execute("PRAGMA busy_timeout = 10000")
        row = db.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
        version = db.execute(
            "SELECT version FROM versions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None or version is None or version[0] < 282:
            raise AssertionError("API initialization and migrations did not finish")
        admin_id = row[0]
        db.execute(
            "INSERT INTO user_tokens (user_id, token, expired_at) VALUES (?, ?, ?)",
            (admin_id, token, int(time.time()) + 1800),
        )
    return admin_id, token


def update_approval(db_path, device_id, status):
    with sqlite3.connect(db_path, timeout=15) as db:
        result = db.execute(
            "UPDATE device_deployments SET status = ? WHERE device_id = ?",
            (status, device_id),
        )
        if result.rowcount != 1:
            raise AssertionError("Deployment record was not saved")
    return status


def check_saved_deployment(db_path, device_id, uuid, public_key, owner_id):
    with sqlite3.connect(db_path, timeout=15) as db:
        row = db.execute(
            "SELECT uuid, public_key, owner_user_id, status "
            "FROM device_deployments WHERE device_id = ?", (device_id,),
        ).fetchone()
        if row != (uuid, public_key, owner_id, "approved"):
            raise AssertionError("API saved a different deployment identity or owner")


def main():
    if len(sys.argv) != 3:
        raise SystemExit(
            "Usage: test_real_api_registration.py /path/to/apimain /path/to/hbbs"
        )
    api_binary, hbbs_binary = [Path(value).resolve() for value in sys.argv[1:]]
    for binary in (api_binary, hbbs_binary):
        if not binary.is_file():
            raise FileNotFoundError(binary)
    api_source = api_binary.parents[1]
    if not (api_source / "conf/config.yaml").is_file():
        raise FileNotFoundError("API source configuration is missing")
    api_port = available_tcp_port()
    hbbs_port = find_ports()
    key = secrets.token_urlsafe(32)
    device_id = "real-api-device-001"
    unknown_id = "real-api-unknown-001"
    uuid_bytes, pk_bytes = os.urandom(16), os.urandom(32)
    uuid, public_key = (
        base64.b64encode(uuid_bytes).decode(),
        base64.b64encode(pk_bytes).decode(),
    )
    identity = {"id": device_id, "uuid": uuid, "pk": public_key}
    base = f"http://127.0.0.1:{api_port}"

    with tempfile.TemporaryDirectory(prefix="rustdesk-real-api-integration-") as directory:
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
        config_path = api_work / "conf/config.yaml"
        config = config_path.read_text(encoding="utf-8")
        original = 'api-addr: "0.0.0.0:21114"'
        if original not in config:
            raise AssertionError("API configuration no longer has its standard listen address")
        config_path.write_text(
            config.replace(original, f'api-addr: "127.0.0.1:{api_port}"'),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env.update({
            "REQUIRE_DEVICE_DEPLOYMENT": "Y",
            "RUSTDESK_API_INTERNAL_KEY": key,
            "RUSTDESK_API_INTERNAL_URL": base + "/internal/v1/device/authorize",
            "MUST_LOGIN": "N",
            "TEST_HBBS": "no",
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
            database = api_work / "data/rustdeskapi.db"
            owner_id, token = create_login_session(database)

            server, log = start_process(
                hbbs_binary,
                ["--bind=127.0.0.1", f"--port={hbbs_port}"],
                server_work, root / "hbbs.log", env,
            )
            processes["hbbs"] = server
            streams.append(log)
            wait_for_port(hbbs_port, server)
            if register_device(hbbs_port, unknown_id, uuid_bytes, pk_bytes) != 8:
                raise AssertionError("Unknown device was allowed to register")
            require_result(base, "/internal/v1/device/authorize", identity, 403,
                           "DENIED", internal_key="incorrect-test-key")
            require_result(base, "/internal/v1/device/authorize", identity, 200,
                           "NOT_DEPLOYED", internal_key=key)
            status, rejected = post_json(
                base, "/api/devices/deploy", identity, token="invalid-test-token",
            )
            if status != 401 or rejected.get("error") != "Unauthorized":
                raise AssertionError("Deployment endpoint accepted an invalid access token")
            require_result(base, "/api/devices/deploy", identity, 200,
                           "OK", token=token)
            check_saved_deployment(database, device_id, uuid, public_key, owner_id)
            require_result(base, "/api/devices/deploy", identity, 200,
                           "OK", token=token)
            require_result(base, "/internal/v1/device/authorize", identity, 200,
                           "OK", internal_key=key)
            if register_device(hbbs_port, device_id, uuid_bytes, pk_bytes) != 0:
                raise AssertionError("Approved device registration was rejected")

            conflicting = dict(identity, pk=base64.b64encode(os.urandom(32)).decode())
            require_result(base, "/api/devices/deploy", conflicting, 200,
                           "ID_TAKEN", token=token)
            require_result(base, "/internal/v1/device/authorize", conflicting, 200,
                           "ID_TAKEN", internal_key=key)
            if register_device(hbbs_port, device_id, uuid_bytes, os.urandom(32)) != 3:
                raise AssertionError("Registration accepted a conflicting public key")

            update_approval(database, device_id, "revoked")
            require_result(base, "/api/devices/deploy", identity, 200,
                           "ID_TAKEN", token=token)
            require_result(base, "/internal/v1/device/authorize", identity, 200,
                           "ID_TAKEN", internal_key=key)
            if register_device(hbbs_port, device_id, uuid_bytes, pk_bytes) != 3:
                raise AssertionError("Revoked device registered again")
            update_approval(database, device_id, "approved")
            if register_device(hbbs_port, device_id, uuid_bytes, pk_bytes) != 0:
                raise AssertionError("Reapproved device failed to register")

            stop_process(api)
            if register_device(hbbs_port, device_id, uuid_bytes, pk_bytes) == 0:
                raise AssertionError("Device registration succeeded while API was offline")
            print(
                "Real API and hbbs passed device authorization, authenticated deployment, "
                "duplicate requests, identity conflict, revocation, reapproval and API outage."
            )
        except Exception:
            for stream in streams:
                stream.flush()
            for name in ("api", "hbbs"):
                logfile = root / f"{name}.log"
                if logfile.is_file():
                    output = logfile.read_text(errors="replace")
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
