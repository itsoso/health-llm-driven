"""CI pytest shard runner contract tests."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_discover_test_files_expands_globs_directories_and_deduplicates(tmp_path):
    from scripts.run_ci_pytest_shard import discover_test_files

    tests_dir = tmp_path / "tests"
    nested_dir = tests_dir / "services"
    nested_dir.mkdir(parents=True)
    first = tests_dir / "test_alpha.py"
    second = tests_dir / "test_beta.py"
    nested = nested_dir / "test_nested.py"
    helper = nested_dir / "helper.py"
    for path in (first, second, nested, helper):
        path.write_text("\n", encoding="utf-8")

    discovered = discover_test_files(
        [
            str(tests_dir / "test_*.py"),
            str(first),
            str(nested_dir),
        ]
    )

    assert discovered == [first, second, nested]


def test_discover_test_files_applies_pytest_ignore_rules(tmp_path):
    from scripts.run_ci_pytest_shard import discover_test_files

    tests_dir = tmp_path / "tests"
    services_dir = tests_dir / "services"
    services_dir.mkdir(parents=True)
    keep = tests_dir / "test_alpha.py"
    ignored_glob = tests_dir / "test_beta.py"
    ignored_dir = services_dir / "test_service.py"
    for path in (keep, ignored_glob, ignored_dir):
        path.write_text("\n", encoding="utf-8")

    discovered = discover_test_files(
        [str(tests_dir)],
        [
            f"--ignore={services_dir}",
            f"--ignore-glob={tests_dir / 'test_beta*.py'}",
        ],
    )

    assert discovered == [keep]


def test_build_pytest_commands_uses_one_process_per_file(tmp_path):
    from scripts.run_ci_pytest_shard import build_pytest_commands

    files = [tmp_path / "test_alpha.py", tmp_path / "test_beta.py"]

    commands = build_pytest_commands(files, ["-q", "--no-cov"])

    assert commands == [
        [sys.executable, "-m", "pytest", str(files[0]), "-q", "--no-cov"],
        [sys.executable, "-m", "pytest", str(files[1]), "-q", "--no-cov"],
    ]


def test_run_test_files_stops_and_propagates_first_failure(tmp_path):
    from scripts.run_ci_pytest_shard import run_test_files

    files = [
        tmp_path / "test_alpha.py",
        tmp_path / "test_beta.py",
        tmp_path / "test_gamma.py",
    ]
    calls: list[list[str]] = []

    def fake_runner(command: list[str], *, check: bool) -> subprocess.CompletedProcess:
        calls.append(command)
        return subprocess.CompletedProcess(command, 7 if "test_beta.py" in command[3] else 0)

    return_code = run_test_files(files, ["-q"], runner=fake_runner)

    assert return_code == 7
    assert [Path(command[3]).name for command in calls] == ["test_alpha.py", "test_beta.py"]
