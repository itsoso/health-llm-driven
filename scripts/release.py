#!/usr/bin/env python3
"""Fail-closed source-aware release planning and orchestration."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence

try:
    import validation_credential
except ModuleNotFoundError:
    from scripts import validation_credential


ROOT = Path(__file__).resolve().parents[1]
STATE_SCHEMA_VERSION = 1
STATE_DIRECTORY_NAME = "reva-release-state"
STATE_FILE_NAME = "release-state.json"
VALIDATION_PROFILE = "all"


class ReleaseError(RuntimeError):
    """A release invariant could not be proven."""


@dataclass(frozen=True)
class Change:
    status: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class ReleasePlan:
    base_sha: str
    target_sha: str
    changes: tuple[Change, ...]
    surfaces: tuple[str, ...]
    actions: tuple[str, ...]
    completed_actions: tuple[str, ...]
    blocked_paths: tuple[str, ...]
    publishable: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


Runner = Callable[..., subprocess.CompletedProcess[Any]]


_STATUS_RE = re.compile(r"^[ACDMRTUXB][0-9]{0,3}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SURFACE_ORDER = (
    "backend",
    "frontend",
    "mobile_native",
    "mobile_ota",
    "mac",
    "validation_only",
)
_VALID_ACTIONS = {
    "validate",
    "deploy_backend",
    "deploy_all",
    "mobile_ota",
    "native_build",
    "mac_build",
}
_ROOT_BACKEND_INPUTS = {
    "Dockerfile.backend",
    "docker-compose.yml",
}
_ROOT_FRONTEND_INPUTS = {"Dockerfile.frontend"}
_ROOT_MOBILE_NATIVE_INPUTS = {
    ".easignore",
    "app.json",
}
_ROOT_VALIDATION_FILES = {
    ".dockerignore",
    ".env.example",
    ".gitattributes",
    ".gitignore",
    ".npmrc",
    ".pre-commit-config.yaml",
    "AGENTS.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    "README.md",
    "deploy.sh",
    "deploy-remote.sh",
    "deploy_production.sh",
    "deploy_to_server.sh",
}


def _git(
    repo: Path,
    *args: str,
    text: bool = True,
    check: bool = True,
) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=text,
    )
    return result.stdout.strip() if text else result.stdout


def _decode_path(value: bytes) -> str:
    path = value.decode("utf-8", errors="surrogateescape")
    if not path:
        raise ReleaseError("Git change contains an empty path")
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise ReleaseError(f"Git change contains an unsafe path: {path!r}")
    return path


def parse_name_status(raw: bytes) -> tuple[Change, ...]:
    """Parse ``git diff --name-status -z`` without losing rename endpoints."""

    if not raw:
        return ()
    fields = raw.split(b"\0")
    if fields[-1] == b"":
        fields.pop()
    changes: list[Change] = []
    index = 0
    while index < len(fields):
        status = fields[index].decode("ascii", errors="strict")
        index += 1
        if not _STATUS_RE.fullmatch(status):
            raise ReleaseError(f"Unsupported Git change status: {status!r}")
        path_count = 2 if status[0] in {"R", "C"} else 1
        if index + path_count > len(fields):
            raise ReleaseError(f"Incomplete Git change record for status {status}")
        paths = tuple(_decode_path(value) for value in fields[index : index + path_count])
        index += path_count
        changes.append(Change(status=status, paths=paths))
    return tuple(changes)


def git_changes(repo: Path, base: str, target: str) -> tuple[str, str, tuple[Change, ...]]:
    repo = _repository_root(repo)
    base_sha = str(_git(repo, "rev-parse", "--verify", f"{base}^{{commit}}"))
    target_sha = str(_git(repo, "rev-parse", "--verify", f"{target}^{{commit}}"))
    if not _SHA_RE.fullmatch(base_sha) or not _SHA_RE.fullmatch(target_sha):
        raise ReleaseError("Unable to resolve an exact base and target commit")
    raw = _git(
        repo,
        "diff",
        "--name-status",
        "-z",
        "--find-renames",
        base_sha,
        target_sha,
        text=False,
    )
    assert isinstance(raw, bytes)
    return base_sha, target_sha, parse_name_status(raw)


def _is_test_or_fixture(path: str) -> bool:
    parts = PurePosixPath(path).parts
    name = parts[-1]
    return (
        "tests" in parts
        or "__tests__" in parts
        or name.startswith("test_")
        or name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
        or name in {"pytest.ini", "jest.config.js", "jest.config.ts"}
    )


def classify_path(path: str) -> str | None:
    """Classify a repository path; ``None`` means fail-closed/unknown."""

    if _is_test_or_fixture(path):
        return "validation_only"

    validation_prefixes = (
        ".agents/",
        ".claude/",
        ".cursor/",
        ".github/",
        "artifacts/",
        "design/",
        "designs/",
        "docs/",
        "harness/",
        "scripts/",
    )
    if path in _ROOT_VALIDATION_FILES or path.startswith(validation_prefixes):
        return "validation_only"

    if path.startswith("apps/mac/"):
        return "mac"

    native_mobile_files = {
        "mobile/app.json",
        "mobile/app.config.js",
        "mobile/app.config.ts",
        "mobile/eas.json",
        "mobile/package.json",
        "mobile/package-lock.json",
        "mobile/yarn.lock",
        "mobile/pnpm-lock.yaml",
    }
    native_mobile_prefixes = (
        "apps/watch/",
        "apps/rokid-pushup-glasses/",
        "mobile/android/",
        "mobile/ios/",
        "mobile/modules/",
        "mobile/native/",
        "mobile/patches/",
        "mobile/plugins/",
    )
    if path in native_mobile_files or path.startswith(native_mobile_prefixes):
        return "mobile_native"

    if path in _ROOT_MOBILE_NATIVE_INPUTS:
        return "mobile_native"

    if path.startswith("mobile/") or path.startswith("packages/shared/"):
        return "mobile_ota"

    if path.startswith("frontend/") or path in _ROOT_FRONTEND_INPUTS:
        return "frontend"

    if path.startswith("backend/") or path in _ROOT_BACKEND_INPUTS:
        return "backend"

    return None


def build_plan(
    changes: Iterable[Change],
    *,
    base_sha: str,
    target_sha: str,
    completed_actions: Iterable[str] = (),
) -> ReleasePlan:
    changes_tuple = tuple(changes)
    surfaces_seen: set[str] = set()
    blocked_paths: set[str] = set()
    for change in changes_tuple:
        for path in change.paths:
            surface = classify_path(path)
            if surface is None:
                blocked_paths.add(path)
            else:
                surfaces_seen.add(surface)

    if not surfaces_seen and not blocked_paths:
        surfaces_seen.add("validation_only")
    if surfaces_seen - {"validation_only"}:
        surfaces_seen.discard("validation_only")
    surfaces = tuple(surface for surface in _SURFACE_ORDER if surface in surfaces_seen)

    actions: list[str] = ["validate"]
    if "frontend" in surfaces_seen:
        actions.append("deploy_all")
    elif "backend" in surfaces_seen:
        actions.append("deploy_backend")
    if "mobile_native" in surfaces_seen:
        actions.append("native_build")
    elif "mobile_ota" in surfaces_seen:
        actions.append("mobile_ota")
    if "mac" in surfaces_seen:
        actions.append("mac_build")

    normalized_completed = tuple(
        action
        for action in dict.fromkeys(completed_actions)
        if action in _VALID_ACTIONS and action != "validate"
    )
    actions = [
        action
        for action in actions
        if action == "validate" or action not in normalized_completed
    ]
    publishable = not blocked_paths and not (
        {"mobile_native", "mac"} & surfaces_seen
    )
    return ReleasePlan(
        base_sha=base_sha,
        target_sha=target_sha,
        changes=changes_tuple,
        surfaces=surfaces,
        actions=tuple(actions),
        completed_actions=normalized_completed,
        blocked_paths=tuple(sorted(blocked_paths)),
        publishable=publishable,
    )


def _repository_root(repo: Path) -> Path:
    try:
        return Path(str(_git(repo.resolve(), "rev-parse", "--show-toplevel"))).resolve()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ReleaseError(f"Not a Git worktree: {repo}") from error


def _git_common_dir(repo: Path) -> Path:
    root = _repository_root(repo)
    try:
        common = str(
            _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
        )
        path = Path(common)
    except subprocess.CalledProcessError:
        common = str(_git(root, "rev-parse", "--git-common-dir"))
        path = Path(common)
        if not path.is_absolute():
            path = root / path
    return path.resolve()


def _owner_repository(repo: Path) -> Path:
    common = _git_common_dir(repo)
    if common.name == ".git" and (common.parent / ".git").exists():
        return common.parent.resolve()
    return _repository_root(repo)


def release_state_dir(repo: Path) -> Path:
    common = _git_common_dir(repo)
    state_dir = common / STATE_DIRECTORY_NAME
    try:
        state_dir.mkdir(mode=0o700, exist_ok=True)
    except OSError as error:
        raise ReleaseError(f"Cannot create shared release state: {state_dir}") from error
    mode = state_dir.lstat().st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise ReleaseError(f"Unsafe shared release state path: {state_dir}")
    os.chmod(state_dir, 0o700)
    return state_dir


def _state_path(repo: Path) -> Path:
    return _git_common_dir(repo) / STATE_DIRECTORY_NAME / STATE_FILE_NAME


def write_release_state(repo: Path, state: Mapping[str, Any]) -> Path:
    directory = release_state_dir(repo)
    destination = directory / STATE_FILE_NAME
    if destination.exists() and destination.is_symlink():
        raise ReleaseError(f"Refusing to replace symlinked release state: {destination}")
    payload = dict(state)
    payload.setdefault("schema_version", STATE_SCHEMA_VERSION)
    payload.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
    descriptor, temporary_name = tempfile.mkstemp(prefix=".release-state.", dir=directory)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def read_release_state(repo: Path) -> dict[str, Any]:
    path = _state_path(repo)
    if not path.exists():
        return {}
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise ReleaseError(f"Unsafe shared release state file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ReleaseError(f"Corrupt shared release state file: {path}") from error
    if not isinstance(value, dict):
        raise ReleaseError(f"Invalid shared release state payload: {path}")
    return value


def _worktree_status(repo: Path) -> str:
    return str(_git(repo, "status", "--porcelain", "--untracked-files=all"))


def _branch_name(repo: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "symbolic-ref", "--quiet", "--short", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _remote_main_sha(repo: Path) -> str:
    output = str(_git(repo, "ls-remote", "origin", "refs/heads/main"))
    rows = [line.split() for line in output.splitlines() if line.strip()]
    if len(rows) != 1 or len(rows[0]) != 2 or not _SHA_RE.fullmatch(rows[0][0]):
        raise ReleaseError("Unable to verify the unique origin/main commit")
    return rows[0][0]


def assert_release_source(release_path: Path) -> str:
    release_path = _repository_root(release_path)
    dirty = _worktree_status(release_path)
    if dirty:
        raise ReleaseError(f"Release worktree is dirty; refusing cleanup:\n{dirty}")
    branch = _branch_name(release_path)
    if branch not in {"", "main"}:
        raise ReleaseError(f"Release worktree is on forbidden branch {branch}")
    head = str(_git(release_path, "rev-parse", "HEAD"))
    local_main = str(_git(release_path, "rev-parse", "refs/remotes/origin/main"))
    remote_main = _remote_main_sha(release_path)
    if not _SHA_RE.fullmatch(head) or head != local_main or head != remote_main:
        raise ReleaseError(
            "Release source must equal both local and remote origin/main: "
            f"head={head[:12]} local={local_main[:12]} remote={remote_main[:12]}"
        )
    return head


def ensure_release_worktree(
    repo: Path,
    *,
    release_path: Path | None = None,
) -> Path:
    source = _repository_root(repo)
    owner = _owner_repository(source)
    destination = (
        release_path.resolve()
        if release_path is not None
        else Path(f"{owner}.release").resolve()
    )

    if destination.exists():
        try:
            destination_root = _repository_root(destination)
        except ReleaseError as error:
            raise ReleaseError(
                f"Release path exists but is not a registered worktree: {destination}"
            ) from error
        if destination_root != destination:
            raise ReleaseError(f"Release path is not a worktree root: {destination}")
        if _git_common_dir(destination) != _git_common_dir(source):
            raise ReleaseError(f"Release path belongs to a different repository: {destination}")
        dirty = _worktree_status(destination)
        if dirty:
            raise ReleaseError(
                f"Release worktree is dirty; refusing cleanup or reset:\n{dirty}"
            )
        branch = _branch_name(destination)
        if branch not in {"", "main"}:
            raise ReleaseError(
                f"Release worktree is on forbidden branch {branch}; refusing checkout"
            )

    subprocess.run(
        ["git", "-C", str(source), "fetch", "--quiet", "origin", "main"],
        check=True,
    )
    local_main = str(_git(source, "rev-parse", "refs/remotes/origin/main"))
    remote_main = _remote_main_sha(source)
    if local_main != remote_main:
        raise ReleaseError("Fetched origin/main does not match the remote main SHA")

    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(source),
                "worktree",
                "add",
                "--detach",
                str(destination),
                local_main,
            ],
            check=True,
        )
    else:
        subprocess.run(
            ["git", "-C", str(destination), "checkout", "--detach", local_main],
            check=True,
        )

    assert_release_source(destination)
    return destination


def _validation_commands() -> list[dict[str, Any]]:
    return [
        {
            "name": "validation:all",
            "argv": ["bash", "scripts/run-all-tests.sh"],
            "cwd": ".",
            "blocking": True,
        }
    ]


def _running_in_ci() -> bool:
    return os.environ.get("CI", "").strip().lower() not in {"", "0", "false", "no"}


def _new_validation_log(repo: Path, profile: str) -> Path:
    try:
        state_dir = validation_credential.validation_state_dir(repo)
        logs_dir = state_dir / "logs"
        if logs_dir.is_symlink():
            raise ValueError(f"refusing symlinked validation log directory: {logs_dir}")
        logs_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if logs_dir.is_symlink() or not logs_dir.is_dir():
            raise ValueError(f"validation log path is not a directory: {logs_dir}")
        logs_dir.chmod(0o700)
        run_dir = Path(tempfile.mkdtemp(prefix="release-validation-", dir=logs_dir))
        run_dir.chmod(0o700)
        return run_dir / f"{profile}.log"
    except (OSError, RuntimeError, ValueError) as error:
        raise ReleaseError(f"Cannot create private validation log: {error}") from error


def _print_validation_log(log_path: Path) -> None:
    try:
        output = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise ReleaseError(f"Cannot read validation log {log_path}: {error}") from error
    if output:
        print(output, end="" if output.endswith("\n") else "\n")


def run_validation(
    plan: ReleasePlan,
    repo: Path,
    *,
    runner: Runner = subprocess.run,
) -> None:
    del plan
    repo = _repository_root(repo)
    profile = VALIDATION_PROFILE
    commands = _validation_commands()
    command = commands[0]["argv"]
    in_ci = _running_in_ci()
    credential_file: Path | None = None
    toolchain: Mapping[str, str] | None = None

    if in_ci:
        print(
            "[release] validation credential bypass: "
            "CI requires commit-specific validation"
        )
    else:
        try:
            credential_file = validation_credential.credential_path(repo, profile)
            toolchain = validation_credential.collect_toolchain(repo)
            verdict = validation_credential.verify_credential(
                repo=repo,
                path=credential_file,
                profile_name=profile,
                profile_version=validation_credential.PROFILE_VERSION,
                commands=commands,
                toolchain=toolchain,
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise ReleaseError(
                f"Validation credential check failed closed: {error}"
            ) from error
        if verdict.reusable:
            print(
                f"[release] validation credential hit: profile={profile} "
                f"reason={verdict.reason}"
            )
            return
        print(
            f"[release] validation credential miss: profile={profile} "
            f"reason={verdict.reason}"
        )

    log_path = _new_validation_log(repo, profile)
    print(f"[release] validation running: profile={profile} log={log_path}")
    try:
        with log_path.open("x", encoding="utf-8") as log_handle:
            log_path.chmod(0o600)
            completed = runner(
                command,
                cwd=repo,
                check=True,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
        if completed.returncode != 0:
            raise subprocess.CalledProcessError(completed.returncode, command)
    except subprocess.CalledProcessError:
        print(f"[release] validation failed: profile={profile} log={log_path}")
        _print_validation_log(log_path)
        raise

    _print_validation_log(log_path)
    if in_ci:
        print(
            f"[release] validation passed: profile={profile}; "
            "tree credential not issued in CI"
        )
        return

    assert credential_file is not None
    assert toolchain is not None
    try:
        credential = validation_credential.build_credential(
            repo=repo,
            profile_name=profile,
            profile_version=validation_credential.PROFILE_VERSION,
            commands=commands,
            logs={commands[0]["name"]: log_path},
            toolchain=toolchain,
        )
        validation_credential.write_credential_atomic(credential_file, credential)
    except (OSError, RuntimeError, ValueError) as error:
        raise ReleaseError(
            f"Validation passed but credential issue failed closed: {error}"
        ) from error
    print(
        f"[release] validation credential issued: profile={profile} "
        f"path={credential_file}"
    )


def _state_completed_actions(
    repo: Path, base_sha: str, target_sha: str
) -> tuple[str, ...]:
    state = read_release_state(repo)
    if state.get("base_sha") != base_sha or state.get("target_sha") != target_sha:
        return ()
    value = state.get("completed_actions", [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ReleaseError("Invalid completed_actions in shared release state")
    return tuple(value)


def publish_plan(
    plan: ReleasePlan,
    repo: Path,
    *,
    owner_repo: Path,
    message: str,
    env_file: Path | None = None,
    runner: Runner = subprocess.run,
) -> None:
    if not plan.publishable:
        details = ", ".join(plan.blocked_paths) or ", ".join(plan.surfaces)
        raise ReleaseError(f"Release requires manual routing before publish: {details}")
    run_validation(plan, repo, runner=runner)
    assert_release_source(repo)
    completed = list(plan.completed_actions)
    environment = os.environ.copy()
    deploy_env = env_file or Path(
        environment.get("DEPLOY_ENV_FILE", str(owner_repo / ".env"))
    )
    environment["DEPLOY_ENV_FILE"] = str(deploy_env.resolve())

    for action in plan.actions:
        if action == "validate":
            continue
        assert_release_source(repo)
        if action == "deploy_backend":
            command = [str(repo / "deploy.sh"), "--backend", "--yes"]
        elif action == "deploy_all":
            command = [str(repo / "deploy.sh"), "--all", "--yes"]
        elif action == "mobile_ota":
            command = [
                str(repo / "scripts/mobile-ota.sh"),
                "production",
                message,
            ]
        else:
            raise ReleaseError(f"Action is not safely publishable: {action}")
        runner(command, cwd=repo, check=True, env=environment)
        completed.append(action)
        write_release_state(
            repo,
            {
                "schema_version": STATE_SCHEMA_VERSION,
                "base_sha": plan.base_sha,
                "target_sha": plan.target_sha,
                "completed_actions": list(dict.fromkeys(completed)),
            },
        )


def _plan_for_refs(
    repo: Path,
    base: str,
    target: str,
    *,
    include_partial_state: bool,
) -> ReleasePlan:
    base_sha, target_sha, changes = git_changes(repo, base, target)
    completed = (
        _state_completed_actions(repo, base_sha, target_sha)
        if include_partial_state
        else ()
    )
    return build_plan(
        changes,
        base_sha=base_sha,
        target_sha=target_sha,
        completed_actions=completed,
    )


def _print_plan(plan: ReleasePlan) -> None:
    print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "validate", "publish"):
        command = subparsers.add_parser(name)
        command.add_argument("--repo", type=Path, default=ROOT)
        command.add_argument("--base", required=True, help="trusted baseline ref")
        command.add_argument("--target", default="origin/main")
        command.add_argument("--release-worktree", type=Path)
        if name == "publish":
            command.add_argument("--message", default="source-aware production release")
            command.add_argument("--env-file", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        repo = _repository_root(args.repo)
        if args.command == "plan":
            plan = _plan_for_refs(
                repo, args.base, args.target, include_partial_state=True
            )
            _print_plan(plan)
            return 0 if plan.publishable else 2

        release_repo = ensure_release_worktree(
            repo, release_path=args.release_worktree
        )
        target_sha = str(_git(release_repo, "rev-parse", args.target))
        exact_main = assert_release_source(release_repo)
        if target_sha != exact_main:
            raise ReleaseError("Validation/publish target must be exact origin/main")
        plan = _plan_for_refs(
            release_repo,
            args.base,
            exact_main,
            include_partial_state=True,
        )
        _print_plan(plan)
        if args.command == "validate":
            run_validation(plan, release_repo)
        else:
            if not plan.publishable:
                return 2
            publish_plan(
                plan,
                release_repo,
                owner_repo=_owner_repository(repo),
                message=args.message,
                env_file=args.env_file,
            )
        return 0
    except (ReleaseError, subprocess.CalledProcessError, OSError) as error:
        print(f"release error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
