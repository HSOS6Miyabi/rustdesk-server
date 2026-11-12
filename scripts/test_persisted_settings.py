#!/usr/bin/env python3
"""Check that hbbs runtime policy changes survive a complete server restart."""
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time


def available_port():
    for port in range(24000, 45000, 41):
        listeners = []
        try:
            for number in (port - 1, port, port + 2):
                listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                listeners.append(listener)
                listener.bind(("127.0.0.1", number))
            return port
        except OSError:
            pass
        finally:
            for listener in listeners:
                listener.close()
    raise RuntimeError("No available rendezvous ports")


def command(port, text):
    with socket.create_connection(("127.0.0.1", port - 1), timeout=3) as connection:
        connection.settimeout(3)
        connection.sendall(text.encode("utf-8"))
        connection.shutdown(socket.SHUT_WR)
        return connection.recv(4096).decode("utf-8")


def start(binary, port, folder):
    env = os.environ.copy()
    env.update({
        "RUSTDESK_API_JWT_KEY": "persistent-policy-test-secret-for-server",
        "MUST_LOGIN": "N",
        "ALWAYS_USE_RELAY": "N",
        "TEST_HBBS": "no",
    })
    log_file = folder / "server.log"
    log = log_file.open("ab")
    process = subprocess.Popen(
        [binary, "-p", str(port), "-r", "127.0.0.1:21117"],
        cwd=folder, env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"hbbs exited with status {process.returncode}")
            try:
                command(port, "must-login")
                return process, log
            except OSError:
                time.sleep(0.15)
        raise TimeoutError("hbbs console did not start")
    except Exception:
        process.terminate()
        process.wait(timeout=5)
        log.close()
        raise


def stop(process, log):
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    log.close()


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: test_persisted_settings.py /path/to/hbbs")
    binary = str(pathlib.Path(sys.argv[1]).resolve())
    port = available_port()
    with tempfile.TemporaryDirectory(prefix="rustdesk-settings-") as work:
        folder = pathlib.Path(work)
        process, log = start(binary, port, folder)
        try:
            assert "false" in command(port, "must-login").lower()
            assert "false" in command(port, "always-use-relay").lower()
            command(port, "must-login Y")
            command(port, "always-use-relay Y")
            command(port, "relay-servers 127.0.0.1:31117")
            time.sleep(0.35)
            settings = json.loads((folder / "rustdesk-server-settings.json").read_text())
            assert settings == {
                "must_login": True,
                "always_use_relay": True,
                "relay_servers": "127.0.0.1:31117",
            }, settings
        finally:
            stop(process, log)

        process, log = start(binary, port, folder)
        try:
            assert "true" in command(port, "must-login").lower()
            assert "true" in command(port, "always-use-relay").lower()
            assert "127.0.0.1:31117" in command(port, "relay-servers")
            command(port, "must-login N")
            command(port, "always-use-relay N")
            assert "false" in command(port, "must-login").lower()
            assert "false" in command(port, "always-use-relay").lower()
        finally:
            stop(process, log)
        process, log = start(binary, port, folder)
        try:
            assert "false" in command(port, "must-login").lower()
            assert "false" in command(port, "always-use-relay").lower()
            assert "127.0.0.1:31117" in command(port, "relay-servers")
        finally:
            stop(process, log)
    print("Saved server management settings survived two complete hbbs restarts.")


if __name__ == "__main__":
    main()
