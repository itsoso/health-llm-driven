#!/usr/bin/env python3
"""Run the backend pytest shards declared by CI with bounded local concurrency."""

from __future__ import annotations

from collections.abc import Sequence
from collections import Counter
from dataclasses import dataclass
import glob
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import signal
import subprocess
import sys
import time

import yaml


DEFAULT_WORKERS = 4
MAX_WORKERS = 8
WORKERS_ENV = "REVA_BACKEND_SHARD_PARALLEL"
LOG_DIR_ENV = "REVA_BACKEND_SHARD_LOG_DIR"
_RUN_STEP_NAME = "Run tests (${{ matrix.label }})"
_MATRIX_PATHS_EXPRESSION = "${{ matrix.paths }}"
_MATRIX_EXTRA_ARGS_EXPRESSION = "${{ matrix.extra_args }}"
_PATHS_SENTINEL = "__REVA_MATRIX_PATHS__"
_EXTRA_ARGS_SENTINEL = "__REVA_MATRIX_EXTRA_ARGS__"
_CANONICAL_TEST_ENVIRONMENT = {
    "APP_ENV": "test",
    "DATABASE_URL": "sqlite:///:memory:",
    "SECRET_KEY": "test-secret-key-32-chars-minimum!!",
    "GARMIN_ENCRYPTION_KEY": (
        "mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU="
    ),
    "TZ": "Asia/Shanghai",
}
_LABEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


class MatrixConfigurationError(ValueError):
    """The CI matrix cannot be executed safely."""


class _MatrixSignal(BaseException):
    def __init__(self, signum: int) -> None:
        self.signum = signum


@dataclass(frozen=True)
class Shard:
    label: str
    paths: tuple[str, ...]
    extra_args: tuple[str, ...]
    matched_paths: tuple[Path, ...]
    executable_paths: tuple[str, ...] = ()
    pytest_args: tuple[str, ...] = ()


@dataclass
class _RunningShard:
    index: int
    shard: Shard
    process: subprocess.Popen[bytes]
    log_file: object
    log_path: Path


@dataclass(frozen=True)
class _ShardResult:
    index: int
    shard: Shard
    return_code: int
    log_path: Path
    log_file: object


def _mapping(
    value: object, location: str, *, allow_non_string_keys: bool = False
) -> dict:
    if not isinstance(value, dict):
        raise MatrixConfigurationError(f"{location} must be a mapping")
    if not allow_non_string_keys and not all(isinstance(key, str) for key in value):
        raise MatrixConfigurationError(f"{location} keys must be strings")
    return value


def _split(value: object, location: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value.strip():
        raise MatrixConfigurationError(f"{location} must be a non-empty string")
    try:
        tokens = tuple(shlex.split(value, posix=True))
    except ValueError as exc:
        raise MatrixConfigurationError(f"invalid shell quoting in {location}: {exc}") from exc
    if not tokens:
        raise MatrixConfigurationError(f"{location} must contain at least one token")
    return tokens


def _resolve_path_tokens(
    tokens: Sequence[str], backend_root: Path, label: str
) -> tuple[tuple[Path, ...], tuple[str, ...]]:
    tests_root = (backend_root / "tests").resolve(strict=True)
    matched_paths: list[Path] = []
    executable_paths: list[str] = []

    for token in tokens:
        file_pattern, separator, node_id = token.partition("::")
        relative = PurePosixPath(file_pattern)
        if (
            relative.is_absolute()
            or not relative.parts
            or relative.parts[0] != "tests"
            or ".." in relative.parts
        ):
            raise MatrixConfigurationError(
                f"shard {label!r} path must remain within backend/tests: {token!r}"
            )

        absolute_pattern = str(backend_root / Path(*relative.parts))
        matches = sorted(glob.glob(absolute_pattern))
        if not matches:
            raise MatrixConfigurationError(
                f"shard {label!r} path pattern matched nothing: {token!r}"
            )
        for match in matches:
            resolved = Path(match).resolve(strict=True)
            try:
                resolved.relative_to(tests_root)
            except ValueError as exc:
                raise MatrixConfigurationError(
                    f"shard {label!r} path escapes backend/tests: {token!r}"
                ) from exc
            matched_paths.append(resolved)
            relative_match = resolved.relative_to(backend_root.resolve()).as_posix()
            executable_paths.append(
                f"{relative_match}::{node_id}" if separator else relative_match
            )

    return (
        tuple(dict.fromkeys(matched_paths)),
        tuple(dict.fromkeys(executable_paths)),
    )


def _validate_extra_args(
    tokens: Sequence[str], backend_root: Path, label: str
) -> None:
    seen: set[str] = set()
    verbosity_seen = False
    for token in tokens:
        if token in seen:
            raise MatrixConfigurationError(
                f"shard {label!r} extra_args contains duplicate argument: {token!r}"
            )
        seen.add(token)
        if token in {"-v", "-vv"}:
            if verbosity_seen:
                raise MatrixConfigurationError(
                    f"shard {label!r} extra_args overrides verbosity more than once"
                )
            verbosity_seen = True
            continue
        prefix = next(
            (
                candidate
                for candidate in ("--ignore=", "--ignore-glob=", "--deselect=")
                if token.startswith(candidate)
            ),
            None,
        )
        if prefix is None or token == prefix:
            raise MatrixConfigurationError(
                f"shard {label!r} extra_args contains an unapproved argument: {token!r}"
            )
        path_value = token[len(prefix) :].split("::", 1)[0]
        relative = PurePosixPath(path_value)
        if (
            relative.is_absolute()
            or not relative.parts
            or relative.parts[0] != "tests"
            or ".." in relative.parts
        ):
            raise MatrixConfigurationError(
                f"shard {label!r} extra_args path must remain within backend/tests: {token!r}"
            )


def selected_test_files(shard: Shard, backend_root: Path) -> tuple[Path, ...]:
    """Return test files selected by one shard's paths and ignore arguments."""

    selected: set[Path] = set()
    for path in shard.matched_paths:
        if path.is_dir():
            selected.update(path.rglob("test_*.py"))
        elif path.name.startswith("test_") and path.suffix == ".py":
            selected.add(path)

    for argument in shard.extra_args:
        if argument.startswith("--ignore="):
            ignored = (backend_root / argument.removeprefix("--ignore=")).resolve()
            selected = {
                path for path in selected if path != ignored and ignored not in path.parents
            }
        elif argument.startswith("--ignore-glob="):
            pattern = argument.removeprefix("--ignore-glob=")
            selected = {
                path
                for path in selected
                if not path.relative_to(backend_root).match(pattern)
            }
    return tuple(sorted(selected))


def _validate_test_coverage(shards: Sequence[Shard], backend_root: Path) -> None:
    for shard in shards:
        has_node_path = any("::" in path for path in shard.paths)
        has_deselect = any(
            argument.startswith("--deselect=") for argument in shard.extra_args
        )
        if (
            shard.label not in {"t-w-z", "twin-api"}
            and (has_node_path or has_deselect)
        ) or (shard.label == "t-w-z" and has_node_path):
            raise MatrixConfigurationError(
                f"shard {shard.label!r} uses a partial test selector outside "
                "the exact complementary twin split"
            )

    coverage = Counter(
        test_file
        for shard in shards
        for test_file in selected_test_files(shard, backend_root)
    )
    expected = set((backend_root / "tests").rglob("test_*.py"))
    missing = sorted(expected - set(coverage))
    extra = sorted(set(coverage) - expected)
    duplicates = {
        path: count
        for path, count in coverage.items()
        if count != 1 and path.name != "test_twin_builder.py"
    }
    twin_path = backend_root / "tests" / "test_twin_builder.py"
    if twin_path in expected:
        by_label = {shard.label: shard for shard in shards}
        broad = by_label.get("t-w-z")
        isolated = by_label.get("twin-api")
        exact_deselect = "--deselect=tests/test_twin_builder.py::TestTwinAPI"
        exact_node = ("tests/test_twin_builder.py::TestTwinAPI",)
        broad_selectors = (
            tuple(
                argument
                for argument in broad.extra_args
                if argument not in {"-v", "-vv"}
            )
            if broad is not None
            else ()
        )
        isolated_selectors = (
            tuple(
                argument
                for argument in isolated.extra_args
                if argument not in {"-v", "-vv"}
            )
            if isolated is not None
            else ()
        )
        if (
            coverage[twin_path] != 2
            or broad is None
            or any("::" in path for path in broad.paths)
            or broad_selectors != (exact_deselect,)
            or isolated is None
            or isolated.paths != exact_node
            or isolated_selectors
        ):
            raise MatrixConfigurationError(
                "CI matrix coverage requires the exact complementary twin split"
            )
    if missing or extra or duplicates:
        raise MatrixConfigurationError(
            "CI matrix test file coverage is not exact: "
            f"missing={[str(path) for path in missing[:5]]}, "
            f"extra={[str(path) for path in extra[:5]]}, "
            f"duplicates={{{', '.join(f'{path}: {count}' for path, count in list(duplicates.items())[:5])}}}"
        )


def _parse_ci_pytest_args(job: dict) -> tuple[str, ...]:
    steps = job.get("steps")
    if not isinstance(steps, list) or not steps:
        raise MatrixConfigurationError("backend-test-shards steps must be non-empty")
    run_steps = [
        _mapping(step, f"backend-test-shards.steps[{index}]")
        for index, step in enumerate(steps)
        if isinstance(step, dict) and step.get("name") == _RUN_STEP_NAME
    ]
    if len(run_steps) != 1:
        raise MatrixConfigurationError(
            f"CI workflow must contain exactly one {_RUN_STEP_NAME!r} step"
        )
    run_step = run_steps[0]
    if run_step.get("working-directory") != "backend":
        raise MatrixConfigurationError(
            f"CI {_RUN_STEP_NAME!r} step must run in backend"
        )
    run_command = run_step.get("run")
    if not isinstance(run_command, str) or not run_command.strip():
        raise MatrixConfigurationError(
            f"CI {_RUN_STEP_NAME!r} step must have a non-empty run command"
        )
    if (
        run_command.count(_MATRIX_PATHS_EXPRESSION) != 1
        or run_command.count(_MATRIX_EXTRA_ARGS_EXPRESSION) != 1
    ):
        raise MatrixConfigurationError(
            f"CI {_RUN_STEP_NAME!r} step must contain each matrix expression once"
        )
    normalized = run_command.replace(
        _MATRIX_PATHS_EXPRESSION, _PATHS_SENTINEL
    ).replace(_MATRIX_EXTRA_ARGS_EXPRESSION, _EXTRA_ARGS_SENTINEL)
    if "${{" in normalized or "}}" in normalized:
        raise MatrixConfigurationError(
            f"CI {_RUN_STEP_NAME!r} step contains an unsupported expression"
        )
    if re.search(r"[;&|<>`$\\]", normalized):
        raise MatrixConfigurationError(
            f"CI {_RUN_STEP_NAME!r} step contains shell control syntax"
        )
    try:
        tokens = tuple(shlex.split(normalized, posix=True))
    except ValueError as exc:
        raise MatrixConfigurationError(
            f"invalid shell quoting in CI {_RUN_STEP_NAME!r} step: {exc}"
        ) from exc
    expected_prefix = (
        "python",
        "scripts/run_ci_pytest_shard.py",
        _PATHS_SENTINEL,
        "--",
    )
    if (
        tokens[: len(expected_prefix)] != expected_prefix
        or not tokens[len(expected_prefix) :]
        or tokens[-1] != _EXTRA_ARGS_SENTINEL
    ):
        raise MatrixConfigurationError(
            f"CI {_RUN_STEP_NAME!r} step has an unsupported command shape"
        )
    pytest_args = tokens[len(expected_prefix) : -1]
    return pytest_args


def load_ci_matrix(workflow_path: Path, backend_root: Path) -> list[Shard]:
    """Load and validate the backend shard declarations from the real CI shape."""

    try:
        document = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise MatrixConfigurationError(f"cannot read CI workflow: {exc}") from exc

    # PyYAML 1.1 treats the top-level Actions key `on` as a boolean. It is
    # outside this coordinator's schema; all traversed matrix mappings remain
    # string-key strict.
    workflow = _mapping(document, "workflow", allow_non_string_keys=True)
    if "jobs" not in workflow:
        raise MatrixConfigurationError("CI workflow is missing 'jobs'")
    jobs = _mapping(workflow["jobs"], "jobs")
    if "backend-test-shards" not in jobs:
        raise MatrixConfigurationError("CI workflow is missing 'backend-test-shards'")
    job = _mapping(jobs["backend-test-shards"], "backend-test-shards")
    pytest_args = _parse_ci_pytest_args(job)
    current = job
    for key in ("strategy", "matrix"):
        if key not in current:
            raise MatrixConfigurationError(f"CI workflow is missing {key!r}")
        current = _mapping(current[key], key)
    include = current.get("include")
    if not isinstance(include, list) or not include:
        raise MatrixConfigurationError("matrix.include must be a non-empty list")

    shards: list[Shard] = []
    labels: set[str] = set()
    allowed_fields = {"label", "paths", "extra_args"}
    for index, raw_entry in enumerate(include):
        entry = _mapping(raw_entry, f"matrix.include[{index}]")
        unknown_fields = set(entry) - allowed_fields
        if unknown_fields:
            raise MatrixConfigurationError(
                f"matrix.include[{index}] has unknown fields: {sorted(unknown_fields)}"
            )
        missing_fields = {"label", "paths"} - set(entry)
        if missing_fields:
            raise MatrixConfigurationError(
                f"matrix.include[{index}] is missing fields: {sorted(missing_fields)}"
            )

        label = entry["label"]
        if not isinstance(label, str) or not _LABEL_PATTERN.fullmatch(label):
            raise MatrixConfigurationError(
                f"matrix.include[{index}].label is not a safe non-empty label"
            )
        if label in labels:
            raise MatrixConfigurationError(f"duplicate label in CI matrix: {label!r}")
        labels.add(label)

        paths = _split(entry["paths"], f"shard {label!r} paths")
        extra_args = (
            _split(entry["extra_args"], f"shard {label!r} extra_args")
            if "extra_args" in entry
            else ()
        )
        _validate_extra_args(extra_args, backend_root, label)
        matched_paths, executable_paths = _resolve_path_tokens(
            paths, backend_root, label
        )
        shards.append(
            Shard(
                label=label,
                paths=paths,
                extra_args=extra_args,
                matched_paths=matched_paths,
                executable_paths=executable_paths,
                pytest_args=pytest_args,
            )
        )

    _validate_test_coverage(shards, backend_root)
    return shards


def parse_worker_count(value: str | None) -> int:
    if value is None:
        return DEFAULT_WORKERS
    try:
        worker_count = int(value)
    except (TypeError, ValueError) as exc:
        raise MatrixConfigurationError(
            f"{WORKERS_ENV} must be an integer in 1..8"
        ) from exc
    if not 1 <= worker_count <= MAX_WORKERS:
        raise MatrixConfigurationError(f"{WORKERS_ENV} must be an integer in 1..8")
    return worker_count


def build_shard_command(shard: Shard, runner_path: Path) -> list[str]:
    return [
        sys.executable,
        str(runner_path),
        *(shard.executable_paths or shard.paths),
        "--",
        *shard.pytest_args,
        *shard.extra_args,
    ]


def _open_private_log(log_path: Path):
    flags = os.O_RDWR | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(log_path, flags, 0o600)
    os.fchmod(descriptor, 0o600)
    return os.fdopen(descriptor, "w+b")


def resolve_log_dir(
    configured_path: str | None, *, common_dir: Path, run_id: str
) -> Path:
    if configured_path is not None:
        if not configured_path.strip():
            raise MatrixConfigurationError(f"{LOG_DIR_ENV} must not be empty")
        candidate = Path(configured_path)
        if not candidate.is_absolute():
            raise MatrixConfigurationError(f"{LOG_DIR_ENV} must be an absolute path")
        return candidate
    return common_dir / "reva-release-state" / "logs" / f"backend-matrix-{run_id}"


def _prepare_log_dir(log_dir: Path) -> None:
    candidate = log_dir
    while not candidate.exists() and not candidate.is_symlink():
        candidate = candidate.parent
    if candidate.is_symlink() or candidate.resolve(strict=True) != candidate.absolute():
        raise MatrixConfigurationError(
            f"log directory must not use symlinked paths: {candidate}"
        )
    log_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    if log_dir.is_symlink():
        raise MatrixConfigurationError(f"log directory must not be a symlink: {log_dir}")
    os.chmod(log_dir, 0o700)


def _clean_subprocess_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PYTHON")
        and not key.startswith("PYTEST")
        and key != "TEST_DATABASE_URL"
    }
    environment.update(_CANONICAL_TEST_ENVIRONMENT)
    return environment


def _log_tail(log_file: object, line_count: int = 20) -> list[str]:
    try:
        log_file.flush()
        log_file.seek(0)
        contents = log_file.read().decode("utf-8", errors="replace")
        return contents.splitlines(keepends=True)[-line_count:]
    except (AttributeError, OSError, ValueError) as exc:
        return [f"<unable to read private shard log: {exc}>\n"]


def _print_failure_summaries(results: Sequence[_ShardResult]) -> None:
    for result in results:
        if result.return_code == 0:
            continue
        print(
            f"[local-matrix] FAILED {result.shard.label}: "
            f"rc={result.return_code} log={result.log_path}",
            file=sys.stderr,
        )
        print("[local-matrix] --- last 20 log lines ---", file=sys.stderr)
        for line in _log_tail(result.log_file):
            print(line.rstrip("\n"), file=sys.stderr)
        print("[local-matrix] --- end log tail ---", file=sys.stderr, flush=True)


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait()


def run_matrix(
    shards: Sequence[Shard],
    runner_path: Path,
    log_dir: Path,
    *,
    worker_count: int,
) -> int:
    """Run every shard and return 1 if any shard fails, preserving shard results."""

    if not 1 <= worker_count <= MAX_WORKERS:
        raise MatrixConfigurationError("worker_count must be in 1..8")
    if not shards:
        raise MatrixConfigurationError("at least one shard is required")
    if not runner_path.is_file():
        raise MatrixConfigurationError(f"shard runner does not exist: {runner_path}")

    _prepare_log_dir(log_dir)
    running: dict[int, _RunningShard] = {}
    return_codes: list[int | None] = [None] * len(shards)
    results: list[_ShardResult] = []
    next_index = 0

    def handle_signal(signum: int, _frame: object) -> None:
        raise _MatrixSignal(signum)

    previous_handlers = {
        signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)
    }
    for signum in previous_handlers:
        signal.signal(signum, handle_signal)

    try:
        while next_index < len(shards) or running:
            while next_index < len(shards) and len(running) < worker_count:
                shard = shards[next_index]
                log_path = log_dir / f"{shard.label}.log"
                log_file = _open_private_log(log_path)
                try:
                    process = subprocess.Popen(
                        build_shard_command(shard, runner_path),
                        cwd=runner_path.parents[1],
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                        env=_clean_subprocess_environment(),
                    )
                except BaseException:
                    log_file.close()
                    raise
                running[process.pid] = _RunningShard(
                    next_index, shard, process, log_file, log_path
                )
                print(
                    f"[local-matrix] started {shard.label} (log: {log_path})",
                    flush=True,
                )
                next_index += 1

            completed = False
            for pid, item in tuple(running.items()):
                return_code = item.process.poll()
                if return_code is None:
                    continue
                return_codes[item.index] = (
                    128 + abs(return_code) if return_code < 0 else return_code
                )
                results.append(
                    _ShardResult(
                        item.index,
                        item.shard,
                        return_codes[item.index],
                        item.log_path,
                        item.log_file,
                    )
                )
                print(
                    f"[local-matrix] finished {item.shard.label}: "
                    f"rc={return_codes[item.index]} (log: {item.log_path})",
                    flush=True,
                )
                del running[pid]
                completed = True
            if running and not completed:
                time.sleep(0.05)
    except _MatrixSignal as exc:
        print(
            f"[local-matrix] received signal {exc.signum}; stopping active shards",
            file=sys.stderr,
            flush=True,
        )
        return 128 + exc.signum
    finally:
        for item in running.values():
            _terminate_process(item.process)
            item.log_file.close()
        for signum, previous_handler in previous_handlers.items():
            signal.signal(signum, previous_handler)

    results.sort(key=lambda result: result.index)
    try:
        _print_failure_summaries(results)
    finally:
        for result in results:
            result.log_file.close()
    failures = [code for code in return_codes if code]
    return 1 if failures else 0


def main() -> int:
    backend_root = Path(__file__).resolve().parents[1]
    repo_root = backend_root.parent
    workflow_path = repo_root / ".github" / "workflows" / "ci.yml"
    runner_path = backend_root / "scripts" / "run_ci_pytest_shard.py"
    try:
        shards = load_ci_matrix(workflow_path, backend_root)
        worker_count = parse_worker_count(os.environ.get(WORKERS_ENV))
        common_dir_text = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        common_dir = Path(common_dir_text)
        if not common_dir.is_absolute():
            common_dir = (repo_root / common_dir).resolve()
        log_dir = resolve_log_dir(
            os.environ.get(LOG_DIR_ENV),
            common_dir=common_dir,
            run_id=f"{int(time.time())}-{os.getpid()}",
        )
        print(
            f"[local-matrix] running {len(shards)} CI shards with "
            f"{worker_count} workers",
            flush=True,
        )
        return run_matrix(
            shards,
            runner_path,
            log_dir,
            worker_count=worker_count,
        )
    except MatrixConfigurationError as exc:
        print(f"[local-matrix] configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
