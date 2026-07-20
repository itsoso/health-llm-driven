"""CI pytest shard runner contract tests."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_app_store_demo_account_runs_in_an_isolated_ci_process():
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    shards = workflow["jobs"]["backend-test-shards"]["strategy"]["matrix"]["include"]
    by_label = {shard["label"]: shard for shard in shards}

    assert by_label["app-store-demo-account"]["paths"] == (
        "tests/test_app_store_demo_account.py"
    )
    assert "a-b-rest" not in by_label
    assert "a-rest" not in by_label
    assert by_label["a-early"]["paths"] == "tests"
    assert by_label["a-late"]["paths"] == "tests"
    assert by_label["b"]["paths"] == "tests/test_b*.py"
    for label in ("a-early", "a-late"):
        assert "--ignore=tests/test_app_store_demo_account.py" in by_label[label][
            "extra_args"
        ]
        assert "--ignore-glob='tests/test_agent_*.py'" in by_label[label][
            "extra_args"
        ]
    assert "--ignore-glob='tests/test_a[i-z]*.py'" in by_label["a-early"][
        "extra_args"
    ]
    assert "--ignore-glob='tests/test_a[_a-h]*.py'" in by_label["a-late"][
        "extra_args"
    ]


def test_v_z_and_service_tests_run_in_bounded_ci_processes():
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    shards = workflow["jobs"]["backend-test-shards"]["strategy"]["matrix"]["include"]
    by_label = {shard["label"]: shard for shard in shards}

    assert "v-z" not in by_label
    assert by_label["voice-watch"]["paths"] == "tests/test_v*.py tests/test_wa*.py"
    assert by_label["wearable-reports"]["paths"] == (
        "tests/test_wearable*.py tests/test_weather*.py tests/test_wechat*.py "
        "tests/test_weekly*.py tests/test_weight.py tests/test_womens_health.py"
    )
    assert by_label["workday-workout"]["paths"] == (
        "tests/test_workday*.py tests/test_workout*.py"
    )
    assert by_label["write-z"]["paths"] == "tests/test_write*.py tests/test_z*.py"
    assert by_label["services"]["paths"] == "tests/services/"


def test_agent_a_h_tests_run_in_bounded_ci_processes():
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    shards = workflow["jobs"]["backend-test-shards"]["strategy"]["matrix"]["include"]
    by_label = {shard["label"]: shard for shard in shards}

    assert "agent-a-h" not in by_label
    assert by_label["agent-a-d"]["paths"] == "tests/test_agent_[a-d]*.py"
    assert by_label["agent-e-core"]["paths"] == (
        "tests/test_agent_eval.py tests/test_agent_event_stream.py "
        "tests/test_agent_evidence_card_memo.py tests/test_agent_explicit_cache_flag.py"
    )
    assert by_label["agent-executor-a-h"]["paths"] == (
        "tests/test_agent_executor_[a-h]*.py"
    )
    assert by_label["agent-executor-i-z"]["paths"] == (
        "tests/test_agent_executor_[i-z]*.py"
    )
    assert by_label["agent-f-h"]["paths"] == "tests/test_agent_[f-h]*.py"


def test_build_pytest_command_keeps_the_shard_in_one_process():
    from scripts.run_ci_pytest_shard import build_pytest_command

    command = build_pytest_command(
        ["tests/test_alpha.py", "tests/test_beta.py"],
        ["-q", "--no-cov"],
    )

    assert command == [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_alpha.py",
        "tests/test_beta.py",
        "-q",
        "--no-cov",
    ]


def test_run_shard_retries_timeout_in_a_fresh_process():
    from scripts.run_ci_pytest_shard import run_shard

    calls: list[tuple[list[str], int]] = []

    def fake_attempt(command: list[str], timeout_seconds: int) -> int:
        calls.append((command, timeout_seconds))
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(command, timeout_seconds)
        return 0

    return_code = run_shard(
        ["tests/test_alpha.py"],
        ["-q"],
        timeout_seconds=600,
        max_attempts=2,
        attempt_runner=fake_attempt,
    )

    assert return_code == 0
    assert len(calls) == 2
    assert calls[0][0] == calls[1][0]


def test_run_shard_does_not_retry_assertion_failure():
    from scripts.run_ci_pytest_shard import run_shard

    calls = 0

    def fake_attempt(_command: list[str], _timeout_seconds: int) -> int:
        nonlocal calls
        calls += 1
        return 7

    return_code = run_shard(
        ["tests/test_alpha.py"],
        ["-q"],
        timeout_seconds=600,
        max_attempts=2,
        attempt_runner=fake_attempt,
    )

    assert return_code == 7
    assert calls == 1


def test_run_shard_returns_timeout_code_after_final_timeout():
    from scripts.run_ci_pytest_shard import TIMEOUT_EXIT_CODE, run_shard

    def always_timeout(command: list[str], timeout_seconds: int) -> int:
        raise subprocess.TimeoutExpired(command, timeout_seconds)

    return_code = run_shard(
        ["tests/test_alpha.py"],
        ["-q"],
        timeout_seconds=600,
        max_attempts=2,
        attempt_runner=always_timeout,
    )

    assert return_code == TIMEOUT_EXIT_CODE


def test_run_attempt_terminates_a_hung_process_group():
    from scripts.run_ci_pytest_shard import run_attempt

    command = [sys.executable, "-c", "import time; time.sleep(60)"]
    started_at = time.monotonic()

    with pytest.raises(subprocess.TimeoutExpired):
        run_attempt(command, timeout_seconds=1)

    assert time.monotonic() - started_at < 5
