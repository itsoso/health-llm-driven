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
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path

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
    if not os.path.lexists(workspace):
        return {"state": "NEVER_STARTED", "inventory": None}
    secure(workspace)
    names = {p.name for p in workspace.iterdir()}
    if not names:
        return {"state": "NEVER_STARTED", "inventory": []}
    allowed = {"started.json", "completed.json", "build-started.json", "native-started.json",
               "build.lock", "source", "home", "bin", "deployment.env", "preparation.log", "deployment.log"}
    if not names <= allowed or not {"started.json", "completed.json"} <= names:
        raise BootstrapError("backend termination unproven; retirement forbidden")
    receipts = {}
    for name in sorted(names):
        path = workspace / name
        secure(path, private=name not in {"source", "home", "bin"})
        if name.endswith(".json"):
            expected = {"sha": sha, "state": "SUCCEEDED" if name == "completed.json" else "STARTED"}
            if _read_json(path) != expected:
                raise BootstrapError("backend termination unproven; retirement forbidden")
            receipts[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"state": "SUCCEEDED", "inventory": sorted(names), "receipts": receipts}


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
                "reva-release", "trusted_release_server.py", "bootstrap_trusted_release.py", "deploy.sh",
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
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
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
        os.close(fd)


def revoke(sha):
    if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise BootstrapError("exact managed SHA required")
    # Revocation does not need a green *current* main: the fixed reviewed local
    # staging remains sufficient to remove its own old, expired authorization.
    reviewed_source(sha)
    secure(STATE)
    fd = os.open(STATE / "launcher.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        secure(STATE / "launcher.lock", private=True)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _revoke_locked(sha)
    finally:
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
    if (
        json.loads(started.read_bytes()) != {"sha": sha, "state": "STARTED"}
        or json.loads(completed.read_bytes()) != {"sha": sha, "state": "SUCCEEDED"}
    ):
        raise BootstrapError("backend termination unproven; retain recovery authorization")


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
        args = parser.parse_args()
        if args.action == "rotate":
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
