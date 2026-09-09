"""Operator-only maintenance, never an SSH RPC or business-deployment bypass.

Run reviewed bytes ONLY with system Python -I -S -B as root at
/var/lib/reva-release/bootstrap/<sha>/source/scripts/trusted_review_reset.py.
Parent governance and fixed-diff G4 approval are prerequisites to execution.
No provisioning, credentials, account selection, retry or recovery is exposed.
"""

import argparse
import configparser
import contextlib
import fcntl
import hashlib
import importlib.util
import io
import json
import os
import re
import runpy
import stat
import subprocess
import sys
import time
from pathlib import Path

STATE = Path("/var/lib/reva-release")
PRODUCTION = Path("/opt/health-app")
SYSTEM_PYTHON = Path("/usr/bin/python3.12")
MAX_RUNTIME_ENTRIES = 100000
SYSTEM_SEARCH_PATHS = frozenset({
    "/usr/lib/python312.zip", "/usr/lib/python3.12", "/usr/lib/python3.12/lib-dynload",
})


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
    if (not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode
            or os.geteuid() != 0
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


def _revision_proof(sha, source, bootstrap):
    path = source / "backend/scripts/activate_health_evidence_runtime.sh"
    bootstrap.secure(path)
    code = path.read_text()
    start, end = "verify_root_owned_nonwritable() {\n", "\nverify_services_active() {\n"
    if code.count(start) != 1 or code.count(end) != 1:
        raise ResetError("reviewed revision proof boundaries changed")
    proof = code[code.index(start):code.index(end)]
    if any(proof.count(name + "() {\n") != 1 for name in (
            "verify_root_owned_nonwritable", "verify_git_metadata_trust",
            "trusted_git", "verify_tracked_worktree_trust", "verify_repo_revision")):
        raise ResetError("reviewed revision proof contract changed")
    # Only this fixed pure function block is evaluated, never activation's
    # argument parser, environment setup, service operations or main routine.
    subprocess.run(["/bin/bash", "-e", "-u", "-c", "set -o pipefail\n" + proof + "\nverify_repo_revision\n"],
        env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C",
             "REPO_PATH": str(PRODUCTION), "EXPECTED_SHA": sha},
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=True, timeout=300)


def _runtime_entries(root, *, exclude=()):
    # Do not follow symlinks, suppress walk errors or allow unbounded trees.
    pending, count = [root], 0
    while pending:
        path = pending.pop()
        count += 1
        if count > MAX_RUNTIME_ENTRIES:
            raise ResetError("runtime inventory exceeds proof bound")
        info = path.lstat()
        yield path, info
        if stat.S_ISDIR(info.st_mode):
            with os.scandir(path) as entries:
                for entry in entries:
                    if Path(entry.path) in exclude:
                        continue
                    if count + len(pending) >= MAX_RUNTIME_ENTRIES:
                        raise ResetError("runtime inventory exceeds proof bound")
                    pending.append(Path(entry.path))


def _validate_application_imports(source, server):
    # Maintenance NEVER imports the live checkout. Verify the complete staged
    # import/resource tree, including files hidden by Git ignore rules.
    backend = source / "backend"
    server.secure_path(backend, directory=True)
    result = subprocess.run(
        ["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
         "-C", str(source), "ls-tree", "-rz", "--full-tree", "HEAD", "--", "backend"],
        env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C",
             "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"},
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=True, timeout=30)
    files, directories = {}, {backend}
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        mode, kind, digest = metadata.decode("ascii").split(" ")
        relative = Path(name.decode("utf-8"))
        if (mode not in {"100644", "100755"} or kind != "blob"
                or re.fullmatch(r"[0-9a-f]{40}", digest) is None
                or relative.is_absolute() or ".." in relative.parts
                or relative.parts[0] != "backend"):
            raise ResetError("unsupported canonical import inventory")
        path = source / relative
        files[path] = digest
        # Retain tracked live-file metadata proof (including hard links) without
        # traversing ignored runtime data. Live bytes are covered by revision proof.
        server.secure_path(PRODUCTION / relative)
        directories.update(parent for parent in path.parents if parent.is_relative_to(backend))
    if backend / "scripts/seed_demo_account.py" not in files:
        raise ResetError("canonical seeder missing")
    seen = set()
    for path, info in _runtime_entries(backend):
        server.secure_path(path, directory=stat.S_ISDIR(info.st_mode))
        if path.name == "__pycache__" or path.suffix in {".pyc", ".pyo"}:
            raise ResetError("application cached code forbidden")
        if stat.S_ISDIR(info.st_mode):
            if path not in directories:
                raise ResetError("unreviewed canonical import directory")
            continue
        if path not in files:
            raise ResetError("unreviewed canonical import file")
        data = path.read_bytes()
        if hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() != files[path]:
            raise ResetError("canonical import content differs")
        seen.add(path)
    if seen != files.keys():
        raise ResetError("incomplete canonical import tree")


def _validate_python_link(path, venv, server):
    aliases = {venv / "bin" / name for name in ("python", "python3", "python3.12")}
    aliases.add(SYSTEM_PYTHON.with_name("python3"))
    seen = set()
    while path != SYSTEM_PYTHON:
        if path not in aliases or path in seen:
            raise ResetError("venv interpreter has an unknown source")
        seen.add(path)
        server.secure_path(path.parent, directory=True)
        info = path.lstat()
        if not stat.S_ISLNK(info.st_mode):
            server.secure_path(path)
            server.secure_path(SYSTEM_PYTHON)
            if path.read_bytes() != SYSTEM_PYTHON.read_bytes():
                raise ResetError("venv interpreter differs from system Python")
            return
        if info.st_uid != 0 or info.st_gid != 0 or info.st_nlink != 1:
            raise ResetError("unsafe interpreter symlink ownership")
        target = Path(os.readlink(path))
        path = Path(os.path.abspath(path.parent / target))
    server.secure_path(SYSTEM_PYTHON)


def _validate_venv(server):
    venv = PRODUCTION / "backend/venv"
    server.secure_path(venv, directory=True)
    config = venv / "pyvenv.cfg"
    server.secure_path(config)
    if config.stat().st_size > 16384:
        raise ResetError("venv configuration exceeds bound")
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.read_string("[venv]\n" + config.read_text())
    if parser.sections() != ["venv"] or parser.defaults():
        raise ResetError("unexpected venv configuration")
    values = dict(parser["venv"])
    if (set(values) - {"home", "include-system-site-packages", "version", "executable", "command"}
            or values.get("home") != str(SYSTEM_PYTHON.parent)
            or values.get("include-system-site-packages") != "false"
            or re.fullmatch(r"3\.12\.[0-9]+", values.get("version", "")) is None
            or values.get("executable", str(SYSTEM_PYTHON)) != str(SYSTEM_PYTHON)):
        raise ResetError("venv configuration differs from fixed system source")
    site = venv / "lib/python3.12/site-packages"
    server.secure_path(site, directory=True)
    _validate_python_link(venv / "bin/python", venv, server)
    for path, info in _runtime_entries(venv):
        if stat.S_ISLNK(info.st_mode):
            if path.parent == venv / "bin" and path.name in {"python", "python3", "python3.12"}:
                _validate_python_link(path, venv, server)
            elif (path == venv / "lib64" and os.readlink(path) == "lib"
                    and info.st_uid == 0 and info.st_gid == 0 and info.st_nlink == 1):
                server.secure_path(venv / "lib", directory=True)
            else:
                raise ResetError("unknown venv symlink")
            continue
        server.secure_path(path, directory=stat.S_ISDIR(info.st_mode))
        # .pth remains metadata-checked, but is never processed: the execution
        # entry requires -S and appends only this exact directory, not addsitedir.
        if (path.suffix == ".egg-link" or "__editable__" in path.name
                or path.name.split(".")[0] in {"sitecustomize", "usercustomize"}
                or (path.name == "site-packages" and path != site)):
            raise ResetError("unknown Python startup or import hook")
        if path.name == "direct_url.json":
            if path.stat().st_size > 16384:
                raise ResetError("dependency source metadata exceeds bound")
            data = json.loads(path.read_bytes())
            if not isinstance(data, dict) or data.get("dir_info", {}).get("editable"):
                raise ResetError("editable dependency source forbidden")


def _validate_production(sha, source, bootstrap, server):
    server.secure_path(PRODUCTION, directory=True)
    _revision_proof(sha, source, bootstrap)
    _validate_application_imports(source, server)
    _validate_venv(server)


def _lease_identity(lease_dir, lease_token, bootstrap, server):
    path = Path(lease_dir)
    if (path != bootstrap.BUSINESS_LEASE or not isinstance(lease_token, str)
            or re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", lease_token) is None):
        raise ResetError("fixed business lease required")
    _private_directory(server, path)
    token = path / "token"
    server.secure_path(token, private=True)
    if token.stat().st_size > 257 or token.read_bytes() not in (
            lease_token.encode(), (lease_token + "\n").encode()):
        raise ResetError("business lease identity differs")
    return tuple((entry.stat().st_dev, entry.stat().st_ino) for entry in (path, token))


def validate_production_execution(sha, lease_dir, lease_token):
    """Read-only canonical runpy interface, called inside deploy -R's lease.

    No launcher lock is acquired: the operator parent already holds it. The
    caller must recheck its lease after return and before .env/seeder execution.
    Venv proof covers root-managed non-replaceability, not wheel provenance.
    """
    try:
        operator_context()
        validate_arguments(sha, "0" * 32)
        source, bootstrap, server = load_reviewed(sha)
        original = _lease_identity(lease_dir, lease_token, bootstrap, server)
        _validate_production(sha, source, bootstrap, server)
        if _lease_identity(lease_dir, lease_token, bootstrap, server) != original:
            raise ResetError("business lease inode changed")
    except Exception:  # noqa: BLE001 -- Preserve a secret-free remote exception boundary.
        raise ResetError("production execution proof failed") from None


class _BoundedSummary(io.StringIO):
    def write(self, value):
        if self.tell() + len(value) > 16384:
            raise ResetError("maintenance output exceeds bound")
        return super().write(value)


def _validate_summary(output):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ResetError("duplicate maintenance summary field")
            result[key] = value
        return result
    summary = json.loads(output, object_pairs_hook=unique)
    counts = {"daily_plan_actions", "timeline_events", "demo_conversation_messages"}
    if (not isinstance(summary, dict) or set(summary) != counts | {"verification"}
            or summary["verification"] != "PASS"
            or any(type(summary[key]) is not int or summary[key] < 1 for key in counts)
            or summary["demo_conversation_messages"] != 2):
        raise ResetError("maintenance summary verification failed")


def _assert_isolated_search_path():
    if not sys.path or any(path not in SYSTEM_SEARCH_PATHS for path in sys.path):
        raise ResetError("unexpected maintenance search path")


def _run_canonical_seeder(source, site, environment, before_write):
    # Called only by the proof-bearing entry below. -I -S supplies OS stdlib
    # paths; no cwd/PYTHONPATH/user site/venv .pth is ever consulted.
    operator_context()
    _assert_isolated_search_path()
    os.chdir(source / "backend")
    sys.path.extend([str(site), str(source / "backend")])
    os.environ.clear()
    os.environ.update(environment)
    entry = source / "backend/scripts/seed_demo_account.py"
    sys.argv = [str(entry), "--secret-free"]
    output = _BoundedSummary()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(_BoundedSummary()):
        module = runpy.run_path(str(entry), run_name="reviewed_maintenance_seeder")
        before_write()
        if module["main"]() != 0:
            raise ResetError("maintenance seeder failed")
    _validate_summary(output.getvalue())


def execute_review_maintenance(sha, lease_dir, lease_token):
    """Fixed lease-internal entry; no account/path/command override or retry."""
    try:
        operator_context()
        _assert_isolated_search_path()
        validate_arguments(sha, "0" * 32)
        source, bootstrap, server = load_reviewed(sha)
        original = _lease_identity(lease_dir, lease_token, bootstrap, server)
        _validate_production(sha, source, bootstrap, server)

        def same_lease():
            if _lease_identity(lease_dir, lease_token, bootstrap, server) != original:
                raise ResetError("business lease changed")

        same_lease()
        # Load credentials only after proofs, without evaluating a shell file.
        # dotenv itself is a root-managed dependency, imported with -S still on.
        site = PRODUCTION / "backend/venv/lib/python3.12/site-packages"
        sys.path.append(str(site))
        try:
            from dotenv import dotenv_values
            values = dotenv_values(stream=io.StringIO(server.read_production_env()), interpolate=False)
        finally:
            sys.path.remove(str(site))
        for key in ("DATABASE_URL", "APP_STORE_REVIEW_DEMO_ACCOUNT", "APP_STORE_REVIEW_DEMO_PASSWORD"):
            if not isinstance(values.get(key), str) or not values[key].strip():
                raise ResetError("required production maintenance configuration missing")
        if not values["DATABASE_URL"].startswith(("postgresql://", "postgresql+psycopg2://")):
            raise ResetError("PostgreSQL maintenance target required")
        environment = {key: value for key, value in values.items() if value is not None}
        environment.update(PATH="/usr/bin:/bin", HOME="/nonexistent")
        same_lease()
        _run_canonical_seeder(source, site, environment, same_lease)
        same_lease()
        print("APP_STORE_REVIEW_RESET_OK")
    except Exception:
        raise ResetError("review maintenance failed; preserve evidence and lease") from None


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
    _validate_production(sha, source, bootstrap, server)
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
    env = server.clean_environment(workspace)
    env.update(DEPLOY_SOURCE_SHA=sha, DEPLOY_ENV_FILE=str(candidate))
    # Expensive proofs must not consume the execution and recovery reserve.
    server._assert_deployment_window(policy)
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
        subprocess.run([server.PYTHON, "-I", "-S", "-B", str(source / "scripts/trusted_release_gate.py"),
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
