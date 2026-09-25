"""Root-installed one-shot SSH commands, each bound to the caller's expected SHA.

Provisioning is deliberately separate: no installation, key issuance, policy
editing, retry, lease cleanup, or recovery is available to the caller.
"""

import datetime
import fcntl
import grp
import hashlib
import json
import os
import re
import secrets
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CONFIG = Path("/etc/reva-release")
POLICY = CONFIG / "authorized-release.json"
STATE = Path("/var/lib/reva-release")
PRODUCTION = Path("/opt/health-app")
BUSINESS_LEASE = Path("/var/lock/health-app-release")
ORIGIN = "https://github.com/itsoso/health-llm-driven.git"
PYTHON = "/usr/bin/python3.12"
DEPLOY_TIMEOUT_SECONDS = 3600
RECOVERY_MARGIN_SECONDS = 3600
PREPARATION_TIMEOUT_SECONDS = 90
PREPARATION_GROUP_EXIT_GRACE_SECONDS = 2


class LaunchError(Exception):
    """A sanitized rejection; callers must never receive deployment logs."""


class PreparationUncertain(LaunchError):
    """Preparation process termination cannot be used as retirement evidence."""


def parse_command(command):
    match = re.fullmatch(r"(run|status|check|claim-build|claim-testflight|check-testflight|claim-testflight-build|claim-testflight-upload) ([0-9a-f]{40})", command)
    if match is None:
        raise LaunchError("only fixed release commands with an exact SHA are allowed")
    return match.group(1), match.group(2)


def authorize_command(command, policy):
    action, expected_sha = parse_command(command)
    if expected_sha != policy["sha"]:
        raise LaunchError("caller SHA does not match server authorization")
    return action


def validate_policy(data, *, now):
    if (
        not isinstance(data, dict)
        or set(data) != {"sha", "expires_at", "executor_sha256"}
        or not isinstance(data["sha"], str)
        or re.fullmatch(r"[0-9a-f]{40}", data["sha"]) is None
        or type(data["expires_at"]) is not int
        or data["expires_at"] <= now
        or not isinstance(data["executor_sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", data["executor_sha256"]) is None
    ):
        raise LaunchError("invalid or expired release authorization")
    return data


def _assert_deployment_window(policy):
    now = time.time()
    validate_policy(policy, now=now)
    if policy["expires_at"] - now < DEPLOY_TIMEOUT_SECONDS + RECOVERY_MARGIN_SECONDS:
        raise LaunchError("authorization lifetime is insufficient for deployment and recovery")


def validate_metadata(metadata, *, private=False, directory=False, single_link=True):
    valid_type = stat.S_ISDIR if directory else stat.S_ISREG
    if (
        metadata.st_uid != 0 or not valid_type(metadata.st_mode)
        or metadata.st_mode & 0o022
        or (not directory and single_link and metadata.st_nlink != 1)
        or (private and stat.S_IMODE(metadata.st_mode) != 0o600)
    ):
        raise LaunchError("unsafe ownership, type, permissions, or link count")


def secure_path(path, *, private=False, directory=False):
    path = Path(path)
    if not path.is_absolute():
        raise LaunchError("absolute server path required")
    for parent in reversed(path.parents):
        validate_metadata(parent.lstat(), directory=True)
    validate_metadata(path.lstat(), private=private, directory=directory)


def validate_object_cache(objects):
    """Prove Git cannot escape the fixed root-controlled object store."""
    objects = Path(objects)
    secure_path(objects, directory=True)
    for name in ("alternates", "http-alternates"):
        if os.path.lexists(objects / "info" / name):
            raise LaunchError("production object cache must not chain alternates")
    for root, directories, files in os.walk(objects, followlinks=False):
        root = Path(root)
        validate_metadata(root.lstat(), directory=True)
        for name in directories:
            validate_metadata((root / name).lstat(), directory=True)
        for name in files:
            # Root-owned, non-writable hard-linked Git objects are immutable to
            # unprivileged callers just like single-linked objects.
            validate_metadata((root / name).lstat(), single_link=False)


def _read_private(path):
    secure_path(path, private=True)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        validate_metadata(os.fstat(stream.fileno()), private=True)
        raw = stream.read(1_000_001)
    if len(raw) > 1_000_000:
        raise LaunchError("server configuration exceeds bound")
    return raw


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise LaunchError("duplicate configuration field")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def validate_production_env_metadata(metadata, group_id):
    validate_metadata(metadata)
    if stat.S_IMODE(metadata.st_mode) != 0o640 or metadata.st_gid != group_id:
        raise LaunchError("production env must retain root:health-app 0640 contract")


def read_production_env():
    path = Path("/opt/health-app/backend/.env")
    secure_path(path)
    group_id = grp.getgrnam("health-app").gr_gid
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        validate_production_env_metadata(os.fstat(stream.fileno()), group_id)
        raw = stream.read(1_000_001)
    if len(raw) > 1_000_000:
        raise LaunchError("production env exceeds bound")
    return raw.decode()


def _write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(Path(path).parent)


def _sync_directory(path):
    parent_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def read_status(sha, workspace):
    workspace = Path(workspace)
    complete = workspace / "completed.json"
    started = workspace / "started.json"
    if complete.exists():
        secure_path(complete, private=True)
        data = _json(complete.read_bytes())
        if data not in tuple({"sha": sha, "state": state} for state in ("SUCCEEDED", "NEEDS_OPERATOR", "PREPARATION_FAILED")):
            raise LaunchError("invalid terminal release state")
        return data
    if started.exists():
        secure_path(started, private=True)
        if _json(started.read_bytes()) != {"sha": sha, "state": "STARTED"}:
            raise LaunchError("invalid started release state")
        return {"sha": sha, "state": "STARTED"}
    return {"sha": sha, "state": "READY"}


def run_once(policy, workspace, prepare, deploy):
    """Durable consumption precedes any preparation or deployment side effect."""
    workspace = Path(workspace)
    secure_path(workspace, directory=True)
    lock = workspace.parent / "launcher.lock"
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        secure_path(lock, private=True)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LaunchError("another release invocation is active") from None
        assert_frontend_rebuild_history()
        if os.path.lexists(workspace / "testflight-base.json"):
            raise LaunchError("native-only continuation cannot deploy backend")
        if read_status(policy["sha"], workspace)["state"] != "READY":
            raise LaunchError("authorization already consumed; manual review required")
        _assert_deployment_window(policy)
        _write_private(workspace / "started.json", json.dumps({"sha": policy["sha"], "state": "STARTED"}).encode())
        # The marker fsync covers the new workspace's contents, not the entry
        # that links this newly created directory into STATE. Persist both
        # before any source preparation or external release operation begins.
        _sync_directory(workspace.parent)
        preparing = False
        try:
            _write_private(workspace / "preparation-started.json", json.dumps({
                "sha": policy["sha"], "state": "PREPARING", "executor_sha256": policy["executor_sha256"],
            }).encode())
            preparing = True
            prepare()
            preparing = False
            _write_private(workspace / "prepared.json", json.dumps({"sha": policy["sha"], "state": "PREPARED"}).encode())
            _assert_deployment_window(policy)
            # This durable intent is a prerequisite to every business side effect.
            _write_private(workspace / "deployment-started.json", json.dumps({"sha": policy["sha"], "state": "DEPLOYING"}).encode())
            deploy()
        except Exception as error:  # noqa: BLE001 -- Persist failures before sanitizing at the boundary.
            state = "PREPARATION_FAILED" if preparing and not isinstance(error, PreparationUncertain) else "NEEDS_OPERATOR"
            _write_private(workspace / "completed.json", json.dumps({"sha": policy["sha"], "state": state}).encode())
            raise LaunchError("release failed; evidence retained, retry forbidden") from None
        # BaseException / process death intentionally leaves STARTED, never READY.
        result = {"sha": policy["sha"], "state": "SUCCEEDED"}
        _write_private(workspace / "completed.json", json.dumps(result).encode())
        return result
    finally:
        os.close(fd)


FRONTEND_NPM_CONFIG_FAILURE = (b'Exit prior to config file resolving\ncause\n'
                               b'double-loading config "/dev/null" as "global", previously loaded as "user"\n')
# Complete reviewed pre-install control flow, not an operation/release SHA allowlist.
FRONTEND_PREINSTALL_CODE_SHA256 = "67583cf9135359022d1bc513374d0eb26aed0305d7b9a8731f17473ed3c87182"


def frontend_preinstall_failure(operation):
    expected = {"intent.json", "before.json", "build.log", "failed.json"}
    secure_path(operation, directory=True)
    if {p.name for p in operation.iterdir()} != expected:
        raise LaunchError("not a bounded pre-install frontend failure")
    raw = {name: _read_private(operation / name) for name in expected}
    intent = _json(raw["intent.json"])
    keys = {"kind", "publisher_sha", "production_sha", "operation_id", "frontend_tree", "state", "artifact_digest"}
    if (not isinstance(intent, dict) or set(intent) != keys or intent["kind"] != "frontend-rebuild"
            or intent["operation_id"] != operation.name or intent["state"] != "FRONTEND_STARTED"
            or intent["artifact_digest"] is not None
            or any(not isinstance(intent[key], str) or re.fullmatch(r"[0-9a-f]{40}", intent[key]) is None
                   for key in ("publisher_sha", "production_sha", "frontend_tree"))
            or _json(raw["failed.json"]) != {**intent, "state": "FRONTEND_NEEDS_OPERATOR"}
            or raw["build.log"] != FRONTEND_NPM_CONFIG_FAILURE):
        raise LaunchError("unknown frontend failure phase")
    before = _json(raw["before.json"])
    if not isinstance(before, dict) or any(before.get(key) != intent[key] for key in (
            "publisher_sha", "production_sha", "operation_id", "frontend_tree")):
        raise LaunchError("failed frontend binding differs")
    return {name: hashlib.sha256(data).hexdigest() for name, data in raw.items()}


def frontend_closure_proof(operation, state, *, acknowledgment=True):
    """Historical proof deliberately does not depend on future live SHA/PIDs."""
    failure = frontend_preinstall_failure(operation)
    closure = Path(state) / "frontend-rebuild-closures" / operation.name
    secure_path(closure, directory=True)
    expected = {"intent.json", "completed.json", "lease"}
    if acknowledgment:
        expected.add("acknowledged.json")
    if stat.S_IMODE(closure.stat().st_mode) != 0o700 or {p.name for p in closure.iterdir()} != expected:
        raise LaunchError("frontend retirement incomplete")
    intent = _json(_read_private(closure / "intent.json"))
    keys = {"kind", "state", "publisher_sha", "production_sha", "operation_id", "old_publisher_sha",
            "old_code_sha256", "failure", "lease", "snapshot", "frontend_runtime", "build_digest",
            "launcher", "unit", "evidence_sha256", "receipt_sha256"}
    old = _json(_read_private(operation / "intent.json"))
    if (not isinstance(intent, dict) or set(intent) != keys
            or intent["kind"] != "frontend-preinstall-closure" or intent["state"] != "CLOSING"
            or intent["operation_id"] != operation.name or intent["failure"] != failure
            or intent["old_publisher_sha"] != old["publisher_sha"]
            or intent["production_sha"] != old["production_sha"]
            or intent["old_code_sha256"] != FRONTEND_PREINSTALL_CODE_SHA256
            or any(not isinstance(intent[key], str) or re.fullmatch(r"[0-9a-f]{64}", intent[key]) is None
                   for key in ("evidence_sha256", "receipt_sha256"))
            or not isinstance(intent["publisher_sha"], str)
            or re.fullmatch(r"[0-9a-f]{40}", intent["publisher_sha"]) is None):
        raise LaunchError("frontend retirement binding differs")
    evidence = {k: v for k, v in intent.items() if k not in ("evidence_sha256", "receipt_sha256")}
    digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if digest(evidence) != intent["evidence_sha256"]:
        raise LaunchError("frontend closure evidence differs")
    archive = closure / "lease"
    secure_path(archive, directory=True)
    names = {"token", "label", "stage", "started_at"}
    if stat.S_IMODE(archive.stat().st_mode) != 0o700 or {p.name for p in archive.iterdir()} != names:
        raise LaunchError("invalid durable lease archive")
    if not isinstance(intent["lease"], dict) or set(intent["lease"]) != {"directory", "files"} or set(intent["lease"]["files"]) != names:
        raise LaunchError("invalid lease evidence")
    for name in names:
        if hashlib.sha256(_read_private(archive / name)).hexdigest() != intent["lease"]["files"][name]["sha256"]:
            raise LaunchError("archived lease changed")
    if (_read_private(archive / "label") != b"frontend-rebuild\n"
            or _read_private(archive / "stage") != (str(operation) + "\n").encode()
            or re.fullmatch(rb"[0-9a-f]{64}\n", _read_private(archive / "token")) is None
            or re.fullmatch(rb"[0-9]{1,12}\n", _read_private(archive / "started_at")) is None):
        raise LaunchError("archived lease binding differs")
    completed = {"state": "CLOSED_PREINSTALL_FRONTEND_FAILURE", "operation_id": operation.name,
                 "intent_sha256": digest(intent)}
    if _json(_read_private(closure / "completed.json")) != completed:
        raise LaunchError("frontend retirement terminal differs")
    if acknowledgment:
        ack = _json(_read_private(closure / "acknowledged.json"))
        if (not isinstance(ack, dict) or set(ack) != {"operation_id", "receipt"}
                or ack["operation_id"] != operation.name or not isinstance(ack["receipt"], str)
                or re.fullmatch(r"[0-9a-f]{64}", ack["receipt"]) is None
                or hashlib.sha256(ack["receipt"].encode()).hexdigest() != intent["receipt_sha256"]):
            raise LaunchError("durably issued frontend closure receipt required")
    return intent


def assert_frontend_rebuild_history(state=None, *, pending_operation=None):
    """Independent frontend evidence must never count as backend success."""
    root = Path(state or STATE) / "frontend-rebuilds"
    closures = root.parent / "frontend-rebuild-closures"
    if os.path.lexists(closures):
        secure_path(closures, directory=True)
        if stat.S_IMODE(closures.stat().st_mode) != 0o700:
            raise LaunchError("frontend closure root must remain private")
        for closure in closures.iterdir():
            if re.fullmatch(r"[0-9a-f]{32}", closure.name) is None or not (root / closure.name).is_dir():
                raise LaunchError("orphan frontend closure")
    if not os.path.lexists(root):
        return
    secure_path(root, directory=True)
    if stat.S_IMODE(root.lstat().st_mode) != 0o700:
        raise LaunchError("frontend audit root must remain private")
    expected_files = {"intent.json", "before.json", "build.log", "install-started.json",
                      "verified.json", "completed.json", "previous-next", "previous-node-modules"}
    for operation in root.iterdir():
        secure_path(operation, directory=True)
        if stat.S_IMODE(operation.lstat().st_mode) != 0o700:
            raise LaunchError("frontend operation must remain private")
        if re.fullmatch(r"[0-9a-f]{32}", operation.name) is None:
            raise LaunchError("invalid frontend operation")
        if operation.name == pending_operation:
            # Only the root operator uses this to inspect the one failure being
            # retired. RPC/normal launch/rotation callers never pass an exception.
            frontend_preinstall_failure(operation)
            continue
        if os.path.lexists(operation / "failed.json"):
            frontend_closure_proof(operation, root.parent)
            continue
        if os.path.lexists(closures / operation.name) or {p.name for p in operation.iterdir()} != expected_files:
            raise LaunchError("unfinished or unknown frontend rebuild; operator review required")
        for name in ("previous-next", "previous-node-modules"):
            secure_path(operation / name, directory=True)
        secure_path(operation / "build.log", private=True)
        intent = _json(_read_private(operation / "intent.json"))
        keys = {"kind", "publisher_sha", "production_sha", "operation_id", "frontend_tree", "state", "artifact_digest"}
        if (not isinstance(intent, dict) or set(intent) != keys or intent["kind"] != "frontend-rebuild"
                or intent["operation_id"] != operation.name or intent["state"] != "FRONTEND_STARTED"
                or intent["artifact_digest"] is not None
                or any(not isinstance(intent[key], str) or re.fullmatch(r"[0-9a-f]{40}", intent[key]) is None
                       for key in ("publisher_sha", "production_sha", "frontend_tree"))):
            raise LaunchError("invalid frontend rebuild binding")
        complete = _json(_read_private(operation / "completed.json"))
        if (not isinstance(complete, dict) or set(complete) != keys
                or not isinstance(complete["artifact_digest"], str)
                or re.fullmatch(r"[0-9a-f]{64}", complete["artifact_digest"]) is None):
            raise LaunchError("invalid frontend completion proof")
        for name, status in (("install-started.json", "FRONTEND_INSTALLING"),
                             ("verified.json", "FRONTEND_VERIFIED"), ("completed.json", "FRONTEND_SUCCEEDED")):
            expected = {**intent, "state": status, "artifact_digest": complete["artifact_digest"]}
            if _json(_read_private(operation / name)) != expected:
                raise LaunchError("frontend completion differs from its intent")
        before = _json(_read_private(operation / "before.json"))
        if not isinstance(before, dict) or any(before.get(key) != intent[key] for key in (
                "publisher_sha", "production_sha", "operation_id", "frontend_tree")):
            raise LaunchError("frontend preflight binding differs")


def _native_started(sha, workspace):
    marker = Path(workspace) / "native-started.json"
    if not marker.exists():
        return False
    secure_path(marker, private=True)
    if _json(marker.read_bytes()) != {"sha": sha, "state": "STARTED"}:
        raise LaunchError("invalid native release state")
    return True


def release_status(sha, workspace):
    return {
        "sha": sha,
        "backend": read_status(sha, workspace)["state"],
        "testflight": "STARTED" if _native_started(sha, workspace) else "UNCLAIMED",
    }


def check_readiness(policy):
    """Read-only target probes before consuming any build/deployment claim."""
    assert_frontend_rebuild_history()
    _assert_deployment_window(policy)
    validate_loopback(policy)
    secure_path(Path(PYTHON))
    env = clean_environment(STATE)
    # No configured HOME or helper binaries are consulted by these fixed tools.
    env.update(PATH="/usr/bin:/bin", HOME="/nonexistent")
    git = ["/usr/bin/git", "-c", "core.hooksPath=/dev/null",
           "-c", "http.followRedirects=false", "-c", "http.version=HTTP/1.1",
           "-c", "http.lowSpeedLimit=1024", "-c", "http.lowSpeedTime=30",
           "ls-remote", ORIGIN, "refs/heads/main"]
    result = subprocess.run(git, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, check=True, timeout=90)
    if result.stdout.strip() != f"{policy['sha']}\trefs/heads/main":
        raise LaunchError("remote main differs from authorized release")
    subprocess.run(["/usr/bin/ssh", "-F", str(CONFIG / "loopback.conf"),
                    "health", "/usr/bin/true"], env=env, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=True, timeout=30)
    _assert_deployment_window(policy)


def _native_binding(workspace, proof, *, create=False):
    binding = workspace / "testflight-base.json"
    if os.path.lexists(binding):
        if proof is None or _json(_read_private(binding)) != proof:
            raise LaunchError("native-only binding requires matching guarded native RPC")
    elif proof is not None:
        if not create or any(os.path.lexists(workspace / name) for name in ("build-started.json", "native-started.json")):
            raise LaunchError("native-only binding missing or legacy claim exists")
        _write_private(binding, json.dumps(proof, sort_keys=True).encode())


def claim_build(policy, workspace, *, native_proof=None):
    """Reserve build only; upload retains its own one-shot claim.

    A separate short lock permits claiming while deployment owns launcher.lock.
    This RPC runs in the build job itself, including every single-job rerun.
    A lost response is consumed and cannot authorize a second vendor build.
    """
    workspace = Path(workspace)
    secure_path(workspace, directory=True)
    lock = workspace / "build.lock"
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        secure_path(lock, private=True)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LaunchError("another release invocation is active") from None
        if native_proof is None:
            _native_binding(workspace, None)
        if read_status(policy["sha"], workspace)["state"] in {"NEEDS_OPERATOR", "PREPARATION_FAILED"}:
            raise LaunchError("failed backend requires operator review before build")
        marker = workspace / "build-started.json"
        if os.path.lexists(marker):
            raise LaunchError("build authorization already consumed; operator review required")
        check_readiness(policy)
        _assert_deployment_window(policy)
        _native_binding(workspace, native_proof, create=True)
        _write_private(marker, json.dumps({"sha": policy["sha"], "state": "STARTED"}).encode())
        _sync_directory(workspace.parent)
        return {"sha": policy["sha"], "state": "CLAIMED"}
    finally:
        os.close(fd)


def claim_testflight(policy, workspace, *, native_proof=None):
    """Consume upload permission independently of a running backend deployment.

    A lost response is still a consumed claim. Only an operator may investigate
    the existing EAS build; this interface cannot clear or retry the claim.
    The workflow validates the exact finished build and joins both outcomes;
    claiming/uploading never proves backend health or App Review readiness.
    """
    workspace = Path(workspace)
    secure_path(workspace, directory=True)
    # Share the short vendor lock with build and credential retirement, not the
    # long-held deployment lock. No new lock inventory or lock-order inversion.
    lock = workspace / "build.lock"
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        secure_path(lock, private=True)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LaunchError("another release invocation is active") from None
        _native_binding(workspace, native_proof)
        assert_frontend_rebuild_history()
        _assert_deployment_window(policy)
        if read_status(policy["sha"], workspace)["state"] in {"NEEDS_OPERATOR", "PREPARATION_FAILED"}:
            raise LaunchError("failed backend requires operator review before upload")
        marker = workspace / "build-started.json"
        if not os.path.lexists(marker) or _json(_read_private(marker)) != {"sha": policy["sha"], "state": "STARTED"}:
            raise LaunchError("exact build claim required before upload")
        if _native_started(policy["sha"], workspace):
            raise LaunchError("native authorization already consumed; operator review required")
        # A session can authenticate before revoke obtains this same lock.
        # Recheck current local authorization under lock, without network I/O.
        validate_loopback(policy)
        _write_private(workspace / "native-started.json", json.dumps({"sha": policy["sha"], "state": "STARTED"}).encode())
        _sync_directory(workspace.parent)
        return {"sha": policy["sha"], "state": "CLAIMED"}
    finally:
        os.close(fd)


def testflight_backend_proof(policy, *, lease):
    """Run only the exact canonical, root-controlled read-only helper."""
    source = STATE / "bootstrap" / policy["sha"] / "source"
    script = source / "scripts/trusted_testflight_preflight.py"
    secure_path(script)
    secure_path(source / ".git/config")
    env = clean_environment(STATE)
    env.update(PATH="/usr/bin:/bin", HOME="/nonexistent", GIT_NO_REPLACE_OBJECTS="1",
               GIT_CONFIG_SYSTEM="/dev/null")
    expected = subprocess.run([
        "/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
        "-C", str(source), "show", policy["sha"] + ":scripts/trusted_testflight_preflight.py",
    ], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=True, timeout=30).stdout
    if script.read_bytes() != expected:
        raise LaunchError("native proof helper differs from reviewed source")
    result = subprocess.run([PYTHON, "-I", "-S", "-B", str(script), "--sha", policy["sha"]],
                            env=env, input=json.dumps(lease).encode(), stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, check=True, timeout=600)
    proof = _json(result.stdout)
    if (not isinstance(proof, dict) or set(proof) != {"sha", "production_sha", "state"}
            or proof["sha"] != policy["sha"] or proof["state"] != "COMPATIBLE"
            or not isinstance(proof["production_sha"], str)
            or re.fullmatch(r"[0-9a-f]{40}", proof["production_sha"]) is None):
        raise LaunchError("invalid native backend proof")
    return proof


def _testflight_lease_parent():
    # Match the existing Ubuntu business-lease protocol, including only its
    # fixed root-owned sticky parent exception. Never relax code/key paths.
    if BUSINESS_LEASE == Path("/var/lock/health-app-release"):
        for parent in (Path("/"), Path("/var"), Path("/run")):
            validate_metadata(parent.lstat(), directory=True)
        alias = Path("/var/lock")
        info = alias.lstat()
        if (not stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_gid != 0
                or info.st_nlink != 1 or os.readlink(alias) != "/run/lock"):
            raise LaunchError("fixed business lease alias differs")
        shared = Path("/run/lock").lstat()
        if (not stat.S_ISDIR(shared.st_mode) or shared.st_uid != 0 or shared.st_gid != 0
                or stat.S_IMODE(shared.st_mode) != 0o1777):
            raise LaunchError("fixed business lease parent differs")
    else:
        # Internal unit-test path injection only; production constant is fixed.
        secure_path(BUSINESS_LEASE.parent, directory=True)


def _assert_testflight_lease(lease, workspace):
    _testflight_lease_parent()
    if (not isinstance(lease, dict) or set(lease) != {"token", "started_at", "identity"}
            or not isinstance(lease["token"], str) or re.fullmatch(r"[0-9a-f]{64}", lease["token"]) is None
            or not isinstance(lease["started_at"], str) or re.fullmatch(r"[0-9]{1,12}", lease["started_at"]) is None):
        raise LaunchError("invalid native lease identity")
    info = BUSINESS_LEASE.lstat()
    validate_metadata(info, directory=True)
    if stat.S_IMODE(info.st_mode) != 0o700:
        raise LaunchError("native business lease must remain private")
    expected = {"token": lease["token"], "label": "testflight-check",
                "stage": str(workspace), "started_at": lease["started_at"]}
    if {p.name for p in BUSINESS_LEASE.iterdir()} != set(expected):
        raise LaunchError("native business lease inventory changed")
    identity = [info.st_dev, info.st_ino]
    for name, value in expected.items():
        fd = os.open(BUSINESS_LEASE / name, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            validate_metadata(metadata, private=True)
            if stream.read(4097) != (value + "\n").encode():
                raise LaunchError("native business lease ownership changed")
            if name == "token":
                identity.extend((metadata.st_dev, metadata.st_ino))
    if lease["identity"] != identity:
        raise LaunchError("native business lease inode changed")


def _acquire_testflight_lease(workspace):
    _testflight_lease_parent()
    try:
        BUSINESS_LEASE.mkdir(mode=0o700)
    except FileExistsError:
        raise LaunchError("business release in progress") from None
    # An interrupted/partial initialization is left closed for operator review.
    lease = {"token": secrets.token_hex(32), "started_at": str(int(time.time()))}
    for name, value in {"token": lease["token"], "label": "testflight-check",
                        "stage": str(workspace), "started_at": lease["started_at"]}.items():
        _write_private(BUSINESS_LEASE / name, (value + "\n").encode())
    lease["identity"] = [value for path in (BUSINESS_LEASE, BUSINESS_LEASE / "token")
                         for value in (path.lstat().st_dev, path.lstat().st_ino)]
    _assert_testflight_lease(lease, workspace)
    return lease


def _release_testflight_lease(lease, workspace):
    _assert_testflight_lease(lease, workspace)
    for name in ("token", "label", "stage", "started_at"):
        (BUSINESS_LEASE / name).unlink()
    BUSINESS_LEASE.rmdir()


def testflight_only(policy, workspace, action):
    """Guard native-only claims without consuming or forging backend success."""
    if action not in {"check", "build", "upload"}:
        raise LaunchError("unknown native action")
    workspace = Path(workspace)
    lock = STATE / "launcher.lock"
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    lease = None
    try:
        secure_path(lock, private=True)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LaunchError("another release invocation is active") from None
        _assert_deployment_window(policy)
        if os.path.lexists(BUSINESS_LEASE):
            raise LaunchError("business release in progress")
        if read_status(policy["sha"], workspace)["state"] != "READY":
            raise LaunchError("native-only candidate already has backend state")
        check_readiness(policy)
        lease = _acquire_testflight_lease(workspace)
        proof = testflight_backend_proof(policy, lease=lease)
        _assert_testflight_lease(lease, workspace)
        binding = workspace / "testflight-base.json"
        if os.path.lexists(binding):
            if _json(_read_private(binding)) != proof:
                raise LaunchError("native-only production binding changed")
        elif any(os.path.lexists(workspace / name) for name in ("build-started.json", "native-started.json")):
            raise LaunchError("existing legacy native claim cannot be rebound")
        _assert_deployment_window(policy)
        if action == "check":
            return {"sha": policy["sha"], "state": "CHECKED"}
        if action == "build":
            return claim_build(policy, workspace, native_proof=proof)
        if not os.path.lexists(binding):
            raise LaunchError("native-only build binding required")
        return claim_testflight(policy, workspace, native_proof=proof)
    finally:
        try:
            if lease is not None:
                _release_testflight_lease(lease, workspace)
        finally:
            os.close(fd)


def clean_environment(workspace):
    return {
        "PATH": str(Path(workspace) / "bin") + ":/usr/bin:/bin",
        "HOME": str(Path(workspace) / "home"),
        "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
        # Literal command-scope entries reach deploy.sh's own Git subprocesses;
        # no caller config keys, values, count, or URL rewrites are inherited.
        "GIT_CONFIG_COUNT": "3",
        "GIT_CONFIG_KEY_0": "http.version", "GIT_CONFIG_VALUE_0": "HTTP/1.1",
        "GIT_CONFIG_KEY_1": "http.lowSpeedLimit", "GIT_CONFIG_VALUE_1": "1024",
        "GIT_CONFIG_KEY_2": "http.lowSpeedTime", "GIT_CONFIG_VALUE_2": "30",
        "GIT_TERMINAL_PROMPT": "0",
    }


def execute(args, cwd, env, log):
    # No shell, inherited environment, caller-selected executable or log output.
    with open(log, "ab", buffering=0) as output:
        os.chmod(log, 0o600)
        subprocess.run(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                       stdout=output, stderr=subprocess.STDOUT, check=True,
                       timeout=DEPLOY_TIMEOUT_SECONDS, start_new_session=True)


def execute_preparation(args, cwd, env, log):
    """Bound fixed Git commands; uncertain process groups never permit retirement."""
    with open(log, "ab", buffering=0) as output:
        os.chmod(log, 0o600)
        process = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        group_exited = False
        try:
            code = process.wait(timeout=PREPARATION_TIMEOUT_SECONDS)
            deadline = time.monotonic() + PREPARATION_GROUP_EXIT_GRACE_SECONDS
            while True:
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    group_exited = True
                    break
                except OSError:
                    raise PreparationUncertain("preparation group inspection failed") from None
                # A successful fixed Git command can outlive its leader briefly
                # while the transport helper closes. The command is not complete
                # until the entire owned process group exits. Failed commands
                # receive no grace.
                if code or time.monotonic() >= deadline:
                    break
                time.sleep(0.05)
        except BaseException:  # noqa: BLE001 -- Cancel the owned group even during grace inspection.
            try:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    # The group exited between timeout delivery and cancellation.
                    process.poll()
                process.wait(timeout=5)
            finally:
                raise PreparationUncertain("preparation interrupted; operator review required") from None
        if group_exited:
            if code:
                raise subprocess.CalledProcessError(code, args) from None
            return
        try:
            os.killpg(process.pid, signal.SIGKILL)
        finally:
            raise PreparationUncertain("preparation descendants remained; operator review required") from None


def prepare_source(policy, workspace):
    workspace = Path(workspace)
    env = clean_environment(workspace)
    (workspace / "home").mkdir(mode=0o700)
    source = workspace / "source"
    log = workspace / "preparation.log"
    git = [
        "/usr/bin/git", "-c", "core.hooksPath=/dev/null",
        "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never",
        "-c", "http.followRedirects=false", "-c", "http.version=HTTP/1.1",
        "-c", "http.lowSpeedLimit=1024", "-c", "http.lowSpeedTime=30",
    ]
    for path in (PRODUCTION, PRODUCTION / ".git"):
        secure_path(path, directory=True)
    validate_object_cache(PRODUCTION / ".git/objects")
    baseline = subprocess.run(
        ["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-C", str(PRODUCTION), "rev-parse", "HEAD"],
        env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, check=True, timeout=10,
    ).stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", baseline) is None or baseline == policy["sha"]:
        raise LaunchError("production object-cache revision is invalid")
    for attempt in range(3):
        _assert_deployment_window(policy)
        try:
            # Seed refs from the root-owned production repository, then fetch a
            # bounded main window from the fixed GitHub origin. The source keeps
            # an explicit read-only alternate and exports only the candidate
            # range above the verified production revision.
            local_git = ["/usr/bin/git", "-c", "core.hooksPath=/dev/null",
                         "-c", "protocol.file.allow=always"]
            execute_preparation(local_git + ["clone", "--shared", "--no-checkout",
                                str(PRODUCTION), str(source)], workspace, env, log)
            execute_preparation(git + ["-C", str(source), "remote", "set-url", "origin", ORIGIN],
                                workspace, env, log)
            execute_preparation(git + ["-C", str(source), "fetch", "--depth=64", "--no-tags",
                                "origin", "main"], workspace, env, log)
            break
        except subprocess.CalledProcessError as error:
            if error.returncode != 128 or attempt == 2:
                raise
            # Only a completed Git clone may retry; preserve partial evidence.
            if os.path.lexists(source):
                secure_path(source, directory=True)
                archive = workspace / "clone-attempts"
                archive.mkdir(mode=0o700, exist_ok=True)
                secure_path(archive, directory=True)
                destination = archive / str(attempt + 1)
                if os.path.lexists(destination):
                    raise LaunchError("existing clone attempt evidence must not be replaced") from None
                source.rename(destination)
                _sync_directory(archive)
                _sync_directory(workspace)
            time.sleep(2 ** attempt)
    fetched = subprocess.run(
        ["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-C", str(source),
         "rev-parse", "FETCH_HEAD"],
        env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, check=True, timeout=10,
    ).stdout.strip()
    if fetched != policy["sha"]:
        raise LaunchError("GitHub main differs from authorized release")
    ancestry = subprocess.run(
        ["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-C", str(source),
         "merge-base", "--is-ancestor", baseline, policy["sha"]],
        env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=False, timeout=10,
    )
    if ancestry.returncode != 0:
        raise LaunchError("bounded history does not include production revision")
    execute_preparation(git + ["-C", str(source), "checkout", "-B", "main", policy["sha"]], workspace, env, log)
    execute_preparation(git + ["-C", str(source), "update-ref", "refs/reva-production", baseline],
                        workspace, env, log)
    alternate = source / ".git/objects/info/alternates"
    secure_path(alternate)
    if alternate.read_text() != str(PRODUCTION / ".git/objects") + "\n":
        raise LaunchError("production object-cache binding is invalid")
    checked_out = subprocess.run(
        ["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-C", str(source), "rev-parse", "HEAD"],
        env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, check=True, timeout=10,
    ).stdout.strip()
    if checked_out != policy["sha"]:
        raise LaunchError("prepared source differs from authorized release")
    # Prove the exact incremental artifact is closed over only the verified
    # production object store. An ancestry check alone misses shallow merge
    # boundaries whose side-parent history falls outside the fetched window.
    with tempfile.TemporaryDirectory(dir=workspace, prefix="bundle-proof-") as proof_root:
        proof_root = Path(proof_root)
        bundle = proof_root / "candidate.bundle"
        proof = proof_root / "receiver.git"
        proof_git = ["/usr/bin/git", "-c", "core.hooksPath=/dev/null",
                     "-c", "protocol.file.allow=always", "-c", "protocol.ext.allow=never"]
        execute_preparation(proof_git + ["-C", str(source), "bundle", "create", str(bundle),
                            "HEAD", "^" + baseline], workspace, env, log)
        execute_preparation(proof_git + ["init", "--bare", str(proof)], workspace, env, log)
        proof_alternate = proof / "objects/info/alternates"
        with proof_alternate.open("x") as stream:
            stream.write(str(PRODUCTION / ".git/objects") + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        execute_preparation(proof_git + ["--git-dir=" + str(proof), "fetch", "--no-tags",
                            str(bundle), "HEAD"], workspace, env, log)
        execute_preparation(proof_git + ["--git-dir=" + str(proof), "fsck", "--connectivity-only",
                            policy["sha"]], workspace, env, log)
        imported = subprocess.run(
            ["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "--git-dir=" + str(proof),
             "rev-parse", "FETCH_HEAD"],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, check=True, timeout=10,
        ).stdout.strip()
        if imported != policy["sha"]:
            raise LaunchError("incremental bundle proof differs from authorized release")
    executor = source / "scripts/trusted_release_server.py"
    secure_path(executor)
    if hashlib.sha256(executor.read_bytes()).hexdigest() != policy["executor_sha256"]:
        raise LaunchError("source executor differs from reviewed authorization")
    gate = source / "scripts/trusted_release_gate.py"
    secure_path(gate)
    # Repository Python first executes inside deploy(), after durable business intent.


def loopback_config():
    return (
        "Host health\n"
        "  HostName 127.0.0.1\n"
        "  User root\n"
        "  Port 22\n"
        "  IdentityFile /etc/reva-release/loopback.key\n"
        "  IdentitiesOnly yes\n"
        "  IdentityAgent none\n"
        "  BatchMode yes\n"
        "  StrictHostKeyChecking yes\n"
        "  UserKnownHostsFile /etc/reva-release/known_hosts\n"
        "  GlobalKnownHostsFile /dev/null\n"
        "  ForwardAgent no\n"
        "  ClearAllForwardings yes\n"
        "  RequestTTY no\n"
        "  PermitLocalCommand no\n"
        "  ProxyCommand none\n"
        "  ProxyJump none\n"
        "  ConnectTimeout 10\n"
        "  ServerAliveInterval 15\n"
        "  ServerAliveCountMax 3\n"
    )


def use_system_timezone():
    os.environ.pop("TZ", None)
    time.tzset()


def expiry_time(expiry):
    # Match sshd's system-local interpretation without trusting caller TZ.
    use_system_timezone()
    stamp = datetime.datetime.fromtimestamp(expiry).strftime("%Y%m%d%H%M%S")  # noqa: DTZ006 -- Match sshd's system-local parser exactly.
    if time.mktime(time.strptime(stamp, "%Y%m%d%H%M%S")) != expiry:
        raise LaunchError("system-local expiry cannot preserve the absolute deadline")
    return stamp


def validate_loopback(policy):
    for name in ("loopback.key", "loopback.pub", "known_hosts", "loopback.conf"):
        secure_path(CONFIG / name, private=True)
    if _read_private(CONFIG / "loopback.conf").decode() != loopback_config():
        raise LaunchError("loopback configuration is not the fixed reviewed configuration")
    public = _read_private(CONFIG / "loopback.pub").decode().strip()
    if re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/]+={0,2}", public) is None:
        raise LaunchError("invalid loopback public identity")
    expiry = expiry_time(policy["expires_at"])
    expected = f'from="127.0.0.1",restrict,expiry-time="{expiry}" {public}'
    keys = _read_private(Path("/root/.ssh/authorized_keys")).decode().splitlines()
    matches = [line for line in keys if public.split()[1] in line]
    if matches != [expected]:
        raise LaunchError("loopback identity lacks exact local-only expiring authorization")


def laya_private_key():
    # Reuse the independent sidecar key after an old-backend rollback; the
    # installer separately verifies its complete receipt and immutable identity.
    path = Path("/etc/reva-laya/service.env")
    if not path.exists() and not path.is_symlink():
        return secrets.token_urlsafe(32)
    secure_path(path)
    info = path.stat()
    if stat.S_IMODE(info.st_mode) != 0o640 or info.st_nlink != 1:
        raise LaunchError("invalid existing Laya credential metadata")
    match = re.fullmatch(r"LAYA_API_KEY=([A-Za-z0-9_-]{43,128})\n", path.read_text())
    if not match:
        raise LaunchError("invalid existing Laya credential format")
    return match.group(1)


def initial_laya_config(production):
    # This release provisions the requested first Laya deployment. Explicit
    # existing decision settings, including the emergency off, always win.
    if any(re.match(r"\s*(?:export\s+)?DECISION_", line, re.IGNORECASE) for line in production.splitlines()):
        return ""
    return ("DECISION_PROVIDER=laya\nDECISION_MODE=on\nDECISION_ADMIN_CONTROL_ENABLED=true\n"
            "DECISION_BASE_URL=http://127.0.0.1:8092/v1\nDECISION_MODEL=multilingual\n"
            "DECISION_MIN_CONFIDENCE=0.8\nDECISION_TIMEOUT_SECONDS=2\n"
            "DECISION_API_KEY=" + laya_private_key() + "\n")


def deploy(policy, workspace):
    # Provisioning remains a separate privileged, reviewed installation step.
    _assert_deployment_window(policy)
    validate_loopback(policy)
    secure_path(Path(PYTHON))
    workspace = Path(workspace)
    bindir = workspace / "bin"
    bindir.mkdir(mode=0o700)
    for command in ("ssh", "scp", "python3"):
        target = PYTHON if command == "python3" else f"/usr/bin/{command}"
        args = "" if command == "python3" else " -F /etc/reva-release/loopback.conf"
        wrapper = bindir / command
        _write_private(wrapper, f'#!/bin/sh\nexec {target}{args} "$@"\n'.encode())
        wrapper.chmod(0o700)
    production = read_production_env()
    lines = [line for line in production.splitlines() if not line.startswith(("DEPLOY_SERVER=", "DEPLOY_PATH="))]
    candidate = workspace / "deployment.env"
    _write_private(candidate, ("\n".join(lines) + "\n" + initial_laya_config(production)
                              + "DEPLOY_SERVER=health\nDEPLOY_PATH=/opt/health-app\n").encode())
    env = clean_environment(workspace)
    env.update(DEPLOY_SOURCE_SHA=policy["sha"], DEPLOY_ENV_FILE=str(candidate))
    source = workspace / "source"
    # Fresh CI/main attestation immediately before business deployment.
    execute([PYTHON, "-I", str(source / "scripts/trusted_release_gate.py"), "--sha", policy["sha"], "--workflow-sha", policy["sha"]], source, env, workspace / "preparation.log")
    _assert_deployment_window(policy)
    execute(["/bin/bash", str(source / "deploy.sh"), "-b"], source, env, workspace / "deployment.log")


def main():
    try:
        if not sys.flags.isolated or os.geteuid() != 0 or len(sys.argv) != 1:
            raise LaunchError("isolated root forced-command invocation required")
        os.umask(0o077)
        use_system_timezone()
        original_command = os.environ.get("SSH_ORIGINAL_COMMAND", "")
        parse_command(original_command)
        policy = validate_policy(_json(_read_private(POLICY)), now=int(time.time()))
        # Comparing the caller's expectation is mandatory before creating any
        # workspace, lock, marker, source checkout, or deployment side effect.
        command = authorize_command(original_command, policy)
        installed = Path(__file__).absolute()
        secure_path(installed)
        if hashlib.sha256(installed.read_bytes()).hexdigest() != policy["executor_sha256"]:
            raise LaunchError("installed executor differs from reviewed authorization")
        secure_path(STATE, directory=True)
        workspace = STATE / policy["sha"]
        if command == "status":
            result = release_status(policy["sha"], workspace)
        elif command in {"check-testflight", "claim-testflight-build", "claim-testflight-upload"}:
            if command != "check-testflight":
                workspace.mkdir(mode=0o700, exist_ok=True)
            action = {"check-testflight": "check", "claim-testflight-build": "build",
                      "claim-testflight-upload": "upload"}[command]
            result = testflight_only(policy, workspace, action)
        elif command == "check":
            check_readiness(policy)
            result = {"sha": policy["sha"], "state": "CHECKED"}
        elif command == "claim-testflight":
            result = claim_testflight(policy, workspace)
        elif command == "claim-build":
            workspace.mkdir(mode=0o700, exist_ok=True)
            result = claim_build(policy, workspace)
        else:
            workspace.mkdir(mode=0o700, exist_ok=True)
            result = run_once(policy, workspace, lambda: prepare_source(policy, workspace), lambda: deploy(policy, workspace))
        print(json.dumps(result, sort_keys=True))
        return 0
    except LaunchError as error:
        print(f"release launcher: {error}", file=sys.stderr)
        return 1
    except Exception:  # noqa: BLE001 -- Forced-command clients must receive no raw secret-bearing errors.
        print("release launcher: server validation failed; operator review required", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
