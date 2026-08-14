#!/usr/bin/env python3
"""Fail closed unless a production OTA fits every eligible iOS native build."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import release
except ModuleNotFoundError:
    from scripts import release


MAX_BUILD_LIST_BYTES = 16 * 1024 * 1024
MAX_BUILD_COUNT = 1_000
_SHA_RE = re.compile(r"[0-9a-f]{40}")
_FINGERPRINT_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    re.IGNORECASE,
)


class CompatibilityError(RuntimeError):
    """The eligible native cohort or source compatibility cannot be proven."""


def _load_json(path: Path, *, label: str) -> Any:
    parent_descriptor = -1
    descriptor = -1
    try:
        parent_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        parent_flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        parent_descriptor = os.open(path.parent, parent_flags)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path.name, flags, dir_fd=parent_descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or metadata.st_size > MAX_BUILD_LIST_BYTES
        ):
            raise CompatibilityError(f"{label} is not a bounded regular file: {path}")
        chunks: list[bytes] = []
        remaining = MAX_BUILD_LIST_BYTES + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_BUILD_LIST_BYTES:
            raise CompatibilityError(f"{label} is not a bounded regular file: {path}")
        final_metadata = os.fstat(descriptor)
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_uid",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(
            getattr(metadata, field) != getattr(final_metadata, field)
            for field in stable_fields
        ):
            raise CompatibilityError(f"{label} changed while reading: {path}")
        current = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (
            final_metadata.st_dev,
            final_metadata.st_ino,
        ):
            raise CompatibilityError(f"{label} changed while reading: {path}")
        return json.loads(raw.decode("utf-8", errors="strict"))
    except CompatibilityError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CompatibilityError(f"invalid {label}: {path}: {error}") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor >= 0:
            os.close(parent_descriptor)


def _required_string(build: dict[str, Any], field: str) -> str:
    value = build.get(field)
    if not isinstance(value, str) or not value:
        raise CompatibilityError(f"eligible EAS build is missing {field}")
    return value


def _parse_timestamp(value: object, *, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise CompatibilityError(f"eligible EAS build has invalid {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CompatibilityError(f"eligible EAS build has invalid {field}") from error
    if parsed.tzinfo is None:
        raise CompatibilityError(f"eligible EAS build has timezone-free {field}")
    return parsed.astimezone(timezone.utc)


def _normalize_build(
    raw: object,
    *,
    runtime_version: str,
    channel: str,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise CompatibilityError("EAS build:list returned a non-object build")
    build_id = _required_string(raw, "id")
    if _UUID_RE.fullmatch(build_id) is None:
        raise CompatibilityError(f"eligible EAS build has invalid id: {build_id}")

    expected_fields = {
        "status": "FINISHED",
        "platform": "IOS",
        "distribution": "STORE",
        "buildProfile": "production",
        "channel": channel,
        "runtimeVersion": runtime_version,
    }
    for field, expected in expected_fields.items():
        actual = _required_string(raw, field)
        if actual != expected:
            raise CompatibilityError(
                f"EAS build {build_id} has ambiguous {field}: "
                f"expected={expected!r} actual={actual!r}"
            )

    commit_sha = _required_string(raw, "gitCommitHash")
    if _SHA_RE.fullmatch(commit_sha) is None:
        raise CompatibilityError(
            f"eligible EAS build {build_id} has invalid gitCommitHash"
        )
    fingerprint = raw.get("fingerprint")
    if not isinstance(fingerprint, dict):
        raise CompatibilityError(
            f"eligible EAS build {build_id} is missing fingerprint"
        )
    fingerprint_hash = fingerprint.get("hash")
    if (
        not isinstance(fingerprint_hash, str)
        or _FINGERPRINT_RE.fullmatch(fingerprint_hash) is None
    ):
        raise CompatibilityError(
            f"eligible EAS build {build_id} has invalid fingerprint.hash"
        )
    if "expirationDate" not in raw:
        raise CompatibilityError(
            f"eligible EAS build {build_id} is missing expirationDate"
        )
    expiration = _parse_timestamp(raw.get("expirationDate"), field="expirationDate")
    simulator = raw.get("isForIosSimulator")
    if not isinstance(simulator, bool):
        raise CompatibilityError(
            f"eligible EAS build {build_id} is missing isForIosSimulator"
        )
    return {
        "id": build_id.lower(),
        "status": "FINISHED",
        "platform": "IOS",
        "distribution": "STORE",
        "buildProfile": "production",
        "channel": channel,
        "runtimeVersion": runtime_version,
        "gitCommitHash": commit_sha,
        "fingerprint": {"hash": fingerprint_hash},
        "expirationDate": expiration.isoformat() if expiration is not None else None,
        "isForIosSimulator": simulator,
    }


def _normalized_list(
    payload: object,
    *,
    runtime_version: str,
    channel: str,
) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise CompatibilityError("EAS build:list response must be a JSON list")
    if len(payload) > MAX_BUILD_COUNT:
        raise CompatibilityError("EAS native build cohort exceeds the safety cap")
    return [
        _normalize_build(item, runtime_version=runtime_version, channel=channel)
        for item in payload
    ]


def _assert_unique_build_ids(builds: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for build in builds:
        build_id = str(build["id"])
        if build_id in seen:
            duplicates.add(build_id)
        seen.add(build_id)
    if duplicates:
        raise CompatibilityError(
            "ambiguous duplicate EAS build identity across paginated build:list: "
            + ", ".join(sorted(duplicates))
        )


def append_page(args: argparse.Namespace) -> int:
    aggregate_path = Path(args.aggregate_json)
    page = _normalized_list(
        _load_json(Path(args.page_json), label="EAS build page"),
        runtime_version=args.runtime_version,
        channel=args.channel,
    )
    aggregate = _normalized_list(
        _load_json(aggregate_path, label="EAS build aggregate"),
        runtime_version=args.runtime_version,
        channel=args.channel,
    )
    combined = [*aggregate, *page]
    if len(combined) > MAX_BUILD_COUNT:
        raise CompatibilityError("EAS native build cohort exceeds the safety cap")
    _assert_unique_build_ids(combined)
    temporary_name = f".{aggregate_path.name}.{os.getpid()}.tmp"
    parent_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    parent_flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    parent_descriptor = os.open(aggregate_path.parent, parent_flags)
    descriptor = -1
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(
            temporary_name, flags, 0o600, dir_fd=parent_descriptor
        )
        payload = (
            json.dumps(combined, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("short write to EAS build aggregate")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(
            temporary_name,
            aggregate_path.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        os.fsync(parent_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=parent_descriptor)
        except FileNotFoundError:
            pass
        os.close(parent_descriptor)
    print(len(page))
    return 0


def _resolve_now(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    parsed = _parse_timestamp(value, field="--now")
    if parsed is None:
        raise CompatibilityError("--now must be a timestamp")
    return parsed


def _changed_native_paths(repo: Path, build_sha: str, target_sha: str) -> list[str]:
    try:
        source = release._resolve_commit(repo, build_sha, label="EAS build git SHA")
        target = release._resolve_commit(repo, target_sha, label="OTA target SHA")
        release._require_ancestor(
            repo, source, target, label=f"EAS native build {build_sha[:12]}"
        )
        _base, _target, changes = release.git_changes(repo, source, target)
        native_assets = release._native_mobile_assets_for_refs(repo, (source, target))
    except (release.ReleaseError, OSError) as error:
        raise CompatibilityError(str(error)) from error

    blocked: set[str] = set()
    for change in changes:
        for path in change.paths:
            if path == "mobile/package.json":
                surface = release._mobile_package_surface_for_refs(
                    repo, source, target
                )
            else:
                surface = release.classify_path(
                    path, native_mobile_assets=native_assets
                )
            if surface == "mobile_native" or surface is None:
                blocked.add(path)
    return sorted(blocked)


def verify(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    builds = _normalized_list(
        _load_json(Path(args.builds_json), label="EAS build aggregate"),
        runtime_version=args.runtime_version,
        channel=args.channel,
    )
    _assert_unique_build_ids(builds)
    now = _resolve_now(args.now)
    eligible: list[dict[str, Any]] = []
    expired_artifact_count = 0
    for build in builds:
        expiration = _parse_timestamp(
            build["expirationDate"], field="expirationDate"
        )
        if expiration is not None and expiration <= now:
            # EAS CLI uses this timestamp to decide whether its hosted build
            # archive can still be downloaded/submitted. It does not revoke an
            # App Store/TestFlight binary already installed on user devices.
            expired_artifact_count += 1
        if build["isForIosSimulator"]:
            raise CompatibilityError(
                f"iOS Store build {build['id']} is unexpectedly marked as a simulator build"
            )
        eligible.append(build)
    if not eligible:
        raise CompatibilityError(
            "no non-simulator iOS Store build proves the production runtime"
        )

    target_sha = release._resolve_commit(repo, args.target_sha, label="OTA target SHA")
    blocked_by_build: dict[str, list[str]] = {}
    for source_sha in sorted({str(build["gitCommitHash"]) for build in eligible}):
        blocked = _changed_native_paths(repo, source_sha, target_sha)
        if blocked:
            blocked_by_build[source_sha] = blocked
    if blocked_by_build:
        details: list[str] = []
        for source_sha, paths in blocked_by_build.items():
            rendered = ", ".join(paths[:20])
            if len(paths) > 20:
                rendered += f", ... (+{len(paths) - 20})"
            details.append(f"{source_sha[:12]} -> {rendered}")
        raise CompatibilityError(
            "native-sensitive changes exist after an eligible build: "
            + "; ".join(details)
        )

    fingerprints = sorted(
        {str(build["fingerprint"]["hash"]) for build in eligible}
    )
    if len(fingerprints) != 1:
        raise CompatibilityError(
            "ambiguous native fingerprints in the eligible production runtime cohort: "
            + ", ".join(fingerprints)
        )

    print(
        json.dumps(
            {
                "channel": args.channel,
                "runtime_version": args.runtime_version,
                "target_sha": target_sha,
                "eligible_build_count": len(eligible),
                "eligible_build_ids": sorted(str(build["id"]) for build in eligible),
                "cohort": sorted(
                    (
                        {
                            "id": str(build["id"]),
                            "git_commit_hash": str(build["gitCommitHash"]),
                            "native_fingerprint": str(build["fingerprint"]["hash"]),
                            "artifact_expiration_date": build["expirationDate"],
                        }
                        for build in eligible
                    ),
                    key=lambda item: item["id"],
                ),
                "native_fingerprint": fingerprints[0],
                "expired_artifact_count": expired_artifact_count,
            },
            sort_keys=True,
        )
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    append = subparsers.add_parser("append-page")
    append.add_argument("--page-json", required=True)
    append.add_argument("--aggregate-json", required=True)
    append.add_argument("--runtime-version", required=True)
    append.add_argument("--channel", required=True)
    append.set_defaults(handler=append_page)

    check = subparsers.add_parser("verify")
    check.add_argument("--repo-root", required=True)
    check.add_argument("--target-sha", required=True)
    check.add_argument("--runtime-version", required=True)
    check.add_argument("--channel", required=True)
    check.add_argument("--builds-json", required=True)
    check.add_argument("--now")
    check.set_defaults(handler=verify)
    return parser


def main() -> int:
    try:
        args = _parser().parse_args()
        return int(args.handler(args))
    except CompatibilityError as error:
        print(
            "Production OTA native compatibility blocked: "
            f"{error}. Publish a new native build with a new runtime version.",
            file=sys.stderr,
        )
        return 2
    except release.ReleaseError as error:
        print(
            "Production OTA native compatibility blocked: "
            f"{error}. Publish a new native build with a new runtime version.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
