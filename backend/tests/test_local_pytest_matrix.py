"""Local coordinator contract for the CI backend pytest matrix."""

from __future__ import annotations

import errno
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import threading
import textwrap
import time
from collections import Counter

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"


def _write_workflow(
    path: Path,
    include_yaml: str,
    *,
    run_command: str = (
        "python scripts/run_ci_pytest_shard.py ${{ matrix.paths }} -- "
        "-q --no-cov --tb=short --maxfail=5 "
        "--timeout=120 --timeout-method=signal ${{ matrix.extra_args }}"
    ),
) -> None:
    path.write_text(
        "jobs:\n"
        "  backend-test-shards:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        include:\n"
        + textwrap.indent(textwrap.dedent(include_yaml).strip(), "          ")
        + "\n"
        "    steps:\n"
        "      - name: Run tests (${{ matrix.label }})\n"
        "        working-directory: backend\n"
        "        run: >-\n"
        + textwrap.indent(run_command, "          ")
        + "\n",
        encoding="utf-8",
    )


def test_load_ci_matrix_parses_the_real_workflow_and_resolves_every_path():
    from scripts.run_local_pytest_matrix import load_ci_matrix, selected_test_files

    shards = load_ci_matrix(ROOT / ".github/workflows/ci.yml", BACKEND_ROOT)

    assert shards
    assert len({shard.label for shard in shards}) == len(shards)
    assert {"a-early", "twin-api", "services"} <= {
        shard.label for shard in shards
    }
    assert all(shard.matched_paths for shard in shards)
    coverage = Counter(
        test_file
        for shard in shards
        for test_file in selected_test_files(shard, BACKEND_ROOT)
    )
    expected = set((BACKEND_ROOT / "tests").rglob("test_*.py"))
    assert set(coverage) == expected
    twin_path = BACKEND_ROOT / "tests" / "test_twin_builder.py"
    assert coverage[twin_path] == 2
    assert all(
        count == 1 for path, count in coverage.items() if path != twin_path
    )
    by_label = {shard.label: shard for shard in shards}
    assert (
        "--deselect=tests/test_twin_builder.py::TestTwinAPI"
        in by_label["t-w-z"].extra_args
    )
    assert by_label["twin-api"].paths == (
        "tests/test_twin_builder.py::TestTwinAPI",
    )


def test_load_ci_matrix_reads_common_pytest_args_from_the_ci_run_step(
    tmp_path: Path,
):
    from scripts.run_local_pytest_matrix import load_ci_matrix

    backend_root = tmp_path / "backend"
    tests_root = backend_root / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_alpha.py").touch()
    workflow = tmp_path / "ci.yml"
    _write_workflow(
        workflow,
        """
        - label: alpha
          paths: tests/test_alpha.py
        """,
        run_command=(
            "python scripts/run_ci_pytest_shard.py ${{ matrix.paths }} -- "
            "-q --maxfail=17 --timeout=45 ${{ matrix.extra_args }}"
        ),
    )

    [shard] = load_ci_matrix(workflow, backend_root)

    assert shard.pytest_args == ("-q", "--maxfail=17", "--timeout=45")


@pytest.mark.parametrize(
    "run_command",
    [
        (
            "python scripts/run_ci_pytest_shard.py ${{ matrix.paths }} -- "
            "-q --timeout=120"
        ),
        (
            "python scripts/run_ci_pytest_shard.py ${{ matrix.paths }} -- "
            "-q ${{ matrix.extra_args }} && echo unsafe"
        ),
        (
            "python scripts/run_ci_pytest_shard.py ${{ matrix.paths }} -- "
            "-q;echo ${{ matrix.extra_args }}"
        ),
    ],
)
def test_load_ci_matrix_rejects_an_unparseable_ci_run_step(
    tmp_path: Path, run_command: str
):
    from scripts.run_local_pytest_matrix import MatrixConfigurationError, load_ci_matrix

    backend_root = tmp_path / "backend"
    tests_root = backend_root / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_alpha.py").touch()
    workflow = tmp_path / "ci.yml"
    _write_workflow(
        workflow,
        """
        - label: alpha
          paths: tests/test_alpha.py
        """,
        run_command=run_command,
    )

    with pytest.raises(MatrixConfigurationError, match="Run tests"):
        load_ci_matrix(workflow, backend_root)


def test_load_ci_matrix_uses_shlex_and_rejects_unknown_or_duplicate_fields(
    tmp_path: Path,
):
    from scripts.run_local_pytest_matrix import MatrixConfigurationError, load_ci_matrix

    backend_root = tmp_path / "backend"
    tests_root = backend_root / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_alpha.py").touch()
    workflow = tmp_path / "ci.yml"
    _write_workflow(
        workflow,
        """
        - label: alpha
          paths: "tests/test_alpha.py"
          extra_args: "--ignore-glob='tests/test_[b-z]*.py' -vv"
        """,
    )

    [shard] = load_ci_matrix(workflow, backend_root)

    assert shard.paths == ("tests/test_alpha.py",)
    assert shard.extra_args == ("--ignore-glob=tests/test_[b-z]*.py", "-vv")

    _write_workflow(
        workflow,
        """
        - label: same
          paths: tests/test_alpha.py
        - label: same
          paths: tests/test_alpha.py
          surprise: true
        """,
    )
    with pytest.raises(MatrixConfigurationError, match="unknown fields|duplicate label"):
        load_ci_matrix(workflow, backend_root)


@pytest.mark.parametrize(
    "extra_args",
    ["-q", "--tb=long", "--timeout=1", "-v -vv", "--ignore=/tmp/outside"],
)
def test_load_ci_matrix_rejects_unapproved_or_overriding_extra_args(
    tmp_path: Path, extra_args: str
):
    from scripts.run_local_pytest_matrix import MatrixConfigurationError, load_ci_matrix

    backend_root = tmp_path / "backend"
    tests_root = backend_root / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_alpha.py").touch()
    workflow = tmp_path / "ci.yml"
    _write_workflow(
        workflow,
        f"""
        - label: alpha
          paths: tests/test_alpha.py
          extra_args: "{extra_args}"
        """,
    )

    with pytest.raises(MatrixConfigurationError, match="extra_args"):
        load_ci_matrix(workflow, backend_root)


def test_glob_matches_are_stably_sorted(tmp_path: Path):
    from scripts.run_local_pytest_matrix import load_ci_matrix

    backend_root = tmp_path / "backend"
    tests_root = backend_root / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_z.py").touch()
    (tests_root / "test_a.py").touch()
    workflow = tmp_path / "ci.yml"
    _write_workflow(
        workflow,
        """
        - label: all
          paths: tests/test_*.py
        """,
    )

    [shard] = load_ci_matrix(workflow, backend_root)

    assert [path.name for path in shard.matched_paths] == ["test_a.py", "test_z.py"]


def test_matrix_rejects_missing_or_duplicate_test_file_coverage(tmp_path: Path):
    from scripts.run_local_pytest_matrix import MatrixConfigurationError, load_ci_matrix

    backend_root = tmp_path / "backend"
    tests_root = backend_root / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_alpha.py").touch()
    (tests_root / "test_beta.py").touch()
    workflow = tmp_path / "ci.yml"
    _write_workflow(
        workflow,
        """
        - label: alpha-one
          paths: tests/test_alpha.py
        - label: alpha-two
          paths: tests/test_alpha.py
        """,
    )

    with pytest.raises(MatrixConfigurationError, match="coverage"):
        load_ci_matrix(workflow, backend_root)


@pytest.mark.parametrize(
    ("paths", "extra_args"),
    [
        ("tests/test_alpha.py::test_only_one", ""),
        (
            "tests/test_alpha.py",
            "--deselect=tests/test_alpha.py::test_silently_skipped",
        ),
    ],
)
def test_matrix_rejects_partial_test_selectors_outside_the_exact_twin_split(
    tmp_path: Path, paths: str, extra_args: str
):
    from scripts.run_local_pytest_matrix import MatrixConfigurationError, load_ci_matrix

    backend_root = tmp_path / "backend"
    tests_root = backend_root / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_alpha.py").touch()
    extra_yaml = f"\n          extra_args: {extra_args}" if extra_args else ""
    workflow = tmp_path / "ci.yml"
    _write_workflow(
        workflow,
        f"""
        - label: alpha
          paths: {paths}{extra_yaml}
        """,
    )

    with pytest.raises(MatrixConfigurationError, match="partial test selector"):
        load_ci_matrix(workflow, backend_root)


def test_matrix_accepts_twin_file_twice_only_for_the_exact_complementary_split(
    tmp_path: Path,
):
    from scripts.run_local_pytest_matrix import MatrixConfigurationError, load_ci_matrix

    backend_root = tmp_path / "backend"
    tests_root = backend_root / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_twin_builder.py").touch()
    workflow = tmp_path / "ci.yml"
    _write_workflow(
        workflow,
        """
        - label: t-w-z
          paths: tests/test_twin_builder.py
        - label: twin-api
          paths: tests/test_twin_builder.py::TestTwinAPI
        """,
    )

    with pytest.raises(MatrixConfigurationError, match="complementary twin split"):
        load_ci_matrix(workflow, backend_root)


@pytest.mark.parametrize(
    ("broad_extra_args", "isolated_extra_args"),
    [
        (
            "--deselect=tests/test_twin_builder.py::TestTwinAPI "
            "--deselect=tests/test_twin_builder.py::TestOther",
            "",
        ),
        (
            "--deselect=tests/test_twin_builder.py::TestTwinAPI "
            "--ignore=tests/test_twin_builder.py",
            "",
        ),
        (
            "--deselect=tests/test_twin_builder.py::TestTwinAPI",
            "--deselect=tests/test_twin_builder.py::TestOther",
        ),
    ],
)
def test_matrix_rejects_extra_twin_split_selectors(
    tmp_path: Path,
    broad_extra_args: str,
    isolated_extra_args: str,
):
    from scripts.run_local_pytest_matrix import MatrixConfigurationError, load_ci_matrix

    backend_root = tmp_path / "backend"
    tests_root = backend_root / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_twin_builder.py").touch()
    isolated_extra_yaml = (
        f"\n          extra_args: {isolated_extra_args}"
        if isolated_extra_args
        else ""
    )
    workflow = tmp_path / "ci.yml"
    _write_workflow(
        workflow,
        f"""
        - label: t-w-z
          paths: tests/test_twin_builder.py
          extra_args: {broad_extra_args}
        - label: twin-api
          paths: tests/test_twin_builder.py::TestTwinAPI{isolated_extra_yaml}
        """,
    )

    with pytest.raises(MatrixConfigurationError, match="complementary twin split"):
        load_ci_matrix(workflow, backend_root)


def test_matrix_rejects_a_node_selector_smuggled_into_the_broad_twin_shard(
    tmp_path: Path,
):
    from scripts.run_local_pytest_matrix import MatrixConfigurationError, load_ci_matrix

    backend_root = tmp_path / "backend"
    tests_root = backend_root / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_twin_builder.py").touch()
    workflow = tmp_path / "ci.yml"
    _write_workflow(
        workflow,
        """
        - label: t-w-z
          paths: tests/test_twin_builder.py::TestNotTwinAPI
          extra_args: --deselect=tests/test_twin_builder.py::TestTwinAPI
        - label: twin-api
          paths: tests/test_twin_builder.py::TestTwinAPI
        """,
    )

    with pytest.raises(MatrixConfigurationError, match="partial test selector"):
        load_ci_matrix(workflow, backend_root)


def test_matrix_accepts_only_verbosity_beside_the_exact_twin_split(
    tmp_path: Path,
):
    from scripts.run_local_pytest_matrix import load_ci_matrix

    backend_root = tmp_path / "backend"
    tests_root = backend_root / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "test_twin_builder.py").touch()
    workflow = tmp_path / "ci.yml"
    _write_workflow(
        workflow,
        """
        - label: t-w-z
          paths: tests/test_twin_builder.py
          extra_args: >-
            --deselect=tests/test_twin_builder.py::TestTwinAPI -vv
        - label: twin-api
          paths: tests/test_twin_builder.py::TestTwinAPI
          extra_args: -v
        """,
    )

    shards = load_ci_matrix(workflow, backend_root)

    assert [shard.label for shard in shards] == ["t-w-z", "twin-api"]


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside.py",
        "tests/../outside.py",
        "/tmp/outside.py",
        "tests/test_missing_*.py",
    ],
)
def test_load_ci_matrix_rejects_unsafe_or_empty_path_patterns(
    tmp_path: Path, unsafe_path: str
):
    from scripts.run_local_pytest_matrix import MatrixConfigurationError, load_ci_matrix

    backend_root = tmp_path / "backend"
    (backend_root / "tests").mkdir(parents=True)
    workflow = tmp_path / "ci.yml"
    _write_workflow(
        workflow,
        f"""
        - label: unsafe
          paths: {unsafe_path}
        """,
    )

    with pytest.raises(MatrixConfigurationError, match="path"):
        load_ci_matrix(workflow, backend_root)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 4), ("1", 1), ("4", 4), ("8", 8)],
)
def test_worker_count_defaults_to_four_and_accepts_one_through_eight(
    value: str | None, expected: int
):
    from scripts.run_local_pytest_matrix import parse_worker_count

    assert parse_worker_count(value) == expected


@pytest.mark.parametrize("value", ["0", "9", "abc", "1.5", ""])
def test_worker_count_rejects_values_outside_one_through_eight(value: str):
    from scripts.run_local_pytest_matrix import MatrixConfigurationError, parse_worker_count

    with pytest.raises(MatrixConfigurationError, match="1..8"):
        parse_worker_count(value)


def test_build_command_delegates_to_the_existing_ci_shard_runner():
    from scripts.run_local_pytest_matrix import Shard, build_shard_command

    runner = BACKEND_ROOT / "scripts" / "run_ci_pytest_shard.py"
    command = build_shard_command(
        Shard(
            label="alpha",
            paths=("tests/test_alpha.py",),
            extra_args=("-vv",),
            matched_paths=(BACKEND_ROOT / "tests" / "test_alpha.py",),
            pytest_args=("-q", "--timeout=37"),
        ),
        runner,
    )

    assert command[:2] == [sys.executable, str(runner)]
    assert command[2:4] == ["tests/test_alpha.py", "--"]
    assert command[-1] == "-vv"
    assert "-q" in command
    assert "--timeout=37" in command


def test_build_command_expands_ci_globs_but_preserves_pytest_node_ids():
    from scripts.run_local_pytest_matrix import build_shard_command, load_ci_matrix

    shards = {
        shard.label: shard
        for shard in load_ci_matrix(ROOT / ".github/workflows/ci.yml", BACKEND_ROOT)
    }
    runner = BACKEND_ROOT / "scripts" / "run_ci_pytest_shard.py"

    b_command = build_shard_command(shards["b"], runner)
    twin_command = build_shard_command(shards["twin-api"], runner)

    separator = b_command.index("--")
    assert b_command[2:separator]
    assert all("*" not in path for path in b_command[2:separator])
    assert "tests/test_twin_builder.py::TestTwinAPI" in twin_command


def test_default_log_dir_uses_git_common_state_not_the_worktree(tmp_path: Path):
    from scripts.run_local_pytest_matrix import resolve_log_dir

    common_dir = tmp_path / ".git"
    common_dir.mkdir()

    log_dir = resolve_log_dir(None, common_dir=common_dir, run_id="fixed")

    assert log_dir == common_dir / "reva-release-state" / "logs" / "backend-matrix-fixed"


def test_explicit_log_dir_must_be_absolute(tmp_path: Path):
    from scripts.run_local_pytest_matrix import MatrixConfigurationError, resolve_log_dir

    with pytest.raises(MatrixConfigurationError, match="absolute"):
        resolve_log_dir("relative/logs", common_dir=tmp_path, run_id="fixed")


def test_run_matrix_reports_real_failure_code_tail_and_creates_private_logs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    from scripts.run_local_pytest_matrix import Shard, run_matrix

    runner = tmp_path / "fake_runner.py"
    runner.write_text(
        """\
import sys
print('runner output', flush=True)
raise SystemExit(7 if any(arg.endswith('test_fail.py') for arg in sys.argv) else 0)
""",
        encoding="utf-8",
    )
    shards = [
        Shard("pass", ("tests/test_pass.py",), (), (tmp_path / "pass",)),
        Shard("fail", ("tests/test_fail.py",), (), (tmp_path / "fail",)),
    ]
    log_dir = tmp_path / "logs"

    return_code = run_matrix(shards, runner, log_dir, worker_count=2)

    assert return_code == 1
    captured = capsys.readouterr()
    assert "FAILED fail: rc=7" in captured.err
    assert str(log_dir / "fail.log") in captured.err
    assert "runner output" in captured.err
    for label in ("pass", "fail"):
        log_path = log_dir / f"{label}.log"
        assert "runner output" in log_path.read_text(encoding="utf-8")
        assert stat.S_IMODE(log_path.stat().st_mode) == 0o600


def test_failure_summary_reads_the_original_log_not_a_replaced_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    from scripts.run_local_pytest_matrix import Shard, run_matrix

    ready = tmp_path / "ready"
    release = tmp_path / "release"
    runner = tmp_path / "runner.py"
    runner.write_text(
        textwrap.dedent(
            f"""
            from pathlib import Path
            import time

            Path({str(ready)!r}).write_text('ready', encoding='utf-8')
            while not Path({str(release)!r}).exists():
                time.sleep(0.01)
            print('ORIGINAL-FAILURE-LINE', flush=True)
            raise SystemExit(7)
            """
        ),
        encoding="utf-8",
    )
    log_dir = tmp_path / "logs"
    victim = tmp_path / "victim.txt"
    victim.write_text("PRIVATE-VICTIM-LINE\n", encoding="utf-8")

    def replace_path() -> None:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        log_path = log_dir / "fail.log"
        log_path.unlink()
        log_path.symlink_to(victim)
        release.touch()

    replacer = threading.Thread(target=replace_path)
    replacer.start()
    try:
        shard = Shard("fail", ("tests/test_fail.py",), (), (tmp_path / "fail",))
        assert run_matrix([shard], runner, log_dir, worker_count=1) == 1
    finally:
        replacer.join(timeout=5)

    captured = capsys.readouterr()
    assert "ORIGINAL-FAILURE-LINE" in captured.err
    assert "PRIVATE-VICTIM-LINE" not in captured.err
    assert victim.read_text(encoding="utf-8") == "PRIVATE-VICTIM-LINE\n"


def test_run_matrix_never_exceeds_configured_worker_count(tmp_path: Path):
    from scripts.run_local_pytest_matrix import Shard, run_matrix

    runner = tmp_path / "concurrency_runner.py"
    state_path = tmp_path / "state.txt"
    runner.write_text(
        textwrap.dedent(
            f"""
            import fcntl
            from pathlib import Path
            import time

            state_path = Path({str(state_path)!r})
            with state_path.open('a+', encoding='utf-8') as state:
                fcntl.flock(state, fcntl.LOCK_EX)
                state.seek(0)
                values = state.read().strip().split()
                active, peak = (map(int, values) if values else (0, 0))
                active += 1
                peak = max(peak, active)
                state.seek(0)
                state.truncate()
                state.write(f'{{active}} {{peak}}')
                state.flush()
                fcntl.flock(state, fcntl.LOCK_UN)
            time.sleep(0.2)
            with state_path.open('r+', encoding='utf-8') as state:
                fcntl.flock(state, fcntl.LOCK_EX)
                active, peak = map(int, state.read().strip().split())
                state.seek(0)
                state.truncate()
                state.write(f'{{active - 1}} {{peak}}')
                state.flush()
                fcntl.flock(state, fcntl.LOCK_UN)
            """
        ),
        encoding="utf-8",
    )
    shards = [
        Shard(f"shard-{index}", (f"tests/test_{index}.py",), (), (tmp_path,))
        for index in range(5)
    ]

    assert run_matrix(shards, runner, tmp_path / "logs", worker_count=2) == 0
    active, peak = map(int, state_path.read_text(encoding="utf-8").split())
    assert active == 0
    assert peak == 2


def test_run_matrix_clears_python_and_pytest_environment_injections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from scripts.run_local_pytest_matrix import Shard, run_matrix

    runner = tmp_path / "env_runner.py"
    runner.write_text(
        """\
import os
keys = (
    'APP_ENV',
    'DATABASE_URL',
    'TEST_DATABASE_URL',
    'SECRET_KEY',
    'GARMIN_ENCRYPTION_KEY',
    'TZ',
)
print(repr({key: os.environ.get(key) for key in keys}))
print('|'.join(sorted(key for key in os.environ if key.startswith(('PYTHON', 'PYTEST_')))))
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://attacker.invalid/production")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://attacker.invalid/test")
    monkeypatch.setenv("SECRET_KEY", "hostile-secret")
    monkeypatch.setenv("GARMIN_ENCRYPTION_KEY", "hostile-garmin-key")
    monkeypatch.setenv("TZ", "America/New_York")
    monkeypatch.setenv("PYTHONPATH", "/hostile")
    monkeypatch.setenv("PYTHONWARNINGS", "error")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--collect-only")
    monkeypatch.setenv("PYTEST_PLUGINS", "hostile_plugin")
    monkeypatch.setenv("PYTESTHOSTILE", "1")
    shard = Shard("env", ("tests/test_env.py",), (), (tmp_path / "env",))
    log_dir = tmp_path / "logs"

    assert run_matrix([shard], runner, log_dir, worker_count=1) == 0
    lines = (log_dir / "env.log").read_text(encoding="utf-8").splitlines()
    assert lines == [
        repr(
            {
                "APP_ENV": "test",
                "DATABASE_URL": "sqlite:///:memory:",
                "TEST_DATABASE_URL": None,
                "SECRET_KEY": "test-secret-key-32-chars-minimum!!",
                "GARMIN_ENCRYPTION_KEY": (
                    "mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU="
                ),
                "TZ": "Asia/Shanghai",
            }
        ),
        "",
    ]


def test_direct_entry_scrubs_hostile_environment_before_launching_shards(
    tmp_path: Path,
):
    source = (BACKEND_ROOT / "scripts" / "run_local_pytest_matrix.py").read_text(
        encoding="utf-8"
    )
    backend_root = tmp_path / "backend"
    scripts_root = backend_root / "scripts"
    tests_root = backend_root / "tests"
    scripts_root.mkdir(parents=True)
    tests_root.mkdir()
    (scripts_root / "run_local_pytest_matrix.py").write_text(source, encoding="utf-8")
    (tests_root / "test_alpha.py").touch()
    runner = scripts_root / "run_ci_pytest_shard.py"
    runner.write_text(
        """\
import os
from pathlib import Path

keys = ('APP_ENV', 'DATABASE_URL', 'TEST_DATABASE_URL', 'SECRET_KEY', 'GARMIN_ENCRYPTION_KEY', 'TZ')
Path(os.environ['CAPTURE_PATH']).write_text(
    repr({key: os.environ.get(key) for key in keys}) + '\\n' +
    '|'.join(sorted(key for key in os.environ if key.startswith(('PYTHON', 'PYTEST')))),
    encoding='utf-8',
)
""",
        encoding="utf-8",
    )
    repo_root = backend_root.parent
    workflow = repo_root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    _write_workflow(
        workflow,
        """
        - label: alpha
          paths: tests/test_alpha.py
        """,
    )
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    capture_path = tmp_path / "environment.txt"
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql://attacker.invalid/production",
            "TEST_DATABASE_URL": "postgresql://attacker.invalid/test",
            "SECRET_KEY": "hostile-secret",
            "GARMIN_ENCRYPTION_KEY": "hostile-key",
            "TZ": "America/New_York",
            "PYTHONPATH": "/hostile",
            "PYTEST_ADDOPTS": "--collect-only",
            "CAPTURE_PATH": str(capture_path),
            "REVA_BACKEND_SHARD_PARALLEL": "1",
            "REVA_BACKEND_SHARD_LOG_DIR": str(tmp_path / "direct-entry-logs"),
        }
    )

    completed = subprocess.run(
        [sys.executable, str(scripts_root / "run_local_pytest_matrix.py")],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    values, separator, injected = capture_path.read_text(encoding="utf-8").partition(
        "\n"
    )
    assert separator == "\n"
    assert values == repr(
        {
            "APP_ENV": "test",
            "DATABASE_URL": "sqlite:///:memory:",
            "TEST_DATABASE_URL": None,
            "SECRET_KEY": "test-secret-key-32-chars-minimum!!",
            "GARMIN_ENCRYPTION_KEY": (
                "mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU="
            ),
            "TZ": "Asia/Shanghai",
        }
    )
    assert injected == ""


def test_run_matrix_rejects_a_symlink_log_directory(tmp_path: Path):
    from scripts.run_local_pytest_matrix import (
        MatrixConfigurationError,
        Shard,
        run_matrix,
    )

    runner = tmp_path / "runner.py"
    runner.write_text("raise SystemExit(0)\n", encoding="utf-8")
    real_logs = tmp_path / "real-logs"
    real_logs.mkdir()
    linked_logs = tmp_path / "linked-logs"
    linked_logs.symlink_to(real_logs, target_is_directory=True)
    shard = Shard("one", ("tests/test_one.py",), (), (tmp_path / "one",))

    with pytest.raises(MatrixConfigurationError, match="symlink"):
        run_matrix([shard], runner, linked_logs, worker_count=1)


def test_run_matrix_rejects_a_symlinked_log_directory_parent(tmp_path: Path):
    from scripts.run_local_pytest_matrix import (
        MatrixConfigurationError,
        Shard,
        run_matrix,
    )

    runner = tmp_path / "runner.py"
    runner.write_text("raise SystemExit(0)\n", encoding="utf-8")
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    shard = Shard("one", ("tests/test_one.py",), (), (tmp_path / "one",))

    with pytest.raises(MatrixConfigurationError, match="symlink"):
        run_matrix([shard], runner, linked_parent / "logs", worker_count=1)


def test_sigterm_reaps_the_active_shard_process_group(tmp_path: Path):
    runner = tmp_path / "slow_runner.py"
    child_pid_file = tmp_path / "child.pid"
    runner.write_text(
        textwrap.dedent(
            f"""
            import os
            from pathlib import Path
            import time

            Path({str(child_pid_file)!r}).write_text(str(os.getpid()), encoding="utf-8")
            time.sleep(60)
            """
        ),
        encoding="utf-8",
    )
    coordinator = subprocess.Popen(
        [
            sys.executable,
            "-c",
            textwrap.dedent(
                f"""
                from pathlib import Path
                from scripts.run_local_pytest_matrix import Shard, run_matrix
                shard = Shard('slow', ('tests/test_slow.py',), (), (Path('unused'),))
                raise SystemExit(run_matrix([shard], Path({str(runner)!r}), Path({str(tmp_path / 'logs')!r}), worker_count=1))
                """
            ),
        ],
        cwd=BACKEND_ROOT,
    )
    try:
        deadline = time.monotonic() + 5
        while not child_pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert child_pid_file.exists(), "shard runner did not start"
        child_pid = int(child_pid_file.read_text(encoding="utf-8"))

        coordinator.send_signal(signal.SIGTERM)
        assert coordinator.wait(timeout=5) == 128 + signal.SIGTERM

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except OSError as exc:
                if exc.errno == errno.ESRCH:
                    break
                raise
            time.sleep(0.02)
        else:
            pytest.fail("active shard process survived coordinator SIGTERM")
    finally:
        if coordinator.poll() is None:
            coordinator.kill()
            coordinator.wait()
