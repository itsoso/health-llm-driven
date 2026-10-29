"""Install/revoke/rotate a version-bound release identity; not a deployment tool.

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
import secrets
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
# Audited phase-aware executor: fixed Git only before durable DEPLOYING intent.
# This is an implementation profile, never permission to retry a consumed SHA.
PHASE_CLONE_TIMEOUT_EXECUTORS = {
    "cae7d46a45778db0bacd9c86f8f31b15b289d1f030ad3a50d8d947d330af313f",
}
# Audited phase-aware executor whose initial no-checkout clone was interrupted
# at the 90-second preparation boundary before Git emitted a terminal error.
PHASE_CLONE_COMPLETED_EXECUTORS = {
    "bdfd21ed1bd67c38ed04916257758ab76970cb3be38f1cacc7f675eb807c2bd4",
}
# Implementation-level proof: this executor opens deployment.log only after
# the exact read-only gate succeeds. Never a release-SHA exemption or retry.
PREDEPLOY_ATTESTATION_IMPLEMENTATIONS = {
    "81dfedcc8ccbeb8b88181a0a309abbfb129d0d48a8d83ce2a42b5d112d5829eb":
        "72b1e2423e54d9251bcabe262798366af25ebbe0aee29197c1c6b64547ac180e",
}
PROC = Path("/proc")
NATIVE_ROTATION_OLD = 'c28050786c1e9aa70cca33d7e3d5c093652aeb26'
NATIVE_ROTATION_ABANDONED = 'ace2737c636c74e9f738cb86960de3f1b4ae94d3'
NATIVE_ROTATION_PRODUCTION = '1f14f9c0a73facc511daafa3a7aa8e447ee62fd0'
NATIVE_ROTATION_AUDIT = '3d469e94e68202508912189f93cc0ce3ef3c9af064121f8182374a98cf3b5d10'


class BootstrapError(Exception):
    """Sanitized operator-facing error."""


def secure(path, *, private=False, allow_hardlinks=False):
    path = Path(path)
    for item in [*reversed(path.parents), path]:
        info = item.lstat()
        if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
            raise BootstrapError("unsafe root-owned installation path")
        if item != path and not stat.S_ISDIR(info.st_mode):
            raise BootstrapError("unsafe parent directory")
        if item == path and (not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)) or (stat.S_ISREG(info.st_mode) and not allow_hardlinks and info.st_nlink != 1)):
            raise BootstrapError("unsafe installation object")
    if private and (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600):
        raise BootstrapError("private configuration must be a regular 0600 file")


def validate_object_cache(objects):
    """Reject recursive alternates and every non-root-controlled Git object."""
    objects = Path(objects)
    secure(objects)
    for name in ("alternates", "http-alternates"):
        if os.path.lexists(objects / "info" / name):
            raise BootstrapError("production object cache must not chain alternates")
    for root, directories, files in os.walk(objects, followlinks=False):
        root = Path(root)
        secure(root)
        for name in directories:
            secure(root / name)
        for name in files:
            secure(root / name, allow_hardlinks=True)


def validate_install(sha, expiry, public, *, now):
    if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise BootstrapError("exact reviewed SHA required")
    if type(expiry) is not int or (expiry != 0 and expiry <= now):
        raise BootstrapError("authorization expiry must be zero or a future timestamp")
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
    deadline = f',expiry-time="{expiry_time(expiry)}"' if expiry != 0 else ""
    return (
        f'command="/usr/bin/python3 -I /usr/local/lib/reva-release/trusted_release_server.py",restrict{deadline} {cloud}',
        f'from="127.0.0.1",restrict{deadline} {loopback}',
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
    alternate = source / ".git/objects/info/alternates"
    if os.path.lexists(alternate):
        secure(alternate)
        production_objects = Path("/opt/health-app/.git/objects")
        validate_object_cache(production_objects)
        if alternate.read_text() != str(production_objects) + "\n":
            raise BootstrapError("unexpected Git object alternate")
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


def install(sha, expiry, public, *, backend_ci=False):
    validate_install(sha, expiry, public, now=int(time.time()))
    _assert_installable(sha)
    source, server = reviewed_source(sha)
    if backend_ci:
        _run(["/usr/bin/python3.12", "-I", "-S", "-B", str(source / "scripts/trusted_backend_admission.py"), "--sha", sha])
    else:
        _run(["/usr/bin/python3.12", "-I", str(source / "scripts/trusted_release_gate.py"),
              "--sha", sha, "--workflow-sha", sha, "--observed-main", sha])
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
    assert_ota_history()
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


def _inventory(directory, names, *, content_digests=None):
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
            "sha256": (content_digests[path.name] if content_digests is not None
                       else hashlib.sha256(path.read_bytes()).hexdigest()) if path != directory else None,
        }
    return result


def _dinner_guard_module():
    path = Path(__file__).absolute().with_name("dinner_guard_retirement.py")
    secure(path)
    if os.path.lexists(path.parent / "__pycache__"):
        raise BootstrapError("cached dinner retirement proof forbidden")
    spec = importlib.util.spec_from_file_location("reviewed_dinner_retirement", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fdd_guard_module():
    path = Path(__file__).absolute().with_name("fdd_guard_retirement.py")
    secure(path)
    if os.path.lexists(path.parent / "__pycache__"):
        raise BootstrapError("cached fdd retirement proof forbidden")
    spec = importlib.util.spec_from_file_location("reviewed_fdd_retirement", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _dinner_profile_module(sha):
    if sha == "fdd5659502888d44bf91c9b35a7368366932098f":
        return _fdd_guard_module()
    return _dinner_guard_module()


def _exam_forward_module():
    path = Path(__file__).absolute().with_name('exam_forward_retirement.py')
    secure(path)
    if os.path.lexists(path.parent / '__pycache__'):
        raise BootstrapError('cached exam closure proof forbidden')
    spec = importlib.util.spec_from_file_location('reviewed_exam_forward_closure', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    exec(compile(path.read_bytes(), str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def _workspace_evidence(sha, *, recovery_receipt=None, historical=False):
    workspace = STATE / sha
    exam_closure = os.path.lexists(STATE / 'exam-forward-closures' / sha)
    dinner_closure = os.path.lexists(STATE / "dinner-guard-closures" / sha)
    fdd_closure = os.path.lexists(STATE / "fdd-guard-closures" / sha)
    rollback_closure = os.path.lexists(STATE / "rolled-back-release-closures" / sha)
    retained_closure = os.path.lexists(STATE / "retained-candidate-closures" / sha)
    native_closure = os.path.lexists(STATE / "native-only-closures" / sha)
    partial_laya = os.path.lexists(STATE / "partial-laya-closures" / sha)
    review_closure = os.path.lexists(STATE / "review-maintenance-closures" / sha)
    unchanged_closure = os.path.lexists(STATE / "unchanged-release-closures" / sha)
    contained_closure = os.path.lexists(STATE / "contained-release-closures" / sha)
    lost_receipt_ack = os.path.lexists(STATE / "lost-closure-receipt-acknowledgments" / sha)
    if sum((review_closure, unchanged_closure, contained_closure, partial_laya, native_closure, retained_closure, rollback_closure, dinner_closure, fdd_closure, exam_closure)) > 1:
        raise BootstrapError("conflicting release closure evidence")
    if exam_closure:
        if lost_receipt_ack or os.path.lexists(STATE / 'recoveries' / sha):
            raise BootstrapError('conflicting exam closure evidence')
        return _exam_forward_module().closed_evidence(
            sys.modules[__name__], sha, recovery_receipt, historical=historical)
    if fdd_closure:
        return _fdd_guard_module().closed_evidence(
            sys.modules[__name__], sha, recovery_receipt, historical=historical)
    if dinner_closure:
        return _dinner_guard_module().closed_evidence(
            sys.modules[__name__], sha, recovery_receipt, historical=historical)
    if rollback_closure:
        if lost_receipt_ack or os.path.lexists(STATE / "recoveries" / sha):
            raise BootstrapError("conflicting rolled-back release closure evidence")
        path = Path(__file__).absolute().with_name("rolled_back_release_operator.py")
        secure(path)
        if os.path.lexists(path.parent / "__pycache__"):
            raise BootstrapError("cached rolled-back release proof forbidden")
        spec = importlib.util.spec_from_file_location("reviewed_rolled_back_release", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.closed_evidence(sys.modules[__name__], sha, recovery_receipt, historical=historical)
    if retained_closure:
        if lost_receipt_ack or os.path.lexists(STATE / "recoveries" / sha):
            raise BootstrapError("conflicting retained candidate closure evidence")
        path = Path(__file__).absolute().with_name("retained_candidate_retirement.py")
        secure(path)
        if os.path.lexists(path.parent / "__pycache__"):
            raise BootstrapError("cached retained candidate proof forbidden")
        spec = importlib.util.spec_from_file_location("reviewed_retained_candidate", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.closed_evidence(sys.modules[__name__], sha, recovery_receipt, historical=historical)
    if native_closure:
        if lost_receipt_ack or os.path.lexists(STATE / "recoveries" / sha):
            raise BootstrapError("conflicting native closure evidence")
        path = Path(__file__).absolute().with_name("native_release_retirement.py")
        secure(path)
        if os.path.lexists(path.parent / "__pycache__"):
            raise BootstrapError("cached native closure proof forbidden")
        spec = importlib.util.spec_from_file_location("reviewed_native_closure", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.closed_evidence(sys.modules[__name__], sha, recovery_receipt, historical=historical)
    if partial_laya:
        if lost_receipt_ack or os.path.lexists(STATE / "recoveries" / sha):
            raise BootstrapError("conflicting partial Laya recovery evidence")
        path = Path(__file__).absolute().with_name("partial_laya_retirement.py")
        secure(path)
        if os.path.lexists(path.parent / "__pycache__"):
            raise BootstrapError("cached partial Laya proof forbidden")
        spec = importlib.util.spec_from_file_location("reviewed_partial_laya", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.closed_evidence(sys.modules[__name__], sha, recovery_receipt)
    if lost_receipt_ack:
        if not unchanged_closure:
            raise BootstrapError("lost receipt acknowledgment lacks unchanged closure")
        path = Path(__file__).absolute().with_name("lost_closure_receipt_acknowledgment.py")
        secure(path)
        if os.path.lexists(path.parent / "__pycache__"):
            raise BootstrapError("cached acknowledgment proof forbidden")
        spec = importlib.util.spec_from_file_location("reviewed_lost_receipt_acknowledgment", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.acknowledged_evidence(
            sys.modules[__name__], sha, recovery_receipt, historical=historical)
    if review_closure:
        path = Path(__file__).absolute().with_name("review_maintenance_retirement.py")
        secure(path)
        if os.path.lexists(path.parent / "__pycache__"):
            raise BootstrapError("cached review closure proof forbidden")
        spec = importlib.util.spec_from_file_location("reviewed_unknown_maintenance_closure", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.closed_evidence(sys.modules[__name__], sha, recovery_receipt)
    if unchanged_closure or contained_closure:
        path = Path(__file__).absolute().with_name("contained_release_retirement.py")
        secure(path)
        if os.path.lexists(path.parent / "__pycache__"):
            raise BootstrapError("cached closure proof forbidden")
        spec = importlib.util.spec_from_file_location("reviewed_closed_containment", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if unchanged_closure:
            return module.closed_evidence(sys.modules[__name__], sha, recovery_receipt, unchanged=True, historical=historical)
        return module.closed_evidence(sys.modules[__name__], sha, recovery_receipt)
    if os.path.lexists(STATE / "recoveries" / sha):
        return _recovered_preparation_evidence(sha, recovery_receipt=recovery_receipt)
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
               "preparation-started.json", "prepared.json", "deployment-started.json", "clone-attempts", "review-resets", "host-hardening"}
    if not names <= allowed or not {"started.json", "completed.json"} <= names:
        raise BootstrapError("backend termination unproven; retirement forbidden")
    phases = {"preparation-started.json", "prepared.json", "deployment-started.json"}
    if names & phases and not phases <= names:
        raise BootstrapError("incomplete successful release phase evidence")
    receipts = {}
    for name in sorted(names):
        path = workspace / name
        secure(path, private=name not in {"source", "home", "bin", "clone-attempts", "review-resets", "host-hardening"})
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
    if "host-hardening" in names:
        receipts["host-hardening"] = _host_hardening_evidence(sha)
    return {"state": "SUCCEEDED", "inventory": sorted(names), "receipts": receipts}


def _host_hardening_evidence(sha):
    root = STATE / sha / "host-hardening"
    if os.path.lexists(root / "failed.json"):
        path = Path(__file__).with_name("public_host_recovery.py")
        secure(path)
        if os.path.lexists(path.parent / "__pycache__"):
            raise BootstrapError("cached host recovery evidence forbidden")
        spec = importlib.util.spec_from_file_location("host_recovery_history", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        result=module.history_evidence(sys.modules[__name__], sha)
        if os.path.lexists(STATE / 'monitor-ingress-repairs'):
            monitor_path=Path(__file__).with_name('monitor_ingress_repair.py')
            secure(monitor_path)
            monitor_spec=importlib.util.spec_from_file_location('monitor_ingress_history',monitor_path)
            monitor=importlib.util.module_from_spec(monitor_spec)
            sys.modules[monitor_spec.name]=monitor
            monitor_spec.loader.exec_module(monitor)
            result={**result,'monitor_ingress':monitor.history_evidence(sys.modules[__name__],result)}
        return result
    inventory = _inventory(root, {"started.json", "verified.json", "completed.json", "frontend.json"})
    expected = {
        "started.json": {"sha": sha, "state": "STARTED"},
        "verified.json": {"sha": sha, "state": "LOCAL_VERIFIED"},
        "completed.json": {"sha": sha, "state": "LOCAL_VERIFIED", "external_readback_required": True},
    }
    for name, value in expected.items():
        if _read_json(root / name) != value:
            raise BootstrapError("host hardening termination unproven")
    frontend = _read_json(root / "frontend.json")
    if (set(frontend) != {"operation_id", "frontend_tree", "artifact_digest"}
            or re.fullmatch(r"[a-f0-9]{32}", str(frontend["operation_id"])) is None
            or re.fullmatch(r"[a-f0-9]{40}", str(frontend["frontend_tree"])) is None
            or re.fullmatch(r"[a-f0-9]{64}", str(frontend["artifact_digest"])) is None):
        raise BootstrapError("host frontend binding malformed")
    return inventory


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


def _retired_public_keys(sha, evidence):
    if evidence.get('retirement_policy') == 'no-backup-v1':
        keys = evidence.get('public_keys')
        if not isinstance(keys, dict) or set(keys) != {'cloud.pub', 'loopback.pub'}:
            raise BootstrapError('invalid retired public identity audit')
        for name, public in keys.items():
            validate_install(sha, 1, public, now=0)
            expected = evidence['installation']['config'][name]['sha256']
            encodings = {public, public + '\n'}
            # Our fixed ssh-keygen -C '' invocation writes an empty comment as
            # space+LF. Retirement stores stripped public text, so reconstruct
            # only this exact producer format, never arbitrary whitespace.
            if name == 'loopback.pub' and len(public.split()) == 2:
                encodings.add(public + ' \n')
            if expected not in {hashlib.sha256(value.encode()).hexdigest() for value in encodings}:
                raise BootstrapError('retired public identity hash differs')
        return keys
    config = _retired_config(sha, evidence)
    result = {}
    for name in ('cloud.pub', 'loopback.pub'):
        secure(config / name, private=True)
        result[name] = (config / name).read_text().strip()
    return result


def _discard_current_installation(sha, expected):
    """Remove only the revoked current installation; retain no recovery copy.

    The durable retirement intent precedes removal. A partial failure blocks
    further rotation, rather than promising an unavailable automatic rollback.
    """
    if _installation_evidence(sha, CONFIG, INSTALLED.parent) != expected:
        raise BootstrapError('installation changed before no-backup retirement')
    for directory, names in ((CONFIG, expected['config']), (INSTALLED.parent, expected['library'])):
        for name in sorted(set(names) - {'.'}):
            path = directory / name
            secure(path, private=True)
            info = path.lstat()
            if (info.st_ino, info.st_dev) != (names[name]['inode'], names[name]['device']):
                raise BootstrapError('installation inode changed during retirement')
            path.unlink()
            _sync_parent(path)
        directory.rmdir()
        _sync_parent(directory)


def _persistent_cloud_successor(sha, public):
    """Prove uninterrupted, audited reuse up to the current restricted identity."""
    policy = _read_json(CONFIG / "authorized-release.json")
    if (not isinstance(policy, dict) or set(policy) != {"sha", "expires_at", "executor_sha256"}
            or not isinstance(policy["sha"], str) or re.fullmatch(r"[0-9a-f]{40}", policy["sha"]) is None
            or type(policy["expires_at"]) is not int or policy["expires_at"] != 0
            or policy["sha"] == sha):
        raise BootstrapError("reused cloud identity lacks persistent successor authorization")
    secure(CONFIG / "cloud.pub", private=True)
    secure(INSTALLED, private=True)
    canonical = canonical_source(policy["sha"]) / "scripts/trusted_release_server.py"
    digest = hashlib.sha256(canonical.read_bytes()).hexdigest()
    if ((CONFIG / "cloud.pub").read_text().strip() != public
            or policy["executor_sha256"] != digest
            or hashlib.sha256(INSTALLED.read_bytes()).hexdigest() != digest):
        raise BootstrapError("reused cloud identity differs from canonical successor")
    seen = set()
    recovery = _native_rotation_recovery()
    while sha != policy["sha"]:
        if sha in seen or len(seen) >= 10000:
            raise BootstrapError("invalid cloud identity succession chain")
        seen.add(sha)
        record = STATE / "retired" / sha
        _inventory(record, {"intent.json", "completed.json"})
        intent = _read_json(record / "intent.json")
        next_sha = intent.get("new_sha")
        if (intent.get("old_sha") != sha or intent.get("cloud_key_reused") is not True
                or not isinstance(next_sha, str) or re.fullmatch(r"[0-9a-f]{40}", next_sha) is None
                or _read_json(record / "completed.json") != {"old_sha": sha, "new_sha": next_sha, "state": "RETIRED"}):
            raise BootstrapError("cloud identity reuse lacks completed succession audit")
        if _retired_public_keys(sha, intent)['cloud.pub'] != public:
            raise BootstrapError("cloud identity changed within succession chain")
        if sha == NATIVE_ROTATION_OLD and recovery is not None:
            next_sha = recovery['publisher_sha']
        sha = next_sha
    expected, _loopback = key_lines(0, public, public)
    matches = [line for line in AUTHORIZED.read_text().splitlines() if public.split()[1] in line]
    if matches != [expected]:
        raise BootstrapError("reused cloud identity lacks exact restricted authorization")


def _installation_evidence(sha, config, library, *, history_only=False):
    historical_digest = (hashlib.sha256((canonical_source(sha) / "scripts/trusted_release_server.py").read_bytes()).hexdigest()
                         if history_only else None)
    config_files = {"known_hosts", "loopback.conf", "authorized-release.json", "loopback.pub", "cloud.pub"}
    inventory = {"config": _inventory(config, config_files),
                 "library": _inventory(library, {INSTALLED.name},
                                       content_digests={INSTALLED.name: historical_digest} if history_only else None)}
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
            if config == CONFIG or name != "cloud.pub":
                raise BootstrapError("old identity is still authorized")
            _persistent_cloud_successor(sha, public)
    return inventory


def _legacy_successful_auth_revocation(entry, intent):
    """Read completed historical formats only against canonical retirement evidence."""
    base = {'old_sha', 'new_sha', 'state', 'old_executor_sha256'}
    compact = base | {'old_receipt_sha256', 'workspace_sha256'}
    expanded = base | {'old_authorized_sha256', 'loopback_public_sha256',
                       'backend_succeeded', 'workspace', 'private_identity'}
    formats = (compact, expanded | {'backend_receipt_sha256'},
               expanded | {'ota_receipt_sha256'},
               expanded | {'credential_sha256', 'no_backup', 'production_sha'})
    if (set(intent) not in formats or intent['old_sha'] != entry.name
            or intent['state'] != 'SUCCESSFUL_IDENTITY_REVOCATION_INTENT'
            or not isinstance(intent['new_sha'], str)
            or re.fullmatch(r'[0-9a-f]{40}', intent['new_sha']) is None
            or intent['new_sha'] == entry.name):
        raise BootstrapError('invalid historical successful identity intent')
    for key, value in intent.items():
        if key.endswith('_sha256') and (not isinstance(value, str)
                or re.fullmatch(r'[0-9a-f]{64}', value) is None):
            raise BootstrapError('invalid historical identity digest')
    retired_path = STATE / 'retired' / entry.name
    _inventory(retired_path, {'intent.json', 'completed.json'})
    retired = _read_json(retired_path / 'intent.json')
    if (not isinstance(retired, dict) or retired.get('old_sha') != entry.name
            or retired.get('new_sha') != intent['new_sha']
            or _read_json(retired_path / 'completed.json') != {
                'old_sha': entry.name, 'new_sha': intent['new_sha'], 'state': 'RETIRED'}):
        raise BootstrapError('historical successful identity retirement differs')
    workspace = _workspace_evidence(entry.name, historical=True)
    if workspace.get('state') != 'SUCCEEDED' or retired.get('workspace') != workspace:
        raise BootstrapError('historical successful workspace differs')
    executor_digest = hashlib.sha256(
        (canonical_source(entry.name) / 'scripts/trusted_release_server.py').read_bytes()
    ).hexdigest()
    if intent['old_executor_sha256'] != executor_digest:
        raise BootstrapError('historical successful executor differs')
    receipt_digest = hashlib.sha256((STATE / entry.name / 'completed.json').read_bytes()).hexdigest()
    installation_digest = _digest_json(retired.get('installation'))
    expected_done = dict(intent, state='SUCCESSFUL_IDENTITY_REVOKED')
    if set(intent) == compact:
        if (intent['old_receipt_sha256'] != receipt_digest
                or intent['workspace_sha256'] != _digest_json(workspace)):
            raise BootstrapError('historical successful receipt differs')
    else:
        identity = intent['private_identity']
        if (intent['backend_succeeded'] is not True or intent['workspace'] != workspace
                or not isinstance(identity, dict) or set(identity) != {'dev', 'ino'}
                or any(type(value) is not int or value <= 0 for value in identity.values())):
            raise BootstrapError('historical successful identity evidence differs')
        if 'backend_receipt_sha256' in intent and intent['backend_receipt_sha256'] != receipt_digest:
            raise BootstrapError('historical backend receipt differs')
        if 'no_backup' in intent and (intent['no_backup'] is not True or intent['production_sha'] != entry.name):
            raise BootstrapError('historical successful production identity differs')
        expected_done['installation_sha256'] = installation_digest
    if _read_json(entry / 'completed.json') != expected_done:
        raise BootstrapError('historical successful completion differs')
    # _retired_history also verifies the actual installation, revoked keys and
    # successor chain. Extra credential/OTA digests are historical audit metadata,
    # never an authority to refresh credentials, publish OTA or skip those checks.
    return {'old_sha': entry.name, 'new_sha': intent['new_sha'],
            'workspace': workspace, 'installation_sha256': installation_digest}


def _successful_auth_revocation_history():
    root = STATE / "successful-auth-revocations"
    if not os.path.lexists(root):
        return {}
    secure(root)
    if not root.is_dir() or stat.S_IMODE(root.lstat().st_mode) != 0o700:
        raise BootstrapError("successful identity revocation audit is invalid")
    history = {}
    for entry in root.iterdir():
        try:
            if re.fullmatch(r"[0-9a-f]{40}", entry.name) is None:
                raise BootstrapError("invalid successful identity SHA")
            _inventory(entry, {"intent.json", "completed.json"})
            intent = _read_json(entry / "intent.json")
            if isinstance(intent, dict) and 'state' in intent:
                history[entry.name] = _legacy_successful_auth_revocation(entry, intent)
                continue
            expected = {
                "old_sha", "new_sha", "workspace", "workspace_completed_sha256",
                "old_executor_sha256", "old_authorized_sha256",
                "loopback_public_sha256", "backend_succeeded",
            }
            if (not isinstance(intent, dict) or set(intent) != expected
                    or intent["old_sha"] != entry.name
                    or not isinstance(intent["new_sha"], str)
                    or re.fullmatch(r"[0-9a-f]{40}", intent["new_sha"]) is None
                    or intent["new_sha"] == entry.name
                    or intent["backend_succeeded"] is not True
                    or any(not isinstance(intent[name], str)
                           or re.fullmatch(r"[0-9a-f]{64}", intent[name]) is None
                           for name in ("workspace_completed_sha256", "old_executor_sha256",
                                        "old_authorized_sha256", "loopback_public_sha256"))):
                raise BootstrapError("invalid successful identity intent")
            expected_executor = hashlib.sha256(
                (canonical_source(entry.name) / "scripts/trusted_release_server.py").read_bytes()
            ).hexdigest()
            if intent["old_executor_sha256"] != expected_executor:
                raise BootstrapError("successful identity executor differs from canonical source")
            completed = _read_json(entry / "completed.json")
            workspace = _workspace_evidence(entry.name, historical=True)
            workspace_completed = STATE / entry.name / "completed.json"
            if (not isinstance(completed, dict)
                    or set(completed) != {"old_sha", "new_sha", "state", "installation_sha256"}
                    or completed.get("old_sha") != entry.name
                    or completed.get("new_sha") != intent["new_sha"]
                    or completed.get("state") != "SUCCESSFUL_IDENTITY_REVOKED"
                    or not isinstance(completed.get("installation_sha256"), str)
                    or re.fullmatch(r"[0-9a-f]{64}", completed["installation_sha256"]) is None
                    or workspace != intent["workspace"]
                    or hashlib.sha256(workspace_completed.read_bytes()).hexdigest()
                       != intent["workspace_completed_sha256"]):
                raise BootstrapError("invalid successful identity completion")
            history[entry.name] = {**intent, "installation_sha256": completed["installation_sha256"]}
        except (BootstrapError, OSError, ValueError, KeyError, TypeError):
            raise BootstrapError("successful identity revocation audit is incomplete or invalid") from None
    return history


def _retired_history():
    _native_rotation_recovery()
    successful = _successful_auth_revocation_history()
    root = STATE / "retired"
    if not os.path.lexists(root):
        if LEGACY_RETIREMENTS or successful:
            raise BootstrapError("pinned or successful retirement is incomplete")
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
            evidence = {"installation": _installation_evidence(entry.name, entry / "config", entry / "executor", history_only=True),
                        "workspace": _workspace_evidence(entry.name, historical=True)}
            digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if (evidence["workspace"] != {"state": "NEVER_STARTED", "inventory": None}
                    or digest != LEGACY_RETIREMENTS[entry.name]):
                raise BootstrapError("legacy retirement evidence changed")
            history[entry.name] = {"format": "pinned-legacy", **evidence}
            continue
        _inventory(entry, {"intent.json", "completed.json"})
        intent = _read_json(entry / "intent.json")
        if (not isinstance(intent, dict) or set(intent) - {"cloud_key_reused", "finalized_native_advance", "review_maintenance_advance", "review_maintenance_release_closure", "retirement_policy", "public_keys"} not in (
                {"old_sha", "new_sha", "installation", "workspace"},
                {"old_sha", "new_sha", "installation", "workspace", "recovery_receipt"})
                or ("cloud_key_reused" in intent and intent["cloud_key_reused"] is not True)
                or intent["old_sha"] != entry.name or not isinstance(intent["new_sha"], str)
                or re.fullmatch(r"[0-9a-f]{40}", intent["new_sha"]) is None
                or intent["new_sha"] == entry.name
                or _read_json(entry / "completed.json") != {"new_sha": intent["new_sha"], "state": "RETIRED", "old_sha": entry.name}):
            raise BootstrapError("incomplete or invalid retirement audit")
        if "finalized_native_advance" in intent:
            if ("recovery_receipt" not in intent
                    or intent["workspace"].get("state") != "CLOSED_NATIVE_ONLY_VENDOR_UPLOAD"):
                raise BootstrapError("finalized advance requires native closure receipt")
            _finalized_advance_module().validate_saved(intent["finalized_native_advance"], entry.name)
        if 'retirement_policy' in intent or 'public_keys' in intent:
            if (intent.get('retirement_policy') != 'no-backup-v1'
                    or any(os.path.lexists(path) for path in _archives(entry.name))):
                raise BootstrapError('invalid no-backup retirement audit')
            saved = intent.get('installation')
            expected_config = {'.','known_hosts','loopback.conf','authorized-release.json','cloud.pub','loopback.pub'}
            if (not isinstance(saved, dict) or set(saved) != {'config','library'}
                    or not isinstance(saved['config'], dict) or set(saved['config']) != expected_config
                    or not isinstance(saved['library'], dict) or set(saved['library']) != {'.',INSTALLED.name}):
                raise BootstrapError('invalid retired installation hash audit')
            for part in saved.values():
                for name, value in part.items():
                    if (not isinstance(value,dict) or set(value) != {'uid','gid','mode','inode','device','sha256'}
                            or any(type(value[key]) is not int or value[key] < 0 for key in ('uid','gid','mode','inode','device'))
                            or (value['sha256'] is not None if name=='.' else not isinstance(value['sha256'],str) or re.fullmatch(r'[0-9a-f]{64}',value['sha256']) is None)):
                        raise BootstrapError('invalid retired installation hash fields')
            expected_executor = hashlib.sha256((canonical_source(entry.name) / 'scripts/trusted_release_server.py').read_bytes()).hexdigest()
            if saved['library'][INSTALLED.name]['sha256'] != expected_executor:
                raise BootstrapError('retired executor audit differs from canonical source')
            public_keys = _retired_public_keys(entry.name, intent)
            secure(AUTHORIZED, private=True)
            for name, public in public_keys.items():
                if public.split()[1] in AUTHORIZED.read_text():
                    if name != 'cloud.pub' or intent.get('cloud_key_reused') is not True:
                        raise BootstrapError('retired identity is still authorized')
                    _persistent_cloud_successor(entry.name, public)
        elif _installation_evidence(entry.name, *_archives(entry.name), history_only=True) != intent["installation"]:
            raise BootstrapError("retired installation evidence changed")
        if "review_maintenance_advance" in intent or "review_maintenance_release_closure" in intent:
            if ("recovery_receipt" in intent or "finalized_native_advance" in intent
                    or ("review_maintenance_advance" in intent and "review_maintenance_release_closure" in intent)):
                raise BootstrapError("review advance cannot mix closure authorities")
            field = "review_maintenance_release_closure" if "review_maintenance_release_closure" in intent else "review_maintenance_advance"
            module = _review_release_closure_module() if field == "review_maintenance_release_closure" else _review_advance_module()
            module.profile(entry.name, intent["new_sha"])
            _, evidence, installation = module.saved(sys.modules[__name__], canonical_source(intent["new_sha"]),
                intent["new_sha"], proof=intent[field])
            observed = module.workspace(evidence)
            if installation != intent["installation"]:
                raise BootstrapError("review advance retired installation differs")
        else:
            observed = _workspace_evidence(entry.name, recovery_receipt=intent.get("recovery_receipt"), historical=True)
        if observed != intent["workspace"]:
            raise BootstrapError("retired consumption evidence changed")
        history[entry.name] = intent
    for old_sha, proof in successful.items():
        retired = history.get(old_sha)
        if (not isinstance(retired, dict)
                or retired.get("new_sha") != proof["new_sha"]
                or _digest_json(retired.get("installation")) != proof["installation_sha256"]
                or retired.get("workspace") != proof["workspace"]):
            raise BootstrapError("successful identity closure lacks matching canonical retirement")
    return history


def _retired_config(sha, evidence):
    if evidence.get("format") == "pinned-legacy":
        return STATE / "retired" / sha / "config"
    return _archives(sha)[0]


def _assert_fresh_sha(sha, history):
    recovery = _native_rotation_recovery()
    successful = _successful_auth_revocation_history()
    if (os.path.lexists(STATE / sha) or sha in history
            or any(item["new_sha"] == sha for item in successful.values())
            or (recovery is not None and recovery['publisher_sha'] == sha)
            or sha in LEGACY_RETIREMENTS
            or any(item.get("new_sha") == sha for item in history.values())
            or any(os.path.lexists(path) for path in _archives(sha))):
        raise BootstrapError("release SHA already used; retry forbidden")


def _assert_known_activity(history, old_sha=None):
    assert_exam_recovery_history()
    assert_xiaoqihou_briefing_history()
    for path in STATE.iterdir():
        if re.fullmatch(r"[0-9a-f]{40}", path.name) and path.name not in history and path.name != old_sha:
            raise BootstrapError("existing release activity requires operator review")


def _exam_history_server():
    path = Path(__file__).with_name('trusted_release_server.py')
    secure(path)
    if os.path.lexists(path.parent / '__pycache__'):
        raise BootstrapError('cached exam history code forbidden')
    spec = importlib.util.spec_from_file_location('exam_history_server', path)
    server = importlib.util.module_from_spec(spec)
    exec(compile(path.read_bytes(), str(path), 'exec', dont_inherit=True), server.__dict__)
    return server


def assert_exam_recovery_history(*, _exam_pending_rotation=None):
    if os.path.lexists(STATE / 'exam-forward-closures'):
        try:
            closure = _exam_forward_module()
            if _exam_pending_rotation is None:
                closure.history_evidence(sys.modules[__name__])
            else:
                closure.validate_pending_rotation(sys.modules[__name__], _exam_pending_rotation)
        except Exception:
            raise BootstrapError('exam closure history is incomplete or invalid') from None
        return
    if _exam_pending_rotation is not None:
        raise BootstrapError('pending exam rotation requires complete closure')
    # Neither service recovery nor read-credential renewal retires the failed
    # release. No completion string grants ordinary rotation/replay authority.
    # lexists also blocks broken links and unexpected file types after reboot.
    if any(os.path.lexists(STATE / name) for name in
           ('exam-a8-forward-acl-v1', 'exam-a8-read-credential-v1')):
        raise BootstrapError('exam recovery requires independent closure')
    server = _exam_history_server()
    try:
        server.assert_no_competing_exam_recovery(STATE)
    except server.LaunchError:
        raise BootstrapError('competing exam recovery evidence or unsafe inventory') from None


def assert_xiaoqihou_briefing_history():
    if not os.path.lexists(STATE / 'review-xiaoqihou-briefings'):
        return
    path=Path(__file__).with_name('trusted_release_server.py')
    secure(path)
    if os.path.lexists(path.parent / '__pycache__'):
        raise BootstrapError('cached maintenance history code forbidden')
    spec=importlib.util.spec_from_file_location('xiaoqihou_history_server',path)
    server=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    server.assert_xiaoqihou_briefing_history(STATE)


def assert_frontend_rebuild_history(*, backup_memo=None, _exam_pending_rotation=None):
    exam_options = {} if _exam_pending_rotation is None else {'_exam_pending_rotation': _exam_pending_rotation}
    assert_exam_recovery_history(**exam_options)
    assert_xiaoqihou_briefing_history()
    if not any(os.path.lexists(STATE / name) for name in ("frontend-rebuilds", "frontend-publications", "neo-wechat")):
        return
    path = Path(__file__).with_name("trusted_release_server.py")
    secure(path)
    spec = importlib.util.spec_from_file_location("frontend_history_server", path)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    server.assert_frontend_rebuild_history(STATE, backup_memo=backup_memo, **exam_options)


def assert_ota_history(*, _exam_pending_rotation=None):
    exam_options = {} if _exam_pending_rotation is None else {'_exam_pending_rotation': _exam_pending_rotation}
    assert_exam_recovery_history(**exam_options)
    assert_xiaoqihou_briefing_history()
    if not any(os.path.lexists(STATE / name) for name in
               ("ota", "retained-testflight", "ota-preintent-failure-closures")):
        return
    path = Path(__file__).with_name("trusted_release_server.py")
    secure(path)
    if os.path.lexists(path.parent / "__pycache__"):
        raise BootstrapError("cached publication history code forbidden")
    spec = importlib.util.spec_from_file_location("ota_history_server", path)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    server.assert_ota_history(**exam_options)


def _assert_idle(*, backup_memo=None, _exam_pending_rotation=None):
    exam_options = {} if _exam_pending_rotation is None else {'_exam_pending_rotation': _exam_pending_rotation}
    assert_exam_recovery_history(**exam_options)
    assert_xiaoqihou_briefing_history()
    assert_frontend_rebuild_history(backup_memo=backup_memo, **exam_options)
    assert_ota_history(**exam_options)
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


def _review_advance_module():
    path = Path(__file__).absolute().with_name("review_maintenance_advance.py")
    secure(path)
    if os.path.lexists(path.parent / "__pycache__"):
        raise BootstrapError("cached review advance forbidden")
    spec = importlib.util.spec_from_file_location("reviewed_maintenance_advance", path)
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    return module


def advance_review_maintenance(old_sha, sha, *, evidence_sha256=None, accepted=False):
    module = _review_advance_module()
    module.profile(old_sha, sha)
    source, server = reviewed_source(sha)
    _run(["/usr/bin/python3.12", "-I", str(source / "scripts/trusted_release_gate.py"),
          "--sha", sha, "--workflow-sha", sha, "--observed-main", sha])
    lock = STATE / "launcher.lock"
    secure(lock, private=True)
    fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
    build_fd = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build_fd = _acquire_existing_build_lock(old_sha)
        if build_fd is None:
            raise BootstrapError("original review build lock required")
        def check():
            _assert_original_lock(lock, fd)
            _assert_original_lock(STATE / old_sha / "build.lock", build_fd)
        check()
        history = _retired_history()
        _assert_fresh_sha(sha, history)
        _assert_known_activity(history, old_sha)
        adapter = module.make_adapter(sys.modules[__name__], source, server, sha, check)
        return module.advance(adapter, accepted=accepted, evidence_sha256=evidence_sha256)
    finally:
        if build_fd is not None:
            os.close(build_fd)
        os.close(fd)


def _review_release_rotation_input():
    """Bounded stdin envelope; neither secret is included in results or argv."""
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise BootstrapError("invalid protected release input")
            value[key] = item
        return value
    try:
        raw = sys.stdin.buffer.read(8193)
        if len(raw) > 8192:
            raise BootstrapError("invalid protected release input")
        value = json.loads(raw, object_pairs_hook=unique)
        if (not isinstance(value, dict) or set(value) != {'receipt', 'github_token'}
                or not isinstance(value['receipt'], str)
                or re.fullmatch('[a-f0-9]{64}', value['receipt']) is None
                or not isinstance(value['github_token'], str)
                or re.fullmatch('[A-Za-z0-9_.-]{1,4096}', value['github_token']) is None):
            raise BootstrapError("invalid protected release input")
        return value
    except (ValueError, OSError, AttributeError):
        raise BootstrapError("invalid protected release input") from None


def _review_release_closure_module():
    path = Path(__file__).absolute().with_name("review_maintenance_release_closure.py")
    secure(path)
    if os.path.lexists(path.parent / "__pycache__"):
        raise BootstrapError("cached review advance forbidden")
    spec = importlib.util.spec_from_file_location("reviewed_maintenance_release_closure", path)
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    return module


def close_review_maintenance_for_release(old_sha, sha, *, evidence_sha256=None, accepted=False, accept_unknown=False, token_stdin=False):
    module = _review_release_closure_module()
    module.profile(old_sha, sha)
    source, server = reviewed_source(sha)
    gate = _predeploy_module(source, 'trusted_release_gate.py')
    token = gate._stdin_token() if token_stdin else None
    get_json = (lambda url: gate._get_json(url, token=token)) if token is not None else gate._get_json
    gate.verify_release(sha, sha, observed_main=sha, _get_json=get_json)
    lock = STATE / "launcher.lock"
    secure(lock, private=True)
    fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
    build_fd = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build_fd = _acquire_existing_build_lock(old_sha)
        if build_fd is None:
            raise BootstrapError("original review build lock required")
        def check():
            _assert_original_lock(lock, fd)
            _assert_original_lock(STATE / old_sha / "build.lock", build_fd)
        check()
        history = _retired_history()
        _assert_fresh_sha(sha, history)
        _assert_known_activity(history, old_sha)
        adapter = module.make_adapter(sys.modules[__name__], source, server, sha, check)
        return module.advance(adapter, accepted=accepted, accept_unknown=accept_unknown,
                              without_demo=accepted, evidence_sha256=evidence_sha256)
    finally:
        if build_fd is not None:
            os.close(build_fd)
        os.close(fd)


def _finalized_advance_module():
    path = Path(__file__).absolute().with_name("native_finalized_advance.py")
    secure(path)
    if os.path.lexists(path.parent / "__pycache__"):
        raise BootstrapError("cached finalized advance proof forbidden")
    spec = importlib.util.spec_from_file_location("reviewed_finalized_advance", path)
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    return module


def _frontend_live_seal_binding(source, server, *, active_operation=None):
    modules = {}
    for name in ('trusted_frontend_rebuild', 'trusted_frontend_publish'):
        path = source / 'scripts' / (name + '.py')
        secure(path)
        spec = importlib.util.spec_from_file_location('seal_' + name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules[name] = module
    frontend = server.PRODUCTION / 'frontend'
    for name in ('.next', 'node_modules'):
        server._frontend_publication_backup_digest(frontend / name, live=True)
    digest = modules['trusted_frontend_publish'].bundle_digest(frontend, modules['trusted_frontend_rebuild'])
    root = STATE / 'frontend-publications'
    candidates = []
    for operation in root.iterdir():
        complete = server.frontend_publication_completion(STATE, operation.name)
        if complete.get('artifact_digest') == digest:
            candidates.append(operation.name)
    if active_operation is not None:
        if active_operation not in candidates:
            raise BootstrapError('explicit frontend operation does not match live artifact')
    elif len(candidates) == 1:
        active_operation = candidates[0]
    else:
        raise BootstrapError('frontend live binding is absent or ambiguous')
    return active_operation, digest


def frontend_history_seal(sha, *, active_operation=None, inspect=False, checkpoint_sha256=None):
    source, server = reviewed_source(sha)
    _run(['/usr/bin/python3.12', '-I', '-S', '-B', str(source / 'scripts/trusted_release_gate.py'),
          '--sha', sha, '--workflow-sha', sha])
    policy = _read_json(CONFIG / 'authorized-release.json')
    server.validate_policy(policy, now=int(time.time()))
    secure(STATE / 'launcher.lock', private=True)
    fd = os.open(STATE / 'launcher.lock', os.O_RDWR | os.O_NOFOLLOW)
    build_fd = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build_fd = _acquire_existing_build_lock(policy['sha'])
        def locks():
            _assert_original_lock(STATE / 'launcher.lock', fd)
            if build_fd is not None:
                _assert_original_lock(STATE / policy['sha'] / 'build.lock', build_fd)
            elif os.path.lexists(STATE / policy['sha'] / 'build.lock'):
                raise BootstrapError('historical build lock appeared')
        locks()
        if os.path.lexists(BUSINESS_LEASE):
            raise BootstrapError('active business release blocks history sealing')
        _recovery_process_proof()
        assert_ota_history()
        if inspect:
            result = server.inspect_frontend_history_seal(STATE)
        else:
            memo = {}
            if checkpoint_sha256 is None:
                server.assert_frontend_rebuild_history(STATE, backup_memo=memo)
            else:
                snapshot = server._frontend_history_seal(STATE, recovery=True)
                server.assert_frontend_rebuild_history(STATE, _seal_snapshot=snapshot)
            active_operation, digest = _frontend_live_seal_binding(source, server, active_operation=active_operation)
            locks()
            if os.path.lexists(BUSINESS_LEASE):
                raise BootstrapError('business release appeared during seal validation')
            _recovery_process_proof()
            assert_ota_history()
            if checkpoint_sha256 is None:
                result = server.seal_frontend_publication_history(
                    STATE, active_operation=active_operation, live_digest=digest,
                    sealed_by_sha=sha, backup_memo=memo)
            else:
                result = server.finish_frontend_history_seal(
                    STATE, checkpoint_sha256=checkpoint_sha256, live_digest=digest)
        locks()
        return result
    finally:
        if build_fd is not None:
            os.close(build_fd)
        os.close(fd)


def _close_successful_identity(old_sha, new_sha, workspace_completed_sha256, check_locks):
    workspace = _workspace_evidence(old_sha)
    completed_path = STATE / old_sha / "completed.json"
    if (workspace.get("state") != "SUCCEEDED"
            or hashlib.sha256(completed_path.read_bytes()).hexdigest() != workspace_completed_sha256):
        raise BootstrapError("successful workspace receipt differs from fixed release evidence")
    policy = _read_json(CONFIG / "authorized-release.json")
    old_source = canonical_source(old_sha)
    executor_digest = hashlib.sha256(
        (old_source / "scripts/trusted_release_server.py").read_bytes()).hexdigest()
    config_names = {
        "authorized-release.json", "cloud.pub", "loopback.pub",
        "known_hosts", "loopback.conf", "loopback.key",
    }
    pre_installation = {
        "config": _inventory(CONFIG, config_names),
        "library": _inventory(INSTALLED.parent, {INSTALLED.name}),
    }
    if (not isinstance(policy, dict)
            or set(policy) != {"sha", "expires_at", "executor_sha256"}
            or policy.get("sha") != old_sha
            or type(policy.get("expires_at")) is not int
            or policy["expires_at"] < 0
            or policy.get("executor_sha256") != executor_digest
            or pre_installation["library"][INSTALLED.name]["sha256"] != executor_digest):
        raise BootstrapError("successful identity installation differs from fixed release evidence")
    key = CONFIG / "loopback.key"
    secure(key, private=True)
    identity = key.lstat()
    if identity.st_nlink != 1:
        raise BootstrapError("successful identity private key has unexpected links")
    public = (CONFIG / "loopback.pub").read_text().strip()
    cloud = (CONFIG / "cloud.pub").read_text().strip()
    for current_public in (cloud, public):
        validate_install(old_sha, 1, current_public, now=0)
    derived = _run(["/usr/bin/ssh-keygen", "-y", "-f", str(key)], capture=True).stdout.strip()
    if derived.split()[:2] != public.split()[:2]:
        raise BootstrapError("successful identity private key differs from public key")
    authorized_digest = hashlib.sha256(AUTHORIZED.read_bytes()).hexdigest()
    expected_lines = key_lines(policy["expires_at"], cloud, public)
    authorized_lines = AUTHORIZED.read_text().splitlines()
    for current_public, expected_line in zip((cloud, public), expected_lines):
        if [line for line in authorized_lines if current_public.split()[1] in line] != [expected_line]:
            raise BootstrapError("successful identity authorization differs from managed policy")
    _assert_backend_terminated_or_unstarted(old_sha)
    proof = {
        "old_sha": old_sha,
        "new_sha": new_sha,
        "workspace": workspace,
        "workspace_completed_sha256": workspace_completed_sha256,
        "old_executor_sha256": executor_digest,
        "old_authorized_sha256": authorized_digest,
        "loopback_public_sha256": hashlib.sha256(public.encode()).hexdigest(),
        "backend_succeeded": True,
    }
    root = STATE / "successful-auth-revocations"
    if not root.exists():
        root.mkdir(mode=0o700)
        _sync_parent(root)
    secure(root)
    record = root / old_sha
    record.mkdir(mode=0o700)
    _sync_parent(record)
    _write(record / "intent.json", json.dumps(proof, sort_keys=True).encode())
    check_locks()
    if (pre_installation != {
            "config": _inventory(CONFIG, config_names),
            "library": _inventory(INSTALLED.parent, {INSTALLED.name}),
        }
            or _workspace_evidence(old_sha) != workspace
            or hashlib.sha256(completed_path.read_bytes()).hexdigest() != workspace_completed_sha256
            or hashlib.sha256(AUTHORIZED.read_bytes()).hexdigest() != authorized_digest):
        raise BootstrapError("successful identity evidence changed before revocation")
    _assert_idle()
    check_locks()
    if _revoke_locked(old_sha) != {"sha": old_sha, "state": "REVOKED"}:
        raise BootstrapError("successful identity revocation did not complete")
    check_locks()
    secure(key, private=True)
    current = key.lstat()
    if ((current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns)
            != (identity.st_dev, identity.st_ino, identity.st_size,
                identity.st_mtime_ns, identity.st_ctime_ns)):
        raise BootstrapError("successful identity private key changed before destruction")
    key.unlink()
    _sync_parent(key)
    check_locks()
    installation = _installation_evidence(old_sha, CONFIG, INSTALLED.parent)
    if (_workspace_evidence(old_sha) != workspace
            or hashlib.sha256(completed_path.read_bytes()).hexdigest() != workspace_completed_sha256):
        raise BootstrapError("successful identity evidence changed after revocation")
    _write(record / "completed.json", json.dumps({
        "old_sha": old_sha,
        "new_sha": new_sha,
        "state": "SUCCESSFUL_IDENTITY_REVOKED",
        "installation_sha256": _digest_json(installation),
    }, sort_keys=True).encode())
    check_locks()
    return installation


def rotate(old_sha, sha, expiry, public, *, recovery_receipt=None, finalized_production_sha=None, backend_ci=False, review_advance_receipt=None, review_release_closure_receipt=None, review_release_github_token=None, dinner_guard_github_token=None, successful_workspace_sha256=None):
    validate_install(sha, expiry, public, now=int(time.time()))
    if not isinstance(old_sha, str) or re.fullmatch(r"[0-9a-f]{40}", old_sha) is None or old_sha == sha:
        raise BootstrapError("distinct exact old and new reviewed SHAs required")
    if dinner_guard_github_token is not None:
        if (old_sha != _dinner_profile_module(old_sha).FAILED or recovery_receipt is None
                or finalized_production_sha is not None or backend_ci
                or review_advance_receipt is not None or review_release_closure_receipt is not None
                or review_release_github_token is not None
                or not isinstance(dinner_guard_github_token, str)
                or re.fullmatch('[A-Za-z0-9_.-]{1,4096}', dinner_guard_github_token) is None):
            raise BootstrapError("exclusive dinner retirement token and receipt required")
    if review_release_github_token is not None and (review_release_closure_receipt is None
            or not isinstance(review_release_github_token, str)
            or re.fullmatch('[A-Za-z0-9_.-]{1,4096}', review_release_github_token) is None):
        raise BootstrapError("ephemeral token requires fixed release closure")
    if review_release_closure_receipt is not None and (review_advance_receipt is not None
            or recovery_receipt is not None or finalized_production_sha is not None or backend_ci):
        raise BootstrapError("release closure requires exclusive exact candidate authority")
    if successful_workspace_sha256 is not None:
        if (any(value is not None for value in (recovery_receipt, finalized_production_sha,
                review_advance_receipt, review_release_closure_receipt,
                review_release_github_token, dinner_guard_github_token))
                or backend_ci
                or not isinstance(successful_workspace_sha256, str)
                or re.fullmatch(r"[0-9a-f]{64}", successful_workspace_sha256) is None):
            raise BootstrapError("successful identity closure requires one exact workspace receipt")
    source, server = reviewed_source(sha)
    review_module = _review_release_closure_module() if review_release_closure_receipt is not None else None
    if review_module is not None:
        review_module.profile(old_sha, sha)
    if review_advance_receipt is not None:
        if recovery_receipt is not None or finalized_production_sha is not None or backend_ci:
            raise BootstrapError("review advance requires exclusive exact candidate CI")
        _review_advance_module().profile(old_sha, sha)
    if dinner_guard_github_token is not None:
        gate = _predeploy_module(source, 'trusted_release_gate.py')
        gate.verify_release(sha, sha, observed_main=sha,
            _get_json=lambda url: gate._get_json(url, token=dinner_guard_github_token))
    elif review_release_github_token is not None:
        gate = _predeploy_module(source, 'trusted_release_gate.py')
        gate.verify_release(sha, sha, observed_main=sha,
            _get_json=lambda url: gate._get_json(url, token=review_release_github_token))
    elif backend_ci:
        if recovery_receipt is not None or finalized_production_sha is not None:
            raise BootstrapError("backend CI admission cannot replace recovery or native closure gates")
        _run(["/usr/bin/python3.12", "-I", "-S", "-B", str(source / "scripts/trusted_backend_admission.py"), "--sha", sha])
    else:
        _run(["/usr/bin/python3.12", "-I", str(source / "scripts/trusted_release_gate.py"),
              "--sha", sha, "--workflow-sha", sha, "--observed-main", sha])
    secure(STATE)
    # Rotation may not recreate the global lock inode of an existing install.
    secure(STATE / "launcher.lock", private=True)
    fd = os.open(STATE / "launcher.lock", os.O_RDWR | os.O_NOFOLLOW)
    build_fd = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build_fd = _acquire_existing_build_lock(old_sha)
        build_path = STATE / old_sha / "build.lock"
        def check_locks():
            _assert_original_lock(STATE / "launcher.lock", fd)
            if build_fd is None:
                if os.path.lexists(build_path):
                    raise BootstrapError("historical build lock appeared")
            else:
                _assert_original_lock(build_path, build_fd)
        # Ephemeral memo shared only by the two checks under this launcher lock.
        backup_memo = {}
        def check_idle(phase, *, exam_pending=None):
            began = time.monotonic()
            print(json.dumps({"stage": phase, "state": "STARTED"}), file=sys.stderr, flush=True)
            options = {} if exam_pending is None else {'_exam_pending_rotation': exam_pending}
            _assert_idle(backup_memo=backup_memo, **options)
            print(json.dumps({"stage": phase, "state": "VERIFIED",
                              "elapsed_seconds": round(time.monotonic() - began, 2),
                              "memoized_backups": len(backup_memo)}), file=sys.stderr, flush=True)
        check_locks()
        history = _retired_history()
        _assert_fresh_sha(sha, history)
        _assert_known_activity(history, old_sha)
        archive_config, archive_library = _archives(old_sha)
        if old_sha in history or any(os.path.lexists(path) for path in (archive_config, archive_library)):
            raise BootstrapError("old retirement already attempted")
        check_locks()
        installation = (None if successful_workspace_sha256 is not None
                        else _installation_evidence(old_sha, CONFIG, INSTALLED.parent))
        review_advance = None
        review_evidence = None
        if review_advance_receipt is not None or review_release_closure_receipt is not None:
            review_module = review_module or _review_advance_module()
            review_advance, review_evidence, bound_installation = review_module.saved(
                sys.modules[__name__], source, sha, receipt=review_release_closure_receipt if review_release_closure_receipt is not None else review_advance_receipt)
            if bound_installation != installation:
                raise BootstrapError("review advance installation changed")
        advanced = finalized_production_sha is not None
        if advanced and recovery_receipt is None:
            raise BootstrapError("finalized advance requires the original native closure receipt")
        def inspect_workspace():
            if review_advance is not None:
                _, current, _ = review_module.saved(sys.modules[__name__], source, sha, proof=review_advance)
                return review_module.workspace(current)
            if advanced:
                return _workspace_evidence(old_sha, recovery_receipt=recovery_receipt, historical=True)
            return _workspace_evidence(old_sha, recovery_receipt=recovery_receipt)
        workspace = inspect_workspace()
        if dinner_guard_github_token is not None and workspace.get("state") != "CLOSED_DINNER_GUARD_RELEASE":
            raise BootstrapError("dinner rotation token requires completed dinner closure")
        advance = None
        if advanced:
            if workspace.get("state") != "CLOSED_NATIVE_ONLY_VENDOR_UPLOAD":
                raise BootstrapError("finalized advance is limited to a closed native workspace")
            advance = _finalized_advance_module().inspect(sys.modules[__name__], source, old_sha, finalized_production_sha)
        def check_advance():
            if review_advance is not None:
                review_module.verify_live(sys.modules[__name__], source, server, sha,
                                                     check_locks, review_evidence)
            if advanced and _finalized_advance_module().inspect(
                    sys.modules[__name__], source, old_sha, finalized_production_sha) != advance:
                raise BootstrapError("finalized production evidence changed during rotation")
        if review_advance is not None:
            check_advance()
        check_locks()
        if recovery_receipt is not None and workspace["state"] not in {"RECOVERED_PREPARATION_FAILURE", "CLOSED_PREDEPLOY_ATTESTATION_FAILURE", "CLOSED_RESTORED_RELEASE", "CLOSED_UNCHANGED_RELEASE", "CLOSED_UNKNOWN_REVIEW_MAINTENANCE", "ACKNOWLEDGED_LOST_CLOSURE_RECEIPT", "CLOSED_PARTIAL_LAYA_ORPHANED_LEASE", "CLOSED_NATIVE_ONLY_VENDOR_UPLOAD", "CLOSED_RETAINED_CANDIDATE_FAILURE", "CLOSED_ROLLED_BACK_RELEASE", "CLOSED_DINNER_GUARD_RELEASE", "CLOSED_EXAM_FORWARD_FAILURE"}:
            raise BootstrapError("recovery receipt only applies to historical recovery")
        current_keys = {name: (CONFIG / name).read_text().strip()
                        for name in ('cloud.pub', 'loopback.pub')}
        identity_history = [current_keys, *(_retired_public_keys(old, item) for old, item in history.items())]
        retired_keys = {public for keys in identity_history for public in keys.values()}
        loopback_keys = {keys['loopback.pub'] for keys in identity_history}
        reuse_cloud = expiry == 0 and public == (CONFIG / "cloud.pub").read_text().strip()
        if public in loopback_keys or (public in retired_keys and not reuse_cloud):
            raise BootstrapError("only the current cloud identity may be reused for persistent authorization")
        if successful_workspace_sha256 is None:
            _installation_inputs(sha, expiry, public)
        else:
            secure(AUTHORIZED, private=True)
            authorized = AUTHORIZED.read_text()
            if public.split()[1] in authorized:
                if not reuse_cloud:
                    raise BootstrapError("new cloud identity is already authorized")
                policy = _read_json(CONFIG / "authorized-release.json")
                expected_cloud, _expected_loopback = key_lines(
                    policy["expires_at"], current_keys["cloud.pub"], current_keys["loopback.pub"])
                matches = [line for line in authorized.splitlines()
                           if public.split()[1] in line]
                if matches != [expected_cloud]:
                    raise BootstrapError("current cloud identity authorization differs before rotation")
            secure(HOST_PUBLIC)
            host = " ".join(HOST_PUBLIC.read_text().split()[:2])
            validate_install(sha, expiry, host, now=int(time.time()))
        if os.path.lexists(STATE / 'frontend-history-seal'):
            sealed = server._frontend_history_seal(STATE)
            observed = server.assert_frontend_publication_history(STATE, backup_memo=backup_memo)
            if set(observed) != set(sealed['payload']['records']):
                # Only complete, validated new publications reach this point.
                # Refresh before any retirement intent or business consumption.
                # Other incomplete histories must block before writing a seal.
                _assert_idle(backup_memo=backup_memo)
                if os.path.lexists(BUSINESS_LEASE):
                    raise BootstrapError('business release blocks history refresh')
                _recovery_process_proof()
                active, live = _frontend_live_seal_binding(source, server)
                check_locks()
                if os.path.lexists(BUSINESS_LEASE):
                    raise BootstrapError('business release appeared during history refresh')
                _recovery_process_proof()
                assert_ota_history()
                server.seal_frontend_publication_history(
                    STATE, active_operation=active, live_digest=live,
                    sealed_by_sha=sha, backup_memo=backup_memo)
        check_idle("history-before-intent")
        if successful_workspace_sha256 is not None:
            installation = _close_successful_identity(
                old_sha, sha, successful_workspace_sha256, check_locks)
        # Intent is durable before discarding the revoked current installation.
        # No backup, rollback, or automatic resume: a partial rotation blocks.
        root = STATE / "retired"
        if not root.exists():
            root.mkdir(mode=0o700)
            _sync_parent(root)
        record = root / old_sha
        record.mkdir(mode=0o700)
        _sync_parent(record)
        intent = {"old_sha": old_sha, "new_sha": sha, "installation": installation, "workspace": workspace,
                  "retirement_policy": "no-backup-v1", "public_keys": current_keys}
        if reuse_cloud:
            intent["cloud_key_reused"] = True
        if recovery_receipt is not None:
            intent["recovery_receipt"] = recovery_receipt
        if advanced:
            intent["finalized_native_advance"] = advance
        if review_advance is not None:
            intent["review_maintenance_release_closure" if review_release_closure_receipt is not None else "review_maintenance_advance"] = review_advance
        check_locks()
        _write(record / "intent.json", json.dumps(intent, sort_keys=True).encode())
        check_locks()
        check_idle('history-before-retirement', exam_pending=(
            intent if workspace.get('state') == 'CLOSED_EXAM_FORWARD_FAILURE' else None))
        check_locks()
        check_advance()
        _discard_current_installation(old_sha, installation)
        check_locks()
        # This certifies retirement, not installation success. Reserve the new
        # SHA permanently, and finish audit writes before publishing any key.
        _write(record / "completed.json", json.dumps({"old_sha": old_sha, "new_sha": sha,
               "state": "RETIRED"}, sort_keys=True).encode())
        if workspace.get("state") in {"CLOSED_UNCHANGED_RELEASE", "CLOSED_DINNER_GUARD_RELEASE", "CLOSED_NATIVE_ONLY_VENDOR_UPLOAD", "CLOSED_EXAM_FORWARD_FAILURE"}:
            # The no-copy closure already proved the revoked installation before
            # deletion. Reconsume its durable retirement audit now: this checks
            # canonical executor/public-key hashes, original closure receipt and
            # workspace bindings without demanding removed installation files.
            retired = _retired_history().get(old_sha)
            if retired != intent:
                raise BootstrapError("completed retirement audit changed during rotation")
            after_workspace = retired["workspace"]
        else:
            after_workspace = inspect_workspace()
        if after_workspace != workspace:
            raise BootstrapError("retirement evidence changed during rotation")
        check_advance()
        check_locks()
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


def _prelease_vision_module():
    return _predeploy_module(Path(__file__).resolve().parents[1], 'prelease_vision_history_proof.py')


def _is_predeploy_workspace(workspace):
    return workspace.get('profile') in {'predeploy-attestation-failure', 'prelease-vision-history-failure'}


def _predeploy_workspace_production(workspace, old_sha, production_sha, source):
    if workspace.get('profile') == 'prelease-vision-history-failure':
        return _predeploy_production_proof(old_sha, production_sha, source, prelease_vision=True)
    return _predeploy_production_proof(old_sha, production_sha, source)


def _recoverable_clone_evidence(sha):
    source = canonical_source(sha)
    digest = hashlib.sha256((source / "scripts/trusted_release_server.py").read_bytes()).hexdigest()
    if sha == '17f9c29f32123ada929fac9af61a17e6521094d8':
        return _prelease_vision_module().inspect(sys.modules[__name__], sha, source)
    if digest in PREDEPLOY_ATTESTATION_IMPLEMENTATIONS:
        return _predeploy_attestation_evidence(sha, source, digest)
    phase_timeout = digest in PHASE_CLONE_TIMEOUT_EXECUTORS
    phase_completed = digest in PHASE_CLONE_COMPLETED_EXECUTORS
    if not phase_timeout and not phase_completed:
        return _legacy_clone_evidence(sha)
    workspace = STATE / sha
    secure(workspace)
    required = {"started.json", "preparation-started.json", "completed.json",
                "preparation.log", "home", "source"}
    if (not workspace.is_dir() or stat.S_IMODE(workspace.lstat().st_mode) != 0o700
            or {p.name for p in workspace.iterdir()} != required):
        raise BootstrapError("phase clone-only inventory unproven")
    for name, state in (("started.json", "STARTED"), ("preparation-started.json", "PREPARING"),
                        ("completed.json", "NEEDS_OPERATOR")):
        expected = {"sha": sha, "state": state}
        if name == "preparation-started.json":
            expected["executor_sha256"] = digest
        secure(workspace / name, private=True)
        if _read_json(workspace / name) != expected:
            raise BootstrapError("phase clone receipt differs")
    for name in ("home", "source", "source/.git"):
        path = workspace / name
        secure(path)
        if (path.is_symlink() or not path.is_dir()
                or stat.S_IMODE(path.lstat().st_mode) != 0o700):
            raise BootstrapError("phase clone directory is not private")
    if (list((workspace / "home").iterdir())
            or {p.name for p in (workspace / "source").iterdir()} != {".git"}):
        raise BootstrapError("phase clone contains checkout or HOME content")
    log = workspace / "preparation.log"
    secure(log, private=True)
    clone = f"Cloning into '{workspace}/source'...\n"
    if phase_timeout:
        failure = (f"fatal: unable to access '{ORIGIN}/': "
                   "Operation too slow. Less than 1024 bytes/sec transferred the last 30 seconds\n")
        expected_log = ((clone + failure) * 2 + clone).encode()
        profile = "phase-clone-timeout"
    else:
        expected_log = clone.encode()
        # Preserve the existing durable evidence spelling for compatibility;
        # the corrected analysis is that this clone was interrupted at timeout.
        profile = "phase-clone-completed-uncertain"
    if log.stat().st_size != len(expected_log) or log.read_bytes() != expected_log:
        raise BootstrapError("phase clone transcript unproven")
    # Never run Git/imports in this partial tree. Hash every retained object,
    # including .git, with the original ownership/link/size/race checks.
    return {"profile": profile, "executor_sha256": digest,
            "manifest": _preparation_manifest(workspace)}


def _predeploy_attestation_evidence(sha, source, digest):
    workspace = STATE / sha
    required = {"started.json", "completed.json", "preparation-started.json", "prepared.json",
                "deployment-started.json", "preparation.log", "deployment.env", "home", "bin", "source"}
    secure(workspace)
    if stat.S_IMODE(workspace.stat().st_mode) != 0o700 or {p.name for p in workspace.iterdir()} != required:
        raise BootstrapError("predeploy attestation inventory unproven")
    for name, state in (("started.json", "STARTED"), ("completed.json", "NEEDS_OPERATOR"),
                        ("preparation-started.json", "PREPARING"), ("prepared.json", "PREPARED"),
                        ("deployment-started.json", "DEPLOYING")):
        expected = {"sha": sha, "state": state}
        if name == "preparation-started.json": expected["executor_sha256"] = digest
        secure(workspace / name, private=True)
        if _read_json(workspace / name) != expected:
            raise BootstrapError("predeploy attestation phase differs")
    for name in ("home", "bin", "source"):
        secure(workspace / name)
        if stat.S_IMODE((workspace / name).stat().st_mode) != 0o700:
            raise BootstrapError("predeploy private directory required")
    if list((workspace / "home").iterdir()) or {p.name for p in (workspace / 'bin').iterdir()} != {'ssh', 'scp', 'python3'}:
        raise BootstrapError("predeploy tool inventory differs")
    for command in ('ssh', 'scp', 'python3'):
        path = workspace / 'bin' / command
        # Executable wrappers are root-private 0700, not 0600 configuration.
        secure(path)
        target = '/usr/bin/python3.12' if command == 'python3' else '/usr/bin/' + command
        args = '' if command == 'python3' else ' -F /etc/reva-release/loopback.conf'
        if not stat.S_ISREG(path.lstat().st_mode) or path.read_bytes() != f'#!/bin/sh\nexec {target}{args} "$@"\n'.encode() or stat.S_IMODE(path.stat().st_mode) != 0o700:
            raise BootstrapError('predeploy tool bytes differ')
    expected_gate = PREDEPLOY_ATTESTATION_IMPLEMENTATIONS[digest]
    for name, expected in (('trusted_release_server.py', digest), ('trusted_release_gate.py', expected_gate)):
        for root in (source, workspace / 'source'):
            path = root / 'scripts' / name
            secure(path)
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise BootstrapError('predeploy implementation differs')
    log = workspace / 'preparation.log'
    secure(log, private=True)
    if log.stat().st_size > 16_000_000:
        raise BootstrapError('predeploy transcript exceeds bound')
    raw = log.read_bytes()
    failure = b'release gate: GitHub metadata unavailable\n'
    if not raw.endswith(failure) or raw.count(failure) != 1 or raw.count(b'release gate:') != 1:
        raise BootstrapError('predeploy read-only attestation failure unproven')
    secure(workspace / 'deployment.env', private=True)
    return {'profile': 'predeploy-attestation-failure', 'executor_sha256': digest,
            'gate_sha256': expected_gate, 'manifest': _preparation_manifest(workspace)}


def _recovery_build_identity(sha, workspace):
    path = STATE / sha / "build.lock"
    if workspace.get("profile") in {"phase-clone-timeout", "phase-clone-completed-uncertain", "predeploy-attestation-failure", "prelease-vision-history-failure"}:
        if os.path.lexists(path):
            raise BootstrapError("absent historical build lock appeared")
        return None
    return _recovery_file_identity(path)


def _assert_recovery_build_lock(sha, fd, workspace):
    if workspace.get("profile") in {"phase-clone-timeout", "phase-clone-completed-uncertain", "predeploy-attestation-failure", "prelease-vision-history-failure"}:
        if fd is not None or _recovery_build_identity(sha, workspace) is not None:
            raise BootstrapError("phase clone build lock must remain absent")
    elif fd is None:
        raise BootstrapError("original build lock required")
    else:
        _assert_original_lock(STATE / sha / "build.lock", fd)


def _recovery_process_proof():
    # A detached Git HTTP/index-pack helper need not name the release in argv.
    # Inspect cwd and environment too; never output process data or credentials.
    entries = list(itertools.islice(PROC.iterdir(), 100001))
    if len(entries) > 100000 or not (PROC / str(os.getpid())).is_dir():
        raise BootstrapError("process inventory unavailable")
    needles = (b"reva-release", b"deploy.sh", b"health-app-backup-preflight", b"trusted_review_reset.py", b"seed_demo_account.py",
               b"/var/lock/health-app-release", b"/run/lock/health-app-release",
               b"rollback_release", b"runtime_state_release_transaction",
               b"reva-frontend", b"trusted_frontend_rebuild.py")
    for process in entries:
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            identity = (process / "stat").read_bytes()
            before_fields = identity.rsplit(b")", 1)[-1].split()
            if len(before_fields) < 20 or not before_fields[6].isdigit():
                raise BootstrapError("process identity is malformed")
            chunks = []
            for name in ("cmdline", "environ"):
                with (process / name).open("rb") as stream:
                    chunk = stream.read(1048577)
                if len(chunk) > 1048576:
                    raise BootstrapError("process inspection bound exceeded")
                chunks.append(chunk)
            # Empty argv does not imply a kernel thread. Linux PF_KTHREAD is
            # kernel-owned metadata; every user process still needs cwd/exe.
            kernel_thread = bool(int(before_fields[6]) & 0x00200000)
            if not kernel_thread:
                chunks.append(os.fsencode(os.readlink(process / "cwd")))
                chunks.append(os.fsencode(os.readlink(process / "exe")))
            after = (process / "stat").read_bytes()
            # comm can contain spaces/parentheses. Fields after its final ')'
            # bind PID reuse via starttime and preserve parent/group/session.
            after_fields = after.rsplit(b")", 1)[-1].split()
            if (len(before_fields) < 20 or len(after_fields) < 20
                    or before_fields[1:4] != after_fields[1:4]
                    or before_fields[19] != after_fields[19]):
                raise BootstrapError("process identity changed during inspection")
            if any(needle in chunk for chunk in chunks for needle in needles):
                raise BootstrapError("release descendant still present")
        except FileNotFoundError:
            # A disappearing parent can leave a newly forked/reparented child
            # outside this enumeration. Do not infer quiescence from its exit.
            raise BootstrapError("process inventory changed during inspection") from None
    after_entries = list(itertools.islice(PROC.iterdir(), 100001))
    if (len(after_entries) > 100000
            or {p.name for p in after_entries if p.name.isdigit()} != {p.name for p in entries if p.name.isdigit()}):
        raise BootstrapError("process inventory changed during inspection")


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


def _predeploy_module(source, name):
    path = source / 'scripts' / name
    secure(path)
    if os.path.lexists(path.parent / '__pycache__'):
        raise BootstrapError('cached canonical operator code forbidden')
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('predeploy_' + name.removesuffix('.py'), path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def _predeploy_production_proof(old_sha, production_sha, source, *, prelease_vision=False):
    """Read-only live proof; never execute the failed source or candidate env."""
    server = _predeploy_module(source, 'trusted_release_server.py')
    proof_module = _predeploy_module(source, 'contained_recovery_proof.py')
    # Only the lease-independent read-only methods are used. This label is not
    # an original lease, claim, sealed stage or deployment authorization.
    reader = SimpleNamespace(secure=secure, BUSINESS_LEASE=BUSINESS_LEASE)
    proof = proof_module.RecoveryProof(source, reader, server, old_sha,
                                       production_sha, 'no-predeployment-lease')
    live = server.read_production_env()
    configuration = None
    if prelease_vision:
        configuration = _prelease_vision_module().configuration(sys.modules[__name__], old_sha, production_sha, live)
        expected = None
    else:
        if not any(re.match(r'\s*(?:export\s+)?DECISION_', line, re.I) for line in live.splitlines()):
            raise BootstrapError('unprovable random initial Laya environment')
        normalized = server.invitation_only_config(live)
        lines = [line for line in normalized.splitlines() if not line.startswith(('DEPLOY_SERVER=', 'DEPLOY_PATH='))]
        expected = ('\n'.join(lines) + '\nDEPLOY_SERVER=health\nDEPLOY_PATH=/opt/health-app\n').encode()
        candidate = STATE / old_sha / 'deployment.env'
        secure(candidate, private=True)
        if candidate.read_bytes() != expected:
            raise BootstrapError('predeploy environment does not derive from live production')
    # This read context supplies only the real terminal/transaction path; it
    # neither constructs a fake release stage nor permits mutation methods.
    layout = SimpleNamespace(transaction_root=proof.runtime_root / 'runtime-state-transaction')
    transaction = proof.runtime.ReleaseTransaction(layout, proof.systemd, code_only=True)
    marker = transaction._load_terminal_marker()
    if marker['phase'] != 'COMMITTED' or marker['terminal_sha'] != production_sha:
        raise BootstrapError('predeploy current production terminal differs')
    proof._absent(layout.transaction_root, transaction._preparing_root(),
                  Path('/var/lib/reva-health-evidence-runtime/enabled.env'),
                  Path('/run/reva-health-evidence-activation'),
                  Path('/opt/health-app/backend/.env.reva-release.tmp'))
    if list(proof.runtime_root.glob('runtime-state-transaction.reap-*')):
        raise BootstrapError('predeploy runtime cleanup remains pending')
    for unit in proof_module.UNITS[1:]:
        proof._absent(Path('/run/systemd/system') / (unit + '.d') / '90-reva-health-evidence-activation.conf')
    began = (STATE / old_sha / 'started.json').stat().st_mtime
    units = _predeploy_unit_configuration(proof, transaction, canonical_source(production_sha), began)
    boot_epoch = time.time() - float((PROC / 'uptime').read_text().split()[0])
    cutoff = int((began - boot_epoch - 1) * 1_000_000)
    before = proof.running_services_snapshot()
    for fields in before.values():
        if int(fields['ActiveEnterTimestampMonotonic']) >= cutoff:
            raise BootstrapError('predeploy service started after original consumption')
        if fields.get('NRestarts') not in ('', '0'):
            raise BootstrapError('predeploy service restarted')
        for started in fields.get('processes', {}).values():
            if int(started) / os.sysconf('SC_CLK_TCK') * 1_000_000 >= cutoff:
                raise BootstrapError('predeploy service descendant started after consumption')
    status = _run(['/usr/bin/curl', '--silent', '--show-error', '--fail', '--max-time', '10',
                   '--output', '/dev/null', '--write-out', '%{http_code}',
                   'http://127.0.0.1:8000/api/v1/health'], capture=True)
    if status.stdout != '200':
        raise BootstrapError('predeploy production health unavailable')
    time.sleep(6)
    if (proof.running_services_snapshot() != before or server.read_production_env() != live
            or _predeploy_unit_configuration(proof, transaction, canonical_source(production_sha), began) != units):
        raise BootstrapError('predeploy production changed across stability window')
    if prelease_vision and _prelease_vision_module().configuration(sys.modules[__name__], old_sha, production_sha, live) != configuration:
        raise BootstrapError('prelease configuration changed across stability window')
    secure(transaction._terminal_marker_path(), private=True)
    result = {'environment_sha256': hashlib.sha256(live.encode()).hexdigest(),
            'candidate_environment_sha256': hashlib.sha256(expected).hexdigest() if expected is not None else None,
            'terminal': _recovery_file_identity(transaction._terminal_marker_path()),
            'services': before, 'units': units, 'health_http': 200}
    if configuration is not None:
        result['prelease_configuration'] = configuration
    return result


def _predeploy_unit_configuration(proof, transaction, old_source, began):
    """Bind existing backend units without implying a lease or Laya closure."""
    units = ('health-backend.socket', 'health-backend.service', 'celery-worker.service', 'celery-beat.service')
    result = {}
    def identity(path):
        secure(path)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_mtime >= began:
            raise BootstrapError('predeploy unit configuration changed after consumption')
        return {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'inode': info.st_ino,
                'device': info.st_dev, 'mode': stat.S_IMODE(info.st_mode), 'mtime_ns': info.st_mtime_ns}
    for unit in units:
        fields = {name: proof.systemd.show(unit, name) for name in
                  ('NeedDaemonReload', 'FragmentPath', 'DropInPaths', 'ExecStart', 'EnvironmentFiles', 'Listen')}
        base = Path('/etc/systemd/system') / unit
        if fields['NeedDaemonReload'] != 'no' or fields['FragmentPath'] != str(base):
            raise BootstrapError('predeploy effective unit source differs')
        entry = {'base': identity(base)}
        if unit.endswith('.socket'):
            if fields['DropInPaths'] or fields['ExecStart'] or fields['EnvironmentFiles'] or fields['Listen'] != '127.0.0.1:8000 (Stream)':
                raise BootstrapError('predeploy socket configuration differs')
        else:
            dropins = fields['DropInPaths'].split()
            parent = Path(str(base) + '.d')
            required = [str(parent / name) for name in ('80-reva-health-evidence-runtime.conf', '90-runtime-state.conf')]
            optional = [str(parent / name) for name in ('security-network.conf', 'zzzz-reva-vision-model.conf')]
            if dropins != required + [name for name in optional if name in dropins]:
                raise BootstrapError('predeploy effective drop-in inventory differs')
            for path in dropins:
                entry[path] = identity(Path(path))
            command_path = (old_source / 'infra/systemd' / unit if unit == 'celery-worker.service' else
                            old_source / 'infra/systemd/dropins' / ('health-backend-runtime-state.conf' if unit == 'health-backend.service' else 'celery-beat-runtime-state.conf'))
            secure(command_path)
            commands = re.findall(r'^ExecStart=(.+)$', command_path.read_text(), re.M)
            if len(commands) != 1:
                raise BootstrapError('predeploy canonical command ambiguous')
            command = commands[0]
            fields['ExecStart'] = transaction._stable_exec_start(fields['ExecStart'])
            if fields['ExecStart'] != f'path={command.split()[0]}\nargv[]={command}\nignore_errors=no':
                raise BootstrapError('predeploy effective command differs')
            expected_env = '/opt/health-app/backend/.env (ignore_errors=no) /var/lib/reva-health-evidence-runtime/enabled.env (ignore_errors=yes)'
            if optional[1] in dropins:
                expected_env += ' /var/lib/reva-vision-model/model.env (ignore_errors=no)'
                entry['vision_environment'] = identity(Path('/var/lib/reva-vision-model/model.env'))
            fields['EnvironmentFiles'] = ' '.join(fields['EnvironmentFiles'].splitlines())
            if fields['EnvironmentFiles'] != expected_env:
                raise BootstrapError('predeploy effective environment paths differ')
        entry['effective'] = fields
        result[unit] = entry
    return result


def _predeploy_loopback_key_proof():
    key = CONFIG / 'loopback.key'
    secure(key, private=True)
    before = _recovery_file_identity(key)
    actual = _run(['/usr/bin/ssh-keygen', '-y', '-f', str(key)], capture=True).stdout.strip().split()
    expected = (CONFIG / 'loopback.pub').read_text().strip().split()
    if actual != expected or _recovery_file_identity(key) != before:
        raise BootstrapError('predeploy loopback private/public identity differs')


def _recovery_snapshot(old_sha, sha, production_sha, source):
    if os.path.lexists(BUSINESS_LEASE):
        raise BootstrapError("business lease blocks historical recovery")
    _assert_idle()
    _recovery_process_proof()
    workspace = _recoverable_clone_evidence(old_sha)
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
    if workspace != _recoverable_clone_evidence(old_sha) or os.path.lexists(BUSINESS_LEASE):
        raise BootstrapError("historical evidence changed during proof")
    result = {"old_sha": old_sha, "recovery_sha": sha, "production_sha": production_sha,
            "workspace": workspace, "config": config, "library": library,
            "authorized": _recovery_file_identity(AUTHORIZED),
            "locks": {"launcher": _recovery_file_identity(STATE / "launcher.lock"),
                      "build": _recovery_build_identity(old_sha, workspace)},
            "toolchain": toolchain}
    if _is_predeploy_workspace(workspace):
        _predeploy_loopback_key_proof()
        result['predeploy_production'] = _predeploy_workspace_production(workspace, old_sha, production_sha, source)
    return result


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
        # Missing locks are accepted only by the audited backend-only profile.
        # Do not create one: its durable absence is part of every later proof.
        _assert_recovery_build_lock(old_sha, build_fd, _recoverable_clone_evidence(old_sha))
        record = STATE / "recoveries" / old_sha
        if os.path.lexists(record):
            raise BootstrapError("historical recovery already attempted; no retry")
        history = _retired_history()
        _assert_known_activity(history, old_sha)
        if old_sha in history or any(os.path.lexists(p) for p in _archives(old_sha)):
            raise BootstrapError("historical retirement already attempted")
        evidence = _recovery_snapshot(old_sha, sha, production_sha, source)
        predeploy = _is_predeploy_workspace(evidence['workspace'])
        terminal_state = 'CLOSED_PREDEPLOY_ATTESTATION_FAILURE' if predeploy else 'RECOVERED_PREPARATION_FAILURE'
        digest = _digest_json(evidence)
        _assert_original_lock(lock, fd)
        _assert_recovery_build_lock(old_sha, build_fd, evidence["workspace"])
        if evidence_sha256 is None:
            return {"sha": old_sha, "state": 'RECOVERABLE_PREDEPLOY_ATTESTATION_FAILURE' if predeploy else "RECOVERABLE_PREPARATION_FAILURE", "evidence_sha256": digest}
        if digest != evidence_sha256:
            raise BootstrapError("historical evidence differs from reviewed inspection")
        if not record.parent.exists():
            record.parent.mkdir(mode=0o700)
            _sync_parent(record.parent)
        secure(record.parent)
        record.mkdir(mode=0o700)
        _sync_parent(record)
        # The preimage is memory-only until every terminal fsync has succeeded.
        # A visible but unflushed completed.json cannot authorize rotation.
        receipt = secrets.token_hex(32)
        intent = {**evidence, "evidence_sha256": digest,
                  "receipt_sha256": hashlib.sha256(receipt.encode()).hexdigest()}
        _write(record / "intent.json", json.dumps(intent, sort_keys=True).encode())
        if _recovery_snapshot(old_sha, sha, production_sha, source) != evidence:
            raise BootstrapError("recovery evidence drift after intent; retain operation")
        _assert_original_lock(lock, fd)
        _assert_recovery_build_lock(old_sha, build_fd, evidence["workspace"])
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
        if _recoverable_clone_evidence(old_sha) != evidence["workspace"]:
            raise BootstrapError("recovery changed original evidence")
        _assert_idle()
        _recovery_process_proof()
        _recovery_production_proof(production_sha, source)
        if predeploy and _predeploy_workspace_production(evidence['workspace'], old_sha, production_sha, source) != evidence['predeploy_production']:
            raise BootstrapError('predeploy production changed after revocation')
        _assert_original_lock(lock, fd)
        _assert_recovery_build_lock(old_sha, build_fd, evidence["workspace"])
        if os.path.lexists(BUSINESS_LEASE):
            raise BootstrapError("business lease appeared during recovery")
        _write(record / "completed.json", json.dumps({"old_sha": old_sha,
               "state": terminal_state, "intent_sha256": _digest_json(intent),
               "installation": installation}, sort_keys=True).encode())
        return {"sha": old_sha, "state": terminal_state, "receipt": receipt}
    finally:
        if build_fd is not None:
            os.close(build_fd)
        os.close(fd)


def _recovered_preparation_evidence(sha, *, recovery_receipt=None):
    record = STATE / "recoveries" / sha
    _inventory(record, {"intent.json", "completed.json"})
    intent = _read_json(record / "intent.json")
    completed = _read_json(record / "completed.json")
    workspace = _recoverable_clone_evidence(sha)
    predeploy = _is_predeploy_workspace(workspace)
    terminal_state = 'CLOSED_PREDEPLOY_ATTESTATION_FAILURE' if predeploy else 'RECOVERED_PREPARATION_FAILURE'
    expected_keys = {"old_sha", "recovery_sha", "production_sha", "workspace", "config",
                     "library", "authorized", "locks", "toolchain", "receipt_sha256", "evidence_sha256"}
    if predeploy:
        expected_keys.add('predeploy_production')
    if (not isinstance(intent, dict) or set(intent) != expected_keys or intent["old_sha"] != sha
            or not isinstance(completed, dict) or set(completed) != {
                "old_sha", "state", "intent_sha256", "installation"}
            or completed["old_sha"] != sha or completed["state"] != terminal_state
            or completed["intent_sha256"] != _digest_json(intent)
            or intent["evidence_sha256"] != _digest_json({k: v for k, v in intent.items()
                                                        if k not in {"receipt_sha256", "evidence_sha256"}})
            or intent["workspace"] != _recoverable_clone_evidence(sha)):
        raise BootstrapError("historical recovery audit differs")
    if (not isinstance(recovery_receipt, str) or re.fullmatch(r"[0-9a-f]{64}", recovery_receipt) is None
            or not isinstance(intent["receipt_sha256"], str)
            or not secrets.compare_digest(hashlib.sha256(recovery_receipt.encode()).hexdigest(), intent["receipt_sha256"])):
        raise BootstrapError("successful operator recovery receipt required")
    if (any(not isinstance(intent[k], str) or re.fullmatch(r"[0-9a-f]{40}", intent[k]) is None
            for k in ("recovery_sha", "production_sha"))
            or len({sha, intent["recovery_sha"], intent["production_sha"]}) != 3
            or not isinstance(intent["config"], dict) or "loopback.key" not in intent["config"]
            or completed["installation"] != {
                "config": {k: v for k, v in intent["config"].items() if k != "loopback.key"},
                "library": intent["library"]}
            or intent["locks"] != {
                "launcher": _recovery_file_identity(STATE / "launcher.lock"),
                "build": _recovery_build_identity(sha, intent["workspace"])}):
        raise BootstrapError("historical recovery bindings differ")
    retirement = STATE / 'retired' / sha
    if os.path.lexists(retirement):
        _inventory(retirement, {'intent.json','completed.json'})
        saved = _read_json(retirement / 'intent.json')
    else:
        saved = None
    if isinstance(saved, dict) and saved.get('retirement_policy') == 'no-backup-v1':
        # A closed recovery receipt is historical audit, not a restoration
        # capability after forward-only retirement removed the old install.
        if (saved.get('old_sha') != sha or not isinstance(saved.get('new_sha'),str)
                or re.fullmatch(r'[0-9a-f]{40}',saved['new_sha']) is None
                or _read_json(retirement/'completed.json') != {'old_sha':sha,'new_sha':saved['new_sha'],'state':'RETIRED'}
                or saved.get('installation') != completed['installation']):
            raise BootstrapError('retired recovery installation audit differs')
    else:
        config, library = _archives(sha)
        historical = True
        if not os.path.lexists(config) and not os.path.lexists(library):
            config, library = CONFIG, INSTALLED.parent
            historical = False
        if completed["installation"] != _installation_evidence(
            sha, config, library, history_only=historical
        ):
            raise BootstrapError("recovered installation differs")
    return {"state": terminal_state, "recovery": _digest_json(completed),
            "workspace": intent["workspace"]}


def acknowledge_lost_closure_receipt(old_sha, sha, *, evidence_sha256=None, accepted=False):
    """Bind a new one-time receipt to an intact completed unchanged closure."""
    if (not isinstance(old_sha, str) or re.fullmatch(r"[0-9a-f]{40}", old_sha) is None
            or not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None
            or old_sha == sha):
        raise BootstrapError("distinct exact closure and acknowledgment SHAs required")
    source, _server = reviewed_source(sha)
    _run(["/usr/bin/python3.12", "-I", str(source / "scripts/trusted_release_gate.py"),
          "--sha", sha, "--workflow-sha", sha])
    secure(STATE)
    secure(STATE / "launcher.lock", private=True)
    fd = os.open(STATE / "launcher.lock", os.O_RDWR | os.O_NOFOLLOW)
    build_fd = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build_fd = _acquire_existing_build_lock(old_sha)
        build_path = STATE / old_sha / "build.lock"
        def check_locks():
            _assert_original_lock(STATE / "launcher.lock", fd)
            if build_fd is None:
                if os.path.lexists(build_path):
                    raise BootstrapError("historical build lock appeared")
            else:
                _assert_original_lock(build_path, build_fd)
        check_locks()
        history = _retired_history()
        _assert_fresh_sha(sha, history)
        _assert_known_activity(history, old_sha)
        if old_sha in history or any(os.path.lexists(path) for path in _archives(old_sha)):
            raise BootstrapError("closed release is already retired")
        _assert_idle()
        path = source / "scripts/lost_closure_receipt_acknowledgment.py"
        secure(path)
        if os.path.lexists(path.parent / "__pycache__"):
            raise BootstrapError("cached acknowledgment operator forbidden")
        spec = importlib.util.spec_from_file_location("reviewed_lost_receipt_operator", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.acknowledge(sys.modules[__name__], old_sha, sha, check_locks,
                                  evidence_sha256=evidence_sha256, accepted=accepted)
    finally:
        if build_fd is not None:
            os.close(build_fd)
        os.close(fd)


def _fixed_native_retirement():
    record = STATE / 'retired' / NATIVE_ROTATION_OLD
    _inventory(record, {'intent.json', 'completed.json'})
    audit = {name: _read_json(record / name) for name in ('intent.json', 'completed.json')}
    if _digest_json(audit) != NATIVE_ROTATION_AUDIT:
        raise BootstrapError('fixed native retirement audit differs')
    return audit['intent.json']


def _native_rotation_recovery():
    root = STATE / 'native-rotation-finalization'
    if not os.path.lexists(root):
        return None
    _inventory(root, {'intent.json', 'completed.json'})
    intent = _read_json(root / 'intent.json')
    required = {'publisher_sha', 'retirement_sha256', 'production_sha', 'executor_sha256',
                'authorized', 'locks', 'closure_sha256', 'policy'}
    if (not isinstance(intent, dict) or set(intent) != required
            or intent['retirement_sha256'] != NATIVE_ROTATION_AUDIT
            or intent['production_sha'] != NATIVE_ROTATION_PRODUCTION
            or intent['policy'] != 'no-backup-v1'
            or not isinstance(intent['publisher_sha'], str)
            or re.fullmatch('[a-f0-9]{40}', intent['publisher_sha']) is None
            or intent['publisher_sha'] in {NATIVE_ROTATION_OLD, NATIVE_ROTATION_ABANDONED, NATIVE_ROTATION_PRODUCTION}
            or _read_json(root / 'completed.json') != {
                'state': 'AUTHORIZATION_INSTALLED', 'intent_sha256': _digest_json(intent)}):
        raise BootstrapError('incomplete native rotation finalization')
    _fixed_native_retirement()
    source = canonical_source(intent['publisher_sha'])
    closure = STATE / 'native-only-closures' / NATIVE_ROTATION_OLD
    if (intent['executor_sha256'] != hashlib.sha256((source / 'scripts/trusted_release_server.py').read_bytes()).hexdigest()
            or intent['closure_sha256'] != _digest_json({name: _read_json(closure / name)
                                                       for name in ('intent.json', 'completed.json')})
            or intent['locks'] != {'launcher': _recovery_file_identity(STATE / 'launcher.lock'),
                                   'build': _recovery_file_identity(STATE / NATIVE_ROTATION_OLD / 'build.lock')}):
        raise BootstrapError('native rotation finalization bindings changed')
    return intent


def finalize_native_rotation(sha, *, evidence_sha256=None):
    """Explicit, once-only repair of the pinned post-retirement/pre-install failure."""
    source, server = reviewed_source(sha)
    _run(['/usr/bin/python3.12', '-I', '-S', '-B', str(source / 'scripts/trusted_release_gate.py'),
          '--sha', sha, '--workflow-sha', sha])
    root = STATE / 'native-rotation-finalization'
    lock = STATE / 'launcher.lock'
    secure(lock, private=True)
    fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
    build_fd = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build_fd = _acquire_existing_build_lock(NATIVE_ROTATION_OLD)
        if build_fd is None:
            raise BootstrapError('original native build lock required')
        def inspect():
            _assert_original_lock(lock, fd)
            _assert_original_lock(STATE / NATIVE_ROTATION_OLD / 'build.lock', build_fd)
            if any(os.path.lexists(path) for path in (root, CONFIG, INSTALLED.parent,
                    STATE / NATIVE_ROTATION_ABANDONED, BUSINESS_LEASE)):
                raise BootstrapError('native rotation is not an unstarted installation')
            history = _retired_history()
            retired = _fixed_native_retirement()
            if history.get(NATIVE_ROTATION_OLD) != retired:
                raise BootstrapError('native retirement history changed')
            _assert_fresh_sha(sha, history)
            _assert_known_activity(history)
            _recovery_production_proof(NATIVE_ROTATION_PRODUCTION, source)
            _assert_idle()
            _recovery_process_proof()
            keys = _retired_public_keys(NATIVE_ROTATION_OLD, retired)
            for item in history.values():
                if item.get('public_keys'):
                    for public in item['public_keys'].values():
                        if public.split()[1] in AUTHORIZED.read_text():
                            raise BootstrapError('retired key still authorized')
            _installation_inputs(sha, 0, keys['cloud.pub'])
            closure = STATE / 'native-only-closures' / NATIVE_ROTATION_OLD
            evidence = {'publisher_sha': sha, 'retirement_sha256': NATIVE_ROTATION_AUDIT,
                        'production_sha': NATIVE_ROTATION_PRODUCTION, 'policy': 'no-backup-v1',
                        'executor_sha256': hashlib.sha256((source / 'scripts/trusted_release_server.py').read_bytes()).hexdigest(),
                        'authorized': _recovery_file_identity(AUTHORIZED),
                        'locks': {'launcher': _recovery_file_identity(lock),
                                  'build': _recovery_file_identity(STATE / NATIVE_ROTATION_OLD / 'build.lock')},
                        'closure_sha256': _digest_json({name: _read_json(closure / name)
                                                       for name in ('intent.json', 'completed.json')})}
            return evidence, keys, history
        evidence, keys, history = inspect()
        digest = _digest_json(evidence)
        if evidence_sha256 is None:
            return {'state': 'READY', 'evidence_sha256': digest}
        if evidence_sha256 != digest or inspect()[0] != evidence:
            raise BootstrapError('native finalization inspection changed')
        root.mkdir(mode=0o700)
        _sync_parent(root)
        _write(root / 'intent.json', json.dumps(evidence, sort_keys=True).encode())
        retired_keys = {public for old, item in history.items()
                        for public in _retired_public_keys(old, item).values()}
        _install_locked(sha, 0, keys['cloud.pub'], source, server, retired_keys=retired_keys)
        policy = _read_json(CONFIG / 'authorized-release.json')
        cloud = (CONFIG / 'cloud.pub').read_text().strip()
        loopback = (CONFIG / 'loopback.pub').read_text().strip()
        lines = AUTHORIZED.read_text().splitlines()
        if (policy != {'sha': sha, 'expires_at': 0, 'executor_sha256': evidence['executor_sha256']}
                or hashlib.sha256(INSTALLED.read_bytes()).hexdigest() != evidence['executor_sha256']
                or cloud != keys['cloud.pub'] or loopback in retired_keys
                or [line for line in lines if cloud.split()[1] in line] != [key_lines(0, cloud, loopback)[0]]
                or [line for line in lines if loopback.split()[1] in line] != [key_lines(0, cloud, loopback)[1]]):
            raise BootstrapError('new native publisher readback failed')
        _write(root / 'completed.json', json.dumps({'state': 'AUTHORIZATION_INSTALLED',
                                                  'intent_sha256': digest}, sort_keys=True).encode())
        _retired_history()
        return {'state': 'AUTHORIZATION_INSTALLED', 'sha': sha}
    finally:
        if build_fd is not None:
            os.close(build_fd)
        os.close(fd)


def main():
    try:
        if not sys.flags.isolated or os.geteuid() != 0:
            raise BootstrapError("isolated root execution required")
        os.umask(0o077)
        use_system_timezone()
        parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
        commands = parser.add_subparsers(dest="action", required=True)
        native_finalizer = commands.add_parser('finalize-native-rotation', allow_abbrev=False)
        native_finalizer.add_argument('--sha', required=True)
        native_finalizer.add_argument('--evidence-sha256')
        create = commands.add_parser("install", allow_abbrev=False)
        create.add_argument("--sha", required=True)
        create.add_argument("--expires-at", default=0, type=int, help="Unix deadline; default 0 stays valid until revocation")
        create.add_argument("--cloud-public-key", required=True)
        create.add_argument("--backend-ci", action="store_true", help="derive narrow backend admission from actual production evidence")
        rotation = commands.add_parser("rotate", allow_abbrev=False)
        rotation.add_argument("--retire-sha", required=True)
        rotation.add_argument("--sha", required=True)
        rotation.add_argument("--expires-at", default=0, type=int, help="Unix deadline; default 0 permits reuse of the current cloud key")
        rotation.add_argument("--cloud-public-key", required=True)
        rotation.add_argument("--backend-ci", action="store_true", help="derive narrow backend admission from actual production evidence")
        rotation.add_argument("--successful-workspace-sha256",
                              help="fixed completed.json digest for one successful-identity closure")
        rotation.add_argument("--recovery-receipt-stdin", action="store_true")
        rotation.add_argument("--dinner-guard-rotation-stdin", action="store_true")
        rotation.add_argument("--review-maintenance-advance-receipt-stdin", action="store_true")
        rotation.add_argument("--review-maintenance-release-closure-receipt-stdin", action="store_true")
        rotation.add_argument("--finalized-production-sha", help="fixed reviewed native-closure production advance only")
        remove = commands.add_parser("revoke", allow_abbrev=False)
        remove.add_argument("--sha", required=True)
        recovery = commands.add_parser("recover-preparation", allow_abbrev=False)
        recovery.add_argument("--retire-sha", required=True)
        recovery.add_argument("--sha", required=True)
        recovery.add_argument("--production-sha", required=True)
        recovery.add_argument("--evidence-sha256")
        acknowledgment = commands.add_parser("acknowledge-lost-closure-receipt", allow_abbrev=False)
        acknowledgment.add_argument("--retire-sha", required=True)
        acknowledgment.add_argument("--sha", required=True)
        acknowledgment.add_argument("--evidence-sha256")
        acknowledgment.add_argument("--accept-lost-closure-receipt", action="store_true")
        review_advance = commands.add_parser('advance-review-maintenance', allow_abbrev=False)
        review_advance.add_argument('--retire-sha', required=True)
        review_advance.add_argument('--sha', required=True)
        review_advance.add_argument('--evidence-sha256')
        review_advance.add_argument('--accept-fixed-review-maintenance-advance', action='store_true')
        release_closure = commands.add_parser('close-review-maintenance-for-release', allow_abbrev=False)
        release_closure.add_argument('--retire-sha', required=True)
        release_closure.add_argument('--sha', required=True)
        release_closure.add_argument('--evidence-sha256')
        release_closure.add_argument('--accept-fixed-maintenance-advance-without-demo', action='store_true')
        release_closure.add_argument('--token-stdin', action='store_true')
        release_closure.add_argument('--accept-unknown-review-writes', action='store_true')
        sealing = commands.add_parser('seal-frontend-history', allow_abbrev=False)
        sealing.add_argument('--sha', required=True)
        sealing.add_argument('--active-operation')
        sealing.add_argument('--inspect', action='store_true')
        sealing.add_argument('--checkpoint-sha256')
        args = parser.parse_args()
        if args.action == 'finalize-native-rotation':
            result = finalize_native_rotation(args.sha, evidence_sha256=args.evidence_sha256)
        elif args.action == 'seal-frontend-history':
            if args.inspect and (args.checkpoint_sha256 is not None or args.active_operation is not None):
                raise BootstrapError('inspection cannot mutate or choose history')
            if args.checkpoint_sha256 is not None and re.fullmatch('[0-9a-f]{64}', args.checkpoint_sha256) is None:
                raise BootstrapError('exact original checkpoint digest required')
            result = frontend_history_seal(args.sha, active_operation=args.active_operation,
                                           inspect=args.inspect, checkpoint_sha256=args.checkpoint_sha256)
        elif args.action == 'close-review-maintenance-for-release':
            result = close_review_maintenance_for_release(args.retire_sha, args.sha,
                evidence_sha256=args.evidence_sha256, accepted=args.accept_fixed_maintenance_advance_without_demo,
                accept_unknown=args.accept_unknown_review_writes, token_stdin=args.token_stdin)
        elif args.action == 'advance-review-maintenance':
            result = advance_review_maintenance(args.retire_sha, args.sha,
                evidence_sha256=args.evidence_sha256, accepted=args.accept_fixed_review_maintenance_advance)
        elif args.action == "recover-preparation":
            result = recover_preparation(args.retire_sha, args.sha, args.production_sha,
                                         evidence_sha256=args.evidence_sha256)
        elif args.action == "acknowledge-lost-closure-receipt":
            result = acknowledge_lost_closure_receipt(
                args.retire_sha, args.sha, evidence_sha256=args.evidence_sha256,
                accepted=args.accept_lost_closure_receipt)
        elif args.action == "rotate":
            receipt = None
            github_token = None
            if sum((args.recovery_receipt_stdin, args.review_maintenance_advance_receipt_stdin, args.review_maintenance_release_closure_receipt_stdin, args.dinner_guard_rotation_stdin)) > 1:
                raise BootstrapError("exclusive protected receipt required")
            if args.dinner_guard_rotation_stdin:
                protected = _dinner_guard_module().rotation_input(sys.stdin.buffer.read(8193))
                receipt, github_token = protected['receipt'], protected['github_token']
            elif args.review_maintenance_release_closure_receipt_stdin:
                protected = _review_release_rotation_input()
                receipt, github_token = protected['receipt'], protected['github_token']
            elif args.recovery_receipt_stdin or args.review_maintenance_advance_receipt_stdin:
                raw = sys.stdin.buffer.read(66)
                if re.fullmatch(rb"[0-9a-f]{64}\n?", raw) is None:
                    raise BootstrapError("exact protected recovery receipt required")
                receipt = raw.rstrip(b"\n").decode("ascii")
            result = rotate(args.retire_sha, args.sha, args.expires_at, args.cloud_public_key,
                            successful_workspace_sha256=args.successful_workspace_sha256,
                            recovery_receipt=receipt if args.recovery_receipt_stdin or args.dinner_guard_rotation_stdin else None,
                            review_advance_receipt=receipt if args.review_maintenance_advance_receipt_stdin else None,
                            review_release_closure_receipt=receipt if args.review_maintenance_release_closure_receipt_stdin else None,
                            **({('dinner_guard_github_token' if args.dinner_guard_rotation_stdin else 'review_release_github_token'): github_token} if github_token is not None else {}),
                            finalized_production_sha=args.finalized_production_sha,
                            **({"backend_ci": True} if args.backend_ci else {}))
        elif args.action == "install":
            result = install(args.sha, args.expires_at, args.cloud_public_key,
                             **({"backend_ci": True} if args.backend_ci else {}))
        else:
            result = revoke(args.sha)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:  # noqa: BLE001 -- Boundary must sanitize all install/credential failures.
        print("release bootstrap: validation/installation failed; preserve evidence for operator review", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
