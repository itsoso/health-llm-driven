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
import stat
import subprocess
import sys
import time
from pathlib import Path

CONFIG = Path("/etc/reva-release")
POLICY = CONFIG / "authorized-release.json"
STATE = Path("/var/lib/reva-release")
ORIGIN = "https://github.com/itsoso/health-llm-driven.git"
PYTHON = "/usr/bin/python3.12"
DEPLOY_TIMEOUT_SECONDS = 3600
RECOVERY_MARGIN_SECONDS = 3600


class LaunchError(Exception):
    """A sanitized rejection; callers must never receive deployment logs."""


def parse_command(command):
    match = re.fullmatch(r"(run|status|check|claim-build|claim-testflight) ([0-9a-f]{40})", command)
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


def validate_metadata(metadata, *, private=False, directory=False):
    valid_type = stat.S_ISDIR if directory else stat.S_ISREG
    if (
        metadata.st_uid != 0 or not valid_type(metadata.st_mode)
        or metadata.st_mode & 0o022
        or (not directory and metadata.st_nlink != 1)
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
        if data not in ({"sha": sha, "state": "SUCCEEDED"}, {"sha": sha, "state": "NEEDS_OPERATOR"}):
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
        if read_status(policy["sha"], workspace)["state"] != "READY":
            raise LaunchError("authorization already consumed; manual review required")
        _assert_deployment_window(policy)
        _write_private(workspace / "started.json", json.dumps({"sha": policy["sha"], "state": "STARTED"}).encode())
        # The marker fsync covers the new workspace's contents, not the entry
        # that links this newly created directory into STATE. Persist both
        # before any source preparation or external release operation begins.
        _sync_directory(workspace.parent)
        try:
            prepare()
            _assert_deployment_window(policy)
            deploy()
        except Exception:  # noqa: BLE001 -- Persist every failure before sanitizing it at this boundary.
            _write_private(workspace / "completed.json", json.dumps({"sha": policy["sha"], "state": "NEEDS_OPERATOR"}).encode())
            raise LaunchError("release failed; evidence retained, retry forbidden") from None
        # BaseException / process death intentionally leaves STARTED, never READY.
        result = {"sha": policy["sha"], "state": "SUCCEEDED"}
        _write_private(workspace / "completed.json", json.dumps(result).encode())
        return result
    finally:
        os.close(fd)


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


def claim_build(policy, workspace):
    """Reserve build only; upload keeps its own backend-success gate.

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
        if read_status(policy["sha"], workspace)["state"] == "NEEDS_OPERATOR":
            raise LaunchError("failed backend requires operator review before build")
        marker = workspace / "build-started.json"
        if os.path.lexists(marker):
            raise LaunchError("build authorization already consumed; operator review required")
        check_readiness(policy)
        _assert_deployment_window(policy)
        _write_private(marker, json.dumps({"sha": policy["sha"], "state": "STARTED"}).encode())
        _sync_directory(workspace.parent)
        return {"sha": policy["sha"], "state": "CLAIMED"}
    finally:
        os.close(fd)


def claim_testflight(policy, workspace):
    """Consume upload permission only after confirmed backend success.

    A lost response is still a consumed claim. Only an operator may investigate
    the existing EAS build; this interface cannot clear or retry the claim.
    """
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
        if read_status(policy["sha"], workspace)["state"] != "SUCCEEDED":
            raise LaunchError("confirmed backend success required before native claim")
        if _native_started(policy["sha"], workspace):
            raise LaunchError("native authorization already consumed; operator review required")
        _write_private(workspace / "native-started.json", json.dumps({"sha": policy["sha"], "state": "STARTED"}).encode())
        return {"sha": policy["sha"], "state": "CLAIMED"}
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
    execute(git + ["clone", "--no-checkout", "--no-local", "--depth=1", "--branch=main", "--single-branch", ORIGIN, str(source)], workspace, env, log)
    execute(git + ["-C", str(source), "checkout", "-B", "main", policy["sha"]], workspace, env, log)
    executor = source / "scripts/trusted_release_server.py"
    secure_path(executor)
    if hashlib.sha256(executor.read_bytes()).hexdigest() != policy["executor_sha256"]:
        raise LaunchError("source executor differs from reviewed authorization")
    gate = source / "scripts/trusted_release_gate.py"
    secure_path(gate)
    execute([PYTHON, "-I", str(gate), "--sha", policy["sha"], "--workflow-sha", policy["sha"]], source, env, log)


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
    _write_private(candidate, ("\n".join(lines) + "\nDEPLOY_SERVER=health\nDEPLOY_PATH=/opt/health-app\n").encode())
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
