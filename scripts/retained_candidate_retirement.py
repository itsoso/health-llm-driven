"""Close a failed backend claim whose retained candidate is already finalized.

This isolated root operator writes its separate closure audit, then precisely
revokes the consumed identities after durable intent and repeated live proofs.
It never finalizes a runtime transaction, edits the consumed workspace, restarts
a service or authorizes retry of the failed revision.
"""

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path("/var/lib/reva-release")
RUNTIME = Path("/var/lib/health-app/release-state")
ROOT_NAME = "retained-candidate-closures"
TERMINAL = "CLOSED_RETAINED_CANDIDATE_FAILURE"
ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C"}
CONFLICTS = (
    "recoveries",
    "partial-laya-closures",
    "contained-release-closures",
    "unchanged-release-closures",
    "review-maintenance-closures",
    "lost-closure-receipt-acknowledgments",
    "contained-service-recoveries",
    "native-only-closures",
)


class RetirementError(Exception):
    """Only static, secret-free diagnostics cross the operator boundary."""


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_terminal(marker, sha):
    if not isinstance(marker, dict) or set(marker) != {
        "version",
        "old_sha",
        "candidate_sha",
        "terminal_sha",
        "phase",
        "target",
        "result",
        "transaction_id",
        "reap_name",
    }:
        raise RetirementError("terminal inventory invalid")
    if (
        type(marker["version"]) is not int
        or marker["version"] != 1
        or not isinstance(sha, str)
        or re.fullmatch("[a-f0-9]{40}", sha) is None
        or not isinstance(marker["old_sha"], str)
        or re.fullmatch("[a-f0-9]{40}", marker["old_sha"]) is None
        or marker["old_sha"] == sha
    ):
        raise RetirementError("terminal revision binding invalid")
    transaction = hashlib.sha256(f"{marker['old_sha']}:{sha}".encode()).hexdigest()[:32]
    expected = {
        "version": 1,
        "old_sha": marker["old_sha"],
        "candidate_sha": sha,
        "terminal_sha": sha,
        "phase": "COMMITTED",
        "target": "candidate",
        "result": "finalized",
        "transaction_id": transaction,
        "reap_name": "runtime-state-transaction.reap-" + transaction,
    }
    if marker != expected:
        raise RetirementError("finalized retained candidate required")


def assert_no_transaction(root):
    if any(
        p.name.startswith(("runtime-state-transaction", ".runtime-state-transaction"))
        for p in root.iterdir()
    ):
        raise RetirementError("runtime transaction or cleanup remains")


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(json.dumps(value, sort_keys=True).encode())
        stream.flush()
        os.fsync(stream.fileno())
    sync(path.parent)


def close_transaction(adapter, evidence_sha256=None):
    if os.path.lexists(adapter.record):
        raise RetirementError("closure already attempted; retry forbidden")
    adapter.check_record_parent()
    evidence = adapter.inspect()
    fingerprint = digest(evidence)
    if evidence_sha256 is None:
        return {
            "state": "INSPECTED_RETAINED_CANDIDATE_FAILURE",
            "evidence_sha256": fingerprint,
        }
    if evidence_sha256 != fingerprint:
        raise RetirementError("closure inspection changed")
    if not adapter.record.parent.exists():
        adapter.record.parent.mkdir(mode=0o700)
        sync(adapter.record.parent.parent)
    adapter.check_record_parent()
    adapter.record.mkdir(mode=0o700)
    sync(adapter.record.parent)
    receipt = secrets.token_hex(32)
    intent = {
        **evidence,
        "evidence_sha256": fingerprint,
        "receipt_sha256": hashlib.sha256(receipt.encode()).hexdigest(),
    }
    stage("intent")
    write_json(adapter.record / "intent.json", intent)
    if adapter.inspect() != evidence:
        raise RetirementError("closure evidence changed after intent")
    stage("revocation")
    adapter.retire_authorization(evidence)
    stage("completion")
    write_json(
        adapter.record / "completed.json",
        {
            "state": TERMINAL,
            "old_sha": evidence["old_sha"],
            "intent_sha256": digest(intent),
        },
    )
    return {"state": TERMINAL, "sha": evidence["old_sha"], "receipt": receipt}


def private_directory(b, path):
    b.secure(path)
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise RetirementError("private closure directory required")


def no_conflicts(b, sha):
    if any(os.path.lexists(b.STATE / name / sha) for name in CONFLICTS):
        raise RetirementError("conflicting failure closure history")


def workspace_evidence(b, sha):
    root = b.STATE / sha
    private_directory(b, root)
    required = {
        "started.json",
        "preparation-started.json",
        "prepared.json",
        "deployment-started.json",
        "completed.json",
        "preparation.log",
        "deployment.log",
        "deployment.env",
        "source",
        "home",
        "bin",
    }
    if {p.name for p in root.iterdir()} != required:
        raise RetirementError("only backend-only phase-complete failure supported")
    source = b.canonical_source(sha)
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
        expected = {"sha": sha, "state": state}
        if name == "preparation-started.json":
            expected["executor_sha256"] = executor
        if b._read_json(root / name) != expected:
            raise RetirementError("original failed phase receipt differs")
    # Entire original tree, including logs, environment, git and tools; hashes
    # only. No execution/import from the failed checkout and no emitted secrets.
    return {"executor_sha256": executor, "manifest": b._preparation_manifest(root)}


def load(b, path, name):
    b.secure(path)
    if os.path.lexists(path.parent / "__pycache__"):
        raise RetirementError("cached operator code forbidden")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


STAGE = "arguments"
STAGES = {
    "arguments",
    "canonical_ci",
    "locks",
    "workspace",
    "authorization",
    "runtime",
    "vision_overlay",
    "effective_units",
    "laya",
    "application_probes",
    "history",
    "intent",
    "revocation",
    "completion",
}


def stage(name):
    global STAGE
    if name not in STAGES:
        raise RetirementError("unknown diagnostic stage")
    STAGE = name


def vision_paths(unit):
    return [
        "/".join(("/etc/systemd/system", unit + ".d", name))
        for name in (
            "80-reva-health-evidence-runtime.conf",
            "90-runtime-state.conf",
            "security-network.conf",
            "zzzz-reva-vision-model.conf",
        )
    ]


class VisionBaseView:
    """Private exact projection: every property except these paths stays raw."""

    def __init__(self, systemd, raw):
        self.systemd = systemd
        self.raw = dict(raw)
        if set(self.raw) != {
            "health-backend.service",
            "celery-worker.service",
            "celery-beat.service",
        }:
            raise RetirementError("vision unit inventory differs")
        if any(
            value != " ".join(vision_paths(unit)) for unit, value in self.raw.items()
        ):
            raise RetirementError("unrecognized raw unit drop-ins")

    def show(self, unit, prop):
        value = self.systemd.show(unit, prop)
        if unit in self.raw and prop == "DropInPaths":
            if value != self.raw[unit]:
                raise RetirementError("raw model drop-ins changed")
            return " ".join(vision_paths(unit)[:-1])
        return value

    def is_enabled(self, unit):
        return self.systemd.is_enabled(unit)


def validate_vision_documents(operation, before, intent, verified, completed):
    if (
        not isinstance(before, dict)
        or set(before)
        != {
            "kind",
            "publisher_sha",
            "production_sha",
            "operation_id",
            "model",
            "services",
            "protected_metadata",
            "before",
            "acceptance",
            "production_apply_enabled",
        }
        or before["kind"] != "vision-model-selection"
        or before["model"] != "qwen3.8-flash"
        or before["operation_id"] != operation
        or before["acceptance"] != "PENDING"
        or before["production_apply_enabled"] is not True
        or any(
            not isinstance(before[k], str)
            or re.fullmatch("[a-f0-9]{40}", before[k]) is None
            for k in ("publisher_sha", "production_sha")
        )
        or not isinstance(operation, str)
        or re.fullmatch("[a-f0-9]{32}", operation) is None
    ):
        raise RetirementError("vision original operation binding invalid")
    expected = {
        "state": "CONFIG_SUCCEEDED_PENDING_MODEL_ACCEPTANCE",
        "publisher_sha": before["publisher_sha"],
        "production_sha": before["production_sha"],
        "operation_id": operation,
        "model": "qwen3.8-flash",
        "model_acceptance": "PENDING",
        "model_requests": 0,
        "evidence_sha256": digest(before),
    }
    if (
        not isinstance(completed, dict)
        or set(completed) != {*expected, "services"}
        or any(completed[k] != v for k, v in expected.items())
        or type(completed["model_requests"]) is not int
        or completed != verified
        or intent != {"state": "CONFIG_STARTED", "evidence_sha256": digest(before)}
    ):
        raise RetirementError(
            "vision terminal does not bind verified original operation"
        )
    return expected


def vision_history(b, source, operation):
    root = b.STATE / "vision-models" / operation
    inventory = b._inventory(
        root,
        {"before.json", "intent.json", "lease.json", "verified.json", "completed.json"},
    )
    before, intent, verified, completed = (
        b._read_json(root / name)
        for name in ("before.json", "intent.json", "verified.json", "completed.json")
    )
    summary = validate_vision_documents(operation, before, intent, verified, completed)
    publisher = b.canonical_source(summary["publisher_sha"])
    b.canonical_source(summary["production_sha"])
    if b._read_json(b.STATE / summary["production_sha"] / "completed.json") != {
        "sha": summary["production_sha"],
        "state": "SUCCEEDED",
    }:
        raise RetirementError("vision original production success unproven")
    path = publisher / "scripts/trusted_vision_model.py"
    b.secure(path)
    return {
        "operation": summary,
        "inventory": inventory,
        "publisher_operator_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def inspect_vision_overlay(b, source, systemd):
    stage("vision_overlay")
    vision = load(
        b, source / "scripts/trusted_vision_model.py", "retained_vision_overlay"
    )
    server = load(
        b, source / "scripts/trusted_release_server.py", "retained_vision_history"
    )
    server.assert_vision_model_history(b.STATE)
    root = b.STATE / "vision-models"
    private_directory(b, root)
    operations = sorted(path.name for path in root.iterdir())
    if len(operations) != 1 or re.fullmatch("[a-f0-9]{32}", operations[0]) is None:
        raise RetirementError("only one proven initial vision operation supported")
    history = vision_history(b, source, operations[0])
    vision.finalization_model_files(rolled_back=False)
    files = {
        str(path): vision.optional_model_file(path)
        for path in [
            vision.MODEL,
            *(
                vision.SYSTEMD / (unit + ".service.d") / vision.DROPIN_NAME
                for unit in vision.SERVICES
            ),
        ]
    }
    if any(
        item["metadata"]["uid"] != 0
        or item["metadata"]["gid"] != 0
        or stat.S_IMODE(item["metadata"]["mode"]) != 0o600
        for item in files.values()
    ):
        raise RetirementError("vision model file metadata differs")
    services = vision.service_snapshot(installed=True)
    raw = {}
    for unit in vision.SERVICES:
        name = unit + ".service"
        raw[name] = systemd.show(name, "DropInPaths")
        if raw[name] != services[unit]["DropInPaths"]:
            raise RetirementError("vision service snapshots differ")
        pid = int(services[unit]["MainPID"])
        vision.target_process_model(pid)
        if vision.process_start(pid) != services[unit]["process_start"]:
            raise RetirementError("vision process identity changed")
    VisionBaseView(systemd, raw)
    return {
        "model": "qwen3.8-flash",
        "history": history,
        "files": files,
        "services": services,
        "raw_dropins": raw,
    }


def validate_archived_vision(b, source, value):
    if (
        not isinstance(value, dict)
        or set(value) != {"model", "history", "files", "services", "raw_dropins"}
        or value["model"] != "qwen3.8-flash"
    ):
        raise RetirementError("archived vision profile differs")
    operation = value["history"]["operation"]["operation_id"]
    if vision_history(b, source, operation) != value["history"]:
        raise RetirementError("archived vision operation evidence changed")
    vision = load(
        b, source / "scripts/trusted_vision_model.py", "retained_archived_vision"
    )
    VisionBaseView(None, value["raw_dropins"])
    expected_files = {
        "/var/lib/reva-vision-model/model.env": vision.model_bytes(
            "qwen3.8-flash"
        ).decode()
    }
    expected_files.update(
        {
            vision_paths(unit)[-1]: vision.dropin_bytes().decode()
            for unit in value["raw_dropins"]
        }
    )
    if not isinstance(value["files"], dict) or set(value["files"]) != set(
        expected_files
    ):
        raise RetirementError("archived vision file inventory differs")
    for path, content in expected_files.items():
        item = value["files"][path]
        if (
            not isinstance(item, dict)
            or set(item) != {"metadata", "content"}
            or item["content"] != content
        ):
            raise RetirementError("archived vision file content differs")
        metadata = item["metadata"]
        if (
            not isinstance(metadata, dict)
            or set(metadata)
            != {
                "dev",
                "ino",
                "mode",
                "nlink",
                "uid",
                "gid",
                "size",
                "mtime_ns",
                "ctime_ns",
            }
            or any(type(v) is not int or v < 0 for v in metadata.values())
            or metadata["uid"] != 0
            or metadata["gid"] != 0
            or metadata["nlink"] != 1
            or metadata["ino"] <= 0
            or metadata["size"] != len(content.encode())
            or metadata["mode"] != stat.S_IFREG | 0o600
        ):
            raise RetirementError("archived vision metadata differs")
    if not isinstance(value["services"], dict) or set(value["services"]) != set(
        vision.SERVICES
    ):
        raise RetirementError("archived vision service inventory differs")
    for unit, service in value["services"].items():
        if (
            service.get("DropInPaths") != value["raw_dropins"][unit + ".service"]
            or service.get("ActiveState") != "active"
            or service.get("SubState") != "running"
            or any(
                not isinstance(service.get(k), str)
                or not service[k].isdigit()
                or int(service[k]) <= 0
                for k in ("MainPID", "process_start")
            )
        ):
            raise RetirementError("archived vision service binding differs")
        vision.validate_env_sources(service.get("EnvironmentFiles"), installed=True)
        vision.validate_unset_environment(service.get("UnsetEnvironment"))


def candidate_configuration(b, source, sha, marker, proof, runtime):
    """Use only existing read-only effective-unit and installation verifiers."""
    candidate = b.canonical_source(sha)
    proof.bootstrap = b
    proof.source = source
    proof.production_sha = sha
    proof.production = Path("/opt/health-app")
    proof.failed_sha = sha
    proof.runtime = runtime
    proof.systemd_root = Path("/etc/systemd/system")
    proof.installed_laya = True
    proof.stage = None
    proof.lease = None
    transaction = object.__new__(runtime.ReleaseTransaction)
    transaction.systemd = proof.systemd
    # _old_effective only consumes these read-only layout fields. No fabricated
    # release-stage pathname or lease is passed to production_layout/transaction.
    transaction.layout = SimpleNamespace(
        base_units={unit: proof.systemd_root / unit for unit in runtime.UNITS},
        legacy_shelf_base=Path("/opt/health-app/backend/data/celerybeat-schedule"),
        current_shelf_base=Path("/var/lib/health-app/celery-beat/celerybeat-schedule"),
    )
    started = datetime.fromtimestamp(
        (b.STATE / sha / "deployment-started.json").stat().st_mtime, UTC
    )
    raw_systemd = proof.systemd
    overlay = inspect_vision_overlay(b, source, raw_systemd)
    proof.systemd = transaction.systemd = VisionBaseView(
        raw_systemd, overlay["raw_dropins"]
    )
    try:
        stage("effective_units")
        units = proof._units(
            candidate, transaction, started_at=started.strftime("%Y-%m-%dT%H:%M:%SZ\n")
        )
    finally:
        proof.systemd = raw_systemd
    stage("laya")
    laya = candidate_laya(b, source, sha, marker, proof)
    if inspect_vision_overlay(b, source, raw_systemd) != overlay:
        raise RetirementError("vision overlay changed during candidate verification")
    return {"units": units, "laya": laya, "vision_overlay": overlay}


def candidate_laya(b, source, sha, marker, proof):
    installer = load(b, source / "infra/laya/install.py", "retained_laya_verifier")
    candidate = b.canonical_source(sha) / "infra/laya"
    assets = {}
    for name in installer.ASSETS:
        raw, _ = proof._file(candidate / name)
        if raw != proof._file(source / "infra/laya" / name)[0]:
            raise RetirementError("closing Laya implementation differs from candidate")
        assets[name] = hashlib.sha256(raw).hexdigest()
    server = load(
        b, source / "scripts/trusted_release_server.py", "retained_laya_environment"
    )
    config = installer.parse_config(server.read_production_env())
    if config is None:
        raise RetirementError(
            "retained candidate requires installed Laya configuration"
        )
    generation, _, _, expected = installer.expected_install(candidate, config)
    receipt_path = installer.STATE / "install.json"
    raw, receipt_identity = proof._file(receipt_path, 0o600)
    receipt = b._read_json(receipt_path)
    if (
        set(receipt)
        != {
            "generation",
            "unit_sha256",
            "env_sha256",
            "state",
            "candidate_sha",
            "lease",
        }
        or not isinstance(receipt["candidate_sha"], str)
        or re.fullmatch("[a-f0-9]{40}", receipt["candidate_sha"]) is None
        or not isinstance(receipt["lease"], str)
        or re.fullmatch("[a-f0-9]{64}", receipt["lease"]) is None
    ):
        raise RetirementError("Laya installed receipt provenance invalid")
    installer.reusable(receipt, expected)
    origin = b.canonical_source(receipt["candidate_sha"]) / "infra/laya"
    if installer.expected_install(origin, config)[3] != expected:
        raise RetirementError("Laya origin does not match retained candidate")
    exported = installer.STATE / "sources" / sha
    proof._directory(exported)
    if {item.name for item in exported.iterdir()} != {*installer.ASSETS, "source.json"}:
        raise RetirementError("candidate Laya export inventory differs")
    parser = load(
        b, source / "scripts/contained_recovery_proof.py", "retained_export_parser"
    )
    manifest = parser.object_json(proof._file(exported / "source.json", 0o400)[0])
    if manifest != {
        "sha": sha,
        "old_sha": marker["old_sha"],
        "old_has_decisions": True,
        "files": assets,
    }:
        raise RetirementError("candidate Laya export binding differs")
    exported_files = {}
    for name in (*installer.ASSETS, "source.json"):
        raw, exported_files[name] = proof._file(exported / name, 0o400)
        if name in assets and hashlib.sha256(raw).hexdigest() != assets[name]:
            raise RetirementError("candidate Laya export bytes differ")
    absent = [
        installer.STATE / "install.json.pending",
        installer.UNIT.with_name(installer.UNIT.name + ".pending"),
        installer.ENV.with_name(installer.ENV.name + ".pending"),
    ]
    if any(os.path.lexists(path) for path in absent):
        raise RetirementError("Laya pending activation remains")

    def snapshot():
        value = installer.service_identity(generation)
        if proof.systemd.show("reva-laya.service", "NeedDaemonReload") != "no":
            raise RetirementError("Laya reload pending")
        value["ExecStart"] = runtime_exec = (
            proof.runtime.ReleaseTransaction._stable_exec_start(
                None, proof.systemd.show("reva-laya.service", "ExecStart")
            )
        )
        executable = generation / "venv/bin/python"
        if (
            runtime_exec
            != f"path={executable}\nargv[]={executable} -I {generation / 'serve.py'}\nignore_errors=no"
        ):
            raise RetirementError("Laya effective command differs")
        pids = proof._pids("reva-laya.service")
        if pids != [value["MainPID"]]:
            raise RetirementError("Laya process inventory differs")
        value["processes"] = {
            pid: (proof.proc / pid / "stat")
            .read_bytes()
            .rsplit(b")", 1)[-1]
            .split()[19]
            .decode()
            for pid in pids
        }
        value["boot_id"] = (
            (proof.proc / "sys/kernel/random/boot_id").read_text().strip()
        )
        return value

    files = {
        str(path): proof._file(path)[1]
        for path in (receipt_path, installer.UNIT, installer.ENV)
    }
    before = snapshot()
    installer.verify_install(candidate, config)
    if snapshot() != before or any(
        proof._file(Path(path))[1] != value for path, value in files.items()
    ):
        raise RetirementError("Laya changed during candidate verification")
    return {
        "candidate_sha": sha,
        "assets": assets,
        "expected": expected,
        "receipt": receipt,
        "receipt_identity": receipt_identity,
        "files": files,
        "exported_source": exported_files,
        "services": before,
    }


def live_state(b, source, closing_sha, sha):
    b._assert_idle()
    b._recovery_process_proof()
    b.secure(RUNTIME)
    assert_no_transaction(RUNTIME)
    absent = [
        Path("/var/lib/reva-health-evidence-runtime/enabled.env"),
        Path("/run/reva-health-evidence-activation"),
        Path("/opt/health-app/backend/.env.reva-release.tmp"),
    ]
    absent += [
        Path("/run/systemd/system")
        / (name + ".d")
        / "90-reva-health-evidence-activation.conf"
        for name in (
            "health-backend.service",
            "celery-worker.service",
            "celery-beat.service",
        )
    ]
    if any(os.path.lexists(path) for path in absent):
        raise RetirementError("runtime activation artifacts remain")
    terminal_path = RUNTIME / "runtime-state-terminal.json"
    identity = b._recovery_file_identity(terminal_path)
    marker = b._read_json(terminal_path)
    validate_terminal(marker, sha)
    b._recovery_production_proof(sha, source)
    runtime = load(
        b,
        source / "backend/scripts/runtime_state_release_transaction.py",
        "retained_runtime",
    )
    proof_module = load(
        b, source / "scripts/contained_recovery_proof.py", "retained_service_proof"
    )
    proof = object.__new__(proof_module.RecoveryProof)
    proof.proc = Path("/proc")
    proof.cgroup = Path("/sys/fs/cgroup")
    proof.systemd = runtime.SubprocessSystemd()
    configuration = candidate_configuration(b, source, sha, marker, proof, runtime)
    before = proof.running_services_snapshot()
    recovery = load(
        b,
        source / "scripts/recover_contained_services.py",
        "retained_application_probe",
    )
    stage("application_probes")
    recovery._application_probes(sha, closing_sha)
    recovery._http_probes()
    time.sleep(7)
    if (
        proof.running_services_snapshot() != before
        or candidate_configuration(b, source, sha, marker, proof, runtime)
        != configuration
    ):
        raise RetirementError("services changed during inspection")
    b._recovery_production_proof(sha, source)
    assert_no_transaction(RUNTIME)
    b._assert_idle()
    b._recovery_process_proof()
    if b._recovery_file_identity(terminal_path) != identity:
        raise RetirementError("terminal changed during inspection")
    return {
        "terminal": marker,
        "terminal_identity": identity,
        "services": before,
        "configuration": configuration,
        "probes": {
            "schema": True,
            "runtime_only_kb": True,
            "auth_unauthenticated_401": True,
            "health_dependencies": True,
            "runtime_flag_false": True,
        },
    }


def validate_configuration(b, source, sha, configuration):
    """Replay archived contracts using canonical files, never live host state."""
    stage("history")
    if not isinstance(configuration, dict) or set(configuration) != {
        "units",
        "laya",
        "vision_overlay",
    }:
        raise RetirementError("candidate configuration evidence incomplete")
    validate_archived_vision(b, source, configuration["vision_overlay"])
    runtime = load(
        b,
        source / "backend/scripts/runtime_state_release_transaction.py",
        "retained_archived_runtime",
    )
    module = load(
        b, source / "scripts/contained_recovery_proof.py", "retained_archived_units"
    )
    closure = load(
        b,
        source / "scripts/contained_release_retirement.py",
        "retained_archived_network",
    )
    units = configuration["units"]
    required = {*module.UNITS, "effective", "network_guard"}
    if not isinstance(units, dict) or set(units) != required:
        raise RetirementError("candidate effective unit inventory incomplete")
    closure.validate_network_guard_snapshot(
        {
            "units": units,
            "installed_laya": {"started_at": units["network_guard"].get("started_at")},
        },
        unchanged=True,
    )
    proof = object.__new__(module.RecoveryProof)
    proof.bootstrap = b
    proof.runtime = runtime
    proof.stage = None
    proof.lease = None
    candidate = b.canonical_source(sha)
    dropins, _ = proof._production_unit_profile(candidate)
    transaction = object.__new__(runtime.ReleaseTransaction)
    effective = runtime.ReleaseTransaction._stable_effective_snapshot(
        transaction, units["effective"]
    )
    if effective != units["effective"]:
        raise RetirementError("archived effective properties are not canonical")
    worker = "/opt/health-app/backend/venv/bin/celery -A app.celery_app:celery_app worker --loglevel=info --concurrency=4"
    proof._production_effective(transaction, effective, dropins, worker)
    for unit in module.UNITS:
        value = units[unit]
        required_entry = (
            {"base"}
            if unit.endswith(".socket")
            else {
                "base",
                "80-reva-health-evidence-runtime.conf",
                "90-runtime-state.conf",
            }
        )
        if (
            not isinstance(value, dict)
            or set(value) - {"legacy_security_effective"} != required_entry
        ):
            raise RetirementError("archived unit files incomplete")
        if "legacy_security_effective" in value:
            module.validate_security_effective(unit, value["legacy_security_effective"])
        for name in required_entry:
            validate_file_identity(value[name], modes={0o644})
        if unit.endswith(".service"):
            for name, raw in [
                ("80-reva-health-evidence-runtime.conf", module.ACTIVATION),
                ("90-runtime-state.conf", dropins[unit]),
            ]:
                if value[name]["sha256"] != hashlib.sha256(raw).hexdigest():
                    raise RetirementError("archived candidate drop-in differs")
            paths = " ".join(
                "/etc/systemd/system/" + unit + ".d/" + name
                for name in (
                    "80-reva-health-evidence-runtime.conf",
                    "90-runtime-state.conf",
                    "security-network.conf",
                )
            )
            if (
                effective[unit]["FragmentPath"] != "/etc/systemd/system/" + unit
                or effective[unit]["DropInPaths"] != paths
            ):
                raise RetirementError("archived effective unit source differs")
    validate_laya_snapshot(b, source, sha, configuration["laya"])


def validate_file_identity(value, *, modes, root_group=True):
    if (
        not isinstance(value, dict)
        or set(value) != {"dev", "ino", "uid", "gid", "mode", "sha256"}
        or any(
            type(value[k]) is not int or value[k] < 0
            for k in ("dev", "ino", "uid", "gid", "mode")
        )
        or value["uid"] != 0
        or root_group
        and value["gid"] != 0
        or value["ino"] <= 0
        or value["mode"] not in modes
        or not isinstance(value["sha256"], str)
        or re.fullmatch("[a-f0-9]{64}", value["sha256"]) is None
    ):
        raise RetirementError("archived file identity invalid")


def validate_laya_snapshot(b, source, sha, value):
    required = {
        "candidate_sha",
        "assets",
        "expected",
        "receipt",
        "receipt_identity",
        "files",
        "exported_source",
        "services",
    }
    if (
        not isinstance(value, dict)
        or set(value) != required
        or value["candidate_sha"] != sha
    ):
        raise RetirementError("archived Laya candidate binding invalid")
    installer = load(b, source / "infra/laya/install.py", "retained_archived_laya")
    candidate = b.canonical_source(sha) / "infra/laya"
    assets = {
        name: hashlib.sha256((candidate / name).read_bytes()).hexdigest()
        for name in installer.ASSETS
    }
    if value["assets"] != assets:
        raise RetirementError("archived Laya candidate assets differ")
    expected = value["expected"]
    generation, _, _, synthetic = installer.expected_install(
        candidate, {"DECISION_API_KEY": ""}
    )
    if (
        not isinstance(expected, dict)
        or set(expected) != {"generation", "unit_sha256", "env_sha256"}
        or any(
            not isinstance(v, str) or re.fullmatch("[a-f0-9]{64}", v) is None
            for v in expected.values()
        )
        or any(expected[k] != synthetic[k] for k in ("generation", "unit_sha256"))
    ):
        raise RetirementError("archived Laya generation differs")
    receipt = value["receipt"]
    if (
        not isinstance(receipt, dict)
        or set(receipt) != {*expected, "state", "candidate_sha", "lease"}
        or not isinstance(receipt["candidate_sha"], str)
        or re.fullmatch("[a-f0-9]{40}", receipt["candidate_sha"]) is None
        or not isinstance(receipt["lease"], str)
        or re.fullmatch("[a-f0-9]{64}", receipt["lease"]) is None
    ):
        raise RetirementError("archived Laya receipt invalid")
    installer.reusable(receipt, expected)
    origin = installer.expected_install(
        b.canonical_source(receipt["candidate_sha"]) / "infra/laya",
        {"DECISION_API_KEY": ""},
    )[3]
    if any(origin[k] != expected[k] for k in ("generation", "unit_sha256")):
        raise RetirementError("archived Laya origin differs")
    files = value["files"]
    paths = {
        str(installer.STATE / "install.json"),
        str(installer.UNIT),
        str(installer.ENV),
    }
    if not isinstance(files, dict) or set(files) != paths:
        raise RetirementError("archived Laya files incomplete")
    for path, identity in files.items():
        mode = (
            0o640
            if path == str(installer.ENV)
            else 0o644
            if path == str(installer.UNIT)
            else 0o600
        )
        validate_file_identity(
            identity, modes={mode}, root_group=path != str(installer.ENV)
        )
    if (
        files[str(installer.STATE / "install.json")] != value["receipt_identity"]
        or files[str(installer.UNIT)]["sha256"] != expected["unit_sha256"]
        or files[str(installer.ENV)]["sha256"] != expected["env_sha256"]
    ):
        raise RetirementError("archived Laya file binding differs")
    exported = value["exported_source"]
    if not isinstance(exported, dict) or set(exported) != {*assets, "source.json"}:
        raise RetirementError("archived Laya export incomplete")
    for name, identity in exported.items():
        validate_file_identity(identity, modes={0o400})
        if name in assets and identity["sha256"] != assets[name]:
            raise RetirementError("archived Laya export binding differs")
    service = value["services"]
    fixed = {
        "ActiveState": "active",
        "SubState": "running",
        "FragmentPath": str(installer.UNIT),
        "DropInPaths": "",
        "User": "reva-laya",
        "Group": "reva-laya",
        "UnitFileState": "enabled",
    }
    executable = generation / "venv/bin/python"
    if (
        not isinstance(service, dict)
        or set(service)
        != {*fixed, "MainPID", "NRestarts", "ExecStart", "processes", "boot_id"}
        or any(service[k] != v for k, v in fixed.items())
        or any(
            not isinstance(service[k], str) or not service[k].isdigit()
            for k in ("MainPID", "NRestarts")
        )
        or int(service["MainPID"]) <= 1
        or service["ExecStart"]
        != f"path={executable}\nargv[]={executable} -I {generation / 'serve.py'}\nignore_errors=no"
        or not isinstance(service["processes"], dict)
        or set(service["processes"]) != {service["MainPID"]}
        or any(
            not isinstance(v, str) or not v.isdigit() or int(v) <= 0
            for v in service["processes"].values()
        )
        or not isinstance(service["boot_id"], str)
        or re.fullmatch(
            "[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}", service["boot_id"]
        )
        is None
    ):
        raise RetirementError("archived Laya service identity differs")


def active_installation_evidence(b, sha, executor):
    config = b._inventory(
        b.CONFIG,
        {
            "known_hosts",
            "loopback.conf",
            "authorized-release.json",
            "loopback.pub",
            "cloud.pub",
            "loopback.key",
        },
    )
    library = b._inventory(b.INSTALLED.parent, {b.INSTALLED.name})
    policy = b._read_json(b.CONFIG / "authorized-release.json")
    if (
        not isinstance(policy, dict)
        or set(policy) != {"sha", "expires_at", "executor_sha256"}
        or policy["sha"] != sha
        or type(policy["expires_at"]) is not int
        or policy["executor_sha256"] != executor
        or library[b.INSTALLED.name]["sha256"] != executor
    ):
        raise RetirementError("active installation binding differs")
    public = [
        (b.CONFIG / name).read_text().strip() for name in ("cloud.pub", "loopback.pub")
    ]
    for key in public:
        b.validate_install(sha, 1, key, now=0)
    if public[0] == public[1]:
        raise RetirementError("release identities must differ")
    b.secure(b.AUTHORIZED, private=True)
    lines = b.AUTHORIZED.read_text().splitlines()
    expected = b.key_lines(policy["expires_at"], *public)
    if any(
        [line for line in lines if key.split()[1] in line] != [exact]
        for key, exact in zip(public, expected)
    ):
        raise RetirementError("original active authorization differs")
    return {
        "config": config,
        "library": library,
        "authorized": b._recovery_file_identity(b.AUTHORIZED),
    }


class Adapter:
    def __init__(self, b, source, closing_sha, sha, check_locks):
        self.b, self.source, self.closing_sha, self.sha = b, source, closing_sha, sha
        self.check_locks = check_locks
        self.record = b.STATE / ROOT_NAME / sha

    def check_record_parent(self):
        if os.path.lexists(self.record.parent):
            private_directory(self.b, self.record.parent)
        else:
            self.b.secure(self.record.parent.parent)

    def inspect(self):
        b = self.b
        self.check_locks()
        no_conflicts(b, self.sha)
        if b.canonical_source(self.closing_sha) != self.source:
            raise RetirementError("closing source changed")
        stage("workspace")
        before = workspace_evidence(b, self.sha)
        stage("authorization")
        active = active_installation_evidence(b, self.sha, before["executor_sha256"])
        installation = {
            "config": {
                key: value
                for key, value in active["config"].items()
                if key != "loopback.key"
            },
            "library": active["library"],
        }
        stage("runtime")
        live = live_state(b, self.source, self.closing_sha, self.sha)
        validate_live_snapshot(live, self.sha)
        validate_configuration(b, self.source, self.sha, live["configuration"])
        if workspace_evidence(b, self.sha) != before:
            raise RetirementError("original workspace changed during inspection")
        self.check_locks()
        return {
            "old_sha": self.sha,
            "closing_sha": self.closing_sha,
            "workspace": before,
            "installation": installation,
            "active_installation": active,
            "live": live,
            "launcher": b._recovery_file_identity(b.STATE / "launcher.lock"),
        }

    def retire_authorization(self, evidence):
        # The caller has persisted intent and repeated the complete live proof.
        # Do not relax bootstrap.revoke for other NEEDS_OPERATOR workspaces.
        b = self.b
        self.check_locks()
        if (
            active_installation_evidence(
                b, self.sha, evidence["workspace"]["executor_sha256"]
            )
            != evidence["active_installation"]
        ):
            raise RetirementError(
                "active authorization changed before closure revocation"
            )
        policy = b._read_json(b.CONFIG / "authorized-release.json")
        public = [
            (b.CONFIG / name).read_text().strip()
            for name in ("cloud.pub", "loopback.pub")
        ]
        expected = b.key_lines(policy["expires_at"], *public)
        retained = b"".join(
            line
            for line in b.AUTHORIZED.read_bytes().splitlines(keepends=True)
            if line.decode().rstrip("\r\n") not in expected
        )
        b._replace_authorized(retained)
        if b.AUTHORIZED.read_bytes() != retained:
            raise RetirementError("closure revocation postcondition failed")
        original_config = evidence["active_installation"]["config"]
        if b._inventory(b.CONFIG, original_config.keys() - {"."}) != original_config:
            raise RetirementError("configuration drift before old private key removal")
        (b.CONFIG / "loopback.key").unlink()
        sync(b.CONFIG)
        if (
            b._installation_evidence(self.sha, b.CONFIG, b.INSTALLED.parent)
            != evidence["installation"]
        ):
            raise RetirementError("post-revocation installation differs")
        if (
            workspace_evidence(b, self.sha) != evidence["workspace"]
            or live_state(b, self.source, self.closing_sha, self.sha)
            != evidence["live"]
        ):
            raise RetirementError("retained candidate changed after revocation")
        self.check_locks()


def validate_live_snapshot(live, sha):
    if not isinstance(live, dict) or set(live) != {
        "terminal",
        "terminal_identity",
        "services",
        "configuration",
        "probes",
    }:
        raise RetirementError("invalid retained live snapshot")
    validate_terminal(live["terminal"], sha)
    identity = live["terminal_identity"]
    if (
        not isinstance(identity, dict)
        or set(identity) != {"uid", "gid", "mode", "inode", "device", "sha256"}
        or any(
            type(identity[k]) is not int
            for k in ("uid", "gid", "mode", "inode", "device")
        )
        or identity["uid"] != 0
        or identity["gid"] != 0
        or identity["mode"] != 0o600
        or identity["inode"] <= 0
        or identity["device"] < 0
        or not isinstance(identity["sha256"], str)
        or re.fullmatch("[a-f0-9]{64}", identity["sha256"]) is None
    ):
        raise RetirementError("unsafe archived terminal identity")
    probes = {
        "schema",
        "runtime_only_kb",
        "auth_unauthenticated_401",
        "health_dependencies",
        "runtime_flag_false",
    }
    if (
        not isinstance(live["probes"], dict)
        or set(live["probes"]) != probes
        or any(value is not True for value in live["probes"].values())
    ):
        raise RetirementError("incomplete archived probe evidence")
    services = live["services"]
    units = {
        "health-backend.socket",
        "health-backend.service",
        "celery-worker.service",
        "celery-beat.service",
    }
    if not isinstance(services, dict) or set(services) != units:
        raise RetirementError("incomplete archived services")
    for unit, value in services.items():
        fields = {
            "ActiveState",
            "SubState",
            "MainPID",
            "NRestarts",
            "ActiveEnterTimestampMonotonic",
            "ControlGroup",
            "Result",
        }
        service = unit.endswith(".service")
        if service:
            fields.add("processes")
        if (
            not isinstance(value, dict)
            or set(value) != fields
            or value["ActiveState"] != "active"
            or value["Result"] != "success"
            or value["SubState"]
            not in ({"running"} if service else {"listening", "running"})
            or any(
                not isinstance(value[k], str) or not value[k].isdigit()
                for k in ("MainPID", "NRestarts", "ActiveEnterTimestampMonotonic")
            )
            or int(value["ActiveEnterTimestampMonotonic"]) <= 0
        ):
            raise RetirementError("invalid archived service readiness")
        if service:
            processes = value["processes"]
            if (
                not isinstance(processes, dict)
                or value["MainPID"] not in processes
                or any(
                    not isinstance(pid, str)
                    or not pid.isdigit()
                    or int(pid) <= 1
                    or not isinstance(start, str)
                    or not start.isdigit()
                    or int(start) <= 0
                    for pid, start in processes.items()
                )
            ):
                raise RetirementError("invalid archived service identity")


def closed_evidence(b, sha, receipt, *, historical=False):
    no_conflicts(b, sha)
    root = b.STATE / ROOT_NAME / sha
    private_directory(b, root.parent)
    private_directory(b, root)
    b._inventory(root, {"intent.json", "completed.json"})
    intent = b._read_json(root / "intent.json")
    completed = b._read_json(root / "completed.json")
    required = {
        "old_sha",
        "closing_sha",
        "workspace",
        "installation",
        "active_installation",
        "live",
        "launcher",
        "evidence_sha256",
        "receipt_sha256",
    }
    if (
        not isinstance(intent, dict)
        or set(intent) != required
        or intent["old_sha"] != sha
        or not isinstance(intent["closing_sha"], str)
        or re.fullmatch("[a-f0-9]{40}", intent["closing_sha"]) is None
        or intent["closing_sha"] == sha
        or intent["evidence_sha256"]
        != digest(
            {
                k: v
                for k, v in intent.items()
                if k not in {"evidence_sha256", "receipt_sha256"}
            }
        )
        or completed
        != {"state": TERMINAL, "old_sha": sha, "intent_sha256": digest(intent)}
    ):
        raise RetirementError("closure audit binding invalid")
    if (
        not isinstance(receipt, str)
        or re.fullmatch("[a-f0-9]{64}", receipt) is None
        or not isinstance(intent["receipt_sha256"], str)
        or not secrets.compare_digest(
            hashlib.sha256(receipt.encode()).hexdigest(), intent["receipt_sha256"]
        )
    ):
        raise RetirementError("original protected closure receipt required")
    active = intent["active_installation"]
    if (
        not isinstance(active, dict)
        or set(active) != {"config", "library", "authorized"}
        or not isinstance(active["config"], dict)
        or "loopback.key" not in active["config"]
        or intent["installation"]
        != {
            "config": {
                k: v for k, v in active["config"].items() if k != "loopback.key"
            },
            "library": active["library"],
        }
    ):
        raise RetirementError("archived revocation installation binding invalid")
    source = b.canonical_source(intent["closing_sha"])
    validate_live_snapshot(intent["live"], sha)
    validate_configuration(b, source, sha, intent["live"]["configuration"])
    if workspace_evidence(b, sha) != intent["workspace"]:
        raise RetirementError("original failed workspace changed")
    config, library = b._archives(sha)
    if not os.path.lexists(config) and not os.path.lexists(library):
        config, library = b.CONFIG, b.INSTALLED.parent
    if b._installation_evidence(sha, config, library) != intent["installation"]:
        raise RetirementError("closed installation changed")
    if b._recovery_file_identity(b.STATE / "launcher.lock") != intent["launcher"]:
        raise RetirementError("original launcher lock changed")
    # Future deployments legitimately replace the live terminal and processes.
    # Historical proof uses the immutable intent snapshot, never today's state.
    if not historical:
        current = live_state(b, source, intent["closing_sha"], sha)
        if current != intent["live"]:
            raise RetirementError("retained production changed before rotation")
    return {
        "state": TERMINAL,
        "closure": digest(completed),
        "workspace": intent["workspace"],
    }


def context(sha):
    if (
        sys.platform != "linux"
        or os.geteuid() != 0
        or "SSH_ORIGINAL_COMMAND" in os.environ
        or not sys.flags.isolated
        or not sys.flags.no_site
        or not sys.flags.dont_write_bytecode
        or sys.executable != "/usr/bin/python3.12"
        or re.fullmatch("[a-f0-9]{40}", sha or "") is None
    ):
        raise RetirementError("isolated canonical root operator required")
    source = ROOT / "bootstrap" / sha / "source"
    entry = source / "scripts/retained_candidate_retirement.py"
    if Path(__file__).absolute() != entry:
        raise RetirementError("canonical operator required")
    for path in [
        *reversed(entry.parents),
        entry,
        entry.with_name("bootstrap_trusted_release.py"),
    ]:
        info = path.lstat()
        if (
            info.st_uid != 0
            or info.st_gid != 0
            or info.st_mode & 0o022
            or stat.S_ISLNK(info.st_mode)
            or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode))
            or stat.S_ISREG(info.st_mode)
            and info.st_nlink != 1
        ):
            raise RetirementError("unsafe canonical operator metadata")
    if os.path.lexists(entry.parent / "__pycache__"):
        raise RetirementError("cached operator code forbidden")
    os.umask(0o077)
    spec = importlib.util.spec_from_file_location(
        "retained_bootstrap", entry.with_name("bootstrap_trusted_release.py")
    )
    b = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = b
    spec.loader.exec_module(b)
    if b.canonical_source(sha) != source:
        raise RetirementError("canonical source differs")
    subprocess.run(
        [
            "/usr/bin/python3.12",
            "-I",
            "-S",
            "-B",
            str(source / "scripts/trusted_release_gate.py"),
            "--sha",
            sha,
            "--workflow-sha",
            sha,
        ],
        env=ENV,
        check=True,
        timeout=90,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return b, source


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise RetirementError("invalid operator arguments")


def main():
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--failed-sha", required=True)
    parser.add_argument("--evidence-sha256")
    args = parser.parse_args()
    if (
        re.fullmatch("[a-f0-9]{40}", args.failed_sha) is None
        or args.sha == args.failed_sha
        or args.evidence_sha256 is not None
        and re.fullmatch("[a-f0-9]{64}", args.evidence_sha256) is None
    ):
        raise RetirementError("exact distinct revisions and optional digest required")
    stage("canonical_ci")
    b, source = context(args.sha)
    stage("locks")
    b.secure(b.STATE / "launcher.lock", private=True)
    fd = os.open(b.STATE / "launcher.lock", os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        def check():
            b._assert_original_lock(b.STATE / "launcher.lock", fd)
            if os.path.lexists(b.STATE / args.failed_sha / "build.lock"):
                raise RetirementError("native claim unsupported")

        result = close_transaction(
            Adapter(b, source, args.sha, args.failed_sha, check), args.evidence_sha256
        )
        print(json.dumps(result, sort_keys=True))
    finally:
        os.close(fd)


def cli():
    stage("arguments")
    try:
        main()
        return 0
    except Exception as exc:  # noqa: BLE001 -- no exception text may cross this secret-bearing boundary.
        known = {
            "RetirementError",
            "BootstrapError",
            "ProofError",
            "TransactionError",
            "VisionError",
            "RecoveryError",
            "InstallError",
            "LaunchError",
            "OSError",
            "FileNotFoundError",
            "PermissionError",
            "ValueError",
            "KeyError",
            "TypeError",
            "AttributeError",
            "CalledProcessError",
            "TimeoutExpired",
        }
        kind = type(exc).__name__
        print(
            json.dumps(
                {
                    "state": "RETAINED_CANDIDATE_CLOSURE_BLOCKED",
                    "stage": STAGE,
                    "exception_class": kind if kind in known else "OtherError",
                    "retry_allowed": False,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
