"""Close a failed backend claim whose retained candidate is already finalized.

This isolated root operator only writes its separate closure audit. It never
finalizes a runtime transaction, edits the consumed workspace, restarts a service,
changes credentials or authorizes retry of the failed revision.
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
from pathlib import Path

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
    write_json(adapter.record / "intent.json", intent)
    if adapter.inspect() != evidence:
        raise RetirementError("closure evidence changed after intent")
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
    before = proof.running_services_snapshot()
    recovery = load(
        b,
        source / "scripts/recover_contained_services.py",
        "retained_application_probe",
    )
    recovery._application_probes(sha, closing_sha)
    recovery._http_probes()
    time.sleep(7)
    if proof.running_services_snapshot() != before:
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
        "probes": {
            "schema": True,
            "runtime_only_kb": True,
            "auth_unauthenticated_401": True,
            "health_dependencies": True,
            "runtime_flag_false": True,
        },
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
        installation = b._installation_evidence(self.sha, b.CONFIG, b.INSTALLED.parent)
        before = workspace_evidence(b, self.sha)
        live = live_state(b, self.source, self.closing_sha, self.sha)
        validate_live_snapshot(live, self.sha)
        if workspace_evidence(b, self.sha) != before:
            raise RetirementError("original workspace changed during inspection")
        self.check_locks()
        return {
            "old_sha": self.sha,
            "closing_sha": self.closing_sha,
            "workspace": before,
            "installation": installation,
            "live": live,
            "launcher": b._recovery_file_identity(b.STATE / "launcher.lock"),
        }


def validate_live_snapshot(live, sha):
    if not isinstance(live, dict) or set(live) != {
        "terminal",
        "terminal_identity",
        "services",
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
    source = b.canonical_source(intent["closing_sha"])
    validate_live_snapshot(intent["live"], sha)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
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
    b, source = context(args.sha)
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


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 -- operator boundary must suppress secret-bearing exception text.
        print(
            "RETAINED_CANDIDATE_CLOSURE_BLOCKED: preserve all evidence; no automatic retry",
            file=sys.stderr,
        )
        raise SystemExit(1)
