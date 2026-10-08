"""Read-only containment proof regressions; never contact production."""
import importlib.util
from datetime import UTC, datetime
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


@pytest.mark.parametrize("damage", [None, "old_mode", "missing_lock", "wrong_claim", "upload_claim", "native_binding"])
def test_built_unuploaded_workspace_keeps_old_modes_closed(tmp_path, damage):
    instance = proof.RecoveryProof.__new__(proof.RecoveryProof)
    instance.failed_sha = "a" * 40
    instance.built_unuploaded = None if damage == "old_mode" else lambda: {}
    workspace = tmp_path / instance.failed_sha
    workspace.mkdir()
    source = tmp_path / "source"
    (source / "scripts").mkdir(parents=True)
    executor = b"canonical executor"
    (source / "scripts/trusted_release_server.py").write_bytes(executor)
    config = tmp_path / "config"
    config.mkdir()
    installed = tmp_path / "installed"
    installed.write_bytes(executor)
    digest = hashlib.sha256(executor).hexdigest()
    (config / "authorized-release.json").write_text(json.dumps({"sha": instance.failed_sha, "expires_at": 0, "executor_sha256": digest}))
    for name, state in (("started.json", "STARTED"), ("completed.json", "NEEDS_OPERATOR"),
                        ("preparation-started.json", "PREPARING"), ("prepared.json", "PREPARED"),
                        ("deployment-started.json", "DEPLOYING"), ("build-started.json", "STARTED")):
        value = {"sha": instance.failed_sha, "state": state}
        if state == "PREPARING": value["executor_sha256"] = digest
        if damage == "wrong_claim" and name == "build-started.json": value["sha"] = "b" * 40
        (workspace / name).write_text(json.dumps(value))
    for name in ("build.lock", "preparation.log", "deployment.log"):
        (workspace / name).write_bytes(b"")
    if damage == "missing_lock": (workspace / "build.lock").unlink()
    if damage == "upload_claim": (workspace / "native-started.json").write_text("{}")
    if damage == "native_binding": (workspace / "testflight-base.json").write_text("{}")
    instance.bootstrap = SimpleNamespace(STATE=tmp_path, CONFIG=config, INSTALLED=installed)
    instance._directory = lambda path: {"ino": path.stat().st_ino}
    instance._file = lambda path, *a: (path.read_bytes(), {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    if damage:
        with pytest.raises(proof.ProofError): instance._workspace(source)
    else:
        snapshot = instance._workspace(source)
        assert "build-started.json" in snapshot and "build.lock" in snapshot["inventory"]


@pytest.mark.parametrize("unchanged", [False, True])
def test_retirement_environment_never_accepts_changed_live_bytes(unchanged):
    instance = proof.RecoveryProof.__new__(proof.RecoveryProof)
    instance.unchanged = unchanged
    sealed = {"backend.env.rollback": b"old", "backend.env.candidate": b"new"}
    with pytest.raises(proof.ProofError):
        instance._validate_unchanged_environment(b"new", sealed)
    if unchanged:
        instance._validate_unchanged_environment(b"old", sealed)
    else:
        with pytest.raises(proof.ProofError):
            instance._validate_unchanged_environment(b"old", sealed)


@pytest.mark.parametrize("start,restarts", [(200, "0"), (50, "1")])
def test_unchanged_retirement_rejects_restarted_or_new_services(tmp_path, start, restarts):
    instance = proof.RecoveryProof.__new__(proof.RecoveryProof)
    instance.proc = tmp_path
    (tmp_path / "stat").write_text("btime 1000\n")
    raw = datetime.fromtimestamp(1200, UTC).strftime("%Y-%m-%dT%H:%M:%SZ\n").encode()
    instance.lease = tmp_path
    instance._file = lambda *a: (raw, {})
    instance.running_snapshot = lambda: {
        unit: {"ActiveEnterTimestampMonotonic": str(start * 1000000),
               "NRestarts": "" if unit.endswith(".socket") else restarts}
        for unit in proof.UNITS
    }
    with pytest.raises(proof.ProofError):
        instance._services_predate_release()


def test_unchanged_retirement_accepts_old_zero_restart_units_and_processes(tmp_path, monkeypatch):
    instance = proof.RecoveryProof.__new__(proof.RecoveryProof)
    instance.proc = tmp_path
    (tmp_path / "stat").write_text("btime 1000\n")
    raw = datetime.fromtimestamp(1300, UTC).strftime("%Y-%m-%dT%H:%M:%SZ\n").encode()
    instance.lease = tmp_path
    instance._file = lambda *a: (raw, {})
    monkeypatch.setattr(proof.os, "sysconf", lambda _: 100)
    instance.running_snapshot = lambda: {
        unit: {"ActiveEnterTimestampMonotonic": "100000000",
               "NRestarts": "" if unit.endswith(".socket") else "0",
               "processes": {} if unit.endswith(".socket") else {"200": "10000"}}
        for unit in proof.UNITS
    }
    instance._services_predate_release()


def test_unchanged_retirement_requires_bounded_preinstallation_inventory(tmp_path, monkeypatch):
    instance = proof.RecoveryProof.__new__(proof.RecoveryProof)
    instance.failed_sha = "a" * 40
    root = tmp_path / "laya"
    (root / "sources" / instance.failed_sha).mkdir(parents=True)
    instance._directory = lambda p: {"ino": p.stat().st_ino}
    instance._absent = lambda *paths: None
    monkeypatch.setattr(proof, "LAYA_STATE", root)
    monkeypatch.setattr(proof.pwd, "getpwnam", lambda _: (_ for _ in ()).throw(KeyError()))
    monkeypatch.setattr(proof.grp, "getgrnam", lambda _: (_ for _ in ()).throw(KeyError()))
    monkeypatch.setattr(proof.subprocess, "check_output", lambda *a, **k: b"not-found\n")
    expected = instance._laya_unstarted()
    assert expected == instance._laya_unstarted()
    (root / "sources" / instance.failed_sha / "install.py").write_text("partial")
    with pytest.raises(proof.ProofError):
        instance._laya_unstarted()


def test_unchanged_retirement_accepts_only_exact_prepared_laya_source(tmp_path, monkeypatch):
    instance = proof.RecoveryProof.__new__(proof.RecoveryProof)
    instance.failed_sha, instance.production_sha = "a" * 40, "b" * 40
    root = tmp_path / "laya"
    candidate = root / "sources" / instance.failed_sha
    candidate.mkdir(parents=True)
    canonical = tmp_path / "canonical"
    source = canonical / "infra/laya"
    source.mkdir(parents=True)
    hashes = {}
    for name in proof.LAYA_ASSETS:
        data = ("canonical:" + name).encode()
        (source / name).write_bytes(data)
        (candidate / name).write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    (candidate / "source.json").write_text(json.dumps({
        "sha": instance.failed_sha, "old_sha": instance.production_sha,
        "old_has_decisions": False, "files": hashes,
    }))
    instance.bootstrap = SimpleNamespace(canonical_source=lambda _: canonical)
    instance._directory = lambda p: {"ino": p.stat().st_ino}
    instance._file = lambda p, *a: (p.read_bytes(), {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    instance._absent = lambda *paths: None
    monkeypatch.setattr(proof, "LAYA_STATE", root)
    monkeypatch.setattr(proof.pwd, "getpwnam", lambda _: (_ for _ in ()).throw(KeyError()))
    monkeypatch.setattr(proof.grp, "getgrnam", lambda _: (_ for _ in ()).throw(KeyError()))
    monkeypatch.setattr(proof.subprocess, "check_output", lambda *a, **k: b"not-found\n")
    result = instance._laya_unstarted()
    assert set(result["prepared_source"]) == {*proof.LAYA_ASSETS, "source.json"}
    (candidate / "install.py").write_text("changed")
    with pytest.raises(proof.ProofError, match="differs from failed revision"):
        instance._laya_unstarted()


@pytest.mark.parametrize("workspace_state", [
    "CLOSED_UNCHANGED_RELEASE",
    "ACKNOWLEDGED_LOST_CLOSURE_RECEIPT",
])
def test_unchanged_retirement_preserves_only_historically_closed_empty_source(
        tmp_path, monkeypatch, workspace_state):
    instance = proof.RecoveryProof.__new__(proof.RecoveryProof)
    instance.failed_sha, instance.production_sha = "a" * 40, "b" * 40
    old_sha = "c" * 40
    root = tmp_path / "laya"
    current = root / "sources" / instance.failed_sha
    old = root / "sources" / old_sha
    current.mkdir(parents=True)
    old.mkdir()
    instance._directory = lambda p: {"ino": p.stat().st_ino}
    instance._absent = lambda *paths: None
    old_identity = instance._directory(old)
    history = {old_sha: {"workspace": {"state": workspace_state}}}
    intent = {"snapshot": {"workspace": {"inventory": []},
                           "unstarted_laya": {str(old): old_identity}}}
    acknowledgment = {"old_sha": old_sha, "closure": {
        "state": "CLOSED_UNCHANGED_RELEASE", "workspace": intent["snapshot"]["workspace"]}}
    instance.bootstrap = SimpleNamespace(
        STATE=tmp_path / "release-state",
        _retired_history=lambda: history,
        _read_json=lambda path: acknowledgment if "lost-closure-receipt-acknowledgments" in str(path) else intent,
    )
    monkeypatch.setattr(proof, "LAYA_STATE", root)
    monkeypatch.setattr(proof.pwd, "getpwnam", lambda _: (_ for _ in ()).throw(KeyError()))
    monkeypatch.setattr(proof.grp, "getgrnam", lambda _: (_ for _ in ()).throw(KeyError()))
    monkeypatch.setattr(proof.subprocess, "check_output", lambda *a, **k: b"not-found\n")
    assert instance._laya_unstarted()[str(old)] == old_identity
    (old / "unexpected").write_text("changed")
    with pytest.raises(proof.ProofError, match="unclosed Laya preparation source"):
        instance._laya_unstarted()
    (old / "unexpected").unlink()
    history.clear()
    with pytest.raises(proof.ProofError, match="unclosed Laya preparation source"):
        instance._laya_unstarted()


def test_unchanged_retirement_rejects_laya_process(tmp_path, monkeypatch):
    instance = proof.RecoveryProof.__new__(proof.RecoveryProof)
    instance.failed_sha = "a" * 40
    root = tmp_path / "laya"
    (root / "sources" / instance.failed_sha).mkdir(parents=True)
    instance._directory = lambda p: {"ino": p.stat().st_ino}
    instance._absent = lambda *paths: None
    monkeypatch.setattr(proof, "LAYA_STATE", root)
    monkeypatch.setattr(proof.pwd, "getpwnam", lambda _: (_ for _ in ()).throw(KeyError()))
    monkeypatch.setattr(proof.grp, "getgrnam", lambda _: (_ for _ in ()).throw(KeyError()))
    outputs = iter((b"not-found\n", b"python /opt/reva-laya/current/serve.py\n"))
    monkeypatch.setattr(proof.subprocess, "check_output", lambda *a, **k: next(outputs))
    with pytest.raises(proof.ProofError):
        instance._laya_unstarted()


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
    deploy_source = (Path(__file__).parents[1] / "deploy.sh").read_text()
    assert 'acquire_remote_release_lock "deploy:${DEPLOY_MODE}"' in deploy_source
    for name, content in (("token", instance.token + "\n"), ("stage", str(staged) + "\n"), ("label", "deploy:backend\n"), ("started_at", "2026-09-09T00:00:00Z\n")):
        path = instance.lease / name
        path.write_text(content)
        path.chmod(0o600)
    return instance, source, actual


def test_stage_proves_exact_original_artifacts_and_unchanged_env(stage):
    instance, source, _ = stage
    assert instance._stage(source) == instance._stage(source)


@pytest.mark.parametrize("fault", ["token", "label", "extra", "hash", "canonical", "env", "manifest_duplicate", "env_mode"])
def test_stage_rejects_original_binding_drift(stage, fault):
    instance, source, actual = stage
    if fault == "token":
        (instance.lease / "token").write_text("different\n")
    elif fault == "label":
        (instance.lease / "label").write_text("backend\n")
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


@pytest.mark.parametrize("damage", ["receipt", "asset", "config", "recent", "restart"])
def test_installed_laya_closure_rejects_changed_or_new_runtime(damage):
    old = {"generation": "a" * 64, "unit_sha256": "b" * 64, "env_sha256": "c" * 64}
    receipt = {**old, "state": "INSTALLED"}
    candidate = dict(old)
    fields = {"NRestarts": "0", "ActiveEnterTimestampMonotonic": "1000000", "processes": {"12": "100"}}
    if damage == "receipt": receipt["state"] = "PREPARED"
    if damage == "asset": candidate["generation"] = "d" * 64
    if damage == "config": candidate["env_sha256"] = "d" * 64
    if damage == "recent": fields["ActiveEnterTimestampMonotonic"] = "200000000"
    if damage == "restart": fields["NRestarts"] = "1"
    with pytest.raises(proof.ProofError):
        proof.validate_installed_laya_binding(receipt, old, candidate, fields,
                                              started=1200, boot=1000, ticks_per_second=100)


def test_installed_laya_closure_accepts_only_same_installed_generation_predating_lease():
    expected = {"generation": "a" * 64, "unit_sha256": "b" * 64, "env_sha256": "c" * 64}
    fields = {"NRestarts": "0", "ActiveEnterTimestampMonotonic": "1000000", "processes": {"12": "100"}}
    proof.validate_installed_laya_binding({**expected, "state": "INSTALLED"}, expected, expected,
                                          fields, started=1200, boot=1000, ticks_per_second=100)
    fields["processes"]["13"] = "20000"
    with pytest.raises(proof.ProofError):
        proof.validate_installed_laya_binding({**expected, "state": "INSTALLED"}, expected, expected,
                                              fields, started=1200, boot=1000, ticks_per_second=100)


def installed_runtime_fixture(tmp_path, monkeypatch):
    instance = proof.RecoveryProof.__new__(proof.RecoveryProof)
    instance.production_sha, instance.failed_sha, origin_sha = (x * 40 for x in "abc")
    root, state = tmp_path / "sources", tmp_path / "state"
    laya = tmp_path / "laya"
    laya.mkdir()
    instance.source = root / ("d" * 40)
    hashes = {}
    for sha in (instance.production_sha, instance.failed_sha, origin_sha, "d" * 40):
        src = root / sha / "infra/laya"
        src.mkdir(parents=True)
        for name in proof.LAYA_ASSETS:
            data = ("reviewed " + name).encode()
            (src / name).write_bytes(data)
            hashes[name] = hashlib.sha256(data).hexdigest()
    exported = laya / "sources" / instance.failed_sha
    exported.mkdir(parents=True)
    for name in proof.LAYA_ASSETS:
        (exported / name).write_bytes((root / instance.failed_sha / "infra/laya" / name).read_bytes())
    (exported / "source.json").write_text(json.dumps({"sha": instance.failed_sha,
        "old_sha": instance.production_sha, "old_has_decisions": True, "files": hashes}))
    expected = {"generation": "1" * 64, "unit_sha256": "2" * 64, "env_sha256": "3" * 64}
    receipt = {**expected, "state": "INSTALLED", "candidate_sha": origin_sha, "lease": "4" * 64}
    (laya / "install.json").write_text(json.dumps(receipt))
    os.utime(laya / "install.json", (1000, 1000))
    success = state / instance.production_sha / "completed.json"
    success.parent.mkdir(parents=True)
    success.write_text(json.dumps({"sha": instance.production_sha, "state": "SUCCEEDED"}))
    os.utime(success, (1100, 1100))
    instance.lease, instance.stage, instance.proc = (tmp_path / n for n in ("lease", "stage", "proc"))
    for p in (instance.lease, instance.stage, instance.proc): p.mkdir()
    (instance.lease / "started_at").write_text("1970-01-01T00:33:20Z\n")
    (instance.proc / "stat").write_text("btime 100\n")
    process = instance.proc / "12"
    process.mkdir()
    (process / "stat").write_text("12 (synthetic) " + " ".join(["0"] * 19 + ["100"]))
    boot = instance.proc / "sys/kernel/random"
    boot.mkdir(parents=True)
    (boot / "boot_id").write_text("old-boot")
    for name in ("backend.env.rollback", "backend.env.candidate"):
        (instance.stage / name).write_text("same-config")
    unit, env = tmp_path / "unit", tmp_path / "env"
    unit.write_text("reviewed unit"); env.write_text("synthetic key")
    instance._file = lambda p, *args: (p.read_bytes(), {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    instance._directory = lambda p: {"directory": str(p)}
    instance._absent = lambda *paths: None
    instance.bootstrap = SimpleNamespace(STATE=state, canonical_source=lambda sha: root / sha)
    generation = tmp_path / "generation"
    calls = []
    service = {"MainPID": "12", "NRestarts": "0", "DropInPaths": ""}
    def service_identity(_):
        if service["DropInPaths"]:
            raise proof.ProofError("unexpected drop-in")
        return service.copy()
    installer = SimpleNamespace(UNIT=unit, ENV=env,
        parse_config=lambda raw: {"config": raw}, expected_install=lambda *a: (generation, b"unit", b"env", expected),
        reusable=lambda r, e: None, service_identity=service_identity,
        verify_install=lambda *a: calls.append("verify"),
        prepare=lambda *a: pytest.fail("no installation"), activate=lambda *a: pytest.fail("no activation"))
    instance._module = lambda *a: installer
    instance._pids = lambda _: ["12"]
    instance.systemd = SimpleNamespace(show=lambda unit, field: {
        "NeedDaemonReload": "no", "ActiveEnterTimestampMonotonic": "1000000", "ControlGroup": "/system.slice/reva-laya.service",
        "ExecStart": f"path={generation / 'venv/bin/python'}\nargv[]={generation / 'venv/bin/python'} -I {generation / 'serve.py'}\nignore_errors=no"}[field])
    instance.runtime = SimpleNamespace(ReleaseTransaction=SimpleNamespace(_stable_exec_start=lambda _, value: value))
    monkeypatch.setattr(proof, "LAYA_STATE", laya)
    return instance, installer, service, calls, laya


def test_installed_profile_proves_real_source_receipt_and_stable_runtime_without_mutation(tmp_path, monkeypatch):
    instance, installer, service, calls, laya = installed_runtime_fixture(tmp_path, monkeypatch)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = instance._laya_installed()
    assert result["profile"] == "installed-reuse-v1"
    assert calls == ["verify"]
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    # Post-closure verification uses the captured release time after the original lease is archived.
    (instance.lease / "started_at").rename(instance.lease / "archived")
    assert instance._laya_installed(started_at=result["started_at"]) == result


@pytest.mark.parametrize("damage", ["asset", "candidate_env", "receipt", "export", "origin",
                                     "success", "unit_override", "pid_drift", "boot_drift", "env_drift"])
def test_installed_profile_rejects_drift_before_or_during_readonly_proof(tmp_path, monkeypatch, damage):
    instance, installer, service, calls, laya = installed_runtime_fixture(tmp_path, monkeypatch)
    if damage == "asset": (instance.source / "infra/laya/serve.py").write_text("changed")
    elif damage == "candidate_env": (instance.stage / "backend.env.candidate").write_text("changed")
    elif damage == "receipt":
        p = laya / "install.json"; data = json.loads(p.read_text()); data["state"] = "PREPARING"; p.write_text(json.dumps(data))
    elif damage == "export": (laya / "sources" / instance.failed_sha / "unknown").write_text("extra")
    elif damage == "origin":
        installer.expected_install = lambda source, config: (tmp_path / "generation", b"unit", b"env", {"generation": source.parts[-3]})
    elif damage == "success": (instance.bootstrap.STATE / instance.production_sha / "completed.json").write_text('{}')
    elif damage == "unit_override": service["DropInPaths"] = "/tmp/override"
    elif damage == "pid_drift": installer.verify_install = lambda *a: service.update(MainPID="13")
    elif damage == "boot_drift": installer.verify_install = lambda *a: (instance.proc / "sys/kernel/random/boot_id").write_text("new-boot")
    elif damage == "env_drift": installer.verify_install = lambda *a: installer.ENV.write_text("changed")
    with pytest.raises(proof.ProofError):
        instance._laya_installed()


@pytest.mark.parametrize('unit', proof.UNITS[1:])
def test_legacy_base_requires_exact_security_dropin_and_effective_properties(unit):
    expected = proof.security_unit_contract(unit)
    directives = b''.join(key.encode() + b'=' + value.encode() + b'\n' for key, value in expected['directives'].items())
    legacy = b'[Service]\nUser=health-app\nRestart=always\n'
    canonical = legacy + directives
    dropin = b'[Service]\n' + directives
    assert proof.validate_unit_base(legacy, canonical, set(), unit, dropin, allow_legacy=True)
    assert not proof.validate_unit_base(canonical, canonical, set(), unit, dropin, allow_legacy=True)
    assert proof.validate_security_effective(unit, expected['effective']) == expected['effective']
    with pytest.raises(proof.ProofError):
        proof.validate_unit_base(legacy, canonical, set(), unit, dropin, allow_legacy=False)
    for key in expected['directives']:
        for suffix in (key.encode() + b'=\n', key.encode() + b'=unexpected\n'):
            with pytest.raises(proof.ProofError):
                proof.validate_unit_base(legacy + suffix, canonical, set(), unit, dropin, allow_legacy=True)
        with pytest.raises(proof.ProofError):
            proof.validate_unit_base(legacy, canonical, set(), unit, dropin.replace(key.encode()+b'=', b'Unknown='), allow_legacy=True)
    for key in expected['effective']:
        with pytest.raises(proof.ProofError):
            proof.validate_security_effective(unit, {**expected['effective'], key: 'unexpected'})
    with pytest.raises(proof.ProofError):
        proof.validate_unit_base(legacy.replace(b'health-app', b'root'), canonical, set(), unit, dropin, allow_legacy=True)
    with pytest.raises(proof.ProofError):
        proof.validate_unit_base(legacy+b'IPAddressAllow=any\n', canonical, set(), unit, dropin, allow_legacy=True)


def test_legacy_base_rejects_duplicate_security_canonical_and_dropin_assignments():
    unit = 'health-backend.service'
    expected = proof.security_unit_contract(unit)
    directives = b''.join(key.encode()+b'='+value.encode()+b'\n' for key,value in expected['directives'].items())
    legacy = b'[Service]\nUser=health-app\n'
    for canonical, dropin in ((legacy+directives+b'MemoryMax=2G\n',b'[Service]\n'+directives),
                              (legacy+directives,b'[Service]\n'+directives+b'IPAddressDeny=\n')):
        with pytest.raises(proof.ProofError):
            proof.validate_unit_base(legacy,canonical,set(),unit,dropin,allow_legacy=True)


@pytest.mark.parametrize('network', [False, True])
@pytest.mark.parametrize('legacy_drain', [False, True])
def test_units_proof_accepts_legacy_base_only_with_actual_exact_dropins(tmp_path, network, legacy_drain):
    source = Path(__file__).resolve().parents[1]
    instance = proof.RecoveryProof.__new__(proof.RecoveryProof)
    instance.systemd_root = tmp_path
    instance.installed_laya = True
    instance._network_guard = lambda old_source: {'profile': 'network-guard-v1'}
    candidates = {unit: (source / 'infra/systemd/dropins' / unit.replace('.service', '-runtime-state.conf')).read_bytes()
                  for unit in proof.UNITS[1:]}
    current_candidates = dict(candidates)
    import shutil
    canonical = tmp_path / 'canonical-production'
    shutil.copytree(source / 'infra/systemd', canonical / 'infra/systemd')
    source = canonical
    if legacy_drain:
        backend = candidates['health-backend.service']
        for line in (b'KillMode=mixed\n', b'TimeoutStopSec=45s\n', b'KillSignal=SIGTERM\n',
                     b'RestartKillSignal=SIGTERM\n', b'SendSIGKILL=yes\n', b'FinalKillSignal=SIGKILL\n'):
            backend = backend.replace(b'\n' + line, b'\n')
        backend = backend.replace(b' --timeout-graceful-shutdown 30', b'')
        candidates['health-backend.service'] = backend
        (source / 'infra/systemd/dropins/health-backend-runtime-state.conf').write_bytes(backend)
        base = source / 'infra/systemd/health-backend.service'
        original_base = base.read_bytes().replace(b' --timeout-graceful-shutdown 30', b'')
        for line in (b'KillMode=mixed\n', b'RestartKillSignal=SIGTERM\n',
                     b'SendSIGKILL=yes\n', b'FinalKillSignal=SIGKILL\n',
                     b'# Keep request-owned Pi children alive while the single worker drains.\n'):
            original_base = original_base.replace(b'\n' + line, b'\n')
        base.write_bytes(original_base)
        poison = source / 'backend/scripts/runtime_state_release_transaction.py'
        poison.parent.mkdir(parents=True)
        poison.write_text('raise AssertionError("historical Python must not execute")')
    instance.runtime = SimpleNamespace(_expected_candidate=current_candidates.__getitem__,
        BACKEND_DRAIN_EFFECTIVE={"KillMode": "mixed", "TimeoutStopUSec": "45s", "KillSignal": "15",
                                "RestartKillSignal": "15", "SendSIGKILL": "yes", "FinalKillSignal": "9"},
        ReleaseTransaction=SimpleNamespace(_stable_exec_start=lambda value: value))
    instance._file = lambda path, *args: (path.read_bytes(), {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    properties = {}
    for unit in proof.UNITS:
        original = (source / 'infra/systemd' / unit).read_bytes()
        if unit.endswith('.service'):
            keys = {key.encode() for key in proof.security_unit_contract(unit)['directives']}
            if unit == 'health-backend.service':
                keys |= {b'KillMode', b'TimeoutStopSec', b'KillSignal',
                         b'RestartKillSignal', b'SendSIGKILL', b'FinalKillSignal'}
            original = b''.join(line for line in original.splitlines(keepends=True)
                                if line.split(b'=', 1)[0] not in keys)
            directory = tmp_path / (unit + '.d')
            directory.mkdir()
            (directory / '80-reva-health-evidence-runtime.conf').write_bytes(proof.ACTIVATION)
            (directory / '90-runtime-state.conf').write_bytes(candidates[unit])
            paths = [str(directory / name) for name in ('80-reva-health-evidence-runtime.conf', '90-runtime-state.conf')]
            if network:
                (directory / 'security-network.conf').write_bytes(b'[Unit]\nRequires=health-network-guard.service\nAfter=health-network-guard.service\n')
                paths.append(str(directory / 'security-network.conf'))
            values = proof.security_unit_contract(unit)['effective']
            if unit == 'health-backend.service':
                values = {**values, **instance.runtime.BACKEND_DRAIN_EFFECTIVE}
                if legacy_drain:
                    values['KillMode'] = 'control-group'
        else:
            paths, values = [], {}
        (tmp_path / unit).write_bytes(original)
        properties[unit] = {**values, 'NeedDaemonReload': 'no', 'FragmentPath': str(tmp_path / unit), 'DropInPaths': ' '.join(paths)}
    instance.systemd = SimpleNamespace(show=lambda unit, key: properties[unit][key], is_enabled=lambda unit: 'enabled')
    worker = (source / 'infra/systemd/celery-worker.service').read_text()
    command = next(line.removeprefix('ExecStart=') for line in worker.splitlines() if line.startswith('ExecStart='))
    effective = {}
    for unit, raw in candidates.items():
        import re
        commands = re.findall(rb'^ExecStart=(.+)$', raw, re.M)
        unit_command = command if unit == 'celery-worker.service' else commands[0].decode()
        writable = re.findall(rb'^ReadWritePaths=(.+)$', raw, re.M)[0].decode()
        effective[unit] = {'ExecStart': f'path={unit_command.split()[0]}\nargv[]={unit_command}\nignore_errors=no',
                           'ReadWritePaths': writable}

    transaction = SimpleNamespace(_old_effective=lambda: effective, _stable_exec_start=lambda value: value,
                                  _validate_candidate_effective=lambda value: None, _stable_effective_snapshot=lambda value: value)
    result = instance._units(source, transaction)
    assert all('legacy_security_effective' in result[unit] for unit in proof.UNITS[1:])
    assert ('network_guard' in result) is network
    dropin = tmp_path / 'health-backend.service.d/90-runtime-state.conf'
    dropin.write_bytes(dropin.read_bytes() + b'CapabilityBoundingSet=CAP_SYS_ADMIN\n')
    with pytest.raises(proof.ProofError, match='drop-in bytes differ'):
        instance._units(source, transaction)
    dropin.write_bytes(candidates['health-backend.service'])
    for prop in instance.runtime.BACKEND_DRAIN_EFFECTIVE:
        expected = properties['health-backend.service'][prop]
        properties['health-backend.service'][prop] = 'unexpected'
        with pytest.raises(proof.ProofError, match='effective backend drain differs'):
            instance._units(source, transaction)
        properties['health-backend.service'][prop] = expected
    # Whole-generation bytes and effective commands cannot be mixed.
    if legacy_drain:
        dropin.write_bytes(current_candidates['health-backend.service'])
        with pytest.raises(proof.ProofError, match='drop-in bytes differ'):
            instance._units(source, transaction)
        dropin.write_bytes(candidates['health-backend.service'])
        properties['health-backend.service']['KillMode'] = 'mixed'
        with pytest.raises(proof.ProofError, match='effective backend drain differs'):
            instance._units(source, transaction)
        properties['health-backend.service']['KillMode'] = 'control-group'
    else:
        older = current_candidates['health-backend.service']
        for line in (b'KillMode=mixed\n', b'TimeoutStopSec=45s\n', b'KillSignal=SIGTERM\n',
                     b'RestartKillSignal=SIGTERM\n', b'SendSIGKILL=yes\n', b'FinalKillSignal=SIGKILL\n'):
            older = older.replace(b'\n' + line, b'\n')
        older = older.replace(b' --timeout-graceful-shutdown 30', b'')
        dropin.write_bytes(older)
        with pytest.raises(proof.ProofError, match='drop-in bytes differ'):
            instance._units(source, transaction)
        dropin.write_bytes(candidates['health-backend.service'])
    for unit in candidates:
        for prop, suffix, error in [('ExecStart', ' --unexpected', 'command differs'),
                                    ('ReadWritePaths', ' /unexpected', 'writable paths differ')]:
            original_value = effective[unit][prop]
            effective[unit][prop] += suffix
            with pytest.raises(proof.ProofError, match=error):
                instance._units(source, transaction)
            effective[unit][prop] = original_value
    for unit in candidates:
        canonical_dropin = source / 'infra/systemd/dropins' / unit.replace('.service', '-runtime-state.conf')
        original_bytes = canonical_dropin.read_bytes()
        canonical_dropin.write_bytes(original_bytes + b'ReadWritePaths=/unexpected\n')
        with pytest.raises(proof.ProofError, match='canonical production runtime profile unsupported'):
            instance._units(source, transaction)
        canonical_dropin.write_bytes(original_bytes)
    properties['health-backend.service']['MemoryMax'] = 'infinity'
    with pytest.raises(proof.ProofError, match='effective security composition differs'):
        instance._units(source, transaction)


def network_guard_fixture(tmp_path):
    source = Path(__file__).resolve().parents[1]
    instance = proof.RecoveryProof.__new__(proof.RecoveryProof)
    instance.source = source
    instance.failed_sha = 'a' * 40
    instance.installed_laya = True
    instance.production = tmp_path / 'production'
    instance.systemd_root = tmp_path / 'systemd'
    instance.proc = tmp_path / 'proc'
    instance.lease = tmp_path / 'lease'
    for directory in (instance.production / 'scripts', instance.systemd_root, instance.proc / 'sys/kernel/random', instance.lease):
        directory.mkdir(parents=True)
    instance.bootstrap = SimpleNamespace(canonical_source=lambda sha: source)
    instance._file = lambda path, *args: (path.read_bytes(), {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    instance._no_jobs = lambda: None
    instance._pids = lambda unit: []
    instance.runtime = SimpleNamespace(ReleaseTransaction=SimpleNamespace(_stable_exec_start=lambda _, value: value))
    script = source / 'scripts/harden_public_host.py'
    (instance.production / 'scripts/harden_public_host.py').write_bytes(script.read_bytes())
    (instance.systemd_root / 'health-network-guard.service').write_bytes((source / 'infra/systemd/health-network-guard.service').read_bytes())
    (instance.proc / 'stat').write_text('btime 1000\n')
    (instance.proc / 'sys/kernel/random/boot_id').write_text('01234567-0123-4123-8123-0123456789ab\n')
    (instance.lease / 'started_at').write_text('1970-01-01T00:21:40Z\n')
    guard = 'health-network-guard.service'
    command = '/usr/bin/python3 -I -S -B /opt/health-app/scripts/harden_public_host.py --network'
    properties = {guard: {
        'FragmentPath': str(instance.systemd_root / guard), 'DropInPaths': '', 'NeedDaemonReload': 'no',
        'ActiveState': 'active', 'SubState': 'exited', 'Result': 'success', 'Type': 'oneshot',
        'RemainAfterExit': 'yes', 'MainPID': '0', 'NRestarts': '0', 'ExecMainCode': '1', 'ExecMainStatus': '0',
        'ActiveEnterTimestampMonotonic': '100000003', 'ExecMainStartTimestampMonotonic': '100000001',
        'ExecMainExitTimestampMonotonic': '100000002',
        'ExecStart': f'path=/usr/bin/python3\nargv[]={command}\nignore_errors=no',
        'ExecStartPre': '', 'ExecStartPost': '', 'ExecCondition': '', 'Environment': '', 'EnvironmentFiles': '',
        'User': '', 'Group': '', 'WorkingDirectory': '',
        'Requires': 'system.slice sysinit.target',
        'After': 'basic.target sysinit.target system.slice network-pre.target systemd-journald.socket',
        'Before': 'health-backend.service celery-worker.service shutdown.target celery-beat.service health-frontend-security-preflight.service health-frontend.service multi-user.target',
    }}
    for unit in proof.UNITS[1:]:
        directory = instance.systemd_root / (unit + '.d')
        directory.mkdir()
        (directory / 'security-network.conf').write_bytes(b'[Unit]\nRequires=health-network-guard.service\nAfter=health-network-guard.service\n')
        properties[unit] = {
            'Requires': 'system.slice sysinit.target -.mount health-network-guard.service' + (' health-backend.socket' if unit == 'health-backend.service' else ''),
            'After': 'basic.target systemd-journald.socket systemd-tmpfiles-setup.service sysinit.target system.slice redis-server.service tmp.mount health-network-guard.service network-online.target -.mount postgresql.service'
                     + (' health-backend.socket' if unit == 'health-backend.service' else ' systemd-remount-fs.service' if unit == 'celery-beat.service' else ''),
            'Before': 'multi-user.target shutdown.target',
            'DropInPaths': ' '.join(str(directory / name) for name in ('80-reva-health-evidence-runtime.conf', '90-runtime-state.conf', 'security-network.conf')),
            'NeedDaemonReload': 'no',
        }
    instance.systemd = SimpleNamespace(show=lambda unit, key: properties[unit][key], is_enabled=lambda unit: 'enabled')
    return instance, source, properties


@pytest.mark.parametrize('damage', [None, 'unit', 'script', 'dropin', 'override', 'dependency', 'guard_dependency', 'disabled',
                                  'reload', 'inactive', 'running', 'failed', 'restarted', 'recent', 'invalid_time',
                                  'extra_command', 'env', 'pid', 'changed', 'old_mode', 'partial', 'order'])
def test_network_guard_proof_rejects_unproven_composition(tmp_path, damage):
    instance, source, properties = network_guard_fixture(tmp_path)
    guard = properties['health-network-guard.service']
    business = properties['health-backend.service']
    if damage in ('unit', 'script', 'dropin'):
        path = {'unit': instance.systemd_root / 'health-network-guard.service',
                'script': instance.production / 'scripts/harden_public_host.py',
                'dropin': instance.systemd_root / 'health-backend.service.d/security-network.conf'}[damage]
        path.write_bytes(path.read_bytes() + b'# changed\n')
    if damage == 'override': guard['DropInPaths'] = '/run/systemd/system/service.d/override.conf'
    if damage == 'dependency': business['Requires'] += ' extra.service'
    if damage == 'guard_dependency': guard['After'] += ' extra.service'
    if damage == 'disabled': instance.systemd.is_enabled = lambda unit: 'disabled'
    if damage == 'reload': guard['NeedDaemonReload'] = 'yes'
    if damage == 'inactive': guard['ActiveState'] = 'inactive'
    if damage == 'running': guard['SubState'] = 'running'
    if damage == 'failed': guard['ExecMainStatus'] = '1'
    if damage == 'restarted': guard['NRestarts'] = '1'
    if damage == 'recent': guard['ActiveEnterTimestampMonotonic'] = '250000000'
    if damage == 'invalid_time': guard['ExecMainStartTimestampMonotonic'] = 'unknown'
    if damage == 'extra_command': guard['ExecStartPre'] = '/bin/true'
    if damage == 'env': guard['Environment'] = 'UNEXPECTED=yes'
    if damage == 'pid': instance._pids = lambda unit: ['123']
    if damage == 'old_mode': instance.installed_laya = False
    if damage == 'partial': business['DropInPaths'] = business['DropInPaths'].rsplit(' ', 1)[0]
    if damage == 'order': guard['ExecMainStartTimestampMonotonic'] = '100000004'
    if damage == 'changed':
        calls = 0
        original_show = instance.systemd.show
        def show(unit, key):
            nonlocal calls
            if key == 'ActiveEnterTimestampMonotonic':
                calls += 1
                return '100000003' if calls == 1 else '100000004'
            return original_show(unit, key)
        instance.systemd.show = show
    if damage:
        with pytest.raises(proof.ProofError): instance._network_guard(source)
    else:
        result = instance._network_guard(source)
        assert result['profile'] == 'network-guard-v1'
        assert result == instance._network_guard(source, started_at=result['started_at'])
