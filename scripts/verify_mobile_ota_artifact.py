#!/usr/bin/env python3
"""Fail-closed validation for transaction-local iOS EAS Update artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
CHANNEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
MAX_MANIFEST_BYTES = 64 * 1024


class VerificationError(ValueError):
    """Raised when an OTA proof is incomplete or contradictory."""


def _private_directory(path: Path, *, create: bool = True) -> bool:
    if create:
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError as exc:
            raise VerificationError(
                f"cannot create shared OTA state directory: {path}"
            ) from exc
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        if not create:
            return False
        raise VerificationError(
            f"shared OTA state directory is unavailable: {path}"
        ) from None
    except OSError as exc:
        raise VerificationError(f"shared OTA state directory is unavailable: {path}") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_uid != os.getuid()
    ):
        raise VerificationError(
            f"shared OTA state directory must be current-owner mode 0700: {path}"
        )
    return True


def _git_common_dir(repo_root: Path) -> Path:
    try:
        value = subprocess.check_output(
            [
                "git",
                "-C",
                str(repo_root),
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise VerificationError("cannot resolve the repository common git directory") from exc
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def _git_worktrees(repo_root: Path) -> list[Path]:
    try:
        output = subprocess.check_output(
            ["git", "-C", str(repo_root), "worktree", "list", "--porcelain"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise VerificationError("cannot enumerate repository worktrees") from exc
    worktrees = []
    for line in output.splitlines():
        if line.startswith("worktree "):
            worktrees.append(Path(line.removeprefix("worktree ")).resolve())
    if not worktrees:
        raise VerificationError("repository worktree inventory is empty")
    return worktrees


def _safe_receipt_bytes(path: Path, *, legacy: bool) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise VerificationError(f"unsafe OTA receipt: {path}: {exc}") from exc
    try:
        metadata = os.fstat(descriptor)
        allowed_modes = {0o600, 0o644} if legacy else {0o600}
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) not in allowed_modes
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
        ):
            raise VerificationError(f"unsafe OTA receipt metadata: {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            payload = handle.read()
        current = path.stat(follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise VerificationError(f"OTA receipt changed while reading: {path}")
        return payload, metadata
    finally:
        os.close(descriptor)


def _validate_receipt_payload(
    kind: str, payload: bytes, _scratch: Path, *, channel: str
) -> None:
    if kind == "manifest":
        try:
            manifest = json.loads(payload.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise VerificationError("legacy OTA manifest is invalid") from exc
        _validate_manifest_payload(manifest, expected_channel=channel)
        return
    if kind == "anchor":
        try:
            value = payload.decode("utf-8").strip()
        except UnicodeError as exc:
            raise VerificationError("legacy OTA anchor is not UTF-8") from exc
        if not SHA_RE.fullmatch(value):
            raise VerificationError("legacy OTA anchor is invalid")
        return
    if kind == "audit":
        try:
            lines = payload.decode("utf-8").splitlines()
            if any(not isinstance(json.loads(line), dict) for line in lines if line.strip()):
                raise ValueError("audit event must be an object")
        except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise VerificationError("legacy OTA audit is invalid") from exc
        return
    raise VerificationError(f"unsupported OTA receipt kind: {kind}")


def _install_private_receipt(path: Path, payload: bytes) -> None:
    parent_fd = os.open(
        path.parent,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    temporary_name = f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=parent_fd)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(
                temporary_name,
                path.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
            os.unlink(temporary_name, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except BaseException:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            raise
    finally:
        os.close(parent_fd)


def _remove_legacy_receipt(path: Path, expected: os.stat_result) -> None:
    current = path.stat(follow_symlinks=False)
    if (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino):
        raise VerificationError(f"legacy OTA receipt changed before migration: {path}")
    path.unlink()
    parent_fd = os.open(
        path.parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _migrate_legacy_receipt(
    *, repo_root: Path, target: Path, channel: str, kind: str
) -> None:
    legacy_names = {
        "manifest": (
            ".mobile-release-manifest.json"
            if channel == "production"
            else f".mobile-release-manifest.{channel}.json"
        ),
        "anchor": ".last-ota-commit" if channel == "production" else None,
        "audit": ".mobile-ota-audit.jsonl" if channel == "production" else None,
    }
    legacy_name = legacy_names[kind]
    if legacy_name is None:
        return
    candidates = [
        worktree / legacy_name
        for worktree in _git_worktrees(repo_root)
        if (worktree / legacy_name).exists() or (worktree / legacy_name).is_symlink()
    ]
    candidate_payloads = [
        (candidate, *_safe_receipt_bytes(candidate, legacy=True))
        for candidate in candidates
    ]
    unique_payloads = {payload for _path, payload, _metadata in candidate_payloads}
    if len(unique_payloads) > 1:
        raise VerificationError(
            f"conflicting legacy OTA {kind} receipts across git worktrees"
        )
    target_payload: bytes | None = None
    if target.exists() or target.is_symlink():
        target_payload, _metadata = _safe_receipt_bytes(target, legacy=False)
    if candidate_payloads:
        payload = candidate_payloads[0][1]
        scratch = target.with_name(f".{target.name}.validation.{os.getpid()}")
        _validate_receipt_payload(kind, payload, scratch, channel=channel)
        if target_payload is None:
            _install_private_receipt(target, payload)
        elif target_payload != payload:
            raise VerificationError(
                f"shared and legacy OTA {kind} receipts conflict; reconcile manually"
            )
        for candidate, _payload, metadata in candidate_payloads:
            _remove_legacy_receipt(candidate, metadata)


def resolve_mobile_state_paths(
    *,
    repo_root: Path,
    channel: str,
    scope: str,
    manifest_file: str | None,
    anchor_file: str | None,
    audit_file: str | None,
    migrate: bool,
    read_only: bool = False,
) -> dict[str, str]:
    if not CHANNEL_RE.fullmatch(channel):
        raise VerificationError("OTA channel is invalid")
    if migrate and read_only:
        raise VerificationError("OTA state migration is incompatible with read-only mode")
    repo_root = repo_root.resolve()

    def explicit(value: str) -> Path:
        path = Path(value).expanduser()
        return (path if path.is_absolute() else repo_root / path).absolute()

    needs_shared_state = manifest_file is None or (
        scope == "mobile" and (anchor_file is None or audit_file is None)
    )
    state_dir: Path | None = None
    state_dir_exists = False
    if needs_shared_state:
        common = _git_common_dir(repo_root)
        state_root = common / "reva-release-state"
        state_root_exists = _private_directory(state_root, create=not read_only)
        state_dir = state_root / "mobile-ota"
        if state_root_exists:
            state_dir_exists = _private_directory(state_dir, create=not read_only)

    if manifest_file is not None:
        manifest = explicit(manifest_file)
        pending = manifest.with_name(f"{manifest.stem}.rollback-pending.json")
    else:
        assert state_dir is not None
        manifest = state_dir / f"manifest.{channel}.json"
        pending = state_dir / f"rollback-pending.{channel}.json"
        if migrate and state_dir_exists:
            _migrate_legacy_receipt(
                repo_root=repo_root,
                target=manifest,
                channel=channel,
                kind="manifest",
            )
    result = {
        "manifest_file": str(manifest),
        "pending_file": str(pending),
    }
    if scope == "mobile":
        if anchor_file is not None:
            anchor = explicit(anchor_file)
        else:
            assert state_dir is not None
            anchor = state_dir / f"anchor.{channel}"
            if migrate and state_dir_exists:
                _migrate_legacy_receipt(
                    repo_root=repo_root,
                    target=anchor,
                    channel=channel,
                    kind="anchor",
                )
        if audit_file is not None:
            audit = explicit(audit_file)
        else:
            assert state_dir is not None
            audit = state_dir / f"audit.{channel}.jsonl"
            if migrate and state_dir_exists:
                _migrate_legacy_receipt(
                    repo_root=repo_root,
                    target=audit,
                    channel=channel,
                    kind="audit",
                )
        result.update({"anchor_file": str(anchor), "audit_file": str(audit)})
    return result


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"invalid JSON file {path}: {exc}") from exc


def _open_directory_without_symlinks(path: Path) -> tuple[int, os.stat_result]:
    absolute = path.expanduser().absolute()
    flags = (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_CLOEXEC
        | os.O_NOFOLLOW
    )
    descriptor = -1
    try:
        descriptor = os.open(absolute.anchor, flags)
        for component in absolute.parts[1:]:
            next_descriptor = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or metadata.st_uid != os.getuid()
        ):
            raise VerificationError(
                "release manifest directory must be current-owner mode 0700"
            )
        return descriptor, metadata
    except VerificationError:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise VerificationError(
            f"release manifest directory is unsafe or unavailable: {path}: {exc}"
        ) from exc


def _assert_private_directory_fd(
    descriptor: int,
    *,
    expected: os.stat_result | None = None,
) -> os.stat_result:
    try:
        metadata = os.fstat(descriptor)
    except OSError as exc:
        raise VerificationError("release manifest directory changed") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_uid != os.getuid()
    ):
        raise VerificationError(
            "release manifest directory must remain current-owner mode 0700"
        )
    if expected is not None and (metadata.st_dev, metadata.st_ino) != (
        expected.st_dev,
        expected.st_ino,
    ):
        raise VerificationError("release manifest directory changed")
    return metadata


def _read_private_manifest(
    path: Path, *, allow_missing: bool
) -> tuple[bytes | None, os.stat_result | None]:
    absolute = path.expanduser().absolute()
    parent_descriptor, parent_metadata = _open_directory_without_symlinks(
        absolute.parent
    )
    descriptor = -1
    try:
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        try:
            descriptor = os.open(absolute.name, flags, dir_fd=parent_descriptor)
        except FileNotFoundError:
            if allow_missing:
                return None, None
            raise VerificationError(f"release manifest is missing: {path}") from None
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise VerificationError(
                "release manifest must be a regular non-symlink file"
            )
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise VerificationError("release manifest permissions must be 0600")
        if metadata.st_uid != os.getuid():
            raise VerificationError("release manifest must be owned by the current user")
        if metadata.st_nlink != 1:
            raise VerificationError("release manifest must have exactly one hard link")
        if metadata.st_size > MAX_MANIFEST_BYTES:
            raise VerificationError("release manifest size is too large")

        chunks: list[bytes] = []
        remaining = MAX_MANIFEST_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > MAX_MANIFEST_BYTES:
            raise VerificationError("release manifest size is too large")

        final_metadata = os.fstat(descriptor)
        stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(
            getattr(metadata, field) != getattr(final_metadata, field)
            for field in stable_fields
        ):
            raise VerificationError("release manifest changed while reading")
        _assert_private_directory_fd(
            parent_descriptor,
            expected=parent_metadata,
        )
        try:
            current = os.stat(
                absolute.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            current_parent = os.stat(absolute.parent, follow_symlinks=False)
        except OSError as exc:
            raise VerificationError("release manifest changed while reading") from exc
        if (
            (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino)
            or (current_parent.st_dev, current_parent.st_ino)
            != (parent_metadata.st_dev, parent_metadata.st_ino)
        ):
            raise VerificationError("release manifest changed while reading")
        return payload, metadata
    except OSError as exc:
        raise VerificationError(f"release manifest is unavailable: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_descriptor)


def _safe_relative_path(value: Any, *, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise VerificationError(f"{label} path is missing or invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise VerificationError(f"{label} path escapes the export root: {value!r}")
    return path


def _regular_files(root: Path) -> list[Path]:
    try:
        root_mode = root.lstat().st_mode
    except OSError as exc:
        raise VerificationError(f"artifact input directory is unavailable: {exc}") from exc
    if stat.S_ISLNK(root_mode):
        raise VerificationError("artifact input directory must not be a symlink")
    if not stat.S_ISDIR(root_mode):
        raise VerificationError("artifact input path is not a directory")

    files: list[Path] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise VerificationError(f"cannot scan artifact directory {directory}: {exc}") from exc
        for entry in entries:
            path = Path(entry.path)
            try:
                mode = entry.stat(follow_symlinks=False).st_mode
            except OSError as exc:
                raise VerificationError(f"cannot stat artifact path {path}: {exc}") from exc
            if stat.S_ISLNK(mode):
                raise VerificationError(f"artifact contains a symlink: {path.relative_to(root)}")
            if stat.S_ISDIR(mode):
                pending.append(path)
            elif stat.S_ISREG(mode):
                files.append(path)
            else:
                raise VerificationError(
                    f"artifact contains a non-regular path: {path.relative_to(root)}"
                )
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def _digest_files(root: Path, files: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def validate_artifact(
    input_dir: Path,
    *,
    platform: str,
    expected_digest: str | None = None,
    not_before_ns: int | None = None,
) -> dict[str, Any]:
    if platform != "ios":
        raise VerificationError("only an ios OTA artifact is allowed")

    files = _regular_files(input_dir)
    if not files:
        raise VerificationError("artifact export is empty")
    empty_files = [
        path.relative_to(input_dir).as_posix()
        for path in files
        if path.lstat().st_size <= 0
    ]
    if empty_files:
        raise VerificationError(f"artifact contains an empty file: {empty_files[0]}")
    relative_files = {path.relative_to(input_dir).as_posix(): path for path in files}
    metadata_path = relative_files.get("metadata.json")
    if metadata_path is None:
        raise VerificationError("artifact is missing Expo metadata.json")

    metadata = _read_json(metadata_path)
    if not isinstance(metadata, dict):
        raise VerificationError("Expo metadata must be an object")
    file_metadata = metadata.get("fileMetadata")
    if not isinstance(file_metadata, dict) or set(file_metadata) != {"ios"}:
        raise VerificationError("artifact metadata must contain ios and no other platform")
    ios = file_metadata.get("ios")
    if not isinstance(ios, dict):
        raise VerificationError("artifact ios metadata must be an object")

    referenced: list[PurePosixPath] = [
        _safe_relative_path(ios.get("bundle"), label="ios bundle")
    ]
    assets = ios.get("assets")
    if not isinstance(assets, list):
        raise VerificationError("artifact ios assets must be a list")
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            raise VerificationError(f"ios asset {index} must be an object")
        referenced.append(
            _safe_relative_path(asset.get("path"), label=f"ios asset {index}")
        )

    for relative in referenced:
        path = relative_files.get(relative.as_posix())
        if path is None:
            raise VerificationError(f"referenced artifact file is missing: {relative}")
        try:
            size = path.lstat().st_size
        except OSError as exc:
            raise VerificationError(f"cannot read referenced artifact file {relative}: {exc}") from exc
        if size <= 0:
            raise VerificationError(f"referenced artifact file is empty: {relative}")

    if not_before_ns is not None:
        stale = [
            path.relative_to(input_dir).as_posix()
            for path in files
            if path.lstat().st_mtime_ns < not_before_ns
        ]
        if stale:
            raise VerificationError(
                f"artifact contains stale files older than this transaction: {stale[0]}"
            )

    artifact_digest = _digest_files(input_dir, files)
    if expected_digest is not None and artifact_digest != expected_digest:
        raise VerificationError(
            "artifact digest mismatch: transaction bytes changed after verification"
        )
    return {
        "schema_version": 1,
        "platform": platform,
        "artifact_digest": artifact_digest,
        "file_count": len(files),
        "total_bytes": sum(path.lstat().st_size for path in files),
        "metadata_file": "metadata.json",
    }


def _validate_manifest_payload(
    payload: Any, *, expected_channel: str | None
) -> int:
    if not isinstance(payload, dict):
        raise VerificationError("release manifest must be a JSON object")
    schema = payload.get("schema_version", 1)
    if schema not in {1, 2}:
        raise VerificationError("release manifest schema is unsupported")
    if expected_channel is not None:
        if not CHANNEL_RE.fullmatch(expected_channel):
            raise VerificationError("expected OTA channel is invalid")
        manifest_channel = payload.get("channel")
        legacy_production = (
            schema == 1
            and manifest_channel is None
            and expected_channel == "production"
        )
        if not legacy_production and manifest_channel != expected_channel:
            raise VerificationError("release manifest channel mismatch")
    for group_key, update_key in (
        ("group_id", "update_id"),
        ("active_group_id", "active_update_id"),
        ("previous_known_good_group_id", "previous_known_good_update_id"),
    ):
        group, update = payload.get(group_key), payload.get(update_key)
        if (group is None) != (update is None):
            raise VerificationError(
                f"release manifest has an incomplete {group_key}/{update_key} pair"
            )
        if group is not None and (
            not isinstance(group, str) or not UUID_RE.fullmatch(group)
        ):
            raise VerificationError(f"release manifest has an invalid {group_key}")
        if update is not None and (
            not isinstance(update, str) or not UUID_RE.fullmatch(update)
        ):
            raise VerificationError(f"release manifest has an invalid {update_key}")
    legacy_pair = (payload.get("group_id"), payload.get("update_id"))
    active_pair = (payload.get("active_group_id"), payload.get("active_update_id"))
    if legacy_pair == (None, None) and active_pair == (None, None):
        raise VerificationError("release manifest has no active update identity")
    allow_legacy_rollback_aliases = schema == 1 and payload.get("status") == "rolled_back"
    if (
        not allow_legacy_rollback_aliases
        and legacy_pair != (None, None)
        and active_pair != (None, None)
        and legacy_pair != active_pair
    ):
        raise VerificationError(
            "release manifest legacy and active update identities disagree"
        )
    artifact_evidence = payload.get("artifact_evidence")
    artifact_digest = payload.get("artifact_digest")
    artifact_file_count = payload.get("artifact_file_count")
    artifact_total_bytes = payload.get("artifact_total_bytes")
    artifact_values = (
        artifact_digest,
        artifact_file_count,
        artifact_total_bytes,
    )
    if artifact_evidence not in {
        None,
        "verified_transaction_artifact",
        "unavailable_after_remote_adoption",
    }:
        raise VerificationError("release manifest has invalid artifact evidence")
    has_artifact_values = any(value is not None for value in artifact_values)
    if artifact_evidence == "unavailable_after_remote_adoption":
        if has_artifact_values:
            raise VerificationError(
                "release manifest unavailable artifact evidence has artifact values"
            )
    elif artifact_evidence == "verified_transaction_artifact" or has_artifact_values:
        if not isinstance(artifact_digest, str) or not DIGEST_RE.fullmatch(
            artifact_digest
        ):
            raise VerificationError("release manifest has invalid artifact digest")
        if (
            not isinstance(artifact_file_count, int)
            or isinstance(artifact_file_count, bool)
            or artifact_file_count < 1
        ):
            raise VerificationError("release manifest has invalid artifact file count")
        if (
            not isinstance(artifact_total_bytes, int)
            or isinstance(artifact_total_bytes, bool)
            or artifact_total_bytes < 1
        ):
            raise VerificationError("release manifest has invalid artifact byte count")
    return schema


def validate_manifest(
    path: Path,
    *,
    allow_missing: bool,
    expected_channel: str | None = None,
) -> dict[str, Any]:
    raw_payload, metadata = _read_private_manifest(path, allow_missing=allow_missing)
    if raw_payload is None:
        return {
            "exists": False,
            "schema_version": None,
            "sha256": None,
            "identity": None,
            "payload": None,
        }
    assert metadata is not None
    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"release manifest JSON is invalid: {exc}") from exc
    schema = _validate_manifest_payload(payload, expected_channel=expected_channel)
    return {
        "exists": True,
        "schema_version": schema,
        "sha256": hashlib.sha256(raw_payload).hexdigest(),
        "identity": {
            "device": metadata.st_dev,
            "inode": metadata.st_ino,
        },
        "payload": payload,
    }


def _read_private_file_at(
    parent_descriptor: int,
    name: str,
    *,
    label: str,
    allow_missing: bool,
) -> tuple[bytes, os.stat_result] | None:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    descriptor = -1
    try:
        try:
            descriptor = os.open(name, flags, dir_fd=parent_descriptor)
        except FileNotFoundError:
            if allow_missing:
                return None
            raise VerificationError(f"{label} is missing") from None
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
        ):
            raise VerificationError(
                f"{label} must be a current-owner 0600 single-link regular file"
            )
        if metadata.st_size > MAX_MANIFEST_BYTES:
            raise VerificationError(f"{label} size is too large")
        chunks: list[bytes] = []
        remaining = MAX_MANIFEST_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > MAX_MANIFEST_BYTES:
            raise VerificationError(f"{label} size is too large")
        final_metadata = os.fstat(descriptor)
        stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(
            getattr(metadata, field) != getattr(final_metadata, field)
            for field in stable_fields
        ):
            raise VerificationError(f"{label} changed while reading")
        current = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise VerificationError(f"{label} changed while reading")
        return data, metadata
    except OSError as exc:
        raise VerificationError(f"{label} is unsafe or unavailable: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _receipt_identity(
    receipt: tuple[bytes, os.stat_result] | None,
) -> tuple[int, int, str] | None:
    if receipt is None:
        return None
    data, metadata = receipt
    return metadata.st_dev, metadata.st_ino, hashlib.sha256(data).hexdigest()


def _atomic_replace_private_file(
    path: Path,
    data: bytes,
    *,
    label: str,
    expected_snapshot: dict[str, Any] | None,
) -> None:
    if len(data) > MAX_MANIFEST_BYTES:
        raise VerificationError(f"{label} size is too large")
    absolute = path.expanduser().absolute()
    parent_descriptor, parent_metadata = _open_directory_without_symlinks(
        absolute.parent
    )
    temporary_name = f".{absolute.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    temporary_created = False
    try:
        before = _read_private_file_at(
            parent_descriptor,
            absolute.name,
            label=label,
            allow_missing=True,
        )
        before_identity = _receipt_identity(before)
        if expected_snapshot is not None:
            expected_exists = expected_snapshot.get("exists") is True
            if expected_exists:
                identity = expected_snapshot.get("identity")
                expected_digest = expected_snapshot.get("sha256")
                if (
                    not isinstance(identity, dict)
                    or not isinstance(identity.get("device"), int)
                    or isinstance(identity.get("device"), bool)
                    or not isinstance(identity.get("inode"), int)
                    or isinstance(identity.get("inode"), bool)
                    or not isinstance(expected_digest, str)
                    or not DIGEST_RE.fullmatch(expected_digest)
                ):
                    raise VerificationError("verified manifest snapshot is invalid")
                expected_identity = (
                    identity["device"],
                    identity["inode"],
                    expected_digest,
                )
                if before_identity != expected_identity:
                    raise VerificationError("release manifest changed after validation")
            elif (
                expected_snapshot.get("exists") is not False
                or expected_snapshot.get("identity") is not None
                or expected_snapshot.get("sha256") is not None
            ):
                raise VerificationError("verified manifest snapshot is invalid")
            elif before is not None:
                raise VerificationError("release manifest appeared after validation")

        write_flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_CLOEXEC
            | os.O_NOFOLLOW
        )
        descriptor = os.open(
            temporary_name,
            write_flags,
            0o600,
            dir_fd=parent_descriptor,
        )
        temporary_created = True
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

        current = _read_private_file_at(
            parent_descriptor,
            absolute.name,
            label=label,
            allow_missing=True,
        )
        if _receipt_identity(current) != before_identity:
            raise VerificationError(f"{label} changed before replacement")
        _assert_private_directory_fd(
            parent_descriptor,
            expected=parent_metadata,
        )
        os.replace(
            temporary_name,
            absolute.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_created = False
        os.fsync(parent_descriptor)
        _assert_private_directory_fd(
            parent_descriptor,
            expected=parent_metadata,
        )
        installed = _read_private_file_at(
            parent_descriptor,
            absolute.name,
            label=label,
            allow_missing=False,
        )
        if installed is None or installed[0] != data:
            raise VerificationError(f"{label} replacement could not be verified")
    finally:
        if temporary_created:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)


def replace_manifest_from_snapshot(
    path: Path,
    *,
    snapshot: dict[str, Any],
    payload: dict[str, Any],
    expected_channel: str,
) -> None:
    _validate_manifest_payload(payload, expected_channel=expected_channel)
    data = (
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    )
    _atomic_replace_private_file(
        path,
        data,
        label="release manifest",
        expected_snapshot=snapshot,
    )


def replace_private_text_receipt(path: Path, value: str, *, label: str) -> None:
    try:
        data = value.encode("utf-8")
    except UnicodeError as exc:
        raise VerificationError(f"{label} is not valid UTF-8") from exc
    _atomic_replace_private_file(
        path,
        data,
        label=label,
        expected_snapshot=None,
    )


def _load_updates(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict) and isinstance(payload.get("updates"), list):
        candidates = payload["updates"]
    else:
        raise VerificationError("structured EAS output does not contain an update list")
    if not candidates or not all(isinstance(item, dict) for item in candidates):
        raise VerificationError("structured EAS update list is empty or invalid")
    return candidates


def _branch_name(update: dict[str, Any]) -> str | None:
    branch = update.get("branch")
    if isinstance(branch, str):
        return branch
    if isinstance(branch, dict) and isinstance(branch.get("name"), str):
        return branch["name"]
    return None


def _normalize_single_ios(payload: Any, *, label: str) -> dict[str, Any]:
    updates = _load_updates(payload)
    if len(updates) != 1 or updates[0].get("platform") != "ios":
        raise VerificationError(f"{label} must contain exactly one ios update")
    update = updates[0]
    update_id = update.get("id")
    group_id = update.get("group")
    if not isinstance(update_id, str) or not UUID_RE.fullmatch(update_id):
        raise VerificationError(f"{label} has an invalid iOS update ID")
    if not isinstance(group_id, str) or not UUID_RE.fullmatch(group_id):
        raise VerificationError(f"{label} has an invalid update group ID")
    branch = _branch_name(update)
    runtime = update.get("runtimeVersion")
    commit = update.get("gitCommitHash")
    message = update.get("message")
    return {
        "update_id": update_id,
        "group_id": group_id,
        "branch": branch,
        "runtime_version": runtime,
        "commit_sha": commit,
        "message": message,
    }


def _channel_points_to(
    payload: Any, *, channel: str, branch: str, group_id: str
) -> bool:
    if not isinstance(payload, dict):
        return False
    current = payload.get("currentPage", payload)
    if (
        not isinstance(current, dict)
        or current.get("name") != channel
        or current.get("isPaused") is not False
    ):
        return False
    branches = current.get("updateBranches")
    # This manifest stores one singular active identity. A channel with more
    # than one branch is an EAS rollout, not a single active group; accepting
    # any matching branch would overstate rollout completion.
    if not isinstance(branches, list) or len(branches) != 1:
        return False
    candidate = branches[0]
    if not isinstance(candidate, dict) or candidate.get("name") != branch:
        return False
    groups = candidate.get("updateGroups")
    if not isinstance(groups, list) or len(groups) != 1:
        return False
    group = groups[0]
    if isinstance(group, dict) and group_id in {group.get("id"), group.get("group")}:
        return True
    if isinstance(group, list) and any(
        isinstance(update, dict) and update.get("group") == group_id
        for update in group
    ):
        return True
    return False


def verify_publish(
    publish_payload: Any,
    view_payload: Any,
    channel_payload: Any,
    *,
    channel: str,
    runtime_version: str,
    commit_sha: str | None,
    transaction_id: str | None,
) -> dict[str, Any]:
    published = _normalize_single_ios(publish_payload, label="publish response")
    viewed = _normalize_single_ios(view_payload, label="update:view response")
    comparable = ("update_id", "group_id", "branch", "runtime_version")
    for field in comparable:
        if published[field] != viewed[field]:
            raise VerificationError(f"structured EAS {field} mismatch")
    if published["runtime_version"] != runtime_version:
        raise VerificationError("structured EAS runtime version mismatch")
    if commit_sha is not None:
        if not SHA_RE.fullmatch(commit_sha):
            raise VerificationError("expected commit SHA is invalid")
        if published["commit_sha"] != commit_sha or viewed["commit_sha"] != commit_sha:
            raise VerificationError("structured EAS commit SHA mismatch")
    if transaction_id is not None:
        marker = f"[tx:{transaction_id}]"
        if marker not in str(published.get("message") or ""):
            raise VerificationError("structured EAS transaction marker mismatch")
    if not _channel_points_to(
        channel_payload,
        channel=channel,
        branch=str(published["branch"]),
        group_id=str(published["group_id"]),
    ):
        raise VerificationError("structured EAS channel mapping mismatch")
    return {
        "platform": "ios",
        "channel": channel,
        **published,
    }


def verify_source_update(
    payload: Any,
    *,
    group_id: str,
    update_id: str,
    runtime_version: str,
) -> dict[str, Any]:
    updates = _load_updates(payload)
    ios_updates = [update for update in updates if update.get("platform") == "ios"]
    source = _normalize_single_ios(
        ios_updates, label="rollback source update:view response"
    )
    if source["group_id"] != group_id or source["update_id"] != update_id:
        raise VerificationError("rollback source group/update mismatch")
    if source["runtime_version"] != runtime_version:
        raise VerificationError("rollback source runtime version mismatch")
    return {"verified": True, **source}


def find_transaction_candidate(
    payload: Any,
    *,
    transaction_id: str,
    branch: str | None,
    runtime_version: str,
) -> dict[str, Any]:
    if isinstance(payload, dict):
        candidates = payload.get("currentPage", payload.get("updates", []))
    else:
        candidates = payload
    if not isinstance(candidates, list):
        raise VerificationError("update:list JSON is invalid")
    marker = f"[tx:{transaction_id}]"
    groups: set[str] = set()
    for item in candidates:
        if not isinstance(item, dict):
            continue
        if marker not in str(item.get("message") or ""):
            continue
        item_branch = _branch_name(item) or item.get("branch")
        if branch is not None and item_branch != branch:
            raise VerificationError(
                "transaction lookup returned a contradictory branch"
            )
        if item.get("runtimeVersion") != runtime_version:
            raise VerificationError(
                "transaction lookup returned a contradictory runtime version"
            )
        group = item.get("group")
        if not isinstance(group, str) or not UUID_RE.fullmatch(group):
            raise VerificationError(
                "transaction lookup returned incomplete matching update metadata"
            )
        groups.add(group)
    if len(groups) > 1:
        raise VerificationError("transaction lookup is ambiguous across multiple groups")
    return {"found": bool(groups), "group_id": next(iter(groups), None)}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    artifact = commands.add_parser("artifact")
    artifact.add_argument("--input-dir", required=True, type=Path)
    artifact.add_argument("--platform", required=True)
    artifact.add_argument("--expected-digest")
    artifact.add_argument("--not-before-ns", type=int)

    manifest = commands.add_parser("manifest")
    manifest.add_argument("--manifest-file", required=True, type=Path)
    manifest.add_argument("--allow-missing", action="store_true")
    manifest.add_argument("--expected-channel")

    write_manifest = commands.add_parser("write-manifest")
    write_manifest.add_argument("--manifest-file", required=True, type=Path)
    write_manifest.add_argument("--snapshot-json", required=True, type=Path)
    write_manifest.add_argument("--payload-json", required=True, type=Path)
    write_manifest.add_argument("--expected-channel", required=True)

    write_receipt = commands.add_parser("write-private-receipt")
    write_receipt.add_argument("--receipt-file", required=True, type=Path)
    write_receipt.add_argument("--value", required=True)
    write_receipt.add_argument("--label", required=True)

    publish = commands.add_parser("publish")
    publish.add_argument("--publish-json", required=True, type=Path)
    publish.add_argument("--view-json", required=True, type=Path)
    publish.add_argument("--channel-json", required=True, type=Path)
    publish.add_argument("--channel", required=True)
    publish.add_argument("--runtime-version", required=True)
    publish.add_argument("--commit-sha")
    publish.add_argument("--transaction-id")

    source = commands.add_parser("source")
    source.add_argument("--view-json", required=True, type=Path)
    source.add_argument("--group-id", required=True)
    source.add_argument("--update-id", required=True)
    source.add_argument("--runtime-version", required=True)

    lookup = commands.add_parser("find-transaction")
    lookup.add_argument("--updates-json", required=True, type=Path)
    lookup.add_argument("--transaction-id", required=True)
    lookup.add_argument("--branch")
    lookup.add_argument("--runtime-version", required=True)

    state = commands.add_parser("state-paths")
    state.add_argument("--repo-root", required=True, type=Path)
    state.add_argument("--channel", required=True)
    state.add_argument("--scope", choices=("mobile", "rollback"), required=True)
    state.add_argument("--manifest-file")
    state.add_argument("--anchor-file")
    state.add_argument("--audit-file")
    state.add_argument("--migrate", action="store_true")
    state.add_argument("--read-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "artifact":
            result = validate_artifact(
                args.input_dir,
                platform=args.platform,
                expected_digest=args.expected_digest,
                not_before_ns=args.not_before_ns,
            )
        elif args.command == "manifest":
            result = validate_manifest(
                args.manifest_file,
                allow_missing=args.allow_missing,
                expected_channel=args.expected_channel,
            )
        elif args.command == "write-manifest":
            snapshot = _read_json(args.snapshot_json)
            payload = _read_json(args.payload_json)
            if not isinstance(snapshot, dict) or not isinstance(payload, dict):
                raise VerificationError("manifest write inputs must be JSON objects")
            replace_manifest_from_snapshot(
                args.manifest_file,
                snapshot=snapshot,
                payload=payload,
                expected_channel=args.expected_channel,
            )
            result = {"written": True}
        elif args.command == "write-private-receipt":
            replace_private_text_receipt(
                args.receipt_file,
                args.value,
                label=args.label,
            )
            result = {"written": True}
        elif args.command == "publish":
            result = verify_publish(
                _read_json(args.publish_json),
                _read_json(args.view_json),
                _read_json(args.channel_json),
                channel=args.channel,
                runtime_version=args.runtime_version,
                commit_sha=args.commit_sha,
                transaction_id=args.transaction_id,
            )
        elif args.command == "source":
            result = verify_source_update(
                _read_json(args.view_json),
                group_id=args.group_id,
                update_id=args.update_id,
                runtime_version=args.runtime_version,
            )
        elif args.command == "find-transaction":
            result = find_transaction_candidate(
                _read_json(args.updates_json),
                transaction_id=args.transaction_id,
                branch=args.branch,
                runtime_version=args.runtime_version,
            )
        else:
            result = resolve_mobile_state_paths(
                repo_root=args.repo_root,
                channel=args.channel,
                scope=args.scope,
                manifest_file=args.manifest_file,
                anchor_file=args.anchor_file,
                audit_file=args.audit_file,
                migrate=args.migrate,
                read_only=args.read_only,
            )
    except (OSError, VerificationError) as exc:
        print(f"verification error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
