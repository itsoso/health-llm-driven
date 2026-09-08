"""Install/revoke/rotate one expiring identity; not a remote deployment tool.

TRUST PREREQUISITE: an operator must freshly clone the fixed public GitHub repo
at the reviewed SHA into /var/lib/reva-release/bootstrap/<sha>/source using
isolated root-owned Git. Execute this script there with system Python -I after
reviewing/pinning its bytes. Never upload a developer checkout or invoke a local
unreviewed bootstrap with production credentials. No source-path override exists.
"""

import argparse
import base64
import configparser
import datetime
import fcntl
import hashlib
import importlib.util
import itertools
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

CONFIG = Path("/etc/reva-release")
STATE = Path("/var/lib/reva-release")
INSTALLED = Path("/usr/local/lib/reva-release/trusted_release_server.py")
AUTHORIZED = Path("/root/.ssh/authorized_keys")
HOST_PUBLIC = Path("/etc/ssh/ssh_host_ed25519_key.pub")
BUSINESS_LEASE = Path("/var/lock/health-app-release")
ORIGIN = "https://github.com/itsoso/health-llm-driven.git"
ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0"}
# Read-only compatibility for the audited, never-started pre-rotation archive.
# The digest binds bytes, ownership, modes, device/inodes and absent consumption.
LEGACY_RETIREMENTS = {
    "fcbf01329dfeabbd22ef83aea56394e93abb9b00": "f2385e5dbc299aeab44f271c9de79b04da01b4f3db8f4e824ab85b24ff93b4ac",
}
# Audited implementation profile, not a release-SHA or log-digest exemption.
# This executor runs clone first, with an empty HOME and no checkout/hooks;
# its exact initial-clone failure transcript cannot follow repository execution.
LEGACY_CLONE_EXECUTORS = {
    "9625c8eb15032a5e82cb5aed5a8617723ce1dd57eb0922933055fac70ed2abd7",
}
PROC = Path("/proc")


class BootstrapError(Exception):
    """Sanitized operator-facing error."""


def secure(path, *, private=False):
    path = Path(path)
    for item in [*reversed(path.parents), path]:
        info = item.lstat()
        if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
            raise BootstrapError("unsafe root-owned installation path")
        if item != path and not stat.S_ISDIR(info.st_mode):
            raise BootstrapError("unsafe parent directory")
        if item == path and (not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)) or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)):
            raise BootstrapError("unsafe installation object")
    if private and (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600):
        raise BootstrapError("private configuration must be a regular 0600 file")


def validate_install(sha, expiry, public, *, now):
    if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise BootstrapError("exact reviewed SHA required")
    if type(expiry) is not int or not now < expiry <= now + 28800:
        raise BootstrapError("authorization must expire within eight hours")
    if not isinstance(public, str) or re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/]+={0,2}", public) is None:
        raise BootstrapError("a single uncommented ed25519 public key is required")
    encoded = public.split(" ")[1]
    try:
        wire = base64.b64decode(encoded, validate=True)
    except ValueError:
        raise BootstrapError("invalid public key encoding") from None
    prefix = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"
    if len(wire) != len(prefix) + 32 or not wire.startswith(prefix) or base64.b64encode(wire).decode() != encoded:
        raise BootstrapError("invalid ed25519 SSH public-key wire format")


def use_system_timezone():
    os.environ.pop("TZ", None)
    time.tzset()


def expiry_time(expiry):
    # OpenSSH 8.9 parses expiry-time in the server's system timezone, without Z.
    use_system_timezone()
    stamp = datetime.datetime.fromtimestamp(expiry).strftime("%Y%m%d%H%M%S")  # noqa: DTZ006 -- sshd requires system-local wall time.
    if time.mktime(time.strptime(stamp, "%Y%m%d%H%M%S")) != expiry:
        raise BootstrapError("system-local expiry cannot preserve the absolute deadline")
    return stamp


def key_lines(expiry, cloud, loopback):
    stamp = expiry_time(expiry)
    return (
        f'command="/usr/bin/python3 -I /usr/local/lib/reva-release/trusted_release_server.py",restrict,expiry-time="{stamp}" {cloud}',
        f'from="127.0.0.1",restrict,expiry-time="{stamp}" {loopback}',
    )


def _run(args, *, capture=False):
    return subprocess.run(args, env=ENV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE if capture else subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True, check=True, timeout=90)


def reviewed_source(sha):
    source = STATE / "bootstrap" / sha / "source"
    if Path(__file__).absolute() != source / "scripts/bootstrap_trusted_release.py":
        raise BootstrapError("bootstrap must run from fixed fresh canonical root staging")
    source = canonical_source(sha)
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("reviewed_release_server", source / "scripts/trusted_release_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return source, module


def canonical_source(sha):
    source = STATE / "bootstrap" / sha / "source"
    for path in (Path(__file__).absolute(), source / ".git/config", source / "scripts/trusted_release_gate.py", source / "scripts/trusted_release_server.py"):
        secure(path)
    if (source / ".git/commondir").exists():
        raise BootstrapError("shared or caller-controlled git directories forbidden")
    config = configparser.ConfigParser(interpolation=None)
    config.read(source / ".git/config")
    allowed = {"core": {"repositoryformatversion", "filemode", "bare", "logallrefupdates", "ignorecase", "precomposeunicode"}, 'remote "origin"': {"url", "fetch"}, 'branch "main"': {"remote", "merge"}}
    if any(section not in allowed or set(config[section]) - allowed[section] for section in config.sections()) or config.get('remote "origin"', "url", fallback="") != ORIGIN:
        raise BootstrapError("noncanonical source Git configuration")
    git = ["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C", str(source)]
    if _run(git + ["rev-parse", "HEAD"], capture=True).stdout.strip() != sha or _run(git + ["status", "--porcelain=v1", "--untracked-files=all"], capture=True).stdout:
        raise BootstrapError("source must be clean at the exact reviewed SHA")
    return source


def _sync_parent(path):
    fd = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    _sync_parent(path)


def _replace_authorized(data):
    secure(AUTHORIZED, private=True)
    original = AUTHORIZED.stat()
    staged = AUTHORIZED.with_name("authorized_keys.reva-new")
    _write(staged, data)
    os.chown(staged, original.st_uid, original.st_gid)
    os.chmod(staged, stat.S_IMODE(original.st_mode))
    os.replace(staged, AUTHORIZED)
    _sync_parent(AUTHORIZED)


def _assert_installable(sha):
    if os.path.lexists(CONFIG) or os.path.lexists(INSTALLED.parent):
        raise BootstrapError("existing release authorization/installation must not be overwritten")
    secure(STATE)
    secure(CONFIG.parent)
    secure(INSTALLED.parent.parent)
    secure(AUTHORIZED, private=True)
    history = _retired_history()
    if history:
        raise BootstrapError("retired lifecycle requires explicit rotation, not reinstall")
    _assert_fresh_sha(sha, history)
    _assert_known_activity(history)


def install(sha, expiry, public):
    validate_install(sha, expiry, public, now=int(time.time()))
    _assert_installable(sha)
    source, server = reviewed_source(sha)
    _run(["/usr/bin/python3.12", "-I", str(source / "scripts/trusted_release_gate.py"), "--sha", sha, "--workflow-sha", sha])
    fd = os.open(STATE / "launcher.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        secure(STATE / "launcher.lock", private=True)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _assert_installable(sha)
        return _install_locked(sha, expiry, public, source, server)
    finally:
        os.close(fd)


def _installation_inputs(sha, expiry, public):
    validate_install(sha, expiry, public, now=int(time.time()))
    secure(AUTHORIZED, private=True)
    original = AUTHORIZED.read_bytes()
    if public.split()[1] in original.decode():
        raise BootstrapError("cloud key already authorized; refusing ambiguous identity")
    secure(HOST_PUBLIC)
    host = " ".join(HOST_PUBLIC.read_text().split()[:2])
    validate_install(sha, expiry, host, now=int(time.time()))
    return original, host


def _install_locked(sha, expiry, public, source, server, *, retired_keys=()):
    original, host = _installation_inputs(sha, expiry, public)
    CONFIG.mkdir(mode=0o700)
    _sync_parent(CONFIG)
    INSTALLED.parent.mkdir(mode=0o700)
    _sync_parent(INSTALLED.parent)
    code = (source / "scripts/trusted_release_server.py").read_bytes()
    _write(INSTALLED, code)
    _write(CONFIG / "cloud.pub", public.encode())
    _run(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "", "-f", str(CONFIG / "loopback.key")])
    loopback = (CONFIG / "loopback.key.pub").read_text().strip()
    validate_install(sha, expiry, loopback, now=int(time.time()))
    if loopback in retired_keys or loopback == public:
        raise BootstrapError("generated loopback identity is not fresh")
    os.rename(CONFIG / "loopback.key.pub", CONFIG / "loopback.pub")
    for name in ("loopback.key", "loopback.pub"):
        os.chmod(CONFIG / name, 0o600)
    _write(CONFIG / "known_hosts", f"127.0.0.1 {host}\n".encode())
    _write(CONFIG / "loopback.conf", server.loopback_config().encode())
    _write(CONFIG / "authorized-release.json", json.dumps({"sha": sha, "expires_at": expiry, "executor_sha256": hashlib.sha256(code).hexdigest()}).encode())
    _run(["/usr/bin/ssh-keygen", "-l", "-f", str(CONFIG / "cloud.pub")])
    cloud_line, local_line = key_lines(expiry, public, loopback)
    _replace_authorized(original + (b"" if not original or original.endswith(b"\n") else b"\n") + f"{cloud_line}\n{local_line}\n".encode())
    return {"sha": sha, "state": "INSTALLED"}


def _read_json(path):
    secure(path, private=True)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise BootstrapError("duplicate audit field")
            result[key] = value
        return result
    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def _inventory(directory, names):
    secure(directory)
    if not directory.is_dir() or stat.S_IMODE(directory.lstat().st_mode) != 0o700:
        raise BootstrapError("retirement requires a private directory")
    if {p.name for p in directory.iterdir()} != set(names):
        raise BootstrapError("unexpected retirement directory inventory")
    result = {}
    for path in [directory, *(directory / name for name in sorted(names))]:
        secure(path, private=path != directory)
        info = path.lstat()
        result[path.name if path != directory else "."] = {
            "uid": info.st_uid, "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode),
            "inode": info.st_ino, "device": info.st_dev,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path != directory else None,
        }
    return result


def _workspace_evidence(sha):
    workspace = STATE / sha
    if os.path.lexists(STATE / "recoveries" / sha):
        return _recovered_preparation_evidence(sha)
    if not os.path.lexists(workspace):
        return {"state": "NEVER_STARTED", "inventory": None}
    secure(workspace)
    names = {p.name for p in workspace.iterdir()}
    if not names:
        return {"state": "NEVER_STARTED", "inventory": []}
    if "completed.json" in names and _read_json(workspace / "completed.json") == {"sha": sha, "state": "PREPARATION_FAILED"}:
        return _preparation_failure_evidence(sha, workspace, names)
    allowed = {"started.json", "completed.json", "build-started.json", "native-started.json",
               "build.lock", "source", "home", "bin", "deployment.env", "preparation.log", "deployment.log",
               "preparation-started.json", "prepared.json", "deployment-started.json", "clone-attempts", "review-resets"}
    if not names <= allowed or not {"started.json", "completed.json"} <= names:
        raise BootstrapError("backend termination unproven; retirement forbidden")
    phases = {"preparation-started.json", "prepared.json", "deployment-started.json"}
    if names & phases and not phases <= names:
        raise BootstrapError("incomplete successful release phase evidence")
    receipts = {}
    for name in sorted(names):
        path = workspace / name
        secure(path, private=name not in {"source", "home", "bin", "clone-attempts", "review-resets"})
        if name.endswith(".json"):
            states = {"completed.json": "SUCCEEDED", "preparation-started.json": "PREPARING",
                      "prepared.json": "PREPARED", "deployment-started.json": "DEPLOYING"}
            expected = {"sha": sha, "state": states.get(name, "STARTED")}
            if name == "preparation-started.json":
                expected["executor_sha256"] = hashlib.sha256((canonical_source(sha) / "scripts/trusted_release_server.py").read_bytes()).hexdigest()
            if _read_json(path) != expected:
                raise BootstrapError("backend termination unproven; retirement forbidden")
            receipts[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if "review-resets" in names:
        receipts["review-resets"] = _review_reset_evidence(sha)
    return {"state": "SUCCEEDED", "inventory": sorted(names), "receipts": receipts}


def _review_reset_evidence(sha):
    root = STATE / sha / "review-resets"
    if not os.path.lexists(root):
        return None
    secure(root)
    if not root.is_dir() or stat.S_IMODE(root.lstat().st_mode) != 0o700:
        raise BootstrapError("review reset evidence must be a private directory")
    operations = list(itertools.islice(root.iterdir(), 1001))
    if len(operations) > 1000:
        raise BootstrapError("review reset inspection bound exceeded")
    result = {}
    for operation in sorted(operations):
        if re.fullmatch(r"[0-9a-f]{32}", operation.name) is None:
            raise BootstrapError("unknown review reset operation")
        inventory = _inventory(operation, {"started.json", "completed.json"})
        for name, state in (("started.json", "STARTED"), ("completed.json", "SUCCEEDED")):
            if _read_json(operation / name) != {"sha": sha, "operation_id": operation.name, "state": state}:
                raise BootstrapError("review reset termination unproven")
        result[operation.name] = inventory
    return result


def _preparation_failure_evidence(sha, workspace, names):
    """Read-only proof for the phase-aware protocol, never legacy inference."""
    required = {"started.json", "preparation-started.json", "completed.json"}
    allowed = required | {"build.lock", "home", "source", "preparation.log", "clone-attempts"}
    if not required <= names <= allowed:
        raise BootstrapError("preparation-only termination unproven")
    digest = hashlib.sha256((canonical_source(sha) / "scripts/trusted_release_server.py").read_bytes()).hexdigest()
    expected = {
        "started.json": {"sha": sha, "state": "STARTED"},
        "preparation-started.json": {"sha": sha, "state": "PREPARING", "executor_sha256": digest},
        "completed.json": {"sha": sha, "state": "PREPARATION_FAILED"},
    }
    receipts = {}
    for name in sorted(names):
        path = workspace / name
        secure(path, private=name not in {"home", "source", "clone-attempts"})
        if name in {"home", "source", "clone-attempts"} and (
                not path.is_dir() or stat.S_IMODE(path.lstat().st_mode) != 0o700):
            raise BootstrapError("preparation directories must be private directories")
        if name in expected:
            if _read_json(path) != expected[name]:
                raise BootstrapError("preparation phase proof differs from canonical executor")
            receipts[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"state": "PREPARATION_FAILED", "inventory": sorted(names), "receipts": receipts,
            "manifest": _preparation_manifest(workspace)}


def _preparation_manifest(workspace):
    # Bound the entire retained tree without following links or emitting log data.
    pending, count, size, digest = [workspace], 0, 0, hashlib.sha256()
    while pending:
        path = pending.pop()
        count += 1
        relative = path.relative_to(workspace)
        if count > 25000 or len(relative.parts) > 64:
            raise BootstrapError("preparation evidence exceeds inspection bound")
        secure(path)
        info = path.lstat()
        content = None
        if stat.S_ISDIR(info.st_mode):
            entries = list(itertools.islice(path.iterdir(), 25001))
            if len(entries) > 25000:
                raise BootstrapError("preparation directory exceeds inspection bound")
            pending.extend(sorted(entries, reverse=True))
        elif stat.S_ISREG(info.st_mode):
            size += info.st_size
            if size > 1024 * 1024 * 1024:
                raise BootstrapError("preparation bytes exceed inspection bound")
            file_hash = hashlib.sha256()
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                remaining = info.st_size
                while remaining:
                    data = stream.read(min(remaining, 65536))
                    if not data:
                        raise BootstrapError("preparation file changed during inspection")
                    file_hash.update(data)
                    remaining -= len(data)
                after = os.fstat(stream.fileno())
            if (after.st_ino, after.st_dev, after.st_size, after.st_mtime_ns) != (
                    info.st_ino, info.st_dev, info.st_size, info.st_mtime_ns):
                raise BootstrapError("preparation file changed during inspection")
            content = file_hash.hexdigest()
        else:
            raise BootstrapError("unsupported preparation evidence type")
        digest.update(json.dumps([str(relative), info.st_uid, info.st_gid, info.st_mode,
                                 info.st_ino, info.st_dev, info.st_size, info.st_mtime_ns,
                                 content], separators=(",", ":")).encode() + b"\n")
    return {"sha256": digest.hexdigest(), "entries": count, "bytes": size}


def _acquire_existing_build_lock(sha):
    path = STATE / sha / "build.lock"
    if not os.path.lexists(path):
        return None
    secure(path, private=True)
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _archives(sha):
    return (CONFIG.with_name(CONFIG.name + ".retired-" + sha),
            INSTALLED.parent.with_name(INSTALLED.parent.name + ".retired-" + sha))


def _installation_evidence(sha, config, library):
    config_files = {"known_hosts", "loopback.conf", "authorized-release.json", "loopback.pub", "cloud.pub"}
    inventory = {"config": _inventory(config, config_files),
                 "library": _inventory(library, {INSTALLED.name})}
    policy = _read_json(config / "authorized-release.json")
    if (not isinstance(policy, dict) or set(policy) != {"sha", "expires_at", "executor_sha256"}
            or policy["sha"] != sha or type(policy["expires_at"]) is not int):
        raise BootstrapError("retire SHA does not match managed authorization")
    # Read the old canonical code as data only. Only the new reviewed bootstrap
    # and server module may execute during rotation.
    old_source = canonical_source(sha)
    digest = hashlib.sha256((old_source / "scripts/trusted_release_server.py").read_bytes()).hexdigest()
    if policy["executor_sha256"] != digest or inventory["library"][INSTALLED.name]["sha256"] != digest:
        raise BootstrapError("old executor differs from exact canonical source")
    secure(AUTHORIZED, private=True)
    authorized = AUTHORIZED.read_text()
    for name in ("cloud.pub", "loopback.pub"):
        public = (config / name).read_text().strip()
        validate_install(sha, 1, public, now=0)
        if public.split()[1] in authorized:
            raise BootstrapError("old identity is still authorized")
    return inventory


def _retired_history():
    root = STATE / "retired"
    if not os.path.lexists(root):
        if LEGACY_RETIREMENTS:
            raise BootstrapError("pinned legacy retirement is missing")
        return {}
    secure(root)
    if not set(LEGACY_RETIREMENTS) <= {p.name for p in root.iterdir()}:
        raise BootstrapError("pinned legacy retirement is missing")
    history = {}
    for entry in root.iterdir():
        if re.fullmatch(r"[0-9a-f]{40}", entry.name) is None:
            raise BootstrapError("unknown retirement audit")
        if entry.name in LEGACY_RETIREMENTS:
            secure(entry)
            if (not entry.is_dir() or stat.S_IMODE(entry.lstat().st_mode) != 0o700
                    or {p.name for p in entry.iterdir()} != {"config", "executor"}):
                raise BootstrapError("unexpected legacy retirement inventory")
            evidence = {"installation": _installation_evidence(entry.name, entry / "config", entry / "executor"),
                        "workspace": _workspace_evidence(entry.name)}
            digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if (evidence["workspace"] != {"state": "NEVER_STARTED", "inventory": None}
                    or digest != LEGACY_RETIREMENTS[entry.name]):
                raise BootstrapError("legacy retirement evidence changed")
            history[entry.name] = {"format": "pinned-legacy", **evidence}
            continue
        _inventory(entry, {"intent.json", "completed.json"})
        intent = _read_json(entry / "intent.json")
        if (not isinstance(intent, dict) or set(intent) != {"old_sha", "new_sha", "installation", "workspace"}
                or intent["old_sha"] != entry.name or not isinstance(intent["new_sha"], str)
                or re.fullmatch(r"[0-9a-f]{40}", intent["new_sha"]) is None
                or intent["new_sha"] == entry.name
                or _read_json(entry / "completed.json") != {"new_sha": intent["new_sha"], "state": "RETIRED", "old_sha": entry.name}):
            raise BootstrapError("incomplete or invalid retirement audit")
        if (_installation_evidence(entry.name, *_archives(entry.name)) != intent["installation"]
                or _workspace_evidence(entry.name) != intent["workspace"]):
            raise BootstrapError("retired installation or consumption evidence changed")
        history[entry.name] = intent
    return history


def _retired_config(sha, evidence):
    if evidence.get("format") == "pinned-legacy":
        return STATE / "retired" / sha / "config"
    return _archives(sha)[0]


def _assert_fresh_sha(sha, history):
    if (os.path.lexists(STATE / sha) or sha in history
            or sha in LEGACY_RETIREMENTS
            or any(item.get("new_sha") == sha for item in history.values())
            or any(os.path.lexists(path) for path in _archives(sha))):
        raise BootstrapError("release SHA already used; retry forbidden")


def _assert_known_activity(history, old_sha=None):
    for path in STATE.iterdir():
        if re.fullmatch(r"[0-9a-f]{40}", path.name) and path.name not in history and path.name != old_sha:
            raise BootstrapError("existing release activity requires operator review")


def _assert_idle():
    if os.path.lexists(BUSINESS_LEASE):
        raise BootstrapError("business release lease exists; retirement forbidden")
    result = _run(["/usr/bin/ps", "-e", "-ww", "-o", "pid=", "-o", "args="], capture=True)
    seen = set()
    for line in result.stdout.splitlines():
        fields = line.split(None, 1)
        if len(fields) != 2 or not fields[0].isdigit() or int(fields[0]) in seen:
            raise BootstrapError("release process termination is uncertain")
        pid, command = int(fields[0]), fields[1]
        seen.add(pid)
        if pid == os.getpid():
            continue
        if any(token in command for token in (
                "reva-release", "trusted_release_server.py", "bootstrap_trusted_release.py", "trusted_review_reset.py", "deploy.sh",
                "health-app-backup-preflight", "rollback_release", "runtime_state_release_transaction")):
            raise BootstrapError("release process still present; retirement forbidden")
    if os.getpid() not in seen or os.path.lexists(BUSINESS_LEASE):
        raise BootstrapError("release process/lease termination is uncertain")


def rotate(old_sha, sha, expiry, public):
    validate_install(sha, expiry, public, now=int(time.time()))
    if not isinstance(old_sha, str) or re.fullmatch(r"[0-9a-f]{40}", old_sha) is None or old_sha == sha:
        raise BootstrapError("distinct exact old and new reviewed SHAs required")
    source, server = reviewed_source(sha)
    _run(["/usr/bin/python3.12", "-I", str(source / "scripts/trusted_release_gate.py"), "--sha", sha, "--workflow-sha", sha])
    secure(STATE)
    # Rotation may not recreate the global lock inode of an existing install.
    secure(STATE / "launcher.lock", private=True)
    fd = os.open(STATE / "launcher.lock", os.O_RDWR | os.O_NOFOLLOW)
    build_fd = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build_fd = _acquire_existing_build_lock(old_sha)
        history = _retired_history()
        _assert_fresh_sha(sha, history)
        _assert_known_activity(history, old_sha)
        archive_config, archive_library = _archives(old_sha)
        if old_sha in history or any(os.path.lexists(path) for path in (archive_config, archive_library)):
            raise BootstrapError("old retirement already attempted")
        installation = _installation_evidence(old_sha, CONFIG, INSTALLED.parent)
        workspace = _workspace_evidence(old_sha)
        retired_keys = {(config / name).read_text().strip()
                        for config in [CONFIG, *(_retired_config(old, item) for old, item in history.items())]
                        for name in ("cloud.pub", "loopback.pub")}
        if public in retired_keys:
            raise BootstrapError("rotation requires a new identity")
        _installation_inputs(sha, expiry, public)
        _assert_idle()
        # Intent is durable before either rename. No cleanup, rollback, or
        # automatic resume: a partial rotation remains a blocking audit record.
        root = STATE / "retired"
        if not root.exists():
            root.mkdir(mode=0o700)
            _sync_parent(root)
        record = root / old_sha
        record.mkdir(mode=0o700)
        _sync_parent(record)
        _write(record / "intent.json", json.dumps({"old_sha": old_sha, "new_sha": sha,
               "installation": installation, "workspace": workspace}, sort_keys=True).encode())
        _assert_idle()
        for current, archive in ((CONFIG, archive_config), (INSTALLED.parent, archive_library)):
            os.rename(current, archive)
            _sync_parent(archive)
        if (_installation_evidence(old_sha, archive_config, archive_library) != installation
                or _workspace_evidence(old_sha) != workspace):
            raise BootstrapError("retirement evidence changed during rotation")
        # This certifies retirement, not installation success. Reserve the new
        # SHA permanently, and finish audit writes before publishing any key.
        _write(record / "completed.json", json.dumps({"old_sha": old_sha, "new_sha": sha,
               "state": "RETIRED"}, sort_keys=True).encode())
        result = _install_locked(sha, expiry, public, source, server, retired_keys=retired_keys)
        result["retired_sha"] = old_sha
        return result
    finally:
        if build_fd is not None:
            os.close(build_fd)
        os.close(fd)


def revoke(sha):
    if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise BootstrapError("exact managed SHA required")
    # Revocation does not need a green *current* main: the fixed reviewed local
    # staging remains sufficient to remove its own old, expired authorization.
    reviewed_source(sha)
    secure(STATE)
    fd = os.open(STATE / "launcher.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    build_fd = None
    try:
        secure(STATE / "launcher.lock", private=True)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build_fd = _acquire_existing_build_lock(sha)
        return _revoke_locked(sha)
    finally:
        if build_fd is not None:
            os.close(build_fd)
        os.close(fd)


def _revoke_locked(sha):
    secure(CONFIG / "authorized-release.json", private=True)
    policy = json.loads((CONFIG / "authorized-release.json").read_bytes())
    if set(policy) != {"sha", "expires_at", "executor_sha256"} or policy["sha"] != sha or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise BootstrapError("revoke SHA does not match managed authorization")
    _assert_backend_terminated_or_unstarted(sha)
    public = []
    for name in ("cloud.pub", "loopback.pub"):
        secure(CONFIG / name, private=True)
        public.append((CONFIG / name).read_text().strip())
    expected = key_lines(policy["expires_at"], *public)
    secure(AUTHORIZED, private=True)
    lines = AUTHORIZED.read_bytes().splitlines(keepends=True)
    for line in lines:
        if any(key.split()[1] in line.decode() for key in public) and line.decode().rstrip("\r\n") not in expected:
            raise BootstrapError("managed key options changed; operator review required")
    retained = [line for line in lines if line.decode().rstrip("\r\n") not in expected]
    if retained != lines:
        _replace_authorized(b"".join(retained))
    return {"sha": sha, "state": "REVOKED"}


def _assert_backend_terminated_or_unstarted(sha):
    # An idle launcher flock does not prove that a timed-out deployment process
    # group or remote release lease ended. Never remove its recovery identity.
    workspace = STATE / sha
    _review_reset_evidence(sha)
    if os.path.lexists(STATE / "recoveries" / sha):
        _recovered_preparation_evidence(sha)
        _assert_idle()
        return
    if not os.path.lexists(workspace):
        return
    secure(workspace)
    if not workspace.is_dir():
        raise BootstrapError("backend termination evidence is invalid")
    started, completed = workspace / "started.json", workspace / "completed.json"
    has_started, has_completed = os.path.lexists(started), os.path.lexists(completed)
    if not has_started and not has_completed:
        return
    if not has_started or not has_completed:
        raise BootstrapError("backend termination unproven; retain recovery authorization")
    for path in (started, completed):
        secure(path, private=True)
    if _read_json(completed) == {"sha": sha, "state": "PREPARATION_FAILED"}:
        # Explicit revocation is still an operator action, never an RPC retry.
        secure(INSTALLED, private=True)
        policy = _read_json(CONFIG / "authorized-release.json")
        digest = hashlib.sha256((canonical_source(sha) / "scripts/trusted_release_server.py").read_bytes()).hexdigest()
        if policy.get("executor_sha256") != digest or hashlib.sha256(INSTALLED.read_bytes()).hexdigest() != digest:
            raise BootstrapError("preparation executor binding differs from installation")
        _workspace_evidence(sha)
        _assert_idle()
        return
    if (
        _read_json(started) != {"sha": sha, "state": "STARTED"}
        or _read_json(completed) != {"sha": sha, "state": "SUCCEEDED"}
    ):
        raise BootstrapError("backend termination unproven; retain recovery authorization")


def _digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _legacy_clone_evidence(sha):
    source = canonical_source(sha)
    digest = hashlib.sha256((source / "scripts/trusted_release_server.py").read_bytes()).hexdigest()
    if digest not in LEGACY_CLONE_EXECUTORS:
        raise BootstrapError("unknown historical executor implementation")
    workspace = STATE / sha
    secure(workspace)
    if (not workspace.is_dir() or stat.S_IMODE(workspace.stat().st_mode) != 0o700
            or {p.name for p in workspace.iterdir()} != {
                "started.json", "completed.json", "build.lock", "home", "preparation.log"}):
        raise BootstrapError("historical clone-only inventory unproven")
    for name, state in (("started.json", "STARTED"), ("completed.json", "NEEDS_OPERATOR")):
        if _read_json(workspace / name) != {"sha": sha, "state": state}:
            raise BootstrapError("historical failure receipt differs")
    home = workspace / "home"
    secure(home)
    if not home.is_dir() or stat.S_IMODE(home.stat().st_mode) != 0o700 or list(home.iterdir()):
        raise BootstrapError("initial clone HOME is not empty/private")
    log = workspace / "preparation.log"
    secure(log, private=True)
    expected = (
        f"Cloning into '{workspace}/source'...\n"
        "error: RPC failed; curl 28 Operation too slow. Less than 1024 bytes/sec transferred the last 30 seconds\n"
        "fatal: early EOF\nfatal: fetch-pack: invalid index-pack output\n"
    ).encode()
    if log.stat().st_size != len(expected) or log.read_bytes() != expected:
        raise BootstrapError("initial clone terminal transcript unproven")
    secure(workspace / "build.lock", private=True)
    if (workspace / "build.lock").stat().st_size:
        raise BootstrapError("unexpected build lock content")
    return {"executor_sha256": digest, "manifest": _preparation_manifest(workspace)}


def _recovery_process_proof():
    # A detached Git HTTP/index-pack helper need not name the release in argv.
    # Inspect cwd and environment too; never output process data or credentials.
    entries = list(itertools.islice(PROC.iterdir(), 100001))
    if len(entries) > 100000 or not (PROC / str(os.getpid())).is_dir():
        raise BootstrapError("process inventory unavailable")
    needles = (b"reva-release", b"deploy.sh", b"health-app-backup-preflight",
               b"rollback_release", b"runtime_state_release_transaction")
    for process in entries:
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            identity = (process / "stat").read_bytes()
            chunks = []
            for name in ("cmdline", "environ"):
                with (process / name).open("rb") as stream:
                    chunk = stream.read(1048577)
                if len(chunk) > 1048576:
                    raise BootstrapError("process inspection bound exceeded")
                chunks.append(chunk)
            if chunks[0]:  # Kernel threads have no cwd or user environment.
                chunks.append(os.fsencode(os.readlink(process / "cwd")))
                chunks.append(os.fsencode(os.readlink(process / "exe")))
            after = (process / "stat").read_bytes()
            # comm can contain spaces/parentheses. Fields after its final ')'
            # bind PID reuse via starttime and preserve parent/group/session.
            before_fields, after_fields = identity.rsplit(b")", 1)[-1].split(), after.rsplit(b")", 1)[-1].split()
            if (len(before_fields) < 20 or len(after_fields) < 20
                    or before_fields[1:4] != after_fields[1:4]
                    or before_fields[19] != after_fields[19]):
                raise BootstrapError("process identity changed during inspection")
            if any(needle in chunk for chunk in chunks for needle in needles):
                raise BootstrapError("release descendant still present")
        except FileNotFoundError:
            if process.exists():
                raise BootstrapError("live process cannot be inspected") from None


def _recovery_toolchain_proof():
    # Existing root-managed OS is the trust boundary; do not execute old repo
    # code or claim to reconstruct the machine's historical package contents.
    result = {}
    for value in ("/usr/bin/git", "/usr/lib/git-core/git-remote-http", "/usr/bin/python3"):
        path = Path(value).resolve(strict=True)
        secure(path)
        result[value] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _recovery_production_proof(sha, source):
    path = source / "scripts/trusted_review_reset.py"
    secure(path)
    if os.path.lexists(path.parent / "__pycache__"):
        raise BootstrapError("cached canonical operator code forbidden")
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("reviewed_recovery_proof", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._revision_proof(sha, source, SimpleNamespace(secure=secure))


def _assert_original_lock(path, fd):
    secure(path, private=True)
    before, after = os.fstat(fd), path.lstat()
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise BootstrapError("original recovery lock replaced")


def _recovery_file_identity(path):
    secure(path, private=True)
    info = path.lstat()
    return {"uid": info.st_uid, "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode),
            "inode": info.st_ino, "device": info.st_dev,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _recovery_snapshot(old_sha, sha, production_sha, source):
    if os.path.lexists(BUSINESS_LEASE):
        raise BootstrapError("business lease blocks historical recovery")
    _assert_idle()
    _recovery_process_proof()
    workspace = _legacy_clone_evidence(old_sha)
    config = _inventory(CONFIG, {"known_hosts", "loopback.conf", "authorized-release.json",
                                 "loopback.pub", "cloud.pub", "loopback.key"})
    library = _inventory(INSTALLED.parent, {INSTALLED.name})
    policy = _read_json(CONFIG / "authorized-release.json")
    if (not isinstance(policy, dict) or set(policy) != {"sha", "expires_at", "executor_sha256"}
            or policy["sha"] != old_sha or type(policy["expires_at"]) is not int
            or policy["executor_sha256"] != workspace["executor_sha256"]
            or library[INSTALLED.name]["sha256"] != workspace["executor_sha256"]):
        raise BootstrapError("historical installation binding differs")
    public = [(CONFIG / name).read_text().strip() for name in ("cloud.pub", "loopback.pub")]
    for key in public:
        validate_install(old_sha, 1, key, now=0)
    if public[0] == public[1]:
        raise BootstrapError("historical identities must differ")
    secure(AUTHORIZED, private=True)
    expected = key_lines(policy["expires_at"], *public)
    lines = AUTHORIZED.read_text().splitlines()
    for key, exact in zip(public, expected):
        if [line for line in lines if key.split()[1] in line] != [exact]:
            raise BootstrapError("historical authorization is not exact")
    _recovery_production_proof(production_sha, source)
    toolchain = _recovery_toolchain_proof()
    _assert_idle()
    _recovery_process_proof()
    if workspace != _legacy_clone_evidence(old_sha) or os.path.lexists(BUSINESS_LEASE):
        raise BootstrapError("historical evidence changed during proof")
    return {"old_sha": old_sha, "recovery_sha": sha, "production_sha": production_sha,
            "workspace": workspace, "config": config, "library": library,
            "authorized": _recovery_file_identity(AUTHORIZED),
            "locks": {"launcher": _recovery_file_identity(STATE / "launcher.lock"),
                      "build": _recovery_file_identity(STATE / old_sha / "build.lock")},
            "toolchain": toolchain}


def recover_preparation(old_sha, sha, production_sha, *, evidence_sha256=None):
    for value in (old_sha, sha, production_sha):
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
            raise BootstrapError("exact recovery revisions required")
    if len({old_sha, sha, production_sha}) != 3 or "SSH_ORIGINAL_COMMAND" in os.environ:
        raise BootstrapError("distinct operator recovery revisions required")
    if evidence_sha256 is not None and re.fullmatch(r"[0-9a-f]{64}", evidence_sha256) is None:
        raise BootstrapError("exact inspected evidence digest required")
    source, _server = reviewed_source(sha)
    _run(["/usr/bin/python3.12", "-I", str(source / "scripts/trusted_release_gate.py"), "--sha", sha, "--workflow-sha", sha])
    lock = STATE / "launcher.lock"
    secure(lock, private=True)
    fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
    build_fd = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build_fd = _acquire_existing_build_lock(old_sha)
        if build_fd is None:
            raise BootstrapError("original build lock required")
        record = STATE / "recoveries" / old_sha
        if os.path.lexists(record):
            raise BootstrapError("historical recovery already attempted; no retry")
        history = _retired_history()
        _assert_known_activity(history, old_sha)
        if old_sha in history or any(os.path.lexists(p) for p in _archives(old_sha)):
            raise BootstrapError("historical retirement already attempted")
        evidence = _recovery_snapshot(old_sha, sha, production_sha, source)
        digest = _digest_json(evidence)
        _assert_original_lock(lock, fd)
        _assert_original_lock(STATE / old_sha / "build.lock", build_fd)
        if evidence_sha256 is None:
            return {"sha": old_sha, "state": "RECOVERABLE_PREPARATION_FAILURE", "evidence_sha256": digest}
        if digest != evidence_sha256:
            raise BootstrapError("historical evidence differs from reviewed inspection")
        if not record.parent.exists():
            record.parent.mkdir(mode=0o700)
            _sync_parent(record.parent)
        secure(record.parent)
        record.mkdir(mode=0o700)
        _sync_parent(record)
        _write(record / "intent.json", json.dumps(evidence, sort_keys=True).encode())
        if _recovery_snapshot(old_sha, sha, production_sha, source) != evidence:
            raise BootstrapError("recovery evidence drift after intent; retain operation")
        _assert_original_lock(lock, fd)
        _assert_original_lock(STATE / old_sha / "build.lock", build_fd)
        # This separate operator action only revokes the exact two old keys.
        # It never calls deploy, rewrites old receipts, or creates a new identity.
        policy = _read_json(CONFIG / "authorized-release.json")
        public = [(CONFIG / name).read_text().strip() for name in ("cloud.pub", "loopback.pub")]
        expected = key_lines(policy["expires_at"], *public)
        lines = AUTHORIZED.read_bytes().splitlines(keepends=True)
        retained = b"".join(line for line in lines if line.decode().rstrip("\r\n") not in expected)
        _replace_authorized(retained)
        if AUTHORIZED.read_bytes() != retained:
            raise BootstrapError("authorization revocation postcondition failed")
        secure(CONFIG / "loopback.key", private=True)
        (CONFIG / "loopback.key").unlink()
        _sync_parent(CONFIG / "loopback.key")
        installation = _installation_evidence(old_sha, CONFIG, INSTALLED.parent)
        if _legacy_clone_evidence(old_sha) != evidence["workspace"]:
            raise BootstrapError("recovery changed original evidence")
        _assert_idle()
        _recovery_process_proof()
        _recovery_production_proof(production_sha, source)
        _assert_original_lock(lock, fd)
        _assert_original_lock(STATE / old_sha / "build.lock", build_fd)
        if os.path.lexists(BUSINESS_LEASE):
            raise BootstrapError("business lease appeared during recovery")
        _write(record / "completed.json", json.dumps({"old_sha": old_sha,
               "state": "RECOVERED_PREPARATION_FAILURE", "intent_sha256": digest,
               "installation": installation}, sort_keys=True).encode())
        return {"sha": old_sha, "state": "RECOVERED_PREPARATION_FAILURE"}
    finally:
        if build_fd is not None:
            os.close(build_fd)
        os.close(fd)


def _recovered_preparation_evidence(sha):
    record = STATE / "recoveries" / sha
    _inventory(record, {"intent.json", "completed.json"})
    intent = _read_json(record / "intent.json")
    completed = _read_json(record / "completed.json")
    expected_keys = {"old_sha", "recovery_sha", "production_sha", "workspace", "config",
                     "library", "authorized", "locks", "toolchain"}
    if (not isinstance(intent, dict) or set(intent) != expected_keys or intent["old_sha"] != sha
            or not isinstance(completed, dict) or set(completed) != {
                "old_sha", "state", "intent_sha256", "installation"}
            or completed["old_sha"] != sha or completed["state"] != "RECOVERED_PREPARATION_FAILURE"
            or completed["intent_sha256"] != _digest_json(intent)
            or intent["workspace"] != _legacy_clone_evidence(sha)):
        raise BootstrapError("historical recovery audit differs")
    if (any(not isinstance(intent[k], str) or re.fullmatch(r"[0-9a-f]{40}", intent[k]) is None
            for k in ("recovery_sha", "production_sha"))
            or len({sha, intent["recovery_sha"], intent["production_sha"]}) != 3
            or not isinstance(intent["config"], dict) or "loopback.key" not in intent["config"]
            or completed["installation"] != {
                "config": {k: v for k, v in intent["config"].items() if k != "loopback.key"},
                "library": intent["library"]}
            or intent["locks"] != {
                "launcher": _recovery_file_identity(STATE / "launcher.lock"),
                "build": _recovery_file_identity(STATE / sha / "build.lock")}):
        raise BootstrapError("historical recovery bindings differ")
    config, library = _archives(sha)
    if not os.path.lexists(config) and not os.path.lexists(library):
        config, library = CONFIG, INSTALLED.parent
    if completed["installation"] != _installation_evidence(sha, config, library):
        raise BootstrapError("recovered installation differs")
    return {"state": "RECOVERED_PREPARATION_FAILURE", "recovery": _digest_json(completed),
            "workspace": intent["workspace"]}


def main():
    try:
        if not sys.flags.isolated or os.geteuid() != 0:
            raise BootstrapError("isolated root execution required")
        os.umask(0o077)
        use_system_timezone()
        parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
        commands = parser.add_subparsers(dest="action", required=True)
        create = commands.add_parser("install", allow_abbrev=False)
        create.add_argument("--sha", required=True)
        create.add_argument("--expires-at", required=True, type=int)
        create.add_argument("--cloud-public-key", required=True)
        rotation = commands.add_parser("rotate", allow_abbrev=False)
        rotation.add_argument("--retire-sha", required=True)
        rotation.add_argument("--sha", required=True)
        rotation.add_argument("--expires-at", required=True, type=int)
        rotation.add_argument("--cloud-public-key", required=True)
        remove = commands.add_parser("revoke", allow_abbrev=False)
        remove.add_argument("--sha", required=True)
        recovery = commands.add_parser("recover-preparation", allow_abbrev=False)
        recovery.add_argument("--retire-sha", required=True)
        recovery.add_argument("--sha", required=True)
        recovery.add_argument("--production-sha", required=True)
        recovery.add_argument("--evidence-sha256")
        args = parser.parse_args()
        if args.action == "recover-preparation":
            result = recover_preparation(args.retire_sha, args.sha, args.production_sha,
                                         evidence_sha256=args.evidence_sha256)
        elif args.action == "rotate":
            result = rotate(args.retire_sha, args.sha, args.expires_at, args.cloud_public_key)
        elif args.action == "install":
            result = install(args.sha, args.expires_at, args.cloud_public_key)
        else:
            result = revoke(args.sha)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:  # noqa: BLE001 -- Boundary must sanitize all install/credential failures.
        print("release bootstrap: validation/installation failed; preserve evidence for operator review", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
