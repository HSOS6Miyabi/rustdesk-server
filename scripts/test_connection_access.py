#!/usr/bin/env python3
"""Check optional connection authorization using a real running hbbs."""
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
    integer_field, parse_fields, raw_field, text_field, ws_send_binary,
    ws_upgrade, ws_recv_binary,
)


class Authorizer(BaseHTTPRequestHandler):
    secret = "test-only-connection-auth-secret"
    requests = []
    unavailable = False

    def do_POST(self):
        size = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(size).decode())
        self.__class__.requests.append({
            "path": self.path, "device_id": data.get("device_id"),
            "token": data.get("token"),
            "key": self.headers.get("X-RustDesk-Internal-Key"),
        })
        if self.unavailable:
            self.send_response(503)
            payload = b'{"error":"API unavailable"}'
        elif self.path != "/internal/v1/connection/authorize" or                 self.headers.get("X-RustDesk-Internal-Key") != self.secret:
            self.send_response(403)
            payload = b'{"error":"denied"}'
        else:
            self.send_response(200)
            allowed = (
                data.get("device_id") == "access-test-device"
                and data.get("token") == "permitted-account-session"
            )
            payload = json.dumps({
                "allow": allowed, "reason": "matching_allow" if allowed else "login_required"
            }).encode()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_):
        pass


def recv_registered_target(sock, wanted):
    for _ in range(6):
        raw, _ = sock.recvfrom(65536)
        msg = parse_fields(raw)
        if wanted in msg:
            return parse_fields(msg[wanted][0])
    raise AssertionError(f"expected forwarding message {wanted}")


def must_not_forward(sock):
    old = sock.gettimeout()
    sock.settimeout(0.55)
    try:
        try:
            value, _ = sock.recvfrom(65536)
        except socket.timeout:
            return
        raise AssertionError(f"unauthorized signaling was forwarded: {parse_fields(value)}")
    finally:
        sock.settimeout(old)


def websocket_request(port, message_type, body, denied=False):
    with ws_upgrade(port + 2) as caller:
        ws_send_binary(caller, raw_field(message_type, body))
        if denied and message_type == 8:
            try:
                answer = parse_fields(ws_recv_binary(caller))
                if 9 in answer or 12 in answer or 18 in answer:
                    raise AssertionError("server forwarded a denied punch request")
                if 11 not in answer:
                    raise AssertionError(f"server response has no connection refusal: {answer}")
            except (socket.timeout, EOFError):
                # No forwarding is also checked directly at the target.
                pass
        elif denied and message_type == 18:
            caller.settimeout(0.7)
            try:
                value=ws_recv_binary(caller)
                if 18 in parse_fields(value):
                    raise AssertionError("relay request was forwarded despite denial")
            except (socket.timeout, EOFError, ConnectionResetError):
                pass


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: test_connection_access.py /path/to/hbbs")
    hbbs = str(Path(sys.argv[1]).resolve())
    with ThreadingHTTPServer(("127.0.0.1", 0), Authorizer) as mock:
        Thread(target=mock.serve_forever, daemon=True).start()
        Authorizer.requests = []
        Authorizer.unavailable = False
        port = find_ports()
        env = os.environ.copy()
        env.update({
            "TEST_HBBS": "no", "MUST_LOGIN": "N",
            "RUSTDESK_API_CONNECTION_ACCESS_URL":
                f"http://127.0.0.1:{mock.server_port}/internal/v1/connection/authorize",
            "RUSTDESK_API_INTERNAL_KEY": Authorizer.secret,
        })
        with tempfile.TemporaryDirectory(prefix="rustdesk-access-check-") as tmp:
            log_path=Path(tmp,"hbbs.log")
            with log_path.open("wb") as log:
                proc=subprocess.Popen([
                    hbbs,"--bind=127.0.0.1",f"--port={port}"
                ],cwd=tmp,env=env,stdout=log,stderr=subprocess.STDOUT)
                try:
                    deadline=time.monotonic()+20
                    while True:
                        if proc.poll() is not None:
                            raise RuntimeError(f"hbbs exited with code {proc.returncode}")
                        if Path(tmp,"id_ed25519.pub").exists():
                            try:
                                with socket.create_connection(("127.0.0.1",port),timeout=0.25):
                                    break
                            except OSError:
                                pass
                        if time.monotonic()>deadline:
                            raise TimeoutError("hbbs did not start")
                        time.sleep(0.2)
                    key=Path(tmp,"id_ed25519.pub").read_text().strip()
                    target="access-test-device"
                    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as receiver:
                        receiver.bind(("127.0.0.1",0))
                        receiver.settimeout(6)
                        receiver.sendto(raw_field(6,text_field(1,target)),("127.0.0.1",port))
                        recv_registered_target(receiver,7)
                        pk=(text_field(1,target)+raw_field(2,os.urandom(16))+
                            raw_field(3,os.urandom(32)))
                        receiver.sendto(raw_field(15,pk),("127.0.0.1",port))
                        recv_registered_target(receiver,16)

                        def punch(token):
                            return (text_field(1,target)+integer_field(2,2)+
                                text_field(3,key)+text_field(5,token))

                        websocket_request(port,8,punch("permitted-account-session"))
                        recv_registered_target(receiver,9)

                        websocket_request(port,8,punch("not-permitted"),denied=True)
                        must_not_forward(receiver)
                        websocket_request(port,8,punch(""),denied=True)
                        must_not_forward(receiver)

                        def relay(token):
                            return text_field(1,target)+text_field(2,"access-test-relay")+text_field(8,token)

                        websocket_request(port,18,relay("permitted-account-session"))
                        recv_registered_target(receiver,18)

                        websocket_request(port,18,relay("invalid-account"),denied=True)
                        must_not_forward(receiver)

                        Authorizer.unavailable=True
                        websocket_request(port,8,punch("permitted-account-session"),denied=True)
                        must_not_forward(receiver)

                    seen={(x["token"],x["device_id"]) for x in Authorizer.requests}
                    if ("permitted-account-session",target) not in seen or ("not-permitted",target) not in seen:
                        raise AssertionError("strict access API did not receive account sessions")
                    if not all(x["key"]==Authorizer.secret for x in Authorizer.requests):
                        raise AssertionError("internal authorization key was missing")
                    print("Strict connection access, relay checks and API failure handling verified.")
                except Exception:
                    log.flush()
                    print(log_path.read_text(errors="replace")[-5000:],file=sys.stderr)
                    raise
                finally:
                    if proc.poll() is None:proc.terminate()
                    try:proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)

if __name__ == "__main__":
    main()
