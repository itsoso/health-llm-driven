from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from staking_report.collector import CollectionResult, collect_safely  # noqa: E402


def test_collection_failure_is_structured() -> None:
    def fail():
        raise TimeoutError("beacon timed out")

    result = collect_safely("beacon.validator", fail)
    assert result == CollectionResult(value=None, complete=False, error="beacon.validator: beacon timed out")
