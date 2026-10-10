"""Canonical, bounded first installation of a dormant owner WeChat bridge.

Package manifests are review evidence, never installation authority. A production
inspector uses the existing root-owned canonical bootstrap, exact current main
full CI and original launcher flock. Only an identical evidence digest admits a
first dormant installation. Activation and automatic rollback are not exposed.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import grp
import pwd
import re
import secrets
import stat
import subprocess
import sys
import time


STATE = Path("/var/lib/reva-release")
LEASE = Path("/var/lock/health-app-release")
ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_FILES = 256
PRODUCTION_APPLY_ENABLED = True
RUNTIME_ROOT = Path("/opt/neo-wechat")
CONFIG_ROOT = Path("/etc/neo-wechat")
DATA_ROOT = Path("/var/lib/neo-wechat")
UNIT = Path("/etc/systemd/system/neo-wechat.service")
SOCKET_UNIT = Path("/etc/systemd/system/neo-wechat.socket")
RUN_ROOT = Path("/run/neo-wechat")
INSTALLED_EXECUTOR = Path("/usr/local/lib/reva-release/trusted_release_server.py")
ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C",
       "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
       "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_NO_REPLACE_OBJECTS": "1"}
BLOCKERS = (
    "independent_G4_exact_revision_required",
    "reviewed_external_bootstrap_and_installed_executor_history_required",
    "isolated_hashed_runtime_artifact_required",
    "owner_secret_entry_QR_and_OAuth_consent_required",
    "Slack_sender_acceptance_and_parent_filter_required",
)


class DeployError(Exception):
    """Secret-free admission error."""


def checked_revision(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise DeployError("exact revision required")
    return value


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def file_digest(path):
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or before.st_size > MAX_FILE_BYTES):
        raise DeployError("invalid package file")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if opened != before:
            raise DeployError("package file changed")
        raw = stream.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES or path.lstat() != before:
        raise DeployError("package file changed")
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def render_unit(revision):
    checked_revision(revision)
    template = (ROOT / "infra/neo-wechat/neo-wechat.service.in").read_bytes()
    if template.count(b"@REVISION@") != 1:
        raise DeployError("unit template revision binding differs")
    return template.replace(b"@REVISION@", revision.encode())


def proxy_bytes():
    return (ROOT / "infra/neo-wechat/nginx-locations.conf").read_bytes()


def socket_unit_bytes():
    return (ROOT / "infra/neo-wechat/neo-wechat.socket.in").read_bytes()


def package_inventory(source):
    """Read only the bounded service/template surface; never .env or credentials."""
    paths = [source / "deploy.sh", source / "scripts/trusted_neo_wechat.py"]
    for name in ("services/neo_wechat", "infra/neo-wechat"):
        base = source / name
        if not base.is_dir() or base.is_symlink():
            raise DeployError("package inputs missing")
        pending = [base]
        count = 0
        while pending:
            directory = pending.pop()
            for path in sorted(directory.iterdir()):
                count += 1
                if count > MAX_FILES:
                    raise DeployError("package inventory exceeds bound")
                info = path.lstat()
                if stat.S_ISDIR(info.st_mode):
                    if path.name not in ("tests", "__pycache__", ".pytest_cache"):
                        pending.append(path)
                elif stat.S_ISREG(info.st_mode):
                    if (re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", path.name) is None
                            or path.name.startswith(".")
                            or not (path.suffix in (".py", ".in", ".conf", ".js", ".md")
                                    or path.name == "requirements.lock")):
                        raise DeployError("unexpected package file")
                    paths.append(path)
                else:
                    raise DeployError("unsupported package object")
    if len(paths) > MAX_FILES:
        raise DeployError("package inventory exceeds bound")
    return {str(path.relative_to(source)): file_digest(path) for path in sorted(paths)}


def secure_path(path, *, directory=False):
    for entry in [*reversed(path.parents), path]:
        info = entry.lstat()
        directory_entry = entry != path or directory
        kind = stat.S_ISDIR if directory_entry else stat.S_ISREG
        if (not kind(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022
                or (not directory_entry and info.st_nlink != 1)):
            raise DeployError("unsafe canonical input")


def load_reviewed(publisher):
    source = STATE / "bootstrap" / publisher / "source"
    entry = source / "scripts/trusted_neo_wechat.py"
    if Path(__file__).absolute() != entry:
        raise DeployError("canonical root staging required")
    secure_path(entry)

    def module(name, filename):
        path = entry.with_name(filename)
        secure_path(path)
        spec = importlib.util.spec_from_file_location(name, path)
        value = importlib.util.module_from_spec(spec)
        sys.modules[name] = value
        spec.loader.exec_module(value)
        return value

    helper = module("neo_reviewed_helpers", "trusted_review_reset.py")
    reviewed, bootstrap, server = helper.load_reviewed(publisher)
    if reviewed != source:
        raise DeployError("canonical source differs")
    gate = module("neo_exact_gate", "trusted_release_gate.py")
    return source, helper, bootstrap, server, gate


def exact_full_ci(gate, publisher):
    # The legacy full gate allows documentation descendants; this new surface
    # deliberately requires the actual current main, on both sides of attestation.
    if gate._main_sha(gate._get_json) != publisher:
        raise DeployError("publisher is not current main")
    result = gate.verify_release(publisher, publisher, observed_main=publisher, target="full")
    if gate._main_sha(gate._get_json) != publisher:
        raise DeployError("main changed")
    return result


def runtime_inputs(source):
    for name in ("__init__.py", "server.py", "listener.py", "store.py", "core.py", "oauth.py", "qr.js", "requirements.lock"):
        path = source / "services/neo_wechat" / name
        if not path.is_file() or path.is_symlink():
            raise DeployError("complete locked runtime inputs required")
        file_digest(path)
    for name in ("neo-wechat.service.in", "neo-wechat.socket.in", "nginx-locations.conf"):
        path = source / "infra/neo-wechat" / name
        if not path.is_file() or path.is_symlink():
            raise DeployError("complete infrastructure inputs required")
        file_digest(path)
    lock = (source / "services/neo_wechat/requirements.lock").read_text()
    logical = lock.replace("\\\n", "").splitlines()
    requirements = [line.strip() for line in logical if line.strip() and not line.strip().startswith("#")]
    if not requirements or any(
            re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+(?:\s+--hash=sha256:[0-9a-f]{64})+", line) is None
            for line in requirements):
        raise DeployError("runtime lock must pin and hash every binary dependency")
    return file_digest(source / "services/neo_wechat/requirements.lock")


def runtime_install_command(revision):
    checked_revision(revision)
    release = RUNTIME_ROOT / "releases" / revision
    # The only writable host path is this candidate. All Health and release
    # secrets are hidden, including paths readable by accidentally broad modes.
    return ["/usr/bin/systemd-run", "--quiet", "--wait", "--pipe", "--collect",
            "--unit=neo-wechat-build-" + revision[:16],
            "--property", "User=neo-wechat", "--property", "Group=neo-wechat",
            "--property", "ProtectSystem=strict", "--property", "ProtectHome=yes",
            "--property", "PrivateTmp=yes", "--property", "PrivateDevices=yes",
            "--property", "NoNewPrivileges=yes", "--property", "CapabilityBoundingSet=",
            "--property", "RestrictNamespaces=yes", "--property", "ProtectProc=invisible",
            "--property", "ProcSubset=pid", "--property", "MemoryMax=512M",
            "--property", "CPUQuota=50%", "--property", "TasksMax=32",
            "--property", "RuntimeMaxSec=300", "--property", "KillMode=control-group",
            "--property", "InaccessiblePaths=-/srv -/data -/mnt -/media -/etc/pip.conf -/etc/xdg/pip",
            "--property", "TemporaryFileSystem=/opt /var/lib /var/cache /var/log /var/backups /etc/neo-wechat /etc/reva-release /etc/health-app",
            "--property", "BindPaths=" + str(release),
            "--property", "ReadWritePaths=" + str(release),
            "/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "HOME=/nonexistent", "PIP_CONFIG_FILE=/dev/null",
            str(release / "venv/bin/python"), "-I", "-m", "pip", "--isolated", "install",
            "--no-cache-dir", "--disable-pip-version-check", "--require-hashes",
            "--only-binary=:all:", "--no-deps", "--index-url", "https://pypi.org/simple",
            "-r", str(release / "requirements.lock")]


def run(args, *, timeout=60):
    try:
        return subprocess.run(args, env=ENV, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout, check=True, text=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        raise DeployError("fixed bridge operation failed; do not retry") from None


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_once(path, raw, *, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(path.parent)


def write_json(path, value):
    write_once(path, json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def directory(path, mode=0o700):
    path.mkdir(mode=mode)
    os.chmod(path, mode)
    sync_directory(path.parent)


def checked_operation(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        raise DeployError("exact operation ID required")
    return value


def health_snapshot():
    result = {}
    for unit in ("health-backend.service", "health-backend.socket", "celery-worker.service", "celery-beat.service"):
        raw = run(["/usr/bin/systemctl", "show", unit,
                   "--property=ActiveState,SubState,MainPID,NRestarts,ActiveEnterTimestampMonotonic,FragmentPath,DropInPaths"])
        values = dict(line.split("=", 1) for line in raw.splitlines())
        if values.get("ActiveState") != "active":
            raise DeployError("existing Health services are not stable")
        result[unit] = values
    return result


def protected_metadata():
    # Only inode/mode/change metadata. Never open application secrets or grants.
    result = {}
    for raw in ("/opt/health-app/backend/.env", "/var/lib/reva-health-evidence-runtime/enabled.env",
                "/etc/health-app/migration.env", "/etc/nginx/sites-enabled", "/etc/nginx/nginx.conf"):
        path = Path(raw)
        if os.path.lexists(path):
            info = path.lstat()
            result[raw] = [getattr(info, "st_" + name) for name in
                           ("dev", "ino", "mode", "uid", "gid", "size", "mtime_ns", "ctime_ns")]
        else:
            result[raw] = None
    return result


def assert_first_install():
    for path in (RUNTIME_ROOT, CONFIG_ROOT, DATA_ROOT, UNIT, SOCKET_UNIT, RUN_ROOT):
        if os.path.lexists(path):
            raise DeployError("existing bridge objects require explicit recovery or upgrade")
        secure_path(path.parent, directory=True)
    try:
        pwd.getpwnam("neo-wechat")
    except KeyError:
        pass
    else:
        raise DeployError("existing bridge account requires review")
    for name in ("neo-wechat", "neo-wechat-proxy"):
        try:
            grp.getgrnam(name)
        except KeyError:
            continue
        raise DeployError("existing bridge group requires review")
    for unit in (UNIT, SOCKET_UNIT):
        state = run(["/usr/bin/systemctl", "show", unit.name,
                     "--property=LoadState,ActiveState,UnitFileState,DropInPaths", "--all"])
        if set(state.splitlines()) != {"LoadState=not-found", "ActiveState=inactive", "UnitFileState=", "DropInPaths="}:
            raise DeployError("unexpected existing bridge unit")


def assert_dormant_units(publisher):
    for unit, expected in ((UNIT, render_unit(publisher)), (SOCKET_UNIT, socket_unit_bytes())):
        state = run(["/usr/bin/systemctl", "show", unit.name,
                     "--property=LoadState,ActiveState,UnitFileState,FragmentPath,DropInPaths", "--all"])
        if set(state.splitlines()) != {"LoadState=loaded", "ActiveState=inactive",
                                      "UnitFileState=static", "FragmentPath=" + str(unit), "DropInPaths="}:
            raise DeployError("bridge units must remain inactive and not enabled")
        secure_path(unit)
        if unit.read_bytes() != expected:
            raise DeployError("bridge unit readback differs")
    if os.path.lexists(RUN_ROOT):
        raise DeployError("dormant install must not create a runtime socket path")


def install_units(publisher):
    # No start/enable operation: both the service and its Unix listener stay
    # dormant. The service cannot create listeners itself under its syscall
    # policy; a later separately reviewed activation must start the socket.
    write_once(UNIT, render_unit(publisher), mode=0o644)
    write_once(SOCKET_UNIT, socket_unit_bytes(), mode=0o644)
    run(["/usr/bin/systemd-analyze", "verify", str(UNIT), str(SOCKET_UNIT)])
    run(["/usr/bin/systemctl", "daemon-reload"])
    assert_dormant_units(publisher)


def assert_installed_history(source):
    # A newer source checkout alone cannot close reboot-lost lease gaps: the
    # actual forced-command executor must already enforce this history protocol.
    secure_path(INSTALLED_EXECUTOR)
    if file_digest(INSTALLED_EXECUTOR) != file_digest(source / "scripts/trusted_release_server.py"):
        raise DeployError("installed release executor must be upgraded through canonical bootstrap first")


def lease_identity(helper, bootstrap, server, token):
    return helper._lease_identity(str(LEASE), token, bootstrap, server)


def verify_account():
    account = pwd.getpwnam("neo-wechat")
    own = grp.getgrnam("neo-wechat")
    proxy = grp.getgrnam("neo-wechat-proxy")
    if (account.pw_uid == 0 or account.pw_gid != own.gr_gid or own.gr_gid == 0
            or proxy.gr_gid in (0, own.gr_gid) or account.pw_dir != "/nonexistent"
            or account.pw_shell != "/usr/sbin/nologin"
            or set(os.getgrouplist("neo-wechat", own.gr_gid)) != {own.gr_gid, proxy.gr_gid}
            or own.gr_mem or set(proxy.gr_mem) != {"neo-wechat"}):
        raise DeployError("isolated account membership differs")
    return account.pw_uid, own.gr_gid, proxy.gr_gid


def runtime_entries(root):
    pending, total = [root], 0
    while pending:
        path = pending.pop()
        total += 1
        if total > 30000:
            raise DeployError("runtime inventory exceeds bound")
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            pending.extend(sorted(path.iterdir()))
        elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise DeployError("runtime links or special files rejected")
        yield path, info


def seal_runtime(root):
    entries = list(runtime_entries(root))
    for path, info in entries:
        os.chown(path, 0, 0, follow_symlinks=False)
        os.chmod(path, 0o755 if stat.S_ISDIR(info.st_mode) or info.st_mode & 0o111 else 0o644)
    result = {}
    for path, _ in entries:
        secure_path(path, directory=path.is_dir())
        if path.is_file():
            # Native wheels legitimately contain large libraries. Hash streaming.
            h = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(chunk)
                os.fsync(stream.fileno())
            result[str(path.relative_to(root))] = h.hexdigest()
    for path, info in reversed(entries):
        if stat.S_ISDIR(info.st_mode):
            sync_directory(path)
    return digest(result)


def install_payload(plan, source, check, helper, bootstrap):
    publisher, production, operation = plan["publisher_sha"], plan["production_sha"], plan["operation_id"]
    check()
    run(["/usr/sbin/groupadd", "--system", "neo-wechat"])
    run(["/usr/sbin/groupadd", "--system", "neo-wechat-proxy"])
    run(["/usr/sbin/useradd", "--system", "--gid", "neo-wechat", "--groups", "neo-wechat-proxy",
         "--no-create-home", "--home-dir", "/nonexistent", "--shell", "/usr/sbin/nologin", "neo-wechat"])
    uid, gid, proxy_gid = verify_account()
    directory(RUNTIME_ROOT, 0o755)
    directory(RUNTIME_ROOT / "releases", 0o755)
    release = RUNTIME_ROOT / "releases" / publisher
    directory(release, 0o755)
    run(["/usr/bin/python3.12", "-I", "-m", "venv", "--copies", str(release / "venv")], timeout=120)
    write_once(release / "requirements.lock", (source / "services/neo_wechat/requirements.lock").read_bytes(), mode=0o644)
    # Python venv's conventional lib64 symlink is unnecessary and would
    # weaken the no-link artifact inventory. Remove only this exact link.
    lib64 = release / "venv/lib64"
    if lib64.is_symlink() and os.readlink(lib64) == "lib":
        lib64.unlink()
    for path, _info in runtime_entries(release):
        os.chown(path, uid, gid, follow_symlinks=False)
    check()
    run(runtime_install_command(publisher), timeout=330)
    if file_digest(release / "requirements.lock") != plan["files"]["services/neo_wechat/requirements.lock"]:
        raise DeployError("dependency lock changed during installation")
    site = release / "venv/lib/python3.12/site-packages"
    if not site.is_dir() or (site / "services").exists():
        raise DeployError("isolated package destination differs")
    directory(site / "services", 0o755)
    write_once(site / "services/__init__.py", b"", mode=0o644)
    directory(site / "services/neo_wechat", 0o755)
    for name in plan["files"]:
        relative = Path(name)
        if relative.parent == Path("services/neo_wechat") and (relative.suffix == ".py" or relative.name == "qr.js"):
            write_once(site / "services/neo_wechat" / relative.name, (source / relative).read_bytes(), mode=0o644)
    # Park the route candidate before sealing. It is NOT included by nginx.
    write_once(release / "nginx-locations.conf", proxy_bytes(), mode=0o644)
    runtime_hash = seal_runtime(release)
    # Compile/import only inside the same isolated unprivileged sandbox;
    # no app startup, QR requests, OAuth grants or Slack traffic.
    command = runtime_install_command(publisher)
    command = command[:command.index(str(release / "venv/bin/python"))] + [
        str(release / "venv/bin/python"), "-I", "-B", "-c",
        "import services.neo_wechat.server as s, services.neo_wechat.store, services.neo_wechat.oauth; "
        "from pathlib import Path; assert Path(s.__file__).with_name('qr.js').is_file()"]
    run(command, timeout=60)
    if seal_runtime(release) != runtime_hash:
        raise DeployError("immutable runtime changed during smoke verification")
    check()
    directory(CONFIG_ROOT, 0o710)
    os.chown(CONFIG_ROOT, 0, gid)
    sync_directory(CONFIG_ROOT)
    directory(DATA_ROOT, 0o700)
    os.chown(DATA_ROOT, uid, gid)
    sync_directory(DATA_ROOT)
    install_units(publisher)
    if health_snapshot() != plan["health_services"]:
        raise DeployError("Health service identities changed")
    if protected_metadata() != plan["protected_metadata"]:
        raise DeployError("protected configuration metadata changed")
    if list(CONFIG_ROOT.iterdir()) or list(DATA_ROOT.iterdir()):
        raise DeployError("dormant install must not create secrets or runtime data")
    verify_account()
    helper._revision_proof(production, source, bootstrap)
    check()
    complete = {"state": "INSTALLED_DORMANT", "publisher_sha": publisher, "production_sha": production,
                "operation_id": operation, "evidence_sha256": digest(plan), "runtime_sha256": runtime_hash,
                "proxy_gid": proxy_gid, "activated": False, "nginx_included": False,
                "health_services_unchanged": True, "secrets_created": False}
    return complete


def assert_backend_history(bootstrap, publisher):
    """Reuse canonical closed-history admission; an absent lease is insufficient."""
    history = bootstrap._retired_history()
    bootstrap._assert_known_activity(history, old_sha=publisher)
    bootstrap._workspace_evidence(publisher)
    bootstrap._recovery_process_proof()


def install_dormant(plan):
    publisher, production, operation = plan["publisher_sha"], plan["production_sha"], plan["operation_id"]
    source, helper, bootstrap, server, _gate = load_reviewed(publisher)
    lock = STATE / "launcher.lock"
    secure_path(lock)
    fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if inspect(publisher, production, operation, _lock=fd) != plan:
            raise DeployError("preflight evidence changed")
        audit_root = STATE / "neo-wechat"
        directory(audit_root)
        audit = audit_root / operation
        directory(audit)
        write_json(audit / "before.json", plan)
        write_json(audit / "intent.json", {"state": "INSTALL_STARTED", "evidence_sha256": digest(plan),
                                           "operation_id": operation, "publisher_sha": publisher})
        # Atomic mkdir follows the existing ordinary-deploy business lease.
        # A collision or partial creation preserves the audit; it is not retryable.
        LEASE.mkdir(mode=0o700)
        os.chmod(LEASE, 0o700)
        server._sync_business_lease_parent()
        token = secrets.token_hex(32)
        for name, value in {"token": token, "label": "neo-wechat-dormant-install", "stage": str(audit),
                            "started_at": str(int(time.time()))}.items():
            write_once(LEASE / name, (value + "\n").encode())
        server._sync_business_lease_parent()
        identity = lease_identity(helper, bootstrap, server, token)
        write_json(audit / "lease.json", {"identity": identity})

        def check():
            helper._assert_lock(server, lock, fd)
            if lease_identity(helper, bootstrap, server, token) != identity:
                raise DeployError("lease identity changed")

        try:
            # Close the last absence-check/atomic-claim gap with real production
            # observations after ownership is acquired and before the first host mutation.
            check()
            assert_backend_history(bootstrap, publisher)
            if health_snapshot() != plan["health_services"] or protected_metadata() != plan["protected_metadata"]:
                raise DeployError("production changed before bridge lease acquisition")
            helper._revision_proof(production, source, bootstrap)
            if package_inventory(source) != plan["files"]:
                raise DeployError("source changed before bridge installation")
            complete = install_payload(plan, source, check, helper, bootstrap)
            assert_backend_history(bootstrap, publisher)
            write_json(audit / "verified.json", complete)
            check()
            if {path.name for path in LEASE.iterdir()} != {"token", "label", "stage", "started_at"}:
                raise DeployError("lease inventory changed")
            for name in ("token", "label", "stage", "started_at"):
                (LEASE / name).unlink()
            LEASE.rmdir()
            server._sync_business_lease_parent()
            write_json(audit / "completed.json", complete)
            return complete
        except BaseException:
            write_json(audit / "failed.json", {"state": "INSTALL_NEEDS_OPERATOR", "operation_id": operation})
            raise DeployError("installation outcome unknown; retain audit and lease; do not retry") from None
    finally:
        os.close(fd)


def inspect(publisher, production, operation=None, *, _lock=None):
    checked_revision(publisher)
    checked_revision(production)
    checked_operation(operation)
    if (os.geteuid() != 0 or sys.executable != "/usr/bin/python3.12"
            or not sys.flags.isolated or not sys.flags.no_site
            or not sys.flags.dont_write_bytecode or "SSH_ORIGINAL_COMMAND" in os.environ):
        raise DeployError("isolated canonical root operator required")
    source, helper, bootstrap, server, gate = load_reviewed(publisher)
    lock = STATE / "launcher.lock"
    secure_path(lock)
    fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW) if _lock is None else _lock
    try:
        if _lock is None:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        helper._assert_lock(server, lock, fd)
        ci = exact_full_ci(gate, publisher)
        assert_installed_history(source)
        assert_backend_history(bootstrap, publisher)
        server.assert_frontend_rebuild_history()
        server.assert_ota_history()
        helper._revision_proof(production, source, bootstrap)
        if bootstrap._read_json(STATE / production / "completed.json") != {
                "sha": production, "state": "SUCCEEDED"}:
            raise DeployError("production success receipt differs")
        if os.path.lexists(LEASE):
            raise DeployError("business release is already owned")
        # No claim is acquired and no state is written by this inspector. Any
        # previous bridge install state requires its separately reviewed recovery.
        if os.path.lexists(STATE / "neo-wechat"):
            raise DeployError("bridge history needs reviewed recovery")
        files = package_inventory(source)
        runtime_inputs(source)
        assert_first_install()
        health_services = health_snapshot()
        protected = protected_metadata()
        helper._assert_lock(server, lock, fd)
        if os.path.lexists(LEASE):
            raise DeployError("business release began during inspection")
        return {"publisher_sha": publisher, "production_sha": production,
                "operation_id": operation, "ci": ci, "files": files,
                "health_services": health_services, "protected_metadata": protected, "lease_claimed": False}
    finally:
        if _lock is None:
            os.close(fd)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    # Explicit negative admission before environment, imports of release helpers,
    # network, paths or locks. No hidden force/enable/retry/install aliases exist.
    if any(arg in ("--apply", "--install", "--activate", "--rollback") for arg in argv):
        print(json.dumps({"state": "NEO_WECHAT_INSTALL_BLOCKED", "blockers": BLOCKERS,
                          "production_changed": False}))
        return 78
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--publisher-sha", required=True)
    parser.add_argument("--production-sha")
    parser.add_argument("--operation-id")
    parser.add_argument("--evidence-sha256")
    parser.add_argument("--package-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        checked_revision(args.publisher_sha)
        if args.package_only:
            if args.evidence_sha256:
                raise DeployError("local package cannot authorize installation")
            evidence = {"declared_revision": args.publisher_sha, "files": package_inventory(ROOT)}
            state = "NEO_WECHAT_LOCAL_PACKAGE_ONLY_UNTRUSTED"
        else:
            evidence = inspect(args.publisher_sha, args.production_sha, args.operation_id)
            state = "NEO_WECHAT_PREFLIGHT_ONLY"
            if args.evidence_sha256:
                if args.evidence_sha256 != digest(evidence):
                    raise DeployError("preflight evidence changed")
                print(json.dumps(install_dormant(evidence), sort_keys=True))
                return 0
        print(json.dumps({"state": state, "evidence_sha256": digest(evidence),
                          "evidence": evidence, "blockers": BLOCKERS,
                          "production_apply_enabled": PRODUCTION_APPLY_ENABLED and not args.package_only,
                          "production_changed": False}, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"state": "NEO_WECHAT_BLOCKED",
                          "production_changed": "UNKNOWN_IF_INSTALL_REQUESTED" if args.evidence_sha256 else False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
