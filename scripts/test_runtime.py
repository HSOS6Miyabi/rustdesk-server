#!/usr/bin/env python3
"""Exercise the running RustDesk rendezvous and relay listeners."""
import base64
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time


def open_port(port, socktype=socket.SOCK_STREAM):
    sock = socket.socket(socket.AF_INET, socktype)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    return sock


def find_ports():
    for base in range(40116, 50116, 11):
        sockets = []
        try:
            sockets = [open_port(base + shift) for shift in (-1, 0, 1, 2, 3)]
            sockets.append(open_port(base, socket.SOCK_DGRAM))
            return base
        except OSError:
            continue
        finally:
            for sock in sockets:
                sock.close()
    raise RuntimeError("No available port range for RustDesk integration test")


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
    with socket.create_connection(("127.0.0.1", port), timeout=3) as conn:
        conn.settimeout(3)
        conn.sendall(request)
        response = conn.recv(4096)
        if b"101 Switching Protocols" not in response:
            raise AssertionError(f"WebSocket port {port} did not accept upgrade: {response[:250]!r}")


def check_udp_rendezvous(port):
    peer_id = b"runtime-test-abcdef"
    register = bytes([0x0A, len(peer_id)]) + peer_id
    wire = bytes([0x32, len(register)]) + register
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as conn:
        conn.settimeout(3)
        conn.sendto(wire, ("127.0.0.1", port))
        response, _ = conn.recvfrom(4096)
    if not response or response[0] != 0x3A:
        raise AssertionError(f"Unexpected UDP registration response: {response[:30]!r}")


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: test_runtime.py /path/to/hbbs /path/to/hbbr")
    hbbs, hbbr = [str(pathlib.Path(item).resolve()) for item in sys.argv[1:]]
    base = find_ports()
    with tempfile.TemporaryDirectory(prefix="rustdesk-runtime-") as work:
        workpath = pathlib.Path(work)
        env = os.environ.copy()
        env["TEST_HBBS"] = "no"
        env["MUST_LOGIN"] = "N"
        processes = []
        logs = []
        try:
            for name, binary, port in (
                ("hbbs", hbbs, base),
                ("hbbr", hbbr, base + 1),
            ):
                log = (workpath / f"{name}.log").open("wb")
                logs.append(log)
                proc = subprocess.Popen(
                    [binary, "--bind=127.0.0.1", f"--port={port}"],
                    cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT,
                )
                processes.append((name, proc))
            ports = [base - 1, base, base + 1, base + 2, base + 3]
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                for name, proc in processes:
                    if proc.poll() is not None:
                        raise RuntimeError(f"{name} exited with code {proc.returncode}")
                try:
                    for port in ports:
                        check_tcp(port)
                    break
                except OSError:
                    time.sleep(0.2)
            else:
                raise TimeoutError("RustDesk listeners were not available within 30 seconds")
            check_websocket(base + 2)
            check_websocket(base + 3)
            check_udp_rendezvous(base)
            print("Both servers started; TCP, WebSocket and UDP registration tests passed.")
        except Exception:
            for stream in logs:
                stream.flush()
            for name, _ in processes:
                logpath = workpath / f"{name}.log"
                if logpath.exists():
                    print(f"\n{name} output:\n{logpath.read_text(errors='replace')[-5000:]}", file=sys.stderr)
            raise
        finally:
            for _, proc in processes:
                if proc.poll() is None:
                    proc.terminate()
            for _, proc in processes:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            for stream in logs:
                stream.close()


if __name__ == "__main__":
    main()
