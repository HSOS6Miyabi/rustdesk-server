#!/usr/bin/env python3
"""Exercise strict deployment, JWT login, connection rules and control roles in one real hbbs."""
import base64
import hashlib
import hmac
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
from urllib.parse import parse_qs, urlparse

from test_connection_access import (
    must_not_forward, recv_registered_target, websocket_request,
)
from test_control_roles import require_permissions
from test_device_deployment import register_device, wait_for_port
from test_runtime import find_ports
from test_webrtc_rendezvous import (
    integer_field, parse_fields, raw_field, text_field, ws_send_binary,
    ws_upgrade,
)


SECRET = "strict-combination-jwt-key-local-2026"
INTERNAL_KEY = "strict-combination-api-key-local-2026"
DEVICE = "combined-test-device-001"
UUID = os.urandom(16)
PK = os.urandom(32)
PERMISSIONS = (1 << 0) | (2 << 4) | (1 << 6) | (2 << 26)


def jwt(user_id):
    def encode(value):
        payload = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
    message = encode({"alg": "HS256", "typ": "JWT"}) + "." + encode({
        "user_id": user_id, "exp": int(time.time()) + 3600,
    })
    signature = base64.urlsafe_b64encode(
        hmac.new(SECRET.encode(), message.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return message + "." + signature


VALID_JWT = jwt(11)
DENIED_JWT = jwt(12)


class IntegrationAPI(BaseHTTPRequestHandler):
    requests = []
    deployment_enabled = True
    unavailable = False

    def send_data(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        return self.headers.get("X-RustDesk-Internal-Key") == INTERNAL_KEY

    def do_POST(self):
        if not self.authorized():
            self.send_data(403, {"error": "invalid internal key"})
            return
        if self.unavailable:
            self.send_data(503, {"error": "API unavailable"})
            return
        length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(length))
        self.__class__.requests.append((self.path, data))
        if self.path == "/internal/v1/device/authorize":
            if data.get("id") != DEVICE:
                self.send_data(200, {"result": "NOT_DEPLOYED"})
            elif not self.deployment_enabled or (
                data.get("uuid") != base64.b64encode(UUID).decode() or
                data.get("pk") != base64.b64encode(PK).decode()
            ):
                self.send_data(200, {"result": "ID_TAKEN"})
            else:
                self.send_data(200, {"result": "OK"})
        elif self.path == "/internal/v1/connection/authorize":
            token = data.get("token")
            permitted = (
                data.get("device_id") == DEVICE and token in
                {VALID_JWT, "invalid-jwt-that-mock-api-allows"}
            )
            self.send_data(200, {"allow": permitted, "reason": "rule" if permitted else "denied"})
        else:
            self.send_data(404, {"error": "invalid route"})

    def do_GET(self):
        parsed = urlparse(self.path)
        device_ids = parse_qs(parsed.query).get("device_id", [])
        if not self.authorized() or parsed.path != "/internal/v1/control/permissions" or device_ids != [DEVICE]:
            self.send_data(403, {"error": "denied"})
            return
        self.send_data(200, {
            "assigned": True, "permissions": PERMISSIONS, "source": "device",
        })

    def log_message(self, *_):
        pass


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: test_strict_combination.py /path/to/hbbs")
    binary = str(Path(sys.argv[1]).resolve())
    with ThreadingHTTPServer(("127.0.0.1", 0), IntegrationAPI) as api:
        Thread(target=api.serve_forever, daemon=True).start()
        IntegrationAPI.requests = []
        IntegrationAPI.deployment_enabled = True
        IntegrationAPI.unavailable = False
        port = find_ports()
        root = f"http://127.0.0.1:{api.server_port}"
        env = os.environ.copy()
        env.update({
            "TEST_HBBS": "no",
            "MUST_LOGIN": "Y",
            "RUSTDESK_API_JWT_KEY": SECRET,
            "REQUIRE_DEVICE_DEPLOYMENT": "Y",
            "RUSTDESK_API_INTERNAL_KEY": INTERNAL_KEY,
            "RUSTDESK_API_INTERNAL_URL": root + "/internal/v1/device/authorize",
            "RUSTDESK_API_CONNECTION_ACCESS_URL": root + "/internal/v1/connection/authorize",
            "RUSTDESK_API_CONTROL_ROLE_URL": root + "/internal/v1/control/permissions",
            "RUSTDESK_API_CONTROL_CACHE_SECONDS": "0",
        })
        with tempfile.TemporaryDirectory(prefix="rustdesk-combined-authorization-") as folder:
            logfile = Path(folder, "hbbs.log")
            with logfile.open("wb") as log:
                proc = subprocess.Popen(
                    [binary, "--bind=127.0.0.1", f"--port={port}"],
                    cwd=folder, env=env, stdout=log, stderr=subprocess.STDOUT,
                )
                try:
                    wait_for_port(port, proc)
                    key = Path(folder, "id_ed25519.pub").read_text().strip()
                    if register_device(port, "not-yet-deployed-001", UUID, PK) != 8:
                        raise AssertionError("unregistered device was accepted")
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
                        receiver.bind(("127.0.0.1", 0))
                        receiver.settimeout(8)
                        receiver.sendto(raw_field(6, text_field(1, DEVICE)), ("127.0.0.1", port))
                        recv_registered_target(receiver, 7)
                        register = text_field(1, DEVICE) + raw_field(2, UUID) + raw_field(3, PK)
                        receiver.sendto(raw_field(15, register), ("127.0.0.1", port))
                        registered = recv_registered_target(receiver, 16)
                        if registered.get(1, [0])[0] != 0:
                            raise AssertionError(f"approved device was rejected: {registered}")

                        def punch(token):
                            return (
                                text_field(1, DEVICE) + integer_field(2, 2) +
                                text_field(3, key) + text_field(5, token)
                            )

                        websocket_request(port, 8, punch(VALID_JWT))
                        forwarded = recv_registered_target(receiver, 9)
                        require_permissions(forwarded, 8, PERMISSIONS)

                        websocket_request(port, 8, punch("invalid-jwt-that-mock-api-allows"), denied=True)
                        must_not_forward(receiver)

                        websocket_request(port, 8, punch(DENIED_JWT), denied=True)
                        must_not_forward(receiver)

                        def relay(token):
                            return (
                                text_field(1, DEVICE) +
                                text_field(2, "combined-access-test-relay") +
                                text_field(8, token)
                            )

                        websocket_request(port, 18, relay(VALID_JWT))
                        forwarded = recv_registered_target(receiver, 18)
                        require_permissions(forwarded, 9, PERMISSIONS)

                        websocket_request(port, 18, relay("invalid-jwt-that-mock-api-allows"), denied=True)
                        must_not_forward(receiver)
                        websocket_request(port, 18, relay(DENIED_JWT), denied=True)
                        must_not_forward(receiver)

                        IntegrationAPI.unavailable = True
                        websocket_request(port, 8, punch(VALID_JWT), denied=True)
                        must_not_forward(receiver)
                        IntegrationAPI.unavailable = False

                    IntegrationAPI.deployment_enabled = False
                    if register_device(port, DEVICE, UUID, PK) != 3:
                        raise AssertionError("revoked device was allowed to re-register")
                    paths = [item[0] for item in IntegrationAPI.requests]
                    if "/internal/v1/device/authorize" not in paths or "/internal/v1/connection/authorize" not in paths:
                        raise AssertionError("combined authorization did not consult both API endpoints")
                    print("Strict deployment, JWT, connection permission and native control role checks passed.")
                    print("The live hbbs rejected invalid JWT, blocked users, revoked devices and API outage.")
                except Exception:
                    log.flush()
                    print(logfile.read_text(errors="replace")[-5500:], file=sys.stderr)
                    raise
                finally:
                    if proc.poll() is None:
                        proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)


if __name__ == "__main__":
    main()
