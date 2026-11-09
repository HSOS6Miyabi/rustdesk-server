#!/usr/bin/env python3
"""Start the complete API/hbbs/hbbr stack as native processes and verify restart persistence."""

import pathlib
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

from test_runtime import (
    check_tcp, check_udp_rendezvous, check_websocket, find_ports,
)


def available_tcp_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def stop_process(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=7)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=7)


def start_process(binary, args, cwd, logpath, env):
    log = open(logpath, "ab")
    process = subprocess.Popen(
        [str(binary), *args], cwd=str(cwd), env=env,
        stdout=log, stderr=subprocess.STDOUT,
    )
    return process, log


def wait_until_ready(processes, api_port, server_port):
    deadline = time.monotonic() + 45
    last_error = None
    while time.monotonic() < deadline:
        for name, process in processes.items():
            if process.poll() is not None:
                raise RuntimeError(f"{name} stopped during the startup check")
        try:
            for port in (server_port - 1, server_port, server_port + 1,
                         server_port + 2, server_port + 3):
                check_tcp(port)
            with urllib.request.urlopen(
                f"http://127.0.0.1:{api_port}/_admin/", timeout=2
            ) as response:
                if response.status != 200 or b"<html" not in response.read(8192).lower():
                    raise AssertionError("native API console could not load")
            with urllib.request.urlopen(
                f"http://127.0.0.1:{api_port}/webclient2/", timeout=2
            ) as response:
                if response.status != 200 or b"<html" not in response.read(8192).lower():
                    raise AssertionError("native WebClient could not load")
            return
        except (OSError, ValueError, AssertionError) as exc:
            last_error = exc
            time.sleep(0.2)
    raise TimeoutError(f"native stack did not become healthy: {last_error}")


def database_snapshot(database_path):
    if not database_path.exists():
        raise AssertionError("native API database was not created")
    with sqlite3.connect(str(database_path)) as connection:
        admin = connection.execute(
            "SELECT id, password FROM users WHERE username = 'admin'"
        ).fetchone()
        version = connection.execute(
            "SELECT version FROM versions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not admin or not admin[1] or not version or version[0] < 282:
            raise AssertionError("native API accounts or version 282 schema are missing")
        return admin, version


def main():
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: test_native_stack.py /path/to/apimain /path/to/hbbs /path/to/hbbr"
        )
    api_binary, hbbs_binary, hbbr_binary = [
        pathlib.Path(value).resolve() for value in sys.argv[1:]
    ]
    for binary in (api_binary, hbbs_binary, hbbr_binary):
        if not binary.exists():
            raise FileNotFoundError(binary)
    source = api_binary.parents[1]
    server_port = find_ports()
    api_port = available_tcp_port()
    with tempfile.TemporaryDirectory(prefix="rustdesk-native-stack-") as directory:
        work = pathlib.Path(directory)
        api_work = work / "api"
        server_work = work / "server"
        api_work.mkdir()
        server_work.mkdir()
        shutil.copytree(source / "conf", api_work / "conf")
        shutil.copytree(source / "resources", api_work / "resources")
        (api_work / "data").mkdir()
        (api_work / "runtime").mkdir()
        configuration = api_work / "conf" / "config.yaml"
        yaml = configuration.read_text()
        expected = 'api-addr: "0.0.0.0:21114"'
        if expected not in yaml:
            raise AssertionError("API listen address has changed")
        configuration.write_text(
            yaml.replace(expected, f'api-addr: "127.0.0.1:{api_port}"')
        )
        env = __import__("os").environ.copy()
        env["MUST_LOGIN"] = "N"
        env["RUSTDESK_API_JWT_KEY"] = "native-test-jwt-secret-with-sufficient-length"
        env["TEST_HBBS"] = "no"
        processes, streams = {}, []
        try:
            for cycle in range(2):
                for name, binary, args, cwd in (
                    ("api", api_binary, ["--config", "./conf/config.yaml"], api_work),
                    ("hbbs", hbbs_binary, ["--bind=127.0.0.1", f"--port={server_port}"], server_work),
                    ("hbbr", hbbr_binary, ["--bind=127.0.0.1", f"--port={server_port + 1}"], server_work),
                ):
                    process, stream = start_process(
                        binary, args, cwd, work / f"{name}.log", env
                    )
                    processes[name] = process
                    streams.append(stream)
                wait_until_ready(processes, api_port, server_port)
                check_websocket(server_port + 2)
                check_websocket(server_port + 3)
                check_udp_rendezvous(server_port)
                current_database = database_snapshot(api_work / "data/rustdeskapi.db")
                public_key = (server_work / "id_ed25519.pub").read_bytes()
                if len(public_key) < 20:
                    raise AssertionError("native hbbs identity was not generated")
                if cycle == 0:
                    previous = current_database, public_key
                elif previous != (current_database, public_key):
                    raise AssertionError("restarting native API and server changed saved data")
                for process in processes.values():
                    stop_process(process)
                processes.clear()
            print("Native API, hbbs, hbbr, HTTP, WebClient, UDP and WebSockets passed two restarts.")
            print("API administrator and database version, and hbbs public key, remain unchanged.")
        except Exception:
            for stream in streams:
                stream.flush()
            for name in ("api", "hbbs", "hbbr"):
                path = work / f"{name}.log"
                if path.exists():
                    print(
                        f"\n{name} output:\n{path.read_text(errors='replace')[-3500:]}",
                        file=sys.stderr,
                    )
            raise
        finally:
            for process in processes.values():
                stop_process(process)
            for stream in streams:
                stream.close()


if __name__ == "__main__":
    main()
