#!/usr/bin/python3
"""Fail-closed publisher for an immutable, notarized macOS DMG.

The release shell builds and verifies the artifact.  This helper is copied to the
production host together with the artifact and a bounded candidate receipt.  It
is the only process allowed to switch the public ``current.json`` pointer.
"""

from __future__ import annotations

import sys

# Direct execution is unconditionally frozen before importing parsers, path
# helpers, or any module that could observe credentials or invoke tools.  Unit
# tests exercise the isolated, non-root protocol by importing this module from
# their dedicated runner; no argv value can weaken the real CLI boundary.
if __name__ == "__main__":
    print(
        "MAC_RELEASE_PUBLISH_FROZEN: production mutation requires the manual "
        "release Gate",
        file=sys.stderr,
    )
    raise SystemExit(78)

import argparse
import ctypes
import errno
import fcntl
import hashlib
import hmac
import json
import os
import re
import stat
import time
import uuid
from pathlib import Path
from typing import Any, Optional, Tuple


MAX_RECEIPT_BYTES = 64 * 1024
MAX_JOURNAL_BYTES = 64 * 1024
MAX_ARTIFACT_BYTES = 1024 * 1024 * 1024
RECEIPT_NAME = "mac-runtime.json"
PREVIOUS_NAME = "mac-runtime.previous.json"
JOURNAL_NAME = "mac-release.transaction.json"
CURRENT_RELATIVE = Path("mac/current.json")
STABLE_NAME = "xiaoba-mac.dmg"
STABLE_BACKUP_NAME = ".xiaoba-mac.dmg.rollback"
LOCK_NAME = "mac-release.lock"
EXPECTED_BUNDLE_ID = "life.executor.health.mac"
EXPECTED_TEAM_ID = "QA2U724DAN"
EXPECTED_RELEASE_LOCK_DIR = Path("/var/lib/health-app/release-state/deploy.lock")
EXPECTED_ASSET_ROOT = Path("/opt/health-app-shared/assets")
EXPECTED_STATE_ROOT = Path("/var/lib/health-app/release-state")

LEASE_LABEL = "mac-dmg-release"
LEASE_FIELDS = (
    "artifact_sha256",
    "artifact_size",
    "candidate_sha256",
    "helper_sha256",
    "label",
    "operation",
    "phase",
    "source_sha",
    "source_tree",
    "stage",
    "stage_kind",
    "started_at",
    "token",
)
LEASE_PHASES = {"staging", "sealed", "mutating"}
LEASE_OPERATIONS = {"publish", "recover", "rollback"}
LEASE_STAGE_KINDS = {"publish", "maintenance"}
HANDOFF_FIELDS = {
    "schema",
    "server",
    "lock_dir",
    "token",
    "operation",
    "stage_kind",
    "stage",
    "source_sha",
    "source_tree",
    "helper_sha256",
    "artifact_sha256",
    "artifact_size",
    "candidate_sha256",
}
HANDOFF_FILES = {"handoff", "mac_release_publish.py"}
REMOTE_STAGE_FILES = {
    "mac_release_publish.py",
    ".mac_release_publish.py.upload",
    "candidate.json",
    ".candidate.json.upload",
    "upload.dmg",
    ".upload.dmg.upload",
}
STAGE_CLEANUP_PREFIX = ".cleanup-"

SHA40_RE = re.compile(r"[0-9a-f]{40}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
TEAM_RE = re.compile(r"[A-Z0-9]{10}")
VERSION_RE = re.compile(r"[0-9]+(?:\.[0-9]+){1,3}")
BUILD_RE = re.compile(r"[0-9]+(?:\.[0-9]+){0,2}")
BUNDLE_RE = re.compile(r"[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)+")
MIN_OS_RE = re.compile(r"[0-9]+(?:\.[0-9]+){1,2}")
UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    re.IGNORECASE,
)
LOCK_TOKEN_RE = re.compile(r"[A-Za-z0-9._:-]{16,200}")
MAC_LEASE_TOKEN_RE = re.compile(
    r"mac-[0-9a-f]{16}-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)
RFC3339_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"
)
ARCHITECTURES = {"arm64", "x86_64"}
RECEIPT_FIELDS = {
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
PUBLIC_FIELDS = {
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
JOURNAL_FIELDS = {
    "schema_version",
    "operation",
    "phase",
    "old_receipt",
    "old_previous",
    "old_current",
    "old_stable",
    "new_receipt",
}
JOURNAL_PHASES = {
    "prepared",
    "previous",
    "receipt",
    "stable",
    "current",
    "committed",
    "recovering",
}


class PublishError(RuntimeError):
    """A release invariant failed before publication completed."""


def fail(message: str) -> None:
    raise PublishError(message)


def _json_object(raw: bytes, *, description: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                fail(f"duplicate {description} field: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: fail(
                f"invalid {description} JSON constant: {value}"
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"invalid {description} JSON: {exc}")
    if not isinstance(value, dict):
        fail(f"{description} must be a JSON object")
    return value


def _encoded(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")


def _bytes_field(raw: bytes | None) -> str | None:
    return None if raw is None else raw.decode("utf-8", errors="strict")


def _journal_payload(
    *,
    operation: str,
    phase: str,
    old_receipt: bytes | None,
    old_previous: bytes | None,
    old_current: bytes | None,
    old_stable: dict[str, object] | None,
    new_receipt: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "operation": operation,
        "phase": phase,
        "old_receipt": _bytes_field(old_receipt),
        "old_previous": _bytes_field(old_previous),
        "old_current": _bytes_field(old_current),
        "old_stable": old_stable,
        "new_receipt": new_receipt,
    }


def _validate_journal(value: dict[str, Any], *, asset_root: Path) -> dict[str, Any]:
    if set(value) != JOURNAL_FIELDS:
        fail("invalid Mac release transaction journal fields")
    if value["schema_version"] != 1 or isinstance(value["schema_version"], bool):
        fail("invalid Mac release transaction journal schema")
    if value["operation"] not in {"publish", "rollback"}:
        fail("invalid Mac release transaction journal operation")
    if value["phase"] not in JOURNAL_PHASES:
        fail("invalid Mac release transaction journal phase")
    for field in ("old_receipt", "old_previous", "old_current"):
        raw = value[field]
        if raw is not None and (not isinstance(raw, str) or len(raw.encode()) > MAX_RECEIPT_BYTES):
            fail(f"invalid Mac release transaction journal {field}")
    stable = value["old_stable"]
    if stable is not None:
        if set(stable) != {"kind", "sha256", "size"} or stable["kind"] not in {
            "receipt",
            "legacy-backup",
            "missing",
        }:
            fail("invalid Mac release transaction journal stable state")
        if (
            not isinstance(stable["sha256"], str)
            or SHA256_RE.fullmatch(stable["sha256"]) is None
            or isinstance(stable["size"], bool)
            or not isinstance(stable["size"], int)
            or not (0 < stable["size"] <= MAX_ARTIFACT_BYTES)
        ):
            fail("invalid Mac release transaction journal stable proof")
    _validate_receipt(value["new_receipt"], asset_root=asset_root)
    return value


def _write_journal(
    state_fd: int,
    journal: dict[str, Any],
    *,
    uid: int,
    gid: int,
) -> None:
    encoded = _encoded(journal)
    if len(encoded) > MAX_JOURNAL_BYTES:
        fail("Mac release transaction journal is oversized")
    _atomic_write(
        state_fd,
        JOURNAL_NAME,
        encoded,
        mode=0o600,
        uid=uid,
        gid=gid,
    )


def _read_journal(
    state_fd: int,
    *,
    asset_root: Path,
    uid: int,
    gid: int,
) -> dict[str, Any] | None:
    raw = _read_named_file(
        state_fd,
        JOURNAL_NAME,
        mode=0o600,
        uid=uid,
        gid=gid,
        maximum=MAX_JOURNAL_BYTES,
        missing_ok=True,
    )
    if raw is None:
        return None
    return _validate_journal(
        _json_object(raw, description="Mac release transaction journal"),
        asset_root=asset_root,
    )


def _absolute_path(raw: str, *, description: str) -> Path:
    path = Path(raw)
    components = raw.split("/")[1:] if raw.startswith("/") else []
    if (
        not path.is_absolute()
        or raw == "/"
        or any(component in {"", ".", ".."} for component in components)
        or str(path) != raw
    ):
        fail(f"{description} must be a canonical non-root absolute path")
    return path


def _require_safe_directory(
    path: Path,
    *,
    mode: int,
    uid: int,
    gid: int,
) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        fail(f"required release directory is missing: {path}")
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != mode
        or metadata.st_uid != uid
        or metadata.st_gid != gid
    ):
        fail(f"unsafe release directory: {path}")


def _mkdir_checked(path: Path, *, mode: int, uid: int, gid: int) -> None:
    try:
        path.mkdir(mode=mode)
    except FileExistsError:
        pass
    _require_safe_directory(path, mode=mode, uid=uid, gid=gid)


def _open_directory(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(path, flags)
    except OSError as exc:
        fail(f"cannot safely open release directory {path}: {exc}")


def _read_named_file(
    directory_fd: int,
    name: str,
    *,
    mode: int,
    uid: int,
    gid: int,
    maximum: int,
    missing_ok: bool,
) -> bytes | None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except FileNotFoundError:
        if missing_ok:
            return None
        fail(f"required release file is missing: {name}")
    except OSError as exc:
        fail(f"cannot safely open release file {name}: {exc}")
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != mode
            or metadata.st_uid != uid
            or metadata.st_gid != gid
            or metadata.st_nlink != 1
            or metadata.st_size <= 0
            or metadata.st_size > maximum
        ):
            fail(f"unsafe release file: {name}")
        raw = os.read(descriptor, maximum + 1)
        if len(raw) > maximum or os.read(descriptor, 1):
            fail(f"oversized release file: {name}")
        after = os.fstat(descriptor)
        if (
            after.st_dev != metadata.st_dev
            or after.st_ino != metadata.st_ino
            or after.st_size != metadata.st_size
            or after.st_mtime_ns != metadata.st_mtime_ns
        ):
            fail(f"release file changed while reading: {name}")
        return raw
    finally:
        os.close(descriptor)


def _verify_named_artifact(
    directory_fd: int,
    name: str,
    *,
    expected_digest: str,
    expected_size: int,
    uid: int,
    gid: int,
    description: str,
) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        fail(f"cannot open {description}: {exc}")
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o644
            or metadata.st_uid != uid
            or metadata.st_gid != gid
            or metadata.st_nlink != 1
            or metadata.st_size != expected_size
            or metadata.st_size <= 0
            or metadata.st_size > MAX_ARTIFACT_BYTES
        ):
            fail(f"unsafe or mismatched {description}")
        digest = hashlib.sha256()
        observed_size = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            observed_size += len(chunk)
            if observed_size > expected_size:
                fail(f"oversized {description}")
            digest.update(chunk)
        after = os.fstat(descriptor)
        if (
            observed_size != expected_size
            or digest.hexdigest() != expected_digest
            or after.st_dev != metadata.st_dev
            or after.st_ino != metadata.st_ino
            or after.st_size != metadata.st_size
            or after.st_mtime_ns != metadata.st_mtime_ns
        ):
            fail(f"immutable {description} verification failed")
    finally:
        os.close(descriptor)


def _inspect_named_artifact(
    directory_fd: int,
    name: str,
    *,
    uid: int,
    gid: int,
    description: str,
) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        fail(f"cannot open {description}: {exc}")
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o644
            or metadata.st_uid != uid
            or metadata.st_gid != gid
            or metadata.st_nlink != 1
            or metadata.st_size <= 0
            or metadata.st_size > MAX_ARTIFACT_BYTES
        ):
            fail(f"unsafe {description}")
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_ARTIFACT_BYTES:
                fail(f"oversized {description}")
            digest.update(chunk)
        after = os.fstat(descriptor)
        if (
            size != metadata.st_size
            or after.st_dev != metadata.st_dev
            or after.st_ino != metadata.st_ino
            or after.st_size != metadata.st_size
            or after.st_mtime_ns != metadata.st_mtime_ns
        ):
            fail(f"{description} changed while reading")
        return digest.hexdigest(), size
    finally:
        os.close(descriptor)


def _atomic_write(
    directory_fd: int,
    name: str,
    content: bytes,
    *,
    mode: int,
    uid: int,
    gid: int,
) -> None:
    temporary = f".{name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                fail(f"short write for release pointer: {name}")
            offset += written
        os.fchmod(descriptor, mode)
        if os.fstat(descriptor).st_uid != uid or os.fstat(descriptor).st_gid != gid:
            os.fchown(descriptor, uid, gid)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(
            temporary,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def _atomic_copy_descriptor(
    source_fd: int,
    destination_fd: int,
    name: str,
    *,
    mode: int,
    uid: int,
    gid: int,
    expected_digest: str,
    expected_size: int,
) -> None:
    temporary = f".{name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    output_fd = -1
    try:
        output_fd = os.open(temporary, flags, 0o600, dir_fd=destination_fd)
        os.lseek(source_fd, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > expected_size:
                fail(f"oversized stable release copy: {name}")
            digest.update(chunk)
            offset = 0
            while offset < len(chunk):
                written = os.write(output_fd, chunk[offset:])
                if written <= 0:
                    fail(f"short stable release copy: {name}")
                offset += written
        if size != expected_size or digest.hexdigest() != expected_digest:
            fail(f"stable release input changed while copying: {name}")
        os.fchmod(output_fd, mode)
        if os.fstat(output_fd).st_uid != uid or os.fstat(output_fd).st_gid != gid:
            os.fchown(output_fd, uid, gid)
        os.fsync(output_fd)
        os.close(output_fd)
        output_fd = -1
        os.replace(
            temporary,
            name,
            src_dir_fd=destination_fd,
            dst_dir_fd=destination_fd,
        )
        os.fsync(destination_fd)
        _verify_named_artifact(
            destination_fd,
            name,
            expected_digest=expected_digest,
            expected_size=expected_size,
            uid=uid,
            gid=gid,
            description="stable DMG",
        )
    finally:
        if output_fd >= 0:
            os.close(output_fd)
        try:
            os.unlink(temporary, dir_fd=destination_fd)
        except FileNotFoundError:
            pass


def _copy_named_to_pointer(
    source_directory_fd: int,
    source_name: str,
    destination_fd: int,
    destination_name: str,
    *,
    uid: int,
    gid: int,
    expected_digest: str,
    expected_size: int,
) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    source_fd = os.open(source_name, flags, dir_fd=source_directory_fd)
    try:
        _atomic_copy_descriptor(
            source_fd,
            destination_fd,
            destination_name,
            mode=0o644,
            uid=uid,
            gid=gid,
            expected_digest=expected_digest,
            expected_size=expected_size,
        )
    finally:
        os.close(source_fd)


def _remove_pointer(directory_fd: int, name: str) -> None:
    try:
        os.unlink(name, dir_fd=directory_fd)
    except FileNotFoundError:
        return
    os.fsync(directory_fd)


def _restore_pointer(
    directory_fd: int,
    name: str,
    old: bytes | None,
    *,
    mode: int,
    uid: int,
    gid: int,
) -> None:
    if old is None:
        _remove_pointer(directory_fd, name)
    else:
        _atomic_write(
            directory_fd,
            name,
            old,
            mode=mode,
            uid=uid,
            gid=gid,
        )


def _restore_stable(
    asset_fd: int,
    old_receipt: dict[str, Any] | None,
    *,
    asset_root: Path,
    uid: int,
    gid: int,
) -> None:
    if old_receipt is None:
        _remove_pointer(asset_fd, STABLE_NAME)
        return
    source_root = asset_root / "mac/releases" / old_receipt["source_sha"]
    source_fd = _open_directory(source_root)
    try:
        _copy_named_to_pointer(
            source_fd,
            f"{old_receipt['artifact_sha256']}.dmg",
            asset_fd,
            STABLE_NAME,
            uid=uid,
            gid=gid,
            expected_digest=old_receipt["artifact_sha256"],
            expected_size=old_receipt["artifact_size"],
        )
    finally:
        os.close(source_fd)


def _validate_receipt(
    value: dict[str, Any],
    *,
    asset_root: Path,
) -> dict[str, Any]:
    if set(value) != RECEIPT_FIELDS:
        missing = sorted(RECEIPT_FIELDS - set(value))
        extra = sorted(set(value) - RECEIPT_FIELDS)
        fail(f"invalid receipt fields missing={missing} extra={extra}")
    if value["schema_version"] != 1 or isinstance(value["schema_version"], bool):
        fail("invalid receipt schema_version")
    for field, pattern in (
        ("source_sha", SHA40_RE),
        ("source_tree", SHA40_RE),
        ("artifact_sha256", SHA256_RE),
        ("bundle_id", BUNDLE_RE),
        ("version", VERSION_RE),
        ("build", BUILD_RE),
        ("team_id", TEAM_RE),
        ("cdhash", SHA40_RE),
        ("min_os", MIN_OS_RE),
        ("notary_submission_id", UUID_RE),
        ("published_at", RFC3339_RE),
    ):
        field_value = value[field]
        if not isinstance(field_value, str) or pattern.fullmatch(field_value) is None:
            fail(f"invalid receipt {field}")
    size = value["artifact_size"]
    if isinstance(size, bool) or not isinstance(size, int) or not (0 < size <= MAX_ARTIFACT_BYTES):
        fail("invalid receipt artifact_size")
    architectures = value["architectures"]
    if (
        not isinstance(architectures, list)
        or not architectures
        or any(not isinstance(item, str) for item in architectures)
        or architectures != sorted(set(architectures))
        or not set(architectures).issubset(ARCHITECTURES)
    ):
        fail("invalid receipt architectures")
    if value["notary_status"] != "Accepted":
        fail("notary status is not Accepted")
    if value["stapled"] is not True:
        fail("release receipt does not prove a stapled DMG")
    if value["bundle_id"] != EXPECTED_BUNDLE_ID:
        fail("receipt bundle_id is not the production identifier")
    if value["team_id"] != EXPECTED_TEAM_ID:
        fail("receipt team_id is not the production Developer Team")

    expected_path = (
        asset_root
        / "mac"
        / "releases"
        / value["source_sha"]
        / f"{value['artifact_sha256']}.dmg"
    )
    if value["artifact_path"] != str(expected_path):
        fail("receipt artifact_path does not match the immutable release key")
    expected_url_suffix = (
        f"/mac/releases/{value['source_sha']}/{value['artifact_sha256']}.dmg"
    )
    artifact_url = value["artifact_url"]
    if (
        not isinstance(artifact_url, str)
        or artifact_url != f"https://health.executor.life{expected_url_suffix}"
    ):
        fail("receipt artifact_url does not match the immutable release key")
    return value


def _public_manifest(receipt: dict[str, Any]) -> dict[str, Any]:
    return {key: receipt[key] for key in sorted(PUBLIC_FIELDS)}


def _validate_public_manifest(
    value: dict[str, Any], *, receipt: dict[str, Any]
) -> dict[str, Any]:
    if set(value) != PUBLIC_FIELDS:
        fail("invalid public current manifest fields")
    expected = _public_manifest(receipt)
    if value != expected:
        fail("public current manifest does not match private receipt")
    return value


def _numeric_version(value: str, *, width: int) -> tuple[int, ...]:
    parts = tuple(int(part) for part in value.split("."))
    return parts + (0,) * (width - len(parts))


def _require_forward_release(
    old: dict[str, Any],
    new: dict[str, Any],
) -> bool:
    """Return False for an exact idempotent retry; reject identity regression."""
    if old == new:
        return False
    old_version = _numeric_version(old["version"], width=4)
    new_version = _numeric_version(new["version"], width=4)
    if new_version < old_version:
        fail("Mac release version must not regress")
    if new_version == old_version:
        old_build = _numeric_version(old["build"], width=3)
        new_build = _numeric_version(new["build"], width=3)
        if new_build < old_build:
            fail("Mac release build must not regress within a version")
        if new_build == old_build:
            fail("Mac release version/build identity cannot name different bytes")
    return True


def _load_candidate(path: Path, *, uid: int, gid: int) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        fail(f"cannot safely open candidate receipt: {exc}")
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != uid
            or metadata.st_gid != gid
            or metadata.st_nlink != 1
            or metadata.st_size <= 0
            or metadata.st_size > MAX_RECEIPT_BYTES
        ):
            fail("unsafe candidate receipt")
        raw = os.read(descriptor, MAX_RECEIPT_BYTES + 1)
        if len(raw) > MAX_RECEIPT_BYTES or os.read(descriptor, 1):
            fail("oversized candidate receipt")
        after = os.fstat(descriptor)
        if (
            after.st_dev != metadata.st_dev
            or after.st_ino != metadata.st_ino
            or after.st_size != metadata.st_size
            or after.st_mtime_ns != metadata.st_mtime_ns
        ):
            fail("candidate receipt changed while reading")
        return _json_object(raw, description="candidate receipt")
    finally:
        os.close(descriptor)


def _open_validated_upload(
    path: Path, *, uid: int, gid: int
) -> tuple[int, str, int]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        fail(f"cannot safely open staged DMG: {exc}")
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != uid
            or metadata.st_gid != gid
            or metadata.st_nlink != 1
            or metadata.st_size <= 0
            or metadata.st_size > MAX_ARTIFACT_BYTES
        ):
            fail("unsafe staged DMG")
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_ARTIFACT_BYTES:
                fail("DMG exceeds the maximum release artifact size")
            digest.update(chunk)
        after = os.fstat(descriptor)
        if (
            after.st_dev != metadata.st_dev
            or after.st_ino != metadata.st_ino
            or after.st_size != metadata.st_size
            or after.st_mtime_ns != metadata.st_mtime_ns
            or size != metadata.st_size
        ):
            fail("staged DMG changed while hashing")
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor, digest.hexdigest(), size
    except BaseException:
        os.close(descriptor)
        raise


def _install_immutable(
    artifact_fd: int,
    receipt: dict[str, Any],
    *,
    asset_root: Path,
    uid: int,
    gid: int,
) -> Path:
    mac_root = asset_root / "mac"
    releases_root = mac_root / "releases"
    source_root = releases_root / receipt["source_sha"]
    _mkdir_checked(mac_root, mode=0o755, uid=uid, gid=gid)
    _mkdir_checked(releases_root, mode=0o755, uid=uid, gid=gid)
    _mkdir_checked(source_root, mode=0o755, uid=uid, gid=gid)
    directory_fd = _open_directory(source_root)
    final_name = f"{receipt['artifact_sha256']}.dmg"
    try:
        try:
            os.stat(final_name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            exists = False
        else:
            exists = True
        if exists:
            _verify_named_artifact(
                directory_fd,
                final_name,
                expected_digest=receipt["artifact_sha256"],
                expected_size=receipt["artifact_size"],
                uid=uid,
                gid=gid,
                description="DMG path",
            )
            return source_root / final_name

        temporary = f".{final_name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        output_fd = os.open(temporary, flags, 0o600, dir_fd=directory_fd)
        try:
            os.lseek(artifact_fd, 0, os.SEEK_SET)
            while True:
                chunk = os.read(artifact_fd, 1024 * 1024)
                if not chunk:
                    break
                offset = 0
                while offset < len(chunk):
                    written = os.write(output_fd, chunk[offset:])
                    if written <= 0:
                        fail("short immutable DMG write")
                    offset += written
            os.fchmod(output_fd, 0o644)
            if os.fstat(output_fd).st_uid != uid or os.fstat(output_fd).st_gid != gid:
                os.fchown(output_fd, uid, gid)
            os.fsync(output_fd)
        finally:
            os.close(output_fd)
        try:
            os.link(
                temporary,
                final_name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            pass
        finally:
            os.unlink(temporary, dir_fd=directory_fd)
        os.fsync(directory_fd)
        _verify_named_artifact(
            directory_fd,
            final_name,
            expected_digest=receipt["artifact_sha256"],
            expected_size=receipt["artifact_size"],
            uid=uid,
            gid=gid,
            description="DMG",
        )
        return source_root / final_name
    finally:
        os.close(directory_fd)


def _verify_immutable_receipt(
    receipt: dict[str, Any],
    *,
    asset_root: Path,
    uid: int,
    gid: int,
    description: str,
) -> None:
    source_root = asset_root / "mac/releases" / receipt["source_sha"]
    _require_safe_directory(asset_root / "mac", mode=0o755, uid=uid, gid=gid)
    _require_safe_directory(
        asset_root / "mac/releases", mode=0o755, uid=uid, gid=gid
    )
    _require_safe_directory(source_root, mode=0o755, uid=uid, gid=gid)
    descriptor = _open_directory(source_root)
    try:
        _verify_named_artifact(
            descriptor,
            f"{receipt['artifact_sha256']}.dmg",
            expected_digest=receipt["artifact_sha256"],
            expected_size=receipt["artifact_size"],
            uid=uid,
            gid=gid,
            description=description,
        )
    finally:
        os.close(descriptor)


def _open_lock(state_fd: int, *, uid: int, gid: int) -> int:
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(LOCK_NAME, flags, 0o600, dir_fd=state_fd)
    except OSError as exc:
        fail(f"cannot open Mac release lock: {exc}")
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != uid
        or metadata.st_gid != gid
        or metadata.st_nlink != 1
    ):
        os.close(descriptor)
        fail("unsafe Mac release lock")
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(descriptor)
        fail("another Mac release is already publishing")
    return descriptor


ReleaseAuthority = Optional[Tuple[Path, str]]


def _assert_release_authority(
    authority: ReleaseAuthority,
    *,
    uid: int,
    gid: int,
    point: str,
    test_mode: bool,
) -> None:
    if authority is None:
        if not test_mode:
            fail("production Mac mutation requires the unified remote release lock")
        if os.environ.get("MAC_RELEASE_DROP_LOCK_AT_FOR_TESTS"):
            fail("release lock loss injection requires an explicit lock")
        return
    lock_dir, expected_token = authority
    requested = os.environ.get("MAC_RELEASE_DROP_LOCK_AT_FOR_TESTS")
    if requested and not test_mode:
        fail("release lock loss injection requires explicit test mode")
    _require_safe_directory(lock_dir, mode=0o700, uid=uid, gid=gid)
    lock_fd = _open_directory(lock_dir)
    try:
        if test_mode and requested == point:
            _remove_pointer(lock_fd, "token")
        try:
            token = _read_named_file(
                lock_fd,
                "token",
                mode=0o600,
                uid=uid,
                gid=gid,
                maximum=512,
                missing_ok=False,
            )
        except PublishError as exc:
            fail(f"unified remote release lock is invalid or lost: {exc}")
        if not hmac.compare_digest(token or b"", (expected_token + "\n").encode()):
            fail("unified remote release lock token does not match")
    finally:
        os.close(lock_fd)


def _release_authority_from_args(
    args: argparse.Namespace,
    *,
    uid: int,
    gid: int,
    test_mode: bool,
) -> ReleaseAuthority:
    raw_dir = getattr(args, "release_lock_dir", None)
    token = getattr(args, "release_lock_token", None)
    if bool(raw_dir) != bool(token):
        fail("unified remote release lock directory and token must be provided together")
    if not raw_dir:
        if not test_mode:
            fail("production Mac mutation requires the unified remote release lock")
        return None
    lock_dir = _absolute_path(raw_dir, description="release lock directory")
    if not test_mode and lock_dir != EXPECTED_RELEASE_LOCK_DIR:
        fail(
            "production Mac mutation requires "
            "/var/lib/health-app/release-state/deploy.lock"
        )
    if not isinstance(token, str) or LOCK_TOKEN_RE.fullmatch(token) is None:
        fail("invalid unified remote release lock token")
    authority: ReleaseAuthority = (lock_dir, token)
    _assert_release_authority(
        authority,
        uid=uid,
        gid=gid,
        point="entry",
        test_mode=test_mode,
    )
    return authority


def _inject_failure(point: str, *, test_mode: bool) -> None:
    requested = os.environ.get("MAC_RELEASE_FAIL_AT_FOR_TESTS")
    if requested and not test_mode:
        fail("failure injection requires explicit test mode")
    if test_mode and requested == point:
        fail(f"injected release failure at {point}")


def _inject_crash(point: str, *, test_mode: bool) -> None:
    requested = os.environ.get("MAC_RELEASE_CRASH_AT_FOR_TESTS")
    if requested and not test_mode:
        fail("crash injection requires explicit test mode")
    if test_mode and requested == point:
        os._exit(86)


def _protocol_test_mode(args: argparse.Namespace) -> tuple[bool, int, int]:
    explicit = os.environ.get("MAC_RELEASE_TEST_MODE") == "1"
    bypass = bool(getattr(args, "allow_non_root_for_tests", False))
    if not bypass or not explicit:
        fail("non-root protocol bypass requires explicit test mode")
    if os.geteuid() == 0:
        fail("Mac release protocol tests require a non-root identity")
    if not _isolated_non_root_cli_test(args):
        fail("Mac release protocol tests require fixed non-production roots")
    return True, os.geteuid(), os.getegid()


def _inject_protocol_crash(point: str, *, test_mode: bool) -> None:
    requested = os.environ.get("MAC_RELEASE_PROTOCOL_CRASH_AT_FOR_TESTS")
    if requested and not test_mode:
        fail("release protocol crash injection requires explicit test mode")
    if test_mode and requested == point:
        os._exit(87)


def _require_owned_directory(path: Path, *, uid: int, gid: int) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        fail(f"required protocol directory is missing: {path}")
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != uid
        or metadata.st_gid != gid
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        fail(f"unsafe protocol directory: {path}")


def _read_protocol_file(
    path: Path,
    *,
    uid: int,
    gid: int,
    modes: set[int],
    maximum: int,
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        fail(f"cannot safely open protocol file {path}: {exc}")
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) not in modes
            or before.st_uid != uid
            or before.st_gid != gid
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > maximum
        ):
            fail(f"unsafe protocol file: {path}")
        raw = os.read(descriptor, maximum + 1)
        if len(raw) > maximum or os.read(descriptor, 1):
            fail(f"oversized protocol file: {path}")
        after = os.fstat(descriptor)
        if (
            after.st_dev != before.st_dev
            or after.st_ino != before.st_ino
            or after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
        ):
            fail(f"protocol file changed while reading: {path}")
        return raw
    finally:
        os.close(descriptor)


def _write_protocol_file(
    path: Path,
    raw: bytes,
    *,
    uid: int,
    gid: int,
    mode: int = 0o600,
) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                fail(f"short protocol write: {path}")
            offset += written
        os.fchmod(descriptor, mode)
        metadata = os.fstat(descriptor)
        if metadata.st_uid != uid or metadata.st_gid != gid:
            os.fchown(descriptor, uid, gid)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = _open_directory(path)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _rename_noreplace(source: Path, destination: Path, *, test_mode: bool) -> None:
    """Atomically rename without replacing an existing lease.

    Production is Linux and requires renameat2(RENAME_NOREPLACE).  Darwin is
    used only by the isolated test harness, where the checked fallback is safe
    because the tests do not race another process.
    """

    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            fail("renameat2 is required for atomic release lease acquisition")
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(
            -100,
            os.fsencode(source),
            -100,
            os.fsencode(destination),
            1,
        )
        if result != 0:
            error = ctypes.get_errno()
            if error in {errno.EEXIST, errno.ENOTEMPTY}:
                raise FileExistsError(destination)
            fail(f"atomic release lease rename failed: {os.strerror(error)}")
        return
    if not test_mode:
        fail("production release lease acquisition requires Linux renameat2")
    if os.path.lexists(destination):
        raise FileExistsError(destination)
    os.rename(source, destination)


def _lease_expected(args: argparse.Namespace) -> tuple[Path, Path, Path, dict[str, str]]:
    lock_dir = _absolute_path(args.lock_dir, description="release lease path")
    asset_root = _absolute_path(args.asset_root, description="asset root")
    state_root = _absolute_path(args.state_root, description="state root")
    token = args.token
    operation = args.operation
    stage_kind = args.stage_kind
    stage = args.stage
    source_sha = args.source_sha
    source_tree = args.source_tree
    helper_sha256 = args.helper_sha256
    artifact_sha256 = args.artifact_sha256
    artifact_size = str(args.artifact_size)
    candidate_sha256 = args.candidate_sha256
    if not isinstance(token, str) or MAC_LEASE_TOKEN_RE.fullmatch(token) is None:
        fail("invalid Mac release lease token")
    if operation not in LEASE_OPERATIONS:
        fail("invalid Mac release lease operation")
    if stage_kind not in LEASE_STAGE_KINDS:
        fail("invalid Mac release lease stage kind")
    if not isinstance(source_sha, str) or SHA40_RE.fullmatch(source_sha) is None:
        fail("invalid Mac release lease source SHA")
    if not isinstance(source_tree, str) or SHA40_RE.fullmatch(source_tree) is None:
        fail("invalid Mac release lease source tree")
    if not isinstance(helper_sha256, str) or SHA256_RE.fullmatch(helper_sha256) is None:
        fail("invalid Mac release lease helper hash")
    expected_stage = asset_root / "mac/.staging" / token
    if stage != str(expected_stage):
        fail("invalid Mac release lease stage path")
    if stage_kind == "publish":
        if SHA256_RE.fullmatch(artifact_sha256 or "") is None:
            fail("invalid Mac release lease artifact hash")
        if not re.fullmatch(r"[1-9][0-9]{0,9}", artifact_size):
            fail("invalid Mac release lease artifact size")
        if int(artifact_size) > MAX_ARTIFACT_BYTES:
            fail("oversized Mac release lease artifact")
        if SHA256_RE.fullmatch(candidate_sha256 or "") is None:
            fail("invalid Mac release lease candidate hash")
    elif (artifact_sha256, artifact_size, candidate_sha256) != ("-", "0", "-"):
        fail("maintenance Mac lease cannot carry publish artifact identity")
    expected = {
        "artifact_sha256": artifact_sha256,
        "artifact_size": artifact_size,
        "candidate_sha256": candidate_sha256,
        "helper_sha256": helper_sha256,
        "label": LEASE_LABEL,
        "operation": operation,
        "source_sha": source_sha,
        "source_tree": source_tree,
        "stage": stage,
        "stage_kind": stage_kind,
        "token": token,
    }
    return lock_dir, asset_root, state_root, expected


def _validate_lease_directory(
    path: Path,
    expected: dict[str, str],
    *,
    uid: int,
    gid: int,
    exact: bool,
    expected_phase: str | None = None,
) -> str | None:
    _require_safe_directory(path, mode=0o700, uid=uid, gid=gid)
    names = set(os.listdir(path))
    allowed = set(LEASE_FIELDS)
    if not names.issubset(allowed) or (exact and names != allowed):
        fail(f"unexpected Mac release lease entries: {sorted(names - allowed)}")
    values: dict[str, str] = {}
    for name in sorted(names):
        raw = _read_protocol_file(
            path / name,
            uid=uid,
            gid=gid,
            modes={0o600},
            maximum=4096,
        )
        try:
            value = raw.decode("utf-8", errors="strict")
        except UnicodeError as exc:
            fail(f"invalid Mac release lease field {name}: {exc}")
        if not value.endswith("\n") or value.count("\n") != 1:
            fail(f"invalid Mac release lease field encoding: {name}")
        values[name] = value[:-1]
    for name, value in expected.items():
        if name in values and values[name] != value:
            fail(f"Mac release lease {name} does not match the retained handoff")
    phase = values.get("phase")
    if phase is not None and phase not in LEASE_PHASES:
        fail("invalid Mac release lease phase")
    if expected_phase is not None and phase is not None and phase != expected_phase:
        fail("Mac release lease phase does not match")
    started_at = values.get("started_at")
    if started_at is not None and RFC3339_RE.fullmatch(started_at) is None:
        fail("invalid Mac release lease start time")
    return phase


def _safe_unlink_protocol_directory(
    path: Path,
    expected: dict[str, str],
    *,
    uid: int,
    gid: int,
    test_mode: bool,
    crash_prefix: str | None = None,
    expected_phase: str | None = None,
) -> None:
    _validate_lease_directory(
        path,
        expected,
        uid=uid,
        gid=gid,
        exact=False,
        expected_phase=expected_phase,
    )
    for name in LEASE_FIELDS:
        target = path / name
        try:
            target.unlink()
        except FileNotFoundError:
            continue
        _fsync_directory(path)
        if crash_prefix:
            _inject_protocol_crash(
                f"{crash_prefix}-after-remove-{name}", test_mode=test_mode
            )
    path.rmdir()
    _fsync_directory(path.parent)


def _scan_lease_residuals(lock_dir: Path, token: str) -> dict[str, Path]:
    parent = lock_dir.parent
    own = {
        "creating": parent / f".{lock_dir.name}.mac-creating-{token}",
        "releasing": parent / f".{lock_dir.name}.mac-releasing-{token}",
        "phase": parent / f".{lock_dir.name}.mac-phase-{token}",
    }
    # This deliberately scans the whole shared sibling namespace.  Generic
    # deploy residues (.deploy.lock.alloc/state/released-*) and Mac residues
    # for another token are both foreign authority and therefore block Mac
    # acquisition.  A detached canonical lease must never look free to the
    # other publisher implementation.
    prefix = f".{lock_dir.name}."
    for name in os.listdir(parent):
        if not name.startswith(prefix):
            continue
        path = parent / name
        if path not in own.values():
            fail(
                "foreign Mac release lease residue requires its retained "
                f"handoff before acquisition: {name}"
            )
    return own


def _stage_cleanup_tombstone(asset_root: Path, token: str) -> Path:
    return asset_root / "mac/.staging" / f"{STAGE_CLEANUP_PREFIX}{token}"


def _validate_stage_cleanup_proof(
    cleanup: Path,
    expected: dict[str, str],
    *,
    uid: int,
    gid: int,
    partial: bool,
) -> None:
    _require_safe_directory(cleanup, mode=0o700, uid=uid, gid=gid)
    names = set(os.listdir(cleanup))
    required = {"mac_release_publish.py"}
    if expected["stage_kind"] == "publish":
        required |= {"candidate.json", "upload.dmg"}
    allowed = REMOTE_STAGE_FILES if partial else required
    if not names.issubset(allowed):
        fail("unexpected Mac release stage cleanup residue")
    for name in names:
        _validate_stage_entry(
            cleanup / name,
            name,
            expected,
            uid=uid,
            gid=gid,
            partial=partial,
        )


def _assert_publisher_idle(state_root: Path, *, uid: int, gid: int) -> None:
    path = state_root / LOCK_NAME
    if not os.path.lexists(path):
        return
    flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != uid
            or metadata.st_gid != gid
            or metadata.st_nlink != 1
            or metadata.st_size > 4096
        ):
            fail("unsafe retained Mac publisher lock")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("retained Mac publisher is still active")
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        os.close(descriptor)


def _validate_stage_entry(
    path: Path,
    name: str,
    expected: dict[str, str],
    *,
    uid: int,
    gid: int,
    partial: bool,
) -> None:
    if name == "mac_release_publish.py":
        raw = _read_protocol_file(path, uid=uid, gid=gid, modes={0o700}, maximum=1024 * 1024)
        if hashlib.sha256(raw).hexdigest() != expected["helper_sha256"]:
            fail("staged Mac release helper hash mismatch")
        return
    if name == "candidate.json":
        raw = _read_protocol_file(path, uid=uid, gid=gid, modes={0o600}, maximum=MAX_RECEIPT_BYTES)
        if hashlib.sha256(raw).hexdigest() != expected["candidate_sha256"]:
            fail("staged Mac release candidate hash mismatch")
        return
    if name == "upload.dmg":
        raw = _read_protocol_file(path, uid=uid, gid=gid, modes={0o600}, maximum=MAX_ARTIFACT_BYTES)
        if len(raw) != int(expected["artifact_size"]) or hashlib.sha256(raw).hexdigest() != expected["artifact_sha256"]:
            fail("staged Mac release artifact mismatch")
        return
    if not partial:
        fail(f"unexpected sealed Mac release stage entry: {name}")
    maximum = 1024 * 1024 if name == ".mac_release_publish.py.upload" else (
        MAX_RECEIPT_BYTES if name == ".candidate.json.upload" else MAX_ARTIFACT_BYTES
    )
    _read_protocol_file(path, uid=uid, gid=gid, modes={0o600, 0o644}, maximum=maximum)


def _validate_remote_stage(
    asset_root: Path,
    expected: dict[str, str],
    *,
    uid: int,
    gid: int,
    exact: bool,
) -> None:
    mac_root = asset_root / "mac"
    staging_root = mac_root / ".staging"
    stage = Path(expected["stage"])
    _require_safe_directory(mac_root, mode=0o755, uid=uid, gid=gid)
    _require_safe_directory(staging_root, mode=0o700, uid=uid, gid=gid)
    _require_safe_directory(stage, mode=0o700, uid=uid, gid=gid)
    names = set(os.listdir(stage))
    required = {"mac_release_publish.py"}
    if expected["stage_kind"] == "publish":
        required |= {"candidate.json", "upload.dmg"}
    if exact and names != required:
        fail(f"sealed Mac release stage entries do not match: {sorted(names)}")
    if not names.issubset(REMOTE_STAGE_FILES):
        fail(f"unexpected Mac release stage entries: {sorted(names - REMOTE_STAGE_FILES)}")
    for name in sorted(names):
        _validate_stage_entry(
            stage / name,
            name,
            expected,
            uid=uid,
            gid=gid,
            partial=not exact,
        )


def _lease_context(
    args: argparse.Namespace,
) -> tuple[bool, int, int, Path, Path, Path, dict[str, str]]:
    test_mode, uid, gid = _protocol_test_mode(args)
    lock_dir, asset_root, state_root, expected = _lease_expected(args)
    _require_safe_directory(asset_root, mode=0o755, uid=uid, gid=gid)
    _require_safe_directory(state_root, mode=0o700, uid=uid, gid=gid)
    _require_owned_directory(lock_dir.parent, uid=uid, gid=gid)
    return test_mode, uid, gid, lock_dir, asset_root, state_root, expected


def lease_acquire(args: argparse.Namespace) -> dict[str, Any]:
    test_mode, uid, gid, lock_dir, asset_root, state_root, expected = _lease_context(args)
    residuals = _scan_lease_residuals(lock_dir, expected["token"])
    creating = residuals["creating"]
    releasing = residuals["releasing"]
    phase_temp = residuals["phase"]
    requested_action = args.requested_action
    if os.path.lexists(phase_temp):
        if not os.path.lexists(lock_dir):
            fail("orphaned Mac release phase transition requires operator review")
        raw = _read_protocol_file(
            phase_temp, uid=uid, gid=gid, modes={0o600}, maximum=64
        )
        pending_phase = raw.decode("ascii", errors="strict").rstrip("\n")
        if pending_phase not in LEASE_PHASES:
            fail("invalid retained Mac release phase transition")
        current_phase = _validate_lease_directory(
            lock_dir,
            expected,
            uid=uid,
            gid=gid,
            exact=True,
        )
        if current_phase == pending_phase:
            phase_temp.unlink()
            _fsync_directory(lock_dir.parent)
        elif (current_phase, pending_phase) in {
            ("staging", "sealed"),
            ("sealed", "mutating"),
        }:
            os.replace(phase_temp, lock_dir / "phase")
            _fsync_directory(lock_dir)
            _fsync_directory(lock_dir.parent)
        else:
            fail("interrupted Mac release phase transition is ambiguous")
    if os.path.lexists(releasing):
        if os.path.lexists(lock_dir) or os.path.lexists(creating):
            fail("ambiguous Mac release lease residue")
        if requested_action != "recover":
            fail("interrupted Mac release unlock requires exact recovery")
        stage = Path(expected["stage"])
        cleanup = _stage_cleanup_tombstone(asset_root, expected["token"])
        if os.path.lexists(stage):
            fail("interrupted Mac release unlock still has an active stage")
        if os.path.lexists(cleanup):
            _require_safe_directory(cleanup, mode=0o700, uid=uid, gid=gid)
            if os.listdir(cleanup):
                fail("interrupted Mac release unlock has incomplete stage cleanup")
            cleanup.rmdir()
            _fsync_directory(cleanup.parent)
        _safe_unlink_protocol_directory(
            releasing,
            expected,
            uid=uid,
            gid=gid,
            test_mode=test_mode,
        )
        return {"status": "completed", "phase": "released"}
    if os.path.lexists(creating):
        if os.path.lexists(lock_dir):
            fail("ambiguous Mac release lease creation residue")
        _safe_unlink_protocol_directory(
            creating,
            expected,
            uid=uid,
            gid=gid,
            test_mode=test_mode,
            expected_phase="staging",
        )
    if not os.path.lexists(lock_dir):
        creating.mkdir(mode=0o700)
        _fsync_directory(lock_dir.parent)
        _inject_protocol_crash("acquire-after-mkdir", test_mode=test_mode)
        values = dict(expected)
        values["phase"] = "staging"
        values["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        for name in LEASE_FIELDS:
            _write_protocol_file(
                creating / name,
                (values[name] + "\n").encode("utf-8"),
                uid=uid,
                gid=gid,
            )
            _fsync_directory(creating)
            _inject_protocol_crash(
                f"acquire-after-write-{name}", test_mode=test_mode
            )
        try:
            _rename_noreplace(creating, lock_dir, test_mode=test_mode)
        except FileExistsError:
            fail("another release acquired the unified lease")
        _fsync_directory(lock_dir.parent)
        _inject_protocol_crash("acquire-after-rename", test_mode=test_mode)
        _validate_lease_directory(
            lock_dir,
            expected,
            uid=uid,
            gid=gid,
            exact=True,
            expected_phase="staging",
        )
        return {"status": "created", "phase": "staging"}
    if requested_action not in {"recover", "rollback"}:
        fail("remote release already active")
    phase = _validate_lease_directory(
        lock_dir, expected, uid=uid, gid=gid, exact=True
    )
    cleanup = _stage_cleanup_tombstone(asset_root, expected["token"])
    stage_exists = os.path.lexists(expected["stage"])
    cleanup_exists = os.path.lexists(cleanup)
    if cleanup_exists:
        if stage_exists:
            fail("ambiguous Mac release stage cleanup state")
        _validate_stage_cleanup_proof(
            cleanup,
            expected,
            uid=uid,
            gid=gid,
            partial=phase != "mutating",
        )
    elif phase in {"sealed", "mutating"}:
        if stage_exists:
            _validate_remote_stage(asset_root, expected, uid=uid, gid=gid, exact=True)
        else:
            fail("sealed or mutating Mac release has neither a stage nor cleanup proof")
    _assert_publisher_idle(state_root, uid=uid, gid=gid)
    return {"status": "adopted", "phase": phase}


def lease_assert(args: argparse.Namespace) -> dict[str, Any]:
    _test_mode, uid, gid, lock_dir, asset_root, _state_root, expected = _lease_context(args)
    phase = args.phase
    if phase not in LEASE_PHASES:
        fail("invalid expected Mac release lease phase")
    _scan_lease_residuals(lock_dir, expected["token"])
    actual = _validate_lease_directory(
        lock_dir,
        expected,
        uid=uid,
        gid=gid,
        exact=True,
        expected_phase=phase,
    )
    cleanup = _stage_cleanup_tombstone(asset_root, expected["token"])
    stage_exists = os.path.lexists(expected["stage"])
    cleanup_exists = os.path.lexists(cleanup)
    if cleanup_exists:
        if stage_exists:
            fail("ambiguous Mac release stage cleanup state")
        _validate_stage_cleanup_proof(
            cleanup,
            expected,
            uid=uid,
            gid=gid,
            partial=actual != "mutating",
        )
    elif actual in {"sealed", "mutating"}:
        if stage_exists:
            _validate_remote_stage(asset_root, expected, uid=uid, gid=gid, exact=True)
        else:
            fail("Mac release stage and cleanup proof are both missing")
    return {"held": True, "phase": actual}


def lease_transition(args: argparse.Namespace) -> dict[str, Any]:
    test_mode, uid, gid, lock_dir, asset_root, _state_root, expected = _lease_context(args)
    old_phase = args.old_phase
    new_phase = args.new_phase
    if (old_phase, new_phase) not in {("staging", "sealed"), ("sealed", "mutating")}:
        fail("invalid Mac release lease phase transition")
    residuals = _scan_lease_residuals(lock_dir, expected["token"])
    if os.path.lexists(residuals["creating"]) or os.path.lexists(residuals["releasing"]):
        fail("Mac release lease transition has unresolved residue")
    current = _validate_lease_directory(
        lock_dir, expected, uid=uid, gid=gid, exact=True
    )
    if new_phase in {"sealed", "mutating"}:
        _validate_remote_stage(asset_root, expected, uid=uid, gid=gid, exact=True)
    temporary = residuals["phase"]
    if os.path.lexists(temporary):
        raw = _read_protocol_file(
            temporary, uid=uid, gid=gid, modes={0o600}, maximum=64
        )
        if raw != (new_phase + "\n").encode():
            fail("retained Mac release phase transition does not match")
        if current == new_phase:
            temporary.unlink()
            _fsync_directory(lock_dir.parent)
            return {"phase": new_phase, "idempotent": True}
        if current != old_phase:
            fail("Mac release phase transition residue is ambiguous")
        temporary.unlink()
        _fsync_directory(lock_dir.parent)
    if current == new_phase:
        return {"phase": new_phase, "idempotent": True}
    if current != old_phase:
        fail("Mac release lease phase changed unexpectedly")
    _write_protocol_file(
        temporary,
        (new_phase + "\n").encode(),
        uid=uid,
        gid=gid,
    )
    _fsync_directory(lock_dir.parent)
    _inject_protocol_crash("transition-after-write", test_mode=test_mode)
    os.replace(temporary, lock_dir / "phase")
    _fsync_directory(lock_dir)
    _fsync_directory(lock_dir.parent)
    _inject_protocol_crash("transition-after-replace", test_mode=test_mode)
    _validate_lease_directory(
        lock_dir,
        expected,
        uid=uid,
        gid=gid,
        exact=True,
        expected_phase=new_phase,
    )
    return {"phase": new_phase, "idempotent": False}


def lease_release(args: argparse.Namespace) -> dict[str, Any]:
    test_mode, uid, gid, lock_dir, asset_root, _state_root, expected = _lease_context(args)
    phase = args.phase
    if phase not in LEASE_PHASES:
        fail("invalid expected Mac release lease phase")
    residuals = _scan_lease_residuals(lock_dir, expected["token"])
    stage = Path(expected["stage"])
    cleanup = _stage_cleanup_tombstone(asset_root, expected["token"])
    if os.path.lexists(stage):
        fail("Mac release stage must be fully cleaned before releasing the lease")
    if os.path.lexists(cleanup):
        _require_safe_directory(cleanup, mode=0o700, uid=uid, gid=gid)
        if os.listdir(cleanup):
            fail("Mac release stage cleanup tombstone is not empty")
    tombstone = residuals["releasing"]
    if os.path.lexists(residuals["creating"]) or os.path.lexists(residuals["phase"]):
        fail("Mac release lease cannot be released with unresolved residue")
    if os.path.lexists(tombstone):
        if os.path.lexists(lock_dir):
            fail("Mac release lease release state is ambiguous")
        if os.path.lexists(cleanup):
            _require_safe_directory(cleanup, mode=0o700, uid=uid, gid=gid)
            if os.listdir(cleanup):
                fail("Mac release stage cleanup tombstone is not empty")
            cleanup.rmdir()
            _fsync_directory(cleanup.parent)
        _safe_unlink_protocol_directory(
            tombstone,
            expected,
            uid=uid,
            gid=gid,
            test_mode=test_mode,
            crash_prefix="release",
            expected_phase=phase,
        )
        return {"released": True, "resumed": True}
    _validate_lease_directory(
        lock_dir,
        expected,
        uid=uid,
        gid=gid,
        exact=True,
        expected_phase=phase,
    )
    try:
        _rename_noreplace(lock_dir, tombstone, test_mode=test_mode)
    except FileExistsError:
        fail("Mac release lease tombstone already exists")
    _fsync_directory(lock_dir.parent)
    _inject_protocol_crash("release-after-rename", test_mode=test_mode)
    if os.path.lexists(cleanup):
        cleanup.rmdir()
        _fsync_directory(cleanup.parent)
        _inject_protocol_crash("release-after-stage-proof", test_mode=test_mode)
    _safe_unlink_protocol_directory(
        tombstone,
        expected,
        uid=uid,
        gid=gid,
        test_mode=test_mode,
        crash_prefix="release",
        expected_phase=phase,
    )
    return {"released": True}


def stage_reset(args: argparse.Namespace) -> dict[str, Any]:
    _test_mode, uid, gid, lock_dir, asset_root, _state_root, expected = _lease_context(args)
    _validate_lease_directory(
        lock_dir,
        expected,
        uid=uid,
        gid=gid,
        exact=True,
        expected_phase="staging",
    )
    mac_root = asset_root / "mac"
    staging_root = mac_root / ".staging"
    cleanup = _stage_cleanup_tombstone(asset_root, expected["token"])
    if os.path.lexists(cleanup):
        fail("Mac stage reset is blocked by a retained cleanup proof")
    _mkdir_checked(mac_root, mode=0o755, uid=uid, gid=gid)
    _mkdir_checked(staging_root, mode=0o700, uid=uid, gid=gid)
    stage = Path(expected["stage"])
    if os.path.lexists(stage):
        _validate_remote_stage(asset_root, expected, uid=uid, gid=gid, exact=False)
        for name in sorted(os.listdir(stage)):
            (stage / name).unlink()
        stage.rmdir()
        _fsync_directory(staging_root)
    stage.mkdir(mode=0o700)
    _fsync_directory(staging_root)
    return {"reset": True, "stage": str(stage)}


def stage_bind_helper(args: argparse.Namespace) -> dict[str, Any]:
    _test_mode, uid, gid, lock_dir, _asset_root, _state_root, expected = _lease_context(args)
    _validate_lease_directory(
        lock_dir,
        expected,
        uid=uid,
        gid=gid,
        exact=True,
        expected_phase="staging",
    )
    stage = Path(expected["stage"])
    _require_safe_directory(stage, mode=0o700, uid=uid, gid=gid)
    uploaded = stage / ".mac_release_publish.py.upload"
    raw = _read_protocol_file(
        uploaded, uid=uid, gid=gid, modes={0o600, 0o644}, maximum=1024 * 1024
    )
    if hashlib.sha256(raw).hexdigest() != expected["helper_sha256"]:
        fail("uploaded Mac release helper hash mismatch")
    os.chmod(uploaded, 0o700, follow_symlinks=False)
    os.replace(uploaded, stage / "mac_release_publish.py")
    _fsync_directory(stage)
    _validate_stage_entry(
        stage / "mac_release_publish.py",
        "mac_release_publish.py",
        expected,
        uid=uid,
        gid=gid,
        partial=True,
    )
    return {"helper_bound": True}


def stage_bind_payload(args: argparse.Namespace) -> dict[str, Any]:
    _test_mode, uid, gid, lock_dir, _asset_root, _state_root, expected = _lease_context(args)
    if expected["stage_kind"] != "publish":
        fail("maintenance Mac release cannot bind a publish payload")
    _validate_lease_directory(
        lock_dir,
        expected,
        uid=uid,
        gid=gid,
        exact=True,
        expected_phase="staging",
    )
    stage = Path(expected["stage"])
    _require_safe_directory(stage, mode=0o700, uid=uid, gid=gid)
    pairs = (
        (".upload.dmg.upload", "upload.dmg"),
        (".candidate.json.upload", "candidate.json"),
    )
    for temporary_name, final_name in pairs:
        temporary = stage / temporary_name
        os.chmod(temporary, 0o600, follow_symlinks=False)
        _validate_stage_entry(
            temporary,
            "upload.dmg" if final_name == "upload.dmg" else "candidate.json",
            expected,
            uid=uid,
            gid=gid,
            partial=True,
        )
    for temporary_name, final_name in pairs:
        os.replace(stage / temporary_name, stage / final_name)
        _fsync_directory(stage)
    return {"payload_bound": True}


def stage_cleanup(args: argparse.Namespace) -> dict[str, Any]:
    test_mode, uid, gid, lock_dir, asset_root, _state_root, expected = _lease_context(args)
    _scan_lease_residuals(lock_dir, expected["token"])
    actual_phase = _validate_lease_directory(
        lock_dir,
        expected,
        uid=uid,
        gid=gid,
        exact=True,
    )
    if args.allow_partial_stage:
        if actual_phase not in {"staging", "sealed"}:
            fail("partial Mac stage cleanup is allowed only before mutation")
    elif actual_phase != "mutating":
        fail("final Mac stage cleanup requires a mutating lease")
    stage = Path(expected["stage"])
    mac_root = asset_root / "mac"
    staging_root = asset_root / "mac/.staging"
    cleanup = _stage_cleanup_tombstone(asset_root, expected["token"])
    if os.path.lexists(stage) and os.path.lexists(cleanup):
        fail("ambiguous Mac release stage cleanup state")
    if os.path.lexists(stage):
        _validate_remote_stage(
            asset_root,
            expected,
            uid=uid,
            gid=gid,
            exact=not args.allow_partial_stage,
        )
        _rename_noreplace(stage, cleanup, test_mode=test_mode)
        _fsync_directory(staging_root)
        _inject_protocol_crash("stage-cleanup-after-rename", test_mode=test_mode)
    elif not os.path.lexists(cleanup):
        if not args.allow_partial_stage:
            fail("Mac stage and its durable cleanup proof are both missing")
        _mkdir_checked(mac_root, mode=0o755, uid=uid, gid=gid)
        _mkdir_checked(staging_root, mode=0o700, uid=uid, gid=gid)
        cleanup.mkdir(mode=0o700)
        _fsync_directory(staging_root)
        _inject_protocol_crash("stage-cleanup-after-rename", test_mode=test_mode)
    _require_safe_directory(cleanup, mode=0o700, uid=uid, gid=gid)
    names = set(os.listdir(cleanup))
    required = {"mac_release_publish.py"}
    if expected["stage_kind"] == "publish":
        required |= {"candidate.json", "upload.dmg"}
    allowed = REMOTE_STAGE_FILES if args.allow_partial_stage else required
    if not names.issubset(allowed):
        fail(f"unexpected Mac stage cleanup entries: {sorted(names - allowed)}")
    for name in sorted(names):
        _validate_stage_entry(
            cleanup / name,
            name,
            expected,
            uid=uid,
            gid=gid,
            partial=args.allow_partial_stage,
        )
    for name in sorted(allowed):
        target = cleanup / name
        try:
            target.unlink()
        except FileNotFoundError:
            continue
        _fsync_directory(cleanup)
        _inject_protocol_crash(
            f"stage-cleanup-after-remove-{name}", test_mode=test_mode
        )
    # Keep the empty token-bound tombstone as durable proof that cleanup has
    # completed. lease-release validates and removes it atomically with lease
    # teardown, so a lost response never turns "stage missing" into ambiguity.
    _inject_protocol_crash("stage-cleanup-after-complete", test_mode=test_mode)
    return {"cleaned": True, "already_missing": False, "tombstone": str(cleanup)}


def handoff_clear(args: argparse.Namespace) -> dict[str, Any]:
    test_mode, uid, gid = _protocol_test_mode(args)
    bundle = _absolute_path(args.bundle, description="Mac recovery handoff bundle")
    token = args.token
    if not isinstance(token, str) or MAC_LEASE_TOKEN_RE.fullmatch(token) is None:
        fail("invalid Mac recovery handoff cleanup token")
    tombstone = bundle.parent / f"{bundle.name}.clearing-{token}"
    _require_owned_directory(bundle.parent, uid=uid, gid=gid)
    if os.path.lexists(bundle) and os.path.lexists(tombstone):
        fail("Mac recovery handoff cleanup state is ambiguous")
    if os.path.lexists(bundle):
        _require_safe_directory(bundle, mode=0o700, uid=uid, gid=gid)
        if set(os.listdir(bundle)) != HANDOFF_FILES:
            fail("unexpected Mac recovery handoff bundle entries")
        for name in HANDOFF_FILES:
            _read_protocol_file(
                bundle / name,
                uid=uid,
                gid=gid,
                modes={0o600},
                maximum=1024 * 1024 if name.endswith(".py") else 4096,
            )
        _rename_noreplace(bundle, tombstone, test_mode=test_mode)
        _fsync_directory(bundle.parent)
        _inject_protocol_crash("handoff-clear-after-rename", test_mode=test_mode)
    elif not os.path.lexists(tombstone):
        return {"cleared": True, "already_missing": True}
    _require_safe_directory(tombstone, mode=0o700, uid=uid, gid=gid)
    names = set(os.listdir(tombstone))
    if not names.issubset(HANDOFF_FILES):
        fail("unexpected Mac recovery cleanup tombstone entries")
    for name in sorted(names):
        _read_protocol_file(
            tombstone / name,
            uid=uid,
            gid=gid,
            modes={0o600},
            maximum=1024 * 1024 if name.endswith(".py") else 4096,
        )
    for name in ("handoff", "mac_release_publish.py"):
        target = tombstone / name
        try:
            target.unlink()
        except FileNotFoundError:
            continue
        _fsync_directory(tombstone)
        _inject_protocol_crash(
            f"handoff-clear-after-remove-{name}", test_mode=test_mode
        )
    tombstone.rmdir()
    _fsync_directory(bundle.parent)
    _inject_protocol_crash("handoff-clear-after-rmdir", test_mode=test_mode)
    return {"cleared": True, "already_missing": False}


def _journal_old_bytes(value: object, *, field: str) -> bytes | None:
    if value is None:
        return None
    if not isinstance(value, str):
        fail(f"invalid Mac release transaction journal {field}")
    return value.encode("utf-8")


def _read_optional_pointer(
    directory_fd: int,
    name: str,
    *,
    mode: int,
    uid: int,
    gid: int,
) -> bytes | None:
    return _read_named_file(
        directory_fd,
        name,
        mode=mode,
        uid=uid,
        gid=gid,
        maximum=MAX_RECEIPT_BYTES,
        missing_ok=True,
    )


def _transaction_states(
    journal: dict[str, Any],
) -> list[tuple[bytes | None, bytes | None, bytes | None, tuple[str, int] | None]]:
    old_receipt = _journal_old_bytes(journal["old_receipt"], field="old_receipt")
    old_previous = _journal_old_bytes(journal["old_previous"], field="old_previous")
    old_current = _journal_old_bytes(journal["old_current"], field="old_current")
    new_receipt = _encoded(journal["new_receipt"])
    new_current = _encoded(_public_manifest(journal["new_receipt"]))
    new_previous = old_receipt if old_receipt is not None else old_previous
    stable = journal["old_stable"]
    old_stable = (
        None
        if stable is None or stable["kind"] == "missing"
        else (stable["sha256"], stable["size"])
    )
    new_stable = (
        journal["new_receipt"]["artifact_sha256"],
        journal["new_receipt"]["artifact_size"],
    )
    return [
        (old_receipt, old_previous, old_current, old_stable),
        (old_receipt, new_previous, old_current, old_stable),
        (new_receipt, new_previous, old_current, old_stable),
        (new_receipt, new_previous, old_current, new_stable),
        (new_receipt, new_previous, new_current, new_stable),
    ]


def _allowed_transaction_states(
    journal: dict[str, Any],
) -> set[tuple[bytes | None, bytes | None, bytes | None, tuple[str, int] | None]]:
    states = _transaction_states(journal)
    if journal["phase"] == "recovering":
        return set(states)
    phase_index = {
        "prepared": 0,
        "previous": 1,
        "receipt": 2,
        "stable": 3,
        "current": 4,
        "committed": 4,
    }[journal["phase"]]
    allowed = {states[phase_index]}
    # Every phase marker is durably written after its pointer. A process can be
    # killed after the next pointer rename but before the next marker write.
    if phase_index < 4 and journal["phase"] != "committed":
        allowed.add(states[phase_index + 1])
    return allowed


def _stable_state(
    asset_fd: int,
    *,
    uid: int,
    gid: int,
) -> tuple[str, int] | None:
    try:
        os.stat(STABLE_NAME, dir_fd=asset_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    return _inspect_named_artifact(
        asset_fd,
        STABLE_NAME,
        uid=uid,
        gid=gid,
        description="stable DMG",
    )


def _recover_locked(
    *,
    state_fd: int,
    asset_root: Path,
    uid: int,
    gid: int,
    authority: ReleaseAuthority,
    test_mode: bool,
) -> dict[str, Any]:
    _assert_release_authority(
        authority,
        uid=uid,
        gid=gid,
        point="recover-entry",
        test_mode=test_mode,
    )
    journal = _read_journal(
        state_fd,
        asset_root=asset_root,
        uid=uid,
        gid=gid,
    )
    if journal is None:
        return {"recovered": False}
    current_dir = asset_root / "mac"
    _require_safe_directory(current_dir, mode=0o755, uid=uid, gid=gid)
    current_fd = _open_directory(current_dir)
    asset_fd = _open_directory(asset_root)
    try:
        actual_receipt = _read_optional_pointer(
            state_fd, RECEIPT_NAME, mode=0o600, uid=uid, gid=gid
        )
        actual_previous = _read_optional_pointer(
            state_fd, PREVIOUS_NAME, mode=0o600, uid=uid, gid=gid
        )
        actual_current = _read_optional_pointer(
            current_fd, CURRENT_RELATIVE.name, mode=0o644, uid=uid, gid=gid
        )
        actual_stable = _stable_state(asset_fd, uid=uid, gid=gid)
        new_receipt = journal["new_receipt"]
        stable = journal["old_stable"]
        actual_state = (
            actual_receipt,
            actual_previous,
            actual_current,
            actual_stable,
        )
        if actual_state not in _allowed_transaction_states(journal):
            fail(
                "unknown Mac release transaction state; reconcile manually before "
                "rerunning recovery (no files were changed)"
            )

        if journal["phase"] == "committed":
            _assert_release_authority(
                authority,
                uid=uid,
                gid=gid,
                point="recover-finalize-backup",
                test_mode=test_mode,
            )
            _remove_pointer(asset_fd, STABLE_BACKUP_NAME)
            _assert_release_authority(
                authority,
                uid=uid,
                gid=gid,
                point="recover-finalize-journal",
                test_mode=test_mode,
            )
            _remove_pointer(state_fd, JOURNAL_NAME)
            return {"recovered": True, "operation": journal["operation"], "finalized": True}

        restore_legacy_from_backup = False
        if stable is not None and stable["kind"] == "receipt":
            old_receipt = _journal_old_bytes(
                journal["old_receipt"], field="old_receipt"
            )
            if old_receipt is None:
                fail("journal cannot restore stable DMG without an old receipt")
            old_receipt_value = _validate_receipt(
                _json_object(old_receipt, description="journal old receipt"),
                asset_root=asset_root,
            )
            _verify_immutable_receipt(
                old_receipt_value,
                asset_root=asset_root,
                uid=uid,
                gid=gid,
                description="journal rollback DMG",
            )
        elif stable is not None and stable["kind"] == "legacy-backup":
            old_stable_proof = (stable["sha256"], stable["size"])
            if actual_stable != old_stable_proof:
                _verify_named_artifact(
                    asset_fd,
                    STABLE_BACKUP_NAME,
                    expected_digest=stable["sha256"],
                    expected_size=stable["size"],
                    uid=uid,
                    gid=gid,
                    description="legacy stable rollback DMG",
                )
                restore_legacy_from_backup = True

        journal["phase"] = "recovering"
        _assert_release_authority(
            authority,
            uid=uid,
            gid=gid,
            point="recover-journal",
            test_mode=test_mode,
        )
        _write_journal(state_fd, journal, uid=uid, gid=gid)
        errors: list[str] = []
        try:
            _assert_release_authority(
                authority,
                uid=uid,
                gid=gid,
                point="recover-current",
                test_mode=test_mode,
            )
            _restore_pointer(
                current_fd,
                CURRENT_RELATIVE.name,
                _journal_old_bytes(journal["old_current"], field="old_current"),
                mode=0o644,
                uid=uid,
                gid=gid,
            )
        except BaseException as exc:
            errors.append(f"{CURRENT_RELATIVE.name}: {exc}")
        if not errors:
            try:
                _assert_release_authority(
                    authority,
                    uid=uid,
                    gid=gid,
                    point="recover-stable",
                    test_mode=test_mode,
                )
                if stable is None or stable["kind"] == "missing":
                    _remove_pointer(asset_fd, STABLE_NAME)
                elif stable["kind"] == "legacy-backup":
                    if restore_legacy_from_backup:
                        os.replace(
                            STABLE_BACKUP_NAME,
                            STABLE_NAME,
                            src_dir_fd=asset_fd,
                            dst_dir_fd=asset_fd,
                        )
                        os.fsync(asset_fd)
                else:
                    _restore_stable(
                        asset_fd,
                        old_receipt_value,
                        asset_root=asset_root,
                        uid=uid,
                        gid=gid,
                    )
            except BaseException as exc:
                errors.append(f"{STABLE_NAME}: {exc}")
        if not errors:
            for descriptor, name, old, mode in (
                (
                    state_fd,
                    RECEIPT_NAME,
                    _journal_old_bytes(journal["old_receipt"], field="old_receipt"),
                    0o600,
                ),
                (
                    state_fd,
                    PREVIOUS_NAME,
                    _journal_old_bytes(journal["old_previous"], field="old_previous"),
                    0o600,
                ),
            ):
                try:
                    _assert_release_authority(
                        authority,
                        uid=uid,
                        gid=gid,
                        point=f"recover-{name}",
                        test_mode=test_mode,
                    )
                    _restore_pointer(
                        descriptor,
                        name,
                        old,
                        mode=mode,
                        uid=uid,
                        gid=gid,
                    )
                except BaseException as exc:
                    errors.append(f"{name}: {exc}")
                    break
        if errors:
            fail(
                "Mac release recovery is incomplete; fix the referenced immutable "
                "artifact and rerun `mac_release_publish.py recover`: "
                + "; ".join(errors)
            )
        _assert_release_authority(
            authority,
            uid=uid,
            gid=gid,
            point="recover-cleanup-backup",
            test_mode=test_mode,
        )
        _remove_pointer(asset_fd, STABLE_BACKUP_NAME)
        _assert_release_authority(
            authority,
            uid=uid,
            gid=gid,
            point="recover-cleanup-journal",
            test_mode=test_mode,
        )
        _remove_pointer(state_fd, JOURNAL_NAME)
    finally:
        os.close(asset_fd)
        os.close(current_fd)
    return {"recovered": True, "operation": journal["operation"]}


def recover_or_rollback(args: argparse.Namespace, *, rollback: bool) -> dict[str, Any]:
    test_mode, uid, gid = _protocol_test_mode(args)
    authority = _release_authority_from_args(
        args,
        uid=uid,
        gid=gid,
        test_mode=test_mode,
    )
    asset_root = _absolute_path(args.asset_root, description="asset root")
    state_root = _absolute_path(args.state_root, description="state root")
    _require_safe_directory(asset_root, mode=0o755, uid=uid, gid=gid)
    _require_safe_directory(state_root, mode=0o700, uid=uid, gid=gid)
    state_fd = _open_directory(state_root)
    lock_fd = -1
    try:
        lock_fd = _open_lock(state_fd, uid=uid, gid=gid)
        recovered = _recover_locked(
            state_fd=state_fd,
            asset_root=asset_root,
            uid=uid,
            gid=gid,
            authority=authority,
            test_mode=test_mode,
        )
        if not rollback:
            return recovered

        current_raw = _read_named_file(
            state_fd,
            RECEIPT_NAME,
            mode=0o600,
            uid=uid,
            gid=gid,
            maximum=MAX_RECEIPT_BYTES,
            missing_ok=False,
        )
        previous_raw = _read_named_file(
            state_fd,
            PREVIOUS_NAME,
            mode=0o600,
            uid=uid,
            gid=gid,
            maximum=MAX_RECEIPT_BYTES,
            missing_ok=False,
        )
        current_receipt = _validate_receipt(
            _json_object(current_raw or b"", description="current receipt"),
            asset_root=asset_root,
        )
        previous_receipt = _validate_receipt(
            _json_object(previous_raw or b"", description="previous receipt"),
            asset_root=asset_root,
        )
        current_dir = asset_root / "mac"
        current_fd = _open_directory(current_dir)
        asset_fd = _open_directory(asset_root)
        try:
            public_raw = _read_named_file(
                current_fd,
                CURRENT_RELATIVE.name,
                mode=0o644,
                uid=uid,
                gid=gid,
                maximum=MAX_RECEIPT_BYTES,
                missing_ok=False,
            )
            _validate_public_manifest(
                _json_object(public_raw or b"", description="public current"),
                receipt=current_receipt,
            )
            _verify_immutable_receipt(
                current_receipt,
                asset_root=asset_root,
                uid=uid,
                gid=gid,
                description="current rollback safety DMG",
            )
            _verify_immutable_receipt(
                previous_receipt,
                asset_root=asset_root,
                uid=uid,
                gid=gid,
                description="rollback DMG",
            )
            stable_digest, stable_size = _inspect_named_artifact(
                asset_fd,
                STABLE_NAME,
                uid=uid,
                gid=gid,
                description="stable DMG",
            )
            if (
                stable_digest != current_receipt["artifact_sha256"]
                or stable_size != current_receipt["artifact_size"]
            ):
                fail("stable DMG does not match current receipt before rollback")
            journal = _journal_payload(
                operation="rollback",
                phase="prepared",
                old_receipt=current_raw,
                old_previous=previous_raw,
                old_current=public_raw,
                old_stable={
                    "kind": "receipt",
                    "sha256": stable_digest,
                    "size": stable_size,
                },
                new_receipt=previous_receipt,
            )
            _assert_release_authority(
                authority,
                uid=uid,
                gid=gid,
                point="rollback-journal",
                test_mode=test_mode,
            )
            _write_journal(state_fd, journal, uid=uid, gid=gid)
            try:
                _assert_release_authority(
                    authority,
                    uid=uid,
                    gid=gid,
                    point="rollback-previous",
                    test_mode=test_mode,
                )
                _atomic_write(
                    state_fd,
                    PREVIOUS_NAME,
                    current_raw or b"",
                    mode=0o600,
                    uid=uid,
                    gid=gid,
                )
                journal["phase"] = "previous"
                _assert_release_authority(
                    authority,
                    uid=uid,
                    gid=gid,
                    point="rollback-previous-journal",
                    test_mode=test_mode,
                )
                _write_journal(state_fd, journal, uid=uid, gid=gid)
                _assert_release_authority(
                    authority,
                    uid=uid,
                    gid=gid,
                    point="rollback-receipt",
                    test_mode=test_mode,
                )
                _atomic_write(
                    state_fd,
                    RECEIPT_NAME,
                    previous_raw or b"",
                    mode=0o600,
                    uid=uid,
                    gid=gid,
                )
                journal["phase"] = "receipt"
                _assert_release_authority(
                    authority,
                    uid=uid,
                    gid=gid,
                    point="rollback-receipt-journal",
                    test_mode=test_mode,
                )
                _write_journal(state_fd, journal, uid=uid, gid=gid)
                _assert_release_authority(
                    authority,
                    uid=uid,
                    gid=gid,
                    point="rollback-stable",
                    test_mode=test_mode,
                )
                _restore_stable(
                    asset_fd,
                    previous_receipt,
                    asset_root=asset_root,
                    uid=uid,
                    gid=gid,
                )
                journal["phase"] = "stable"
                _assert_release_authority(
                    authority,
                    uid=uid,
                    gid=gid,
                    point="rollback-stable-journal",
                    test_mode=test_mode,
                )
                _write_journal(state_fd, journal, uid=uid, gid=gid)
                _assert_release_authority(
                    authority,
                    uid=uid,
                    gid=gid,
                    point="rollback-current",
                    test_mode=test_mode,
                )
                _atomic_write(
                    current_fd,
                    CURRENT_RELATIVE.name,
                    _encoded(_public_manifest(previous_receipt)),
                    mode=0o644,
                    uid=uid,
                    gid=gid,
                )
                journal["phase"] = "committed"
                _assert_release_authority(
                    authority,
                    uid=uid,
                    gid=gid,
                    point="rollback-committed",
                    test_mode=test_mode,
                )
                _write_journal(state_fd, journal, uid=uid, gid=gid)
                _assert_release_authority(
                    authority,
                    uid=uid,
                    gid=gid,
                    point="rollback-journal-cleanup",
                    test_mode=test_mode,
                )
                _remove_pointer(state_fd, JOURNAL_NAME)
            except BaseException:
                _recover_locked(
                    state_fd=state_fd,
                    asset_root=asset_root,
                    uid=uid,
                    gid=gid,
                    authority=authority,
                    test_mode=test_mode,
                )
                raise
        finally:
            os.close(asset_fd)
            os.close(current_fd)
        return previous_receipt
    finally:
        if lock_fd >= 0:
            os.close(lock_fd)
        os.close(state_fd)


def verify_release_state(args: argparse.Namespace) -> dict[str, Any]:
    test_mode, uid, gid = _protocol_test_mode(args)
    authority = _release_authority_from_args(
        args,
        uid=uid,
        gid=gid,
        test_mode=test_mode,
    )
    asset_root = _absolute_path(args.asset_root, description="asset root")
    state_root = _absolute_path(args.state_root, description="state root")
    _require_safe_directory(asset_root, mode=0o755, uid=uid, gid=gid)
    _require_safe_directory(state_root, mode=0o700, uid=uid, gid=gid)
    state_fd = _open_directory(state_root)
    lock_fd = -1
    try:
        lock_fd = _open_lock(state_fd, uid=uid, gid=gid)
        _assert_release_authority(
            authority,
            uid=uid,
            gid=gid,
            point="verify",
            test_mode=test_mode,
        )
        if _read_journal(
            state_fd,
            asset_root=asset_root,
            uid=uid,
            gid=gid,
        ) is not None:
            fail("Mac release transaction journal still requires recovery")
        current_dir = asset_root / "mac"
        _require_safe_directory(current_dir, mode=0o755, uid=uid, gid=gid)
        current_fd = _open_directory(current_dir)
        asset_fd = _open_directory(asset_root)
        try:
            receipt_raw = _read_optional_pointer(
                state_fd, RECEIPT_NAME, mode=0o600, uid=uid, gid=gid
            )
            previous_raw = _read_optional_pointer(
                state_fd, PREVIOUS_NAME, mode=0o600, uid=uid, gid=gid
            )
            current_raw = _read_optional_pointer(
                current_fd, CURRENT_RELATIVE.name, mode=0o644, uid=uid, gid=gid
            )
            stable = _stable_state(asset_fd, uid=uid, gid=gid)
            if receipt_raw is None:
                if current_raw is not None or previous_raw is not None:
                    fail("Mac formal pointers disagree without a current receipt")
                if stable is None:
                    return {"release": None, "legacy_baseline": None}
                return {
                    "release": None,
                    "legacy_baseline": {"sha256": stable[0], "size": stable[1]},
                }
            if current_raw is None or stable is None:
                fail("Mac current receipt, public manifest and stable DMG must coexist")
            receipt = _validate_receipt(
                _json_object(receipt_raw, description="current receipt"),
                asset_root=asset_root,
            )
            _validate_public_manifest(
                _json_object(current_raw, description="public current"),
                receipt=receipt,
            )
            _verify_immutable_receipt(
                receipt,
                asset_root=asset_root,
                uid=uid,
                gid=gid,
                description="current immutable DMG",
            )
            if stable != (receipt["artifact_sha256"], receipt["artifact_size"]):
                fail("stable DMG does not match current receipt")
            if previous_raw is not None:
                previous = _validate_receipt(
                    _json_object(previous_raw, description="previous receipt"),
                    asset_root=asset_root,
                )
                _verify_immutable_receipt(
                    previous,
                    asset_root=asset_root,
                    uid=uid,
                    gid=gid,
                    description="previous immutable DMG",
                )
            return {"release": receipt, "legacy_baseline": None}
        finally:
            os.close(asset_fd)
            os.close(current_fd)
    finally:
        if lock_fd >= 0:
            os.close(lock_fd)
        os.close(state_fd)


def publish(args: argparse.Namespace) -> dict[str, Any]:
    test_mode, uid, gid = _protocol_test_mode(args)
    authority = _release_authority_from_args(
        args,
        uid=uid,
        gid=gid,
        test_mode=test_mode,
    )

    artifact = _absolute_path(args.artifact, description="staged DMG path")
    candidate_path = _absolute_path(
        args.candidate, description="candidate receipt path"
    )
    asset_root = _absolute_path(args.asset_root, description="asset root")
    state_root = _absolute_path(args.state_root, description="state root")
    _require_safe_directory(asset_root, mode=0o755, uid=uid, gid=gid)
    _require_safe_directory(state_root, mode=0o700, uid=uid, gid=gid)

    receipt = _validate_receipt(
        _load_candidate(candidate_path, uid=uid, gid=gid),
        asset_root=asset_root,
    )
    artifact_fd, digest, size = _open_validated_upload(
        artifact, uid=uid, gid=gid
    )
    if digest != receipt["artifact_sha256"] or size != receipt["artifact_size"]:
        os.close(artifact_fd)
        fail("staged DMG does not match candidate receipt")

    state_fd = -1
    lock_fd = -1
    try:
        state_fd = _open_directory(state_root)
        lock_fd = _open_lock(state_fd, uid=uid, gid=gid)
        _recover_locked(
            state_fd=state_fd,
            asset_root=asset_root,
            uid=uid,
            gid=gid,
            authority=authority,
            test_mode=test_mode,
        )
        # Reject a regressive or reused release identity before installing even
        # immutable bytes.  The previous receipt is the durable high-water mark
        # after an explicit rollback.
        preflight_current_raw = _read_named_file(
            state_fd,
            RECEIPT_NAME,
            mode=0o600,
            uid=uid,
            gid=gid,
            maximum=MAX_RECEIPT_BYTES,
            missing_ok=True,
        )
        preflight_previous_raw = _read_named_file(
            state_fd,
            PREVIOUS_NAME,
            mode=0o600,
            uid=uid,
            gid=gid,
            maximum=MAX_RECEIPT_BYTES,
            missing_ok=True,
        )
        if preflight_current_raw is not None:
            preflight_current = _validate_receipt(
                _json_object(
                    preflight_current_raw,
                    description="current receipt high-water preflight",
                ),
                asset_root=asset_root,
            )
            _require_forward_release(preflight_current, receipt)
        if preflight_previous_raw is not None:
            preflight_previous = _validate_receipt(
                _json_object(
                    preflight_previous_raw,
                    description="previous receipt high-water preflight",
                ),
                asset_root=asset_root,
            )
            if not _require_forward_release(preflight_previous, receipt):
                fail(
                    "Mac release must advance beyond the durable "
                    "version/build high-water mark"
                )
        _assert_release_authority(
            authority,
            uid=uid,
            gid=gid,
            point="artifact-install",
            test_mode=test_mode,
        )
        immutable = _install_immutable(
            artifact_fd,
            receipt,
            asset_root=asset_root,
            uid=uid,
            gid=gid,
        )
        if immutable != Path(receipt["artifact_path"]):
            fail("installed DMG path does not match receipt")
        _assert_release_authority(
            authority,
            uid=uid,
            gid=gid,
            point="artifact",
            test_mode=test_mode,
        )
        _inject_failure("after-artifact", test_mode=test_mode)
        if args.prepare_only:
            return receipt

        current_dir = asset_root / "mac"
        current_fd = _open_directory(current_dir)
        asset_fd = _open_directory(asset_root)
        try:
            old_receipt = _read_named_file(
                state_fd,
                RECEIPT_NAME,
                mode=0o600,
                uid=uid,
                gid=gid,
                maximum=MAX_RECEIPT_BYTES,
                missing_ok=True,
            )
            old_previous = _read_named_file(
                state_fd,
                PREVIOUS_NAME,
                mode=0o600,
                uid=uid,
                gid=gid,
                maximum=MAX_RECEIPT_BYTES,
                missing_ok=True,
            )
            old_current = _read_named_file(
                current_fd,
                CURRENT_RELATIVE.name,
                mode=0o644,
                uid=uid,
                gid=gid,
                maximum=MAX_RECEIPT_BYTES,
                missing_ok=True,
            )
            try:
                os.stat(STABLE_NAME, dir_fd=asset_fd, follow_symlinks=False)
            except FileNotFoundError:
                old_stable_exists = False
            else:
                old_stable_exists = True
            try:
                os.stat(STABLE_BACKUP_NAME, dir_fd=asset_fd, follow_symlinks=False)
            except FileNotFoundError:
                orphan_backup_exists = False
            else:
                orphan_backup_exists = True
            if (old_receipt is None) != (old_current is None):
                fail("Mac receipt and public current pointer disagree")
            if old_receipt is None and old_previous is not None:
                fail("Mac previous receipt exists without a current release")
            if old_receipt is not None and not old_stable_exists:
                fail("Mac stable URL is missing for the current release")
            old_receipt_value: dict[str, Any] | None = None
            old_previous_value: dict[str, Any] | None = None
            if old_receipt is not None:
                old_receipt_value = _validate_receipt(
                    _json_object(old_receipt, description="current receipt"),
                    asset_root=asset_root,
                )
                _validate_public_manifest(
                    _json_object(old_current or b"", description="public current"),
                    receipt=old_receipt_value,
                )
                _verify_immutable_receipt(
                    old_receipt_value,
                    asset_root=asset_root,
                    uid=uid,
                    gid=gid,
                    description="previous DMG",
                )
                _verify_named_artifact(
                    asset_fd,
                    STABLE_NAME,
                    expected_digest=old_receipt_value["artifact_sha256"],
                    expected_size=old_receipt_value["artifact_size"],
                    uid=uid,
                    gid=gid,
                    description="stable DMG",
                )
                if orphan_backup_exists:
                    # A crash after committing and deleting the journal can only
                    # leave this legacy backup after the formal pointers already
                    # agree. It is no longer needed for rollback.
                    _assert_release_authority(
                        authority,
                        uid=uid,
                        gid=gid,
                        point="orphan-backup-cleanup",
                        test_mode=test_mode,
                    )
                    _remove_pointer(asset_fd, STABLE_BACKUP_NAME)
                    orphan_backup_exists = False
            elif orphan_backup_exists:
                fail(
                    "unfinished legacy stable Mac release rollback requires "
                    "`mac_release_publish.py recover`"
                )

            if old_previous is not None:
                old_previous_value = _validate_receipt(
                    _json_object(old_previous, description="previous receipt"),
                    asset_root=asset_root,
                )
                _verify_immutable_receipt(
                    old_previous_value,
                    asset_root=asset_root,
                    uid=uid,
                    gid=gid,
                    description="release high-water DMG",
                )

            if old_receipt_value is not None:
                if not _require_forward_release(old_receipt_value, receipt):
                    return receipt
            if old_previous_value is not None:
                if not _require_forward_release(old_previous_value, receipt):
                    fail(
                        "Mac release must advance beyond the durable "
                        "version/build high-water mark"
                    )

            new_value = _encoded(receipt)
            new_public_value = _encoded(_public_manifest(receipt))
            if old_receipt_value is not None:
                old_stable: dict[str, object] | None = {
                    "kind": "receipt",
                    "sha256": old_receipt_value["artifact_sha256"],
                    "size": old_receipt_value["artifact_size"],
                }
            elif old_stable_exists:
                legacy_digest, legacy_size = _inspect_named_artifact(
                    asset_fd,
                    STABLE_NAME,
                    uid=uid,
                    gid=gid,
                    description="legacy stable DMG",
                )
                old_stable = {
                    "kind": "legacy-backup",
                    "sha256": legacy_digest,
                    "size": legacy_size,
                }
            else:
                old_stable = None
            journal = _journal_payload(
                operation="publish",
                phase="prepared",
                old_receipt=old_receipt,
                old_previous=old_previous,
                old_current=old_current,
                old_stable=old_stable,
                new_receipt=receipt,
            )
            _assert_release_authority(
                authority,
                uid=uid,
                gid=gid,
                point="journal",
                test_mode=test_mode,
            )
            _write_journal(state_fd, journal, uid=uid, gid=gid)
            _inject_crash("after-journal", test_mode=test_mode)
            try:
                if old_receipt is None and old_stable_exists:
                    _assert_release_authority(
                        authority,
                        uid=uid,
                        gid=gid,
                        point="legacy-backup",
                        test_mode=test_mode,
                    )
                    _copy_named_to_pointer(
                        asset_fd,
                        STABLE_NAME,
                        asset_fd,
                        STABLE_BACKUP_NAME,
                        uid=uid,
                        gid=gid,
                        expected_digest=legacy_digest,
                        expected_size=legacy_size,
                    )
                if old_receipt is not None:
                    _assert_release_authority(
                        authority,
                        uid=uid,
                        gid=gid,
                        point="previous",
                        test_mode=test_mode,
                    )
                    _atomic_write(
                        state_fd,
                        PREVIOUS_NAME,
                        old_receipt,
                        mode=0o600,
                        uid=uid,
                        gid=gid,
                    )
                journal["phase"] = "previous"
                _assert_release_authority(
                    authority,
                    uid=uid,
                    gid=gid,
                    point="previous-journal",
                    test_mode=test_mode,
                )
                _write_journal(state_fd, journal, uid=uid, gid=gid)
                _inject_crash("after-previous", test_mode=test_mode)
                _assert_release_authority(
                    authority,
                    uid=uid,
                    gid=gid,
                    point="receipt",
                    test_mode=test_mode,
                )
                _atomic_write(
                    state_fd,
                    RECEIPT_NAME,
                    new_value,
                    mode=0o600,
                    uid=uid,
                    gid=gid,
                )
                journal["phase"] = "receipt"
                _assert_release_authority(
                    authority,
                    uid=uid,
                    gid=gid,
                    point="receipt-journal",
                    test_mode=test_mode,
                )
                _write_journal(state_fd, journal, uid=uid, gid=gid)
                _inject_crash("after-receipt", test_mode=test_mode)
                source_fd = _open_directory(Path(receipt["artifact_path"]).parent)
                try:
                    _assert_release_authority(
                        authority,
                        uid=uid,
                        gid=gid,
                        point="stable",
                        test_mode=test_mode,
                    )
                    _copy_named_to_pointer(
                        source_fd,
                        Path(receipt["artifact_path"]).name,
                        asset_fd,
                        STABLE_NAME,
                        uid=uid,
                        gid=gid,
                        expected_digest=receipt["artifact_sha256"],
                        expected_size=receipt["artifact_size"],
                    )
                finally:
                    os.close(source_fd)
                journal["phase"] = "stable"
                _assert_release_authority(
                    authority,
                    uid=uid,
                    gid=gid,
                    point="stable-journal",
                    test_mode=test_mode,
                )
                _write_journal(state_fd, journal, uid=uid, gid=gid)
                _inject_crash("after-stable", test_mode=test_mode)
                _inject_failure("before-current", test_mode=test_mode)
                _assert_release_authority(
                    authority,
                    uid=uid,
                    gid=gid,
                    point="current",
                    test_mode=test_mode,
                )
                _atomic_write(
                    current_fd,
                    CURRENT_RELATIVE.name,
                    new_public_value,
                    mode=0o644,
                    uid=uid,
                    gid=gid,
                )
                journal["phase"] = "current"
                _assert_release_authority(
                    authority,
                    uid=uid,
                    gid=gid,
                    point="current-journal",
                    test_mode=test_mode,
                )
                _write_journal(state_fd, journal, uid=uid, gid=gid)
                _inject_crash("after-current", test_mode=test_mode)
                _inject_failure("after-current", test_mode=test_mode)
                verified_receipt = _read_named_file(
                    state_fd,
                    RECEIPT_NAME,
                    mode=0o600,
                    uid=uid,
                    gid=gid,
                    maximum=MAX_RECEIPT_BYTES,
                    missing_ok=False,
                )
                verified_current = _read_named_file(
                    current_fd,
                    CURRENT_RELATIVE.name,
                    mode=0o644,
                    uid=uid,
                    gid=gid,
                    maximum=MAX_RECEIPT_BYTES,
                    missing_ok=False,
                )
                if (
                    verified_receipt != new_value
                    or verified_current != new_public_value
                ):
                    fail("Mac release pointer verification failed")
                _verify_named_artifact(
                    asset_fd,
                    STABLE_NAME,
                    expected_digest=receipt["artifact_sha256"],
                    expected_size=receipt["artifact_size"],
                    uid=uid,
                    gid=gid,
                    description="stable DMG",
                )
                journal["phase"] = "committed"
                _assert_release_authority(
                    authority,
                    uid=uid,
                    gid=gid,
                    point="committed",
                    test_mode=test_mode,
                )
                _write_journal(state_fd, journal, uid=uid, gid=gid)
                _inject_crash("after-committed", test_mode=test_mode)
                if old_receipt is None and old_stable_exists:
                    _assert_release_authority(
                        authority,
                        uid=uid,
                        gid=gid,
                        point="backup-cleanup",
                        test_mode=test_mode,
                    )
                    _remove_pointer(asset_fd, STABLE_BACKUP_NAME)
                _assert_release_authority(
                    authority,
                    uid=uid,
                    gid=gid,
                    point="journal-cleanup",
                    test_mode=test_mode,
                )
                _remove_pointer(state_fd, JOURNAL_NAME)
            except BaseException:
                _recover_locked(
                    state_fd=state_fd,
                    asset_root=asset_root,
                    uid=uid,
                    gid=gid,
                    authority=authority,
                    test_mode=test_mode,
                )
                raise

        finally:
            os.close(asset_fd)
            os.close(current_fd)
    finally:
        if lock_fd >= 0:
            os.close(lock_fd)
        if state_fd >= 0:
            os.close(state_fd)
        os.close(artifact_fd)
    return receipt


def create_candidate(args: argparse.Namespace) -> dict[str, Any]:
    _protocol_test_mode(args)
    output = Path(args.output)
    if not output.is_absolute():
        fail("candidate output path must be absolute")
    parent = output.parent.resolve(strict=True)
    if output.exists() or output.is_symlink():
        fail("candidate output already exists")
    value: dict[str, Any] = {
        "schema_version": 1,
        "source_sha": args.source_sha,
        "source_tree": args.source_tree,
        "artifact_sha256": args.artifact_sha256,
        "artifact_size": args.artifact_size,
        "artifact_path": args.artifact_path,
        "artifact_url": args.artifact_url,
        "bundle_id": args.bundle_id,
        "version": args.version,
        "build": args.build,
        "team_id": args.team_id,
        "cdhash": args.cdhash.lower(),
        "architectures": sorted(args.architecture),
        "min_os": args.min_os,
        "notary_submission_id": args.notary_submission_id,
        "notary_status": args.notary_status,
        "stapled": args.stapled,
        "published_at": args.published_at,
    }
    # ``artifact_path`` is validated against its declared immutable root by
    # deriving that root from the fixed ``mac/releases`` suffix.  Publication
    # repeats validation against the actual production asset root.
    marker = f"/mac/releases/{value['source_sha']}/{value['artifact_sha256']}.dmg"
    artifact_path = value["artifact_path"]
    if not isinstance(artifact_path, str) or not artifact_path.endswith(marker):
        fail("candidate artifact_path is not an immutable Mac release path")
    asset_root = Path(artifact_path[: -len(marker)])
    _validate_receipt(value, asset_root=asset_root)
    parent_fd = _open_directory(parent)
    try:
        _atomic_write(
            parent_fd,
            output.name,
            _encoded(value),
            mode=0o600,
            uid=os.geteuid(),
            gid=os.getegid(),
        )
    finally:
        os.close(parent_fd)
    return value


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    commands = result.add_subparsers(dest="command", required=True)
    publish_parser = commands.add_parser("publish")
    publish_parser.add_argument("--artifact", required=True)
    publish_parser.add_argument("--candidate", required=True)
    publish_parser.add_argument("--asset-root", required=True)
    publish_parser.add_argument("--state-root", required=True)
    publish_parser.add_argument("--prepare-only", action="store_true")
    publish_parser.add_argument("--release-lock-dir")
    publish_parser.add_argument("--release-lock-token")
    publish_parser.add_argument(
        "--allow-non-root-for-tests",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    for command in ("recover", "rollback", "verify"):
        maintenance_parser = commands.add_parser(command)
        maintenance_parser.add_argument("--asset-root", required=True)
        maintenance_parser.add_argument("--state-root", required=True)
        maintenance_parser.add_argument("--release-lock-dir")
        maintenance_parser.add_argument("--release-lock-token")
        maintenance_parser.add_argument(
            "--allow-non-root-for-tests",
            action="store_true",
            help=argparse.SUPPRESS,
        )
    candidate_parser = commands.add_parser("create-candidate")
    candidate_parser.add_argument("--output", required=True)
    candidate_parser.add_argument("--source-sha", required=True)
    candidate_parser.add_argument("--source-tree", required=True)
    candidate_parser.add_argument("--artifact-sha256", required=True)
    candidate_parser.add_argument("--artifact-size", required=True, type=int)
    candidate_parser.add_argument("--artifact-path", required=True)
    candidate_parser.add_argument("--artifact-url", required=True)
    candidate_parser.add_argument("--bundle-id", required=True)
    candidate_parser.add_argument("--version", required=True)
    candidate_parser.add_argument("--build", required=True)
    candidate_parser.add_argument("--team-id", required=True)
    candidate_parser.add_argument("--cdhash", required=True)
    candidate_parser.add_argument(
        "--architecture", action="append", required=True
    )
    candidate_parser.add_argument("--min-os", required=True)
    candidate_parser.add_argument("--notary-submission-id", required=True)
    candidate_parser.add_argument("--notary-status", required=True)
    candidate_parser.add_argument("--stapled", action="store_true", required=True)
    candidate_parser.add_argument("--published-at", required=True)
    candidate_parser.add_argument(
        "--allow-non-root-for-tests",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    handoff_parser = commands.add_parser("handoff-clear", help=argparse.SUPPRESS)
    handoff_parser.add_argument("--bundle", required=True)
    handoff_parser.add_argument("--token", required=True)
    handoff_parser.add_argument(
        "--allow-non-root-for-tests",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    for name in (
        "lease-acquire",
        "lease-assert",
        "lease-transition",
        "lease-release",
        "stage-reset",
        "stage-bind-helper",
        "stage-bind-payload",
        "stage-cleanup",
    ):
        protocol_parser = commands.add_parser(name, help=argparse.SUPPRESS)
        protocol_parser.add_argument("--lock-dir", required=True)
        protocol_parser.add_argument("--token", required=True)
        protocol_parser.add_argument("--operation", required=True)
        protocol_parser.add_argument("--stage-kind", required=True)
        protocol_parser.add_argument("--stage", required=True)
        protocol_parser.add_argument("--asset-root", required=True)
        protocol_parser.add_argument("--state-root", required=True)
        protocol_parser.add_argument("--source-sha", required=True)
        protocol_parser.add_argument("--source-tree", required=True)
        protocol_parser.add_argument("--helper-sha256", required=True)
        protocol_parser.add_argument("--artifact-sha256", required=True)
        protocol_parser.add_argument("--artifact-size", required=True)
        protocol_parser.add_argument("--candidate-sha256", required=True)
        protocol_parser.add_argument(
            "--allow-non-root-for-tests",
            action="store_true",
            help=argparse.SUPPRESS,
        )
        if name == "lease-acquire":
            protocol_parser.add_argument("--requested-action", required=True)
        elif name == "lease-assert":
            protocol_parser.add_argument("--phase", required=True)
        elif name == "lease-transition":
            protocol_parser.add_argument("--old-phase", required=True)
            protocol_parser.add_argument("--new-phase", required=True)
        elif name == "lease-release":
            protocol_parser.add_argument("--phase", required=True)
        elif name == "stage-cleanup":
            protocol_parser.add_argument("--allow-partial-stage", action="store_true")
    return result


_CLI_MUTATING_COMMANDS = {
    "publish",
    "recover",
    "rollback",
    "verify",
    "handoff-clear",
    "lease-acquire",
    "lease-assert",
    "lease-transition",
    "lease-release",
    "stage-reset",
    "stage-bind-helper",
    "stage-bind-payload",
    "stage-cleanup",
}
_CLI_PATH_ARGUMENTS = (
    "output",
    "artifact",
    "artifact_path",
    "candidate",
    "asset_root",
    "state_root",
    "release_lock_dir",
    "lock_dir",
    "stage",
    "bundle",
)


def _isolated_non_root_cli_test(args: argparse.Namespace) -> bool:
    if (
        os.geteuid() == 0
        or os.environ.get("MAC_RELEASE_TEST_MODE") != "1"
        or not getattr(args, "allow_non_root_for_tests", False)
    ):
        return False
    configured_roots = (
        (Path("/private/tmp"), Path("/private/var/folders"))
        if sys.platform == "darwin"
        else (Path("/tmp"),)
    )
    safe_roots: list[Path] = []
    for root in configured_roots:
        try:
            canonical = root.resolve(strict=True)
            metadata = canonical.stat()
        except OSError:
            continue
        if stat.S_ISDIR(metadata.st_mode):
            safe_roots.append(canonical)
    if not safe_roots:
        return False
    paths: list[Path] = []
    for attribute in _CLI_PATH_ARGUMENTS:
        raw = getattr(args, attribute, None)
        if raw:
            path = Path(raw)
            if not path.is_absolute():
                return False
            resolved = path.resolve(strict=False)
            if not any(resolved != root and root in resolved.parents for root in safe_roots):
                return False
            paths.append(resolved)
    return bool(paths)


def main() -> int:
    args = parser().parse_args()
    if args.command == "create-candidate" and not _isolated_non_root_cli_test(args):
        print(
            "MAC_RELEASE_PUBLISH_FROZEN: local candidate creation requires an isolated non-root test root",
            file=sys.stderr,
        )
        return 78
    if args.command in _CLI_MUTATING_COMMANDS and not _isolated_non_root_cli_test(args):
        print(
            "MAC_RELEASE_PUBLISH_FROZEN: production mutation requires the manual release Gate",
            file=sys.stderr,
        )
        return 78
    try:
        if args.command == "publish":
            result = publish(args)
        elif args.command == "recover":
            result = recover_or_rollback(args, rollback=False)
        elif args.command == "rollback":
            result = recover_or_rollback(args, rollback=True)
        elif args.command == "verify":
            result = verify_release_state(args)
        elif args.command == "create-candidate":
            result = create_candidate(args)
        elif args.command == "lease-acquire":
            result = lease_acquire(args)
        elif args.command == "lease-assert":
            result = lease_assert(args)
        elif args.command == "lease-transition":
            result = lease_transition(args)
        elif args.command == "lease-release":
            result = lease_release(args)
        elif args.command == "stage-reset":
            result = stage_reset(args)
        elif args.command == "stage-bind-helper":
            result = stage_bind_helper(args)
        elif args.command == "stage-bind-payload":
            result = stage_bind_payload(args)
        elif args.command == "stage-cleanup":
            result = stage_cleanup(args)
        elif args.command == "handoff-clear":
            result = handoff_clear(args)
        else:  # pragma: no cover - argparse owns this invariant
            fail("unsupported command")
    except (OSError, PublishError) as exc:
        print(f"MAC_RELEASE_PUBLISH_ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
