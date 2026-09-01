"""CI pytest shard runner contract tests."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SHARD_CATALOG = ROOT / ".github" / "ci" / "backend-pytest-shards.json"


def _shards_by_label() -> dict[str, dict]:
    payload = json.loads(SHARD_CATALOG.read_text(encoding="utf-8"))
    return {
        shard["label"]: {
            **shard,
            "paths": " ".join(shard["paths"]),
            "extra_args": " ".join(shard.get("extra_args", [])),
        }
        for shard in payload["shards"]
    }


def test_non_agent_a_tests_run_in_bounded_ci_processes():
    by_label = _shards_by_label()

    assert by_label["app-store-demo-account"]["paths"] == (
        "tests/test_app_store_demo_account.py"
    )
    assert "a-early" not in by_label
    assert "a-b-rest" not in by_label
    assert "a-rest" not in by_label
    assert by_label["a-action"]["paths"] == "tests/test_action*.py"
    assert by_label["a-agenda"]["paths"] == "tests/test_agenda*.py"
    assert by_label["a-early-rest"]["paths"] == (
        "tests/test_a_to_i_smoke.py tests/test_account*.py "
        "tests/test_activation*.py tests/test_adherence*.py "
        "tests/test_admin*.py tests/test_advice*.py"
    )
    assert by_label["a-late"]["paths"] == "tests"
    assert by_label["b"]["paths"] == "tests/test_b*.py"
    assert "e-g" not in by_label
    assert by_label["e"]["paths"] == "tests/test_e*.py"
    assert by_label["f"]["paths"] == "tests/test_f*.py"
    assert by_label["g"]["paths"] == "tests/test_g*.py"
    assert "--ignore=tests/test_app_store_demo_account.py" in by_label["a-late"][
        "extra_args"
    ]
    assert "--ignore-glob=tests/test_agent_*.py" in by_label["a-late"][
        "extra_args"
    ]
    assert "--ignore-glob=tests/test_a[_a-h]*.py" in by_label["a-late"][
        "extra_args"
    ]


def test_v_z_and_service_tests_run_in_bounded_ci_processes():
    by_label = _shards_by_label()

    assert "v-z" not in by_label
    assert "voice-watch" not in by_label
    assert by_label["voice"]["paths"] == "tests/test_v*.py"
    assert by_label["watch"]["paths"] == "tests/test_wa*.py"
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
    by_label = _shards_by_label()

    assert "agent-a-h" not in by_label
    assert by_label["agent-a-d"]["paths"] == "tests/test_agent_[a-d]*.py"
    assert by_label["agent-e-core"]["paths"] == (
        "tests/test_agent_eval.py tests/test_agent_event_stream.py "
        "tests/test_agent_evidence_card_memo.py tests/test_agent_explicit_cache_flag.py"
    )
    assert "agent-executor-a-h" not in by_label
    assert by_label["agent-executor-a-d"]["paths"] == (
        "tests/test_agent_executor_[a-d]*.py"
    )
    assert by_label["agent-executor-error-fast"]["paths"] == (
        "tests/test_agent_executor_error_sanitization.py "
        "tests/test_agent_executor_failover_gate.py "
        "tests/test_agent_executor_fast_routing.py"
    )
    assert by_label["agent-executor-food"]["paths"] == (
        "tests/test_agent_executor_food_vision.py"
    )
    assert by_label["agent-executor-g-h"]["paths"] == (
        "tests/test_agent_executor_[g-h]*.py"
    )
    assert by_label["agent-executor-i-z"]["paths"] == (
        "tests/test_agent_executor_[i-z]*.py"
    )
    assert by_label["agent-f-h"]["paths"] == "tests/test_agent_[f-h]*.py"


def test_agent_i_z_tests_run_in_bounded_ci_processes():
    by_label = _shards_by_label()

    assert "agent-i-z" not in by_label
    assert by_label["agent-i-l"]["paths"] == "tests/test_agent_[i-l]*.py"
    assert "agent-m-r" not in by_label
    assert "agent-s-z" not in by_label
    assert by_label["agent-m-p"]["paths"] == "tests/test_agent_[m-p]*.py"
    assert by_label["agent-r"]["paths"] == "tests/test_agent_r*.py"
    assert by_label["agent-s-v"]["paths"] == "tests/test_agent_[s-v]*.py"
    assert by_label["agent-w-z"]["paths"] == "tests/test_agent_[w-z]*.py"


def test_observed_slow_alphabetic_families_run_in_single_letter_shards():
    by_label = _shards_by_label()

    assert "c-d" not in by_label
    assert "n-o" not in by_label
    assert by_label["c"]["paths"] == "tests/test_c*.py"
    assert "d" not in by_label
    assert by_label["d-dedao"]["paths"] == (
        "tests/test_dedao*.py tests/test_down_dedao*.py"
    )
    assert by_label["d-diet"]["paths"] == "tests/test_diet*.py"
    assert by_label["d-data-device"]["paths"] == (
        "tests/test_daily*.py tests/test_data*.py tests/test_day*.py "
        "tests/test_desktop*.py tests/test_device*.py"
    )
    assert by_label["d-rest"]["paths"] == (
        "tests/test_dependency*.py tests/test_deploy*.py "
        "tests/test_deprescribing*.py tests/test_deterministic*.py "
        "tests/test_doc*.py tests/test_dogfood*.py tests/test_dossier*.py "
        "tests/test_drug*.py tests/test_dynamic*.py"
    )
    assert by_label["n"]["paths"] == "tests/test_n*.py"
    assert by_label["o"]["paths"] == "tests/test_o*.py"


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


def test_instrument_pytest_args_adds_durations_and_optional_junit_output():
    from scripts.run_ci_pytest_shard import instrument_pytest_args

    args = instrument_pytest_args(
        ["-q", "--no-cov"],
        junit_path="test-results/agent-a-d.xml",
    )

    assert args == [
        "-q",
        "--no-cov",
        "--durations=50",
        "--durations-min=0.01",
        "--junitxml=test-results/agent-a-d.xml",
    ]


def test_instrument_pytest_args_preserves_explicit_timing_options():
    from scripts.run_ci_pytest_shard import instrument_pytest_args

    args = instrument_pytest_args(
        ["--durations", "10", "--durations-min=1"],
        junit_path=None,
    )

    assert args == ["--durations", "10", "--durations-min=1"]


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


def test_balance_shards_uses_longest_processing_time_and_is_deterministic():
    from scripts.build_ci_pytest_matrix import balance_shards

    shards = [
        {"label": "slow", "estimated_seconds": 9},
        {"label": "medium", "estimated_seconds": 5},
        {"label": "small-b", "estimated_seconds": 3},
        {"label": "small-a", "estimated_seconds": 3},
    ]

    workers = balance_shards(shards, worker_count=2)

    assert workers == [
        {
            "label": "balanced-01",
            "shards": "slow",
            "estimated_seconds": 9.0,
        },
        {
            "label": "balanced-02",
            "shards": "medium,small-a,small-b",
            "estimated_seconds": 11.0,
        },
    ]


def test_balance_shards_rejects_duplicate_labels():
    from scripts.build_ci_pytest_matrix import balance_shards

    with pytest.raises(ValueError, match="duplicate shard label"):
        balance_shards(
            [
                {"label": "same", "estimated_seconds": 1},
                {"label": "same", "estimated_seconds": 2},
            ],
            worker_count=2,
        )


def test_expand_path_inputs_preserves_node_ids_and_expands_globs(tmp_path):
    from scripts.run_ci_pytest_worker import expand_path_inputs

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_beta.py").write_text("", encoding="utf-8")
    (tests_dir / "test_alpha.py").write_text("", encoding="utf-8")

    expanded = expand_path_inputs(
        ["tests/test_*.py", "tests/test_alpha.py::TestAPI"],
        cwd=tmp_path,
        exclude_paths=["tests/test_beta.py"],
    )

    assert expanded == [
        "tests/test_alpha.py",
        "tests/test_alpha.py::TestAPI",
    ]


def test_run_worker_keeps_catalog_shards_in_fresh_pytest_processes(tmp_path):
    from scripts.run_ci_pytest_worker import run_worker

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_alpha.py").write_text("", encoding="utf-8")
    (tests_dir / "test_beta.py").write_text("", encoding="utf-8")
    calls: list[tuple[list[str], list[str], int]] = []

    def fake_runner(
        paths: list[str], args: list[str], *, timeout_seconds: int
    ) -> int:
        calls.append((paths, args, timeout_seconds))
        return 0

    catalog = [
        {"label": "alpha", "paths": ["tests/test_alpha.py"], "extra_args": []},
        {
            "label": "beta",
            "paths": ["tests/test_beta.py"],
            "extra_args": ["-vv"],
            "timeout_seconds": 180,
        },
    ]

    result = run_worker(
        ["alpha", "beta"],
        catalog,
        cwd=tmp_path,
        junit_dir=tmp_path / "results",
        shard_runner=fake_runner,
    )

    assert result == 0
    assert calls == [
        (
            ["tests/test_alpha.py"],
            [
                "-q",
                "--no-cov",
                "--tb=short",
                "--maxfail=5",
                "--timeout=120",
                "--timeout-method=signal",
                "--durations=50",
                "--durations-min=0.01",
                f"--junitxml={tmp_path / 'results' / 'alpha.xml'}",
            ],
            180,
        ),
        (
            ["tests/test_beta.py"],
            [
                "-q",
                "--no-cov",
                "--tb=short",
                "--maxfail=5",
                "--timeout=120",
                "--timeout-method=signal",
                "-vv",
                "--durations=50",
                "--durations-min=0.01",
                f"--junitxml={tmp_path / 'results' / 'beta.xml'}",
            ],
            180,
        ),
    ]


def test_run_worker_rejects_non_positive_process_deadline(tmp_path):
    from scripts.run_ci_pytest_worker import run_worker

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_alpha.py").write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="timeout_seconds"):
        run_worker(
            ["alpha"],
            [{
                "label": "alpha",
                "paths": ["tests/test_alpha.py"],
                "timeout_seconds": 0,
            }],
            cwd=tmp_path,
            junit_dir=tmp_path / "results",
        )


def test_shard_timeout_seconds_scales_and_caps_historical_duration():
    from scripts.run_ci_pytest_worker import shard_timeout_seconds

    assert shard_timeout_seconds({"estimated_seconds": 20}) == 180
    assert shard_timeout_seconds({"estimated_seconds": 100}) == 300
    assert shard_timeout_seconds({"estimated_seconds": 300}) == 600
    assert shard_timeout_seconds({
        "estimated_seconds": 300,
        "timeout_seconds": 240,
    }) == 240
