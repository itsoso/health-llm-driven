"""Summary reports must preserve missingness and exclude private source text."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "food_timing_summary", Path(__file__).resolve().parents[2] / "scripts/summarize_food_vision_timing.py",
)
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


def row(ms, outcome="returned", stage="provider"):
    return f"INFO food_vision_stage input_kind=base64 stage={stage} outcome={outcome} elapsed_ms={ms}\n"


def test_fixed_summary_preserves_tail_and_outcome_groups():
    result = summary.summarize([row(100), row(200), row(1000), row(80, "cancelled"), row(3, stage="decode_sanitize")])
    provider = next(r for r in result["stages"] if r["stage"] == "provider" and r["outcome"] == "returned")
    assert provider == dict(input_kind="base64", stage="provider", outcome="returned", samples=3, p50_ms=200, sample_p95_ms=920, sample_p99_ms=984)
    assert result["events"] == 5


def test_no_events_is_missing_not_zero_and_source_never_leaks():
    result = summary.summarize(["private-synthetic-payload\n", row(-1), row("NaN")])
    assert result["stages"] == []
    assert result["events"] == 0
    assert "private-synthetic-payload" not in json.dumps(result)


def test_event_limit_fails_instead_of_truncating():
    with pytest.raises(ValueError, match="event limit"):
        summary.summarize([row(1), row(2)], max_events=1)
