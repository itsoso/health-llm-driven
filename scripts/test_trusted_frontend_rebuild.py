"""Offline tests; npm configuration probes never install or use the network."""

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import uuid

import pytest


def load():
    path = Path(__file__).with_name("trusted_frontend_rebuild.py")
    spec = importlib.util.spec_from_file_location("frontend_rebuild_tested", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_binding_refuses_drift_and_unproven_backend():
    m = load()
    args = ("a" * 40, "b" * 40, "c" * 40, "c" * 40)
    m.validate_binding(*args, {"sha": "b" * 40, "state": "SUCCEEDED"})
    for live, tree, receipt in [
        ("d" * 40, "c" * 40, {"sha": "b" * 40, "state": "SUCCEEDED"}),
        ("b" * 40, "d" * 40, {"sha": "b" * 40, "state": "SUCCEEDED"}),
        ("b" * 40, "c" * 40, {"sha": "b" * 40, "state": "STARTED"}),
        ("b" * 40, "c" * 40, {"sha": "a" * 40, "state": "SUCCEEDED"}),
    ]:
        with pytest.raises(m.RebuildError):
            m.validate_binding("a" * 40, "b" * 40, "c" * 40, tree, receipt, live_sha=live)


def test_build_is_unprivileged_and_cannot_read_production_or_release_credentials():
    m = load()
    command = m.build_command("a" * 32, Path("/var/lib/reva-frontend-builds") / ("a" * 32))
    joined = " ".join(command)
    for required in ["DynamicUser=yes", "ProtectSystem=strict", "ProtectHome=yes",
                     "ProtectProc=invisible", "NoNewPrivileges=yes", "KillMode=control-group",
                     "WorkingDirectory=/tmp/reva-frontend", "BindPaths="]:
        assert required in joined
    denied = next(arg.split("=", 2)[2].split() for arg in command if arg.startswith("--property=InaccessiblePaths="))
    for required in ("/opt", "/var/lib", "/var/cache", "/var/log", "/var/backups",
                     "/srv", "/data", "/mnt", "/media", "/etc/reva-release", "/etc/health-app"):
        assert "-" + required in denied
    assert "npm ci --ignore-scripts" in joined
    assert "npm run build" in joined
    assert "--collect" not in command  # keep unit evidence until separately verified


def test_real_npm_starts_with_isolated_distinct_configuration(tmp_path):
    m = load()
    command = m.build_command("a" * 32, m.BUILDS / ("a" * 32))
    start, end = command.index("/usr/bin/env") + 2, command.index("/bin/bash")
    environment = dict(argument.split("=", 1) for argument in command[start:end])
    # Substitute only the private sandbox mount with a local synthetic directory.
    environment = {key: value.replace("/tmp/reva-home", str(tmp_path / "home"))
                   .replace("/tmp/reva-cache", str(tmp_path / "cache"))
                   for key, value in environment.items()}
    (tmp_path / "home").mkdir()
    npm = shutil.which("npm")
    assert npm is not None, "npm startup is a required release regression"
    environment["PATH"] = str(Path(npm).parent) + os.pathsep + environment["PATH"]
    result = subprocess.run([npm, "config", "get", "registry"], cwd=tmp_path,
                            env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "https://registry.npmjs.org/"
    assert environment["npm_config_userconfig"] != environment["npm_config_globalconfig"]


def test_deploy_entry_precedes_env_and_never_reinterprets_normal_frontend_mode():
    script = (Path(__file__).resolve().parents[1] / "deploy.sh").read_text()
    assert script.index('--rebuild-deployed-frontend') < script.index('ENV_FILE=')
    assert '"$SCRIPT_DIR/scripts/trusted_frontend_rebuild.py" "$@"' in script
    assert 'if ! verify_deployed_revision; then' in script


def test_success_receipt_is_frontend_specific_and_binds_both_revisions():
    m = load()
    value = m.receipt("a" * 40, "b" * 40, "c" * 32, "d" * 40, "FRONTEND_SUCCEEDED", "e" * 64)
    assert value == {"kind": "frontend-rebuild", "publisher_sha": "a" * 40,
                     "production_sha": "b" * 40, "operation_id": "c" * 32,
                     "frontend_tree": "d" * 40, "state": "FRONTEND_SUCCEEDED",
                     "artifact_digest": "e" * 64}
    assert "sha" not in value


def test_artifact_manifest_rejects_links_outside_bundle(tmp_path):
    m = load()
    (tmp_path / "safe").write_text("payload")
    first = m.artifact_digest(tmp_path)
    (tmp_path / "safe").write_text("changed")
    assert m.artifact_digest(tmp_path) != first
    (tmp_path / "escape").symlink_to("/etc/passwd")
    with pytest.raises(m.RebuildError):
        m.artifact_digest(tmp_path)


def test_build_env_file_rejects_unknown_keys_and_expansion():
    m = load()
    assert m.public_build_env("BACKEND_URL=http://127.0.0.1:8000\n") == {"BACKEND_URL": "http://127.0.0.1:8000"}
    for value in ["SECRET_KEY=secret", "BACKEND_URL=$(id)", "BACKEND_URL=https://user:pass@example.com", "NODE_OPTIONS=--require=evil", "BACKEND_URL=http://127.0.0.1:8000\nBACKEND_URL=http://localhost:8000"]:
        with pytest.raises(m.RebuildError):
            m.public_build_env(value)


def test_unfinished_frontend_audit_blocks_later_backend_operations(tmp_path, monkeypatch):
    path = Path(__file__).with_name("trusted_release_server.py")
    spec = importlib.util.spec_from_file_location("frontend_audit_server", path)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    monkeypatch.setattr(server, "secure_path", lambda *a, **kw: None)
    monkeypatch.setattr(server, "_read_private", lambda p: p.read_bytes())
    root = tmp_path / "frontend-rebuilds"
    root.mkdir(mode=0o700)
    op = root / ("c" * 32)
    op.mkdir(mode=0o700)
    m = load()
    intent = m.receipt("a" * 40, "b" * 40, op.name, "d" * 40, "FRONTEND_STARTED", None)
    (op / "intent.json").write_text(json.dumps(intent))
    with pytest.raises(server.LaunchError):
        server.assert_frontend_rebuild_history(tmp_path)
    for name, state in [("install-started.json", "FRONTEND_INSTALLING"), ("verified.json", "FRONTEND_VERIFIED"), ("completed.json", "FRONTEND_SUCCEEDED")]:
        (op / name).write_text(json.dumps(m.receipt("a" * 40, "b" * 40, op.name, "d" * 40, state, "e" * 64)))
    (op / "before.json").write_text(json.dumps({"publisher_sha": "a" * 40, "production_sha": "b" * 40, "operation_id": op.name, "frontend_tree": "d" * 40}))
    (op / "build.log").write_text("build complete")
    (op / "previous-next").mkdir()
    (op / "previous-node-modules").mkdir()
    server.assert_frontend_rebuild_history(tmp_path)
    (op / "failed.json").write_text("{}")
    with pytest.raises(server.LaunchError):
        server.assert_frontend_rebuild_history(tmp_path)


def test_preinstall_failure_requires_exact_log_inventory_and_receipts(tmp_path, monkeypatch):
    m = load()
    server = load_server(monkeypatch)
    operation = tmp_path / ("c" * 32)
    operation.mkdir()
    intent = m.receipt("a" * 40, "b" * 40, operation.name, "d" * 40, "FRONTEND_STARTED", None)
    before = {key: intent[key] for key in ("publisher_sha", "production_sha", "operation_id", "frontend_tree")}
    for name, value in [("intent.json", intent), ("before.json", before),
                        ("failed.json", {**intent, "state": "FRONTEND_NEEDS_OPERATOR"})]:
        (operation / name).write_text(json.dumps(value))
    (operation / "build.log").write_bytes(server.FRONTEND_NPM_CONFIG_FAILURE)
    proof = server.frontend_preinstall_failure(operation)
    assert set(proof) == {"intent.json", "before.json", "build.log", "failed.json"}
    (operation / "build.log").write_bytes(server.FRONTEND_NPM_CONFIG_FAILURE + b"another command\n")
    with pytest.raises(server.LaunchError):
        server.frontend_preinstall_failure(operation)
    (operation / "build.log").write_bytes(server.FRONTEND_NPM_CONFIG_FAILURE)
    (operation / "install-started.json").write_text("{}")
    with pytest.raises(server.LaunchError):
        server.frontend_preinstall_failure(operation)


def load_server(monkeypatch):
    path = Path(__file__).with_name("trusted_release_server.py")
    spec = importlib.util.spec_from_file_location("frontend_retirement_server", path)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    monkeypatch.setattr(server, "secure_path", lambda *a, **kw: None)
    monkeypatch.setattr(server, "_read_private", lambda p: p.read_bytes())
    return server


def test_retirement_preserves_failed_audit_and_archives_lease_before_release(tmp_path, monkeypatch):
    m = load()
    monkeypatch.setattr(m, "STATE", tmp_path)
    monkeypatch.setattr(m, "LEASE", tmp_path / "active-lease")
    monkeypatch.setattr(m, "retired_lease", lambda op: tmp_path / "retired-lease")
    m.LEASE.mkdir(mode=0o700)
    for name in ("token", "label", "stage", "started_at"):
        (m.LEASE / name).write_text(name)
    events = []
    def write(path, data):
        events.append(path.name)
        with path.open("xb") as stream:
            stream.write(data)
    server = SimpleNamespace(_write_private=write, _sync_directory=lambda p: events.append("sync"),
                             secure_path=lambda *a, **kw: None)
    original = m.LEASE.stat().st_ino
    plan = {"operation_id": "c" * 32}
    def inspect(archived=False):
        assert (m.retired_lease(plan["operation_id"]) if archived else m.LEASE).is_dir()
        events.append("inspect-archived" if archived else "inspect-live")
        return plan
    def move(args, **kwargs):
        assert args[:4] == ["/usr/bin/mv", "--no-clobber", "-T", "--"]
        assert "intent.json" in events and all(n in events for n in ("token", "label", "stage", "started_at"))
        Path(args[-2]).rename(args[-1])
    monkeypatch.setattr(m, "run", move)
    result = m.retire_failure(plan, inspect, server)
    assert result["state"] == "CLOSED_PREINSTALL_FRONTEND_FAILURE"
    assert len(result["receipt"]) == 64
    assert not m.LEASE.exists()
    assert m.retired_lease(plan["operation_id"]).stat().st_ino == original
    closure = tmp_path / "frontend-rebuild-closures" / plan["operation_id"]
    assert (closure / "lease/token").read_text() == "token"
    assert not (closure / "acknowledged.json").exists()
    assert result["receipt"] not in (closure / "intent.json").read_text()
    with pytest.raises(m.RebuildError):
        m.retire_failure(plan, inspect, server)


def test_terminal_unit_rejects_live_or_unknown_state(monkeypatch):
    m = load()
    monkeypatch.setattr(m, "run", lambda *a, **kw: "ActiveState=active\nSubState=running\nMainPID=7\nControlPID=0\nResult=success\nExecMainCode=1\nExecMainStatus=0\nControlGroup=\n")
    with pytest.raises(m.RebuildError):
        m.failed_build_unit("c" * 32)


@pytest.fixture
def retirement(tmp_path, monkeypatch):
    m = load()
    server = load_server(monkeypatch)
    monkeypatch.setattr(m, "STATE", tmp_path)
    monkeypatch.setattr(m, "LEASE", tmp_path / "active")
    monkeypatch.setattr(m, "retired_lease", lambda op: tmp_path / "retired")
    operation = "c" * 32
    audit = tmp_path / "frontend-rebuilds" / operation
    audit.mkdir(parents=True, mode=0o700)
    audit.parent.chmod(0o700)
    original = m.receipt("a" * 40, "b" * 40, operation, "d" * 40, "FRONTEND_STARTED", None)
    for name, data in (("intent.json", original), ("before.json", original),
                       ("failed.json", {**original, "state": "FRONTEND_NEEDS_OPERATOR"})):
        server._write_private(audit / name, json.dumps(data).encode())
    server._write_private(audit / "build.log", server.FRONTEND_NPM_CONFIG_FAILURE)
    m.LEASE.mkdir(mode=0o700)
    for name, value in {"label": "frontend-rebuild", "stage": str(audit), "token": "e" * 64, "started_at": "1789999999"}.items():
        server._write_private(m.LEASE / name, (value + "\n").encode())
    plan = {"kind": "frontend-preinstall-closure", "state": "CLOSING", "publisher_sha": "f" * 40,
            "production_sha": "b" * 40, "operation_id": operation, "old_publisher_sha": "a" * 40,
            "old_code_sha256": server.FRONTEND_PREINSTALL_CODE_SHA256,
            "failure": server.frontend_preinstall_failure(audit),
            "lease": {"directory": {"ino": m.LEASE.stat().st_ino},
                      "files": {p.name: m.data_fingerprint(p)[0] for p in m.LEASE.iterdir()}},
            "snapshot": {}, "frontend_runtime": {}, "build_digest": "e" * 64, "launcher": {}, "unit": {}}
    def move(args, **kwargs):
        assert args[:4] == ["/usr/bin/mv", "--no-clobber", "-T", "--"]
        Path(args[-2]).rename(args[-1])
    monkeypatch.setattr(m, "run", move)
    return m, server, audit, plan, lambda archived=False: plan


def test_closure_requires_issued_receipt_and_history_survives_future_deployment(retirement):
    m, server, audit, plan, inspect = retirement
    result = m.retire_failure(plan, inspect, server)
    with pytest.raises(server.LaunchError):
        server.assert_frontend_rebuild_history(m.STATE)
    gate = SimpleNamespace(verify_release=lambda *a: None)
    with pytest.raises(m.RebuildError):
        m.acknowledge_retirement(plan["publisher_sha"], plan["production_sha"], audit.name, server, gate, "0" * 64)
    m.acknowledge_retirement(plan["publisher_sha"], plan["production_sha"], audit.name, server, gate, result["receipt"])
    server.assert_frontend_rebuild_history(m.STATE)
    # Runtime state is not consulted for a historical closure; real deployments
    # can change SHA, services and volatile /run archives without self-blocking.
    assert server.frontend_closure_proof(audit, m.STATE)["failure"] == plan["failure"]
    assert json.loads((audit / "failed.json").read_text())["state"] == "FRONTEND_NEEDS_OPERATOR"


@pytest.mark.parametrize("change", ["intent", "failure", "archive", "ack", "extra", "orphan", "old-code", "evidence"])
def test_historical_closure_tampering_blocks(retirement, change):
    m, server, audit, plan, inspect = retirement
    result = m.retire_failure(plan, inspect, server)
    gate = SimpleNamespace(verify_release=lambda *a: None)
    m.acknowledge_retirement(plan["publisher_sha"], plan["production_sha"], audit.name, server, gate, result["receipt"])
    closure = m.STATE / "frontend-rebuild-closures" / audit.name
    if change == "intent":
        (closure / "intent.json").write_text("{}")
    elif change == "failure":
        (audit / "failed.json").write_text("{}")
    elif change == "archive":
        (closure / "lease/token").write_text("x" * 64 + "\n")
    elif change == "ack":
        (closure / "acknowledged.json").unlink()
    elif change == "extra":
        (audit / "install-started.json").write_text("{}")
    elif change == "orphan":
        (closure.parent / ("9" * 32)).mkdir(mode=0o700)
    else:
        value = json.loads((closure / "intent.json").read_text())
        value["old_code_sha256" if change == "old-code" else "evidence_sha256"] = "0" * 64
        (closure / "intent.json").write_text(json.dumps(value))
    with pytest.raises((server.LaunchError, FileNotFoundError)):
        server.assert_frontend_rebuild_history(m.STATE)


@pytest.mark.parametrize("point", ["intent", "archive", "move", "postcheck", "terminal", "fsync"])
def test_retirement_interruption_never_issues_receipt_or_retries(retirement, monkeypatch, point):
    m, server, audit, plan, original_inspect = retirement
    write = server._write_private
    def fail():
        raise OSError("synthetic interrupted operation")
    def guarded_write(path, data):
        if ((point == "intent" and path.name == "intent.json")
                or (point == "archive" and path.name == "token")
                or (point == "terminal" and path.name == "completed.json")):
            fail()
        write(path, data)
    monkeypatch.setattr(server, "_write_private", guarded_write)
    if point == "move":
        monkeypatch.setattr(m, "run", lambda *a, **kw: fail())
    if point == "fsync":
        sync = server._sync_directory
        def guarded_sync(path):
            if (path / "completed.json").exists():
                fail()
            sync(path)
        monkeypatch.setattr(server, "_sync_directory", guarded_sync)
    def inspect(archived=False):
        if point == "postcheck" and archived:
            fail()
        return original_inspect(archived=archived)
    with pytest.raises(OSError):
        m.retire_failure(plan, inspect, server)
    with pytest.raises((server.LaunchError, FileNotFoundError)):
        server.assert_frontend_rebuild_history(m.STATE)
    with pytest.raises(m.RebuildError):
        m.retire_failure(plan, inspect, server)
    assert (audit / "failed.json").exists()


@pytest.mark.parametrize("key,value", [("ActiveState", "inactive"), ("MainPID", "123"), ("ControlPID", "123"),
                                      ("Result", "success"), ("ControlGroup", "/system.slice/build.service"),
                                      ("ExecMainStatus", "2")])
def test_failed_unit_exact_negative_proof(monkeypatch, key, value):
    m = load()
    values = {"ActiveState": "failed", "SubState": "failed", "MainPID": "0", "ControlPID": "0",
              "Result": "exit-code", "ExecMainCode": "1", "ExecMainStatus": "1", "ControlGroup": ""}
    monkeypatch.setattr(m, "run", lambda *a, **kw: "\n".join(k + "=" + v for k, v in values.items()))
    assert m.failed_build_unit("c" * 32) == values
    values[key] = value
    with pytest.raises(m.RebuildError):
        m.failed_build_unit("c" * 32)


@pytest.mark.parametrize("fault", [None, "code", "receipt", "live-sha", "production", "process", "unit", "snapshot", "lock", "ci"])
def test_inspect_retirement_checks_source_scope_and_live_evidence(retirement, monkeypatch, fault):
    m, server, audit, plan, _ = retirement
    old_source = m.STATE / "old-source"
    (old_source / "scripts").mkdir(parents=True)
    old_entry = old_source / "scripts/trusted_frontend_rebuild.py"
    old_entry.write_bytes(b"synthetic reviewed publisher")
    monkeypatch.setattr(server, "FRONTEND_PREINSTALL_CODE_SHA256", hashlib.sha256(old_entry.read_bytes()).hexdigest())
    if fault == "code":
        old_entry.write_bytes(b"unreviewed")
    before = {**json.loads((audit / "before.json").read_text()), "snapshot": {"services": "same"}}
    (audit / "before.json").write_text(json.dumps(before))
    monkeypatch.setattr(m, "BUILDS", m.STATE / "builds")
    stage = m.BUILDS / audit.name
    stage.mkdir(parents=True, mode=0o700)
    (stage / "input").write_text("public canonical source")
    (m.STATE / "launcher.lock").write_text("")
    monkeypatch.setattr(server, "validate_metadata", lambda *a, **kw: None)
    monkeypatch.setattr(m, "secure_entry", lambda *a: None)
    monkeypatch.setattr(m, "lease_evidence", lambda *a: plan["lease"])
    monkeypatch.setattr(m, "git", lambda source, *args: ("9" * 40 if fault == "live-sha" else "b" * 40)
                        if source == m.PRODUCTION else "d" * 40)
    def checked(tag):
        if fault == tag:
            raise m.RebuildError("synthetic failed gate")
    monkeypatch.setattr(m, "assert_unchanged", lambda *a: checked("snapshot"))
    monkeypatch.setattr(m, "failed_build_unit", lambda *a: checked("unit"))
    monkeypatch.setattr(m, "run", lambda *a, **kw: json.dumps([{"name": "health-frontend", "pid": 42,
                                                              "pm2_env": {"restart_time": 0, "pm_uptime": 123}}]))
    helper = SimpleNamespace(_assert_lock=lambda *a: checked("lock"))
    def read(path):
        if path.name == "completed.json":
            return {"sha": "b" * 40, "state": "STARTED" if fault == "receipt" else "SUCCEEDED"}
        return json.loads(path.read_text())
    bootstrap = SimpleNamespace(_read_json=read, canonical_source=lambda *a: old_source,
                                _recovery_process_proof=lambda: checked("process"))
    gate = SimpleNamespace(verify_release=lambda *a: checked("ci"), _latest=lambda *a: None, _get_json=None)
    args = ("f" * 40, "9" * 40 if fault == "production" else "b" * 40, audit.name,
            old_source, helper, bootstrap, server, gate, 1)
    if fault:
        with pytest.raises(m.RebuildError):
            m.inspect_failed(*args)
    else:
        result = m.inspect_failed(*args)
        assert result["old_code_sha256"] == server.FRONTEND_PREINSTALL_CODE_SHA256
        assert result["frontend_runtime"]["pid"] == 42
        assert result["failure"] == server.frontend_preinstall_failure(audit)


@pytest.fixture
def execution(tmp_path, monkeypatch):
    m = load()
    for name, path in [("STATE", tmp_path / "state"), ("PRODUCTION", tmp_path / "production"),
                       ("BUILDS", tmp_path / "builds"), ("LEASE", tmp_path / "lease")]:
        monkeypatch.setattr(m, name, path)
    m.STATE.mkdir()
    m.PRODUCTION.mkdir()
    (m.PRODUCTION / "frontend").mkdir()
    for name in (".next", "node_modules"):
        path = m.PRODUCTION / "frontend" / name
        path.mkdir()
        (path / "payload").write_text("old")
    events = []
    def prepare(source, stage, environment):
        events.append("build-inputs")
        for name in (".next", "node_modules"):
            path = stage / "frontend" / name
            path.mkdir(parents=True)
            (path / "payload").write_text("new")
    monkeypatch.setattr(m, "copy_build_inputs", prepare)
    monkeypatch.setattr(m.subprocess, "run", lambda *a, **kw: events.append("build"))
    monkeypatch.setattr(m, "freeze_artifacts", lambda *a: "e" * 64)
    monkeypatch.setattr(m, "assert_unchanged", lambda *a: events.append("unchanged"))
    monkeypatch.setattr(m, "run", lambda args, **kw: events.append(args[1]))
    monkeypatch.setattr(m, "assert_frontend_stopped", lambda: events.append("stopped"))
    monkeypatch.setattr(m, "verify_pages", lambda: events.append("readback"))
    def write(path, data):
        with path.open("xb") as stream:
            stream.write(data)
        path.chmod(0o600)
    server = SimpleNamespace(_write_private=write, _sync_directory=lambda p: None, secure_path=lambda *a, **kw: None)
    helper = SimpleNamespace(_lease_identity=lambda *a: ((1, 2), (1, 3)))
    plan = {"publisher_sha": "a" * 40, "production_sha": "b" * 40,
            "operation_id": "c" * 32, "frontend_tree": "d" * 40, "public_build_env": {}}
    return m, plan, helper, server, events


def test_execution_preserves_old_artifacts_and_only_stops_frontend(execution):
    m, plan, helper, server, events = execution
    result = m.execute(plan, Path("/unused"), helper, None, server)
    assert result["state"] == "FRONTEND_SUCCEEDED"
    assert events == ["build-inputs", "build", "unchanged", "stop", "stopped", "restart", "readback", "unchanged"]
    audit = m.STATE / "frontend-rebuilds" / plan["operation_id"]
    assert (audit / "previous-next/payload").read_text() == "old"
    assert (audit / "previous-node-modules/payload").read_text() == "old"
    assert (m.PRODUCTION / "frontend/.next/payload").read_text() == "new"
    assert not m.LEASE.exists()
    assert not (m.STATE / plan["publisher_sha"]).exists()
    with pytest.raises(FileExistsError):
        m.execute(plan, Path("/unused"), helper, None, server)


@pytest.mark.parametrize("failure", ["assert_unchanged", "assert_frontend_stopped", "verify_pages"])
def test_failed_or_unverified_execution_retains_lease_and_never_claims_success(execution, monkeypatch, failure):
    m, plan, helper, server, events = execution
    def fail(*a):
        raise m.RebuildError("test failure")
    monkeypatch.setattr(m, failure, fail)
    with pytest.raises(m.RebuildError):
        m.execute(plan, Path("/unused"), helper, None, server)
    audit = m.STATE / "frontend-rebuilds" / plan["operation_id"]
    assert m.LEASE.is_dir()
    assert (audit / "failed.json").is_file()
    assert not (audit / "completed.json").exists()
    if failure == "assert_unchanged":
        assert "stop" not in events
    if failure == "assert_frontend_stopped":
        assert (m.PRODUCTION / "frontend/.next/payload").read_text() == "old"


@pytest.mark.skipif(os.environ.get("REVA_TEST_FRONTEND_SANDBOX") != "1", reason="requires isolated Linux systemd runner")
def test_native_frontend_sandbox_private_mounts_and_dynamic_uid(monkeypatch):
    assert os.geteuid() == 0 and Path("/run/systemd/system").is_dir()
    m = load()
    root = Path(tempfile.mkdtemp(prefix="reva-frontend-sandbox-", dir="/var/lib"))
    root.chmod(0o755)
    operation = uuid.uuid4().hex
    stage = root / operation
    stage.mkdir(mode=0o700)
    monkeypatch.setattr(m, "BUILDS", root)
    for name in ("frontend", "home", "cache"):
        (stage / name).mkdir(mode=0o777)
        (stage / name).chmod(0o777)
    (stage / "frontend/input").write_text("public source")
    (stage / "frontend/input").chmod(0o644)
    command = m.build_command(operation, stage)
    # Exercise the actual production deny list, never replace it with a test-only path.
    denied = next(arg.split("=", 2)[2].split() for arg in command if arg.startswith("--property=InaccessiblePaths="))
    created_roots, canaries = [], []
    for entry in denied:
        directory = Path(entry.removeprefix("-"))
        assert directory.is_absolute() and not directory.is_symlink()
        if not directory.exists():
            directory.mkdir(mode=0o755)
            created_roots.append(directory)
        canary = Path(tempfile.mkdtemp(prefix="reva-synthetic-health-", dir=directory))
        canary.chmod(0o755)
        (canary / "record").write_text("synthetic test data only")
        (canary / "record").chmod(0o644)
        canaries.append(canary)
    # Real deployments keep world-readable uploads below these external roots.
    assert "-/opt" in denied and "-/var/lib" in denied
    negative_checks = "".join(f"test ! -r {path}/record\n" for path in canaries)
    command[-1] = (f"test -r /tmp/reva-frontend/input\ntest ! -r {stage}/frontend/input\n"
                   + negative_checks + "test -z \"${REVA_SYNTHETIC_SECRET:-}\"\n"
                   "test \"$HOME\" = /tmp/reva-home\nid -u > uid\ntouch /tmp/reva-home/proof /tmp/reva-cache/proof\n"
                   "test \"$(npm config get registry)\" = https://registry.npmjs.org/")
    completed = False
    try:
        result = subprocess.run(command, env={**m.ENV, "REVA_SYNTHETIC_SECRET": "must-not-propagate"},
                                capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stderr
        uid = int((stage / "frontend/uid").read_text())
        assert uid not in (0, 65534)
        assert (stage / "home/proof").is_file() and (stage / "cache/proof").is_file()
        completed = True
    finally:
        # Isolated CI only. Never remove existing root contents; keep unknown units/evidence.
        if completed:
            for canary in canaries:
                (canary / "record").unlink()
                canary.rmdir()
            for directory in reversed(created_roots):
                directory.rmdir()
            shutil.rmtree(root)
