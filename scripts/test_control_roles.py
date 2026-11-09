#!/usr/bin/env python3
"""Verify control roles in signaling messages from a real hbbs process."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from threading import Thread
import time

from test_runtime import find_ports
from test_webrtc_rendezvous import (
    integer_field, parse_fields, raw_field, send_framed, text_field,
    ws_send_binary, ws_upgrade,
)


class ControlAPI(BaseHTTPRequestHandler):
    key = "temporary-control-role-internal-key"
    allow = True
    requested_ids = []
    bitmap = (1 << 0) | (2 << 4) | (1 << 6) | (2 << 26)

    def do_GET(self):
        from urllib.parse import parse_qs, urlparse
        url = urlparse(self.path)
        ids = parse_qs(url.query).get("device_id", [])
        valid = (
            url.path == "/internal/v1/control/permissions"
            and self.headers.get("X-RustDesk-Internal-Key") == self.key
            and ids == ["control-test-device"]
        )
        self.__class__.requested_ids.extend(ids)
        self.send_response(200 if valid else 403)
        data = json.dumps({
            "assigned": self.allow, "permissions": self.bitmap if self.allow else 0,
            "source": "device" if self.allow else "",
        } if valid else {"error": "access denied"}).encode()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


def get_target_message(receiver, tag):
    for _ in range(8):
        data, _ = receiver.recvfrom(65536)
        outer = parse_fields(data)
        if tag in outer:
            return parse_fields(outer[tag][0])
    raise AssertionError(f"Expected forwarded message with tag {tag}")


def require_permissions(message, field, expected):
    if expected is None:
        if field in message:
            raise AssertionError(f"Unassigned role unexpectedly supplied permissions: {message}")
        return
    container = message.get(field)
    if not container:
        raise AssertionError(f"Native control permissions absent: {message}")
    value = parse_fields(container[0]).get(1, [0])[0]
    if value != expected:
        raise AssertionError(f"Wrong native control bitmap: {value}, expected {expected}")


def until(condition, process, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"hbbs exited with status {process.returncode}")
        try:
            if condition():
                return
        except (ConnectionError, OSError):
            pass
        time.sleep(0.2)
    raise TimeoutError("hbbs did not start")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: test_control_roles.py /path/to/hbbs")
    binary = str(Path(sys.argv[1]).resolve())
    with ThreadingHTTPServer(("127.0.0.1", 0), ControlAPI) as api:
        Thread(target=api.serve_forever, daemon=True).start()
        ControlAPI.allow = True
        ControlAPI.requested_ids = []
        port = find_ports()
        with tempfile.TemporaryDirectory(prefix="rustdesk-control-roles-") as directory:
            log_path = Path(directory, "hbbs.log")
            env = os.environ.copy()
            env.update({
                "TEST_HBBS": "no",
                "MUST_LOGIN": "N",
                "RUSTDESK_API_INTERNAL_KEY": ControlAPI.key,
                "RUSTDESK_API_CONTROL_ROLE_URL":
                    f"http://127.0.0.1:{api.server_port}/internal/v1/control/permissions",
                "RUSTDESK_API_CONTROL_CACHE_SECONDS": "0",
            })
            with log_path.open("wb") as log:
                process = subprocess.Popen([
                    binary, "--bind=127.0.0.1", f"--port={port}"
                ], cwd=directory, env=env, stdout=log, stderr=subprocess.STDOUT)
                try:
                    until(lambda: socket.create_connection(
                        ("127.0.0.1", port), timeout=0.5).close() is None,
                        process)
                    key = Path(directory, "id_ed25519.pub").read_text().strip()
                    target = "control-test-device"
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
                        receiver.bind(("127.0.0.1", 0))
                        receiver.settimeout(8)
                        receiver.sendto(raw_field(6, text_field(1, target)),
                            ("127.0.0.1", port))
                        get_target_message(receiver, 7)
                        register_pk = (
                            text_field(1, target) + raw_field(2, os.urandom(16))
                            + raw_field(3, os.urandom(32))
                        )
                        receiver.sendto(raw_field(15, register_pk),
                            ("127.0.0.1", port))
                        get_target_message(receiver, 16)

                        with ws_upgrade(port + 2) as caller:
                            punch = (
                                text_field(1, target)
                                + integer_field(2, 2)
                                + text_field(3, key)
                            )
                            ws_send_binary(caller, raw_field(8, punch))
                            forwarded = get_target_message(receiver, 9)
                            require_permissions(forwarded, 8, ControlAPI.bitmap)

                        with ws_upgrade(port + 2) as relay:
                            request = (
                                text_field(1, target)
                                + text_field(2, "control-role-request")
                            )
                            ws_send_binary(relay, raw_field(18, request))
                            forwarded = get_target_message(receiver, 18)
                            require_permissions(forwarded, 9, ControlAPI.bitmap)

                        # The native TCP path forwards local address requests
                        # when both ends are on the same network.
                        with socket.create_connection(("127.0.0.1", port), timeout=8) as local:
                            local.settimeout(8)
                            send_framed(local, raw_field(8, text_field(1, target)
                                + integer_field(2, 2) + text_field(3, key)))
                            forwarded = get_target_message(receiver, 12)
                            require_permissions(forwarded, 4, ControlAPI.bitmap)

                        ControlAPI.allow = False
                        with ws_upgrade(port + 2) as caller:
                            punch = (
                                text_field(1, target)
                                + integer_field(2, 2)
                                + text_field(3, key)
                            )
                            ws_send_binary(caller, raw_field(8, punch))
                            forwarded = get_target_message(receiver, 9)
                            require_permissions(forwarded, 8, None)

                        if ControlAPI.requested_ids.count(target) < 4:
                            raise AssertionError(
                                f"Control role API was not queried for every test: {ControlAPI.requested_ids}"
                            )
                    print("Native control role signaling verified for PunchHole, RequestRelay and FetchLocalAddr.")
                except Exception:
                    log.flush()
                    print(log_path.read_text(errors="replace")[-6000:], file=sys.stderr)
                    raise
                finally:
                    if process.poll() is None:
                        process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)


if __name__ == "__main__":
    main()
