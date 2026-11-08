#!/usr/bin/env python3
"""Run hbbs with a temporary companion API and verify managed registration."""
import base64
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
from test_webrtc_rendezvous import parse_fields, raw_field, text_field


class AuthorizationHandler(BaseHTTPRequestHandler):
    results = {}
    received = []
    shared_key = "test-internal-device-key"

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        data = json.loads(self.rfile.read(length))
        self.received.append(data)
        if self.path != "/internal/v1/device/authorize" or self.headers.get("X-RustDesk-Internal-Key") != self.shared_key:
            self.send_response(403)
            result = "DENIED"
        else:
            self.send_response(200)
            result = self.results.get(data["id"], "NOT_DEPLOYED")
        body = json.dumps({"result": result}).encode()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def register_device(port, device_id, uuid, pk):
    payload = text_field(1, device_id) + raw_field(2, uuid) + raw_field(3, pk)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as conn:
        conn.settimeout(6)
        conn.sendto(raw_field(15, payload), ("127.0.0.1", port))
        response, _ = conn.recvfrom(4096)
    outer = parse_fields(response)
    if 16 not in outer:
        raise AssertionError(f"Missing public-key registration reply: {outer!r}")
    result = parse_fields(outer[16][0])
    return result.get(1, [0])[0]


def wait_for_port(port, process):
    until = time.monotonic() + 20
    while time.monotonic() < until:
        if process.poll() is not None:
            raise RuntimeError(f"hbbs unexpectedly exited: {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.15)
    raise TimeoutError("hbbs did not start")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: test_device_deployment.py /path/to/hbbs")
    binary = str(Path(sys.argv[1]).resolve())
    port = find_ports()
    with ThreadingHTTPServer(("127.0.0.1", 0), AuthorizationHandler) as api:
        thread = Thread(target=api.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory(prefix="rustdesk-deployment-") as directory:
            logpath = Path(directory, "hbbs.log")
            env = os.environ.copy()
            env.update({
                "TEST_HBBS": "no",
                "MUST_LOGIN": "N",
                "REQUIRE_DEVICE_DEPLOYMENT": "Y",
                "RUSTDESK_API_INTERNAL_KEY": AuthorizationHandler.shared_key,
                "RUSTDESK_API_INTERNAL_URL": f"http://127.0.0.1:{api.server_port}/internal/v1/device/authorize",
            })
            with logpath.open("wb") as log:
                proc = subprocess.Popen(
                    [binary, "--bind=127.0.0.1", f"--port={port}"],
                    cwd=directory, env=env, stdout=log, stderr=subprocess.STDOUT,
                )
                try:
                    wait_for_port(port, proc)
                    uuid, pk = os.urandom(16), os.urandom(32)
                    unknown = "deploy-missing-001"
                    allowed = "deploy-approved-001"
                    taken = "deploy-conflict-001"
                    AuthorizationHandler.results = {
                        allowed: "OK",
                        taken: "ID_TAKEN",
                    }
                    if register_device(port, unknown, uuid, pk) != 8:
                        raise AssertionError("Unapproved device registration was not rejected")
                    if register_device(port, allowed, uuid, pk) != 0:
                        raise AssertionError("Approved device registration did not succeed")
                    if register_device(port, taken, uuid, pk) != 3:
                        raise AssertionError("Conflicting device ID was not rejected")
                    ids = [item["id"] for item in AuthorizationHandler.received]
                    if not {unknown, allowed, taken}.issubset(ids):
                        raise AssertionError(f"API missed registration requests: {ids!r}")
                    request = next(item for item in AuthorizationHandler.received if item["id"] == allowed)
                    if base64.b64decode(request["uuid"]) != uuid or base64.b64decode(request["pk"]) != pk:
                        raise AssertionError("Device identity bytes were modified during API validation")
                    print("Actual hbbs registration approval, rejection and API calls passed.")
                except Exception:
                    log.flush()
                    print(logpath.read_text(errors="replace")[-5000:], file=sys.stderr)
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
