"""Failure closure archives facts; it cannot turn a failed release into success."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def load():
    spec = importlib.util.spec_from_file_location(
        "retained_test", Path(__file__).with_name("retained_candidate_retirement.py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def marker(candidate="b" * 40):
    old = "a" * 40 if candidate != "a" * 40 else "f" * 40
    transaction = hashlib.sha256(f"{old}:{candidate}".encode()).hexdigest()[:32]
    return {
        "version": 1,
        "old_sha": old,
        "candidate_sha": candidate,
        "terminal_sha": candidate,
        "phase": "COMMITTED",
        "target": "candidate",
        "result": "finalized",
        "transaction_id": transaction,
        "reap_name": "runtime-state-transaction.reap-" + transaction,
    }


def test_terminal_requires_exact_finalized_candidate():
    m = load()
    m.validate_terminal(marker(), "b" * 40)
    for field, value in [
        ("version", True),
        ("phase", "RESTORE_FINALIZED"),
        ("target", "old"),
        ("result", "unknown"),
        ("terminal_sha", "a" * 40),
        ("candidate_sha", "c" * 40),
        ("transaction_id", "0" * 32),
        ("extra", 1),
    ]:
        altered = marker()
        altered[field] = value
        with pytest.raises(m.RetirementError):
            m.validate_terminal(altered, "b" * 40)


class Adapter:
    def __init__(self, path):
        self.record = path / "retained" / ("b" * 40)
        self.value = {
            "old_sha": "b" * 40,
            "closing_sha": "c" * 40,
            "terminal": marker(),
        }
        self.calls = 0
        self.drift = False

    def check_record_parent(self):
        pass

    def inspect(self):
        self.calls += 1
        value = copy.deepcopy(self.value)
        if self.drift and self.calls > 1:
            value["closing_sha"] = "d" * 40
        return value

    def retire_authorization(self, evidence):
        pass


def test_inspect_is_read_only_and_close_issues_receipt_only_after_completion(tmp_path):
    m = load()
    a = Adapter(tmp_path)
    inspected = m.close_transaction(a)
    assert not a.record.exists()
    result = m.close_transaction(a, inspected["evidence_sha256"])
    assert result["state"] == "CLOSED_RETAINED_CANDIDATE_FAILURE"
    assert {p.name for p in a.record.iterdir()} == {"intent.json", "completed.json"}
    intent = json.loads((a.record / "intent.json").read_text())
    assert (
        hashlib.sha256(result["receipt"].encode()).hexdigest()
        == intent["receipt_sha256"]
    )
    assert result["receipt"] not in (a.record / "intent.json").read_text()
    with pytest.raises(m.RetirementError):
        m.close_transaction(a, inspected["evidence_sha256"])


def test_stale_digest_never_consumes_and_post_intent_drift_stays_blocked(tmp_path):
    m = load()
    a = Adapter(tmp_path)
    with pytest.raises(m.RetirementError):
        m.close_transaction(a, "0" * 64)
    assert not a.record.exists()
    a.calls = 0
    a.drift = True
    digest = m.digest(a.value)
    with pytest.raises(m.RetirementError):
        m.close_transaction(a, digest)
    assert (a.record / "intent.json").exists()
    assert not (a.record / "completed.json").exists()
    with pytest.raises(m.RetirementError):
        m.close_transaction(a, digest)


def test_pending_transaction_blocks_even_with_valid_terminal(tmp_path):
    m = load()
    (tmp_path / "runtime-state-transaction.reap-dead").mkdir()
    with pytest.raises(m.RetirementError):
        m.assert_no_transaction(tmp_path)


def test_no_finalization_or_success_receipt_written():
    m = load()
    text = Path(m.__file__).read_text()
    assert ".finalize(" not in text and ".commit(" not in text


def history_fixture(monkeypatch, tmp_path):
    m = load()
    sha = "b" * 40
    closing = "c" * 40
    receipt = "d" * 64
    root = tmp_path / m.ROOT_NAME / sha
    root.mkdir(parents=True)
    live = {
        "terminal": marker(),
        "terminal_identity": {
            "uid": 0,
            "gid": 0,
            "mode": 0o600,
            "inode": 1,
            "device": 1,
            "sha256": "e" * 64,
        },
        "services": {},
        "configuration": {"units": {}, "laya": {}},
        "kb_quarantine": quarantine_fixture(sha),
        "probes": {
            "schema": True,
            "runtime_only_kb": True,
            "auth_unauthenticated_401": True,
            "health_dependencies": True,
            "runtime_flag_false": True,
        },
    }
    # Live services are validated by the canonical service proof; history holds
    # that immutable snapshot instead of querying a different deployment.
    for unit in (
        "health-backend.socket",
        "health-backend.service",
        "celery-worker.service",
        "celery-beat.service",
    ):
        live["services"][unit] = {
            "ActiveState": "active",
            "SubState": "listening" if unit.endswith(".socket") else "running",
            "MainPID": "0" if unit.endswith(".socket") else "123",
            "NRestarts": "0",
            "ActiveEnterTimestampMonotonic": "123",
            "ControlGroup": "/system.slice/" + unit,
            "Result": "success",
        }
        if unit.endswith(".service"):
            live["services"][unit]["processes"] = {"123": "789"}
    evidence = {
        "old_sha": sha,
        "closing_sha": closing,
        "workspace": {"manifest": "old"},
        "installation": {"config": {"old": "config"}, "library": {"old": "library"}},
        "active_installation": {
            "config": {"old": "config", "loopback.key": {"old": "key"}},
            "library": {"old": "library"},
            "authorized": {"old": "auth"},
        },
        "live": live,
        "launcher": {"old": "lock"},
    }
    intent = {
        **evidence,
        "evidence_sha256": m.digest(evidence),
        "receipt_sha256": hashlib.sha256(receipt.encode()).hexdigest(),
    }
    completed = {"state": m.TERMINAL, "old_sha": sha, "intent_sha256": m.digest(intent)}
    for name, value in [("intent.json", intent), ("completed.json", completed)]:
        (root / name).write_text(json.dumps(value))
    b = SimpleNamespace(
        STATE=tmp_path,
        CONFIG=tmp_path / "config",
        INSTALLED=tmp_path / "lib" / "server.py",
        secure=lambda *a, **k: None,
        _inventory=lambda *a: None,
        _read_json=lambda p: json.loads(p.read_text()),
        canonical_source=lambda sha: tmp_path / "source",
        _archives=lambda sha: (tmp_path / "archconfig", tmp_path / "archlib"),
        _installation_evidence=lambda *a: evidence["installation"],
        _recovery_file_identity=lambda p: evidence["launcher"],
    )
    monkeypatch.setattr(m, "private_directory", lambda *a: None)
    monkeypatch.setattr(m, "validate_configuration", lambda *a: None)
    monkeypatch.setattr(m, "workspace_evidence", lambda *a: evidence["workspace"])
    return m, b, sha, receipt, evidence


def test_history_never_queries_future_production(monkeypatch, tmp_path):
    m, b, sha, receipt, _evidence = history_fixture(monkeypatch, tmp_path)

    def forbidden(*a):
        raise AssertionError("history must not inspect current production")

    monkeypatch.setattr(m, "live_state", forbidden)
    assert m.closed_evidence(b, sha, receipt, historical=True)["state"] == m.TERMINAL
    with pytest.raises(AssertionError):
        m.closed_evidence(b, sha, receipt, historical=False)
    with pytest.raises(m.RetirementError):
        m.closed_evidence(b, sha, "f" * 64, historical=True)
    monkeypatch.setattr(m, "workspace_evidence", lambda *a: {"manifest": "changed"})
    with pytest.raises(m.RetirementError):
        m.closed_evidence(b, sha, receipt, historical=True)


@pytest.mark.parametrize("fault", ["terminal", "probe", "service", "identity"])
def test_self_consistent_but_invalid_archived_proof_is_rejected(
    monkeypatch, tmp_path, fault
):
    m, b, sha, receipt, evidence = history_fixture(monkeypatch, tmp_path)
    if fault == "terminal":
        evidence["live"]["terminal"]["phase"] = "RESTORE_FINALIZED"
    if fault == "probe":
        evidence["live"]["probes"]["schema"] = False
    if fault == "service":
        evidence["live"]["services"]["celery-worker.service"]["Result"] = "failed"
    if fault == "identity":
        evidence["live"]["terminal_identity"]["uid"] = 1000
    intent = {
        **evidence,
        "evidence_sha256": m.digest(evidence),
        "receipt_sha256": hashlib.sha256(receipt.encode()).hexdigest(),
    }
    root = tmp_path / m.ROOT_NAME / sha
    (root / "intent.json").write_text(json.dumps(intent))
    (root / "completed.json").write_text(
        json.dumps(
            {"state": m.TERMINAL, "old_sha": sha, "intent_sha256": m.digest(intent)}
        )
    )
    with pytest.raises(m.RetirementError):
        m.closed_evidence(b, sha, receipt, historical=True)


def workspace_fixture(monkeypatch, tmp_path):
    m = load()
    sha = "b" * 40
    root = tmp_path / sha
    root.mkdir()
    source = tmp_path / "canonical"
    (source / "scripts").mkdir(parents=True)
    executor = source / "scripts/trusted_release_server.py"
    executor.write_text("# canonical executor\n")
    for name, state in [
        ("started.json", "STARTED"),
        ("preparation-started.json", "PREPARING"),
        ("prepared.json", "PREPARED"),
        ("deployment-started.json", "DEPLOYING"),
        ("completed.json", "NEEDS_OPERATOR"),
    ]:
        value = {"sha": sha, "state": state}
        if name == "preparation-started.json":
            value["executor_sha256"] = hashlib.sha256(executor.read_bytes()).hexdigest()
        (root / name).write_text(json.dumps(value))
    for name in ("preparation.log", "deployment.log", "deployment.env"):
        (root / name).write_text("private bytes")
    for name in ("source", "home", "bin"):
        (root / name).mkdir()
    spec = importlib.util.spec_from_file_location(
        "retained_manifest", Path(__file__).with_name("bootstrap_trusted_release.py")
    )
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    monkeypatch.setattr(b, "secure", lambda *a, **k: None)
    b.STATE = tmp_path
    monkeypatch.setattr(b, "canonical_source", lambda sha: source)
    monkeypatch.setattr(m, "private_directory", lambda *a: None)
    return m, b, sha, root


def test_workspace_keeps_original_failure_and_detects_every_retained_byte(
    monkeypatch, tmp_path
):
    m, b, sha, root = workspace_fixture(monkeypatch, tmp_path)
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    proof = m.workspace_evidence(b, sha)
    assert before == {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    (root / "source" / "retained").write_text("additional private content")
    assert m.workspace_evidence(b, sha) != proof
    (root / "source" / "link").symlink_to(tmp_path / "outside")
    with pytest.raises(b.BootstrapError):
        m.workspace_evidence(b, sha)


@pytest.mark.parametrize(
    "fault", ["claim", "extra", "incomplete", "wrong_sha", "executor"]
)
def test_workspace_rejects_mixed_claim_and_invalid_phase(monkeypatch, tmp_path, fault):
    m, b, sha, root = workspace_fixture(monkeypatch, tmp_path)
    if fault == "claim":
        (root / "build.lock").touch()
    if fault == "extra":
        (root / "unexpected").touch()
    if fault == "incomplete":
        (root / "prepared.json").unlink()
    if fault == "wrong_sha":
        (root / "completed.json").write_text(
            json.dumps({"sha": "a" * 40, "state": "NEEDS_OPERATOR"})
        )
    if fault == "executor":
        (root / "preparation-started.json").write_text(
            json.dumps({"sha": sha, "state": "PREPARING", "executor_sha256": "f" * 64})
        )
    with pytest.raises(m.RetirementError):
        m.workspace_evidence(b, sha)


def test_completion_write_failure_never_returns_receipt_or_retries(
    monkeypatch, tmp_path
):
    m = load()
    a = Adapter(tmp_path)
    original = m.write_json

    def fail(path, value):
        if path.name == "completed.json":
            raise OSError("injected durability fault")
        original(path, value)

    monkeypatch.setattr(m, "write_json", fail)
    with pytest.raises(OSError):
        m.close_transaction(a, m.digest(a.value))
    assert (a.record / "intent.json").exists()
    assert not (a.record / "completed.json").exists()
    with pytest.raises(m.RetirementError):
        m.close_transaction(a, m.digest(a.value))


@pytest.mark.parametrize("revocation_fault", [None, "write", "postcondition"])
def test_active_failed_claim_can_close_without_pre_revocation(
    monkeypatch, tmp_path, revocation_fault
):
    """Start with actual install and NEEDS_OPERATOR, not a revoked rotation fixture."""
    spec = importlib.util.spec_from_file_location(
        "bootstrap_fixture",
        Path(__file__).with_name("test_bootstrap_trusted_release.py"),
    )
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    b, _ = fixtures.fixture(monkeypatch, tmp_path)
    sha, closing = fixtures.SHA, fixtures.NEW_SHA
    b.install(sha, 200, fixtures.PUBLIC)
    source, _ = b.reviewed_source(closing)
    monkeypatch.setattr(b, "canonical_source", lambda revision: source)
    root = b.STATE / sha
    root.mkdir(mode=0o700)
    executor = hashlib.sha256(
        (source / "scripts/trusted_release_server.py").read_bytes()
    ).hexdigest()
    for name, state in [
        ("started.json", "STARTED"),
        ("preparation-started.json", "PREPARING"),
        ("prepared.json", "PREPARED"),
        ("deployment-started.json", "DEPLOYING"),
        ("completed.json", "NEEDS_OPERATOR"),
    ]:
        value = {"sha": sha, "state": state}
        if name == "preparation-started.json":
            value["executor_sha256"] = executor
        (root / name).write_text(json.dumps(value))
        (root / name).chmod(0o600)
    for name in ("preparation.log", "deployment.log", "deployment.env"):
        (root / name).write_bytes(b"unchanged evidence")
        (root / name).chmod(0o600)
    for name in ("source", "home", "bin"):
        (root / name).mkdir(mode=0o700)
    with pytest.raises(b.BootstrapError, match="termination unproven"):
        b.revoke(sha)
    assert fixtures.PUBLIC in b.AUTHORIZED.read_text()
    assert (b.CONFIG / "loopback.key").exists()
    m = load()
    monkeypatch.setattr(m, "private_directory", lambda *a: None)
    # Only external host probes are substituted; workspace, installation,
    # policy, authorization, durable writes and post-revocation checks are real.
    live = history_fixture(monkeypatch, tmp_path / "sample")[4]["live"]
    live["terminal"] = marker(sha)
    live["kb_quarantine"]["candidate_sha"] = sha
    monkeypatch.setattr(m, "live_state", lambda *a: copy.deepcopy(live))
    monkeypatch.setattr(m, "validate_configuration", lambda *a: None)
    adapter = m.Adapter(b, source, closing, sha, lambda: None)
    original = b._preparation_manifest(root)
    inspected = m.close_transaction(adapter)
    assert fixtures.PUBLIC in b.AUTHORIZED.read_text()
    if revocation_fault:

        def faulty_write(value):
            if revocation_fault == "write":
                raise OSError("injected authorization write failure")
            b.AUTHORIZED.write_bytes(value + b"unexpected unrelated mutation\n")

        monkeypatch.setattr(b, "_replace_authorized", faulty_write)
        with pytest.raises((OSError, m.RetirementError)):
            m.close_transaction(adapter, inspected["evidence_sha256"])
        assert (adapter.record / "intent.json").exists()
        assert not (adapter.record / "completed.json").exists()
        assert b._preparation_manifest(root) == original
        with pytest.raises(m.RetirementError):
            m.close_transaction(adapter, inspected["evidence_sha256"])
        return
    result = m.close_transaction(adapter, inspected["evidence_sha256"])
    assert result["state"] == m.TERMINAL
    assert fixtures.PUBLIC not in b.AUTHORIZED.read_text()
    assert fixtures.LOOPBACK not in b.AUTHORIZED.read_text()
    assert b.AUTHORIZED.read_text() == "ssh-ed25519 AAAAExisting unrelated\n"
    assert not (b.CONFIG / "loopback.key").exists()
    assert b._preparation_manifest(root) == original
    assert b._read_json(root / "completed.json")["state"] == "NEEDS_OPERATOR"
    assert m.closed_evidence(b, sha, result["receipt"])["state"] == m.TERMINAL


def configuration_fixture(monkeypatch, tmp_path):
    m = load()
    source = Path(__file__).resolve().parents[1]

    def local_load(_b, path, name):
        import sys

        spec = importlib.util.spec_from_file_location(name, path)
        value = importlib.util.module_from_spec(spec)
        sys.modules[name] = value
        spec.loader.exec_module(value)
        return value

    monkeypatch.setattr(m, "load", local_load)
    b = SimpleNamespace(
        secure=lambda *a, **k: None, canonical_source=lambda sha: source
    )
    f = local_load(
        b,
        source / "scripts/test_contained_recovery_proof.py",
        "retained_network_test_fixture",
    )
    proof, _, _ = f.network_guard_fixture(tmp_path)
    guard = proof._network_guard(source)
    # Fixture helper has temporary paths; archive uses fixed production paths.
    guard["files"] = {
        path.replace(str(proof.production), "/opt/health-app").replace(
            str(proof.systemd_root), "/etc/systemd/system"
        ): {**value, "dev": 1, "ino": 2, "uid": 0, "gid": 0, "mode": 0o644}
        for path, value in guard["files"].items()
    }
    guard["service"]["FragmentPath"] = (
        "/etc/systemd/system/health-network-guard.service"
    )
    installer = local_load(
        b, source / "infra/laya/install.py", "retained_laya_test_fixture"
    )
    generation, _, _, expected = installer.expected_install(
        source / "infra/laya", {"DECISION_API_KEY": ""}
    )

    def identity(raw=b"fixture", mode=0o644):
        return {
            "dev": 1,
            "ino": 2,
            "uid": 0,
            "gid": 0,
            "mode": mode,
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    assets = {
        name: hashlib.sha256((source / "infra/laya" / name).read_bytes()).hexdigest()
        for name in installer.ASSETS
    }
    receipt = {
        **expected,
        "state": "INSTALLED",
        "candidate_sha": "a" * 40,
        "lease": "e" * 64,
    }
    receipt_identity = identity(json.dumps(receipt).encode(), 0o600)
    executable = generation / "venv/bin/python"
    laya = {
        "candidate_sha": "b" * 40,
        "assets": assets,
        "expected": expected,
        "receipt": receipt,
        "receipt_identity": receipt_identity,
        "files": {
            str(installer.STATE / "install.json"): receipt_identity,
            str(installer.UNIT): {**identity(), "sha256": expected["unit_sha256"]},
            str(installer.ENV): {
                **identity(mode=0o640),
                "gid": 99,
                "sha256": expected["env_sha256"],
            },
        },
        "exported_source": {
            name: identity((source / "infra/laya" / name).read_bytes(), 0o400)
            for name in assets
        },
        "services": {
            "ActiveState": "active",
            "SubState": "running",
            "FragmentPath": str(installer.UNIT),
            "DropInPaths": "",
            "User": "reva-laya",
            "Group": "reva-laya",
            "UnitFileState": "enabled",
            "MainPID": "123",
            "NRestarts": "0",
            "ExecStart": f"path={executable}\nargv[]={executable} -I {generation / 'serve.py'}\nignore_errors=no",
            "processes": {"123": "456"},
            "boot_id": "11111111-1111-1111-1111-111111111111",
        },
    }
    laya["exported_source"]["source.json"] = identity(mode=0o400)
    units = {"network_guard": guard, "effective": {}}
    for unit in (
        f.proof.UNITS
        if hasattr(f, "proof")
        else (
            "health-backend.socket",
            "health-backend.service",
            "celery-worker.service",
            "celery-beat.service",
        )
    ):
        units[unit] = {"base": identity((source / "infra/systemd" / unit).read_bytes())}
        if unit.endswith(".socket"):
            continue
        raw = (
            source
            / "infra/systemd/dropins"
            / unit.replace(".service", "-runtime-state.conf")
        ).read_bytes()
        units[unit]["80-reva-health-evidence-runtime.conf"] = identity(
            b"[Service]\nEnvironmentFile=-/var/lib/reva-health-evidence-runtime/enabled.env\n"
        )
        units[unit]["90-runtime-state.conf"] = identity(raw)
        import re

        command = (
            "/opt/health-app/backend/venv/bin/celery -A app.celery_app:celery_app worker --loglevel=info --concurrency=4"
            if unit == "celery-worker.service"
            else re.findall(rb"^ExecStart=(.+)$", raw, re.MULTILINE)[0].decode()
        )
        units["effective"][unit] = {
            "FragmentPath": "/etc/systemd/system/" + unit,
            "DropInPaths": " ".join(
                "/etc/systemd/system/" + unit + ".d/" + name
                for name in (
                    "80-reva-health-evidence-runtime.conf",
                    "90-runtime-state.conf",
                    "security-network.conf",
                )
            ),
            "ExecStart": f"path={command.split()[0]}\nargv[]={command}\nignore_errors=no",
            "ReadWritePaths": re.findall(rb"^ReadWritePaths=(.+)$", raw, re.MULTILINE)[
                0
            ].decode(),
        }
    monkeypatch.setattr(m, "validate_archived_vision", lambda *a: None)
    return m, b, source, {"units": units, "laya": laya, "vision_overlay": {}}


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "command",
        "fragment",
        "dropin",
        "writable",
        "laya_candidate",
        "laya_generation",
        "laya_service",
    ],
)
def test_archived_candidate_effective_and_laya_contracts(monkeypatch, tmp_path, fault):
    m, b, source, value = configuration_fixture(monkeypatch, tmp_path)
    effective = value["units"]["effective"]["health-backend.service"]
    if fault == "command":
        effective["ExecStart"] = (
            "path=/usr/bin/false\nargv[]=/usr/bin/false\nignore_errors=no"
        )
    if fault == "fragment":
        effective["FragmentPath"] = "/tmp/untrusted.service"
    if fault == "dropin":
        effective["DropInPaths"] += " /tmp/extra.conf"
    if fault == "writable":
        effective["ReadWritePaths"] += " /"
    if fault == "laya_candidate":
        value["laya"]["candidate_sha"] = "c" * 40
    if fault == "laya_generation":
        value["laya"]["expected"]["generation"] = "f" * 64
    if fault == "laya_service":
        value["laya"]["services"]["User"] = "root"
    if fault:
        with pytest.raises((m.RetirementError, RuntimeError)):
            m.validate_configuration(b, source, "b" * 40, value)
    else:
        m.validate_configuration(b, source, "b" * 40, value)


@pytest.mark.parametrize("fault", ["effective_units", "laya"])
def test_live_candidate_configuration_propagates_external_proof_failures(
    monkeypatch, tmp_path, fault
):
    m = load()
    sha = "b" * 40
    stage = tmp_path / sha
    stage.mkdir()
    (stage / "deployment-started.json").write_text("{}")
    source = tmp_path / "source"
    source.mkdir()
    b = SimpleNamespace(STATE=tmp_path, canonical_source=lambda revision: source)

    class Transaction:
        pass

    runtime = SimpleNamespace(
        ReleaseTransaction=Transaction,
        UNITS=(
            "health-backend.service",
            "celery-worker.service",
            "celery-beat.service",
        ),
    )
    calls = []

    def units(candidate, tx, *, started_at):
        calls.append("units")
        assert candidate == source and proof.stage is None and proof.lease is None
        assert set(tx.layout.base_units) == set(runtime.UNITS)
        if fault == "effective_units":
            raise m.RetirementError("effective unit mismatch")
        return {"verified": "units"}

    proof = SimpleNamespace(systemd=object(), _units=units)

    def laya(*args):
        calls.append("laya")
        raise m.RetirementError("Laya not bound to candidate")

    monkeypatch.setattr(m, "candidate_laya", laya)
    monkeypatch.setattr(
        m,
        "inspect_vision_overlay",
        lambda *a: {
            "raw_dropins": {
                unit: " ".join(m.vision_paths(unit)) for unit in runtime.UNITS
            }
        },
    )
    with pytest.raises(m.RetirementError):
        m.candidate_configuration(b, source, sha, marker(), proof, runtime)
    assert calls == (["units"] if fault == "effective_units" else ["units", "laya"])


def test_vision_projection_keeps_raw_paths_and_rejects_unknown_or_moved_overlay():
    m = load()
    units = ("health-backend.service", "celery-worker.service", "celery-beat.service")
    raw = {
        u: " ".join(
            "/etc/systemd/system/" + u + ".d/" + name
            for name in (
                "80-reva-health-evidence-runtime.conf",
                "90-runtime-state.conf",
                "security-network.conf",
                "zzzz-reva-vision-model.conf",
            )
        )
        for u in units
    }
    host = SimpleNamespace(
        show=lambda u, k: raw[u] if k == "DropInPaths" else "unchanged-property",
        is_enabled=lambda u: "enabled",
    )
    view = m.VisionBaseView(host, raw)
    for u in units:
        assert view.show(u, "DropInPaths") == raw[u].rsplit(" ", 1)[0]
        for prop in ("EnvironmentFiles", "UnsetEnvironment", "ExecStart", "User"):
            assert view.show(u, prop) == "unchanged-property"
    assert view.is_enabled(units[0]) == "enabled"
    raw[units[0]] += " /tmp/unknown.conf"
    with pytest.raises(m.RetirementError):
        view.show(units[0], "DropInPaths")


def vision_history_documents():
    operation = "d" * 32
    before = {
        "kind": "vision-model-selection",
        "publisher_sha": "a" * 40,
        "production_sha": "b" * 40,
        "operation_id": operation,
        "model": "qwen3.8-flash",
        "services": {},
        "protected_metadata": {},
        "before": {},
        "acceptance": "PENDING",
        "production_apply_enabled": True,
    }
    m = load()
    fingerprint = m.digest(before)
    intent = {"state": "CONFIG_STARTED", "evidence_sha256": fingerprint}
    completed = {
        "state": "CONFIG_SUCCEEDED_PENDING_MODEL_ACCEPTANCE",
        "publisher_sha": "a" * 40,
        "production_sha": "b" * 40,
        "operation_id": operation,
        "model": "qwen3.8-flash",
        "model_acceptance": "PENDING",
        "model_requests": 0,
        "evidence_sha256": fingerprint,
        "services": {},
    }
    return m, operation, before, intent, copy.deepcopy(completed), completed


@pytest.mark.parametrize(
    "fault", [None, "model", "digest", "operation", "verified", "pending"]
)
def test_vision_history_requires_matching_root_operation_documents(fault):
    m, operation, before, intent, verified, completed = vision_history_documents()
    if fault == "model":
        completed["model"] = "other"
    if fault == "digest":
        intent["evidence_sha256"] = "0" * 64
    if fault == "operation":
        completed["operation_id"] = "e" * 32
    if fault == "verified":
        verified["model_requests"] = 1
    if fault == "pending":
        completed["state"] = "CONFIG_NEEDS_OPERATOR"
    if fault:
        with pytest.raises(m.RetirementError):
            m.validate_vision_documents(operation, before, intent, verified, completed)
    else:
        m.validate_vision_documents(operation, before, intent, verified, completed)


def test_cli_diagnostics_never_include_exception_text(monkeypatch, capsys):
    m = load()
    secret = "PRIVATE_HEALTH_AND_CREDENTIAL_PAYLOAD"
    monkeypatch.setattr(m, "main", lambda: (_ for _ in ()).throw(ValueError(secret)))
    assert m.cli() == 1
    output = capsys.readouterr()
    assert secret not in output.out + output.err
    value = json.loads(output.err)
    assert value["state"] == "RETAINED_CANDIDATE_CLOSURE_BLOCKED"
    assert value["exception_class"] == "ValueError"
    assert value["stage"] == "arguments"


def overlay_fixture(monkeypatch, tmp_path):
    m = load()
    root = Path(__file__).resolve().parents[1]

    def module(path, name):
        import sys

        spec = importlib.util.spec_from_file_location(name, path)
        v = importlib.util.module_from_spec(spec)
        sys.modules[name] = v
        spec.loader.exec_module(v)
        return v

    vision = module(
        root / "scripts/trusted_vision_model.py", "retained_overlay_real_vision"
    )
    server = module(
        root / "scripts/trusted_release_server.py", "retained_overlay_real_server"
    )
    bootstrap = module(
        root / "scripts/bootstrap_trusted_release.py", "retained_overlay_real_bootstrap"
    )
    monkeypatch.setattr(bootstrap, "STATE", tmp_path)
    monkeypatch.setattr(bootstrap, "secure", lambda *a, **k: None)
    monkeypatch.setattr(bootstrap, "canonical_source", lambda sha: root)
    monkeypatch.setattr(server, "secure_path", lambda *a, **k: None)
    monkeypatch.setattr(m, "private_directory", lambda *a: None)
    monkeypatch.setattr(
        m,
        "load",
        lambda b, path, name: (
            vision if path.name == "trusted_vision_model.py" else server
        ),
    )
    _, operation, before, intent, verified, completed = vision_history_documents()
    audit = tmp_path / "vision-models" / operation
    audit.mkdir(parents=True, mode=0o700)
    for name, value in [
        ("before", before),
        ("intent", intent),
        ("verified", verified),
        ("completed", completed),
        ("lease", {"identity": {}}),
    ]:
        (audit / (name + ".json")).write_text(json.dumps(value))
        (audit / (name + ".json")).chmod(0o600)
    production = tmp_path / before["production_sha"]
    production.mkdir()
    (production / "completed.json").write_text(
        json.dumps({"sha": before["production_sha"], "state": "SUCCEEDED"})
    )
    (production / "completed.json").chmod(0o600)
    raw = {
        u + ".service": " ".join(m.vision_paths(u + ".service"))
        for u in vision.SERVICES
    }
    paths = [
        vision.MODEL,
        *[
            vision.SYSTEMD / (u + ".service.d") / vision.DROPIN_NAME
            for u in vision.SERVICES
        ],
    ]
    physical = {
        path: tmp_path / ("model-file-" + str(i)) for i, path in enumerate(paths)
    }
    for path, local in physical.items():
        local.write_bytes(
            vision.model_bytes("qwen3.8-flash")
            if path == vision.MODEL
            else vision.dropin_bytes()
        )
        local.chmod(0o600)
    original = vision.optional_model_file

    def read(path):
        value = original(physical[path])
        value["metadata"].update(uid=0, gid=0)
        return value

    monkeypatch.setattr(vision, "optional_model_file", read)
    monkeypatch.setattr(vision, "secure_path", lambda *a, **k: None)
    monkeypatch.setattr(vision, "process_start", lambda pid: "123")
    monkeypatch.setattr(vision, "target_process_value", lambda pid, key: "false")
    model = {"value": "qwen3.8-flash"}

    def process_model(pid):
        if model["value"] != "qwen3.8-flash":
            raise vision.VisionError("model mismatch")

    monkeypatch.setattr(vision, "target_process_model", process_model)

    def run(args):
        unit = args[2]
        unit = unit.removesuffix(".service")
        values = {
            "ActiveState": "active",
            "SubState": "running",
            "MainPID": "123",
            "NRestarts": "0",
            "ExecMainStartTimestampMonotonic": "1",
            "EnvironmentFiles": "/opt/health-app/backend/.env (ignore_errors=no) /var/lib/reva-health-evidence-runtime/enabled.env (ignore_errors=yes) /var/lib/reva-vision-model/model.env (ignore_errors=no)",
            "DropInPaths": raw[unit + ".service"],
            "UnsetEnvironment": "",
            "User": "health-app",
            "Group": "health-app",
            "WorkingDirectory": "/opt/health-app/backend",
            "NoNewPrivileges": "yes",
            "ProtectSystem": "strict",
            "ProtectHome": "yes",
            "PrivateTmp": "yes",
            "CapabilityBoundingSet": "",
        }
        return "\n".join(k + "=" + v for k, v in values.items())

    monkeypatch.setattr(vision, "run", run)
    systemd = SimpleNamespace(
        show=lambda unit, prop: raw[unit] if prop == "DropInPaths" else "unmodified"
    )
    return m, bootstrap, root, systemd, physical, raw, model, audit


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "extra_directive",
        "wrong_model_file",
        "wrong_process_model",
        "unknown_dropin",
        "missing_terminal",
        "history_digest",
    ],
)
def test_real_governed_overlay_readback_rejects_unproven_state(
    monkeypatch, tmp_path, fault
):
    m, b, source, systemd, files, raw, model, audit = overlay_fixture(
        monkeypatch, tmp_path
    )
    expected_errors = (
        m.RetirementError,
        b.BootstrapError,
        m.load(b, source / "scripts/trusted_vision_model.py", "unused").VisionError,
        m.load(b, source / "scripts/trusted_release_server.py", "unused").LaunchError,
    )
    paths = list(files)
    if fault == "extra_directive":
        files[paths[1]].write_bytes(
            files[paths[1]].read_bytes() + b"ExecStart=/bin/false\n"
        )
    if fault == "wrong_model_file":
        files[paths[0]].write_bytes(b"LLM_VISION_MODEL=other\n")
    if fault == "wrong_process_model":
        model["value"] = "other"
    if fault == "unknown_dropin":
        prefix, own = raw["health-backend.service"].rsplit(" ", 1)
        raw["health-backend.service"] = prefix + " /tmp/unknown.conf " + own
    if fault == "missing_terminal":
        (audit / "completed.json").unlink()
    if fault == "history_digest":
        value = json.loads((audit / "intent.json").read_text())
        value["evidence_sha256"] = "f" * 64
        (audit / "intent.json").write_text(json.dumps(value))
    if fault:
        with pytest.raises(expected_errors):
            m.inspect_vision_overlay(b, source, systemd)
    else:
        proof = m.inspect_vision_overlay(b, source, systemd)
        assert proof["raw_dropins"] == raw and set(proof["files"]) == set(
            map(str, files)
        )
        m.validate_archived_vision(b, source, proof)
        files[paths[0]].write_bytes(b"LLM_VISION_MODEL=other\n")
        # Archive validation never re-reads live configuration after a later deploy.
        m.validate_archived_vision(b, source, proof)
        with pytest.raises(expected_errors):
            m.inspect_vision_overlay(b, source, systemd)


def test_cli_invalid_arguments_do_not_echo_untrusted_values(monkeypatch, capsys):
    m = load()
    secret = "PRIVATE_ARGUMENT_PAYLOAD"
    monkeypatch.setattr(
        m.sys, "argv", ["retained_candidate_retirement.py", "--unknown", secret]
    )
    assert m.cli() == 1
    output = capsys.readouterr()
    assert secret not in output.out + output.err
    assert json.loads(output.err)["stage"] == "arguments"


@pytest.mark.parametrize("changed", ["files", "services", "history", "raw_dropins"])
def test_candidate_configuration_blocks_overlay_drift_after_base_proof(
    monkeypatch, tmp_path, changed
):
    m = load()
    sha = "b" * 40
    root = tmp_path / sha
    root.mkdir()
    (root / "deployment-started.json").write_text("{}")
    source = tmp_path / "source"
    source.mkdir()
    units = ("health-backend.service", "celery-worker.service", "celery-beat.service")
    raw = {unit: " ".join(m.vision_paths(unit)) for unit in units}
    systemd = SimpleNamespace(
        show=lambda unit, prop: raw[unit], is_enabled=lambda unit: "enabled"
    )
    proof = SimpleNamespace(systemd=systemd, _units=lambda *a, **k: {"checked": True})

    class Transaction:
        pass

    runtime = SimpleNamespace(ReleaseTransaction=Transaction, UNITS=units)
    b = SimpleNamespace(STATE=tmp_path, canonical_source=lambda revision: source)
    snapshot = {
        "raw_dropins": raw,
        "files": {"stable": 1},
        "services": {"stable": 1},
        "history": {"stable": 1},
    }
    calls = []

    def inspect(*args):
        result = copy.deepcopy(snapshot)
        if calls:
            result[changed]["changed"] = True
        calls.append(True)
        return result

    monkeypatch.setattr(m, "inspect_vision_overlay", inspect)
    monkeypatch.setattr(m, "candidate_laya", lambda *a: {"checked": True})
    with pytest.raises(m.RetirementError, match="overlay changed"):
        m.candidate_configuration(b, source, sha, marker(), proof, runtime)
    assert proof.systemd is systemd


@pytest.fixture
def retained_pg(monkeypatch):
    """Opt-in real PostgreSQL; no SQLite emulation of quarantine/JSONB/locks."""
    import os
    import sys
    import uuid
    from datetime import UTC, datetime

    url = os.environ.get("RETAINED_TEST_DATABASE_URL")
    if not url:
        pytest.skip("RETAINED_TEST_DATABASE_URL required for PostgreSQL proof")
    monkeypatch.setenv("SECRET_KEY", "retained-test-secret-key-32-chars!!")
    monkeypatch.setenv(
        "GARMIN_ENCRYPTION_KEY", "mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU="
    )
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session

    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql" and "test" in parsed.database
    backend = Path(__file__).resolve().parents[1] / "backend"
    sys.path.insert(0, str(backend))
    import app.models  # noqa: F401
    from app.database import Base
    from app.services.system_knowledge_importer import import_system_kb_artifacts

    from scripts import quarantine_runtime_only_kb as quarantine
    from scripts import verify_runtime_only_kb_contract as probe

    engine = create_engine(url)
    schema = "retained_test_" + uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    connection = engine.connect()
    connection.execute(text(f'SET search_path TO "{schema}"'))
    connection.commit()
    Base.metadata.create_all(connection)
    connection.commit()
    db = Session(bind=connection)
    manifest_path = backend / "data/system_kb_v2_seed/review_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    before = datetime.now(UTC)
    import_system_kb_artifacts(db, manifest_path.parent, actor="test:retained-import")
    quarantine.quarantine_runtime_only_documents(
        db, manifest=manifest, actor="rollback:" + "b" * 12
    )
    after = datetime.now(UTC)
    try:
        yield db, probe, manifest, before, after
    finally:
        db.rollback()
        db.close()
        connection.close()
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()
        sys.path.remove(str(backend))


def test_retained_quarantine_postgres_accepts_actual_rollback_and_rolls_back(
    retained_pg,
):
    from app.models.system_knowledge import KBDocument
    from sqlalchemy import text

    db, probe, manifest, before, after = retained_pg
    m = load()
    # The original probe genuinely rejects the actual rollback state.
    with pytest.raises(RuntimeError, match="active reviewed pack mismatch"):
        probe.verify_runtime_only_database(db, manifest=manifest, require_present=True)
    db.rollback()
    original = db.query(KBDocument).count()
    db.rollback()
    result = m.quarantined_kb_probe(
        db, probe, manifest, "b" * 40, before, after, runtime_enabled=False
    )
    assert result["state"] == "ROLLBACK_QUARANTINED"
    assert (
        result["generic_eligible_documents"] == result["runtime_eligible_claims"] == 0
    )
    assert db.query(KBDocument).count() == original
    db.rollback()
    assert (
        db.execute(
            text(
                "SELECT count(*) FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory'"
            )
        ).scalar()
        == 0
    )


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "active",
        "type",
        "review",
        "artifact",
        "audit_actor",
        "audit_time",
        "audit_json",
        "enabled",
    ],
)
def test_retained_quarantine_postgres_rejects_corruption(retained_pg, fault):
    from datetime import timedelta

    from app.models.system_knowledge import KBAudit, KBDocument

    db, probe, manifest, before, after = retained_pg
    ids = probe.runtime_only_document_ids(manifest)
    doc = (
        db.query(KBDocument)
        .filter(KBDocument.doc_id.in_(ids), KBDocument.doc_type == "claim")
        .first()
    )
    audit = db.query(KBAudit).filter(KBAudit.op == "rollback_kb_quarantine").one()
    if fault == "missing":
        from app.models.system_knowledge import KBEdge
        from sqlalchemy import or_

        db.query(KBEdge).filter(
            or_(KBEdge.src_doc_id == doc.doc_id, KBEdge.dst_doc_id == doc.doc_id)
        ).delete(synchronize_session=False)
        db.delete(doc)
    elif fault == "active":
        doc.is_archived = False
    elif fault == "type":
        doc.doc_type = "entity"
    elif fault == "review":
        doc.metadata_json = {**doc.metadata_json, "review_status": "pending"}
    elif fault == "artifact":
        doc.title = "corrupted artifact"
    elif fault == "audit_actor":
        audit.actor = "rollback:" + "a" * 12
    elif fault == "audit_time":
        audit.ts = before - timedelta(days=1)
    elif fault == "audit_json":
        audit.diff = {**audit.diff, "matched_documents": True}
    db.commit()
    m = load()
    with pytest.raises((m.RetirementError, RuntimeError)):
        m.quarantined_kb_probe(
            db,
            probe,
            manifest,
            "b" * 40,
            before,
            after,
            runtime_enabled=fault == "enabled",
        )


def quarantine_fixture(sha):
    return {
        "state": "ROLLBACK_QUARANTINED",
        "candidate_sha": sha,
        "started": "2026-10-09T00:00:00+00:00",
        "completed": "2026-10-09T02:00:00+00:00",
        "audit_time": "2026-10-09T01:00:00+00:00",
        "audit_id": 1,
        "audit_sha256": "a" * 64,
        "pack_sha256": "b" * 64,
        "target_documents": 11,
        "matched_documents": 11,
        "generic_eligible_documents": 0,
        "runtime_eligible_claims": 0,
        "desktop_held_documents": 0,
        "genetic_held_claims": 0,
    }


@pytest.mark.parametrize("fail_after_projection", [False, True])
def test_retained_quarantine_postgres_lock_and_exception_rollback(
    retained_pg, monkeypatch, fail_after_projection
):
    from app.models.system_knowledge import KBAudit, KBDocument, KBEdge
    from sqlalchemy import event, text

    db, probe, manifest, before, after = retained_pg
    initial = tuple(db.query(model).count() for model in (KBDocument, KBEdge, KBAudit))
    db.rollback()
    commits = []
    event.listen(db, "before_commit", lambda session: commits.append(True))
    original = probe._verify_surface_projections
    calls = []

    def checked_projection(*args, **kwargs):
        with db.get_bind().engine.connect() as second:
            assert (
                second.execute(
                    text("SELECT pg_try_advisory_xact_lock(:key)"),
                    {"key": probe.SYSTEM_KB_RELEASE_MUTATION_LOCK_KEY},
                ).scalar()
                is False
            )
            second.rollback()
        result = original(*args, **kwargs)
        assert result == (0, 0)
        probe._assert_system_kb_release_mutation_lock_held(db)
        calls.append(result)
        if fail_after_projection:
            raise RuntimeError("injected projection failure")
        return result

    monkeypatch.setattr(probe, "_verify_surface_projections", checked_projection)
    m = load()
    if fail_after_projection:
        with pytest.raises(RuntimeError, match="injected projection failure"):
            m.quarantined_kb_probe(
                db, probe, manifest, "b" * 40, before, after, runtime_enabled=False
            )
    else:
        m.quarantined_kb_probe(
            db, probe, manifest, "b" * 40, before, after, runtime_enabled=False
        )
    assert calls and not commits
    assert (
        tuple(db.query(model).count() for model in (KBDocument, KBEdge, KBAudit))
        == initial
    )
    db.rollback()
    with db.get_bind().engine.connect() as second:
        assert (
            second.execute(
                text("SELECT pg_try_advisory_xact_lock(:key)"),
                {"key": probe.SYSTEM_KB_RELEASE_MUTATION_LOCK_KEY},
            ).scalar()
            is True
        )
        second.rollback()


def test_retained_quarantine_postgres_accepts_idempotent_audit(retained_pg):
    from app.models.system_knowledge import KBAudit

    db, probe, manifest, before, after = retained_pg
    audit = db.query(KBAudit).filter(KBAudit.op == "rollback_kb_quarantine").one()
    audit.diff = {**audit.diff, "archived_documents": 0}
    db.commit()
    result = load().quarantined_kb_probe(
        db, probe, manifest, "b" * 40, before, after, runtime_enabled=False
    )
    assert result["state"] == "ROLLBACK_QUARANTINED"


def test_quarantine_child_fixed_isolation_and_bounded_evidence(monkeypatch):
    m = load()
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(stdout=json.dumps(quarantine_fixture("b" * 40)).encode())

    monkeypatch.setattr(m.subprocess, "run", run)
    assert (
        m.quarantined_application_probes("b" * 40, "c" * 40)["state"]
        == "ROLLBACK_QUARANTINED"
    )
    argv, kwargs = calls[0]
    assert argv[:5] == ["/usr/bin/python3.12", "-I", "-S", "-B", "-c"]
    assert kwargs["env"] == m.ENV and kwargs["check"] is True
    assert kwargs["stderr"] == m.subprocess.DEVNULL
    monkeypatch.setattr(
        m.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=b"x" * 8193)
    )
    with pytest.raises(m.RetirementError, match="exceeds bound"):
        m.quarantined_application_probes("b" * 40, "c" * 40)


@pytest.mark.parametrize(
    "field,value",
    [
        ("candidate_sha", "a" * 40),
        ("state", "STAGED"),
        ("runtime_eligible_claims", 1),
        ("generic_eligible_documents", 1),
        ("desktop_held_documents", 1),
        ("genetic_held_claims", 1),
        ("matched_documents", 10),
        ("audit_id", True),
        ("audit_time", "2026-10-10T01:00:00+00:00"),
        ("completed", "2026-10-08T00:00:00+00:00"),
        ("audit_sha256", "invalid"),
    ],
)
def test_quarantine_archive_rejects_weakened_evidence(field, value):
    m = load()
    evidence = quarantine_fixture("b" * 40)
    evidence[field] = value
    with pytest.raises(m.RetirementError):
        m.validate_quarantine_evidence(evidence, "b" * 40)
