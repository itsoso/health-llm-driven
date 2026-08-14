#!/usr/bin/python3
"""Crash-recoverable one-time bootstrap for the production Mac download routes."""

from __future__ import annotations

import sys

if __name__ == "__main__":
    print(
        "MAC_NGINX_BOOTSTRAP_FROZEN: production route mutation requires the "
        "manual infrastructure Gate",
        file=sys.stderr,
    )
    raise SystemExit(78)

import base64
import binascii
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
from pathlib import Path
from typing import Callable, NamedTuple


TARGET_PATH = Path("/etc/nginx/conf.d/health.executor.life.conf")
SNIPPET_PATH = Path("/etc/nginx/snippets/reva-mac-release-routes.conf")
STATE_ROOT = Path("/var/lib/health-app/mac-nginx-bootstrap")
ANCHOR = b"    # Rokid glasses push-up APK static distribution"
INCLUDE_LINE = b"    include /etc/nginx/snippets/reva-mac-release-routes.conf;"
BEGIN_MARKER = b"# BEGIN REVA MANAGED MAC RELEASE ROUTES"
END_MARKER = b"# END REVA MANAGED MAC RELEASE ROUTES"
MAX_CONFIG_BYTES = 512 * 1024
MAX_SNIPPET_BYTES = 32 * 1024
MAX_STATE_BYTES = 64 * 1024
HEX64 = re.compile(r"[0-9a-f]{64}")
SAFE_BACKUP = re.compile(r"[0-9a-f]{64}\.conf")


class BootstrapError(RuntimeError):
    pass


class BootstrapPaths(NamedTuple):
    target: Path
    snippet: Path
    state_root: Path
    formal_receipt: Path
    formal_previous_receipt: Path
    formal_journal: Path
    formal_current: Path


RunCommand = Callable[[tuple[str, ...]], None]
ProbeHTTP = Callable[[], dict[str, object]]


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _default_run_command(argv: tuple[str, ...]) -> None:
    try:
        completed = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BootstrapError(f"command could not complete: {argv[0]}") from error
    if completed.returncode != 0:
        detail = completed.stderr[:4096].decode("utf-8", errors="replace").strip()
        raise BootstrapError(f"command failed: {argv[0]}: {detail}")


def _curl_base() -> list[str]:
    return [
        "/usr/bin/curl",
        "--silent",
        "--show-error",
        "--proto",
        "=https",
        "--tlsv1.2",
        "--connect-timeout",
        "10",
    ]


def _legacy_http_hash() -> str:
    command = _curl_base() + [
        "--fail",
        "--max-time",
        "300",
        "https://health.executor.life/xiaoba-mac.dmg",
    ]
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise BootstrapError("legacy HTTP proof could not start") from error
    digest = hashlib.sha256()
    total = 0
    assert process.stdout is not None
    while True:
        chunk = process.stdout.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > 1024 * 1024 * 1024:
            process.kill()
            process.wait()
            raise BootstrapError("legacy HTTP proof exceeds the 1 GiB safety cap")
        digest.update(chunk)
    try:
        _, stderr = process.communicate(timeout=300)
    except subprocess.TimeoutExpired as error:
        process.kill()
        process.wait()
        raise BootstrapError("legacy HTTP proof timed out") from error
    if process.returncode != 0 or total == 0:
        detail = stderr[:4096].decode("utf-8", errors="replace").strip()
        raise BootstrapError(f"legacy HTTP proof failed: {detail}")
    return digest.hexdigest()


def _marker_proof(url: str) -> tuple[int, str | None]:
    command = _curl_base() + [
        "--max-time",
        "30",
        "--dump-header",
        "-",
        "--output",
        "/dev/null",
        "--write-out",
        "\nX_REVA_HTTP_STATUS:%{http_code}\n",
        url,
    ]
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=40,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BootstrapError("route marker HTTP proof could not complete") from error
    if completed.returncode != 0 or len(completed.stdout) > 64 * 1024:
        raise BootstrapError("route marker HTTP proof failed")
    headers = completed.stdout.decode("iso-8859-1", errors="strict")
    status_values = re.findall(r"(?m)^X_REVA_HTTP_STATUS:([0-9]{3})$", headers)
    if len(status_values) != 1:
        raise BootstrapError("route marker HTTP status proof is ambiguous")
    values = re.findall(r"(?im)^X-Reva-Artifact:\s*([^\r\n]+)\s*$", headers)
    if len(values) > 1:
        raise BootstrapError("route marker HTTP proof is ambiguous")
    return int(status_values[0]), values[0].strip() if values else None


def _default_probe_http() -> dict[str, object]:
    zero_sha = "0" * 40
    zero_digest = "0" * 64
    current_status, current_marker = _marker_proof(
        "https://health.executor.life/mac/current.json"
    )
    immutable_status, immutable_marker = _marker_proof(
        f"https://health.executor.life/mac/releases/{zero_sha}/{zero_digest}.dmg"
    )
    return {
        "legacy_sha256": _legacy_http_hash(),
        "current_status": current_status,
        "current_marker": current_marker,
        "immutable_status": immutable_status,
        "immutable_marker": immutable_marker,
    }


def _assert_protocol_test_boundary(
    *,
    paths: BootstrapPaths,
    expected_uid: int,
    expected_gid: int,
    run_command: RunCommand,
    probe_http: ProbeHTTP,
) -> None:
    if os.environ.get("MAC_RELEASE_TEST_MODE") != "1":
        raise BootstrapError("Mac nginx protocol manager requires explicit test mode")
    effective_uid = os.geteuid()
    effective_gid = os.getegid()
    if effective_uid == 0:
        raise BootstrapError("Mac nginx protocol manager requires a non-root identity")
    if expected_uid != effective_uid or expected_gid != effective_gid:
        raise BootstrapError("Mac nginx protocol manager identity does not match the caller")
    if (
        run_command is _default_run_command
        or probe_http is _default_probe_http
        or not callable(run_command)
        or not callable(probe_http)
    ):
        raise BootstrapError(
            "Mac nginx protocol manager requires explicit test callbacks"
        )
    allowed_roots = (
        (Path("/private/tmp"), Path("/private/var/folders"))
        if sys.platform == "darwin"
        else (Path("/tmp"),)
    )
    for path in paths:
        if not path.is_absolute():
            raise BootstrapError(
                "Mac nginx protocol paths must use a fixed non-production root"
            )
        try:
            resolved = path.resolve(strict=False)
        except OSError as error:
            raise BootstrapError(
                "Mac nginx protocol paths must use a fixed non-production root"
            ) from error
        if not any(root in resolved.parents for root in allowed_roots):
            raise BootstrapError(
                "Mac nginx protocol paths must use a fixed non-production root"
            )


class RouteBootstrap:
    def __init__(
        self,
        *,
        paths: BootstrapPaths,
        expected_uid: int,
        expected_gid: int,
        run_command: RunCommand = _default_run_command,
        probe_http: ProbeHTTP = _default_probe_http,
        fault_hook: Callable[[str], None] | None = None,
        assert_lock: Callable[[], None] | None = None,
    ) -> None:
        _assert_protocol_test_boundary(
            paths=paths,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            run_command=run_command,
            probe_http=probe_http,
        )
        self.paths = paths
        self.expected_uid = expected_uid
        self.expected_gid = expected_gid
        self.run_command = run_command
        self.probe_http = probe_http
        self.fault_hook = fault_hook or (lambda _point: None)
        self.assert_lock = assert_lock or (lambda: None)

    def _validate_metadata(
        self, metadata: os.stat_result, *, mode: int, regular: bool, label: str
    ) -> None:
        kind_ok = stat.S_ISREG(metadata.st_mode) if regular else stat.S_ISDIR(metadata.st_mode)
        if (
            not kind_ok
            or metadata.st_uid != self.expected_uid
            or metadata.st_gid != self.expected_gid
            or stat.S_IMODE(metadata.st_mode) != mode
            or (regular and metadata.st_nlink != 1)
        ):
            raise BootstrapError(f"unsafe {label} metadata")

    def _read_regular(self, path: Path, *, mode: int, maximum: int) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            raise BootstrapError(f"could not safely open {path.name}") from error
        try:
            metadata = os.fstat(descriptor)
            self._validate_metadata(metadata, mode=mode, regular=True, label=path.name)
            if metadata.st_size <= 0 or metadata.st_size > maximum:
                raise BootstrapError(f"unsafe {path.name} size")
            value = os.read(descriptor, maximum + 1)
            if len(value) > maximum or os.read(descriptor, 1):
                raise BootstrapError(f"oversized {path.name}")
            final_metadata = os.fstat(descriptor)
            if (
                metadata.st_dev != final_metadata.st_dev
                or metadata.st_ino != final_metadata.st_ino
                or metadata.st_size != final_metadata.st_size
                or metadata.st_mtime_ns != final_metadata.st_mtime_ns
                or metadata.st_ctime_ns != final_metadata.st_ctime_ns
            ):
                raise BootstrapError(f"{path.name} changed while it was read")
            return value
        finally:
            os.close(descriptor)

    def _ensure_state_root(self) -> None:
        parent = self.paths.state_root.parent
        try:
            parent_meta = os.lstat(parent)
        except OSError as error:
            raise BootstrapError("state parent is unavailable") from error
        if (
            not stat.S_ISDIR(parent_meta.st_mode)
            or parent_meta.st_uid != self.expected_uid
            or parent_meta.st_gid != self.expected_gid
            or stat.S_IMODE(parent_meta.st_mode) & 0o022
        ):
            raise BootstrapError("unsafe state parent")
        try:
            self.paths.state_root.mkdir(mode=0o700)
        except FileExistsError:
            pass
        metadata = os.lstat(self.paths.state_root)
        self._validate_metadata(metadata, mode=0o700, regular=False, label="state root")
        backups = self.paths.state_root / "backups"
        try:
            backups.mkdir(mode=0o700)
        except FileExistsError:
            pass
        self._validate_metadata(
            os.lstat(backups), mode=0o700, regular=False, label="backup root"
        )

    def _validate_snippet_parent(self) -> None:
        try:
            metadata = os.lstat(self.paths.snippet.parent)
        except OSError as error:
            raise BootstrapError("nginx snippet parent is unavailable") from error
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != self.expected_uid
            or metadata.st_gid != self.expected_gid
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise BootstrapError("unsafe nginx snippet parent")

    def _assert_no_formal_mac_release(self) -> None:
        """Refuse the one-time route rollback once formal publication has started."""
        markers = (
            self.paths.formal_receipt,
            self.paths.formal_previous_receipt,
            self.paths.formal_journal,
            self.paths.formal_current,
        )
        checked_parents: set[Path] = set()
        for path in markers:
            parent = path.parent
            if parent not in checked_parents:
                checked_parents.add(parent)
                try:
                    parent_meta = os.lstat(parent)
                except FileNotFoundError:
                    parent_meta = None
                except OSError as error:
                    raise BootstrapError(
                        "formal Mac release state cannot be inspected safely"
                    ) from error
                if parent_meta is not None and (
                    not stat.S_ISDIR(parent_meta.st_mode)
                    or parent_meta.st_uid != self.expected_uid
                    or parent_meta.st_gid != self.expected_gid
                    or stat.S_IMODE(parent_meta.st_mode) & 0o022
                ):
                    raise BootstrapError("unsafe formal Mac release state parent")
            try:
                os.lstat(path)
            except FileNotFoundError:
                continue
            except OSError as error:
                raise BootstrapError(
                    "formal Mac release state cannot be inspected safely"
                ) from error
            raise BootstrapError(
                "formal Mac release state exists; nginx route rollback is forbidden"
            )

    def _read_optional_snippet(self) -> bytes | None:
        self._validate_snippet_parent()
        try:
            os.lstat(self.paths.snippet)
        except FileNotFoundError:
            return None
        return self._read_regular(
            self.paths.snippet, mode=0o644, maximum=MAX_SNIPPET_BYTES
        )

    def _remove_snippet(self) -> None:
        try:
            metadata = os.lstat(self.paths.snippet)
        except FileNotFoundError:
            return
        self._validate_metadata(
            metadata, mode=0o644, regular=True, label="nginx route snippet"
        )
        self.assert_lock()
        self.paths.snippet.unlink()
        directory_fd = os.open(
            self.paths.snippet.parent,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _atomic_write(self, path: Path, value: bytes, *, mode: int) -> None:
        parent_meta = os.lstat(path.parent)
        if (
            not stat.S_ISDIR(parent_meta.st_mode)
            or parent_meta.st_uid != self.expected_uid
            or parent_meta.st_gid != self.expected_gid
            or stat.S_IMODE(parent_meta.st_mode) & 0o022
        ):
            raise BootstrapError("atomic write parent is unsafe")
        temporary = path.parent / f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, mode)
        try:
            os.fchmod(descriptor, mode)
            os.fchown(descriptor, self.expected_uid, self.expected_gid)
            view = memoryview(value)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise BootstrapError("short atomic write")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            self.assert_lock()
            os.replace(temporary, path)
            directory_fd = os.open(
                path.parent,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _write_json(self, name: str, value: dict[str, object]) -> None:
        encoded = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
        if len(encoded) > MAX_STATE_BYTES:
            raise BootstrapError("state payload is too large")
        self._atomic_write(self.paths.state_root / name, encoded, mode=0o600)

    def _read_json(self, name: str) -> dict[str, object] | None:
        path = self.paths.state_root / name
        try:
            os.lstat(path)
        except FileNotFoundError:
            return None
        raw = self._read_regular(path, mode=0o600, maximum=MAX_STATE_BYTES)

        def reject_duplicate_keys(
            pairs: list[tuple[str, object]],
        ) -> dict[str, object]:
            value: dict[str, object] = {}
            for key, item in pairs:
                if key in value:
                    raise BootstrapError(f"duplicate key in {name}: {key}")
                value[key] = item
            return value

        try:
            value = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise BootstrapError(f"invalid {name}") from error
        if not isinstance(value, dict):
            raise BootstrapError(f"invalid {name}")
        return value

    def _delete_state(self, name: str) -> None:
        path = self.paths.state_root / name
        try:
            metadata = os.lstat(path)
        except FileNotFoundError:
            return
        self._validate_metadata(metadata, mode=0o600, regular=True, label=name)
        self.assert_lock()
        path.unlink()
        directory_fd = os.open(
            self.paths.state_root,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _lock(self):
        self._ensure_state_root()
        lock_path = self.paths.state_root / "lock"
        flags = os.O_RDWR | os.O_CREAT
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(lock_path, flags, 0o600)
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, self.expected_uid, self.expected_gid)
        self._validate_metadata(
            os.fstat(descriptor), mode=0o600, regular=True, label="bootstrap lock"
        )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            os.close(descriptor)
            raise BootstrapError("another Mac route bootstrap is active") from error
        return descriptor

    def _validate_target(self, value: bytes) -> None:
        if value.count(INCLUDE_LINE) not in (0, 1):
            raise BootstrapError("managed route include is ambiguous")
        if value.count(ANCHOR) != 1:
            raise BootstrapError("required legacy route anchor is not unique")
        if value.count(b"location = /xiaoba-mac.dmg") != 1:
            raise BootstrapError("required legacy Mac download location is not unique")
        if BEGIN_MARKER in value or END_MARKER in value:
            raise BootstrapError("route snippet must not be inlined into the active config")

    def _validate_snippet(self, snippet: bytes) -> bytes:
        if not snippet or len(snippet) > MAX_SNIPPET_BYTES or b"\x00" in snippet:
            raise BootstrapError("invalid route snippet size")
        try:
            snippet.decode("ascii", errors="strict")
        except UnicodeError as error:
            raise BootstrapError("route snippet must be ASCII") from error
        required = (
            BEGIN_MARKER,
            END_MARKER,
            b"location = /mac/current.json",
            b"mac-current-manifest",
            b"mac-immutable-dmg",
        )
        if any(snippet.count(token) != 1 for token in required):
            raise BootstrapError("route snippet contract is incomplete or ambiguous")
        if snippet.count(b"alias /opt/health-app-shared/assets/") != 2:
            raise BootstrapError("route snippet asset roots are incomplete or ambiguous")
        if b"$uri" in snippet or b".." in snippet:
            raise BootstrapError("route snippet contains an unsafe path expression")
        return snippet.rstrip(b"\n") + b"\n"

    def _validate_proof(self, proof: dict[str, object]) -> None:
        if set(proof) != {
            "legacy_sha256",
            "current_status",
            "current_marker",
            "immutable_status",
            "immutable_marker",
        }:
            raise BootstrapError("HTTP proof shape is invalid")
        legacy = proof["legacy_sha256"]
        if not isinstance(legacy, str) or HEX64.fullmatch(legacy) is None:
            raise BootstrapError("legacy HTTP hash is invalid")
        for key in ("current_marker", "immutable_marker"):
            if proof[key] is not None and not isinstance(proof[key], str):
                raise BootstrapError("route marker is invalid")
        for key in ("current_status", "immutable_status"):
            if isinstance(proof[key], bool) or not isinstance(proof[key], int):
                raise BootstrapError("route status is invalid")

    def _verify_runtime(
        self,
        *,
        legacy_sha256: str,
        current_marker: str | None,
        immutable_marker: str | None,
        current_status: int | tuple[int, ...],
        immutable_status: int,
        reload: bool,
    ) -> None:
        self.assert_lock()
        self.run_command(("/usr/sbin/nginx", "-t"))
        if reload:
            self.assert_lock()
            self.run_command(("/usr/bin/systemctl", "reload", "nginx"))
        self.assert_lock()
        self.run_command(("/usr/bin/systemctl", "is-active", "--quiet", "nginx"))
        proof = self.probe_http()
        self._validate_proof(proof)
        allowed_current = (
            current_status if isinstance(current_status, tuple) else (current_status,)
        )
        if (
            proof["legacy_sha256"] != legacy_sha256
            or proof["current_status"] not in allowed_current
            or proof["current_marker"] != current_marker
            or proof["immutable_status"] != immutable_status
            or proof["immutable_marker"] != immutable_marker
        ):
            raise BootstrapError("HTTP route proof changed unexpectedly")

    def _backup_path(self, name: object) -> Path:
        if not isinstance(name, str) or SAFE_BACKUP.fullmatch(name) is None:
            raise BootstrapError("invalid backup name")
        return self.paths.state_root / "backups" / name

    def _save_backup(self, value: bytes) -> str:
        name = f"{_sha256(value)}.conf"
        path = self._backup_path(name)
        if path.exists():
            if self._read_regular(path, mode=0o600, maximum=MAX_CONFIG_BYTES) != value:
                raise BootstrapError("existing backup content does not match its digest")
        else:
            self._atomic_write(path, value, mode=0o600)
        return name

    def _load_backup(self, name: object, expected_hash: object) -> bytes:
        if not isinstance(expected_hash, str) or HEX64.fullmatch(expected_hash) is None:
            raise BootstrapError("invalid expected backup hash")
        value = self._read_regular(
            self._backup_path(name), mode=0o600, maximum=MAX_CONFIG_BYTES
        )
        if _sha256(value) != expected_hash:
            raise BootstrapError("backup digest mismatch")
        return value

    def _validate_receipt(
        self, receipt: dict[str, object], *, statuses: set[str]
    ) -> None:
        required = {
            "schema_version",
            "status",
            "target",
            "snippet_path",
            "backup_name",
            "original_sha256",
            "applied_sha256",
            "snippet_sha256",
            "managed_snippet_backup_name",
            "original_snippet_existed",
            "original_snippet_sha256",
            "snippet_backup_name",
            "http_before",
        }
        if set(receipt) != required:
            raise BootstrapError("receipt fields are invalid")
        if receipt["schema_version"] != 1 or receipt["status"] not in statuses:
            raise BootstrapError("receipt version or status is invalid")
        if receipt["target"] != str(self.paths.target):
            raise BootstrapError("receipt target is invalid")
        if receipt["snippet_path"] != str(self.paths.snippet):
            raise BootstrapError("receipt snippet path is invalid")
        for key in ("original_sha256", "applied_sha256", "snippet_sha256"):
            value = receipt[key]
            if not isinstance(value, str) or HEX64.fullmatch(value) is None:
                raise BootstrapError(f"receipt {key} is invalid")
        if receipt["managed_snippet_backup_name"] != f"{receipt['snippet_sha256']}.conf":
            raise BootstrapError("receipt managed snippet backup binding is invalid")
        expected_backup = f"{receipt['original_sha256']}.conf"
        if receipt["backup_name"] != expected_backup:
            raise BootstrapError("receipt target backup binding is invalid")
        existed = receipt["original_snippet_existed"]
        if not isinstance(existed, bool):
            raise BootstrapError("receipt snippet existence is invalid")
        if existed:
            snippet_hash = receipt["original_snippet_sha256"]
            if not isinstance(snippet_hash, str) or HEX64.fullmatch(snippet_hash) is None:
                raise BootstrapError("receipt original snippet digest is invalid")
            if receipt["snippet_backup_name"] != f"{snippet_hash}.conf":
                raise BootstrapError("receipt snippet backup binding is invalid")
        elif (
            receipt["original_snippet_sha256"] is not None
            or receipt["snippet_backup_name"] is not None
        ):
            raise BootstrapError("receipt absent snippet binding is invalid")
        proof = receipt["http_before"]
        if not isinstance(proof, dict):
            raise BootstrapError("receipt HTTP proof is invalid")
        self._validate_proof(proof)

    def _validate_journal(self, journal: dict[str, object]) -> dict[str, object]:
        if set(journal) != {"schema_version", "action", "receipt"}:
            raise BootstrapError("journal fields are invalid")
        if journal["schema_version"] != 1 or journal["action"] not in {
            "apply",
            "rollback",
        }:
            raise BootstrapError("journal version or action is invalid")
        receipt = journal["receipt"]
        if not isinstance(receipt, dict):
            raise BootstrapError("journal receipt is invalid")
        self._validate_receipt(receipt, statuses={"applied"})
        return receipt

    def _original_components(
        self, receipt: dict[str, object]
    ) -> tuple[bytes, bytes | None]:
        original = self._load_backup(
            receipt["backup_name"], receipt["original_sha256"]
        )
        original_snippet = None
        if receipt["original_snippet_existed"]:
            original_snippet = self._load_backup(
                receipt["snippet_backup_name"], receipt["original_snippet_sha256"]
            )
        return original, original_snippet

    def _restore_original_components(
        self, original: bytes, original_snippet: bytes | None
    ) -> None:
        self._atomic_write(self.paths.target, original, mode=0o644)
        if original_snippet is None:
            self._remove_snippet()
        else:
            self._atomic_write(self.paths.snippet, original_snippet, mode=0o644)

    @staticmethod
    def _snippet_matches(value: bytes | None, expected_hash: object) -> bool:
        return value is not None and _sha256(value) == expected_hash

    def _receipt_from_journal(self, journal: dict[str, object]) -> dict[str, object]:
        return self._validate_journal(journal)

    def _recover_apply(self, journal: dict[str, object], snippet_hash: str) -> str | None:
        receipt = self._validate_journal(journal)
        if journal["action"] != "apply":
            return None
        if receipt["snippet_sha256"] != snippet_hash:
            raise BootstrapError("interrupted apply used a different route snippet")
        target = self._read_regular(self.paths.target, mode=0o644, maximum=MAX_CONFIG_BYTES)
        active_snippet = self._read_optional_snippet()
        target_hash = _sha256(target)
        old_hash = receipt["original_sha256"]
        applied_hash = receipt["applied_sha256"]
        original, original_snippet = self._original_components(receipt)
        known_snippet_hashes = {snippet_hash}
        if original_snippet is not None:
            known_snippet_hashes.add(_sha256(original_snippet))
        if target_hash not in {old_hash, applied_hash} or (
            active_snippet is not None and _sha256(active_snippet) not in known_snippet_hashes
        ):
            raise BootstrapError("interrupted apply encountered unknown nginx bytes")
        before = receipt["http_before"]
        assert isinstance(before, dict)
        if target_hash != applied_hash or not self._snippet_matches(
            active_snippet, snippet_hash
        ):
            self._restore_original_components(original, original_snippet)
            self._verify_runtime(
                legacy_sha256=str(before["legacy_sha256"]),
                current_status=int(before["current_status"]),
                current_marker=before["current_marker"],
                immutable_status=int(before["immutable_status"]),
                immutable_marker=before["immutable_marker"],
                reload=True,
            )
            self._delete_state("journal.json")
            return None
        self._verify_runtime(
            legacy_sha256=str(before["legacy_sha256"]),
            current_status=(200, 404),
            current_marker="mac-current-manifest",
            immutable_status=404,
            immutable_marker="mac-immutable-dmg",
            reload=True,
        )
        self._write_json("receipt.json", receipt)
        self._delete_state("journal.json")
        return "recovered-applied"

    def apply(self, snippet: bytes) -> str:
        snippet = self._validate_snippet(snippet)
        self.assert_lock()
        lock_fd = self._lock()
        try:
            journal = self._read_json("journal.json")
            if journal is not None:
                recovered = self._recover_apply(journal, _sha256(snippet))
                if recovered is not None:
                    return recovered
            original = self._read_regular(
                self.paths.target, mode=0o644, maximum=MAX_CONFIG_BYTES
            )
            self._validate_target(original)
            existing_snippet = self._read_optional_snippet()
            if INCLUDE_LINE in original:
                receipt = self._read_json("receipt.json")
                if receipt is None:
                    if not self._snippet_matches(existing_snippet, _sha256(snippet)):
                        raise BootstrapError(
                            "managed routes exist without an exact tracked snippet"
                        )
                    proof = self.probe_http()
                    self._validate_proof(proof)
                    self._verify_runtime(
                        legacy_sha256=str(proof["legacy_sha256"]),
                        current_status=(200, 404),
                        current_marker="mac-current-manifest",
                        immutable_status=404,
                        immutable_marker="mac-immutable-dmg",
                        reload=False,
                    )
                    return "tracked-baseline-already-installed"
                self._validate_receipt(receipt, statuses={"applied"})
                if (
                    receipt["applied_sha256"] != _sha256(original)
                    or receipt["snippet_sha256"] != _sha256(snippet)
                    or not self._snippet_matches(existing_snippet, _sha256(snippet))
                ):
                    raise BootstrapError("managed routes do not match their receipt")
                before = receipt["http_before"]
                assert isinstance(before, dict)
                self._verify_runtime(
                    legacy_sha256=str(before["legacy_sha256"]),
                    current_status=(200, 404),
                    current_marker="mac-current-manifest",
                    immutable_status=404,
                    immutable_marker="mac-immutable-dmg",
                    reload=False,
                )
                return "already-applied"

            pre_http = self.probe_http()
            self._validate_proof(pre_http)
            self._verify_runtime(
                legacy_sha256=str(pre_http["legacy_sha256"]),
                current_status=int(pre_http["current_status"]),
                current_marker=pre_http["current_marker"],
                immutable_status=int(pre_http["immutable_status"]),
                immutable_marker=pre_http["immutable_marker"],
                reload=False,
            )
            backup_name = self._save_backup(original)
            original_snippet_backup = (
                self._save_backup(existing_snippet) if existing_snippet is not None else None
            )
            managed_snippet_backup = self._save_backup(snippet)
            replacement = INCLUDE_LINE + b"\n\n" + ANCHOR
            applied = original.replace(ANCHOR, replacement, 1)
            receipt: dict[str, object] = {
                "schema_version": 1,
                "status": "applied",
                "target": str(self.paths.target),
                "snippet_path": str(self.paths.snippet),
                "backup_name": backup_name,
                "original_sha256": _sha256(original),
                "applied_sha256": _sha256(applied),
                "snippet_sha256": _sha256(snippet),
                "managed_snippet_backup_name": managed_snippet_backup,
                "original_snippet_existed": existing_snippet is not None,
                "original_snippet_sha256": (
                    _sha256(existing_snippet) if existing_snippet is not None else None
                ),
                "snippet_backup_name": original_snippet_backup,
                "http_before": pre_http,
            }
            journal = {"schema_version": 1, "action": "apply", "receipt": receipt}
            self._write_json("journal.json", journal)
            self._atomic_write(self.paths.snippet, snippet, mode=0o644)
            self.fault_hook("after-snippet-replace")
            self._atomic_write(self.paths.target, applied, mode=0o644)
            self.fault_hook("after-target-replace")
            try:
                self._verify_runtime(
                    legacy_sha256=str(pre_http["legacy_sha256"]),
                    current_status=(200, 404),
                    current_marker="mac-current-manifest",
                    immutable_status=404,
                    immutable_marker="mac-immutable-dmg",
                    reload=True,
                )
            except Exception as error:
                self._restore_original_components(original, existing_snippet)
                try:
                    self._verify_runtime(
                        legacy_sha256=str(pre_http["legacy_sha256"]),
                        current_status=int(pre_http["current_status"]),
                        current_marker=pre_http["current_marker"],
                        immutable_status=int(pre_http["immutable_status"]),
                        immutable_marker=pre_http["immutable_marker"],
                        reload=True,
                    )
                except Exception as restore_error:
                    raise BootstrapError(
                        "route activation failed and automatic restore could not be verified"
                    ) from restore_error
                self._delete_state("journal.json")
                raise BootstrapError("route activation failed; original config restored") from error
            self._write_json("receipt.json", receipt)
            self._delete_state("journal.json")
            return "applied"
        finally:
            os.close(lock_fd)

    def rollback(self) -> str:
        self.assert_lock()
        lock_fd = self._lock()
        try:
            self.assert_lock()
            self._assert_no_formal_mac_release()
            journal = self._read_json("journal.json")
            if journal is not None:
                receipt_for_recovery = self._validate_journal(journal)
                action = journal["action"]
                if action == "apply":
                    recovered = self._recover_apply(
                        journal, str(receipt_for_recovery["snippet_sha256"])
                    )
                    if recovered is None:
                        receipt_for_recovery["status"] = "rolled-back"
                        self._write_json("receipt.json", receipt_for_recovery)
                        return "recovered-rolled-back"
                else:
                    original, original_snippet = self._original_components(
                        receipt_for_recovery
                    )
                    current = self._read_regular(
                        self.paths.target, mode=0o644, maximum=MAX_CONFIG_BYTES
                    )
                    active_snippet = self._read_optional_snippet()
                    known_targets = {
                        receipt_for_recovery["original_sha256"],
                        receipt_for_recovery["applied_sha256"],
                    }
                    known_snippets = {receipt_for_recovery["snippet_sha256"]}
                    if original_snippet is not None:
                        known_snippets.add(_sha256(original_snippet))
                    if _sha256(current) not in known_targets or (
                        active_snippet is not None
                        and _sha256(active_snippet) not in known_snippets
                    ):
                        raise BootstrapError(
                            "interrupted rollback encountered unknown nginx bytes"
                        )
                    self._restore_original_components(original, original_snippet)
                    before = receipt_for_recovery["http_before"]
                    assert isinstance(before, dict)
                    self._verify_runtime(
                        legacy_sha256=str(before["legacy_sha256"]),
                        current_status=int(before["current_status"]),
                        current_marker=before["current_marker"],
                        immutable_status=int(before["immutable_status"]),
                        immutable_marker=before["immutable_marker"],
                        reload=True,
                    )
                    receipt_for_recovery["status"] = "rolled-back"
                    self._write_json("receipt.json", receipt_for_recovery)
                    self._delete_state("journal.json")
                    return "recovered-rolled-back"
            receipt = self._read_json("receipt.json")
            if receipt is None:
                raise BootstrapError("no Mac route bootstrap receipt exists")
            self._validate_receipt(receipt, statuses={"applied", "rolled-back"})
            original, original_snippet = self._original_components(receipt)
            current = self._read_regular(
                self.paths.target, mode=0o644, maximum=MAX_CONFIG_BYTES
            )
            active_snippet = self._read_optional_snippet()
            before = receipt["http_before"]
            assert isinstance(before, dict)
            if receipt["status"] == "rolled-back":
                original_snippet_ok = (
                    active_snippet is None
                    if original_snippet is None
                    else self._snippet_matches(active_snippet, _sha256(original_snippet))
                )
                if (
                    _sha256(current) != receipt["original_sha256"]
                    or not original_snippet_ok
                ):
                    raise BootstrapError("rolled-back receipt does not match target")
                self._verify_runtime(
                    legacy_sha256=str(before["legacy_sha256"]),
                    current_status=int(before["current_status"]),
                    current_marker=before["current_marker"],
                    immutable_status=int(before["immutable_status"]),
                    immutable_marker=before["immutable_marker"],
                    reload=False,
                )
                return "already-rolled-back"
            if (
                _sha256(current) != receipt["applied_sha256"]
                or not self._snippet_matches(active_snippet, receipt["snippet_sha256"])
            ):
                raise BootstrapError("current nginx config does not match the applied receipt")
            journal = {"schema_version": 1, "action": "rollback", "receipt": receipt}
            self._write_json("journal.json", journal)
            self._restore_original_components(original, original_snippet)
            self.fault_hook("after-target-replace")
            try:
                self._verify_runtime(
                    legacy_sha256=str(before["legacy_sha256"]),
                    current_status=int(before["current_status"]),
                    current_marker=before["current_marker"],
                    immutable_status=int(before["immutable_status"]),
                    immutable_marker=before["immutable_marker"],
                    reload=True,
                )
            except Exception as error:
                self._atomic_write(
                    self.paths.snippet,
                    self._load_backup(
                        receipt["managed_snippet_backup_name"],
                        receipt["snippet_sha256"],
                    ),
                    mode=0o644,
                )
                self._atomic_write(self.paths.target, current, mode=0o644)
                try:
                    self._verify_runtime(
                        legacy_sha256=str(before["legacy_sha256"]),
                        current_status=(200, 404),
                        current_marker="mac-current-manifest",
                        immutable_status=404,
                        immutable_marker="mac-immutable-dmg",
                        reload=True,
                    )
                except Exception as restore_error:
                    raise BootstrapError(
                        "rollback failed and applied config restore could not be verified"
                    ) from restore_error
                self._delete_state("journal.json")
                raise BootstrapError("rollback failed; applied config restored") from error
            receipt["status"] = "rolled-back"
            self._write_json("receipt.json", receipt)
            self._delete_state("journal.json")
            return "rolled-back"
        finally:
            os.close(lock_fd)


def _decode_snippet(encoded: str) -> bytes:
    if not encoded or len(encoded) > MAX_SNIPPET_BYTES * 2:
        raise BootstrapError("encoded route snippet has an invalid size")
    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise BootstrapError("route snippet is not valid base64") from error


def assert_remote_release_lock(token: str) -> None:
    lock_path = Path("/var/lib/health-app/release-state/deploy.lock")
    if re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", token) is None:
        raise BootstrapError("remote release lock token is invalid")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        lock_fd = os.open(lock_path, flags)
    except OSError as error:
        raise BootstrapError("remote release lock is unavailable") from error
    try:
        metadata = os.fstat(lock_fd)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_gid != 0
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise BootstrapError("remote release lock directory is unsafe")
        token_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        token_flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        token_fd = os.open("token", token_flags, dir_fd=lock_fd)
        try:
            token_meta = os.fstat(token_fd)
            if (
                not stat.S_ISREG(token_meta.st_mode)
                or token_meta.st_uid != 0
                or token_meta.st_gid != 0
                or stat.S_IMODE(token_meta.st_mode) != 0o600
                or token_meta.st_nlink != 1
                or token_meta.st_size <= 0
                or token_meta.st_size > 257
            ):
                raise BootstrapError("remote release lock token file is unsafe")
            raw = os.read(token_fd, 258)
            if len(raw) > 257 or os.read(token_fd, 1):
                raise BootstrapError("remote release lock token is oversized")
        finally:
            os.close(token_fd)
    finally:
        os.close(lock_fd)
    if raw != f"{token}\n".encode("ascii"):
        raise BootstrapError("remote release lock ownership changed")


def main(_argv: list[str]) -> int:
    raise BootstrapError(
        "Mac nginx production bootstrap is frozen; use the manual infrastructure Gate"
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except BootstrapError as error:
        print(f"MAC_NGINX_BOOTSTRAP_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
