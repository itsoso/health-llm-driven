"""Fixed native retirement bridge after a separately finalized backend deploy.

Only bootstrap rotate can use this proof. It never creates a backend receipt.
"""

import hashlib
import importlib.util
import json
from pathlib import Path
import time
import urllib.request

NATIVE = "e19043ecb269e20f3bc0a546165e43d467f1fc8c"
ORIGINAL = "30ac1c67be7b2df79363ac7509f70f8a56ce4834"
PRODUCTION = "5c3eb6ed2c0c7f18f2a36443aee4216f5fe21670"
TERMINAL_DIGEST = "b1a0c9c6b2e2b216a98dbf4a86b7f58602458f39d32a869ed8354b3afa47b03d"
TRANSACTION = hashlib.sha256(f"{ORIGINAL}:{PRODUCTION}".encode()).hexdigest()[:32]
TERMINAL = {
    "candidate_sha": PRODUCTION, "old_sha": ORIGINAL, "phase": "COMMITTED",
    "reap_name": "runtime-state-transaction.reap-" + TRANSACTION,
    "result": "finalized", "target": "candidate", "terminal_sha": PRODUCTION,
    "transaction_id": TRANSACTION, "version": 1,
}
ROOT = Path("/var/lib/health-app/release-state")
REPO = Path("/opt/health-app")


class AdvanceError(Exception):
    """Reject anything outside the fixed, independently reviewed transition."""


def validate_saved(proof, native):
    if (native != NATIVE or not isinstance(proof, dict)
            or set(proof) != {"kind", "native_sha", "production_sha", "terminal", "identity"}
            or proof["kind"] != "finalized-native-production-advance"
            or proof["native_sha"] != NATIVE or proof["production_sha"] != PRODUCTION
            or proof["terminal"] != TERMINAL
            or type(proof["terminal"].get("version")) is not int):
        raise AdvanceError("fixed finalized native production proof required")
    identity = proof["identity"]
    if (not isinstance(identity, dict)
            or set(identity) != {"uid", "gid", "mode", "inode", "device", "sha256"}
            or any(type(identity[k]) is not int for k in ("uid", "gid", "mode", "inode", "device"))
            or identity["uid"] != 0 or identity["gid"] != 0 or identity["mode"] != 0o600
            or identity["inode"] <= 0 or identity["device"] < 0
            or identity["sha256"] != TERMINAL_DIGEST):
        raise AdvanceError("protected terminal identity differs")


def assert_no_transaction(root):
    if any(p.name.startswith(("runtime-state-transaction", ".runtime-state-transaction"))
           for p in root.iterdir()):
        raise AdvanceError("runtime transaction or cleanup remains")


def services(b):
    result = {}
    for service in ("health-backend", "celery-worker", "celery-beat"):
        raw = b._run(["/usr/bin/systemctl", "show", service,
                      "--property=ActiveState,SubState,MainPID,NRestarts,ExecMainStartTimestampMonotonic"],
                     capture=True).stdout
        values = dict(line.split("=", 1) for line in raw.splitlines())
        if (set(values) != {"ActiveState", "SubState", "MainPID", "NRestarts", "ExecMainStartTimestampMonotonic"}
                or values["ActiveState"] != "active" or values["SubState"] != "running"
                or not values["MainPID"].isdigit() or int(values["MainPID"]) <= 0
                or values["NRestarts"] != "0"
                or not values["ExecMainStartTimestampMonotonic"].isdigit()
                or int(values["ExecMainStartTimestampMonotonic"]) <= 0):
            raise AdvanceError("production services are not stable")
        result[service] = values
    return result


def inspect(b, source, native, production):
    if native != NATIVE or production != PRODUCTION:
        raise AdvanceError("only the fixed finalized production advance is supported")
    closure = b._read_json(b.STATE / "native-only-closures" / native / "intent.json")
    if closure["production_sha"] != ORIGINAL:
        raise AdvanceError("native closure original production differs")
    b._assert_idle()
    b._recovery_process_proof()
    b.secure(ROOT)
    assert_no_transaction(ROOT)
    path = ROOT / "runtime-state-terminal.json"
    before = b._recovery_file_identity(path)
    raw = path.read_bytes()
    if len(raw) > 4096 or hashlib.sha256(raw).hexdigest() != TERMINAL_DIGEST:
        raise AdvanceError("fixed terminal bytes differ")
    proof = {"kind": "finalized-native-production-advance", "native_sha": native,
             "production_sha": production, "terminal": json.loads(raw), "identity": before}
    validate_saved(proof, native)
    b._recovery_production_proof(production, source)
    git = ["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false"]
    b._run(git + ["-C", str(REPO), "merge-base", "--is-ancestor", ORIGINAL, production])
    # Read raw commit headers: shallow staging still preserves the real parent.
    commit = b._run(git + ["-C", str(source), "cat-file", "commit", "HEAD"], capture=True).stdout
    parents = [line[7:] for line in commit.split("\n\n", 1)[0].splitlines() if line.startswith("parent ")]
    if parents != [production]:
        raise AdvanceError("recovery publisher must directly follow the fixed production revision")
    gate_path = source / "scripts/trusted_release_gate.py"
    b.secure(gate_path)
    spec = importlib.util.spec_from_file_location("advance_ci_gate", gate_path)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    gate._latest(gate._get_json, production)
    first = services(b)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open("http://127.0.0.1:8000/api/v1/health", timeout=10) as response:
        if response.geturl() != "http://127.0.0.1:8000/api/v1/health" or response.status != 200:
            raise AdvanceError("production health endpoint differs")
        health = json.loads(response.read(4097))
    if health != {"status": "healthy", "services": {"api": "running", "database": "connected",
                                                    "redis": "connected", "celery": "connected"}}:
        raise AdvanceError("production dependencies are not healthy")
    time.sleep(6)
    if services(b) != first:
        raise AdvanceError("production service identity changed")
    b._recovery_production_proof(production, source)
    assert_no_transaction(ROOT)
    b._assert_idle()
    b._recovery_process_proof()
    if b._recovery_file_identity(path) != before:
        raise AdvanceError("terminal evidence changed")
    return proof
