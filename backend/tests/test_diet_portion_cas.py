"""Synthetic owned meal corrections: signed baselines must survive real races."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
from datetime import date
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import update

from app.api.diet import _convert_to_response, update_diet_record
from app.config import settings
from app.models.daily_health import DietRecord
from app.models.user import User
from app.schemas.diet import DietRecordUpdate
from app.services.internal_diet_correction import (
    build_internal_diet_portion_signature, diet_portion_update_fingerprint,
)


@pytest.fixture
def owned_meal(db):
    user = User(username="portion-cas-owner", name="合成份量测试用户", hashed_password="synthetic", is_active=True)
    db.add(user)
    db.flush()
    meal = DietRecord(user_id=user.id, record_date=date(2026, 9, 11),
                      meal_type="lunch", food_items="米饭和青菜", calories=900,
                      protein=60, carbs=90, fat=30, fiber=9)
    db.add(meal)
    db.commit()
    db.refresh(meal)
    baseline = _convert_to_response(meal).model_dump(mode="json")
    return SimpleNamespace(id=user.id), meal.id, baseline


def portion_payload(baseline, divisor=3):
    return {"meal_type": baseline["meal_type"],
            "food_items": f"米饭和青菜（按实际食用1/{divisor}计）",
            **{key: baseline[key] / divisor
               for key in ("calories", "protein", "carbs", "fat", "fiber")}}


def signed(owner, record_id, payload, baseline):
    return build_internal_diet_portion_signature(owner.id, record_id, payload,
                                                baseline_record=baseline)


def apply(session, owner, record_id, payload, signature):
    return update_diet_record(record_id, DietRecordUpdate(**payload),
                              db=session, current_user=owner,
                              internal_portion_signature=signature)


@pytest.mark.parametrize("field,value", [("calories", 1200.0), ("food_items", "面条和鸡蛋"),
                                         ("notes", "已由另一操作核对")])
def test_signed_portion_rejects_changed_baseline_without_overwrite(db, owned_meal, field, value):
    owner, record_id, baseline = owned_meal
    payload = portion_payload(baseline)
    signature = signed(owner, record_id, payload, baseline)
    # Deliberately retain a stale identity-map object, as a request may have
    # loaded it during auth/context work before acquiring the update lock.
    cached = db.get(DietRecord, record_id)
    with Session(db.get_bind()) as writer:
        # Hold timestamp fixed to prove the value snapshot protects writes
        # within the same timestamp precision window as well.
        writer.execute(update(DietRecord).where(DietRecord.id == record_id).values(
            **{field: value, "updated_at": baseline["updated_at"]},
        ))
        writer.commit()
    assert getattr(cached, field) != value
    with pytest.raises(HTTPException) as error:
        apply(db, owner, record_id, payload, signature)
    assert error.value.status_code == 409
    db.rollback()
    current = db.get(DietRecord, record_id)
    assert getattr(current, field) == value
    assert current.food_items != payload["food_items"]


def test_signed_portion_succeeds_once_and_old_snapshot_replay_conflicts(db, owned_meal):
    owner, record_id, baseline = owned_meal
    payload = portion_payload(baseline)
    signature = signed(owner, record_id, payload, baseline)
    result = apply(db, owner, record_id, payload, signature)
    assert result.calories == 300
    with pytest.raises(HTTPException) as error:
        apply(db, owner, record_id, payload, signature)
    assert error.value.status_code == 409
    db.rollback()
    assert db.get(DietRecord, record_id).calories == 300
    # A new authoritative read can repeat the absolute desired state safely.
    refreshed = _convert_to_response(db.get(DietRecord, record_id)).model_dump(mode="json")
    result = apply(db, owner, record_id, payload, signed(owner, record_id, payload, refreshed))
    assert result.calories == 300


@pytest.mark.parametrize("tamper", ["payload", "owner", "record", "baseline", "malformed", "legacy"])
def test_internal_portion_authentication_never_degrades_to_unsigned_update(db, owned_meal, tamper):
    owner, record_id, baseline = owned_meal
    payload = portion_payload(baseline)
    signature = signed(owner, record_id, payload, baseline)
    if tamper == "payload":
        payload["calories"] = 1.0
    elif tamper == "owner":
        signature = signed(SimpleNamespace(id=owner.id + 1), record_id, payload, baseline)
    elif tamper == "record":
        signature = signed(owner, record_id + 1, payload, baseline)
    elif tamper == "legacy":
        old_message = f"diet-portion:v1:{owner.id}:{diet_portion_update_fingerprint(record_id, payload)}"
        signature = hmac.new(str(settings.secret_key).encode(), old_message.encode(), hashlib.sha256).hexdigest()
    elif tamper == "baseline":
        signature = "v2:" + "0" * 64 + ":" + signature.rsplit(":", 1)[-1]
    else:
        signature = "malformed"
    with pytest.raises(HTTPException) as error:
        apply(db, owner, record_id, payload, signature)
    assert error.value.status_code == 403
    db.rollback()
    assert db.get(DietRecord, record_id).calories == 900


def test_signed_portion_cannot_update_foreign_owner_record(db, owned_meal):
    owner, record_id, baseline = owned_meal
    payload = portion_payload(baseline)
    foreign_owner = SimpleNamespace(id=owner.id + 1)
    signature = signed(foreign_owner, record_id, payload, baseline)
    with pytest.raises(HTTPException) as error:
        apply(db, foreign_owner, record_id, payload, signature)
    assert error.value.status_code == 403
    assert db.get(DietRecord, record_id).calories == 900


def test_alcohol_units_are_visible_to_portion_read_and_protected_by_baseline(db, owned_meal):
    owner, record_id, _ = owned_meal
    record = db.get(DietRecord, record_id)
    record.alcohol_units = 3.0
    db.commit()
    baseline = _convert_to_response(record).model_dump(mode="json")
    assert baseline["alcohol_units"] == 3.0
    payload = {**portion_payload(baseline), "alcohol_units": 1.0}
    signature = signed(owner, record_id, payload, baseline)
    with Session(db.get_bind()) as writer:
        writer.execute(update(DietRecord).where(DietRecord.id == record_id).values(
            alcohol_units=6.0, updated_at=record.updated_at,
        ))
        writer.commit()
    with pytest.raises(HTTPException) as error:
        apply(db, owner, record_id, payload, signature)
    assert error.value.status_code == 409
    db.rollback()
    assert db.get(DietRecord, record_id).alcohol_units == 6.0


def test_postgres_concurrent_portion_updates_have_exactly_one_winner(db, owned_meal):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("requires TEST_DATABASE_URL PostgreSQL")
    owner, record_id, baseline = owned_meal
    db.rollback()
    barrier = Barrier(2)

    def worker(divisor):
        payload = portion_payload(baseline, divisor)
        signature = signed(owner, record_id, payload, baseline)
        with Session(db.get_bind()) as session:
            barrier.wait(timeout=5)
            try:
                result = apply(session, owner, record_id, payload, signature)
                return 200, result.calories
            except HTTPException as exc:
                return exc.status_code, None

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, divisor) for divisor in (2, 3)]
        results = [future.result(timeout=15) for future in futures]
    assert sorted(status for status, _ in results) == [200, 409]
    winner = next(calories for status, calories in results if status == 200)
    with Session(db.get_bind()) as reader:
        record = reader.get(DietRecord, record_id)
        assert record.calories == winner
        assert reader.query(DietRecord).count() == 1
