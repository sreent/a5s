from __future__ import annotations

import subprocess

import pytest

from a5s import devdb


def test_windows_devdb_starts_and_stops_docker(monkeypatch, tmp_path):
    monkeypatch.setattr(devdb, "_windows", lambda: True)
    monkeypatch.setattr(devdb.shutil, "which", lambda name: "/usr/bin/docker")
    calls = []

    def run(cmd, *, capture_output, check):
        calls.append(cmd)
        code = 1 if cmd[:2] == ["docker", "inspect"] else 0
        return subprocess.CompletedProcess(cmd, code, b"", b"")

    monkeypatch.setattr(devdb.subprocess, "run", run)
    folder = tmp_path / "pg"
    assert devdb.start(folder, 54329) == "postgresql://a5s@127.0.0.1:54329/postgres"
    started = next(cmd for cmd in calls if cmd[:2] == ["docker", "run"])
    assert "--rm" in started
    assert "127.0.0.1:54329:5432" in started
    assert f"{(folder / 'data').resolve()}:/var/lib/postgresql/data" in started
    ready = next(cmd for cmd in calls if cmd[:2] == ["docker", "exec"])
    assert "/proc/1/comm" in ready[-1] and "pg_isready" in ready[-1]
    devdb.stop(folder)
    assert calls[-1] == ["docker", "stop", devdb._docker_name(folder)]


def test_windows_devdb_reuses_a_running_container(monkeypatch, tmp_path):
    monkeypatch.setattr(devdb, "_windows", lambda: True)
    monkeypatch.setattr(devdb.shutil, "which", lambda name: "/usr/bin/docker")
    calls = []

    def run(cmd, *, capture_output, check):
        calls.append(cmd)
        out = b"true\n" if cmd[:2] == ["docker", "inspect"] else b""
        return subprocess.CompletedProcess(cmd, 0, out, b"")

    monkeypatch.setattr(devdb.subprocess, "run", run)
    assert devdb.start(tmp_path / "pg", 54329).endswith(":54329/postgres")
    assert not [cmd for cmd in calls if cmd[:2] == ["docker", "run"]]


def test_windows_devdb_says_when_it_has_no_docker(monkeypatch, tmp_path):
    monkeypatch.setattr(devdb, "_windows", lambda: True)
    monkeypatch.setattr(devdb.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="Docker Desktop"):
        devdb.start(tmp_path / "pg", 54329)
