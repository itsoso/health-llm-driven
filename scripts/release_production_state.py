#!/usr/bin/env python3
"""Read-only, fail-closed probes for the live production release surfaces."""

import sys

_NETWORK_CLI_MODES = frozenset({"server", "server-under-lock", "mobile"})
if __name__ == "__main__" and sys.argv[1:2] and sys.argv[1] in _NETWORK_CLI_MODES:
    print(
        "production network probes are frozen; use the external trusted Gate",
        file=sys.stderr,
    )
    raise SystemExit(78)

import atexit
import hashlib
import importlib.util
import json
import os
import re
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


ROOT = Path(__file__).resolve().parents[1]
PROBE_TIMEOUT_SECONDS = 300
MAX_PROBE_BYTES = 64 * 1024
MOBILE_RUNTIME_PAGE_LIMIT = 50
MOBILE_RUNTIME_MAX_PAGES = 20

_SSH_BINARY = "/usr/bin/ssh"
_EAS_BINARY = ROOT / "scripts/eas-cli-tool/node_modules/.bin/eas"
_LOCKED_EAS_HELPER = ROOT / "scripts/locked_eas_cli.py"
_PREPARED_EAS_WORKSPACE: Path | None = None
_PREPARED_EAS_BINARY: Path | None = None
_PRODUCTION_SERVER = "root@39.98.206.178"
_PRODUCTION_CHANNEL = "production"
_PRODUCTION_PLATFORM = "ios"
_PRODUCTION_KNOWN_HOST = (
    b"39.98.206.178 ssh-ed25519 "
    b"AAAAC3NzaC1lZDI1NTE5AAAAIC6Wg0sU8uYKL4xq1HCCpPxTPy24LOxvzr2uSpycraav\n"
)
_SHA_RE = re.compile(r"[0-9a-f]{40}")
_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)

_REMOTE_PROBE = r"""exec /usr/bin/python3 - __REVA_EXPECTED_RELEASE_LOCK_TOKEN__ <<'PY'
import hashlib
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import sys
import time
from datetime import datetime, timezone

REPO = "/opt/health-app"
BACKEND_CWD = "/opt/health-app/backend"
STATE_ROOT = "/var/lib/health-app/release-state"
TERMINAL_MARKER_PATH = "/var/lib/health-app/release-state/runtime-state-terminal.json"
FRONTEND_RECEIPT_PATH = "/var/lib/health-app/release-state/frontend-runtime.json"
MAC_RECEIPT_PATH = "/var/lib/health-app/release-state/mac-runtime.json"
MAC_JOURNAL_PATH = "/var/lib/health-app/release-state/mac-release.transaction.json"
REMOTE_RELEASE_LOCK_PATH = "/var/lib/health-app/release-state/deploy.lock"
MAC_ASSET_ROOT = "/opt/health-app-shared/assets/mac"
MAC_CURRENT_PATH = "/opt/health-app-shared/assets/mac/current.json"
MAC_RELEASES_ROOT = "/opt/health-app-shared/assets/mac/releases"
MAC_STABLE_PATH = "/opt/health-app-shared/assets/xiaoba-mac.dmg"
PUBLIC_MAC_BASE = "https://health.executor.life"
NEXT_BUILD_ID_RELATIVE = ".next/BUILD_ID"
NEXT_BUILD_ID_PATH = os.path.join(
    "/opt/health-app/frontend", NEXT_BUILD_ID_RELATIVE
)
TERMINAL_MARKER = os.path.basename(TERMINAL_MARKER_PATH)
FRONTEND_RECEIPT = os.path.basename(FRONTEND_RECEIPT_PATH)
MAC_RECEIPT = os.path.basename(MAC_RECEIPT_PATH)
MAC_JOURNAL = os.path.basename(MAC_JOURNAL_PATH)
SHA_RE = re.compile(r"[0-9a-f]{40}")
HEX64_RE = re.compile(r"[0-9a-f]{64}")
TX_RE = re.compile(r"[0-9a-f]{32}")
BUILD_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,128}")
TOKEN_RE = re.compile(r"[A-Za-z0-9._:-]{1,128}")
VERSION_RE = re.compile(r"[0-9]+(?:\.[0-9]+){1,3}")
MAC_BUILD_RE = re.compile(r"[0-9]+(?:\.[0-9]+){0,2}")
UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    re.IGNORECASE,
)
CDHASH_RE = re.compile(r"[0-9a-f]{40}")
ARCHITECTURES = {"arm64", "x86_64"}
MAC_BUNDLE_ID = "life.executor.health.mac"
MAC_TEAM_ID = "QA2U724DAN"
MAC_MAX_ARTIFACT_BYTES = 1024 * 1024 * 1024
COMMAND_OUTPUT_CAP = 64 * 1024
PUBLIC_HEADER_TIMEOUT_SECONDS = 15
PUBLIC_MANIFEST_TIMEOUT_SECONDS = 30
PUBLIC_ARTIFACT_TIMEOUT_SECONDS = 60
MAIN_PID_PROPERTY = "MainPID"
PROCESS_UNITS = (
    "health-backend.service",
    "celery-worker.service",
    "celery-beat.service",
)
ALL_UNITS = ("health-backend.socket", *PROCESS_UNITS)
SAFE_ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
    "HOME": "/root",
    "PM2_HOME": "/root/.pm2",
    "LANG": "C",
    "LC_ALL": "C",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_ATTR_NOSYSTEM": "1",
    "GIT_OPTIONAL_LOCKS": "0",
}


def fail(message):
    raise RuntimeError(message)


EXPECTED_RELEASE_LOCK_TOKEN = sys.argv[1]
if EXPECTED_RELEASE_LOCK_TOKEN == "none":
    EXPECTED_RELEASE_LOCK_TOKEN = None
elif TOKEN_RE.fullmatch(EXPECTED_RELEASE_LOCK_TOKEN) is None:
    fail("invalid expected release lock token")


def run(argv, *, cwd=None, discard_stdout=False):
    try:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=SAFE_ENV,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError:
        fail(f"command could not start: {argv[0]}")
    selector = selectors.DefaultSelector()
    streams = {process.stdout: bytearray(), process.stderr: bytearray()}
    total = 0
    deadline = time.monotonic() + 15
    try:
        for stream in streams:
            assert stream is not None
            selector.register(stream, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                fail(f"command timed out: {argv[0]}")
            events = selector.select(min(remaining, 0.25))
            for key, _mask in events:
                chunk = os.read(key.fd, min(16 * 1024, COMMAND_OUTPUT_CAP + 1 - total))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                streams[key.fileobj].extend(chunk)
                total += len(chunk)
                if total > COMMAND_OUTPUT_CAP:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    fail(f"command output exceeds safety cap: {argv[0]}")
        status = process.wait(timeout=max(0.01, deadline - time.monotonic()))
    finally:
        selector.close()
    if status != 0:
        fail(f"command failed: {argv[0]}")
    try:
        stdout = bytes(streams[process.stdout]).decode("utf-8", errors="strict")
        bytes(streams[process.stderr]).decode("utf-8", errors="strict")
    except UnicodeError:
        fail(f"command returned non-UTF-8 output: {argv[0]}")
    return "" if discard_stdout else stdout


def json_value(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                fail(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    return json.loads(
        raw,
        object_pairs_hook=unique,
        parse_constant=lambda value: fail(f"invalid JSON constant: {value}"),
    )


DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
DIR_FLAGS |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
FILE_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
FILE_FLAGS |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)


def open_root_directory(path, *, mode):
    descriptor = os.open(path, DIR_FLAGS)
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != mode
    ):
        os.close(descriptor)
        fail(f"unsafe root directory: {path}")
    return descriptor


def read_root_file(directory_fd, name, *, mode, maximum, allow_missing=False):
    try:
        descriptor = os.open(name, FILE_FLAGS, dir_fd=directory_fd)
    except FileNotFoundError:
        if allow_missing:
            return None
        raise
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_gid != 0
            or stat.S_IMODE(metadata.st_mode) != mode
            or metadata.st_nlink != 1
            or metadata.st_size <= 0
            or metadata.st_size > maximum
        ):
            fail(f"unsafe root file: {name}")
        raw = os.read(descriptor, maximum + 1)
        if (
            len(raw) > maximum
            or len(raw) != metadata.st_size
            or os.read(descriptor, 1)
        ):
            fail(f"oversized root file: {name}")
        after = os.fstat(descriptor)
        try:
            current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            fail(f"root file changed during verification: {name}")
        expected_identity = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
        )
        if (
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            != expected_identity
            or (
                current.st_dev,
                current.st_ino,
                current.st_size,
                current.st_mtime_ns,
            )
            != expected_identity
        ):
            fail(f"root file changed during verification: {name}")
        return raw, after
    finally:
        os.close(descriptor)


def hash_root_file(
    directory_fd,
    name,
    *,
    mode,
    expected_size,
    maximum,
    expected_uid=0,
    expected_gid=0,
):
    descriptor = os.open(name, FILE_FLAGS, dir_fd=directory_fd)
    try:
        metadata = os.fstat(descriptor)
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != expected_uid
            or metadata.st_gid != expected_gid
            or stat.S_IMODE(metadata.st_mode) != mode
            or metadata.st_nlink != 1
            or metadata.st_size != expected_size
            or metadata.st_size <= 0
            or metadata.st_size > maximum
            or (metadata.st_dev, metadata.st_ino) != (entry.st_dev, entry.st_ino)
        ):
            fail(f"unsafe root artifact: {name}")
        digest = hashlib.sha256()
        total = 0
        while total <= maximum:
            chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - total))
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
        if total != expected_size or total > maximum:
            fail(f"invalid root artifact size: {name}")
        after = os.fstat(descriptor)
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            != (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
            or (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino)
        ):
            fail(f"root artifact changed during verification: {name}")
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def public_url(path):
    if not isinstance(path, str) or not path.startswith("/") or not path.isascii():
        fail("invalid public Mac path")
    if re.fullmatch(r"/[A-Za-z0-9._/-]+", path) is None or ".." in path:
        fail("invalid public Mac path")
    return PUBLIC_MAC_BASE + path


def public_process(path, extra, *, max_time):
    if isinstance(max_time, bool) or not isinstance(max_time, int) or max_time <= 0:
        fail("invalid public Mac probe timeout")
    argv = [
        "/usr/bin/curl",
        "--silent",
        "--show-error",
        "--fail",
        "--write-out", "%{http_code}",
        "--proto", "=https",
        "--tlsv1.2",
        "--max-redirs", "0",
        "--connect-timeout", "10",
        "--max-time", str(max_time),
        "--header", "Accept-Encoding: identity",
        *extra,
        public_url(path),
    ]
    try:
        return subprocess.Popen(
            argv,
            env=SAFE_ENV,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        fail(f"public Mac probe could not start: {error.__class__.__name__}")


def read_public_bytes(path, *, maximum):
    process = public_process(
        path,
        ("--request", "GET"),
        max_time=PUBLIC_MANIFEST_TIMEOUT_SECONDS,
    )
    assert process.stdout is not None
    value = bytearray()
    maximum_wire = maximum + 3
    while len(value) <= maximum_wire:
        chunk = process.stdout.read(
            min(1024 * 1024, maximum_wire + 1 - len(value))
        )
        if not chunk:
            break
        value.extend(chunk)
    if len(value) > maximum_wire:
        process.kill()
        process.wait()
        fail("public Mac response exceeds the safety cap")
    try:
        status = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        fail("public Mac response did not terminate")
    if status != 0 or not value:
        fail("public Mac response failed")
    if len(value) < 3 or value[-3:] != b"200":
        fail("public Mac response was not exact HTTP 200")
    return bytes(value[:-3])


def public_artifact_marker(path):
    process = public_process(
        path,
        ("--head", "--dump-header", "-", "--output", "/dev/null"),
        max_time=PUBLIC_HEADER_TIMEOUT_SECONDS,
    )
    assert process.stdout is not None
    raw = process.stdout.read(16 * 1024 + 4)
    if len(raw) > 16 * 1024 + 3 or process.stdout.read(1):
        process.kill()
        process.wait()
        fail("public Mac headers exceed the safety cap")
    try:
        status = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        fail("public Mac header probe did not terminate")
    if status != 0:
        fail("public Mac header probe failed")
    try:
        lines = raw.decode("ascii", errors="strict").splitlines()
    except UnicodeError:
        fail("public Mac headers are not ASCII")
    if not lines or not re.fullmatch(r"200", lines[-1]):
        fail("public Mac header probe was not exact HTTP 200")
    lines = lines[:-1]
    status_lines = [line for line in lines if line.startswith("HTTP/")]
    if len(status_lines) != 1 or re.fullmatch(r"HTTP/[0-9.]+ 200(?: .*)?", status_lines[0]) is None:
        fail("public Mac header probe was not exact HTTP 200")
    markers = [
        line.split(":", 1)[1].strip()
        for line in lines
        if line.lower().startswith("x-reva-artifact:")
    ]
    if len(markers) != 1:
        fail("public Mac artifact marker is missing or ambiguous")
    return markers[0]


def hash_public_artifact(path, *, expected_size, maximum):
    process = public_process(
        path,
        ("--request", "GET"),
        max_time=PUBLIC_ARTIFACT_TIMEOUT_SECONDS,
    )
    assert process.stdout is not None
    digest = hashlib.sha256()
    wire_total = 0
    body_total = 0
    tail = b""
    maximum_wire = maximum + 3
    while wire_total <= maximum_wire:
        chunk = process.stdout.read(
            min(1024 * 1024, maximum_wire + 1 - wire_total)
        )
        if not chunk:
            break
        wire_total += len(chunk)
        combined = tail + chunk
        if len(combined) > 3:
            body = combined[:-3]
            digest.update(body)
            body_total += len(body)
            tail = combined[-3:]
        else:
            tail = combined
    if wire_total > maximum_wire:
        process.kill()
        process.wait()
        fail("public Mac artifact exceeds the safety cap")
    try:
        status = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        fail("public Mac artifact probe did not terminate")
    if status != 0 or body_total != expected_size:
        fail("public Mac artifact size does not match runtime receipt")
    if tail != b"200":
        fail("public Mac artifact was not exact HTTP 200")
    return digest.hexdigest()


def valid_utc_timestamp(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo == timezone.utc


def assert_mac_release_quiescent(state_fd):
    try:
        os.stat(MAC_JOURNAL, dir_fd=state_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    except OSError:
        fail("Mac release transaction state cannot be inspected safely")
    else:
        fail("Mac release transaction is still in progress")

    lock_name = os.path.basename(REMOTE_RELEASE_LOCK_PATH)
    if os.path.dirname(REMOTE_RELEASE_LOCK_PATH) != STATE_ROOT:
        fail("unified remote release lease path is outside release state")
    try:
        entries = os.listdir(state_fd)
    except OSError:
        fail("unified remote release lease cannot be inspected safely")
    for entry in entries:
        if (
            entry == lock_name
            or entry.startswith(f".{lock_name}.")
            or entry.startswith(f"{lock_name}.")
        ):
            fail("unified remote release lease is still held")


def assert_expected_release_lock(state_fd):
    if EXPECTED_RELEASE_LOCK_TOKEN is None:
        fail("expected release lock token is missing")
    try:
        os.stat(MAC_JOURNAL, dir_fd=state_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    except OSError:
        fail("Mac release transaction state cannot be inspected safely")
    else:
        fail("Mac release transaction is still in progress")

    lock_name = os.path.basename(REMOTE_RELEASE_LOCK_PATH)
    entries = os.listdir(state_fd)
    recovery_entries = [
        entry
        for entry in entries
        if entry.startswith(f".{lock_name}.") or entry.startswith(f"{lock_name}.")
    ]
    if recovery_entries or entries.count(lock_name) != 1:
        fail("expected unified remote release lease is ambiguous")
    lock_fd = os.open(lock_name, DIR_FLAGS, dir_fd=state_fd)
    try:
        metadata = os.fstat(lock_fd)
        expected_names = {
            "schema", "token", "label", "stage", "started_at", "source_sha",
            "source_tree", "state", "surface", "operation", "channel",
            "transaction_id", "baseline_digest", "request_digest",
            "terminal_digest",
        }
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_gid != 0
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or set(os.listdir(lock_fd)) != expected_names
        ):
            fail("unsafe expected unified remote release lease")
        token_raw, _token_metadata = read_root_file(
            lock_fd, "token", mode=0o600, maximum=256
        )
        if token_raw != (EXPECTED_RELEASE_LOCK_TOKEN + "\n").encode("ascii"):
            fail("release lock ownership changed during production proof")
        values = {}
        for name in expected_names:
            raw, _entry_metadata = read_root_file(
                lock_fd, name, mode=0o600, maximum=512
            )
            try:
                value = raw.decode("ascii")
            except UnicodeError:
                fail("non-ASCII expected unified remote release lease")
            if not value.endswith("\n") or "\n" in value[:-1]:
                fail("malformed expected unified remote release lease")
            values[name] = value[:-1]
        if (
            values["schema"] != "2"
            or re.fullmatch(r"[0-9a-f]{64}", values["token"]) is None
            or values["token"] != EXPECTED_RELEASE_LOCK_TOKEN
            or re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", values["label"]) is None
            or re.fullmatch(
                r"/tmp/health-app-backup-preflight-(?:[1-9][0-9]*-[1-9][0-9]*|[0-9a-f]{64})",
                values["stage"],
            )
            is None
            or not valid_utc_timestamp(values["started_at"])
            or SHA_RE.fullmatch(values["source_sha"]) is None
            or SHA_RE.fullmatch(values["source_tree"]) is None
            or values["state"] not in {"allocating", "sealed", "mutating", "completed"}
            or values["surface"] not in {"server", "mobile", "native", "mac"}
            or values["channel"] != "production"
            or re.fullmatch(r"[0-9a-f]{32}", values["transaction_id"]) is None
            or HEX64_RE.fullmatch(values["request_digest"]) is None
            or re.fullmatch(r"-|[0-9a-f]{64}", values["baseline_digest"]) is None
            or re.fullmatch(r"-|[0-9a-f]{64}", values["terminal_digest"]) is None
        ):
            fail("unsafe expected unified remote release lease")
        allowed_operations = {
            "server": {
                "all", "frontend", "backend", "env", "health-evidence",
                "app-store-review-reset", "restart", "mac-routes",
            },
            "mobile": {"forward", "rollback"},
            "native": {"remote-build"},
            "mac": {"publish", "recover", "rollback"},
        }
        if values["operation"] not in allowed_operations[values["surface"]]:
            fail("unsafe expected unified remote release lease")
        expected_label = (
            f"deploy:{values['operation']}"
            if values["surface"] == "server"
            else f"coordinator:{values['surface']}:{values['operation']}"
        )
        if values["label"] != expected_label:
            fail("unsafe expected unified remote release lease")
        return (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_ctime_ns,
        )
    finally:
        os.close(lock_fd)


def root_file_identity(value):
    if value is None:
        return None
    raw, metadata = value
    return (
        hashlib.sha256(raw).hexdigest(),
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def checkout_identity():
    revision = run(
        [
            "/usr/bin/git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "filter.lfs.process=",
            "-c",
            "filter.lfs.required=false",
            "rev-parse",
            "HEAD",
        ],
        cwd=REPO,
    ).strip()
    if SHA_RE.fullmatch(revision) is None:
        fail("invalid checkout revision")
    repository_clean = not run(
        [
            "/usr/bin/git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "filter.lfs.process=",
            "-c",
            "filter.lfs.required=false",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        cwd=REPO,
    ).strip()
    return revision, repository_clean


def backend_process_identity(marker_metadata):
    for unit in ALL_UNITS:
        active = run(
            [
                "/usr/bin/systemctl",
                "show",
                unit,
                "--property=ActiveState",
                "--value",
            ]
        ).strip()
        if active != "active":
            fail(f"inactive backend unit: {unit}")

    boot_now_ns = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    wall_now_ns = time.time_ns()
    ticks_per_second = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
    identity = []
    for unit in PROCESS_UNITS:
        pid_raw = run(
            [
                "/usr/bin/systemctl",
                "show",
                unit,
                f"--property={MAIN_PID_PROPERTY}",
                "--value",
            ]
        ).strip()
        if not pid_raw.isascii() or not pid_raw.isdecimal() or int(pid_raw) <= 1:
            fail(f"invalid MainPID for {unit}")
        pid = int(pid_raw)
        process_root = f"/proc/{pid}"
        process_stat = open(f"{process_root}/stat", encoding="ascii").read()
        try:
            fields = process_stat.rsplit(")", 1)[1].strip().split()
            start_ticks = int(fields[19])
        except (IndexError, ValueError):
            fail(f"invalid process identity for {unit}")
        cwd = os.path.realpath(f"{process_root}/cwd")
        if cwd != BACKEND_CWD:
            fail(f"unexpected process cwd for {unit}")
        start_boot_ns = start_ticks * 1_000_000_000 // ticks_per_second
        start_wall_ns = wall_now_ns - (boot_now_ns - start_boot_ns)
        if marker_metadata.st_mtime_ns < start_wall_ns:
            fail(f"backend process restarted after terminal marker: {unit}")
        identity.append(
            {"unit": unit, "pid": pid, "start_ticks": start_ticks, "cwd": cwd}
        )
    return identity


def frontend_process_identity():
    processes = json_value(run(["/usr/bin/pm2", "jlist"]))
    if not isinstance(processes, list):
        fail("invalid PM2 process list")
    matches = [
        process
        for process in processes
        if isinstance(process, dict) and process.get("name") == "health-frontend"
    ]
    if len(matches) != 1:
        fail("ambiguous frontend PM2 process")
    frontend_process = matches[0]
    frontend_environment = frontend_process.get("pm2_env")
    if not isinstance(frontend_environment, dict) or frontend_environment.get("status") != "online":
        fail("frontend PM2 process is not online")
    frontend_pid = frontend_process.get("pid")
    frontend_uptime = frontend_environment.get("pm_uptime")
    if (
        isinstance(frontend_pid, bool)
        or not isinstance(frontend_pid, int)
        or frontend_pid <= 1
        or isinstance(frontend_uptime, bool)
        or not isinstance(frontend_uptime, int)
        or frontend_uptime <= 0
    ):
        fail("invalid frontend PM2 identity")
    return frontend_pid, frontend_uptime


def assert_local_health():
    for label, url in (
        ("backend", "http://127.0.0.1:8000/api/v1/health"),
        ("frontend", "http://127.0.0.1:3000/"),
    ):
        status = run(
            [
                "/usr/bin/curl",
                "--silent",
                "--show-error",
                "--max-time",
                "5",
                "--max-redirs",
                "0",
                "--output",
                "/dev/null",
                "--write-out",
                "%{http_code}",
                url,
            ]
        )
        if status != "200":
            fail(f"{label} health did not return exact HTTP 200")


initial_checkout_identity = checkout_identity()
revision, repository_clean = initial_checkout_identity

state_fd = open_root_directory(STATE_ROOT, mode=0o700)
try:
    marker_raw, marker_metadata = read_root_file(
        state_fd,
        TERMINAL_MARKER,
        mode=0o600,
        maximum=64 * 1024,
    )
    initial_terminal_identity = root_file_identity((marker_raw, marker_metadata))
    marker = json_value(marker_raw.decode("utf-8", errors="strict"))
    marker_keys = {
        "version",
        "old_sha",
        "candidate_sha",
        "terminal_sha",
        "transaction_id",
        "target",
        "phase",
        "result",
        "reap_name",
    }
    if not isinstance(marker, dict) or set(marker) != marker_keys:
        fail("invalid terminal marker fields")
    if marker.get("version") != 1 or isinstance(marker.get("version"), bool):
        fail("invalid terminal marker version")
    for field in ("old_sha", "candidate_sha", "terminal_sha"):
        if not isinstance(marker.get(field), str) or SHA_RE.fullmatch(marker[field]) is None:
            fail(f"invalid terminal marker {field}")
    transaction_id = hashlib.sha256(
        f"{marker['old_sha']}:{marker['candidate_sha']}".encode()
    ).hexdigest()[:32]
    if marker.get("transaction_id") != transaction_id or TX_RE.fullmatch(transaction_id) is None:
        fail("invalid terminal transaction")
    if marker.get("reap_name") != f"runtime-state-transaction.reap-{transaction_id}":
        fail("invalid terminal reap name")
    if os.path.lexists(os.path.join(STATE_ROOT, marker["reap_name"])):
        fail("terminal cleanup is incomplete")
    if marker.get("target") == "candidate":
        expected_terminal = {
            "phase": "COMMITTED",
            "result": "finalized",
            "terminal_sha": marker["candidate_sha"],
        }
    elif marker.get("target") == "old":
        expected_terminal = {
            "phase": "RESTORE_FINALIZED",
            "result": "RESTORE_FINALIZED",
            "terminal_sha": marker["old_sha"],
        }
    else:
        fail("invalid terminal target")
    if any(marker.get(key) != value for key, value in expected_terminal.items()):
        fail("invalid terminal marker contract")
    if marker["terminal_sha"] != revision:
        fail("backend runtime marker does not match checkout")

    initial_backend_process_identity = backend_process_identity(marker_metadata)
    process_identity = initial_backend_process_identity
    backend_proof_id = hashlib.sha256(
        json.dumps(
            {
                "revision": revision,
                "transaction_id": transaction_id,
                "processes": process_identity,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    initial_frontend_process_identity = frontend_process_identity()
    frontend_pid, frontend_uptime = initial_frontend_process_identity
    assert_local_health()

    receipt_value = read_root_file(
        state_fd,
        FRONTEND_RECEIPT,
        mode=0o600,
        maximum=16 * 1024,
        allow_missing=True,
    )
    initial_frontend_receipt_identity = root_file_identity(receipt_value)
    initial_build_id_identity = None
    if receipt_value is None:
        frontend_revision = None
        frontend_proof_id = None
    else:
        receipt_raw, _receipt_metadata = receipt_value
        receipt = json_value(receipt_raw.decode("utf-8", errors="strict"))
        receipt_keys = {
            "schema_version",
            "revision",
            "pm2_pid",
            "pm2_uptime_ms",
            "next_build_id",
        }
        if not isinstance(receipt, dict) or set(receipt) != receipt_keys:
            fail("invalid frontend runtime receipt fields")
        frontend_revision = receipt.get("revision")
        if (
            receipt.get("schema_version") != 1
            or isinstance(receipt.get("schema_version"), bool)
            or not isinstance(frontend_revision, str)
            or SHA_RE.fullmatch(frontend_revision) is None
            or receipt.get("pm2_pid") != frontend_pid
            or receipt.get("pm2_uptime_ms") != frontend_uptime
        ):
            fail("frontend runtime receipt does not match PM2")
        next_dir_fd = open_root_directory(
            os.path.dirname(NEXT_BUILD_ID_PATH), mode=0o755
        )
        try:
            build_id_raw, _build_metadata = read_root_file(
                next_dir_fd,
                os.path.basename(NEXT_BUILD_ID_PATH),
                mode=0o644,
                maximum=256,
            )
            initial_build_id_identity = root_file_identity(
                (build_id_raw, _build_metadata)
            )
        finally:
            os.close(next_dir_fd)
        build_id = build_id_raw.decode("ascii", errors="strict").strip()
        if BUILD_ID_RE.fullmatch(build_id) is None or receipt.get("next_build_id") != build_id:
            fail("frontend runtime receipt does not match BUILD_ID")
        frontend_proof_id = hashlib.sha256(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if HEX64_RE.fullmatch(frontend_proof_id) is None:
            fail("invalid frontend proof identity")

    if EXPECTED_RELEASE_LOCK_TOKEN is None:
        assert_mac_release_quiescent(state_fd)
        initial_release_lock_identity = None
    else:
        initial_release_lock_identity = assert_expected_release_lock(state_fd)
    mac_receipt_value = read_root_file(
        state_fd,
        MAC_RECEIPT,
        mode=0o600,
        maximum=32 * 1024,
        allow_missing=True,
    )
    if mac_receipt_value is None:
        mac_revision = None
        mac_artifact_sha256 = None
        mac_receipt_id = None
    else:
        mac_receipt_raw, _mac_receipt_metadata = mac_receipt_value
        mac_receipt = json_value(mac_receipt_raw.decode("utf-8", errors="strict"))
        mac_receipt_keys = {
            "schema_version",
            "source_sha",
            "source_tree",
            "artifact_sha256",
            "artifact_size",
            "artifact_path",
            "artifact_url",
            "bundle_id",
            "version",
            "build",
            "team_id",
            "cdhash",
            "architectures",
            "min_os",
            "notary_submission_id",
            "notary_status",
            "stapled",
            "published_at",
        }
        if not isinstance(mac_receipt, dict) or set(mac_receipt) != mac_receipt_keys:
            fail("invalid Mac runtime receipt fields")
        mac_revision = mac_receipt.get("source_sha")
        source_tree = mac_receipt.get("source_tree")
        mac_artifact_sha256 = mac_receipt.get("artifact_sha256")
        artifact_size = mac_receipt.get("artifact_size")
        artifact_path = mac_receipt.get("artifact_path")
        artifact_url = mac_receipt.get("artifact_url")
        architectures = mac_receipt.get("architectures")
        if (
            mac_receipt.get("schema_version") != 1
            or isinstance(mac_receipt.get("schema_version"), bool)
            or not isinstance(mac_revision, str)
            or SHA_RE.fullmatch(mac_revision) is None
            or not isinstance(source_tree, str)
            or SHA_RE.fullmatch(source_tree) is None
            or not isinstance(mac_artifact_sha256, str)
            or HEX64_RE.fullmatch(mac_artifact_sha256) is None
            or isinstance(artifact_size, bool)
            or not isinstance(artifact_size, int)
            or artifact_size <= 0
            or artifact_size > MAC_MAX_ARTIFACT_BYTES
            or mac_receipt.get("bundle_id") != MAC_BUNDLE_ID
            or not isinstance(mac_receipt.get("version"), str)
            or VERSION_RE.fullmatch(mac_receipt["version"]) is None
            or not isinstance(mac_receipt.get("build"), str)
            or MAC_BUILD_RE.fullmatch(mac_receipt["build"]) is None
            or mac_receipt.get("team_id") != MAC_TEAM_ID
            or not isinstance(mac_receipt.get("cdhash"), str)
            or CDHASH_RE.fullmatch(mac_receipt["cdhash"]) is None
            or not isinstance(architectures, list)
            or not architectures
            or architectures != sorted(set(architectures))
            or any(
                not isinstance(item, str) or item not in ARCHITECTURES
                for item in architectures
            )
            or not isinstance(mac_receipt.get("min_os"), str)
            or VERSION_RE.fullmatch(mac_receipt["min_os"]) is None
            or not isinstance(mac_receipt.get("notary_submission_id"), str)
            or UUID_RE.fullmatch(mac_receipt["notary_submission_id"]) is None
            or mac_receipt.get("notary_status") != "Accepted"
            or mac_receipt.get("stapled") is not True
            or not valid_utc_timestamp(mac_receipt.get("published_at"))
        ):
            fail("invalid Mac runtime receipt values")
        expected_artifact_path = os.path.join(
            MAC_RELEASES_ROOT,
            mac_revision,
            f"{mac_artifact_sha256}.dmg",
        )
        expected_artifact_url = (
            "https://health.executor.life/mac/releases/"
            f"{mac_revision}/{mac_artifact_sha256}.dmg"
        )
        if artifact_path != expected_artifact_path or artifact_url != expected_artifact_url:
            fail("Mac runtime receipt artifact identity is invalid")
        proved_tree = run(
            ["/usr/bin/git", "rev-parse", f"{mac_revision}^{{tree}}"], cwd=REPO
        ).strip()
        if proved_tree != source_tree:
            fail("Mac runtime receipt source tree is invalid")

        mac_root_fd = open_root_directory(MAC_ASSET_ROOT, mode=0o755)
        try:
            current_raw, _current_metadata = read_root_file(
                mac_root_fd,
                os.path.basename(MAC_CURRENT_PATH),
                mode=0o644,
                maximum=16 * 1024,
            )
            current = json_value(current_raw.decode("utf-8", errors="strict"))
            public_fields = {
                "schema_version",
                "source_sha",
                "source_tree",
                "artifact_sha256",
                "artifact_size",
                "bundle_id",
                "version",
                "build",
                "architectures",
                "min_os",
                "artifact_url",
                "published_at",
            }
            expected_current = {
                field: mac_receipt[field] for field in public_fields
            }
            if not isinstance(current, dict) or set(current) != public_fields or current != expected_current:
                fail("Mac current manifest does not match runtime receipt")
        finally:
            os.close(mac_root_fd)

        if public_artifact_marker("/mac/current.json") != "mac-current-manifest":
            fail("public Mac current route marker is invalid")
        public_current = json_value(
            read_public_bytes(
                "/mac/current.json", maximum=16 * 1024
            ).decode("utf-8", errors="strict")
        )
        if public_current != expected_current:
            fail("public current manifest does not match runtime receipt")

        releases_fd = open_root_directory(MAC_RELEASES_ROOT, mode=0o755)
        try:
            source_fd = os.open(
                mac_revision,
                DIR_FLAGS,
                dir_fd=releases_fd,
            )
            try:
                source_metadata = os.fstat(source_fd)
                if (
                    not stat.S_ISDIR(source_metadata.st_mode)
                    or source_metadata.st_uid != 0
                    or source_metadata.st_gid != 0
                    or stat.S_IMODE(source_metadata.st_mode) != 0o755
                ):
                    fail("unsafe Mac release source directory")
                proved_artifact = hash_root_file(
                    source_fd,
                    f"{mac_artifact_sha256}.dmg",
                    mode=0o644,
                    expected_size=artifact_size,
                    maximum=MAC_MAX_ARTIFACT_BYTES,
                )
            finally:
                os.close(source_fd)
        finally:
            os.close(releases_fd)
        if proved_artifact != mac_artifact_sha256:
            fail("Mac artifact digest does not match runtime receipt")

        public_artifact_path = (
            f"/mac/releases/{mac_revision}/{mac_artifact_sha256}.dmg"
        )
        if public_artifact_marker(public_artifact_path) != "mac-immutable-dmg":
            fail("public immutable Mac route marker is invalid")
        if hash_public_artifact(
            public_artifact_path,
            expected_size=artifact_size,
            maximum=MAC_MAX_ARTIFACT_BYTES,
        ) != mac_artifact_sha256:
            fail("public immutable Mac artifact digest does not match runtime receipt")

        stable_root_fd = open_root_directory(
            os.path.dirname(MAC_STABLE_PATH), mode=0o755
        )
        try:
            proved_stable = hash_root_file(
                stable_root_fd,
                os.path.basename(MAC_STABLE_PATH),
                mode=0o644,
                expected_size=artifact_size,
                maximum=MAC_MAX_ARTIFACT_BYTES,
            )
        finally:
            os.close(stable_root_fd)
        if proved_stable != mac_artifact_sha256:
            fail("Mac stable artifact digest does not match runtime receipt")
        if public_artifact_marker("/xiaoba-mac.dmg") != "xiaoba-mac-dmg":
            fail("public stable Mac route marker is invalid")
        if hash_public_artifact(
            "/xiaoba-mac.dmg",
            expected_size=artifact_size,
            maximum=MAC_MAX_ARTIFACT_BYTES,
        ) != mac_artifact_sha256:
            fail("public stable Mac artifact digest does not match runtime receipt")
        mac_receipt_id = hashlib.sha256(
            json.dumps(mac_receipt, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    # Public Mac verification can be slow. Re-prove both live health endpoints
    # immediately before the final identity/quiescence sample.
    assert_local_health()
    confirmed_checkout_identity = checkout_identity()
    confirmed_marker_value = read_root_file(
        state_fd,
        TERMINAL_MARKER,
        mode=0o600,
        maximum=64 * 1024,
    )
    confirmed_terminal_identity = root_file_identity(confirmed_marker_value)
    confirmed_backend_process_identity = backend_process_identity(
        confirmed_marker_value[1]
    )
    confirmed_frontend_process_identity = frontend_process_identity()
    confirmed_frontend_receipt = read_root_file(
        state_fd,
        FRONTEND_RECEIPT,
        mode=0o600,
        maximum=16 * 1024,
        allow_missing=True,
    )
    confirmed_frontend_receipt_identity = root_file_identity(
        confirmed_frontend_receipt
    )
    confirmed_build_id_identity = None
    if confirmed_frontend_receipt is not None:
        confirmed_next_dir_fd = open_root_directory(
            os.path.dirname(NEXT_BUILD_ID_PATH), mode=0o755
        )
        try:
            confirmed_build_id = read_root_file(
                confirmed_next_dir_fd,
                os.path.basename(NEXT_BUILD_ID_PATH),
                mode=0o644,
                maximum=256,
            )
            confirmed_build_id_identity = root_file_identity(confirmed_build_id)
        finally:
            os.close(confirmed_next_dir_fd)
    if (
        confirmed_checkout_identity != initial_checkout_identity
        or confirmed_terminal_identity != initial_terminal_identity
        or confirmed_backend_process_identity != initial_backend_process_identity
        or confirmed_frontend_process_identity != initial_frontend_process_identity
        or confirmed_frontend_receipt_identity
        != initial_frontend_receipt_identity
        or confirmed_build_id_identity != initial_build_id_identity
    ):
        fail("production server identity changed during proof")

    confirmed_mac_receipt = read_root_file(
        state_fd,
        MAC_RECEIPT,
        mode=0o600,
        maximum=32 * 1024,
        allow_missing=True,
    )
    if (confirmed_mac_receipt is None) != (mac_receipt_value is None):
        fail("Mac runtime receipt changed during production proof")
    if (
        confirmed_mac_receipt is not None
        and mac_receipt_value is not None
        and (
            confirmed_mac_receipt[0] != mac_receipt_value[0]
            or (
                confirmed_mac_receipt[1].st_dev,
                confirmed_mac_receipt[1].st_ino,
                confirmed_mac_receipt[1].st_size,
                confirmed_mac_receipt[1].st_mtime_ns,
            )
            != (
                mac_receipt_value[1].st_dev,
                mac_receipt_value[1].st_ino,
                mac_receipt_value[1].st_size,
                mac_receipt_value[1].st_mtime_ns,
            )
        )
    ):
        fail("Mac runtime receipt changed during production proof")
    if EXPECTED_RELEASE_LOCK_TOKEN is None:
        assert_mac_release_quiescent(state_fd)
    else:
        confirmed_release_lock_identity = assert_expected_release_lock(state_fd)
        if confirmed_release_lock_identity != initial_release_lock_identity:
            fail("release lock ownership changed during production proof")
finally:
    os.close(state_fd)

print(
    json.dumps(
        {
            "schema_version": 3,
            "checkout_revision": revision,
            "repository_clean": repository_clean,
            "backend_revision": revision,
            "backend_proof_id": backend_proof_id,
            "backend_service": "active",
            "backend_health": "ok",
            "frontend_pm2": "online",
            "frontend_health": "ok",
            "frontend_revision": frontend_revision,
            "frontend_proof_id": frontend_proof_id,
            "mac_revision": mac_revision,
            "mac_artifact_sha256": mac_artifact_sha256,
            "mac_receipt_id": mac_receipt_id,
        },
        separators=(",", ":"),
    )
)
PY
"""


class ProductionProbeError(RuntimeError):
    """Production state could not be proven unambiguously."""


@dataclass(frozen=True)
class ProductionSurfaces:
    backend_sha: str
    backend_proof_id: str
    frontend_sha: str | None
    frontend_proof_id: str | None
    mac_sha: str | None
    mac_artifact_sha256: str | None
    mac_receipt_id: str | None
    mobile_ota_sha: str
    mobile_group_id: str
    mobile_update_id: str
    mobile_runtime: str
    mobile_channel_id: str = ""
    mobile_channel_updated_at: str = ""
    mobile_branch_mapping: str = ""
    mobile_branch_id: str = ""
    mobile_identity_digest: str = ""
    mobile_runtime_vector_digest: str = ""

    @property
    def server_sha(self) -> str:
        """Compatibility alias for callers that have not split server surfaces."""

        return self.backend_sha


@dataclass(frozen=True)
class MobileChannelIdentity:
    channel_id: str
    channel_updated_at: str
    branch_mapping: str
    branch_id: str
    branch_name: str


@dataclass(frozen=True)
class MobileRuntimeUpdate:
    group_id: str
    update_id: str
    runtime: str
    commit_sha: str
    created_at: str

    @property
    def canonical_payload(self) -> dict[str, str]:
        return {
            "group_id": self.group_id,
            "update_id": self.update_id,
            "runtime": self.runtime,
            "commit_sha": self.commit_sha,
            "created_at": self.created_at,
        }

@dataclass(frozen=True)
class MobileProductionIdentity:
    channel_id: str
    channel_updated_at: str
    branch_mapping: str
    branch_id: str
    branch_name: str
    group_id: str
    update_id: str
    runtime: str
    commit_sha: str
    runtime_vector: tuple[MobileRuntimeUpdate, ...]

    @property
    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "channel_id": self.channel_id,
            "channel_updated_at": self.channel_updated_at,
            "branch_mapping": self.branch_mapping,
            "branch_id": self.branch_id,
            "branch_name": self.branch_name,
            "group_id": self.group_id,
            "update_id": self.update_id,
            "runtime": self.runtime,
            "commit_sha": self.commit_sha,
            "runtime_vector": [
                update.canonical_payload for update in self.runtime_vector
            ],
        }

    @property
    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("ascii")).hexdigest()

    @property
    def runtime_vector_digest(self) -> str:
        canonical = json.dumps(
            [update.canonical_payload for update in self.runtime_vector],
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("ascii")).hexdigest()


Runner = Callable[..., subprocess.CompletedProcess[Any]]


def _locked_eas_binary(runner: Runner) -> Path:
    global _PREPARED_EAS_BINARY, _PREPARED_EAS_WORKSPACE
    if runner is not subprocess.run:
        # Unit runners execute no local program; retain a deterministic command
        # identity so command-contract tests do not require an online install.
        return _EAS_BINARY
    if _PREPARED_EAS_BINARY is not None:
        return _PREPARED_EAS_BINARY
    spec = importlib.util.spec_from_file_location(
        "reva_locked_eas_cli", _LOCKED_EAS_HELPER
    )
    if spec is None or spec.loader is None:
        raise ProductionProbeError("cannot load the locked EAS CLI preparer")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    try:
        workspace, executable = helper.prepare_locked_eas_cli(ROOT)
    except Exception as error:
        raise ProductionProbeError(
            "cannot prepare the integrity-locked EAS CLI"
        ) from error
    _PREPARED_EAS_WORKSPACE = workspace
    _PREPARED_EAS_BINARY = executable

    def cleanup() -> None:
        if _PREPARED_EAS_WORKSPACE is None:
            return
        try:
            helper.cleanup_locked_eas_cli(_PREPARED_EAS_WORKSPACE)
        except Exception as error:
            print(
                f"warning: failed to remove locked EAS workspace: {error}",
                file=sys.stderr,
            )

    atexit.register(cleanup)
    return executable


def _probe_environment(source: Mapping[str, str]) -> dict[str, str]:
    """Build a small environment without command/runtime injection hooks."""

    environment = {
        "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C",
        "LC_ALL": "C",
        "CI": "1",
        "NO_COLOR": "1",
        "NPM_CONFIG_USERCONFIG": "/dev/null",
        "NPM_CONFIG_REGISTRY": "https://registry.npmjs.org/",
        "NPM_CONFIG_AUDIT": "false",
        "NPM_CONFIG_FUND": "false",
        "NPM_CONFIG_UPDATE_NOTIFIER": "false",
    }
    for name in ("HOME", "USER", "LOGNAME", "SSH_AUTH_SOCK", "TMPDIR"):
        value = source.get(name)
        if value:
            environment[name] = value
    expo_token = source.get("EXPO_TOKEN")
    if expo_token:
        environment["EXPO_TOKEN"] = expo_token
    return environment


def _pinned_known_hosts_command() -> str:
    """Return a static ssh KnownHostsCommand with no path or input expansion."""

    try:
        host_key = _PRODUCTION_KNOWN_HOST.decode("ascii", errors="strict").strip()
    except UnicodeError as error:
        raise ProductionProbeError("the pinned production host key is invalid") from error
    if not re.fullmatch(
        r"[0-9.]+ ssh-ed25519 [A-Za-z0-9+/=]+", host_key
    ):
        raise ProductionProbeError("the pinned production host key is invalid")
    return "/usr/bin/printf " + host_key.replace(" ", r"\ ") + r"\n"


def _decode_stream(value: object, *, label: str, stream: str) -> tuple[str, int]:
    if value is None:
        return "", 0
    try:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="strict"), len(value)
        if isinstance(value, str):
            encoded = value.encode("utf-8", errors="strict")
            return value, len(encoded)
    except UnicodeError as error:
        raise ProductionProbeError(f"{label} returned non-UTF-8 {stream}") from error
    raise ProductionProbeError(f"{label} returned an invalid {stream} stream")


def _checked_output(
    completed: subprocess.CompletedProcess[Any], *, label: str
) -> str:
    """Accept only successful, UTF-8 and size-bounded subprocess output."""

    stdout, stdout_size = _decode_stream(
        completed.stdout, label=label, stream="stdout"
    )
    stderr, stderr_size = _decode_stream(
        completed.stderr, label=label, stream="stderr"
    )
    if stdout_size + stderr_size > MAX_PROBE_BYTES:
        raise ProductionProbeError(f"{label} output exceeds the safety limit")
    if completed.returncode != 0:
        detail = " ".join(stderr.split())[:512]
        suffix = f": {detail}" if detail else ""
        raise ProductionProbeError(
            f"{label} failed with exit code {completed.returncode}{suffix}"
        )
    return stdout


def _json_object(raw: str, *, label: str) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result

    try:
        payload = json.loads(
            raw,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"invalid JSON constant: {value}")
            ),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ProductionProbeError(f"{label} returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise ProductionProbeError(f"{label} must return one JSON object")
    return payload


def _parse_server_evidence(
    raw: str,
) -> tuple[
    str,
    str,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
]:
    payload = _json_object(raw, label="production server probe")
    expected_keys = {
        "schema_version",
        "checkout_revision",
        "repository_clean",
        "backend_revision",
        "backend_proof_id",
        "backend_service",
        "backend_health",
        "frontend_pm2",
        "frontend_health",
        "frontend_revision",
        "frontend_proof_id",
        "mac_revision",
        "mac_artifact_sha256",
        "mac_receipt_id",
    }
    checkout_revision = payload.get("checkout_revision")
    backend_revision = payload.get("backend_revision")
    backend_proof_id = payload.get("backend_proof_id")
    if (
        set(payload) != expected_keys
        or payload.get("schema_version") != 3
        or isinstance(payload.get("schema_version"), bool)
        or not isinstance(checkout_revision, str)
        or _SHA_RE.fullmatch(checkout_revision) is None
        or not isinstance(backend_revision, str)
        or _SHA_RE.fullmatch(backend_revision) is None
    ):
        raise ProductionProbeError(
            "production server evidence has missing or unexpected fields"
        )
    if payload["repository_clean"] is not True:
        raise ProductionProbeError(
            "production server evidence must prove the tracked and untracked clean state"
        )
    if backend_revision != checkout_revision:
        raise ProductionProbeError(
            "production backend runtime revision does not match checkout"
        )
    if (
        not isinstance(backend_proof_id, str)
        or re.fullmatch(r"[0-9a-f]{64}", backend_proof_id) is None
    ):
        raise ProductionProbeError("production backend runtime proof is invalid")
    if payload["backend_service"] != "active":
        raise ProductionProbeError("production backend services are not active")
    if payload["backend_health"] != "ok":
        raise ProductionProbeError("production backend health is not ok")
    if payload["frontend_pm2"] != "online":
        raise ProductionProbeError("production frontend process is not online")
    if payload["frontend_health"] != "ok":
        raise ProductionProbeError("production frontend health is not ok")
    frontend_revision = payload.get("frontend_revision")
    frontend_proof_id = payload.get("frontend_proof_id")
    if frontend_revision is None and frontend_proof_id is None:
        frontend_result: tuple[str | None, str | None] = (None, None)
    elif (
        not isinstance(frontend_revision, str)
        or _SHA_RE.fullmatch(frontend_revision) is None
        or not isinstance(frontend_proof_id, str)
        or re.fullmatch(r"[0-9a-f]{64}", frontend_proof_id) is None
    ):
        raise ProductionProbeError("production frontend runtime proof is invalid")
    else:
        frontend_result = (frontend_revision, frontend_proof_id)

    mac_revision = payload.get("mac_revision")
    mac_artifact_sha256 = payload.get("mac_artifact_sha256")
    mac_receipt_id = payload.get("mac_receipt_id")
    if (
        mac_revision is None
        and mac_artifact_sha256 is None
        and mac_receipt_id is None
    ):
        mac_result: tuple[str | None, str | None, str | None] = (None, None, None)
    elif (
        not isinstance(mac_revision, str)
        or _SHA_RE.fullmatch(mac_revision) is None
        or not isinstance(mac_artifact_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", mac_artifact_sha256) is None
        or not isinstance(mac_receipt_id, str)
        or re.fullmatch(r"[0-9a-f]{64}", mac_receipt_id) is None
    ):
        raise ProductionProbeError("production Mac runtime proof is invalid")
    else:
        mac_result = (mac_revision, mac_artifact_sha256, mac_receipt_id)
    return (
        backend_revision,
        backend_proof_id,
        *frontend_result,
        *mac_result,
    )


def _expected_mobile_runtime() -> str:
    app_json = Path(__file__).resolve().parents[1] / "mobile/app.json"
    try:
        raw = app_json.read_bytes()
        if not raw or len(raw) > MAX_PROBE_BYTES:
            raise ValueError("invalid app config size")
        payload = json.loads(raw.decode("utf-8", errors="strict"))
        expo = payload.get("expo")
        if not isinstance(expo, dict):
            raise ValueError("missing expo config")
        version = expo.get("version")
        runtime = expo.get("runtimeVersion")
        if isinstance(runtime, str):
            expected = runtime
        elif runtime == {"policy": "appVersion"}:
            expected = version
        else:
            raise ValueError("unsupported runtime policy")
        if not isinstance(expected, str) or not expected or len(expected) > 64:
            raise ValueError("invalid runtime")
        return expected
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ProductionProbeError(
            "cannot determine the expected mobile production runtime"
        ) from error


def _required_dict(value: object, *, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProductionProbeError(message)
    return value


def _canonical_branch_mapping(value: object, *, branch_id: str) -> str:
    if isinstance(value, str):
        try:
            mapping = json.loads(
                value,
                object_pairs_hook=lambda pairs: _unique_json_pairs(
                    pairs, label="EAS branch mapping"
                ),
                parse_constant=lambda constant: (_ for _ in ()).throw(
                    ValueError(f"invalid JSON constant: {constant}")
                ),
            )
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ProductionProbeError(
                "EAS production branch mapping is invalid"
            ) from error
    else:
        mapping = value
    if not isinstance(mapping, dict):
        raise ProductionProbeError("EAS production branch mapping is invalid")

    referenced_branch_ids: list[str] = []

    def validate(node: object) -> None:
        if node is None or isinstance(node, (str, bool, int)):
            return
        if isinstance(node, float):
            raise ProductionProbeError(
                "EAS production branch mapping contains an unsafe number"
            )
        if isinstance(node, list):
            for item in node:
                validate(item)
            return
        if isinstance(node, dict):
            for key, item in node.items():
                if not isinstance(key, str):
                    raise ProductionProbeError(
                        "EAS production branch mapping is invalid"
                    )
                if key == "branchId":
                    if not isinstance(item, str):
                        raise ProductionProbeError(
                            "EAS production branch mapping has an invalid branch"
                        )
                    referenced_branch_ids.append(item)
                validate(item)
            return
        raise ProductionProbeError("EAS production branch mapping is invalid")

    validate(mapping)
    if referenced_branch_ids != [branch_id]:
        raise ProductionProbeError(
            "EAS production branch mapping does not select the active branch"
        )
    return json.dumps(
        mapping,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _unique_json_pairs(
    pairs: list[tuple[str, Any]], *, label: str
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key in {label}: {key}")
        result[key] = value
    return result


def _parse_mobile_channel_evidence(raw: str) -> MobileChannelIdentity:
    payload = _json_object(raw, label="EAS production channel probe")
    page = _required_dict(
        payload.get("currentPage"), message="EAS production channel is missing"
    )
    if page.get("name") != _PRODUCTION_CHANNEL:
        raise ProductionProbeError("EAS channel is not production")
    if page.get("isPaused") is not False:
        raise ProductionProbeError("EAS production channel is paused or ambiguous")
    channel_id = page.get("id")
    if not isinstance(channel_id, str) or _UUID_RE.fullmatch(channel_id) is None:
        raise ProductionProbeError("EAS production channel identity is invalid")
    channel_updated_at = page.get("updatedAt")
    if (
        not isinstance(channel_updated_at, str)
        or re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:"
            r"[0-9]{2}(?:\.[0-9]{1,9})?Z",
            channel_updated_at,
        )
        is None
    ):
        raise ProductionProbeError(
            "EAS production channel updated identity is invalid"
        )

    branches = page.get("updateBranches")
    if not isinstance(branches, list) or len(branches) != 1:
        raise ProductionProbeError(
            "EAS production channel must have a single active branch"
        )
    branch = _required_dict(branches[0], message="EAS production branch is invalid")
    if branch.get("name") != _PRODUCTION_CHANNEL:
        raise ProductionProbeError("EAS active branch is not production")
    branch_id = branch.get("id")
    if not isinstance(branch_id, str) or _UUID_RE.fullmatch(branch_id) is None:
        raise ProductionProbeError("EAS production branch identity is invalid")
    branch_mapping = _canonical_branch_mapping(
        page.get("branchMapping"), branch_id=branch_id
    )

    # channel:view intentionally exposes only the branch's newest *overall*
    # group. It is authoritative for channel→branch mapping, never for a
    # particular runtime/platform's newest compatible update.
    return MobileChannelIdentity(
        channel_id=channel_id,
        channel_updated_at=channel_updated_at,
        branch_mapping=branch_mapping,
        branch_id=branch_id,
        branch_name=_PRODUCTION_CHANNEL,
    )


def _runtime_update(raw: object) -> MobileRuntimeUpdate:
    update = _required_dict(raw, message="EAS production update is invalid")

    update_id = update.get("id")
    group_id = update.get("group")
    commit_sha = update.get("gitCommitHash")
    runtime = update.get("runtimeVersion")
    branch = update.get("branch")
    branch_name = branch.get("name") if isinstance(branch, dict) else branch
    if not isinstance(update_id, str) or _UUID_RE.fullmatch(update_id) is None:
        raise ProductionProbeError("EAS production update identity is invalid")
    if not isinstance(group_id, str) or _UUID_RE.fullmatch(group_id) is None:
        raise ProductionProbeError("EAS production group identity is invalid")
    if not isinstance(commit_sha, str) or _SHA_RE.fullmatch(commit_sha) is None:
        raise ProductionProbeError("EAS production commit identity is invalid")
    if update.get("platform") != _PRODUCTION_PLATFORM:
        raise ProductionProbeError("EAS production group is not an iOS update")
    if branch_name != _PRODUCTION_CHANNEL:
        raise ProductionProbeError("EAS production update is on another branch")
    # update:view omits these fields in the pinned EAS renderer, but
    # channel:view currently includes them. Whenever evidence exposes either
    # field, reject contradictory values instead of silently discarding them.
    if (
        "isGitWorkingTreeDirty" in update
        and update.get("isGitWorkingTreeDirty") is not False
    ):
        raise ProductionProbeError("EAS production update is dirty")
    if "environment" in update and update.get("environment") != _PRODUCTION_CHANNEL:
        raise ProductionProbeError("EAS production update is not production")
    if (
        not isinstance(runtime, str)
        or not runtime
        or len(runtime) > 64
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}", runtime) is None
    ):
        raise ProductionProbeError("EAS production runtime identity is invalid")
    # update:view --json intentionally emits a reduced stable projection in
    # v21.8.0; createdAt/environment/dirty are absent from that JSON renderer.
    # Exact source cleanliness is established by the controlled publisher,
    # while production OTA remains disabled until ASC cohort authority exists.
    return MobileRuntimeUpdate(
        group_id=group_id,
        update_id=update_id,
        runtime=runtime,
        commit_sha=commit_sha,
        created_at="",
    )


def _parse_mobile_group_page(raw: str) -> list[tuple[str, str]]:
    try:
        payload = json.loads(
            raw,
            object_pairs_hook=lambda pairs: _unique_json_pairs(
                pairs, label="EAS runtime update list"
            ),
            parse_constant=lambda constant: (_ for _ in ()).throw(
                ValueError(f"invalid JSON constant: {constant}")
            ),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ProductionProbeError(
            "EAS runtime update list returned invalid JSON"
        ) from error
    if isinstance(payload, dict):
        items = payload.get("currentPage")
    else:
        items = payload
    if not isinstance(items, list):
        raise ProductionProbeError("EAS runtime update page is invalid")
    result: list[tuple[str, str]] = []
    for item in items:
        descriptor = _required_dict(
            item, message="EAS runtime group descriptor is invalid"
        )
        group = descriptor.get("group")
        runtime = descriptor.get("runtimeVersion")
        platforms = descriptor.get("platforms")
        if (
            descriptor.get("branch") != _PRODUCTION_CHANNEL
            or not isinstance(group, str)
            or _UUID_RE.fullmatch(group) is None
            or not isinstance(runtime, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}", runtime)
            is None
            or not isinstance(platforms, str)
            or _PRODUCTION_PLATFORM not in {
                value.strip().lower() for value in platforms.split(",")
            }
        ):
            raise ProductionProbeError(
                "EAS runtime group descriptor identity is invalid"
            )
        result.append((runtime, group))
    return result


def _mobile_runtime_vector(parsed: list[MobileRuntimeUpdate]) -> tuple[MobileRuntimeUpdate, ...]:
    if not parsed:
        raise ProductionProbeError("EAS runtime update vector is empty or invalid")
    by_runtime: dict[str, MobileRuntimeUpdate] = {}
    for update in parsed:
        if update.runtime in by_runtime:
            raise ProductionProbeError("EAS runtime vector contains duplicate runtimes")
        by_runtime[update.runtime] = update
    result = tuple(by_runtime[runtime] for runtime in sorted(by_runtime))
    if len({update.update_id for update in result}) != len(result):
        raise ProductionProbeError("EAS runtime vector reuses one update identity")
    return result


def _parse_mobile_runtime_vector(raw: str) -> tuple[MobileRuntimeUpdate, ...]:
    # Explicit JSON evidence mode accepts only full update:view rows.
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ProductionProbeError("EAS runtime vector is invalid JSON") from error
    items = payload.get("currentPage") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ProductionProbeError("EAS runtime vector is invalid")
    return _mobile_runtime_vector([_runtime_update(item) for item in items])


def _compose_mobile_identity(
    channel: MobileChannelIdentity,
    runtime_vector: tuple[MobileRuntimeUpdate, ...],
    *,
    expected_runtime: str | None,
) -> MobileProductionIdentity:
    if expected_runtime is None:
        selected = max(
            runtime_vector,
            key=lambda update: (update.created_at, update.runtime, update.update_id),
        )
    else:
        selected = next(
            (update for update in runtime_vector if update.runtime == expected_runtime),
            None,
        )
        if selected is None:
            raise ProductionProbeError(
                "EAS production runtime does not match the source runtime"
            )
    return MobileProductionIdentity(
        channel_id=channel.channel_id,
        channel_updated_at=channel.channel_updated_at,
        branch_mapping=channel.branch_mapping,
        branch_id=channel.branch_id,
        branch_name=channel.branch_name,
        group_id=selected.group_id,
        update_id=selected.update_id,
        runtime=selected.runtime,
        commit_sha=selected.commit_sha,
        runtime_vector=runtime_vector,
    )


def _parse_mobile_evidence(
    channel_raw: str,
    *,
    expected_runtime: str | None,
    runtime_raw: str | None = None,
) -> MobileProductionIdentity:
    if runtime_raw is None:
        # Observability-only fallback. channel:view exposes the branch's newest
        # overall group, not latest-per-runtime. Production OTA/rollback are
        # hard-disabled, so no writer may use this fallback as authorization.
        payload = _json_object(channel_raw, label="EAS production channel probe")
        page = _required_dict(
            payload.get("currentPage"), message="EAS production channel is missing"
        )
        branches = page.get("updateBranches")
        if not isinstance(branches, list) or len(branches) != 1:
            raise ProductionProbeError(
                "EAS production channel must have a single active branch"
            )
        branch = _required_dict(
            branches[0], message="EAS production branch is invalid"
        )
        groups = branch.get("updateGroups")
        if not isinstance(groups, list) or len(groups) != 1:
            raise ProductionProbeError(
                "EAS production branch must have a single active group"
            )
        updates = groups[0]
        if not isinstance(updates, list) or len(updates) != 1:
            raise ProductionProbeError(
                "EAS production group must have one unambiguous iOS update"
            )
        update = _required_dict(
            updates[0], message="EAS production update is invalid"
        )
        projected = dict(update)
        projected["branch"] = {"name": _PRODUCTION_CHANNEL}
        selected = _runtime_update(projected)
        return _compose_mobile_identity(
            _parse_mobile_channel_evidence(channel_raw),
            (selected,),
            expected_runtime=expected_runtime,
        )
    return _compose_mobile_identity(
        _parse_mobile_channel_evidence(channel_raw),
        _parse_mobile_runtime_vector(runtime_raw),
        expected_runtime=expected_runtime,
    )


def mobile_identity_from_channel_and_views(
    channel_raw: str,
    view_rows: list[object],
    *,
    expected_runtime: str | None,
) -> MobileProductionIdentity:
    """Compose observability identity from channel mapping + latest view rows."""

    updates = [_runtime_update(row) for row in view_rows]
    return _compose_mobile_identity(
        _parse_mobile_channel_evidence(channel_raw),
        _mobile_runtime_vector(updates),
        expected_runtime=expected_runtime,
    )


def _run_probe(
    runner: Runner,
    command: list[str],
    *,
    label: str,
    **kwargs: object,
) -> str:
    try:
        if runner is subprocess.run:
            completed = _run_bounded_probe_process(command, label=label, **kwargs)
        else:
            completed = runner(command, **kwargs)
    except subprocess.TimeoutExpired as error:
        raise ProductionProbeError(
            f"{label} timed out after {PROBE_TIMEOUT_SECONDS} seconds"
        ) from error
    except OSError as error:
        raise ProductionProbeError(f"{label} could not be started") from error
    return _checked_output(completed, label=label)


def _run_bounded_probe_process(
    command: list[str], *, label: str, **kwargs: object
) -> subprocess.CompletedProcess[bytes]:
    timeout = kwargs.pop("timeout", PROBE_TIMEOUT_SECONDS)
    kwargs.pop("check", None)
    kwargs.pop("stdout", None)
    kwargs.pop("stderr", None)
    kwargs.pop("text", None)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ProductionProbeError(f"{label} has an invalid timeout")
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            **kwargs,
        )
    except OSError as error:
        raise ProductionProbeError(f"{label} could not be started") from error
    selector = selectors.DefaultSelector()
    buffers = {process.stdout: bytearray(), process.stderr: bytearray()}
    total = 0
    deadline = time.monotonic() + timeout

    def terminate() -> None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            try:
                process.kill()
            except OSError:
                pass
        process.wait()

    try:
        for stream in buffers:
            assert stream is not None
            selector.register(stream, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                terminate()
                raise ProductionProbeError(
                    f"{label} timed out after {PROBE_TIMEOUT_SECONDS} seconds"
                )
            for key, _mask in selector.select(min(remaining, 0.25)):
                chunk = os.read(
                    key.fd,
                    min(16 * 1024, MAX_PROBE_BYTES + 1 - total),
                )
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                buffers[key.fileobj].extend(chunk)
                total += len(chunk)
                if total > MAX_PROBE_BYTES:
                    terminate()
                    raise ProductionProbeError(
                        f"{label} output exceeds the safety limit"
                    )
        returncode = process.wait(timeout=max(0.01, deadline - time.monotonic()))
    except subprocess.TimeoutExpired as error:
        terminate()
        raise ProductionProbeError(
            f"{label} timed out after {PROBE_TIMEOUT_SECONDS} seconds"
        ) from error
    finally:
        selector.close()
    return subprocess.CompletedProcess(
        command,
        returncode,
        stdout=bytes(buffers[process.stdout]),
        stderr=bytes(buffers[process.stderr]),
    )


def _remote_probe_command(expected_lock_token: str | None) -> str:
    marker = "__REVA_EXPECTED_RELEASE_LOCK_TOKEN__"
    if _REMOTE_PROBE.count(marker) != 1:
        raise ProductionProbeError("production server probe token marker is invalid")
    if expected_lock_token is None:
        value = "none"
    elif re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", expected_lock_token) is None:
        raise ProductionProbeError("invalid expected release lease token")
    else:
        value = expected_lock_token
    return _REMOTE_PROBE.replace(marker, value)


def _probe_server_surfaces(
    repo_root: Path,
    *,
    expected_lock_token: str | None,
    runner: Runner,
) -> tuple[str, str, str | None, str | None, str | None, str | None, str | None]:
    environment = _probe_environment(os.environ)
    ssh_command = [
        _SSH_BINARY,
        "-F",
        "/dev/null",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "GlobalKnownHostsFile=/dev/null",
        "-o",
        f"KnownHostsCommand={_pinned_known_hosts_command()}",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        "ConnectTimeout=15",
        _PRODUCTION_SERVER,
        _remote_probe_command(expected_lock_token),
    ]
    server_raw = _run_probe(
        runner,
        ssh_command,
        label="production server probe",
        cwd=Path(repo_root),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=PROBE_TIMEOUT_SECONDS,
        check=False,
    )
    return _parse_server_evidence(server_raw)


def probe_server_surfaces_under_release_lock(
    repo_root: Path,
    *,
    expected_lock_token: str,
    runner: Runner = subprocess.run,
) -> tuple[str, str, str | None, str | None, str | None, str | None, str | None]:
    """Prove exact server generations while the caller owns the shared lease."""

    return _probe_server_surfaces(
        repo_root,
        expected_lock_token=expected_lock_token,
        runner=runner,
    )


def probe_server_surfaces(
    repo_root: Path,
    *,
    runner: Runner = subprocess.run,
) -> tuple[str, str, str | None, str | None, str | None, str | None, str | None]:
    """Prove exact server generations while no shared release lease is held."""

    return _probe_server_surfaces(
        repo_root,
        expected_lock_token=None,
        runner=runner,
    )


def _probe_production_surfaces(
    repo_root: Path,
    *,
    mobile_dir: Path,
    expected_lock_token: str | None,
    runner: Runner = subprocess.run,
) -> ProductionSurfaces:
    """Read the active server and iOS identities under one lock expectation."""

    (
        backend_sha,
        backend_proof_id,
        frontend_sha,
        frontend_proof_id,
        mac_sha,
        mac_artifact_sha256,
        mac_receipt_id,
    ) = _probe_server_surfaces(
        repo_root,
        expected_lock_token=expected_lock_token,
        runner=runner,
    )

    mobile_identity = probe_mobile_production_identity(
        mobile_dir=mobile_dir,
        runner=runner,
    )
    return ProductionSurfaces(
        backend_sha=backend_sha,
        backend_proof_id=backend_proof_id,
        frontend_sha=frontend_sha,
        frontend_proof_id=frontend_proof_id,
        mac_sha=mac_sha,
        mac_artifact_sha256=mac_artifact_sha256,
        mac_receipt_id=mac_receipt_id,
        mobile_ota_sha=mobile_identity.commit_sha,
        mobile_group_id=mobile_identity.group_id,
        mobile_update_id=mobile_identity.update_id,
        mobile_runtime=mobile_identity.runtime,
        mobile_channel_id=mobile_identity.channel_id,
        mobile_channel_updated_at=mobile_identity.channel_updated_at,
        mobile_branch_mapping=mobile_identity.branch_mapping,
        mobile_branch_id=mobile_identity.branch_id,
        mobile_identity_digest=mobile_identity.digest,
        mobile_runtime_vector_digest=mobile_identity.runtime_vector_digest,
    )


def probe_mobile_production_identity(
    *,
    mobile_dir: Path,
    expected_runtime: str | None = None,
    runner: Runner = subprocess.run,
) -> MobileProductionIdentity:
    """Return one canonical, ABA-sensitive identity for the production channel."""

    environment = _probe_environment(os.environ)
    eas_command = [
        str(_locked_eas_binary(runner)),
        "channel:view",
        _PRODUCTION_CHANNEL,
        "--json",
        "--non-interactive",
    ]
    channel_raw = _run_probe(
        runner,
        eas_command,
        label="EAS production channel probe",
        cwd=Path(mobile_dir),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=PROBE_TIMEOUT_SECONDS,
        check=False,
    )
    return _parse_mobile_evidence(
        channel_raw,
        expected_runtime=expected_runtime,
    )


def probe_production_surfaces(
    repo_root: Path,
    *,
    mobile_dir: Path,
    runner: Runner = subprocess.run,
) -> ProductionSurfaces:
    """Read active server/iOS identities while no release lease is held."""

    return _probe_production_surfaces(
        repo_root,
        mobile_dir=mobile_dir,
        expected_lock_token=None,
        runner=runner,
    )


def probe_production_surfaces_under_release_lock(
    repo_root: Path,
    *,
    mobile_dir: Path,
    expected_lock_token: str,
    runner: Runner = subprocess.run,
) -> ProductionSurfaces:
    """Read active server/iOS identities while holding the exact retained lease."""

    return _probe_production_surfaces(
        repo_root,
        mobile_dir=mobile_dir,
        expected_lock_token=expected_lock_token,
        runner=runner,
    )


__all__ = [
    "MAX_PROBE_BYTES",
    "MobileProductionIdentity",
    "PROBE_TIMEOUT_SECONDS",
    "ProductionProbeError",
    "ProductionSurfaces",
    "probe_production_surfaces",
    "probe_production_surfaces_under_release_lock",
    "probe_mobile_production_identity",
    "probe_server_surfaces",
    "probe_server_surfaces_under_release_lock",
]


def _main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] in _NETWORK_CLI_MODES:
        print(
            "production network probes are frozen; use the external trusted Gate",
            file=sys.stderr,
        )
        return 78
    if len(argv) not in {2, 3, 4, 5} or argv[1] not in {
        "server",
        "server-under-lock",
        "mobile",
        "mobile-evidence",
    }:
        print(
            "usage: release_production_state.py "
            "{server|server-under-lock TOKEN|mobile [EXPECTED_RUNTIME]|"
            "mobile-evidence EXPECTED_RUNTIME CHANNEL_JSON RUNTIME_JSON}",
            file=sys.stderr,
        )
        return 2
    if argv[1] == "server":
        if len(argv) != 2:
            return 2
        identity = probe_server_surfaces(ROOT)
    elif argv[1] == "server-under-lock":
        if len(argv) != 3:
            return 2
        identity = probe_server_surfaces_under_release_lock(
            ROOT,
            expected_lock_token=argv[2],
        )
    elif argv[1] == "mobile":
        expected_runtime = argv[2] if len(argv) == 3 else None
        mobile_identity = probe_mobile_production_identity(
            mobile_dir=ROOT / "mobile",
            expected_runtime=expected_runtime,
        )
        print(mobile_identity.canonical_json)
        return 0
    else:
        if len(argv) != 5:
            return 2
        evidence_path = Path(argv[3])
        runtime_path = Path(argv[4])
        try:
            raw = evidence_path.read_bytes()
            runtime_raw = runtime_path.read_bytes()
            if (
                not raw
                or len(raw) > MAX_PROBE_BYTES
                or not runtime_raw
                or len(runtime_raw) > MAX_PROBE_BYTES
            ):
                raise ValueError("invalid channel evidence size")
            runtime_payload = json.loads(
                runtime_raw.decode("utf-8", errors="strict")
            )
            runtime_rows = (
                runtime_payload.get("currentPage")
                if isinstance(runtime_payload, dict)
                else runtime_payload
            )
            if not isinstance(runtime_rows, list):
                raise ValueError("invalid runtime view evidence")
            evidence = mobile_identity_from_channel_and_views(
                raw.decode("utf-8", errors="strict"),
                runtime_rows,
                expected_runtime=None if argv[2] == "-" else argv[2],
            )
        except (OSError, UnicodeError, ValueError) as error:
            raise ProductionProbeError(
                "cannot parse bounded EAS channel evidence"
            ) from error
        print(evidence.canonical_json)
        return 0
    print(json.dumps(identity, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
