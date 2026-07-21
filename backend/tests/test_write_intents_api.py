"""Focused API-boundary tests for write-intent confirmation failures."""

import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import write_intents
from app.services.medication_intake_batch import (
    ExpiredMedicationIntakePlan,
    MedicationIntakePlanNotPresented,
)


class _RollbackSpy:
    def __init__(self) -> None:
        self.rollback_calls = 0

    def rollback(self) -> None:
        self.rollback_calls += 1


@pytest.mark.asyncio
async def test_confirm_expired_medication_plan_returns_409_without_sensitive_log(
    monkeypatch, caplog
):
    sensitive_detail = "expired: 伊托必利 1粒 at 2026-07-21 18:32"

    def raise_expired(*args, **kwargs):
        raise ExpiredMedicationIntakePlan(sensitive_detail)

    monkeypatch.setattr(write_intents.svc, "confirm", raise_expired)
    db = _RollbackSpy()

    with caplog.at_level(logging.WARNING, logger="app.api.write_intents"):
        with pytest.raises(HTTPException) as caught:
            await write_intents.confirm_write_intent(
                91,
                current_user=SimpleNamespace(id=17),
                db=db,
            )

    assert caught.value.status_code == 409
    assert caught.value.detail == "确认计划已过期，请重新提交记录"
    assert db.rollback_calls == 1
    assert "user_id=17" in caplog.text
    assert "intent_id=91" in caplog.text
    assert "error_type=ExpiredMedicationIntakePlan" in caplog.text
    assert sensitive_detail not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.asyncio
async def test_confirm_generic_failure_keeps_500_and_logs_only_safe_context(
    monkeypatch, caplog
):
    sensitive_detail = "database failed for 替普瑞酮 20mg"

    def raise_generic(*args, **kwargs):
        raise RuntimeError(sensitive_detail)

    monkeypatch.setattr(write_intents.svc, "confirm", raise_generic)
    db = _RollbackSpy()

    with caplog.at_level(logging.ERROR, logger="app.api.write_intents"):
        with pytest.raises(HTTPException) as caught:
            await write_intents.confirm_write_intent(
                92,
                current_user=SimpleNamespace(id=18),
                db=db,
            )

    assert caught.value.status_code == 500
    assert caught.value.detail == "确认执行失败,请稍后重试"
    assert db.rollback_calls == 1
    assert "user_id=18" in caplog.text
    assert "intent_id=92" in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert sensitive_detail not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.asyncio
async def test_confirm_unpresented_medication_plan_returns_safe_409(
    monkeypatch, caplog
):
    sensitive_detail = "not shown: 伊托必利和替普瑞酮各999粒"

    def raise_unpresented(*args, **kwargs):
        raise MedicationIntakePlanNotPresented(sensitive_detail)

    monkeypatch.setattr(write_intents.svc, "confirm", raise_unpresented)
    db = _RollbackSpy()

    with caplog.at_level(logging.WARNING, logger="app.api.write_intents"):
        with pytest.raises(HTTPException) as caught:
            await write_intents.confirm_write_intent(
                93,
                current_user=SimpleNamespace(id=19),
                db=db,
            )

    assert caught.value.status_code == 409
    assert caught.value.detail == "确认计划尚未完整展示，请等待当前回复完成后重试"
    assert db.rollback_calls == 1
    assert sensitive_detail not in caplog.text
    assert "error_type=MedicationIntakePlanNotPresented" in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.asyncio
async def test_dismiss_generic_failure_rolls_back_and_logs_only_safe_context(
    monkeypatch, caplog
):
    sensitive_detail = "projection failed for 伊托必利 1粒"

    def raise_generic(*args, **kwargs):
        raise RuntimeError(sensitive_detail)

    monkeypatch.setattr(write_intents.svc, "dismiss", raise_generic)
    db = _RollbackSpy()

    with caplog.at_level(logging.ERROR, logger="app.api.write_intents"):
        with pytest.raises(HTTPException) as caught:
            await write_intents.dismiss_write_intent(
                94,
                current_user=SimpleNamespace(id=20),
                db=db,
            )

    assert caught.value.status_code == 500
    assert caught.value.detail == "取消执行失败,请稍后重试"
    assert db.rollback_calls == 1
    assert "user_id=20" in caplog.text
    assert "intent_id=94" in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert sensitive_detail not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
