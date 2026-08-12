#!/usr/bin/env python3
"""Issue and verify reusable release-validation credentials.

Credentials intentionally bind to the Git *tree*, not the commit. A metadata-only
rebase/amend can therefore reuse evidence, while source, command, dependency,
toolchain, result-log, profile, or expiry drift fails closed.

Operational state is shared by every worktree below Git's common directory::

    <git-common-dir>/reva-release-state/

Directories are mode 0700 and files are mode 0600. Credential writes are atomic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
DEFAULT_TTL_SECONDS = 6 * 60 * 60
PROFILE_VERSION = "1"
_SAFE_PROFILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
_COMMON_LOCKFILES = ("pnpm-lock.yaml",)
_PROFILE_LOCKFILES = {
    "backend": ("backend/requirements.lock",),
    "frontend": ("frontend/package-lock.json",),
    "mobile": ("mobile/package-lock.json",),
    "mac": ("apps/mac/Package.resolved",),
    "quick": ("frontend/package-lock.json", "mobile/package-lock.json"),
    "all": (
        "backend/requirements.lock",
        "frontend/package-lock.json",
        "mobile/package-lock.json",
        "apps/mac/Package.resolved",
    ),
    "structural": (),
}


@dataclass(frozen=True)
class CredentialVerdict:
    reusable: bool
    reason: str
    credential: dict[str, Any] | None = None


def _run_text(argv: Sequence[str], *, cwd: Path) -> str:
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(argv)}: {detail}")
    return completed.stdout.strip()


def _worktree_is_dirty(repo: Path) -> bool:
    return bool(
        _run_text(
            ["git", "status", "--porcelain=v1", "--untracked-files=normal"],
            cwd=repo,
        )
    )


def _ensure_private_directory(path: Path) -> Path:
    if path.is_symlink():
        raise ValueError(f"refusing symlinked state directory: {path}")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"state path is not a private directory: {path}")
    path.chmod(0o700)
    return path


def validation_state_dir(repo: Path | str) -> Path:
    repo_path = Path(repo).resolve()
    common_raw = _run_text(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=repo_path,
    )
    common = Path(common_raw)
    if not common.is_absolute():
        common = (repo_path / common).resolve()
    return _ensure_private_directory(common / "reva-release-state")


def credential_path(repo: Path | str, profile: str) -> Path:
    if not _SAFE_PROFILE.fullmatch(profile):
        raise ValueError(f"invalid validation profile: {profile!r}")
    directory = _ensure_private_directory(validation_state_dir(repo) / "credentials")
    return directory / f"{profile}.json"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _private_regular_log(path: Path) -> tuple[bool, str]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False, f"log missing: {path}"
    if stat.S_ISLNK(metadata.st_mode):
        return False, f"log is a symlink: {path}"
    if not stat.S_ISREG(metadata.st_mode):
        return False, f"log is not a regular file: {path}"
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        return False, f"log is not private (expected mode 0600): {path}"
    return True, "ok"


def _command_version(argv: Sequence[str], *, cwd: Path) -> str:
    try:
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "__missing__"
    output = (completed.stdout or completed.stderr).strip().splitlines()
    if completed.returncode != 0 or not output:
        return "__missing__"
    return output[0]


def collect_toolchain(repo: Path | str) -> dict[str, str]:
    repo_path = Path(repo).resolve()
    return {
        "python": platform.python_version(),
        "node": _command_version(["node", "--version"], cwd=repo_path),
        "npm": _command_version(["npm", "--version"], cwd=repo_path),
        "swift": _command_version(["swift", "--version"], cwd=repo_path),
        "os": platform.platform(),
    }


def _normalize_commands(commands: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for command in commands:
        argv = command.get("argv")
        if not isinstance(argv, (list, tuple)) or not argv or not all(
            isinstance(part, str) and part for part in argv
        ):
            raise ValueError("every validation command requires a non-empty string argv")
        name = command.get("name")
        cwd = command.get("cwd", ".")
        if not isinstance(name, str) or not name or not isinstance(cwd, str) or not cwd:
            raise ValueError("every validation command requires name and cwd strings")
        normalized.append(
            {
                "name": name,
                "argv": list(argv),
                "cwd": cwd,
                "blocking": bool(command.get("blocking", True)),
            }
        )
    return normalized


def _lockfile_names(profile: str, explicit: Sequence[str] | None) -> list[str]:
    if explicit is not None:
        names = list(explicit)
    else:
        names = [*_COMMON_LOCKFILES, *_PROFILE_LOCKFILES.get(profile, ())]
    return sorted(dict.fromkeys(names))


def collect_lock_hashes(
    repo: Path | str,
    profile: str,
    lock_paths: Sequence[str] | None = None,
) -> dict[str, str]:
    repo_path = Path(repo).resolve()
    result: dict[str, str] = {}
    for relative in _lockfile_names(profile, lock_paths):
        candidate = (repo_path / relative).resolve()
        try:
            candidate.relative_to(repo_path)
        except ValueError as exc:
            raise ValueError(f"lockfile escapes repository: {relative}") from exc
        if candidate.is_symlink():
            raise ValueError(f"refusing symlinked lockfile: {relative}")
        result[relative] = _sha256_file(candidate) if candidate.is_file() else "__missing__"
    return result


def _collect_logs(logs: Mapping[str, Path | str]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for name, raw_path in sorted(logs.items()):
        path = Path(raw_path).absolute()
        private, reason = _private_regular_log(path)
        if not private:
            raise ValueError(reason)
        result[name] = {"path": str(path), "sha256": _sha256_file(path)}
    return result


def _identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": payload.get("schema_version"),
        "tree": payload.get("tree"),
        "profile": payload.get("profile"),
        "profile_version": payload.get("profile_version"),
        "commands": payload.get("commands"),
        "lockfiles": payload.get("lockfiles"),
        "toolchain": payload.get("toolchain"),
        "logs": payload.get("logs"),
        "result": payload.get("result"),
    }


def _identity_digest(payload: Mapping[str, Any]) -> str:
    digest_input = {
        **_identity(payload),
        "commit_at_issue": payload.get("commit_at_issue"),
        "issued_at": payload.get("issued_at"),
        "expires_at": payload.get("expires_at"),
    }
    encoded = json.dumps(
        digest_input, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_credential(
    *,
    repo: Path | str,
    profile_name: str,
    profile_version: str,
    commands: Sequence[Mapping[str, Any]],
    logs: Mapping[str, Path | str],
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: int | float | None = None,
    toolchain: Mapping[str, str] | None = None,
    lock_paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    if ttl_seconds <= 0:
        raise ValueError("credential TTL must be positive")
    if not _SAFE_PROFILE.fullmatch(profile_name):
        raise ValueError(f"invalid validation profile: {profile_name!r}")
    repo_path = Path(repo).resolve()
    if _worktree_is_dirty(repo_path):
        raise ValueError("refusing to issue a credential for a dirty worktree")
    issued_at = int(time.time() if now is None else now)
    normalized_commands = _normalize_commands(commands)
    command_names = [command["name"] for command in normalized_commands]
    if len(command_names) != len(set(command_names)):
        raise ValueError("validation command names must be unique")
    if set(logs) != set(command_names):
        raise ValueError("log bindings must exactly match validation command names")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tree": _run_text(["git", "rev-parse", "HEAD^{tree}"], cwd=repo_path),
        "commit_at_issue": _run_text(["git", "rev-parse", "HEAD"], cwd=repo_path),
        "profile": profile_name,
        "profile_version": str(profile_version),
        "commands": normalized_commands,
        "lockfiles": collect_lock_hashes(repo_path, profile_name, lock_paths),
        "toolchain": dict(sorted((toolchain or collect_toolchain(repo_path)).items())),
        "logs": _collect_logs(logs),
        "result": "pass",
        "issued_at": issued_at,
        "expires_at": issued_at + int(ttl_seconds),
    }
    payload["identity_sha256"] = _identity_digest(payload)
    return payload


def build_fingerprint(
    repo: Path | str,
    profile: str,
    commands: Sequence[Mapping[str, Any]],
    log_paths: Mapping[str, Path | str],
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: int | float | None = None,
    *,
    profile_version: str = PROFILE_VERSION,
    toolchain: Mapping[str, str] | None = None,
    lock_paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Compatibility API used by the release planner."""
    return build_credential(
        repo=repo,
        profile_name=profile,
        profile_version=profile_version,
        commands=commands,
        logs=log_paths,
        ttl_seconds=ttl_seconds,
        now=now,
        toolchain=toolchain,
        lock_paths=lock_paths,
    )


def write_credential_atomic(path: Path | str, credential: Mapping[str, Any]) -> None:
    destination = Path(path).absolute()
    parent = _ensure_private_directory(destination.parent)
    if destination.is_symlink():
        raise ValueError(f"refusing symlinked credential path: {destination}")
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".tmp-", dir=parent)
        temporary = Path(temporary_name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(credential, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        destination.chmod(0o600)
        directory_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _read_stored(path: Path) -> CredentialVerdict:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return CredentialVerdict(False, "credential missing")
    if stat.S_ISLNK(metadata.st_mode):
        return CredentialVerdict(False, "credential is a symlink")
    if not stat.S_ISREG(metadata.st_mode):
        return CredentialVerdict(False, "credential is not a regular file")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        return CredentialVerdict(False, "credential is not private")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return CredentialVerdict(False, "credential is invalid JSON")
    if not isinstance(payload, dict):
        return CredentialVerdict(False, "credential payload is invalid")
    return CredentialVerdict(True, "loaded", payload)


def _verify_log_bindings(logs: object) -> str | None:
    if not isinstance(logs, dict) or not logs:
        return "credential log bindings are invalid"
    for name, binding in logs.items():
        if not isinstance(name, str) or not isinstance(binding, dict):
            return "credential log bindings are invalid"
        path_raw = binding.get("path")
        expected_hash = binding.get("sha256")
        if not isinstance(path_raw, str) or not isinstance(expected_hash, str):
            return "credential log bindings are invalid"
        path = Path(path_raw)
        private, reason = _private_regular_log(path)
        if not private:
            return reason
        if _sha256_file(path) != expected_hash:
            return f"log hash mismatch: {name}"
    return None


def load_reusable_credential(
    path: Path | str,
    expected_fingerprint: Mapping[str, Any],
    now: int | float | None = None,
) -> dict[str, Any] | None:
    loaded = _read_stored(Path(path).absolute())
    if not loaded.reusable or loaded.credential is None:
        return None
    stored = loaded.credential
    current_time = int(time.time() if now is None else now)
    if stored.get("result") != "pass" or stored.get("expires_at", 0) < current_time:
        return None
    if stored.get("identity_sha256") != _identity_digest(stored):
        return None
    if _identity(stored) != _identity(expected_fingerprint):
        return None
    if _verify_log_bindings(stored.get("logs")) is not None:
        return None
    return stored


def verify_credential(
    *,
    repo: Path | str,
    path: Path | str,
    profile_name: str,
    profile_version: str,
    commands: Sequence[Mapping[str, Any]],
    now: int | float | None = None,
    toolchain: Mapping[str, str] | None = None,
    lock_paths: Sequence[str] | None = None,
) -> CredentialVerdict:
    loaded = _read_stored(Path(path).absolute())
    if not loaded.reusable or loaded.credential is None:
        return loaded
    stored = loaded.credential
    current_time = int(time.time() if now is None else now)
    if stored.get("schema_version") != SCHEMA_VERSION:
        return CredentialVerdict(False, "credential schema is invalid")
    if stored.get("result") != "pass":
        return CredentialVerdict(False, "credential result is not pass")
    expires_at = stored.get("expires_at")
    if not isinstance(expires_at, int) or expires_at < current_time:
        return CredentialVerdict(False, "credential expired")
    if stored.get("identity_sha256") != _identity_digest(stored):
        return CredentialVerdict(False, "credential identity is invalid")

    repo_path = Path(repo).resolve()
    expected = {
        "tree": _run_text(["git", "rev-parse", "HEAD^{tree}"], cwd=repo_path),
        "profile": profile_name,
        "profile_version": str(profile_version),
        "commands": _normalize_commands(commands),
        "lockfiles": collect_lock_hashes(repo_path, profile_name, lock_paths),
        "toolchain": dict(sorted((toolchain or collect_toolchain(repo_path)).items())),
    }
    for field in ("tree", "profile", "profile_version", "commands", "lockfiles", "toolchain"):
        if stored.get(field) != expected[field]:
            label = "lock" if field == "lockfiles" else field
            return CredentialVerdict(False, f"{label} fingerprint mismatch")
    if _worktree_is_dirty(repo_path):
        return CredentialVerdict(False, "worktree is dirty")
    log_error = _verify_log_bindings(stored.get("logs"))
    if log_error:
        return CredentialVerdict(False, log_error)
    return CredentialVerdict(True, "reusable", stored)


def _load_json(path: str) -> Any:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("issue", "verify"):
        child = subparsers.add_parser(command)
        child.add_argument("--repo", default=".")
        child.add_argument("--profile", required=True)
        child.add_argument("--profile-version", default=PROFILE_VERSION)
        child.add_argument("--commands-json", required=True)
        child.add_argument("--toolchain-json")
        child.add_argument("--lock", action="append", dest="lock_paths")
        child.add_argument("--path")
    issue = subparsers.choices["issue"]
    issue.add_argument("--logs-json", required=True)
    issue.add_argument("--ttl-seconds", type=int, default=DEFAULT_TTL_SECONDS)
    subparsers.add_parser("state-dir").add_argument("--repo", default=".")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "state-dir":
        print(validation_state_dir(args.repo))
        return 0

    repo = Path(args.repo).resolve()
    path = Path(args.path) if args.path else credential_path(repo, args.profile)
    commands = _load_json(args.commands_json)
    toolchain = _load_json(args.toolchain_json) if args.toolchain_json else None
    if args.command == "issue":
        logs = _load_json(args.logs_json)
        credential = build_credential(
            repo=repo,
            profile_name=args.profile,
            profile_version=args.profile_version,
            commands=commands,
            logs=logs,
            ttl_seconds=args.ttl_seconds,
            toolchain=toolchain,
            lock_paths=args.lock_paths,
        )
        write_credential_atomic(path, credential)
        print(json.dumps({"status": "issued", "path": str(path), "tree": credential["tree"]}))
        return 0

    verdict = verify_credential(
        repo=repo,
        path=path,
        profile_name=args.profile,
        profile_version=args.profile_version,
        commands=commands,
        toolchain=toolchain,
        lock_paths=args.lock_paths,
    )
    print(
        json.dumps(
            {"status": "reusable" if verdict.reusable else "miss", "reason": verdict.reason},
            ensure_ascii=False,
        )
    )
    return 0 if verdict.reusable else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"status": "error", "reason": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
