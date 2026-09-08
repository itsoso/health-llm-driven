"""Historical clone-failure recovery uses synthetic local evidence only."""

import fcntl
import hashlib
import json
import os

import pytest
from test_bootstrap_trusted_release import HOST, NEW_LOOPBACK, PUBLIC, SHA, fixture

NEW_SHA = "b" * 40
PRODUCTION_SHA = "c" * 40


def recovery_fixture(monkeypatch, tmp_path):
    b, calls = fixture(monkeypatch, tmp_path)
    b.install(SHA, 200, PUBLIC)
    source, _ = b.reviewed_source(NEW_SHA)
    monkeypatch.setattr(b, "canonical_source", lambda sha: source)
    digest = hashlib.sha256(b.INSTALLED.read_bytes()).hexdigest()
    monkeypatch.setattr(b, "LEGACY_CLONE_EXECUTORS", {digest}, raising=False)
    monkeypatch.setattr(b, "BUSINESS_LEASE", tmp_path / "lease")
    monkeypatch.setattr(b, "_recovery_process_proof", lambda: None, raising=False)
    monkeypatch.setattr(b, "_recovery_production_proof", lambda *args: None, raising=False)
    monkeypatch.setattr(b, "_recovery_toolchain_proof", lambda: {"git": "fixture"}, raising=False)
    monkeypatch.setattr(b, "_assert_idle", lambda: None)
    w = b.STATE / SHA
    w.mkdir(mode=0o700)
    (w / "home").mkdir(mode=0o700)
    for name, state in (("started.json", "STARTED"), ("completed.json", "NEEDS_OPERATOR")):
        b._write(w / name, json.dumps({"sha": SHA, "state": state}).encode())
    b._write(w / "build.lock", b"")
    b._write(w / "preparation.log", (
        f"Cloning into '{w}/source'...\n"
        "error: RPC failed; curl 28 Operation too slow. Less than 1024 bytes/sec transferred the last 30 seconds\n"
        "fatal: early EOF\nfatal: fetch-pack: invalid index-pack output\n"
    ).encode())
    calls.clear()
    return b, w, calls


def inspect(b):
    return b.recover_preparation(SHA, NEW_SHA, PRODUCTION_SHA)


def recover(b, digest):
    return b.recover_preparation(SHA, NEW_SHA, PRODUCTION_SHA, evidence_sha256=digest)


def test_inspect_is_read_only_and_recovery_preserves_original_evidence(monkeypatch, tmp_path):
    b, w, calls = recovery_fixture(monkeypatch, tmp_path)
    original = b._preparation_manifest(w)
    keys = b.AUTHORIZED.read_bytes()
    plan = inspect(b)
    assert plan["state"] == "RECOVERABLE_PREPARATION_FAILURE"
    assert b.AUTHORIZED.read_bytes() == keys
    assert not (b.STATE / "recoveries").exists()
    result = recover(b, plan["evidence_sha256"])
    assert result["state"] == "RECOVERED_PREPARATION_FAILURE"
    assert b._preparation_manifest(w) == original
    assert b._read_json(w / "completed.json")["state"] == "NEEDS_OPERATOR"
    assert b.AUTHORIZED.read_text() == "ssh-ed25519 AAAAExisting unrelated\n"
    assert not (b.CONFIG / "loopback.key").exists()
    with pytest.raises(b.BootstrapError):
        b._workspace_evidence(SHA)
    assert b._workspace_evidence(SHA, recovery_receipt=result["receipt"])["state"] == "RECOVERED_PREPARATION_FAILURE"
    intent_bytes = (b.STATE / "recoveries" / SHA / "intent.json").read_bytes()
    assert result["receipt"].encode() not in intent_bytes
    assert b._read_json(b.STATE / "recoveries" / SHA / "intent.json")["evidence_sha256"] == plan["evidence_sha256"]
    with pytest.raises(b.BootstrapError):
        b._workspace_evidence(SHA, recovery_receipt="0" * 64)
    assert not any("deploy.sh" in str(arg) for arg in calls)
    with pytest.raises(b.BootstrapError):
        recover(b, plan["evidence_sha256"])


@pytest.mark.parametrize("mutation", ["source", "home", "log", "claim", "receipt", "executor", "policy", "lease"])
def test_unsafe_or_unrecognized_scene_cannot_revoke(monkeypatch, tmp_path, mutation):
    b, w, _ = recovery_fixture(monkeypatch, tmp_path)
    before = b.AUTHORIZED.read_bytes()
    if mutation == "source":
        (w / "source").mkdir()
    elif mutation == "home":
        (w / "home/.gitconfig").write_text("changed")
    elif mutation == "log":
        (w / "preparation.log").write_text("fatal: early EOF\n")
    elif mutation == "claim":
        b._write(w / "build-started.json", b"{}")
    elif mutation == "receipt":
        (w / "completed.json").write_text(json.dumps({"sha": SHA, "state": "STARTED"}))
    elif mutation == "executor":
        b.INSTALLED.write_bytes(b"changed executor")
    elif mutation == "policy":
        (b.CONFIG / "authorized-release.json").write_text("{}")
    else:
        b.BUSINESS_LEASE.mkdir()
    with pytest.raises(b.BootstrapError):
        inspect(b)
    assert b.AUTHORIZED.read_bytes() == before
    assert not (b.STATE / "recoveries").exists()


@pytest.mark.parametrize("lock", ["launcher.lock", "build.lock"])
def test_recovery_holds_original_locks(monkeypatch, tmp_path, lock):
    b, w, _ = recovery_fixture(monkeypatch, tmp_path)
    path = b.STATE / lock if lock == "launcher.lock" else w / lock
    with path.open("r+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            inspect(b)
    path.unlink()
    with pytest.raises((b.BootstrapError, FileNotFoundError)):
        inspect(b)
    assert not path.exists()


def test_changed_inspection_digest_fails_before_intent(monkeypatch, tmp_path):
    b, w, _ = recovery_fixture(monkeypatch, tmp_path)
    plan = inspect(b)
    os.utime(w / "preparation.log", ns=(1, 1))
    with pytest.raises(b.BootstrapError):
        recover(b, plan["evidence_sha256"])
    assert not (b.STATE / "recoveries").exists()


@pytest.mark.parametrize("proof", ["_recovery_process_proof", "_recovery_production_proof", "_recovery_toolchain_proof"])
def test_failed_proof_never_mutates_authorization(monkeypatch, tmp_path, proof):
    b, _w, _ = recovery_fixture(monkeypatch, tmp_path)
    keys = b.AUTHORIZED.read_bytes()
    def fail(*args):
        raise b.BootstrapError("unproven")
    monkeypatch.setattr(b, proof, fail)
    with pytest.raises(b.BootstrapError):
        inspect(b)
    assert b.AUTHORIZED.read_bytes() == keys


def test_unknown_recovery_keeps_durable_intent_and_forbids_retry(monkeypatch, tmp_path):
    b, _w, _ = recovery_fixture(monkeypatch, tmp_path)
    plan = inspect(b)
    original_write = b._write
    def fail_terminal(path, data):
        if path.name == "completed.json" and path.parent.parent.name == "recoveries":
            raise OSError("disk failure")
        original_write(path, data)
    monkeypatch.setattr(b, "_write", fail_terminal)
    with pytest.raises(OSError):
        recover(b, plan["evidence_sha256"])
    assert (b.STATE / "recoveries" / SHA / "intent.json").exists()
    with pytest.raises(b.BootstrapError):
        b._workspace_evidence(SHA)
    with pytest.raises(b.BootstrapError):
        inspect(b)


def test_ordinary_revoke_does_not_infer_legacy_recovery(monkeypatch, tmp_path):
    b, _w, _ = recovery_fixture(monkeypatch, tmp_path)
    with pytest.raises(b.BootstrapError):
        b.revoke(SHA)


@pytest.mark.parametrize("fault", ["append", "truncate", "control", "duplicate", "wrong_path"])
def test_only_complete_initial_clone_transcript_is_accepted(monkeypatch, tmp_path, fault):
    b, w, _ = recovery_fixture(monkeypatch, tmp_path)
    path = w / "preparation.log"
    data = path.read_bytes()
    mutations = {"append": data + b"gate passed\n", "truncate": data[:-1],
                 "control": data.replace(b"fatal", b"\x1bfatal"), "duplicate": data + data,
                 "wrong_path": data.replace(SHA.encode(), NEW_SHA.encode())}
    path.write_bytes(mutations[fault])
    with pytest.raises(b.BootstrapError):
        inspect(b)


def test_replaced_lock_after_slow_proof_is_rejected(monkeypatch, tmp_path):
    b, _w, _ = recovery_fixture(monkeypatch, tmp_path)
    lock = b.STATE / "launcher.lock"
    def replace(*args):
        lock.rename(lock.with_suffix(".old"))
        b._write(lock, b"")
    monkeypatch.setattr(b, "_recovery_production_proof", replace)
    with pytest.raises(b.BootstrapError):
        inspect(b)
    assert not (b.STATE / "recoveries").exists()


@pytest.mark.parametrize("boundary", ["intent", "authorized", "private", "terminal"])
def test_every_mutation_boundary_preserves_unknown_operation(monkeypatch, tmp_path, boundary):
    b, _w, _ = recovery_fixture(monkeypatch, tmp_path)
    plan = inspect(b)
    write = b._write
    def fail_write(path, data):
        if (boundary == "intent" and path.name == "intent.json") or (boundary == "terminal" and path.name == "completed.json"):
            raise OSError("injected durable write failure")
        write(path, data)
    monkeypatch.setattr(b, "_write", fail_write)
    if boundary == "authorized":
        def fail_authorized(*args):
            raise OSError("injected atomic replacement failure")
        monkeypatch.setattr(b, "_replace_authorized", fail_authorized)
    if boundary == "private":
        original = b._sync_parent
        def fail_sync(path):
            if path.name == "loopback.key":
                raise OSError("injected private unlink fsync failure")
            original(path)
        monkeypatch.setattr(b, "_sync_parent", fail_sync)
    with pytest.raises(OSError):
        recover(b, plan["evidence_sha256"])
    with pytest.raises(b.BootstrapError):
        b._workspace_evidence(SHA)
    with pytest.raises(b.BootstrapError):
        b.revoke(SHA)
    with pytest.raises(b.BootstrapError):
        inspect(b)


@pytest.mark.parametrize("boundary", ["file_fsync", "directory_fsync"])
def test_visible_but_not_durable_terminal_is_not_accepted(monkeypatch, tmp_path, boundary):
    b, _w, _ = recovery_fixture(monkeypatch, tmp_path)
    plan = inspect(b)
    record = b.STATE / "recoveries" / SHA
    complete = record / "completed.json"
    fsync = b.os.fsync
    injected = False
    def fail_after_write(fd):
        nonlocal injected
        if complete.exists() and not injected:
            target = complete if boundary == "file_fsync" else record
            if os.fstat(fd).st_ino == target.stat().st_ino:
                injected = True
                raise OSError("terminal durability unknown")
        return fsync(fd)
    monkeypatch.setattr(b.os, "fsync", fail_after_write)
    with pytest.raises(OSError):
        recover(b, plan["evidence_sha256"])
    assert injected
    with pytest.raises(b.BootstrapError):
        b._workspace_evidence(SHA)


def test_valid_recovery_allows_fresh_rotation_and_retains_audit(monkeypatch, tmp_path):
    b, w, _ = recovery_fixture(monkeypatch, tmp_path)
    result = recover(b, inspect(b)["evidence_sha256"])
    manifest = b._preparation_manifest(w)
    run = b._run
    def new_key(args, **kwargs):
        result = run(args, **kwargs)
        if args[0] == "/usr/bin/ssh-keygen" and "-q" in args:
            (b.CONFIG / "loopback.key.pub").write_text(NEW_LOOPBACK + "\n")
        return result
    monkeypatch.setattr(b, "_run", new_key)
    with pytest.raises(b.BootstrapError):
        b.rotate(SHA, NEW_SHA, 200, HOST)
    assert b.rotate(SHA, NEW_SHA, 200, HOST, recovery_receipt=result["receipt"])["state"] == "INSTALLED"
    assert b._preparation_manifest(w) == manifest
    assert b._retired_history()[SHA]["workspace"]["state"] == "RECOVERED_PREPARATION_FAILURE"


@pytest.mark.parametrize("fault", ["delete_workspace", "change_receipt", "change_intent", "reauthorize", "restore_private", "change_lock"])
def test_recovered_audit_cannot_mask_drift(monkeypatch, tmp_path, fault):
    import shutil
    b, w, _ = recovery_fixture(monkeypatch, tmp_path)
    old_keys = b.AUTHORIZED.read_bytes()
    result = recover(b, inspect(b)["evidence_sha256"])
    record = b.STATE / "recoveries" / SHA
    if fault == "delete_workspace":
        shutil.rmtree(w)
    elif fault == "change_receipt":
        (record / "completed.json").write_text("{}")
    elif fault == "change_intent":
        (record / "intent.json").write_text("{}")
    elif fault == "reauthorize":
        b.AUTHORIZED.write_bytes(old_keys)
    elif fault == "restore_private":
        b._write(b.CONFIG / "loopback.key", b"fixture")
    else:
        (b.STATE / "launcher.lock").rename(b.STATE / "old-lock")
        b._write(b.STATE / "launcher.lock", b"")
    with pytest.raises((b.BootstrapError, FileNotFoundError)):
        b._workspace_evidence(SHA, recovery_receipt=result["receipt"])


@pytest.mark.parametrize("indicator", ["cwd", "exe", "environ", "cmdline", "none", "unreadable", "empty_argv"])
def test_proc_proof_catches_reparented_helper(monkeypatch, tmp_path, indicator):
    from test_bootstrap_trusted_release import load_bootstrap
    b = load_bootstrap()
    proc = tmp_path / "proc"
    proc.mkdir()
    monkeypatch.setattr(b, "PROC", proc, raising=False)
    for pid in (os.getpid(), 999999):
        p = proc / str(pid)
        p.mkdir()
        (p / "cmdline").write_bytes(b"/usr/lib/git-core/git-remote-https\0")
        (p / "environ").write_bytes(b"PATH=/usr/bin\0")
        (p / "cwd").symlink_to("/nonexistent")
        (p / "exe").symlink_to("/usr/lib/git-core/git-remote-http")
        (p / "stat").write_bytes(f"{pid} (git) S ".encode() + b"1 " * 19)
    p = proc / "999999"
    if indicator in {"cwd", "exe"}:
        (p / indicator).unlink()
        (p / indicator).symlink_to("/var/lib/reva-release/old/source")
    elif indicator in {"environ", "cmdline"}:
        (p / indicator).write_bytes(b"HOME=/var/lib/reva-release/old/home\0")
    elif indicator == "unreadable":
        (p / "environ").unlink()
    elif indicator == "empty_argv":
        (p / "cmdline").write_bytes(b"")
        (p / "cwd").unlink()
        (p / "cwd").symlink_to("/var/lib/reva-release/old")
    if indicator == "none":
        b._recovery_process_proof()
    else:
        with pytest.raises(b.BootstrapError):
            b._recovery_process_proof()


def test_parent_exit_during_enumeration_is_unknown_not_quiescent(monkeypatch, tmp_path):
    from pathlib import Path

    from test_bootstrap_trusted_release import load_bootstrap
    b = load_bootstrap()
    proc = tmp_path / "proc"
    proc.mkdir()
    monkeypatch.setattr(b, "PROC", proc)
    (proc / str(os.getpid())).mkdir()
    parent = proc / "999999"
    parent.mkdir()
    original = Path.read_bytes
    def spawn_and_exit(path):
        if path == parent / "stat":
            (proc / "999998").mkdir()
            parent.rmdir()
            raise FileNotFoundError("parent exited leaving child")
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", spawn_and_exit)
    with pytest.raises(b.BootstrapError):
        b._recovery_process_proof()
