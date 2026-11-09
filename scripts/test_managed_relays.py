#!/usr/bin/env python3
"""Exercise hbbs relay configuration against a local OSS API and TCP relays."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import socketserver
import subprocess
import sys
import tempfile
from threading import Thread
import time

from test_runtime import find_ports


class RelayHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(1.0)
        try:
            self.request.recv(16)
        except (socket.timeout, OSError):
            pass


class RelayTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class APIMock(BaseHTTPRequestHandler):
    secret = "local-test-relay-key"
    nodes = []
    received = 0

    def do_GET(self):
        self.__class__.received += 1
        valid = (
            self.path == "/internal/v1/relay/nodes"
            and self.headers.get("X-RustDesk-Internal-Key") == self.secret
        )
        self.send_response(200 if valid else 403)
        data = json.dumps({"nodes": self.nodes} if valid else {"error": "denied"}).encode()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_):
        pass


def console(port, command):
    with socket.create_connection(("127.0.0.1", port), timeout=2) as stream:
        stream.settimeout(2)
        stream.sendall(command.encode())
        return stream.recv(4096).decode(errors="replace").strip()


def until(proc, condition, timeout=25):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if proc.poll() is not None:
            raise RuntimeError(f"hbbs exited: {proc.returncode}")
        try:
            if condition():
                return
        except (OSError, TimeoutError):
            pass
        time.sleep(0.3)
    raise TimeoutError("relay selection did not reflect the managed configuration")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: test_managed_relays.py /path/to/hbbs")
    binary = str(Path(sys.argv[1]).resolve())
    relay_a = RelayTCPServer(("127.0.0.1", 0), RelayHandler)
    relay_b = RelayTCPServer(("127.0.0.1", 0), RelayHandler)
    fallback = RelayTCPServer(("127.0.0.1", 0), RelayHandler)
    relays = [relay_a, relay_b, fallback]
    for srv in relays:
        Thread(target=srv.serve_forever, daemon=True).start()
    a_address = f"127.0.0.1:{relay_a.server_address[1]}"
    b_address = f"127.0.0.1:{relay_b.server_address[1]}"
    fallback_address = f"127.0.0.1:{fallback.server_address[1]}"
    APIMock.nodes = [
        {"address": a_address, "priority": 10, "subnets": ["203.0.113.0/24"]},
        {"address": b_address, "priority": 20, "subnets": ["198.51.100.0/24"]},
    ]
    APIMock.received = 0
    try:
        with ThreadingHTTPServer(("127.0.0.1", 0), APIMock) as api:
            Thread(target=api.serve_forever, daemon=True).start()
            port = find_ports()
            env = os.environ.copy()
            env.update({
                "TEST_HBBS": "no",
                "MUST_LOGIN": "N",
                "RUSTDESK_API_INTERNAL_KEY": APIMock.secret,
                "RUSTDESK_API_RELAY_NODES_URL": f"http://127.0.0.1:{api.server_port}/internal/v1/relay/nodes",
                "RUSTDESK_API_RELAY_SYNC_SECONDS": "10",
            })
            with tempfile.TemporaryDirectory(prefix="rustdesk-managed-relay-") as directory:
                output_path = Path(directory, "hbbs.log")
                with output_path.open("wb") as output:
                    proc = subprocess.Popen([
                        binary, "--bind=127.0.0.1", f"--port={port}",
                        f"--relay-servers={fallback_address}",
                    ], cwd=directory, env=env, stdout=output, stderr=subprocess.STDOUT)
                    try:
                        nat_port = port - 1
                        command_a = "test-geo 203.0.113.10 192.0.2.7"
                        command_b = "test-geo 198.51.100.12 192.0.2.7"
                        until(proc, lambda:
                            a_address in console(nat_port, command_a)
                            and b_address in console(nat_port, command_b))
                        if APIMock.received == 0:
                            raise AssertionError("hbbs never fetched the relay list from the API")
                        APIMock.nodes = []
                        until(proc, lambda: fallback_address in console(nat_port, command_a), timeout=25)
                        print("Managed relay preferences, API polling and standard fallback verified.")
                    except Exception:
                        output.flush()
                        print(output_path.read_text(errors="replace")[-5000:], file=sys.stderr)
                        raise
                    finally:
                        if proc.poll() is None:
                            proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=5)
    finally:
        for srv in relays:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    main()
