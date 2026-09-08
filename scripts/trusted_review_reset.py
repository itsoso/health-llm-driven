"""Operator-only maintenance, never an SSH RPC or business-deployment bypass.

Run reviewed bytes ONLY with system Python -I as root at
/var/lib/reva-release/bootstrap/<sha>/source/scripts/trusted_review_reset.py.
Parent governance and fixed-diff G4 approval are prerequisites to execution.
No provisioning, credentials, account selection, retry or recovery is exposed.
"""

import argparse
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

STATE = Path("/var/lib/reva-release")
PRODUCTION = Path("/opt/health-app")


class ResetError(Exception):
    """Sanitized operator rejection; never include configuration values."""


def validate_arguments(sha, operation_id):
    if (not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None
            or not isinstance(operation_id, str)
            or re.fullmatch(r"[0-9a-f]{32}", operation_id) is None):
        raise ResetError("exact reviewed SHA and operation ID required")


def _secure_import(path):
    # This check must precede loading the same-directory bootstrap's helpers.
    for item in [*reversed(path.parents), path]:
        info = item.lstat()
        expected_type = stat.S_ISREG if item == path else stat.S_ISDIR
        if (info.st_uid != 0 or info.st_mode & 0o022 or not expected_type(info.st_mode)
                or (item == path and info.st_nlink != 1)):
            raise ResetError("unsafe canonical operator entry")


def operator_context():
    if (not sys.flags.isolated or os.geteuid() != 0
            or sys.executable not in ("/usr/bin/python3", "/usr/bin/python3.12")
            or "SSH_ORIGINAL_COMMAND" in os.environ):
        raise ResetError("isolated system Python operator execution required")
    _secure_import(Path(sys.executable).resolve(strict=True))
    os.umask(0o077)
    sys.dont_write_bytecode = True


def load_reviewed(sha):
    source = STATE / "bootstrap" / sha / "source"
    entry = source / "scripts/trusted_review_reset.py"
    if Path(__file__).absolute() != entry:
        raise ResetError("operator entry must use fresh canonical staging")
    bootstrap_path = entry.with_name("bootstrap_trusted_release.py")
    _secure_import(entry)
    _secure_import(bootstrap_path)
    if os.path.lexists(entry.parent / "__pycache__"):
        raise ResetError("canonical operator staging must not contain cached code")
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("reviewed_reset_bootstrap", bootstrap_path)
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    for path in source.rglob("*"):
        bootstrap.secure(path)
        if path.name == "__pycache__" or path.suffix == ".pyc":
            raise ResetError("canonical operator staging must not contain cached code")
    reviewed, server = bootstrap.reviewed_source(sha)
    if reviewed != source:
        raise ResetError("canonical source mismatch")
    return source, bootstrap, server


def _private_directory(server, path):
    server.secure_path(path, directory=True)
    if stat.S_IMODE(path.lstat().st_mode) != 0o700:
        raise ResetError("private operation directory required")


def _marker(sha, operation_id, state):
    return {"sha": sha, "operation_id": operation_id, "state": state}


def _assert_previous_resets(bootstrap, server):
    # Include other release SHAs: old unknown work is not a new authorization.
    for workspace in STATE.iterdir():
        if re.fullmatch(r"[0-9a-f]{40}", workspace.name) is None:
            continue
        server.secure_path(workspace, directory=True)
        root = workspace / "review-resets"
        if not os.path.lexists(root):
            continue
        _private_directory(server, root)
        for operation in root.iterdir():
            if re.fullmatch(r"[0-9a-f]{32}", operation.name) is None:
                raise ResetError("unknown review reset evidence")
            _private_directory(server, operation)
            if {path.name for path in operation.iterdir()} != {"started.json", "completed.json"}:
                raise ResetError("previous review reset termination unproven")
            for name, state in (("started.json", "STARTED"), ("completed.json", "SUCCEEDED")):
                if bootstrap._read_json(operation / name) != _marker(workspace.name, operation.name, state):
                    raise ResetError("previous review reset termination unproven")


def _assert_lock(server, lock, fd):
    server.secure_path(lock, private=True)
    info = os.fstat(fd)
    server.validate_metadata(info, private=True)
    current = lock.lstat()
    if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
        raise ResetError("original launcher lock changed")


def _validate_workspace(sha, source, bootstrap, server):
    if bootstrap.canonical_source(sha) != source:
        raise ResetError("canonical source mismatch")
    for path in (source / "deploy.sh", source / "scripts/trusted_review_reset.py"):
        bootstrap.secure(path)
    policy = server.validate_policy(bootstrap._read_json(bootstrap.CONFIG / "authorized-release.json"), now=time.time())
    server._assert_deployment_window(policy)
    digest = hashlib.sha256((source / "scripts/trusted_release_server.py").read_bytes()).hexdigest()
    bootstrap.secure(bootstrap.INSTALLED)
    if (policy["sha"] != sha or policy["executor_sha256"] != digest
            or hashlib.sha256(bootstrap.INSTALLED.read_bytes()).hexdigest() != digest):
        raise ResetError("installed authorization differs from canonical source")
    workspace = STATE / sha
    _private_directory(server, workspace)
    for name, state in (("started.json", "STARTED"), ("completed.json", "SUCCEEDED")):
        if bootstrap._read_json(workspace / name) != {"sha": sha, "state": state}:
            raise ResetError("confirmed backend success required")
    if os.path.lexists(bootstrap.BUSINESS_LEASE):
        raise ResetError("business lease exists; operator review required")
    server.validate_loopback(policy)
    server.secure_path(Path(server.PYTHON))
    bindir = workspace / "bin"
    _private_directory(server, bindir)
    _private_directory(server, workspace / "home")
    if {path.name for path in bindir.iterdir()} != {"ssh", "scp", "python3"}:
        raise ResetError("unexpected deployment wrapper inventory")
    for command in ("ssh", "scp", "python3"):
        target = server.PYTHON if command == "python3" else f"/usr/bin/{command}"
        args = "" if command == "python3" else " -F /etc/reva-release/loopback.conf"
        wrapper = bindir / command
        server.secure_path(wrapper)
        if (stat.S_IMODE(wrapper.lstat().st_mode) != 0o700
                or wrapper.read_bytes() != f'#!/bin/sh\nexec {target}{args} "$@"\n'.encode()):
            raise ResetError("deployment wrapper differs from reviewed bytes")
    candidate = workspace / "deployment.env"
    # Reuse the server's fixed production-env metadata/read boundary and exact
    # candidate semantics. Drift fails closed; never rewrite an existing env.
    production = server.read_production_env()
    lines = [line for line in production.splitlines() if not line.startswith(("DEPLOY_SERVER=", "DEPLOY_PATH="))]
    expected = ("\n".join(lines) + "\nDEPLOY_SERVER=health\nDEPLOY_PATH=/opt/health-app\n").encode()
    if server._read_private(candidate) != expected:
        raise ResetError("deployment environment differs from fixed candidate")
    server.secure_path(PRODUCTION, directory=True)
    server.secure_path(PRODUCTION / ".git/config")
    result = subprocess.run(["/usr/bin/git", "-c", "core.hooksPath=/dev/null",
        "-c", "core.fsmonitor=false", "-C", str(PRODUCTION), "rev-parse", "HEAD"],
        env=bootstrap.ENV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, check=True, timeout=90)
    if result.stdout.strip() != sha:
        raise ResetError("production revision differs from reviewed SHA")
    env = server.clean_environment(workspace)
    env.update(DEPLOY_SOURCE_SHA=sha, DEPLOY_ENV_FILE=str(candidate))
    return env


def reset_review(sha, operation_id):
    validate_arguments(sha, operation_id)
    source, bootstrap, server = load_reviewed(sha)
    server.secure_path(STATE, directory=True)
    lock = STATE / "launcher.lock"
    server.secure_path(lock, private=True)
    # No O_CREAT: losing the installed lock inode is a blocking incident.
    fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
    try:
        _assert_lock(server, lock, fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _assert_lock(server, lock, fd)
        _assert_previous_resets(bootstrap, server)
        workspace = STATE / sha
        root = workspace / "review-resets"
        operation = root / operation_id
        if os.path.lexists(operation):
            raise ResetError("operation ID already consumed; retry forbidden")
        server.secure_path(Path(server.PYTHON))
        env = server.clean_environment(workspace)
        env.update(PATH="/usr/bin:/bin", HOME="/nonexistent")
        subprocess.run([server.PYTHON, "-I", str(source / "scripts/trusted_release_gate.py"),
            "--sha", sha, "--workflow-sha", sha], cwd=source, env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=True, timeout=90)
        # Production credentials are read only after the credential-free CI gate.
        # Validate the current target and authorization under the original lock.
        env = _validate_workspace(sha, source, bootstrap, server)
        _assert_lock(server, lock, fd)
        if not os.path.lexists(root):
            root.mkdir(mode=0o700)
        _private_directory(server, root)
        server._sync_directory(workspace)
        operation.mkdir(mode=0o700)
        _private_directory(server, operation)
        server._sync_directory(root)
        server._write_private(operation / "started.json", json.dumps(_marker(sha, operation_id, "STARTED"), sort_keys=True).encode())
        # Persist both the intent's directory and the operation's parent entry.
        server._sync_directory(root)
        try:
            subprocess.run(["/bin/bash", str(source / "deploy.sh"), "-R"], cwd=source, env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=True, timeout=server.DEPLOY_TIMEOUT_SECONDS, start_new_session=True)
        except BaseException:  # noqa: BLE001 -- Timeout/interruption cannot prove remote termination.
            server._write_private(operation / "completed.json", json.dumps(_marker(sha, operation_id, "NEEDS_OPERATOR"), sort_keys=True).encode())
            # deploy.sh owns its business lease and strict receipt. Never remove
            # the lease, signal remote work, retry, or expose subprocess output.
            raise ResetError("review reset outcome unknown; preserve evidence and lease") from None
        result = _marker(sha, operation_id, "SUCCEEDED")
        server._write_private(operation / "completed.json", json.dumps(result, sort_keys=True).encode())
        return result
    finally:
        os.close(fd)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ResetError("invalid operator arguments")


def main():
    try:
        operator_context()
        parser = _Parser(description=__doc__, allow_abbrev=False)
        parser.add_argument("--sha", required=True)
        parser.add_argument("--operation-id", required=True)
        args = parser.parse_args()
        result = reset_review(args.sha, args.operation_id)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt):  # noqa: BLE001 -- No secret-bearing exception text crosses this boundary.
        print("review reset: validation or execution failed; preserve evidence for operator review", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
