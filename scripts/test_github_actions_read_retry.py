"""Bounded, atomic retry contract for read-only GitHub Actions evidence."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import github_actions_read_retry as retry


def test_transient_failure_retries_inside_one_read_and_replaces_atomically(tmp_path: Path) -> None:
    output = tmp_path / "jobs.json"
    output.write_bytes(b"previous")
    calls: list[list[str]] = []
    sleeps: list[float] = []

    def run(command, *, stdout, stderr, check):
        calls.append(command)
        stdout.write(b"partial" if len(calls) == 1 else b"complete")
        return SimpleNamespace(returncode=1 if len(calls) == 1 else 0, stderr=b"ignored")

    retry.read_action_resource(
        repository="itsoso/health-llm-driven",
        run_id=41068488731,
        resource="jobs",
        output=output,
        run=run,
        sleep=sleeps.append,
    )

    assert len(calls) == 2
    assert calls[0][-1] == "repos/itsoso/health-llm-driven/actions/runs/41068488731/jobs?per_page=100"
    assert sleeps == [1.0]
    assert output.read_bytes() == b"complete"
    assert list(tmp_path.iterdir()) == [output]


def test_exhausted_read_preserves_prior_output_and_fails_closed(tmp_path: Path) -> None:
    output = tmp_path / "logs.zip"
    output.write_bytes(b"previous")
    calls = 0
    sleeps: list[float] = []

    def run(command, *, stdout, stderr, check):
        nonlocal calls
        calls += 1
        stdout.write(b"partial")
        return SimpleNamespace(returncode=1, stderr=b"token must not be echoed")

    with pytest.raises(retry.ReadError, match="logs.*3 attempts"):
        retry.read_action_resource(
            repository="itsoso/health-llm-driven",
            run_id=41068488731,
            resource="logs",
            output=output,
            run=run,
            sleep=sleeps.append,
        )

    assert calls == 3
    assert sleeps == [1.0, 2.0]
    assert output.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [output]


def test_successful_main_run_list_is_one_fixed_bounded_read(tmp_path: Path) -> None:
    output = tmp_path / "runs.json"
    calls: list[list[str]] = []

    def run(command, *, stdout, stderr, check):
        calls.append(command)
        stdout.write(b"[]")
        return SimpleNamespace(returncode=0, stderr=b"")

    retry.read_action_resource(
        repository="itsoso/health-llm-driven",
        run_id=None,
        resource="runs",
        output=output,
        run=run,
    )

    assert calls == [[
        "gh", "run", "list",
        "--repo", "itsoso/health-llm-driven",
        "--workflow", "CI",
        "--branch", "main",
        "--status", "success",
        "--limit", "12",
        "--json", "databaseId,headSha,headBranch,workflowName,status,conclusion,attempt",
    ]]
    assert output.read_bytes() == b"[]"


@pytest.mark.parametrize(
    ("repository", "run_id", "resource"),
    [
        ("owner", 1, "jobs"),
        ("owner/repo/extra", 1, "jobs"),
        ("owner/repo", 0, "jobs"),
        ("owner/repo", True, "jobs"),
        ("owner/repo", 1, "artifacts"),
        ("owner/repo", 1, "runs"),
    ],
)
def test_unbounded_targets_are_rejected(repository: str, run_id: int, resource: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        retry.read_action_resource(
            repository=repository,
            run_id=run_id,
            resource=resource,
            output=tmp_path / "out",
        )
