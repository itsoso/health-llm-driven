"""Operator-only rebuild of an unchanged, already deployed frontend tree.

The only entry is canonical deploy.sh --rebuild-deployed-frontend. This does
not consume or manufacture a backend release receipt, rotate identities, or
change the production checkout. Unknown outcomes retain the business lease.
"""

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import time
import urllib.request

STATE = Path("/var/lib/reva-release")
PRODUCTION = Path("/opt/health-app")
BUILDS = Path("/var/lib/reva-frontend-builds")
LEASE = Path("/var/lock/health-app-release")
ENV = {"PATH": "/usr/bin:/bin", "HOME": "/root", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
       "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_NO_REPLACE_OBJECTS": "1"}
SERVICES = ("health-backend", "celery-worker", "celery-beat")
# Build tools live in /usr, while only explicitly bound inputs may be read from
# application/data roots. ProtectSystem is write protection, not confidentiality.
# A '-' tolerates an absent root; it does not expose one that exists.
PRIVATE_ROOTS = ("/opt", "/var/lib", "/var/cache", "/var/log", "/var/backups",
                 "/srv", "/data", "/mnt", "/media", "/etc/reva-release", "/etc/health-app")
PUBLIC_ENV = {
    "BACKEND_URL": {"http://127.0.0.1:8000", "http://localhost:8000"},
    "NEXT_PUBLIC_API_BASE_URL": {"/api", "https://health.executor.life/api"},
    "NEXT_PUBLIC_API_URL": {"/api", "https://health.executor.life/api"},
    "NEXT_PUBLIC_SITE_BASE_URL": {"https://health.executor.life"},
}


class RebuildError(Exception):
    """Sanitized error; no process output or configuration values escape."""


def checked_hex(value, length):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{%d}" % length, value) is None:
        raise RebuildError("invalid exact revision or operation identity")
    return value


def validate_binding(publisher, production, expected_tree, actual_tree, backend_receipt, *, live_sha=None):
    for value in (publisher, production, expected_tree, actual_tree):
        checked_hex(value, 40)
    if ((live_sha is not None and live_sha != production) or expected_tree != actual_tree
            or backend_receipt != {"sha": production, "state": "SUCCEEDED"}):
        raise RebuildError("production revision, frontend tree or backend success proof differs")


def receipt(publisher, production, operation, tree, state, digest):
    return {"kind": "frontend-rebuild", "publisher_sha": publisher, "production_sha": production,
            "operation_id": operation, "frontend_tree": tree, "state": state, "artifact_digest": digest}


def public_build_env(raw):
    result = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not separator or key in result or key not in PUBLIC_ENV or value not in PUBLIC_ENV[key]:
            raise RebuildError("frontend build configuration is not a fixed public endpoint")
        result[key] = value
    return result


def build_command(operation, stage):
    checked_hex(operation, 32)
    if stage != BUILDS / operation:
        raise RebuildError("unexpected build stage")
    properties = [
        "DynamicUser=yes", f"User=reva-front-{operation[:12]}", "ProtectSystem=strict", "ProtectHome=yes",
        "ProtectProc=invisible", "NoNewPrivileges=yes", "PrivateTmp=yes", "PrivateDevices=yes",
        "ProtectKernelTunables=yes", "ProtectControlGroups=yes", "RestrictSUIDSGID=yes",
        "RestrictNamespaces=yes", "CapabilityBoundingSet=", "KillMode=control-group",
        "CPUQuota=100%", "MemoryHigh=2G", "MemoryMax=3G", "TasksMax=256", "Nice=10",
        "TimeoutStartSec=1800", "TimeoutStopSec=30", "RuntimeMaxSec=1800",
        "InaccessiblePaths=" + " ".join("-" + path for path in PRIVATE_ROOTS),
        "ReadWritePaths=/tmp/reva-frontend /tmp/reva-home /tmp/reva-cache",
        f"BindPaths={stage}/frontend:/tmp/reva-frontend {stage}/home:/tmp/reva-home {stage}/cache:/tmp/reva-cache",
        "WorkingDirectory=/tmp/reva-frontend",
    ]
    command = ["/usr/bin/systemd-run", "--wait", "--pipe", "--quiet", f"--unit=reva-frontend-build-{operation}"]
    command.extend(f"--property={value}" for value in properties)
    command.extend(["/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "HOME=/tmp/reva-home",
                    "npm_config_cache=/tmp/reva-cache", "CI=1", "NEXT_TELEMETRY_DISABLED=1",
                    "npm_config_userconfig=/dev/null", "npm_config_globalconfig=/dev/null",
                    "NODE_OPTIONS=--max-old-space-size=2048",
                    "/bin/bash", "--noprofile", "--norc", "-euc",
                    "npm ci --ignore-scripts --no-audit --no-fund\nnpm run build"])
    return command


def artifact_digest(root):
    root = Path(root)
    digest, count = hashlib.sha256(), 0
    pending = [root]
    while pending:
        path = pending.pop()
        count += 1
        if count > 150000:
            raise RebuildError("artifact inventory exceeds bound")
        info = path.lstat()
        relative = path.relative_to(root).as_posix()
        digest.update((relative + "\0" + str(stat.S_IMODE(info.st_mode)) + "\0").encode())
        if stat.S_ISLNK(info.st_mode):
            try:
                target = path.resolve(strict=True)
            except (OSError, RuntimeError):
                raise RebuildError("invalid artifact link") from None
            if not target.is_relative_to(root.resolve()) or os.path.isabs(os.readlink(path)):
                raise RebuildError("artifact link escapes bundle")
            digest.update(b"link\0" + os.readlink(path).encode())
        elif stat.S_ISDIR(info.st_mode):
            digest.update(b"directory\0")
            pending.extend(sorted(path.iterdir(), reverse=True))
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size < 2_000_000_000:
            digest.update(b"file\0" + str(info.st_size).encode() + b"\0")
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        else:
            raise RebuildError("unsupported artifact object")
    return digest.hexdigest()


def run(args, *, cwd=None, timeout=90):
    try:
        return subprocess.run(args, cwd=cwd, env=ENV, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
                              check=True, text=True).stdout
    except (subprocess.SubprocessError, OSError):
        raise RebuildError("fixed operation failed; private evidence retained") from None


def module_at(path, name, secure):
    secure(path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def secure_entry(path):
    for item in [*reversed(path.parents), path]:
        info = item.lstat()
        expected = stat.S_ISREG if item == path else stat.S_ISDIR
        if (info.st_uid != 0 or info.st_mode & 0o022 or not expected(info.st_mode)
                or (item == path and info.st_nlink != 1)):
            raise RebuildError("unsafe canonical operator entry")


def load_reviewed(publisher):
    source = STATE / "bootstrap" / publisher / "source"
    entry = source / "scripts/trusted_frontend_rebuild.py"
    if Path(__file__).absolute() != entry:
        raise RebuildError("operator must run from canonical publisher staging")
    secure_entry(entry)
    helper = module_at(entry.with_name("trusted_review_reset.py"), "frontend_revision_helpers", secure_entry)
    checked_source, bootstrap, server = helper.load_reviewed(publisher)
    if source != checked_source:
        raise RebuildError("canonical source differs")
    gate = module_at(entry.with_name("trusted_release_gate.py"), "frontend_ci_gate", secure_entry)
    return source, helper, bootstrap, server, gate


def git(source, *args):
    return run(["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
                "-C", str(source), *args]).strip()


def data_fingerprint(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 1000000:
        raise RebuildError("invalid bounded configuration file")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        current = os.fstat(stream.fileno())
        if current != info:
            raise RebuildError("configuration changed while opening")
        data = stream.read(1000001)
    after = path.lstat()
    identity_fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_uid", "st_gid", "st_mtime_ns", "st_ctime_ns")
    if len(data) > 1000000 or any(getattr(after, field) != getattr(info, field) for field in identity_fields):
        raise RebuildError("configuration changed while reading")
    return {"dev": info.st_dev, "ino": info.st_ino, "mode": info.st_mode,
            "uid": info.st_uid, "gid": info.st_gid, "sha256": hashlib.sha256(data).hexdigest()}, data


def snapshot(server):
    services = {}
    for name in SERVICES:
        values = dict(line.split("=", 1) for line in run([
            "/usr/bin/systemctl", "show", name, "--property=ActiveState,SubState,MainPID,NRestarts,ExecMainStartTimestampMonotonic",
        ]).splitlines())
        if values.get("ActiveState") != "active" or values.get("SubState") != "running" or not int(values.get("MainPID", "0")):
            raise RebuildError("backend service is not stable and active")
        services[name] = values
    server.read_production_env()  # existing root:health-app 0640 metadata contract
    config = {}
    path = PRODUCTION / "backend/.env"
    config[str(path)] = data_fingerprint(path)[0]
    for path in [Path("/etc/reva-release/authorized-release.json"), Path("/root/.ssh/authorized_keys")]:
        server.secure_path(path, private=True)
        config[str(path)] = data_fingerprint(path)[0]
    return {"services": services, "configuration": config}


def frontend_configuration():
    environment, fingerprints = {}, {}
    for name in (".env", ".env.production", ".env.local", ".env.production.local"):
        path = PRODUCTION / "frontend" / name
        if os.path.lexists(path):
            fingerprint, raw = data_fingerprint(path)
            # Public endpoint data is allowlisted, never sourced or executed.
            values = public_build_env(raw.decode())
            environment.update(values)
            fingerprints[name] = fingerprint
    rows = json.loads(run(["/usr/bin/pm2", "jlist"]))
    matches = [row for row in rows if row.get("name") == "health-frontend"]
    if len(matches) != 1:
        raise RebuildError("frontend process identity is ambiguous")
    pm = matches[0]["pm2_env"]
    expected = {"pm_cwd": "/opt/health-app/frontend", "pm_exec_path": "/usr/bin/npm",
                "exec_interpreter": "/usr/bin/node", "args": ["start"]}
    if any(pm.get(key) != value for key, value in expected.items()) or pm.get("status") != "online":
        raise RebuildError("frontend process configuration differs")
    # Runtime public overrides must match the build inputs; other PM2 env is never exported.
    for key in PUBLIC_ENV:
        if pm.get(key) is not None:
            value = public_build_env(f"{key}={pm[key]}")[key]
            if key in environment and environment[key] != value:
                raise RebuildError("frontend endpoint sources conflict")
            environment[key] = value
    return environment, fingerprints, expected


def assert_frontend_stopped():
    matches = [row for row in json.loads(run(["/usr/bin/pm2", "jlist"])) if row.get("name") == "health-frontend"]
    if len(matches) != 1 or matches[0].get("pid") != 0 or matches[0].get("pm2_env", {}).get("status") != "stopped":
        raise RebuildError("frontend has not stopped; artifact switch forbidden")


def inspect(publisher, production, operation, source, helper, bootstrap, server, gate):
    gate.verify_release(publisher, publisher)
    gate._latest(gate._get_json, production)  # historical exact-SHA CI, not a relaxation of main gate
    helper._revision_proof(production, source, bootstrap)
    live = git(PRODUCTION, "rev-parse", "HEAD")
    tree = git(source, "rev-parse", "HEAD:frontend")
    actual = git(PRODUCTION, "rev-parse", production + ":frontend")
    validate_binding(publisher, production, tree, actual,
                     bootstrap._read_json(STATE / production / "completed.json"), live_sha=live)
    bootstrap.assert_frontend_rebuild_history()
    if os.path.lexists(LEASE) or os.path.lexists(STATE / "frontend-rebuilds" / operation) or os.path.lexists(BUILDS / operation):
        raise RebuildError("existing operation or business lease; retry forbidden")
    environment, env_fingerprints, pm = frontend_configuration()
    return {"publisher_sha": publisher, "production_sha": production, "operation_id": operation,
            "frontend_tree": tree, "snapshot": snapshot(server), "frontend_env": env_fingerprints,
            "frontend_process": pm, "public_build_env": environment,
            "toolchain": {"node": run(["/usr/bin/node", "--version"]).strip(),
                          "npm": run(["/usr/bin/npm", "--version"]).strip()}}


def write_json(server, path, value):
    server._write_private(path, json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def copy_build_inputs(source, stage, environment):
    for path in (BUILDS,):
        if not path.exists():
            path.mkdir(mode=0o755)
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise RebuildError("unsafe build root")
    # Host processes cannot traverse this root-owned private parent. Only the
    # transient private mount namespace exposes its bind mounts to a unique UID.
    stage.mkdir(mode=0o700)
    for name in ("frontend", "home", "cache"):
        path = stage / name
        path.mkdir(mode=0o700)
        path.chmod(0o777)
    records = git(source, "ls-tree", "-rz", "--full-tree", "HEAD", "--", "frontend").split("\0")
    for record in records:
        if not record:
            continue
        meta, name = record.split("\t", 1)
        mode, kind, blob = meta.split()
        relative = Path(name)
        if mode not in {"100644", "100755"} or kind != "blob" or relative.parts[0] != "frontend" or ".." in relative.parts:
            raise RebuildError("unsupported canonical frontend input")
        data = (source / relative).read_bytes()
        if hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() != blob:
            raise RebuildError("canonical frontend bytes differ")
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(data)
        destination.chmod(0o755 if mode == "100755" else 0o644)
    if environment:
        with (stage / "frontend/.env.production.local").open("x") as stream:
            stream.write("".join(f"{key}={value}\n" for key, value in sorted(environment.items())))
    for path in (stage / "frontend").rglob("*"):
        path.chmod(0o777 if path.is_dir() or path.stat().st_mode & 0o111 else 0o666)


def freeze_artifacts(stage):
    frontend = stage / "frontend"
    if not (frontend / ".next/BUILD_ID").is_file() or not (frontend / "node_modules/next/package.json").is_file():
        raise RebuildError("complete frontend build output missing")
    for name in (".next", "node_modules"):
        root = frontend / name
        artifact_digest(root)  # reject escaping links / special objects before touching ownership
        for path in [root, *root.rglob("*")]:
            info = path.lstat()
            os.chown(path, 0, 0, follow_symlinks=False)
            if not stat.S_ISLNK(info.st_mode):
                path.chmod(0o755 if stat.S_ISDIR(info.st_mode) or info.st_mode & 0o111 else 0o644)
    return hashlib.sha256("".join(artifact_digest(frontend / name) for name in (".next", "node_modules")).encode()).hexdigest()


def assert_unchanged(plan, source, helper, bootstrap, server):
    helper._revision_proof(plan["production_sha"], source, bootstrap)
    if snapshot(server) != plan["snapshot"] or frontend_configuration()[1] != plan["frontend_env"]:
        raise RebuildError("backend or frontend configuration changed during rebuild")


def verify_pages():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for url in ("http://127.0.0.1:30001/privacy", "https://health.executor.life/privacy"):
        verified = False
        for _ in range(10):
            try:
                with opener.open(urllib.request.Request(url, headers={"Cache-Control": "no-cache"}), timeout=10) as response:
                    raw = response.read(2_000_001)
                    verified = response.status == 200 and len(raw) <= 2_000_000 and "可选足迹与分享" in raw.decode()
            except (OSError, UnicodeError):
                verified = False
            if verified:
                break
            time.sleep(2)
        if not verified:
            raise RebuildError("published frontend privacy readback failed")


def execute(plan, source, helper, bootstrap, server):
    publisher, production, operation, tree = (plan[key] for key in ("publisher_sha", "production_sha", "operation_id", "frontend_tree"))
    root = STATE / "frontend-rebuilds"
    root.mkdir(mode=0o700, exist_ok=True)
    server.secure_path(root, directory=True)
    audit = root / operation
    audit.mkdir(mode=0o700)
    server._sync_directory(root)
    write_json(server, audit / "intent.json", receipt(publisher, production, operation, tree, "FRONTEND_STARTED", None))
    write_json(server, audit / "before.json", plan)
    # Durable intent precedes lease and build/service mutations. Never reclaim a stale lease.
    LEASE.mkdir(mode=0o700)
    token = secrets.token_hex(32)
    for name, value in {"token": token, "label": "frontend-rebuild", "stage": str(audit), "started_at": str(int(time.time()))}.items():
        server._write_private(LEASE / name, (value + "\n").encode())
    identity = helper._lease_identity(str(LEASE), token, bootstrap, server)
    stage = BUILDS / operation
    try:
        copy_build_inputs(source, stage, plan["public_build_env"])
        with (audit / "build.log").open("xb") as log:
            subprocess.run(build_command(operation, stage), env=ENV, stdin=subprocess.DEVNULL,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1900)
        # systemd --wait must finish the service and its control group, not merely npm's shell.
        cgroup = Path("/sys/fs/cgroup/system.slice") / f"reva-frontend-build-{operation}.service"
        if cgroup.exists() and any(p.read_text().strip() for p in cgroup.rglob("cgroup.procs")):
            raise RebuildError("build descendants remain")
        digest = freeze_artifacts(stage)
        assert_unchanged(plan, source, helper, bootstrap, server)
        if helper._lease_identity(str(LEASE), token, bootstrap, server) != identity:
            raise RebuildError("business lease changed")
        for name in (".next", "node_modules"):
            live = PRODUCTION / "frontend" / name
            if not stat.S_ISDIR(live.lstat().st_mode) or live.stat().st_dev != audit.stat().st_dev or live.stat().st_dev != (stage / "frontend" / name).stat().st_dev:
                raise RebuildError("frontend artifact switch requires normal same-filesystem directories")
        write_json(server, audit / "install-started.json", receipt(publisher, production, operation, tree, "FRONTEND_INSTALLING", digest))
        run(["/usr/bin/pm2", "stop", "health-frontend"])
        assert_frontend_stopped()
        for name, backup in ((".next", "previous-next"), ("node_modules", "previous-node-modules")):
            (PRODUCTION / "frontend" / name).rename(audit / backup)
            (stage / "frontend" / name).rename(PRODUCTION / "frontend" / name)
        server._sync_directory(PRODUCTION / "frontend")
        server._sync_directory(audit)
        run(["/usr/bin/pm2", "restart", "health-frontend"])
        verify_pages()
        assert_unchanged(plan, source, helper, bootstrap, server)
        if helper._lease_identity(str(LEASE), token, bootstrap, server) != identity:
            raise RebuildError("business lease changed after readback")
        write_json(server, audit / "verified.json", receipt(publisher, production, operation, tree, "FRONTEND_VERIFIED", digest))
        # Under the original launcher flock. If interrupted, the unfinished audit blocks future launchers.
        for name in ("token", "label", "stage", "started_at"):
            (LEASE / name).unlink()
        LEASE.rmdir()
        server._sync_directory(LEASE.parent)
        complete = receipt(publisher, production, operation, tree, "FRONTEND_SUCCEEDED", digest)
        write_json(server, audit / "completed.json", complete)
        return complete
    except BaseException:
        # Never restart the backend, auto-rollback, erase evidence, or retry with another ID.
        if not (audit / "failed.json").exists():
            write_json(server, audit / "failed.json", receipt(publisher, production, operation, tree, "FRONTEND_NEEDS_OPERATOR", None))
        raise RebuildError("frontend rebuild stopped; lease and evidence retained; no retry") from None


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--publisher-sha", required=True)
    parser.add_argument("--production-sha", required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--evidence-sha256")
    args = parser.parse_args()
    try:
        if (not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode
                or os.geteuid() != 0 or sys.executable != "/usr/bin/python3.12"):
            raise RebuildError("isolated system Python root operator required")
        for value in (args.publisher_sha, args.production_sha):
            checked_hex(value, 40)
        checked_hex(args.operation_id, 32)
        if args.evidence_sha256 is not None:
            checked_hex(args.evidence_sha256, 64)
        os.umask(0o077)
        source, helper, bootstrap, server, gate = load_reviewed(args.publisher_sha)
        lock = STATE / "launcher.lock"
        server.secure_path(lock, private=True)
        with lock.open("r+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            helper._assert_lock(server, lock, stream.fileno())
            plan = inspect(args.publisher_sha, args.production_sha, args.operation_id, source, helper, bootstrap, server, gate)
            digest = hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if args.evidence_sha256 is None:
                print(json.dumps({"state": "FRONTEND_PREFLIGHT", "publisher_sha": args.publisher_sha,
                                  "production_sha": args.production_sha, "frontend_tree": plan["frontend_tree"], "evidence_sha256": digest}))
                return 0
            if args.evidence_sha256 != digest:
                raise RebuildError("frontend preflight evidence changed")
            helper._assert_lock(server, lock, stream.fileno())
            print(json.dumps(execute(plan, source, helper, bootstrap, server), sort_keys=True))
        return 0
    except Exception:
        print("frontend rebuild: blocked or failed; inspect private evidence; no automatic retry", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
