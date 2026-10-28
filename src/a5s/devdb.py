"""A throwaway Postgres for development and tests.

Postgres won't run as root, so as root it runs as the `postgres` user.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import time
from pathlib import Path


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


def start(folder: Path, port: int) -> str:
    url = f"postgresql://a5s@127.0.0.1:{port}/postgres"
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
    if (folder / "postmaster.pid").exists():
        subprocess.run(_as_owner([_bin("pg_ctl"), "-D", str(folder), "-m", "fast", "stop"]),
                       capture_output=True, check=False)
