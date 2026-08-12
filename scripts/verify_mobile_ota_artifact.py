#!/usr/bin/env python3
"""Fail-closed validation for transaction-local iOS EAS Update artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class VerificationError(ValueError):
    """Raised when an OTA proof is incomplete or contradictory."""


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"invalid JSON file {path}: {exc}") from exc


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


def validate_manifest(path: Path, *, allow_missing: bool) -> dict[str, Any]:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        if allow_missing:
            return {"exists": False, "schema_version": None}
        raise VerificationError(f"release manifest is missing: {path}") from None
    except OSError as exc:
        raise VerificationError(f"release manifest is unavailable: {exc}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise VerificationError("release manifest must be a regular non-symlink file")
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise VerificationError("release manifest must be a JSON object")
    schema = payload.get("schema_version", 1)
    if schema not in {1, 2}:
        raise VerificationError("release manifest schema is unsupported")
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
    return {"exists": True, "schema_version": schema}


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
            )
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
        else:
            result = find_transaction_candidate(
                _read_json(args.updates_json),
                transaction_id=args.transaction_id,
                branch=args.branch,
                runtime_version=args.runtime_version,
            )
    except (OSError, VerificationError) as exc:
        print(f"verification error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
