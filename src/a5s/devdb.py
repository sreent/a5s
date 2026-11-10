"""A throwaway Postgres for development and tests.

Postgres won't run as root, so as root it runs as the `postgres` user. On Windows,
Docker Desktop supplies Postgres instead.
"""

from __future__ import annotations

import glob
import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path

POSTGRES_IMAGE = "postgres:16@sha256:1beaa3084eee2676f20a9cd9928f0bf2c5bf674f8e49f81017912183d377c61c"


def _windows() -> bool:
    return os.name == "nt"


def _bin(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    candidates = sorted(glob.glob(f"/usr/lib/postgresql/*/bin/{name}"))
    if not candidates:
        raise RuntimeError(f"can't find {name}; install Postgres or set A5S_DATABASE_URL")
    return candidates[-1]


def _as_owner(cmd: list[str]) -> list[str]:
    return ["runuser", "-u", "postgres", "--", *cmd] if os.geteuid() == 0 else cmd


def _ready(port: int) -> bool:
    probe = [_bin("pg_isready"), "-h", "127.0.0.1", "-p", str(port)]
    return subprocess.run(probe, capture_output=True, check=False).returncode == 0


def _docker_name(folder: Path) -> str:
    digest = hashlib.sha256(str(folder.resolve()).encode()).hexdigest()[:12]
    return f"a5s-devdb-{digest}"


def _docker_ready(name: str) -> bool:
    probe = ["docker", "exec", name, "sh", "-c",
             '[ "$(cat /proc/1/comm)" = postgres ] && pg_isready -U a5s -d postgres']
    return subprocess.run(probe, capture_output=True, check=False).returncode == 0


def _docker_start(folder: Path, port: int, url: str) -> str:
    if not shutil.which("docker"):
        raise RuntimeError("Windows development needs Docker Desktop or Postgres installed")
    name = _docker_name(folder)
    found = subprocess.run(["docker", "inspect", "--format", "{{.State.Running}}", name],
                           capture_output=True, check=False)
    if found.returncode == 0:
        if found.stdout.strip() != b"true":
            subprocess.run(["docker", "start", name], capture_output=True, check=True)
    else:
        data = folder / "data"
        data.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            "docker", "run", "--rm", "-d", "--name", name,
            "-e", "POSTGRES_USER=a5s", "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
            "-p", f"127.0.0.1:{port}:5432",
            "-v", f"{data.resolve()}:/var/lib/postgresql/data", POSTGRES_IMAGE,
        ], capture_output=True, check=True)
    for _ in range(60):
        if _docker_ready(name):
            return url
        time.sleep(1)
    raise RuntimeError("Postgres in Docker didn't start")


def start(folder: Path, port: int) -> str:
    url = f"postgresql://a5s@127.0.0.1:{port}/postgres"
    if _windows():
        return _docker_start(folder, port, url)
    if (folder / "postmaster.pid").exists() and _ready(port):
        return url
    folder.mkdir(parents=True, exist_ok=True)
    if os.geteuid() == 0:
        shutil.chown(folder, "postgres", "postgres")
    if not (folder / "PG_VERSION").exists():
        subprocess.run(
            _as_owner([_bin("initdb"), "-D", str(folder), "-A", "trust", "-U", "a5s", "--no-sync"]),
            check=True, capture_output=True,
        )
    subprocess.run(
        _as_owner([
            _bin("pg_ctl"), "-D", str(folder), "-l", str(folder / "server.log"), "-w",
            "-o", f"-p {port} -c listen_addresses=127.0.0.1 -k {folder} -c fsync=off",
            "start",
        ]),
        check=True, capture_output=True,
    )
    for _ in range(50):
        if _ready(port):
            return url
        time.sleep(0.1)
    raise RuntimeError("Postgres didn't start")


def stop(folder: Path) -> None:
    if _windows():
        if shutil.which("docker"):
            subprocess.run(["docker", "stop", _docker_name(folder)], capture_output=True, check=False)
        return
    if (folder / "postmaster.pid").exists():
        subprocess.run(_as_owner([_bin("pg_ctl"), "-D", str(folder), "-m", "fast", "stop"]),
                       capture_output=True, check=False)
