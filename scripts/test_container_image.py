#!/usr/bin/env python3
"""Check the combined RustDesk API, rendezvous and relay Docker image."""
import base64
import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def exposed_port(name, container_port):
    addresses = docker("port", name, f"{container_port}/tcp").splitlines()
    if not addresses:
        raise RuntimeError(f"Container port {container_port}/tcp is not published")
    return int(addresses[0].rsplit(":", 1)[1])


def check_tcp(port):
    with socket.create_connection(("127.0.0.1", port), timeout=1):
        return


def check_websocket(port):
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        "GET / HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Connection: Upgrade\r\n"
        "Upgrade: websocket\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    ).encode("ascii")
    with socket.create_connection(("127.0.0.1", port), timeout=5) as conn:
        conn.settimeout(5)
        conn.sendall(request)
        response = conn.recv(4096)
        if b"101 Switching Protocols" not in response:
            raise AssertionError(f"WebSocket upgrade failed: {response[:250]!r}")


def fetch_html(port, path):
    url = f"http://127.0.0.1:{port}{path}"
    with urllib.request.urlopen(url, timeout=3) as response:
        body = response.read(16384).decode("utf-8", "replace")
        if response.status != 200 or "<html" not in body.lower():
            raise AssertionError(f"{path} did not return an HTML document")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: test_container_image.py ghcr.io/owner/image:tag-arch")
    image = sys.argv[1]
    name = "rustdesk-image-test-" + uuid.uuid4().hex[:10]
    started = False
    try:
        docker(
            "run", "--rm", "-d", "-P", "--name", name,
            "-e", "MUST_LOGIN=N",
            "-e", "ENCRYPTED_ONLY=0",
            "-e", "RUSTDESK_API_JWT_KEY=local-integration-test-secret-very-long",
            "-e", "RELAY=127.0.0.1:21117",
            image
        )
        started = True
        deadline = time.monotonic() + 120
        last_failure = None
        while time.monotonic() < deadline:
            if docker("inspect", "-f", "{{.State.Running}}", name) != "true":
                raise RuntimeError("Combined RustDesk Docker container stopped during startup")
            try:
                ports = {
                    number: exposed_port(name, number)
                    for number in (21114, 21116, 21117, 21118, 21119)
                }
                for number in (21116, 21117, 21118, 21119):
                    check_tcp(ports[number])
                fetch_html(ports[21114], "/_admin/")
                fetch_html(ports[21114], "/webclient2/")
                check_websocket(ports[21118])
                check_websocket(ports[21119])
                print("Combined image passed API, WebClient v2, hbbs, hbbr and WebSocket checks.")
                return
            except (OSError, ValueError, AssertionError) as exc:
                last_failure = exc
                time.sleep(1)
        raise TimeoutError(f"Combined image was not ready within 120 seconds: {last_failure}")
    except Exception:
        if started:
            try:
                print("Container output:\n" + docker("logs", "--tail", "140", name), file=sys.stderr)
            except subprocess.CalledProcessError:
                pass
        raise
    finally:
        if started:
            subprocess.run(["docker", "rm", "-fv", name], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)


if __name__ == "__main__":
    main()
