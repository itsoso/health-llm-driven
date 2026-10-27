"""Root-installed one-shot SSH commands, each bound to the caller's expected SHA.

Provisioning is deliberately separate: no installation, key issuance, policy
editing, retry, lease cleanup, or recovery is available to the caller.
"""

import datetime
import fcntl
import grp
import hashlib
import hmac
import importlib.util
import json
import os
import pwd
import re
import secrets
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

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
    match = re.fullmatch(r"(run|status|check|check-backend-v1|run-backend-v1|claim-build|claim-testflight|check-testflight|claim-testflight-build|claim-testflight-upload|claim-ota|finish-ota|claim-retained-testflight|finish-retained-testflight) ([0-9a-f]{40})", command)
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
        or (data["expires_at"] != 0 and data["expires_at"] <= now)
        or not isinstance(data["executor_sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", data["executor_sha256"]) is None
    ):
        raise LaunchError("invalid or expired release authorization")
    return data


def _assert_deployment_window(policy):
    now = time.time()
    validate_policy(policy, now=now)
    if policy["expires_at"] != 0 and policy["expires_at"] - now < DEPLOY_TIMEOUT_SECONDS + RECOVERY_MARGIN_SECONDS:
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
        assert_ota_history()
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


def _load_frontend_finalizer():
    """Load only the helper committed alongside this canonical executor."""
    entry = Path(__file__).absolute()
    if entry == Path("/usr/local/lib/reva-release/trusted_release_server.py"):
        policy = validate_policy(_json(_read_private(POLICY)), now=0)
        secure_path(entry)
        if hashlib.sha256(entry.read_bytes()).hexdigest() != policy["executor_sha256"]:
            raise LaunchError("installed executor binding differs")
        sha = policy["sha"]
        source = STATE / "bootstrap" / sha / "source"
    else:
        source = entry.parent.parent
        sha = source.parent.name
        if (re.fullmatch(r"[0-9a-f]{40}", sha) is None
                or source != STATE / "bootstrap" / sha / "source"
                or entry != source / "scripts/trusted_release_server.py"):
            raise LaunchError("canonical frontend history helper source required")
    script = source / "scripts/frontend_verified_finalization.py"
    secure_path(script)
    if os.path.lexists(script.parent / "__pycache__"):
        raise LaunchError("cached frontend history helper forbidden")
    env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_NO_REPLACE_OBJECTS": "1"}
    expected = subprocess.run(["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-C", str(source),
                               "show", sha + ":scripts/frontend_verified_finalization.py"],
                              env=env, stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=30).stdout
    if script.read_bytes() != expected:
        raise LaunchError("frontend history helper differs from canonical source")
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("canonical_frontend_finalizer", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_ota_unclaimed_retirement():
    """Load only the helper committed alongside this canonical executor."""
    entry = Path(__file__).absolute()
    if entry == Path("/usr/local/lib/reva-release/trusted_release_server.py"):
        policy = validate_policy(_json(_read_private(POLICY)), now=0)
        secure_path(entry)
        if hashlib.sha256(entry.read_bytes()).hexdigest() != policy["executor_sha256"]:
            raise LaunchError("installed executor binding differs")
        sha = policy["sha"]
        source = STATE / "bootstrap" / sha / "source"
    else:
        source = entry.parent.parent
        sha = source.parent.name
        if (re.fullmatch(r"[0-9a-f]{40}", sha) is None
                or source != STATE / "bootstrap" / sha / "source"
                or entry != source / "scripts/trusted_release_server.py"):
            raise LaunchError("canonical OTA preclaim history helper source required")
    script = source / "scripts/trusted_ota_unclaimed_retirement.py"
    secure_path(script)
    if os.path.lexists(script.parent / "__pycache__"):
        raise LaunchError("cached OTA preclaim history helper forbidden")
    env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_NO_REPLACE_OBJECTS": "1"}
    expected = subprocess.run(["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-C", str(source),
                               "show", sha + ":scripts/trusted_ota_unclaimed_retirement.py"],
                              env=env, stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=30).stdout
    if script.read_bytes() != expected:
        raise LaunchError("OTA preclaim history helper differs from canonical source")
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("canonical_ota_unclaimed_retirement", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frontend_publication_backup_entries(root, *, live=False):
    """Revalidate every entry on every pass, including cache hits."""
    root = Path(root)
    if live:
        if root not in {PRODUCTION / "frontend" / ".next", PRODUCTION / "frontend" / "node_modules"}:
            raise LaunchError("fixed live frontend artifact path required")
        secure_path(root, directory=True)
    count = 0
    pending = [root]
    while pending:
        path = pending.pop()
        count += 1
        if count > 150000:
            raise LaunchError("frontend backup inventory exceeds bound")
        info = path.lstat()
        relative = path.relative_to(root)
        cache_root = root.name == "previous-next" or (live and root == PRODUCTION / "frontend" / ".next")
        cache = cache_root and relative.parts and relative.parts[0] == "cache"
        if stat.S_ISLNK(info.st_mode) and (cache or info.st_uid != 0):
            raise LaunchError("unsafe frontend backup link metadata")
        if cache and info.st_uid != 0:
            try:
                account = pwd.getpwnam("health-web")
            except KeyError:
                raise LaunchError("frontend cache identity missing") from None
            if ((info.st_uid, info.st_gid) != (account.pw_uid, account.pw_gid)
                    or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode)
                    or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))
                    or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)):
                raise LaunchError("unsafe frontend cache metadata")
        elif not stat.S_ISLNK(info.st_mode):
            validate_metadata(info, directory=stat.S_ISDIR(info.st_mode))
        target = None
        if stat.S_ISLNK(info.st_mode):
            try:
                resolved = path.resolve(strict=True)
            except (OSError, RuntimeError):
                raise LaunchError("invalid frontend backup link") from None
            target = os.readlink(path)
            if not resolved.is_relative_to(root.resolve()) or os.path.isabs(target):
                raise LaunchError("frontend backup link escapes bundle")
        elif stat.S_ISDIR(info.st_mode):
            pending.extend(sorted(path.iterdir(), reverse=True))
        elif not (stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size < 2_000_000_000):
            raise LaunchError("unsupported frontend backup object")
        yield path, relative, info, target


def _frontend_backup_identity(info):
    values = (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
              info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if any(type(value) is not int for value in values):
        raise LaunchError("frontend backup identity unavailable")
    return values


def _frontend_publication_backup_fingerprint(root):
    fingerprint = hashlib.sha256()
    for _path, relative, info, target in _frontend_publication_backup_entries(root):
        # ctime cannot be restored with utime; no persistent or cross-run cache.
        record = [relative.as_posix(), *_frontend_backup_identity(info), target]
        fingerprint.update(json.dumps(record, separators=(",", ":")).encode() + b"\n")
    return fingerprint.hexdigest()


def _frontend_publication_backup_digest(root, *, live=False, memo=None, expected=None):
    """Keep historical digest bytes; reuse only inside one locked rotation."""
    root = Path(root)
    before = None
    key = str(root.absolute())
    if memo is not None and not live:
        before = _frontend_publication_backup_fingerprint(root)
        saved = memo.get(key)
        if saved is not None and saved[0] == before:
            if _frontend_publication_backup_fingerprint(root) != before:
                raise LaunchError("frontend backup changed during verification")
            return saved[1]
    digest = hashlib.sha256()
    for path, relative, info, target in _frontend_publication_backup_entries(root, live=live):
        digest.update((relative.as_posix() + "\0" + str(stat.S_IMODE(info.st_mode)) + "\0"
                       + str(info.st_uid) + "\0" + str(info.st_gid) + "\0").encode())
        if target is not None:
            digest.update(b"link\0" + target.encode())
        elif stat.S_ISDIR(info.st_mode):
            digest.update(b"directory\0")
        else:
            digest.update(b"file\0" + str(info.st_size).encode() + b"\0")
            if before is None:
                # Preserve the existing non-memo path for publishers/live data.
                stream = path.open("rb")
            else:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                stream = os.fdopen(fd, "rb")
            with stream:
                if before is not None and _frontend_backup_identity(os.fstat(stream.fileno())) != _frontend_backup_identity(info):
                    raise LaunchError("frontend backup file changed before read")
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                if before is not None and _frontend_backup_identity(os.fstat(stream.fileno())) != _frontend_backup_identity(info):
                    raise LaunchError("frontend backup file changed during read")
    result = digest.hexdigest()
    if before is not None:
        after = _frontend_publication_backup_fingerprint(root)
        if after != before:
            raise LaunchError("frontend backup changed during verification")
        if expected is not None and result == expected:
            memo[key] = (after, result)
    return result


def _frontend_publication_file_digest(path):
    secure_path(path, private=True)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    digest = hashlib.sha256()
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        validate_metadata(info, private=True)
        if info.st_size >= 2_000_000_000:
            raise LaunchError("frontend publication proof exceeds bound")
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frontend_stopped_failure(operation):
    """Bind the one authorized, still-intact stopped-before-rename incident."""
    intent = dict(kind='frontend-publication', publisher_sha='f8dd4fe8cc962aed54a2db97dc981c82093b93ea',
                  production_sha='dbad4e66c29f31c0ae149fecefa6c0d4f3e45283',
                  operation_id='637078dd8c584686a59000de91d2dad2',
                  frontend_tree='0e0a36d69a526e0ca5395f5c5082a77534dd739c',
                  state='FRONTEND_STARTED', artifact_digest=None)
    artifact='2d8d765d014a5015ae6eaf016e77d8bab46ff262a3954ae15a4044914a3dfa8e'
    if (operation.name!=intent['operation_id']
            or _json(_read_private(operation/'intent.json'))!=intent
            or _json(_read_private(operation/'failed.json'))!={**intent,'state':'FRONTEND_NEEDS_OPERATOR'}
            or _json(_read_private(operation/'install-started.json'))!={**intent,'state':'FRONTEND_INSTALLING','artifact_digest':artifact}):
        raise LaunchError('fixed stopped frontend incident differs')
    before=_json(_read_private(operation/'before.json'))
    if not isinstance(before,dict) or any(before.get(k)!=intent[k] for k in ('publisher_sha','production_sha','operation_id','frontend_tree')):
        raise LaunchError('original stopped frontend preflight differs')
    return intent,artifact


def validate_frontend_stopped_recovery(operation,complete):
    _,artifact=frontend_stopped_failure(operation)
    intent=_json(_read_private(operation/'recovery-intent.json'))
    finished=_json(_read_private(operation/'recovery-completed.json'))
    keys={'kind','state','operation_id','recovery_publisher_sha','original_proof',
          'original_code_sha256','candidate_digest','old_bundle_digest','frontend_process','lease'}
    if (not isinstance(intent,dict) or set(intent)!=keys or intent['kind']!='frontend-stopped-recovery'
            or intent['state']!='RECOVERY_STARTED' or intent['operation_id']!=operation.name
            or not isinstance(intent['recovery_publisher_sha'],str)
            or re.fullmatch('[0-9a-f]{40}',intent['recovery_publisher_sha']) is None
            or intent['original_code_sha256']!='d17d896f05340e20735cba86a92eaaf2eeb6b548fd0e56e084ed86e375d15c68'
            or intent['candidate_digest']!=artifact or not isinstance(intent['old_bundle_digest'],str)
            or re.fullmatch('[0-9a-f]{64}',intent['old_bundle_digest']) is None
            or complete.get('artifact_digest')!=artifact
            or finished!={**intent,'state':'RECOVERY_SUCCEEDED',
                'intent_sha256':_frontend_publication_file_digest(operation/'recovery-intent.json'),
                'backups_digest':complete.get('backups_digest')}
            or complete.get('recovery_sha256')!=_frontend_publication_file_digest(operation/'recovery-completed.json')):
        raise LaunchError('stopped frontend recovery completion differs')
    proofs={}
    for name in ('intent.json','before.json','build.log','install-started.json','failed.json'):
        path=operation/name;secure_path(path,private=True);info=path.lstat()
        proofs[name]=dict(dev=info.st_dev,ino=info.st_ino,mode=info.st_mode,uid=info.st_uid,
                          gid=info.st_gid,sha256=_frontend_publication_file_digest(path))
    if intent['original_proof']!=proofs:
        raise LaunchError('original failed publication evidence changed')


def _history_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _release_io_snapshot():
    try:
        raw = Path('/proc/self/io').read_text()
    except OSError:
        return None
    values = dict(re.findall(r'^(rchar|read_bytes): ([0-9]+)$', raw, re.MULTILINE))
    return {k: int(values[k]) for k in ('rchar', 'read_bytes')} if len(values) == 2 else None


def _history_signature(key, purpose, value):
    return hmac.new(key, purpose.encode() + b"\0" + _history_json(value), hashlib.sha256).hexdigest()


def _history_private(path):
    secure_path(path, private=True)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
        raise LaunchError("unsafe history seal file")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        validate_metadata(opened, private=True)
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise LaunchError("history seal identity changed")
        raw = stream.read(1_000_001)
    if len(raw) > 1_000_000:
        raise LaunchError("history seal exceeds bound")
    return raw


def _history_signed(key, purpose, value):
    return _history_json({'payload': value, 'signature': _history_signature(key, purpose, value)})


def _history_verify(key, purpose, raw):
    value = _json(raw)
    if (not isinstance(value, dict) or set(value) != {'payload', 'signature'}
            or not isinstance(value['signature'], str)
            or not hmac.compare_digest(value['signature'], _history_signature(key, purpose, value['payload']))):
        raise LaunchError("history seal signature differs")
    return value['payload']


def _frontend_history_seal(state, *, recovery=False):
    root = Path(state) / 'frontend-history-seal'
    if not os.path.lexists(root):
        return None
    secure_path(root, directory=True)
    if stat.S_IMODE(root.lstat().st_mode) != 0o700:
        raise LaunchError("history seal directory must remain private")
    names = {p.name for p in root.iterdir()}
    generations = sorted(n for n in names if re.fullmatch(r'[0-9]{10}\.json', n))
    allowed = {'key', 'anchor.json'} | set(generations)
    if recovery:
        allowed |= {'update-intent.json', 'anchor.pending'}
    if (not generations or len(generations) > 1000 or 'key' not in names
            or names - allowed or generations != [f'{n:010d}.json' for n in range(1, len(generations) + 1)]):
        raise LaunchError("partial or unknown history seal inventory")
    key = _history_private(root / 'key')
    if len(key) != 32:
        raise LaunchError("invalid history seal key")
    previous = None
    digests = []
    payload = None
    for generation, name in enumerate(generations, 1):
        raw = _history_private(root / name)
        payload = _history_verify(key, 'reva-frontend-history-checkpoint-v1', raw)
        fields = {'schema', 'purpose', 'generation', 'previous', 'sealed_by_sha', 'active_operation',
                  'live_digest', 'records'}
        if (not isinstance(payload, dict) or set(payload) != fields
                or type(payload['schema']) is not int or payload['schema'] != 1
                or payload['purpose'] != 'frontend-publication-history'
                or type(payload['generation']) is not int or payload['generation'] != generation
                or payload['previous'] != previous
                or not isinstance(payload['sealed_by_sha'], str)
                or re.fullmatch('[0-9a-f]{40}', payload['sealed_by_sha']) is None
                or not isinstance(payload['live_digest'], str)
                or re.fullmatch('[0-9a-f]{64}', payload['live_digest']) is None
                or not isinstance(payload['records'], dict) or not 1 <= len(payload['records']) <= 4096
                or any(not isinstance(k, str) or re.fullmatch('[0-9a-f]{32}', k) is None
                       or not isinstance(v, str) or re.fullmatch('[0-9a-f]{64}', v) is None
                       for k, v in payload['records'].items())
                or not isinstance(payload['active_operation'], str)
                or payload['active_operation'] not in payload['records']):
            raise LaunchError("invalid history checkpoint binding")
        previous = hashlib.sha256(raw).hexdigest()
        digests.append(previous)
    anchor = None
    if 'anchor.json' in names:
        anchor = _history_verify(key, 'reva-frontend-history-anchor-v1', _history_private(root / 'anchor.json'))
    expected = {'generation': len(generations), 'checkpoint_sha256': previous}
    tail = anchor != expected
    old = {'generation': len(generations) - 1, 'checkpoint_sha256': digests[-2]} if len(digests) > 1 else None
    if tail and (not recovery or anchor != old):
        raise LaunchError("history anchor or terminal generation differs")
    if 'update-intent.json' in names:
        intent = _history_verify(key, 'reva-frontend-history-update-v1', _history_private(root / 'update-intent.json'))
        if intent != expected:
            raise LaunchError("history update intent differs")
    if 'anchor.pending' in names:
        pending = _history_verify(key, 'reva-frontend-history-anchor-v1', _history_private(root / 'anchor.pending'))
        if pending != expected:
            raise LaunchError("history pending anchor differs")
    return dict(payload=payload, digest=previous, key=key, root=root,
                incomplete=tail or 'update-intent.json' in names or 'anchor.pending' in names)


def _history_write(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(path.parent)


def _history_commit_anchor(seal):
    root, key = seal['root'], seal['key']
    value = {'generation': seal['payload']['generation'], 'checkpoint_sha256': seal['digest']}
    intent = root / 'update-intent.json'
    intent_raw = _history_signed(key, 'reva-frontend-history-update-v1', value)
    if not os.path.lexists(intent):
        _history_write(intent, intent_raw)
    pending = root / 'anchor.pending'
    if not os.path.lexists(pending):
        _history_write(pending, _history_signed(key, 'reva-frontend-history-anchor-v1', value))
    os.replace(pending, root / 'anchor.json')
    _sync_directory(root)
    intent.unlink()
    try:
        _sync_directory(root)
    except OSError:
        # Preserve an explicit incomplete marker even after an unlink/fsync failure.
        _history_write(intent, intent_raw)
        raise


def seal_frontend_publication_history(state, *, active_operation, live_digest,
                                      sealed_by_sha='0' * 40, backup_memo=None):
    if (not isinstance(active_operation, str) or re.fullmatch('[0-9a-f]{32}', active_operation) is None
            or not isinstance(live_digest, str) or re.fullmatch('[0-9a-f]{64}', live_digest) is None
            or not isinstance(sealed_by_sha, str) or re.fullmatch('[0-9a-f]{40}', sealed_by_sha) is None):
        raise LaunchError("exact frontend seal binding required")
    old = _frontend_history_seal(state)
    records = assert_frontend_publication_history(state, backup_memo=backup_memo,
                                                 _force_operations={active_operation})
    complete = frontend_publication_completion(state, active_operation)
    if active_operation not in records or complete['artifact_digest'] != live_digest:
        raise LaunchError("active frontend differs from original publication")
    if not 1 <= len(records) <= 4096:
        raise LaunchError('history catalog exceeds bound')
    root = Path(state) / 'frontend-history-seal'
    if old is None:
        root.mkdir(mode=0o700)
        _sync_directory(root.parent)
        key = secrets.token_bytes(32)
        _history_write(root / 'key', key)
        generation, previous = 1, None
    else:
        key = old['key']
        generation, previous = old['payload']['generation'] + 1, old['digest']
    if generation > 1000:
        raise LaunchError('history generation bound reached; explicit maintenance required')
    payload = dict(schema=1, purpose='frontend-publication-history', generation=generation,
                   previous=previous, sealed_by_sha=sealed_by_sha, active_operation=active_operation,
                   live_digest=live_digest, records=records)
    raw = _history_signed(key, 'reva-frontend-history-checkpoint-v1', payload)
    _history_write(root / f'{generation:010d}.json', raw)
    current = dict(root=root, key=key, payload=payload, digest=hashlib.sha256(raw).hexdigest())
    _history_commit_anchor(current)
    return dict(state='FRONTEND_HISTORY_SEALED', generation=generation,
                checkpoint_sha256=current['digest'], active_operation=active_operation,
                archived_operations=len(records) - 1)


def inspect_frontend_history_seal(state):
    seal = _frontend_history_seal(state, recovery=True)
    if seal is None or not seal['incomplete']:
        raise LaunchError("no incomplete history checkpoint")
    return dict(state='FRONTEND_HISTORY_SEAL_INCOMPLETE', checkpoint_sha256=seal['digest'],
                active_operation=seal['payload']['active_operation'], generation=seal['payload']['generation'])


def finish_frontend_history_seal(state, *, checkpoint_sha256, live_digest):
    seal = _frontend_history_seal(state, recovery=True)
    if (seal is None or not seal['incomplete'] or checkpoint_sha256 != seal['digest']
            or live_digest != seal['payload']['live_digest']):
        raise LaunchError("original incomplete seal or live binding differs")
    records = assert_frontend_publication_history(state, _seal_snapshot=seal,
                                                 _force_operations={seal['payload']['active_operation']})
    if records != seal['payload']['records']:
        raise LaunchError("history changed before seal completion")
    _history_commit_anchor(seal)
    return dict(state='FRONTEND_HISTORY_SEALED', checkpoint_sha256=seal['digest'],
                generation=seal['payload']['generation'], active_operation=seal['payload']['active_operation'])


def _frontend_no_backup_provenance(state, operation, intent, before, complete):
    """Check consumed build provenance without reading moved build directories."""
    root = Path(state) / 'frontend-artifacts'
    artifact = root / operation.name
    for path in (root, artifact):
        secure_path(path, directory=True)
        if stat.S_IMODE(path.lstat().st_mode) != 0o700:
            raise LaunchError('unsafe consumed frontend artifact audit')
    if {p.name for p in artifact.iterdir()} != {'prepare.lock', 'intent.json', 'build.log', 'ready.json', 'claim.json'}:
        raise LaunchError('consumed frontend artifact audit differs')
    _read_private(artifact / 'prepare.lock')
    raw = _read_private(artifact / 'ready.json')
    ready = _json(raw)
    proof = before.get('prepared_artifact')
    if (not isinstance(ready, dict)
            or set(ready) != {'binding', 'state', 'artifact_digest', 'intent_sha256', 'build_log_sha256'}
            or ready['state'] != 'FRONTEND_ARTIFACT_READY'
            or ready['artifact_digest'] != complete['artifact_digest']
            or proof != {'artifact_id': operation.name, 'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'manifest': ready}):
        raise LaunchError('consumed frontend artifact proof differs')
    binding = ready['binding']
    expected_keys = {'schema_version', 'publisher_sha', 'frontend_tree', 'artifact_id', 'package_lock_sha256',
                     'public_build_env', 'toolchain', 'recipe_sha256'}
    if (not isinstance(binding, dict) or set(binding) != expected_keys
            or type(binding['schema_version']) is not int or binding['schema_version'] != 1
            or any(binding[k] != intent[k] for k in ('publisher_sha', 'frontend_tree'))
            or binding['artifact_id'] != operation.name
            or binding['public_build_env'] != before.get('public_build_env')
            or any(not isinstance(binding[k], str) or re.fullmatch('[0-9a-f]{64}', binding[k]) is None
                   for k in ('package_lock_sha256', 'recipe_sha256'))):
        raise LaunchError('consumed frontend artifact binding differs')
    original = _read_private(artifact / 'intent.json')
    if (_json(original) != {'binding': binding, 'state': 'FRONTEND_ARTIFACT_PREPARING'}
            or hashlib.sha256(original).hexdigest() != ready['intent_sha256']
            or _frontend_publication_file_digest(artifact / 'build.log') != ready['build_log_sha256']
            or _frontend_publication_file_digest(operation / 'build.log') != ready['build_log_sha256']
            or _json(_read_private(artifact / 'claim.json')) != {
                'schema_version': 1, 'artifact_id': operation.name, 'operation_id': operation.name,
                'production_sha': intent['production_sha'], 'manifest_sha256': proof['manifest_sha256']}):
        raise LaunchError('consumed frontend claim or source hashes differ')


# One reviewed false-negative readback profile; not a retry of publication.
NO_BACKUP_FINALIZATION_OPERATION = 'c140343fa265bb6d2214a3b9eda4e98b'
NO_BACKUP_FINALIZATION_BINDING = {
    'publisher_sha': '65fe758296487bb552cfdc0e3c98554aab7a0b0e',
    'production_sha': 'b2948b77b0b3df260d03623c5b3cfb6539e5d640',
    'frontend_tree': '668fa6267030b8e97d5f4bff3824cf669e6d460e',
    'operation_id': NO_BACKUP_FINALIZATION_OPERATION,
    'artifact_digest': '07eee86c85dce19e35318857cb372ea2a4adb921e458ac553a3f79328ac09550',
}
PRIVACY_FINALIZATION_OPERATION = 'e94f8c89521046fcae79cdb8fd54dc09'
PRIVACY_FINALIZATION_BINDING = {
    'publisher_sha': '6e2e52a591dde9a18d485373dcbf8fc1d9c07207',
    'production_sha': '6e2e52a591dde9a18d485373dcbf8fc1d9c07207',
    'frontend_tree': 'd281e5eea362a1f1fad09984e7a64798b66af340',
    'operation_id': PRIVACY_FINALIZATION_OPERATION,
    'artifact_digest': '3aca2e050a0530e27a1080c0049e0f2121f5c814d3d71c20e0731db3ee35824d',
}

PRIVACY_FINALIZATION_SOURCE_HASHES = {'deploy.sh': 'd01655afff653c26185c75b53ed7fd5f5280b867406f6374c510365ccba1009e', 'scripts/trusted_frontend_artifact.py': 'e4a7ed22df4a246bc55e5babb4a377663e9b61a7ca8840486d2189e517f10d1c', 'scripts/trusted_frontend_no_backup.py': '8ba60f0e28577d89f8b67203ab2509b563f21f61b9e0e0e3015ee79c790688f5', 'scripts/trusted_frontend_publish.py': 'b76c2ba1381764563db28c904d67ce844011a2386481213e52e73de27e085f48', 'scripts/trusted_frontend_rebuild.py': 'b68843dd71d79541bba3395cb32cae84d5d7f9cd771745d74f36adb163776d4d'}

def no_backup_finalization_profile(operation_id):
    if operation_id == NO_BACKUP_FINALIZATION_OPERATION:
        return 'csr-login-readback-v1', dict(NO_BACKUP_FINALIZATION_BINDING)
    if operation_id == PRIVACY_FINALIZATION_OPERATION:
        return 'privacy-title-readback-v1', dict(PRIVACY_FINALIZATION_BINDING)
    raise LaunchError('unknown no-backup finalization profile')


NO_BACKUP_ORIGINAL_FILES = {'intent.json', 'before.json', 'build.log', 'install-started.json', 'failed.json'}


def _finalization_file_evidence(path):
    secure_path(path, private=True)
    before = path.lstat()
    raw = _read_private(path)
    after = path.lstat()
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if any(getattr(before, name) != getattr(after, name) for name in fields):
        raise LaunchError('finalization evidence changed while reading')
    return {'sha256': hashlib.sha256(raw).hexdigest(), **{name: getattr(after, name) for name in fields}}


def privacy_finalization_source_proof(state, binding):
    source = Path(state) / 'bootstrap' / binding['publisher_sha'] / 'source'
    for name, expected in PRIVACY_FINALIZATION_SOURCE_HASHES.items():
        path = source / name
        secure_path(path)
        before = path.lstat()
        with path.open('rb') as stream:
            opened = os.fstat(stream.fileno())
            raw = stream.read(1048577)
            after = os.fstat(stream.fileno())
        named = path.lstat()
        fields = ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if (len(raw) > 1048576 or before.st_nlink != 1
                or any(getattr(before, k) != getattr(value, k) for k in fields for value in (opened, after, named))
                or hashlib.sha256(raw).hexdigest() != expected):
            raise LaunchError('original privacy publication implementation differs')
    return dict(PRIVACY_FINALIZATION_SOURCE_HASHES)


def no_backup_finalization_original(state, operation_id):
    _, binding = no_backup_finalization_profile(operation_id)
    operation = Path(state) / 'frontend-publications' / operation_id
    secure_path(operation, directory=True)
    if stat.S_IMODE(operation.lstat().st_mode) != 0o700 or {p.name for p in operation.iterdir()} != NO_BACKUP_ORIGINAL_FILES:
        raise LaunchError('original failed publication inventory differs')
    files = {name: _finalization_file_evidence(operation / name) for name in NO_BACKUP_ORIGINAL_FILES}
    intent = {**binding, 'kind': 'frontend-publication', 'state': 'FRONTEND_STARTED',
              'artifact_digest': None, 'publication_policy': 'no-backup-v1'}
    if _json(_read_private(operation / 'intent.json')) != intent:
        raise LaunchError('original failed publication binding differs')
    for name, status, digest in [('install-started.json', 'FRONTEND_INSTALLING', binding['artifact_digest']),
                                 ('failed.json', 'FRONTEND_NEEDS_OPERATOR', None)]:
        if _json(_read_private(operation / name)) != {**intent, 'state': status, 'artifact_digest': digest}:
            raise LaunchError('original failure phase differs')
    before = _json(_read_private(operation / 'before.json'))
    if (not isinstance(before, dict) or before.get('publication_policy') != 'no-backup-v1'
            or any(before.get(k) != binding[k] for k in ('publisher_sha', 'production_sha', 'frontend_tree', 'operation_id'))):
        raise LaunchError('original failure plan differs')
    _frontend_no_backup_provenance(state, operation, intent, before, binding)
    result = {'binding': binding, 'files': files}
    if operation_id == PRIVACY_FINALIZATION_OPERATION:
        result['source_hashes'] = privacy_finalization_source_proof(state, binding)
    return result


def no_backup_finalization_completion(state, operation_id):
    original = no_backup_finalization_original(state, operation_id)
    profile, binding = no_backup_finalization_profile(operation_id)
    root = Path(state) / 'frontend-publication-finalizations'
    audit = root / operation_id
    for path in (root, audit):
        secure_path(path, directory=True)
        if stat.S_IMODE(path.lstat().st_mode) != 0o700:
            raise LaunchError('finalization audit directory differs')
    if {p.name for p in audit.iterdir()} != {'intent.json', 'verified.json', 'completed.json'}:
        raise LaunchError('incomplete no-backup finalization')
    raw = _read_private(audit / 'intent.json')
    plan = _json(raw)
    if (not isinstance(plan, dict) or set(plan) != {'schema_version', 'profile', 'finalizer_sha', 'original', 'lease', 'process'}
            or type(plan['schema_version']) is not int or plan['schema_version'] != 1
            or plan['profile'] != profile or plan['original'] != original
            or not isinstance(plan['finalizer_sha'], str) or re.fullmatch('[a-f0-9]{40}', plan['finalizer_sha']) is None
            or not isinstance(plan['process'], dict) or not isinstance(plan['lease'], dict)):
        raise LaunchError('finalization intent binding differs')
    verified = _json(_read_private(audit / 'verified.json'))
    if verified != {'state': 'LIVE_VERIFIED', 'intent_sha256': hashlib.sha256(raw).hexdigest()}:
        raise LaunchError('finalization verification differs')
    complete = _json(_read_private(audit / 'completed.json'))
    expected = {'state': 'FINALIZED_NO_BACKUP_PUBLICATION', **binding,
                'finalizer_sha': plan['finalizer_sha'], 'intent_sha256': hashlib.sha256(raw).hexdigest(),
                'verified_sha256': _frontend_publication_file_digest(audit / 'verified.json')}
    if complete != expected:
        raise LaunchError('finalization terminal differs')
    return complete


def frontend_publication_completion(state, operation_id):
    finalized = Path(state) / 'frontend-publication-finalizations' / operation_id
    if os.path.lexists(finalized):
        return no_backup_finalization_completion(state, operation_id)
    return _json(_read_private(Path(state) / 'frontend-publications' / operation_id / 'completed.json'))


def assert_frontend_publication_history(state=None, *, pending_stopped_publication=None, backup_memo=None,
                                        _force_operations=(), _seal_snapshot=None, verify_backups=False, pending_no_backup_finalization=None):
    """Validate release receipts, without claiming old backups are restorable.

    Only an explicitly requested single recovery target reads backup contents.
    Current candidate/live artifact validation remains in its own publisher.
    """
    if (type(verify_backups) is not bool or (verify_backups and (len(_force_operations) != 1
            or not isinstance(_force_operations[0], str) or re.fullmatch(r'[0-9a-f]{32}', _force_operations[0]) is None))):
        raise LaunchError('explicit target operation required for backup recovery verification')
    if pending_no_backup_finalization is not None:
        no_backup_finalization_profile(pending_no_backup_finalization)
    finalizations = Path(state or STATE) / 'frontend-publication-finalizations'
    if os.path.lexists(finalizations):
        secure_path(finalizations, directory=True)
        if stat.S_IMODE(finalizations.lstat().st_mode) != 0o700:
            raise LaunchError('unsafe no-backup finalization root')
        for finalized in finalizations.iterdir():
            if finalized.name == pending_no_backup_finalization:
                raise LaunchError('no-backup finalization already attempted')
            no_backup_finalization_completion(state or STATE, finalized.name)
    started, io_before = time.monotonic(), _release_io_snapshot()
    seal = _seal_snapshot if _seal_snapshot is not None else _frontend_history_seal(state or STATE)
    catalog = {}
    archived, verified = 0, 0
    root = Path(state or STATE) / "frontend-publications"
    if not os.path.lexists(root):
        if seal is not None:
            raise LaunchError("sealed frontend history is missing")
        return catalog
    secure_path(root, directory=True)
    if stat.S_IMODE(root.lstat().st_mode) != 0o700:
        raise LaunchError("frontend publication root must remain private")
    proof_names = {"before.json", "build.log", "install-started.json", "verified.json"}
    legacy_backups = {"previous-next", "previous-node-modules"}
    base_keys = {"kind", "publisher_sha", "production_sha", "operation_id", "frontend_tree", "state", "artifact_digest"}
    for operation in root.iterdir():
        secure_path(operation, directory=True)
        inventory={p.name for p in operation.iterdir()}
        if operation.name == pending_no_backup_finalization:
            no_backup_finalization_original(state or STATE, operation.name)
            continue
        if os.path.lexists(finalizations / operation.name):
            if verify_backups and operation.name in _force_operations:
                raise LaunchError('no-backup finalization has no backup set')
            complete = no_backup_finalization_completion(state or STATE, operation.name)
            intent = _json(_read_private(operation / 'intent.json'))
            catalog[operation.name] = hashlib.sha256(_history_json({'intent': intent, 'completed': complete})).hexdigest()
            if seal is not None and operation.name in seal['payload']['records']:
                if (seal['payload']['records'][operation.name] != catalog[operation.name]
                        or (operation.name == seal['payload']['active_operation'] and complete['artifact_digest'] != seal['payload']['live_digest'])):
                    raise LaunchError('sealed finalization binding differs')
                if operation.name != seal['payload']['active_operation']: archived += 1
            continue
        if pending_stopped_publication is not None and operation.name==pending_stopped_publication:
            if inventory!={'intent.json','before.json','build.log','install-started.json','failed.json'} or stat.S_IMODE(operation.lstat().st_mode)!=0o700:
                raise LaunchError('stopped recovery already attempted or partial switch')
            frontend_stopped_failure(operation)
            continue
        if 'intent.json' not in inventory:
            raise LaunchError('unfinished frontend publication; operator review required')
        intent = _json(_read_private(operation / "intent.json"))
        no_backup = isinstance(intent, dict) and intent.get('publication_policy') == 'no-backup-v1'
        if isinstance(intent, dict) and 'publication_policy' in intent and not no_backup:
            raise LaunchError('unknown frontend publication policy')
        keys = base_keys | ({'publication_policy'} if no_backup else set())
        backups = set() if no_backup else legacy_backups
        recovered='recovery-completed.json' in inventory
        if no_backup and (recovered or (verify_backups and operation.name in _force_operations)):
            raise LaunchError('no-backup publication has no recovery set')
        extras={'failed.json','recovery-intent.json','recovery-completed.json'} if recovered else set()
        if (stat.S_IMODE(operation.lstat().st_mode) != 0o700
                or re.fullmatch(r"[0-9a-f]{32}", operation.name) is None
                or inventory != proof_names | backups | {"intent.json", "completed.json"} | extras):
            raise LaunchError("unfinished or unknown frontend publication; operator review required")
        if (not isinstance(intent, dict) or set(intent) != keys or intent["kind"] != "frontend-publication"
                or intent["operation_id"] != operation.name or intent["state"] != "FRONTEND_STARTED"
                or intent["artifact_digest"] is not None
                or any(not isinstance(intent[k], str) or re.fullmatch(r"[0-9a-f]{40}", intent[k]) is None
                       for k in ("publisher_sha", "production_sha", "frontend_tree"))):
            raise LaunchError("invalid frontend publication binding")
        complete = _json(_read_private(operation / "completed.json"))
        if (not isinstance(complete, dict) or set(complete) != keys | {"proof_sha256", "backups_digest"} | ({'recovery_sha256'} if recovered else set())
                or not isinstance(complete["artifact_digest"], str)
                or re.fullmatch(r"[0-9a-f]{64}", complete["artifact_digest"]) is None
                or {k: complete[k] for k in keys} != {**intent, "state": "FRONTEND_SUCCEEDED", "artifact_digest": complete["artifact_digest"]}):
            raise LaunchError("invalid frontend publication completion")
        if recovered:
            validate_frontend_stopped_recovery(operation,complete)
        for name, status in (("install-started.json", "FRONTEND_INSTALLING"), ("verified.json", "FRONTEND_VERIFIED")):
            if _json(_read_private(operation / name)) != {**intent, "state": status, "artifact_digest": complete["artifact_digest"]}:
                raise LaunchError("frontend publication phase differs")
        before = _json(_read_private(operation / "before.json"))
        if not isinstance(before, dict) or any(before.get(k) != intent[k] for k in ("publisher_sha", "production_sha", "operation_id", "frontend_tree")):
            raise LaunchError("frontend publication preflight differs")
        if complete["proof_sha256"] != {n: _frontend_publication_file_digest(operation / n) for n in proof_names}:
            raise LaunchError("frontend publication proof hashes differ")
        for name in backups:
            secure_path(operation / name, directory=True)
        expected_backups = complete["backups_digest"]
        if not isinstance(expected_backups, dict) or set(expected_backups) != backups:
            raise LaunchError("invalid frontend publication backup proof")
        if no_backup:
            if before.get('publication_policy') != 'no-backup-v1':
                raise LaunchError('frontend publication preflight policy differs')
            _frontend_no_backup_provenance(state or STATE, operation, intent, before, complete)
        catalog[operation.name] = hashlib.sha256(_history_json({'intent': intent, 'completed': complete})).hexdigest()
        if seal is not None and operation.name in seal['payload']['records']:
            if (operation.name == seal['payload']['active_operation']
                    and complete['artifact_digest'] != seal['payload']['live_digest']):
                raise LaunchError('sealed active frontend binding differs')
            if seal['payload']['records'][operation.name] != catalog[operation.name]:
                raise LaunchError("sealed frontend audit differs")
            if operation.name != seal['payload']['active_operation'] and operation.name not in _force_operations:
                archived += 1
                continue
        if not verify_backups or operation.name not in _force_operations:
            continue
        verified += 1
        observed_backups = {
            name: _frontend_publication_backup_digest(operation / name, memo=backup_memo,
                                                      expected=expected_backups[name])
            for name in backups
        }
        if expected_backups != observed_backups:
            raise LaunchError("frontend publication backup hashes differ")
    if verify_backups and not set(_force_operations).issubset(catalog):
        raise LaunchError('requested backup recovery target is absent')
    if seal is not None and not set(seal['payload']['records']).issubset(catalog):
        raise LaunchError("sealed frontend audit disappeared")
    io_after = _release_io_snapshot()
    delta = {k: io_after[k] - io_before[k] for k in io_before} if io_before is not None and io_after is not None else None
    print(json.dumps(dict(stage='frontend-history', state='VERIFIED',
                          elapsed_seconds=round(time.monotonic() - started, 2),
                          archived_operations=archived, rollback_operations_verified=verified,
                          backup_integrity='verified' if verify_backups else 'not_checked',
                          io=delta, io_measurement='available' if delta is not None else 'unavailable')),
          file=sys.stderr, flush=True)
    return catalog


def assert_neo_wechat_history(state=None):
    """Durable bridge uncertainty blocks release/rotation even after reboot."""
    root = Path(state or STATE) / "neo-wechat"
    if not os.path.lexists(root):
        return
    secure_path(root, directory=True)
    if stat.S_IMODE(root.lstat().st_mode) != 0o700:
        raise LaunchError("bridge audit root must remain private")
    audits = list(root.iterdir())
    if len(audits) != 1:
        raise LaunchError("unexpected first-install bridge history")
    audit = audits[0]
    if re.fullmatch(r"[0-9a-f]{32}", audit.name) is None:
        raise LaunchError("unknown bridge operation identity")
    secure_path(audit, directory=True)
    if stat.S_IMODE(audit.lstat().st_mode) != 0o700:
        raise LaunchError("bridge audit must remain private")
    if {p.name for p in audit.iterdir()} != {"before.json", "intent.json", "lease.json", "verified.json", "completed.json"}:
        raise LaunchError("unfinished bridge installation; preserve evidence")
    values = {}
    for name in ("before", "intent", "lease", "verified", "completed"):
        path = audit / (name + ".json")
        secure_path(path, private=True)
        if path.stat().st_size > 262144:
            raise LaunchError("bridge audit exceeds bound")
        values[name] = _json(path.read_bytes())
    complete = values["completed"]
    expected = {"state", "publisher_sha", "production_sha", "operation_id", "evidence_sha256",
                "runtime_sha256", "proxy_gid", "activated", "nginx_included", "health_services_unchanged", "secrets_created"}
    if (not isinstance(complete, dict) or set(complete) != expected
            or complete != values["verified"] or complete["state"] != "INSTALLED_DORMANT"
            or complete["operation_id"] != audit.name
            or any(complete[k] is not False for k in ("activated", "nginx_included", "secrets_created"))
            or complete["health_services_unchanged"] is not True
            or type(complete["proxy_gid"]) is not int or complete["proxy_gid"] <= 0
            or any(re.fullmatch(r"[0-9a-f]{40}", str(complete[k])) is None for k in ("publisher_sha", "production_sha"))
            or any(re.fullmatch(r"[0-9a-f]{64}", str(complete[k])) is None for k in ("evidence_sha256", "runtime_sha256"))):
        raise LaunchError("unknown bridge terminal receipt")
    before_hash = hashlib.sha256(json.dumps(values["before"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if (before_hash != complete["evidence_sha256"]
            or values["intent"] != {"state": "INSTALL_STARTED", "evidence_sha256": before_hash,
                                    "operation_id": audit.name, "publisher_sha": complete["publisher_sha"]}
            or any(values["before"].get(k) != complete[k] for k in ("publisher_sha", "production_sha", "operation_id"))
            or set(values["lease"]) != {"identity"}
            or not isinstance(values["lease"]["identity"], list)
            or len(values["lease"]["identity"]) != 2
            or any(not isinstance(pair, list) or len(pair) != 2 or any(type(v) is not int or v < 0 for v in pair)
                   for pair in values["lease"]["identity"])):
        raise LaunchError("bridge evidence binding differs")


def assert_vision_model_history(state=None, *, pending_operation=None):
    """Unknown model-configuration outcomes block every existing launcher.

    Configuration success with model acceptance pending is an honest separate
    terminal state, not a paid-inference success receipt.
    """
    assert_neo_wechat_history(state)
    root = Path(state or STATE) / 'vision-models'
    if not os.path.lexists(root):
        return
    secure_path(root,directory=True)
    for audit in root.iterdir():
        if re.fullmatch(r'[0-9a-f]{32}',audit.name) is None:
            raise LaunchError('unknown vision configuration audit')
        secure_path(audit,directory=True)
        if audit.name == pending_operation:
            continue
        terminal = audit / ('rollback-completed.json' if os.path.lexists(audit / 'rollback-intent.json') else 'completed.json')
        if not os.path.lexists(terminal):
            raise LaunchError('unfinished vision configuration operation')
        secure_path(terminal,private=True)
        if terminal.stat().st_size > 32768:
            raise LaunchError('vision configuration receipt exceeds bound')
        value = _json(terminal.read_bytes())
        expected = 'CONFIG_ROLLED_BACK' if terminal.name == 'rollback-completed.json' else 'CONFIG_SUCCEEDED_PENDING_MODEL_ACCEPTANCE'
        if value.get('state') != expected or value.get('operation_id') != audit.name or value.get('model_requests') != 0:
            raise LaunchError('unknown vision configuration terminal receipt')
        if expected == 'CONFIG_SUCCEEDED_PENDING_MODEL_ACCEPTANCE' and value.get('model_acceptance') != 'PENDING':
            raise LaunchError('configuration cannot manufacture model acceptance')


EXAM_FAILED_SHA = 'a8cd1e7635eb697c0f0bc528382c98b3602893c3'
EXAM_COMPETING_RECORDS = (
    'exam-service-recovery-' + EXAM_FAILED_SHA,
    'exam-attempts-migrations/recovery-' + EXAM_FAILED_SHA,
    'exam-recovery-lease-retirement-' + EXAM_FAILED_SHA,
    'retained-candidate-closures/' + EXAM_FAILED_SHA,
    'retired/' + EXAM_FAILED_SHA,
)
EXAM_PROVIDER_REFRESH_ROOT = Path('/var/lib/reva-github-api/refresh')
EXAM_CREDENTIAL_ROOT = Path('/etc/reva-github-api')
EXAM_RETIRED_INSTALLATIONS = (
    Path('/etc/reva-release.retired-' + EXAM_FAILED_SHA),
    Path('/usr/local/lib/reva-release.retired-' + EXAM_FAILED_SHA),
)


def _exam_directory_names(path):
    """Bounded names only; absent directories are valid, unsafe parents are not."""
    path = Path(path)
    if not path.is_absolute():
        raise LaunchError('absolute exam inventory required')
    fields = ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode')
    identity = lambda info: tuple(getattr(info, key) for key in fields)
    chain = []
    missing = None
    for item in (*reversed(path.parents), path):
        try:
            before = item.lstat()
        except FileNotFoundError:
            missing = item
            break
        secure_path(item, directory=True)
        if identity(item.lstat()) != identity(before):
            raise LaunchError('exam inventory directory changed')
        chain.append((item, identity(before)))
    names = set()
    if missing is None:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            opened = os.fstat(fd)
            if identity(opened) != chain[-1][1]:
                raise LaunchError('exam inventory directory changed')
            generation = (opened.st_mtime_ns, opened.st_ctime_ns)
            with os.scandir(fd) as entries:
                for entry in entries:
                    names.add(entry.name)
                    if len(names) > 10000:
                        raise LaunchError('exam inventory exceeds bound')
            after = os.fstat(fd)
            if (identity(after) != chain[-1][1] or
                    (after.st_mtime_ns, after.st_ctime_ns) != generation):
                raise LaunchError('exam inventory directory changed')
        finally:
            os.close(fd)
    for item, expected in chain:
        secure_path(item, directory=True)
        if identity(item.lstat()) != expected:
            raise LaunchError('exam inventory ancestry changed')
    if missing is not None and os.path.lexists(missing):
        raise LaunchError('exam inventory appeared during inspection')
    return names


def assert_no_competing_exam_recovery(state=None):
    """Neither success text nor a missing volatile lease authorizes mixing attempts."""
    root = Path(STATE if state is None else state)
    try:
        paths = [*(root / name for name in EXAM_COMPETING_RECORDS), *EXAM_RETIRED_INSTALLATIONS]
        for path in paths:
            if path.name in _exam_directory_names(path.parent):
                raise LaunchError('competing exam recovery evidence exists')
        if any(name.startswith('exam-') for name in _exam_directory_names(EXAM_PROVIDER_REFRESH_ROOT)):
            raise LaunchError('competing exam recovery provider evidence exists')
        if any(name.startswith('credential.exam-') for name in _exam_directory_names(EXAM_CREDENTIAL_ROOT)):
            raise LaunchError('competing exam recovery credential artifact exists')
    except (OSError, ValueError):
        raise LaunchError('competing exam recovery inventory unavailable') from None


def assert_exam_recovery_history(state=None):
    # A separate reviewed closure must account for every incident side effect.
    # Presence alone blocks here; partial, malformed and completed attempts all
    # remain ineligible for ordinary publication even if /run lost its lease.
    root = Path(STATE if state is None else state)
    if any(os.path.lexists(root / name) for name in
           ('exam-a8-forward-acl-v1', 'exam-a8-read-credential-v1')):
        raise LaunchError('exam recovery requires independent closure')
    assert_no_competing_exam_recovery(root)


def assert_xiaoqihou_briefing_history(state=None):
    """Durable UNKNOWN admission survives loss of the volatile business lease.

    This validates the one fixed narrow attempt only. No history is repaired,
    no DB query is made, and a complete chain never grants retry authority.
    """
    root=Path(state or STATE)/'review-xiaoqihou-briefings'
    if not os.path.lexists(root):
        return
    attempt='xiaoqihou-fixed-briefing-v1'
    def directory(path):
        secure_path(path,directory=True)
        if stat.S_IMODE(path.stat().st_mode)!=0o700:
            raise LaunchError('private Xiaoqihou maintenance audit required')
    directory(root)
    if {p.name for p in root.iterdir()}!={attempt}:
        raise LaunchError('unknown Xiaoqihou maintenance attempt')
    record=root/attempt; directory(record)
    names={'intent.json','database-started.json','completed.json'}
    if {p.name for p in record.iterdir()}!=names:
        raise LaunchError('Xiaoqihou maintenance incomplete; no publication authority')
    raw={name:_read_private(record/name) for name in names}
    intent,start,end=(_json(raw[name]) for name in ('intent.json','database-started.json','completed.json'))
    if not all(isinstance(v,dict) for v in (intent,start,end)):
        raise LaunchError('invalid Xiaoqihou maintenance receipt')
    evidence=intent.get('evidence'); operator=intent.get('operator_sha'); lease=intent.get('lease'); parent=intent.get('parent_binding')
    hexdigest=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    is_hash=lambda value: isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value) is not None
    fields={'target_sha','fixture_sha256','legacy_closure_sha256','database_snapshot_sha256',
            'production_evidence_sha256','health_snapshot_sha256','demo_user_id','action','ordering_metadata_plan'}
    if (set(intent)!={'evidence','evidence_sha256','operator_sha','attempt','accept_xiaoqihou_briefing','lease','parent_binding'}
            or not isinstance(operator,str) or re.fullmatch('[a-f0-9]{40}',operator) is None
            or intent['attempt']!=attempt or intent['accept_xiaoqihou_briefing'] is not True
            or not isinstance(evidence,dict) or set(evidence)!=fields
            or evidence['target_sha']!='8f7d94696424f92ff57243edb906cd6d2dd14a3a'
            or evidence['fixture_sha256']!='40263013f3b91292e997343f535a45520ec9c28c979e5410530f0f11c0beed14'
            or evidence['action']!='INSERT_XIAOQIHOU_FIXED_BRIEFING_ONLY_V1'
            or evidence['ordering_metadata_plan']!={'action':'PRESERVE_ALL_EXISTING_ROWS','rows':[]}
            or type(evidence['demo_user_id']) is not int or evidence['demo_user_id']<1
            or any(not is_hash(evidence[k]) for k in ('legacy_closure_sha256','database_snapshot_sha256','production_evidence_sha256','health_snapshot_sha256'))
            or intent['evidence_sha256']!=hexdigest(evidence)
            or not isinstance(lease,dict) or set(lease)!={'token','identity'} or not is_hash(lease['token'])
            or not isinstance(lease['identity'],list) or len(lease['identity'])!=2
            or any(not isinstance(pair,list) or len(pair)!=2 or any(type(n) is not int or n<1 for n in pair) for pair in lease['identity'])
            or not isinstance(parent,dict) or set(parent)!={'pid','start_ticks','nonce_sha256'}
            or type(parent['pid']) is not int or parent['pid']<2
            or not isinstance(parent['start_ticks'],str) or not parent['start_ticks'].isdigit()
            or not is_hash(parent['nonce_sha256'])):
        raise LaunchError('Xiaoqihou maintenance intent binding differs')
    fingerprint=intent['evidence_sha256']
    if start!={'state':'DATABASE_ATTEMPT_STARTED','operator_sha':operator,'attempt':attempt,'evidence_sha256':fingerprint}:
        raise LaunchError('Xiaoqihou database attempt binding differs')
    result=end.get('result')
    if (not isinstance(result,dict) or set(result)!={'state','before_sha256','after_sha256'}
            or result['state']!='VERIFIED_BRIEFING_ONLY' or result['before_sha256']!=evidence['database_snapshot_sha256']
            or not is_hash(result['after_sha256'])
            or end!={'state':'BRIEFING_REPAIRED_ONLY','evidence_sha256':fingerprint,'result':result,
                     'original_outcome':'UNKNOWN','reset_authorized':False,'release_unblocked':False,'retry_authorized':False}):
        raise LaunchError('Xiaoqihou maintenance completion unverified')
    directory(root); directory(record)
    if ({p.name for p in root.iterdir()}!={attempt} or {p.name for p in record.iterdir()}!=names
            or any(_read_private(record/name)!=raw[name] for name in names)):
        raise LaunchError('Xiaoqihou maintenance history changed during read')


def assert_frontend_rebuild_history(state=None, *, pending_operation=None, pending_finalization_operation=None, pending_stopped_publication=None, pending_vision_operation=None, backup_memo=None, _seal_snapshot=None, pending_no_backup_finalization=None):
    """Independent frontend evidence must never count as backend success."""
    assert_exam_recovery_history(state)
    assert_xiaoqihou_briefing_history(state)
    assert_vision_model_history(state,pending_operation=pending_vision_operation)
    publication_options = dict(pending_stopped_publication=pending_stopped_publication, backup_memo=backup_memo,
                               pending_no_backup_finalization=pending_no_backup_finalization)
    if _seal_snapshot is not None:
        publication_options['_seal_snapshot'] = _seal_snapshot
    assert_frontend_publication_history(state, **publication_options)
    root = Path(state or STATE) / "frontend-rebuilds"
    closures = root.parent / "frontend-rebuild-closures"
    finalizations = root.parent / "frontend-finalizations"
    if pending_finalization_operation is not None and (
            pending_operation is not None or re.fullmatch(r"[0-9a-f]{32}", pending_finalization_operation) is None):
        raise LaunchError("invalid selected frontend finalization")
    if os.path.lexists(finalizations):
        secure_path(finalizations, directory=True)
        if stat.S_IMODE(finalizations.stat().st_mode) != 0o700:
            raise LaunchError("frontend finalization root must remain private")
        for finalized in finalizations.iterdir():
            if (re.fullmatch(r"[0-9a-f]{32}", finalized.name) is None
                    or not (root / finalized.name).is_dir()):
                raise LaunchError("orphan frontend finalization")
    if os.path.lexists(closures):
        secure_path(closures, directory=True)
        if stat.S_IMODE(closures.stat().st_mode) != 0o700:
            raise LaunchError("frontend closure root must remain private")
        for closure in closures.iterdir():
            if re.fullmatch(r"[0-9a-f]{32}", closure.name) is None or not (root / closure.name).is_dir():
                raise LaunchError("orphan frontend closure")
    if not os.path.lexists(root):
        if pending_finalization_operation is not None:
            raise LaunchError("selected frontend finalization is missing")
        return
    secure_path(root, directory=True)
    if stat.S_IMODE(root.lstat().st_mode) != 0o700:
        raise LaunchError("frontend audit root must remain private")
    expected_files = {"intent.json", "before.json", "build.log", "install-started.json",
                      "verified.json", "completed.json", "previous-next", "previous-node-modules"}
    selected_found = False
    for operation in root.iterdir():
        secure_path(operation, directory=True)
        if stat.S_IMODE(operation.lstat().st_mode) != 0o700:
            raise LaunchError("frontend operation must remain private")
        if re.fullmatch(r"[0-9a-f]{32}", operation.name) is None:
            raise LaunchError("invalid frontend operation")
        if operation.name == pending_finalization_operation:
            if os.path.lexists(closures / operation.name):
                raise LaunchError("conflicting frontend finalization")
            selected = finalizations / operation.name
            if os.path.lexists(selected):
                secure_path(selected, directory=True)
                if stat.S_IMODE(selected.stat().st_mode) != 0o700 or {p.name for p in selected.iterdir()} != {"intent.json"}:
                    raise LaunchError("unknown selected frontend finalization state")
                _read_private(selected / "intent.json")
            _load_frontend_finalizer().original_evidence(SimpleNamespace(**globals()), operation.name, state=root.parent)
            selected_found = True
            continue
        if os.path.lexists(finalizations / operation.name):
            if os.path.lexists(closures / operation.name):
                raise LaunchError("conflicting frontend closures")
            _load_frontend_finalizer().history_evidence(SimpleNamespace(**globals()), operation.name, state=root.parent)
            continue
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
    if pending_finalization_operation is not None and not selected_found:
        raise LaunchError("selected frontend finalization is missing")


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


def attest_documentation_main(policy, observed_main):
    """Execute only the policy-bound canonical gate, before any vendor claim."""
    source = STATE / "bootstrap" / policy["sha"] / "source"
    script = source / "scripts/trusted_release_gate.py"
    try:
        secure_path(script)
        secure_path(source / ".git/config")
        env = clean_environment(STATE)
        env.update(PATH="/usr/bin:/bin", HOME="/nonexistent", GIT_NO_REPLACE_OBJECTS="1",
                   GIT_CONFIG_SYSTEM="/dev/null")
        expected = subprocess.run([
            "/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
            "-C", str(source), "show", policy["sha"] + ":scripts/trusted_release_gate.py",
        ], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=True, timeout=30).stdout
        if script.read_bytes() != expected:
            raise LaunchError("documentation gate differs from reviewed source")
        subprocess.run([PYTHON, "-I", "-S", "-B", str(script), "--sha", policy["sha"],
                        "--workflow-sha", policy["sha"], "--observed-main", observed_main],
                       env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        raise LaunchError("canonical documentation attestation unavailable") from None


def attest_backend_ci(policy):
    """Fixed backend RPC derives eligibility from trusted production evidence."""
    script = STATE / "bootstrap" / policy["sha"] / "source/scripts/trusted_backend_admission.py"
    secure_path(script)
    subprocess.run([PYTHON, "-I", "-S", "-B", str(script), "--sha", policy["sha"]],
                   env=clean_environment(STATE), stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=True, timeout=300)


def attest_full_ci(policy):
    """Backend-only provisioning never authorizes native or OTA claims."""
    script = STATE / "bootstrap" / policy["sha"] / "source/scripts/trusted_release_gate.py"
    secure_path(script)
    subprocess.run([PYTHON, "-I", "-S", "-B", str(script), "--sha", policy["sha"],
                    "--workflow-sha", policy["sha"]],
                   env=clean_environment(STATE), stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=True, timeout=300)


def check_readiness(policy):
    """Read-only target probes before consuming any build/deployment claim."""
    assert_frontend_rebuild_history()
    assert_ota_history()
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
    match = re.fullmatch(r"([0-9a-f]{40})\trefs/heads/main\n?", result.stdout)
    if match is None:
        raise LaunchError("invalid remote main observation")
    if match[1] != policy["sha"]:
        attest_documentation_main(policy, match[1])
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
        assert_retained_history()
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
        assert_ota_history()
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


def _sync_business_lease_parent():
    """Sync the validated fixed lock parent without following arbitrary links."""
    _testflight_lease_parent()
    parent = (Path("/run/lock") if BUSINESS_LEASE == Path("/var/lock/health-app-release")
              else BUSINESS_LEASE.parent)
    before = parent.lstat()
    def identity(info):
        return info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid
    fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if identity(os.fstat(fd)) != identity(before):
            raise LaunchError("business lease parent changed before synchronization")
        os.fsync(fd)
        _testflight_lease_parent()
        if identity(parent.lstat()) != identity(before) or identity(os.fstat(fd)) != identity(before):
            raise LaunchError("business lease parent changed during synchronization")
    finally:
        os.close(fd)


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
        assert_retained_history()
        _assert_deployment_window(policy)
        if os.path.lexists(BUSINESS_LEASE):
            raise LaunchError("business release in progress")
        backend_state = read_status(policy["sha"], workspace)["state"]
        if backend_state not in {"READY", "SUCCEEDED"}:
            raise LaunchError("native continuation requires ready or successful backend state")
        check_readiness(policy)
        lease = _acquire_testflight_lease(workspace)
        proof = testflight_backend_proof(policy, lease=lease)
        _assert_testflight_lease(lease, workspace)
        if backend_state == "SUCCEEDED":
            if proof["production_sha"] != policy["sha"]:
                raise LaunchError("successful backend must match the live production revision")
            # Keep the existing backend lifecycle and its one-shot vendor claims.
            # A native-only binding would relabel this completed workspace.
            _native_binding(workspace, None)
            _assert_deployment_window(policy)
            if action == "check":
                return {"sha": policy["sha"], "state": "CHECKED"}
            if action == "build":
                return claim_build(policy, workspace)
            return claim_testflight(policy, workspace)
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


def validate_ota_archive(operation):
    """Prove an atomically archived lease belongs to this exact OTA claim."""
    operation = Path(operation)
    archive = operation / "released-lease"
    secure_path(archive, directory=True)
    lease = _json(_read_private(operation / "lease.json"))
    expected = {"token": lease["token"], "label": "testflight-check",
                "stage": str(STATE / operation.name), "started_at": lease["started_at"]}
    if {p.name for p in archive.iterdir()} != set(expected) or stat.S_IMODE(archive.stat().st_mode) != 0o700:
        raise LaunchError("invalid archived OTA lease")
    for name, value in expected.items():
        path = archive / name
        if _read_private(path) != (value + "\n").encode():
            raise LaunchError("archived OTA lease changed")
    if (not isinstance(lease.get("identity"), list) or len(lease["identity"]) != 4
            or any(type(v) is not int or v < 0 for v in lease["identity"])):
        raise LaunchError("invalid original OTA lease identity")


def _retained_module(sha):
    if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise LaunchError("invalid retained publisher identity")
    source = STATE / "bootstrap" / sha / "source"
    script = source / "scripts/trusted_retained_testflight.py"
    secure_path(script)
    if os.path.lexists(script.parent / "__pycache__"):
        raise LaunchError("cached retained helper forbidden")
    env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_NO_REPLACE_OBJECTS": "1"}
    expected = subprocess.run(["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-C", str(source),
                               "show", sha + ":scripts/trusted_retained_testflight.py"],
                              env=env, stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=30).stdout
    if script.read_bytes() != expected:
        raise LaunchError("retained helper differs from canonical source")
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("reviewed_retained_testflight", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.initialize(source, sha)
    return module


def assert_retained_history():
    root = STATE / "retained-testflight"
    if not os.path.lexists(root):
        return
    secure_path(root, directory=True)
    if stat.S_IMODE(root.stat().st_mode) != 0o700:
        raise LaunchError("invalid retained audit root")
    for operation in root.iterdir():
        secure_path(operation, directory=True)
        if operation.name != "63b61a31-058c-44e5-bb82-67727ca7d073":
            raise LaunchError("unknown retained artifact audit")
        intent = _json(_read_private(operation / "intent.json"))
        module = _retained_module(intent["request"]["sha"])
        module.validate_history(SimpleNamespace(**globals()), operation)


def retained_rpc(policy, action):
    module = _retained_module(policy["sha"])
    raw = sys.stdin.buffer.read(1000001)
    if len(raw) > 1000000:
        raise LaunchError("oversized retained input")
    result = subprocess.run([PYTHON, "-I", "-S", "-B", str(Path(module.__file__)),
                             "--sha", policy["sha"], "--action", action],
                            env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
                            input=raw, capture_output=True, check=True, timeout=600)
    value = _json(result.stdout)
    if action == "claim":
        if (not isinstance(value, dict) or set(value) != {"sha", "state", "claim_id"}
                or value["sha"] != policy["sha"] or value["state"] != "CLAIMED"
                or not isinstance(value["claim_id"], str) or re.fullmatch(r"[0-9a-f]{64}", value["claim_id"]) is None):
            raise LaunchError("invalid retained claim receipt")
    elif (not isinstance(value, dict) or set(value) != {"sha", "state", "build_id", "submission_id"}
          or value["sha"] != policy["sha"] or value["state"] != "UPLOADED" or value["build_id"] != module.BUILD_ID
          or not isinstance(value["submission_id"], str) or re.fullmatch(module.UUID, value["submission_id"]) is None):
        raise LaunchError("invalid retained completion receipt")
    return value


def assert_ota_history():
    """Every started OTA must finish before any later publisher or rotation."""
    assert_exam_recovery_history()
    assert_xiaoqihou_briefing_history()
    assert_retained_history()
    root = STATE / "ota"
    closures = STATE / "ota-preclaim-closures"
    if os.path.lexists(closures):
        secure_path(closures, directory=True)
        if stat.S_IMODE(closures.stat().st_mode) != 0o700:
            raise LaunchError("invalid OTA preclaim closure root")
        for closure in closures.iterdir():
            secure_path(closure, directory=True)
            if (re.fullmatch(r"[0-9a-f]{40}", closure.name) is None
                    or not os.path.lexists(root / closure.name)):
                raise LaunchError("orphan OTA preclaim closure")
    if not os.path.lexists(root):
        return
    secure_path(root, directory=True)
    for operation in root.iterdir():
        secure_path(operation, directory=True)
        if os.path.lexists(closures / operation.name):
            _load_ota_unclaimed_retirement().validate_closed_history(SimpleNamespace(**globals()), operation)
            continue
        if (re.fullmatch(r"[0-9a-f]{40}", operation.name) is None
                or stat.S_IMODE(operation.stat().st_mode) != 0o700
                or {p.name for p in operation.iterdir()} != {"intent.json", "lease.json", "claimed.json", "verified.json", "completed.json", "released-lease"}):
            raise LaunchError("unfinished OTA requires operator recovery")
        sha = operation.name
        intent = _json(_read_private(operation / "intent.json"))
        receipt = _json(_read_private(operation / "verified.json"))
        if (intent.get("sha") != sha or intent.get("channel") != "production" or intent.get("platform") != "ios"
                or not isinstance(receipt, dict) or set(receipt) != {"sha", "group_id", "update_id"}
                or receipt["sha"] != sha
                or any(not isinstance(receipt[k], str) or re.fullmatch(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", receipt[k]) is None for k in ("group_id", "update_id"))
                or _json(_read_private(operation / "claimed.json")) != {"sha": sha, "state": "CLAIMED"}
                or _json(_read_private(operation / "completed.json")) != {"sha": sha, "state": "SUCCEEDED",
                    "intent_sha256": hashlib.sha256(_read_private(operation / "intent.json")).hexdigest(),
                    "receipt_sha256": hashlib.sha256(_read_private(operation / "verified.json")).hexdigest()}):
            raise LaunchError("invalid OTA history")
        validate_ota_archive(operation)


def ota_rpc(policy, action):
    source = STATE / "bootstrap" / policy["sha"] / "source"
    script = source / "scripts/trusted_ota_server.py"
    secure_path(script)
    env = clean_environment(STATE)
    env.update(PATH="/usr/bin:/bin", HOME="/nonexistent", GIT_NO_REPLACE_OBJECTS="1", GIT_CONFIG_SYSTEM="/dev/null")
    expected = subprocess.run(["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-C", str(source), "show",
                               policy["sha"] + ":scripts/trusted_ota_server.py"], env=env,
                              stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=30).stdout
    if script.read_bytes() != expected:
        raise LaunchError("OTA helper differs from canonical source")
    raw = sys.stdin.buffer.read(1000001)
    if len(raw) > 1000000:
        raise LaunchError("oversized OTA input")
    result = subprocess.run([PYTHON, "-I", "-S", "-B", str(script), "--sha", policy["sha"], "--action", action],
                            env=env, input=raw, capture_output=True, check=True, timeout=600)
    expected_state = "CLAIMED" if action == "claim" else "SUCCEEDED"
    value = _json(result.stdout)
    if value != {"sha": policy["sha"], "state": expected_state}:
        raise LaunchError("invalid OTA helper receipt")
    return value


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
    deadline = f',expiry-time="{expiry_time(policy["expires_at"])}"' if policy["expires_at"] != 0 else ""
    expected = f'from="127.0.0.1",restrict{deadline} {public}'
    keys = _read_private(Path("/root/.ssh/authorized_keys")).decode().splitlines()
    matches = [line for line in keys if public.split()[1] in line]
    if matches != [expected]:
        raise LaunchError("loopback identity lacks exact local-only authorization")


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


def invitation_only_config(production):
    """This containment release must not enable public self-registration."""
    keys = {"AUTH_PHONE_SELF_REGISTRATION_ENABLED": "false",
            "REGISTRATION_INVITATION_ENFORCEMENT_ENABLED": "true",
            "REGISTRATION_INVITATION_ROLLOUT_ENABLED": "true"}
    lines = []
    for line in production.splitlines():
        if any(re.match(r"\s*(?:export\s+)?" + key + r"\s*=", line, re.IGNORECASE) for key in keys):
            continue
        lines.append(line)
    return "\n".join(lines) + "\n" + "".join(f"{key}={value}\n" for key, value in keys.items())


def validate_live_deployment_config(production):
    """Accept only complete reviewed admission profiles; never rewrite live env."""
    admission = ('AUTH_PHONE_SELF_REGISTRATION_ENABLED',
                 'REGISTRATION_INVITATION_ENFORCEMENT_ENABLED',
                 'REGISTRATION_INVITATION_ROLLOUT_ENABLED')
    required = {*admission, 'HEALTH_EVIDENCE_RUNTIME_ENABLED'}
    seen = {}
    for line in production.splitlines():
        assignment = re.fullmatch(r'\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)', line)
        if assignment is None or assignment[1] not in required:
            continue
        key, value = assignment.groups()
        parsed = re.fullmatch(r"(?:([a-z]+)|'([a-z]+)'|\"([a-z]+)\")\s*(?:#.*)?", value)
        if key in seen or parsed is None:
            raise LaunchError('live deployment safety flag is ambiguous or invalid')
        seen[key] = next(item for item in parsed.groups() if item is not None)
    if set(seen) != required:
        raise LaunchError('live deployment safety flags are incomplete')
    if (seen['HEALTH_EVIDENCE_RUNTIME_ENABLED'] != 'false'
            or tuple(seen[key] for key in admission) not in (
                ('false', 'true', 'true'), ('true', 'false', 'false'))):
        raise LaunchError('live deployment safety flag is ambiguous or invalid')


def deploy(policy, workspace, *, backend_ci=False):
    # Provisioning remains a separate privileged, reviewed installation step.
    _assert_deployment_window(policy)
    validate_loopback(policy)
    secure_path(Path(PYTHON))
    validate_live_deployment_config(read_production_env())
    workspace = Path(workspace)
    bindir = workspace / "bin"
    bindir.mkdir(mode=0o700)
    for command in ("ssh", "scp", "python3"):
        target = PYTHON if command == "python3" else f"/usr/bin/{command}"
        args = "" if command == "python3" else " -F /etc/reva-release/loopback.conf"
        wrapper = bindir / command
        _write_private(wrapper, f'#!/bin/sh\nexec {target}{args} "$@"\n'.encode())
        wrapper.chmod(0o700)
    env = clean_environment(workspace)
    env.update(DEPLOY_SOURCE_SHA=policy["sha"], DEPLOY_ENV_FILE='/opt/health-app/backend/.env',
               DEPLOY_SERVER='health', DEPLOY_PATH='/opt/health-app')
    source = workspace / "source"
    # Fresh CI/main attestation immediately before business deployment.
    if backend_ci:
        attest_backend_ci(policy)
    else:
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
        # OTA claim's byte-bound helper performs exact full CI under its original
        # locks before intent; duplicating it here wastes the same server quota.
        if command not in {"status", "check", "check-backend-v1", "run-backend-v1",
                           "claim-ota", "finish-ota", "finish-retained-testflight"}:
            attest_full_ci(policy)
        if command == "status":
            result = release_status(policy["sha"], workspace)
        elif command in {"check-testflight", "claim-testflight-build", "claim-testflight-upload"}:
            if command != "check-testflight":
                workspace.mkdir(mode=0o700, exist_ok=True)
            action = {"check-testflight": "check", "claim-testflight-build": "build",
                      "claim-testflight-upload": "upload"}[command]
            result = testflight_only(policy, workspace, action)
        elif command in {"claim-ota", "finish-ota"}:
            result = ota_rpc(policy, "claim" if command == "claim-ota" else "finish")
        elif command in {"claim-retained-testflight", "finish-retained-testflight"}:
            result = retained_rpc(policy, "claim" if command == "claim-retained-testflight" else "finish")
        elif command in {"check", "check-backend-v1"}:
            if command == "check-backend-v1":
                attest_backend_ci(policy)
            check_readiness(policy)
            result = {"sha": policy["sha"], "state": "CHECKED"}
        elif command == "claim-testflight":
            result = claim_testflight(policy, workspace)
        elif command == "claim-build":
            workspace.mkdir(mode=0o700, exist_ok=True)
            result = claim_build(policy, workspace)
        elif command == "run-backend-v1":
            # Reject missing/full-required CI before creating/consuming a claim.
            attest_backend_ci(policy)
            workspace.mkdir(mode=0o700, exist_ok=True)
            result = run_once(policy, workspace, lambda: prepare_source(policy, workspace),
                              lambda: deploy(policy, workspace, backend_ci=True))
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
