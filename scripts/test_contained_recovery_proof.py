"""Read-only containment proof regressions; never contact production."""
import importlib.util
import hashlib
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location("contained_proof", Path(__file__).with_name("contained_recovery_proof.py"))
proof = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(proof)


@pytest.mark.parametrize("kind", ["stage", "lease"])
def test_fixed_shared_parent_layout_is_validated_without_blanket_trust(monkeypatch, kind):
    instance = proof.RecoveryProof.__new__(proof.RecoveryProof)
    instance.stage = Path("/tmp/health-app-backup-preflight-123-456")
    instance.lease = Path("/var/lock/health-app-release")
    paths = {
        Path("/"): stat.S_IFDIR | 0o755, Path("/tmp"): stat.S_IFDIR | 0o1777,
        Path("/var"): stat.S_IFDIR | 0o755, Path("/var/lock"): stat.S_IFLNK | 0o777,
        Path("/run"): stat.S_IFDIR | 0o755, Path("/run/lock"): stat.S_IFDIR | 0o1777,
        instance.stage: stat.S_IFDIR | 0o700, instance.lease: stat.S_IFDIR | 0o700,
    }
    target = (instance.stage if kind == "stage" else instance.lease) / "token"
    paths[target] = stat.S_IFREG | 0o600
    monkeypatch.setattr(Path, "lstat", lambda path: SimpleNamespace(st_mode=paths[path], st_uid=0, st_gid=0, st_nlink=1))
    monkeypatch.setattr(proof.os, "readlink", lambda path: "/run/lock")
    instance._secure_evidence(target)
    shared = Path("/tmp" if kind == "stage" else "/run/lock")
    paths[shared] = stat.S_IFDIR | 0o777
    with pytest.raises(proof.ProofError):
        instance._secure_evidence(target)
    paths[shared] = stat.S_IFDIR | 0o1777
    paths[target] = stat.S_IFLNK | 0o777
    with pytest.raises(proof.ProofError):
        instance._secure_evidence(target)
    paths[target] = stat.S_IFREG | 0o660
    with pytest.raises(proof.ProofError):
        instance._secure_evidence(target)
    if kind == "lease":
        paths[target] = stat.S_IFREG | 0o600
        monkeypatch.setattr(proof.os, "readlink", lambda path: "/tmp")
        with pytest.raises(proof.ProofError):
            instance._secure_evidence(target)


def test_base_normalization_ignores_only_reset_service_fields():
    before = b"[Service]\nExecStart=/old\nUser=health-app\n[Install]\nWantedBy=multi-user.target\n"
    after = before.replace(b"/old", b"/new")
    assert proof.normalized_base(before, {"ExecStart"}) == proof.normalized_base(after, {"ExecStart"})
    assert proof.normalized_base(before, set()) != proof.normalized_base(after, set())
    assert proof.normalized_base(before, {"ExecStart"}) != proof.normalized_base(before.replace(b"User=health-app", b"User=root"), {"ExecStart"})
    assert proof.normalized_base(before, {"ExecStart"}) == proof.normalized_base(b"# Legacy comment\n\n; comment\n" + before, {"ExecStart"})


@pytest.mark.parametrize("raw", [b"HEALTH_EVIDENCE_RUNTIME_ENABLED=true\n", b"HEALTH_EVIDENCE_RUNTIME_ENABLED=false\nHEALTH_EVIDENCE_RUNTIME_ENABLED=false\n", b"export HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"])
def test_false_flag_is_unique_and_exact(raw):
    with pytest.raises(proof.ProofError):
        proof.require_false(raw)


def test_false_flag_accepts_other_unrelated_configuration():
    proof.require_false(b"OTHER=value\nHEALTH_EVIDENCE_RUNTIME_ENABLED=false\n")


@pytest.mark.parametrize("raw", [b'{"state":1,"state":2}', b'[]'])
def test_json_rejects_duplicate_or_nonobject(raw):
    with pytest.raises(proof.ProofError):
        proof.object_json(raw)


def test_normalization_rejects_continuation_and_unknown_sections():
    with pytest.raises(proof.ProofError):
        proof.normalized_base(b"[Service]\nExecStart=/bin/x \\\n --arg\n", {"ExecStart"})
    assert proof.normalized_base(b"[Unit]\nExecStart=unchanged\n", {"ExecStart"}) == b"[Unit]\nExecStart=unchanged\n"


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    instance = proof.RecoveryProof.__new__(proof.RecoveryProof)
    instance.proc, instance.cgroup = tmp_path / "proc", tmp_path / "cgroup"
    instance._assert_original_lease = lambda: None
    fields = {}
    for index, unit in enumerate(proof.UNITS):
        pid = str(200 + index)
        group = "/system.slice/" + unit
        directory = instance.cgroup / group.lstrip("/")
        directory.mkdir(parents=True)
        (directory / "cgroup.procs").write_text("" if unit.endswith(".socket") else pid + "\n")
        process = instance.proc / pid
        process.mkdir(parents=True)
        (process / "stat").write_bytes(b"200 (test process) " + b" ".join([b"1"] * 20))
        (process / "environ").write_bytes(b"OTHER=unrelated\0HEALTH_EVIDENCE_RUNTIME_ENABLED=false\0")
        fields[unit] = {"ActiveState": "active", "SubState": "listening" if unit.endswith(".socket") else "running",
                        "MainPID": "0" if unit.endswith(".socket") else pid, "NRestarts": "0",
                        "ActiveEnterTimestampMonotonic": "2000", "ControlGroup": group, "Result": "success", "RestartUSec": "5s"}
    instance.systemd = SimpleNamespace(show=lambda unit, prop: fields[unit][prop])
    monkeypatch.setattr(proof.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=b""))
    return instance, fields


def test_running_snapshot_is_stable_and_contains_no_environment(runtime):
    instance, _ = runtime
    first = instance.running_snapshot()
    assert first == instance.running_snapshot()
    assert "unrelated" not in str(first)


@pytest.mark.parametrize("fault", ["flag", "duplicate", "child", "restart", "pid", "not_ready", "pending_job"])
def test_running_proof_rejects_faults_or_exposes_stability_change(runtime, monkeypatch, fault):
    instance, fields = runtime
    baseline = instance.running_snapshot()
    unit = "celery-beat.service"
    pid = fields[unit]["MainPID"]
    if fault == "restart":
        fields[unit]["NRestarts"] = "1"
        assert instance.running_snapshot() != baseline
        return
    if fault in {"flag", "duplicate"}:
        (instance.proc / pid / "environ").write_bytes(b"HEALTH_EVIDENCE_RUNTIME_ENABLED=true\0" if fault == "flag" else b"HEALTH_EVIDENCE_RUNTIME_ENABLED=false\0" * 2)
    elif fault == "child":
        child = instance.proc / "999"
        child.mkdir()
        (child / "stat").write_bytes((instance.proc / pid / "stat").read_bytes())
        (child / "environ").write_bytes(b"HEALTH_EVIDENCE_RUNTIME_ENABLED=true\0")
        (instance.cgroup / fields[unit]["ControlGroup"].lstrip("/") / "cgroup.procs").write_text(pid + "\n999\n")
    elif fault == "pid":
        fields[unit]["MainPID"] = "999"
    elif fault == "not_ready":
        fields[unit]["SubState"] = "auto-restart"
    elif fault == "pending_job":
        monkeypatch.setattr(proof.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=b"123 celery-beat.service start running\n"))
    with pytest.raises(proof.ProofError):
        instance.running_snapshot()


def test_stopped_requires_zero_processes_and_no_jobs(runtime, monkeypatch):
    instance, fields = runtime
    for unit, entry in fields.items():
        entry["ActiveState"], entry["MainPID"] = "inactive", "0"
        (instance.cgroup / entry["ControlGroup"].lstrip("/") / "cgroup.procs").write_text("")
    instance.stopped()
    monkeypatch.setattr(proof.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=b"123 health-backend.socket start waiting\n"))
    with pytest.raises(proof.ProofError):
        instance.stopped()


def test_file_identity_rejects_symlink_hardlink_and_group_write(tmp_path):
    instance = proof.RecoveryProof.__new__(proof.RecoveryProof)
    instance.bootstrap = SimpleNamespace(secure=lambda path: None)
    path = tmp_path / "file"
    path.write_bytes(b"evidence")
    identity = instance._file(path)[1]
    assert identity["sha256"]
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(proof.ProofError):
        instance._file(link)
    link.unlink()
    os.link(path, link)
    with pytest.raises(proof.ProofError):
        instance._file(path)


@pytest.fixture
def stage(tmp_path, monkeypatch):
    instance = proof.RecoveryProof.__new__(proof.RecoveryProof)
    instance.lease = tmp_path / "lease"
    instance.lease.mkdir()
    instance.token = "original-token"
    instance.production = tmp_path / "production"
    (instance.production / "backend").mkdir(parents=True)
    instance.bootstrap = SimpleNamespace(secure=lambda path: None)
    # Pure fixture adapter: production parser remains fixed /tmp-only.
    staged = Path("/tmp/health-app-backup-preflight-fixture")
    actual = tmp_path / "stage"
    actual.mkdir()
    instance._directory = lambda path, mode=0o700: {"inode": 123}
    original_file = instance._file
    def read(path, mode=None):
        result = original_file(actual / path.name if path.parent == staged else path, mode)
        result[1]["gid"] = 0
        return result
    instance._file = read
    original_iterdir = Path.iterdir
    monkeypatch.setattr(Path, "iterdir", lambda path: original_iterdir(actual if path == staged else path))
    monkeypatch.setattr(proof.grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=0))
    source = tmp_path / "canonical"
    hashes = {}
    for name, relative in proof.ARTIFACTS.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((name + "\n").encode())
        (actual / name).write_bytes(path.read_bytes())
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    env = b"HEALTH_EVIDENCE_RUNTIME_ENABLED=false\n"
    for name in ("backend.env.rollback", "backend.env.candidate"):
        (actual / name).write_bytes(env)
        (actual / name).chmod(0o400)
        hashes[name] = hashlib.sha256(env).hexdigest()
    manifest = actual / "staged.sha256"
    manifest.write_text("".join(f"{value}  {name}\n" for name, value in hashes.items()))
    manifest.chmod(0o400)
    live = instance.production / "backend/.env"
    live.write_bytes(env)
    live.chmod(0o640)
    for name, content in (("token", instance.token + "\n"), ("stage", str(staged) + "\n"), ("label", "backend\n"), ("started_at", "2026-09-09T00:00:00Z\n")):
        path = instance.lease / name
        path.write_text(content)
        path.chmod(0o600)
    return instance, source, actual


def test_stage_proves_exact_original_artifacts_and_unchanged_env(stage):
    instance, source, _ = stage
    assert instance._stage(source) == instance._stage(source)


@pytest.mark.parametrize("fault", ["token", "extra", "hash", "canonical", "env", "manifest_duplicate", "env_mode"])
def test_stage_rejects_original_binding_drift(stage, fault):
    instance, source, actual = stage
    if fault == "token":
        (instance.lease / "token").write_text("different\n")
    elif fault == "extra":
        (actual / "sitecustomize.py").write_text("bad")
    elif fault == "hash":
        (actual / "backup_db.sh").write_text("changed")
    elif fault == "canonical":
        (source / "backend/scripts/backup_db.sh").write_text("changed")
    elif fault == "env":
        (instance.production / "backend/.env").write_text("CHANGED=true\nHEALTH_EVIDENCE_RUNTIME_ENABLED=false\n")
    elif fault == "env_mode":
        (instance.production / "backend/.env").chmod(0o600)
    else:
        manifest = actual / "staged.sha256"
        manifest.chmod(0o600)
        raw = manifest.read_bytes()
        manifest.write_bytes(raw + raw.splitlines(keepends=True)[0])
        manifest.chmod(0o400)
    with pytest.raises(proof.ProofError):
        instance._stage(source)
