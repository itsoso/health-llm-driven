"""Real filesystem regression for the fixed Ubuntu lock-directory alias."""

import importlib.util
import os
from pathlib import Path

import pytest


def load():
    spec = importlib.util.spec_from_file_location(
        "lease_sync_server", Path(__file__).with_name("trusted_release_server.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_paths(tmp_path, monkeypatch):
    server = load()
    actual = tmp_path / "run-lock"
    actual.mkdir(mode=0o1777)
    alias = tmp_path / "var-lock"
    alias.symlink_to(actual, target_is_directory=True)
    paths = {
        "/var/lock/health-app-release": alias / "health-app-release",
        "/run/lock": actual,
    }
    monkeypatch.setattr(server, "Path", lambda value: paths.get(str(value), Path(value)))
    monkeypatch.setattr(server, "BUSINESS_LEASE", alias / "health-app-release")
    calls = []
    # The separate fixed-path metadata guard is already covered by native tests.
    # Only remap that guard here; open/fsync and the alias are real filesystem I/O.
    monkeypatch.setattr(server, "_testflight_lease_parent", lambda: calls.append("guard"))
    return server, alias, actual, calls


def test_generic_directory_sync_still_rejects_real_symlink(tmp_path):
    server = load()
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(OSError):
        server._sync_directory(alias)


def test_business_parent_sync_validates_then_opens_real_directory(tmp_path, monkeypatch):
    server, alias, actual, calls = fixture_paths(tmp_path, monkeypatch)
    server._sync_business_lease_parent()
    assert calls == ["guard", "guard"]
    assert alias.is_symlink() and alias.resolve() == actual


def test_business_parent_sync_rejects_directory_replacement(tmp_path, monkeypatch):
    server, _, actual, _ = fixture_paths(tmp_path, monkeypatch)
    original_fsync = os.fsync

    def swap(fd):
        original_fsync(fd)
        actual.rename(actual.with_name("original"))
        actual.mkdir()

    monkeypatch.setattr(server.os, "fsync", swap)
    with pytest.raises(server.LaunchError, match="parent changed"):
        server._sync_business_lease_parent()


def test_business_parent_sync_never_opens_when_guard_rejects(tmp_path, monkeypatch):
    server, _, _, _ = fixture_paths(tmp_path, monkeypatch)

    def reject():
        raise server.LaunchError("fixed business lease alias differs")

    monkeypatch.setattr(server, "_testflight_lease_parent", reject)
    monkeypatch.setattr(server.os, "open", lambda *a, **k: pytest.fail("opened before guard"))
    with pytest.raises(server.LaunchError, match="alias differs"):
        server._sync_business_lease_parent()
