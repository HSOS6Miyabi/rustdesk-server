#!/usr/bin/env python3
"""Verify that recreating the combined Docker container preserves API and hbbs data."""
import hashlib
import json
import shlex
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True, stderr=subprocess.PIPE).strip()


def available_ports(container):
    result = {}
    for number in (21114, 21116, 21117):
        mapping = docker("port", container, f"{number}/tcp")
        result[number] = int(mapping.splitlines()[0].rsplit(":", 1)[1])
    return result


def wait_for_services(container):
    last_error = None
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if docker("inspect", "-f", "{{.State.Running}}", container) != "true":
            raise RuntimeError("the combined container exited before the checks completed")
        try:
            ports = available_ports(container)
            for port in (21116, 21117):
                with socket.create_connection(("127.0.0.1", ports[port]), timeout=2):
                    pass
            with urllib.request.urlopen(
                f"http://127.0.0.1:{ports[21114]}/_admin/", timeout=3
            ) as response:
                if response.status != 200 or b"<html" not in response.read(4096).lower():
                    raise AssertionError("the API console is unavailable")
            return
        except (IndexError, OSError, AssertionError, ValueError) as exc:
            last_error = exc
            time.sleep(1)
    raise TimeoutError(f"services were not ready after starting the container: {last_error}")


def server_command(container, command):
    quoted = shlex.quote(command)
    shell = "exec 3<>/dev/tcp/127.0.0.1/21115; printf %s " + quoted + " >&3; cat <&3"
    return docker("exec", container, "/bin/bash", "-c", shell)


def state_of(container):
    with tempfile.TemporaryDirectory() as tmp:
        backup = os.path.join(tmp, "rustdeskapi.db")
        docker("cp", f"{container}:/app/data/rustdeskapi.db", backup)
        database = sqlite3.connect(f"file:{backup}?mode=ro", uri=True)
        try:
            user = database.execute(
                "SELECT id, username, password FROM users WHERE username = 'admin'"
            ).fetchone()
            latest = database.execute(
                "SELECT version FROM versions ORDER BY id DESC LIMIT 1"
            ).fetchone()
        finally:
            database.close()
        if not user or not user[2] or not latest or latest[0] < 282:
            raise AssertionError("administrator or schema migration did not persist")
        public_key = docker("exec", container, "cat", "/data/id_ed25519.pub")
        if len(public_key.strip()) < 20:
            raise AssertionError("the RustDesk identity public key is missing")
        settings = json.loads(docker("exec", container, "cat", "/data/rustdesk-server-settings.json"))
        return (user, latest, hashlib.sha256(public_key.encode()).hexdigest(), settings)


def launch(container, image, api_volume, server_volume):
    docker(
        "run", "--rm", "-d", "-P", "--name", container,
        "--mount", f"type=volume,source={api_volume},target=/app/data",
        "--mount", f"type=volume,source={server_volume},target=/data",
        "-e", "MUST_LOGIN=N",
        "-e", "ENCRYPTED_ONLY=0",
        "-e", "RUSTDESK_API_JWT_KEY=local-integration-test-secret-very-long",
        "-e", "RELAY=127.0.0.1:21117",
        image,
    )


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: test_persistent_container.py <combined-image>")
    image = sys.argv[1]
    suffix = uuid.uuid4().hex[:10]
    container = f"rustdesk-persistence-{suffix}"
    api_volume, server_volume = f"rustdesk-api-{suffix}", f"rustdesk-server-{suffix}"
    created = []
    running = False
    try:
        for name in (api_volume, server_volume):
            docker("volume", "create", name)
            created.append(name)
        snapshots = []
        for attempt in range(2):
            launch(container, image, api_volume, server_volume)
            running = True
            wait_for_services(container)
            if attempt == 0:
                for command in (
                    "must-login Y",
                    "always-use-relay Y",
                    "relay-servers 127.0.0.1:31117",
                ):
                    response = server_command(container, command)
                    if response.startswith("ERROR:"):
                        raise AssertionError(response)
                time.sleep(0.5)
            if "true" not in server_command(container, "must-login").lower():
                raise AssertionError("mandatory login did not survive recreation")
            if "true" not in server_command(container, "always-use-relay").lower():
                raise AssertionError("forced relay did not survive recreation")
            if "127.0.0.1:31117" not in server_command(container, "relay-servers"):
                raise AssertionError("relay server list did not survive recreation")
            snapshots.append(state_of(container))
            docker("rm", "-fv", container)
            running = False
        if snapshots[0] != snapshots[1]:
            raise AssertionError("the API accounts, server identity or saved server settings changed")
        print("API accounts, RustDesk keys and all three server settings survived container recreation.")
    except Exception:
        if running:
            try:
                print(docker("logs", "--tail", "180", container), file=sys.stderr)
            except subprocess.CalledProcessError:
                pass
        raise
    finally:
        if running:
            subprocess.run(["docker", "rm", "-fv", container], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for name in created:
            subprocess.run(["docker", "volume", "rm", "-f", name], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
