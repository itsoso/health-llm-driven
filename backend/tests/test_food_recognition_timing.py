"""Passive timing must cover both callers without exposing image or model data."""
import asyncio
import json
import logging

import pytest

from app.services.ai import food_recognition as food


@pytest.mark.parametrize("method", ["recognize_food_from_base64", "recognize_food_from_url"])
@pytest.mark.parametrize("outcome", ["valid", "invalid", "error", "cancel", "empty"])
def test_passive_vision_stages_preserve_results_and_cancellation(caplog, method, outcome):
    private = "synthetic-private-sentinel"

    class Provider:
        async def chat_with_vision(self, **kwargs):
            if outcome == "cancel":
                raise asyncio.CancelledError(private)
            if outcome == "error":
                raise RuntimeError(private)
            if outcome == "empty":
                return ""
            if outcome == "invalid":
                return private
            return json.dumps({"foods": [{"name": private, "quantity": "1个", "calories": 80}]})

    service = food.FoodRecognitionService()
    service._provider = Provider()
    with caplog.at_level(logging.INFO, logger=food.__name__):
        if outcome == "cancel":
            with pytest.raises(asyncio.CancelledError):
                asyncio.run(getattr(service, method)(private))
        else:
            result = asyncio.run(getattr(service, method)(private))
            assert result["success"] is (outcome == "valid")
    rows = [r.getMessage() for r in caplog.records if r.getMessage().startswith("food_vision_stage ")]
    assert len(rows) == (2 if outcome in {"valid", "invalid"} else 1)
    assert "stage=provider" in rows[0]
    expected = "cancelled" if outcome == "cancel" else "failed" if outcome == "error" else "returned"
    assert f"outcome={expected}" in rows[0]
    if len(rows) == 2:
        assert "stage=decode_sanitize" in rows[1]
        assert f"outcome={'failed' if outcome == 'invalid' else 'returned'}" in rows[1]
    assert all("elapsed_ms=" in r for r in rows)
    assert private not in caplog.text


def test_stage_duration_uses_monotonic_clock(monkeypatch, caplog):
    values = iter([100.0, 100.125])
    monkeypatch.setattr(food, "perf_counter", lambda: next(values))
    with caplog.at_level(logging.INFO, logger=food.__name__):
        with food._vision_stage("base64", "provider"):
            pass
    assert "elapsed_ms=125" in caplog.text
