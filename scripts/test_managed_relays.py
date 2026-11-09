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


def write_geo_country_files(directory, source_country):
    root = Path(directory)
    (root / "GeoLite2-Country-Locations-en.csv").write_text(
        "geoname_id,locale_code,continent_code,continent_name,country_iso_code,country_name\n"
        "1861060,en,AS,Asia,JP,Japan\n"
        '6252001,en,NA,North America,US,"United States"\n',
        encoding="utf-8",
    )
    mapped_id = "1861060" if source_country == "JP" else "6252001"
    (root / "GeoLite2-Country-Blocks-IPv4.csv").write_text(
        "network,geoname_id,registered_country_geoname_id\n"
        f"192.0.2.0/24,{mapped_id},\n"
        "198.18.0.0/16,1861060,\n",
        encoding="utf-8",
    )
    (root / "GeoLite2-Country-Blocks-IPv6.csv").write_text(
        "network,geoname_id,registered_country_geoname_id\n"
        "2001:db8:1::/48,1861060,\n",
        encoding="utf-8",
    )


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
        {"address": a_address, "priority": 10, "subnets": ["203.0.113.0/24"], "countries": ["JP"]},
        {"address": b_address, "priority": 20, "subnets": ["198.51.100.0/24"], "countries": ["US"]},
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
                write_geo_country_files(directory, source_country="US")
                env["RUSTDESK_GEOIP_CSV_DIR"] = directory
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
                        country_us = "test-geo 192.0.2.30 192.0.2.31"
                        country_jp = "test-geo 198.18.1.1 198.18.1.2"
                        until(proc, lambda:
                            a_address in console(nat_port, command_a)
                            and b_address in console(nat_port, command_b)
                            and b_address in console(nat_port, country_us)
                            and a_address in console(nat_port, country_jp))
                        if APIMock.received == 0:
                            raise AssertionError("hbbs never fetched the relay list from the API")
                        write_geo_country_files(directory, source_country="JP")
                        reply = console(nat_port, "reload-geo")
                        if "reload requested" not in reply:
                            raise AssertionError(f"GeoLite2 reload command was rejected: {reply!r}")
                        until(proc, lambda: a_address in console(nat_port, country_us))
                        relay_a.shutdown()
                        relay_a.server_close()
                        relays.remove(relay_a)
                        until(proc, lambda: b_address in console(nat_port, command_a), timeout=20)
                        APIMock.nodes = []
                        until(proc, lambda: fallback_address in console(nat_port, command_a), timeout=25)
                        print("Managed relay preferences, GeoLite2 country lookup, reload, node failover and standard fallback passed.")
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
