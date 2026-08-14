#!/usr/bin/env python3
"""Build internal validation evidence and inspect legacy credentials.

The command-line interface is intentionally read-only: it cannot issue a passing
credential from caller-provided logs.  More importantly, local credential reuse is
disabled because files writable by the same UID are not an independent attestation.
Release validation must therefore execute the full suite for every publication.

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
import secrets
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 2
DEFAULT_TTL_SECONDS = 6 * 60 * 60
PROFILE_VERSION = "2"
_SAFE_PROFILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
_GIT_ENV_OVERRIDES = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_NOSYSTEM",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_SYSTEM",
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_WORK_TREE",
)
_COMMON_LOCKFILES = ("pnpm-lock.yaml",)
_PROFILE_LOCKFILES = {
    "backend": ("backend/requirements.lock", "backend/requirements-dev.txt"),
    "frontend": ("frontend/package-lock.json",),
    "mobile": ("mobile/package-lock.json",),
    "mac": ("apps/mac/Package.resolved",),
    "quick": ("frontend/package-lock.json", "mobile/package-lock.json"),
    "all": (
        "backend/requirements.lock",
        "backend/requirements-dev.txt",
        "frontend/package-lock.json",
        "mobile/package-lock.json",
        "apps/mac/Package.resolved",
    ),
    "structural": (),
}
_PROFILE_DEPENDENCY_COMPONENTS = {
    "backend": ("backend",),
    "frontend": ("frontend",),
    "mobile": ("mobile",),
    "quick": ("frontend", "mobile"),
    "all": ("backend", "frontend", "mobile"),
    "structural": (),
}
CANONICAL_VALIDATION_ENVIRONMENT = {
    "APP_ENV": "test",
    "DATABASE_URL": "sqlite:///:memory:",
    "GARMIN_ENCRYPTION_KEY": "mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=",
    "NODE_ENV": "test",
    "SECRET_KEY": "test-secret-key-32-chars-minimum!!",
    # The backend fixture interprets any value as an explicit PostgreSQL URL.
    # A sentinel binds the required absence without putting it in the process env.
    "TEST_DATABASE_URL": "__unset__",
    "TZ": "Asia/Shanghai",
}
_NPM_ENVIRONMENT_OVERRIDES = frozenset(
    {
        "BASH_ENV",
        "ENV",
        "NODE_OPTIONS",
        "NODE_PATH",
        "NPM_CONFIG_GLOBALCONFIG",
        "NPM_CONFIG_NODE_OPTIONS",
        "NPM_CONFIG_SCRIPT_SHELL",
        "NPM_CONFIG_USERCONFIG",
        "npm_config_globalconfig",
        "npm_config_node_options",
        "npm_config_script_shell",
        "npm_config_userconfig",
    }
)


@dataclass(frozen=True)
class CredentialVerdict:
    reusable: bool
    reason: str
    credential: dict[str, Any] | None = None


@dataclass(frozen=True)
class ValidationContext:
    dependency_state: dict[str, str]
    toolchain: dict[str, str]
    validation_environment: dict[str, str]


def _run_text(argv: Sequence[str], *, cwd: Path) -> str:
    environment = os.environ.copy()
    for name in _GIT_ENV_OVERRIDES:
        environment.pop(name, None)
    for name in tuple(environment):
        if name.startswith("GIT_CONFIG_KEY_") or name.startswith(
            "GIT_CONFIG_VALUE_"
        ):
            environment.pop(name, None)
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
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


def _private_directory_fd(path: Path, *, repair_created_mode: bool = False) -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        if path.is_symlink():
            raise ValueError(f"refusing symlinked state directory: {path}") from error
        raise ValueError(f"state path is not a private directory: {path}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"state path is not a private directory: {path}")
        if metadata.st_uid != os.getuid():
            raise ValueError(f"state directory owner mismatch: {path}")
        if repair_created_mode and stat.S_IMODE(metadata.st_mode) != 0o700:
            os.fchmod(descriptor, 0o700)
            metadata = os.fstat(descriptor)
        if stat.S_IMODE(metadata.st_mode) != 0o700:
            raise ValueError(f"state directory permissions must be 0700: {path}")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _ensure_private_directory(path: Path) -> Path:
    created = False
    try:
        path.mkdir(mode=0o700)
        created = True
    except FileExistsError:
        pass
    descriptor = _private_directory_fd(path, repair_created_mode=created)
    os.close(descriptor)
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


def _private_regular_metadata_error(
    metadata: os.stat_result,
    *,
    label: str,
    path: Path,
) -> str | None:
    if not stat.S_ISREG(metadata.st_mode):
        return f"{label} is not a regular file: {path}"
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        return f"{label} permissions must be 0600: {path}"
    if metadata.st_nlink != 1:
        return f"{label} must have exactly one hard link: {path}"
    if metadata.st_uid != os.getuid():
        return f"{label} owner mismatch: {path}"
    return None


def _open_private_regular(path: Path, *, label: str) -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        raise
    except OSError as error:
        if path.is_symlink():
            raise ValueError(f"{label} is a symlink: {path}") from error
        raise ValueError(f"{label} is unavailable: {path}") from error
    try:
        reason = _private_regular_metadata_error(
            os.fstat(descriptor), label=label, path=path
        )
        if reason:
            raise ValueError(reason)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _sha256_private_regular(path: Path, *, label: str) -> str:
    descriptor = _open_private_regular(path, label=label)
    digest = hashlib.sha256()
    try:
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _command_version(argv: Sequence[str], *, cwd: Path) -> str:
    environment = os.environ.copy()
    for name in tuple(environment):
        normalized = name.lower().replace("-", "_")
        if name in {"NODE_OPTIONS", "NODE_PATH"} or normalized in {
            "npm_config_globalconfig",
            "npm_config_node_options",
            "npm_config_script_shell",
            "npm_config_userconfig",
        }:
            environment.pop(name, None)
    try:
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
            env=environment,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "__missing__"
    output = (completed.stdout or completed.stderr).strip().splitlines()
    if completed.returncode != 0 or not output:
        return "__missing__"
    return output[0]


def _scrub_execution_environment() -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if name in {"HOME", "LANG", "LC_ALL", "LOGNAME", "PATH", "SHELL", "TMPDIR", "USER"}
        or name.startswith("LC_")
    }
    return environment


def _safe_owned_directory(path: Path, *, label: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise RuntimeError(f"{label} missing: {path}") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"{label} is not a real directory: {path}")
    if metadata.st_uid != os.getuid():
        raise RuntimeError(f"{label} owner mismatch: {path}")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise RuntimeError(f"{label} is group/world writable: {path}")


def _canonical_json_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _run_json_command(argv: Sequence[str], *, cwd: Path, label: str) -> Any:
    try:
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
            env=_scrub_execution_environment(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"{label} inventory unavailable") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            f"{label} inventory failed ({completed.returncode}): {detail}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{label} inventory is not valid JSON") from error


def _collect_backend_dependency_state(repo: Path) -> str:
    venv = repo / "backend" / "venv"
    _safe_owned_directory(venv, label="backend validation venv")
    python = venv / "bin" / "python"
    try:
        python_metadata = python.lstat()
    except FileNotFoundError as error:
        raise RuntimeError(f"backend validation interpreter missing: {python}") from error
    resolved_python = python.resolve()
    try:
        resolved_metadata = resolved_python.stat()
    except FileNotFoundError as error:
        raise RuntimeError(
            f"backend validation interpreter target missing: {python}"
        ) from error
    if (
        not (stat.S_ISREG(python_metadata.st_mode) or stat.S_ISLNK(python_metadata.st_mode))
        or not stat.S_ISREG(resolved_metadata.st_mode)
        or resolved_metadata.st_uid not in {0, os.getuid()}
        or stat.S_IMODE(resolved_metadata.st_mode) & 0o022
        or not os.access(python, os.X_OK)
    ):
        raise RuntimeError(f"backend validation interpreter is unsafe: {python}")
    payload = _run_json_command(
        [
            str(python),
            "-I",
            "-c",
            (
                "import importlib.metadata,json,platform,re;"
                "c=lambda n:re.sub(r'[-_.]+','-',n).lower();"
                "rows=sorted((c(str(d.metadata.get('Name') or '')),str(d.version)) "
                "for d in importlib.metadata.distributions());"
                "assert rows and all(n for n,_ in rows);"
                "assert len({n for n,_ in rows})==len(rows);"
                "print(json.dumps({'python':platform.python_version(),'distributions':rows},separators=(',',':')))"
            ),
        ],
        cwd=repo / "backend",
        label="backend installed dependency",
    )
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("python"), str)
        or not isinstance(payload.get("distributions"), list)
        or not payload["distributions"]
    ):
        raise RuntimeError("backend installed dependency inventory is empty")
    check = subprocess.run(
        [str(python), "-I", "-m", "pip", "check"],
        cwd=repo / "backend",
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
        env=_scrub_execution_environment(),
    )
    if check.returncode != 0:
        detail = (check.stderr or check.stdout).strip()
        raise RuntimeError(f"backend dependency check failed: {detail}")
    return _canonical_json_digest(payload)


def _collect_node_dependency_state(repo: Path, component: str) -> str:
    workspace = repo / component
    node_modules = workspace / "node_modules"
    _safe_owned_directory(node_modules, label=f"{component} node_modules")
    installed_lock = node_modules / ".package-lock.json"
    try:
        installed_metadata = installed_lock.lstat()
    except FileNotFoundError as error:
        raise RuntimeError(
            f"{component} installed package lock missing or unsafe"
        ) from error
    if (
        stat.S_ISLNK(installed_metadata.st_mode)
        or not stat.S_ISREG(installed_metadata.st_mode)
        or installed_metadata.st_uid != os.getuid()
        or stat.S_IMODE(installed_metadata.st_mode) & 0o022
    ):
        raise RuntimeError(f"{component} installed package lock missing or unsafe")
    inventory = _run_json_command(
        ["npm", "ls", "--all", "--json"],
        cwd=workspace,
        label=f"{component} installed dependency",
    )
    if not isinstance(inventory, dict) or inventory.get("problems"):
        raise RuntimeError(f"{component} installed dependency inventory is invalid")
    return _canonical_json_digest(
        {
            "tree": inventory,
            "installed_lock_sha256": _sha256_file(installed_lock),
        }
    )


def collect_dependency_state(
    repo: Path | str, profile: str
) -> dict[str, str]:
    """Hash the exact installed dependency trees used by a validation profile."""

    repo_path = Path(repo).resolve()
    try:
        components = _PROFILE_DEPENDENCY_COMPONENTS[profile]
    except KeyError as error:
        raise ValueError(f"unknown validation dependency profile: {profile}") from error
    result: dict[str, str] = {}
    for component in components:
        if component == "backend":
            result[component] = _collect_backend_dependency_state(repo_path)
        else:
            result[component] = _collect_node_dependency_state(repo_path, component)
    if components and set(result) != set(components):
        raise RuntimeError("validation dependency inventory is incomplete")
    return result


def _normalize_dependency_state(
    repo: Path,
    profile: str,
    dependency_state: Mapping[str, str] | None,
) -> dict[str, str]:
    expected = set(_PROFILE_DEPENDENCY_COMPONENTS.get(profile, ()))
    if profile not in _PROFILE_DEPENDENCY_COMPONENTS:
        raise ValueError(f"unknown validation dependency profile: {profile}")
    resolved = (
        collect_dependency_state(repo, profile)
        if dependency_state is None
        else dict(dependency_state)
    )
    if set(resolved) != expected:
        raise ValueError(
            "dependency state must exactly bind profile components: "
            + ", ".join(sorted(expected))
        )
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in resolved.values()):
        raise ValueError("dependency state values must be SHA-256 digests")
    return dict(sorted(resolved.items()))


def _normalize_validation_environment(
    validation_environment: Mapping[str, str] | None,
) -> dict[str, str]:
    resolved = dict(
        CANONICAL_VALIDATION_ENVIRONMENT
        if validation_environment is None
        else validation_environment
    )
    if not resolved or any(
        not isinstance(name, str)
        or not name
        or not isinstance(value, str)
        for name, value in resolved.items()
    ):
        raise ValueError("validation environment binding must be non-empty strings")
    return dict(sorted(resolved.items()))


def collect_toolchain(
    repo: Path | str, *, profile: str = "all"
) -> dict[str, str]:
    repo_path = Path(repo).resolve()
    backend_python = repo_path / "backend" / "venv" / "bin" / "python"
    backend_version = "__missing__"
    if backend_python.exists():
        backend_version = _command_version(
            [str(backend_python), "--version"], cwd=repo_path
        )
    toolchain = {
        "orchestrator_python": platform.python_version(),
        "backend_python": backend_version,
        "node": _command_version(["node", "--version"], cwd=repo_path),
        "npm": _command_version(["npm", "--version"], cwd=repo_path),
        "swift": _command_version(["swift", "--version"], cwd=repo_path),
        "os": platform.platform(),
    }
    components = set(_PROFILE_DEPENDENCY_COMPONENTS.get(profile, ()))
    if profile not in _PROFILE_DEPENDENCY_COMPONENTS:
        raise ValueError(f"unknown validation dependency profile: {profile}")
    required: set[str] = set()
    if components & {"frontend", "mobile"}:
        required.update({"node", "npm"})
    if profile in {"all", "mac"}:
        required.add("swift")
    if "backend" in components:
        required.add("backend_python")
    missing = sorted(
        name for name, value in toolchain.items()
        if name in required and value == "__missing__"
    )
    if missing:
        raise RuntimeError("required toolchain command missing: " + ", ".join(missing))
    return toolchain


def collect_validation_context(
    repo: Path | str, profile: str
) -> ValidationContext:
    """Capture the one context reused by credential check, execution, and issue."""

    repo_path = Path(repo).resolve()
    dependency_state = collect_dependency_state(repo_path, profile)
    return ValidationContext(
        dependency_state=dependency_state,
        toolchain=collect_toolchain(repo_path, profile=profile),
        validation_environment=_normalize_validation_environment(None),
    )


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
        result[name] = {
            "path": str(path),
            "sha256": _sha256_private_regular(path, label="log"),
        }
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
        "dependency_state": payload.get("dependency_state"),
        "validation_environment": payload.get("validation_environment"),
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
    dependency_state: Mapping[str, str] | None = None,
    validation_environment: Mapping[str, str] | None = None,
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
        "toolchain": dict(
            sorted((toolchain or collect_toolchain(repo_path, profile=profile_name)).items())
        ),
        "dependency_state": _normalize_dependency_state(
            repo_path, profile_name, dependency_state
        ),
        "validation_environment": _normalize_validation_environment(
            validation_environment
        ),
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
    dependency_state: Mapping[str, str] | None = None,
    validation_environment: Mapping[str, str] | None = None,
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
        dependency_state=dependency_state,
        validation_environment=validation_environment,
    )


def write_credential_atomic(path: Path | str, credential: Mapping[str, Any]) -> None:
    destination = Path(path).absolute()
    parent = _ensure_private_directory(destination.parent)
    parent_descriptor = _private_directory_fd(parent)
    destination_name = destination.name
    existing_descriptor: int | None = None
    temporary_descriptor: int | None = None
    temporary_name: str | None = None
    try:
        try:
            flags = os.O_RDONLY
            flags |= getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            existing_descriptor = os.open(
                destination_name, flags, dir_fd=parent_descriptor
            )
        except FileNotFoundError:
            existing_descriptor = None
        except OSError as error:
            raise ValueError(
                f"refusing unsafe existing credential path: {destination}"
            ) from error
        if existing_descriptor is not None:
            reason = _private_regular_metadata_error(
                os.fstat(existing_descriptor), label="credential", path=destination
            )
            if reason:
                raise ValueError(reason)
            os.close(existing_descriptor)
            existing_descriptor = None

        create_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        create_flags |= getattr(os, "O_CLOEXEC", 0)
        create_flags |= getattr(os, "O_NOFOLLOW", 0)
        for _attempt in range(100):
            candidate = f".tmp-{os.getpid()}-{secrets.token_hex(8)}"
            try:
                temporary_descriptor = os.open(
                    candidate,
                    create_flags,
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if temporary_descriptor is None or temporary_name is None:
            raise OSError("unable to allocate a private credential temporary file")
        os.fchmod(temporary_descriptor, 0o600)
        reason = _private_regular_metadata_error(
            os.fstat(temporary_descriptor), label="credential", path=destination
        )
        if reason:
            raise ValueError(reason)
        encoded = (
            json.dumps(
                credential, ensure_ascii=False, sort_keys=True, indent=2
            )
            + "\n"
        ).encode("utf-8")
        view = memoryview(encoded)
        while view:
            written = os.write(temporary_descriptor, view)
            if written <= 0:
                raise OSError("short write to validation credential")
            view = view[written:]
        os.fsync(temporary_descriptor)
        os.close(temporary_descriptor)
        temporary_descriptor = None
        os.replace(
            temporary_name,
            destination_name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_name = None
        os.fsync(parent_descriptor)
    finally:
        if existing_descriptor is not None:
            os.close(existing_descriptor)
        if temporary_descriptor is not None:
            os.close(temporary_descriptor)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)


def _read_stored(path: Path) -> CredentialVerdict:
    try:
        descriptor = _open_private_regular(path, label="credential")
    except FileNotFoundError:
        return CredentialVerdict(False, "credential missing")
    except (OSError, ValueError) as error:
        return CredentialVerdict(False, str(error))
    try:
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
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
        try:
            actual_hash = _sha256_private_regular(path, label="log")
        except FileNotFoundError:
            return f"log missing: {path}"
        except (OSError, ValueError) as error:
            return str(error)
        if actual_hash != expected_hash:
            return f"log hash mismatch: {name}"
    return None


def load_reusable_credential(
    path: Path | str,
    expected_fingerprint: Mapping[str, Any],
    now: int | float | None = None,
) -> dict[str, Any] | None:
    """Legacy compatibility API; local same-UID evidence is never reusable."""

    del path, expected_fingerprint, now
    return None


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
    dependency_state: Mapping[str, str] | None = None,
    validation_environment: Mapping[str, str] | None = None,
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
        "toolchain": dict(
            sorted((toolchain or collect_toolchain(repo_path, profile=profile_name)).items())
        ),
        "dependency_state": _normalize_dependency_state(
            repo_path, profile_name, dependency_state
        ),
        "validation_environment": _normalize_validation_environment(
            validation_environment
        ),
    }
    for field in (
        "tree",
        "profile",
        "profile_version",
        "commands",
        "lockfiles",
        "toolchain",
        "dependency_state",
        "validation_environment",
    ):
        if stored.get(field) != expected[field]:
            label = {
                "lockfiles": "lock",
                "dependency_state": "dependency",
                "validation_environment": "environment",
            }.get(field, field)
            return CredentialVerdict(False, f"{label} fingerprint mismatch")
    if _worktree_is_dirty(repo_path):
        return CredentialVerdict(False, "worktree is dirty")
    log_error = _verify_log_bindings(stored.get("logs"))
    if log_error:
        return CredentialVerdict(False, log_error)
    return CredentialVerdict(
        False,
        "credential reuse disabled: same-UID local evidence is not trusted",
        stored,
    )


def _load_json(path: str) -> Any:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--repo", default=".")
    verify.add_argument("--profile", required=True)
    verify.add_argument("--profile-version", default=PROFILE_VERSION)
    verify.add_argument("--commands-json", required=True)
    verify.add_argument("--toolchain-json")
    verify.add_argument("--dependency-state-json")
    verify.add_argument("--validation-environment-json")
    verify.add_argument("--lock", action="append", dest="lock_paths")
    verify.add_argument("--path")
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
    dependency_state = (
        _load_json(args.dependency_state_json)
        if args.dependency_state_json
        else None
    )
    validation_environment = (
        _load_json(args.validation_environment_json)
        if args.validation_environment_json
        else None
    )
    verdict = verify_credential(
        repo=repo,
        path=path,
        profile_name=args.profile,
        profile_version=args.profile_version,
        commands=commands,
        toolchain=toolchain,
        lock_paths=args.lock_paths,
        dependency_state=dependency_state,
        validation_environment=validation_environment,
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
