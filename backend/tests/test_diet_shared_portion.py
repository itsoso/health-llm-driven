"""Absolute whole-table portions are atomic and never compound on retry."""
from datetime import date
import json
from unittest.mock import Mock

import pytest

from app.models.daily_health import DietRecord
from app.services.ai.food_recognition import food_recognition_service
from app.services.agent_executor import _contextual_meal_consumed_fraction


@pytest.fixture
def meal(db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    record = DietRecord(user_id=user.id, record_date=date.today(), meal_type="lunch",
                        food_items="合成整桌餐食", calories=1000, protein=100,
                        carbs=120, fat=40, fiber=10)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record, headers


def command(client, meal, fraction, key, **overrides):
    record, headers = meal
    payload = {"food_items": "合成整桌餐食", "consumed_fraction": fraction,
               "expected_updated_at": record.updated_at.isoformat() if record.updated_at else None}
    payload.update(overrides)
    return client.post(f"/api/v1/diet/records/{record.id}/recalculate-nutrition",
                       headers={**headers, "Idempotency-Key": key}, json=payload)


def test_absolute_portions_reuse_authoritative_totals_without_rounding_or_model(client, db, meal, monkeypatch):
    estimate = Mock(side_effect=AssertionError("unchanged description must not invoke model"))
    monkeypatch.setattr(food_recognition_service, "estimate_nutrition_from_text", estimate)
    for index, fraction in enumerate((1/5, 1/3, 1/5, 1)):
        response = command(client, meal, fraction, f"portion-sequence-{index}")
        assert response.status_code == 200, response.text
        body = response.json()
        for field, baseline in (("calories", 1000), ("protein", 100), ("carbs", 120), ("fat", 40), ("fiber", 10)):
            assert body[field] == pytest.approx(baseline * fraction)
        assert body["food_items"] == ("合成整桌餐食" if fraction == 1 else f"合成整桌餐食（按实际食用1/{round(1/fraction)}计）")
        db.refresh(meal[0])
    estimate.assert_not_called()


@pytest.mark.parametrize("fraction", [0, -0.2, 1.1, True, "bad", 1e-20])
def test_invalid_portion_is_zero_write(client, db, meal, fraction):
    assert command(client, meal, fraction, "invalid-portion-value").status_code == 422
    db.refresh(meal[0])
    assert meal[0].calories == 1000


def test_fraction_binds_idempotency_and_stale_revision(client, db, meal):
    first = command(client, meal, 0.2, "portion-replay-key")
    assert first.status_code == 200
    assert command(client, meal, 0.2, "portion-replay-key", expected_updated_at=None).status_code == 200
    assert command(client, meal, 0.5, "portion-replay-key", expected_updated_at=None).status_code == 409
    assert command(client, meal, 0.5, "portion-stale-key", expected_updated_at=None).status_code == 409
    db.refresh(meal[0])
    assert meal[0].calories == 200


@pytest.mark.parametrize("structured", [True, False])
def test_changed_description_estimates_whole_table_once_then_scales(client, db, meal, monkeypatch, structured):
    estimate = Mock(return_value={"success": True, "foods": [{"name": "合成牛肉面", "quantity": "五碗",
        "calories": 2000, "protein": 200, "carbs": 240, "fat": 80, "fiber": 20}]})
    monkeypatch.setattr(food_recognition_service, "estimate_nutrition_from_text", estimate)
    response = command(client, meal, 0.2 if structured else None, "changed-table-portion",
        food_items="合成牛肉面五碗" if structured else "合成牛肉面五碗（按实际食用1/5计）")
    assert response.status_code == 200, response.text
    assert response.json()["calories"] == 400
    assert response.json()["protein"] == 40
    estimate.assert_called_once_with("合成牛肉面五碗")


def test_portion_never_trusts_client_writable_raw_totals(client, db, meal, monkeypatch):
    meal[0].ai_raw_result = '{"whole_meal_calories": 5000, "consumed_fraction": 0.01}'
    db.commit()
    response = command(client, meal, 0.2, "untrusted-baseline-json")
    assert response.status_code == 200
    assert response.json()["calories"] == 200


def test_portion_description_change_conflicts_with_update_during_estimate(client, db, meal, monkeypatch):
    def estimate(_text):
        meal[0].food_items = "其他端更新"
        db.commit()
        return {"success": True, "foods": [{"name": "合成米饭", "calories": 1000, "protein": 40}]}
    monkeypatch.setattr(food_recognition_service, "estimate_nutrition_from_text", estimate)
    response = command(client, meal, 0.2, "portion-concurrent-edit", food_items="合成米饭")
    assert response.status_code == 409
    db.refresh(meal[0])
    assert meal[0].food_items == "其他端更新"


@pytest.mark.parametrize("message", ["我只吃了1/5", "这桌菜我只吃了1/5", "聚餐，我只吃了1/5"])
def test_explicit_first_person_shared_photo_portion(message):
    assert _contextual_meal_consumed_fraction(message) == (0.2, "1/5")


@pytest.mark.parametrize("message", ["这桌菜他只吃了1/5", "我可能只吃了1/5", "我只吃了1/5的牛肉",
    "聚餐，我只吃了1/5，不要记录", "这桌菜我只吃了1/5，他吃了1/3", "这桌菜我打算只吃1/5"])
def test_ambiguous_shared_photo_portion_remains_nonwriting(message):
    assert _contextual_meal_consumed_fraction(message) is None


@pytest.mark.parametrize("description", [
    "整桌菜，我只吃了1/5", "整桌菜，我只吃了1/3", "牛肉一盘，仅吃了五分之一",
    "整桌菜，按1/5计算", "整桌菜，我的份额20%", "整桌菜，实际食用一半",
    "整桌菜，剩下4/5", "整桌菜，实际吃了半份", "整桌菜，五人分我一份",
    "整桌菜，吃了1/5",
    "吃了1/5", "这餐吃了1/5", "整桌食用了20%", "摄入三成",
    "all table dishes, I ate 1/5", "table dishes consumed20%", "I had one fifth",
    "food, I consumed half", "20% of the meal",
])
@pytest.mark.parametrize("same_description", [False, True])
def test_structured_fraction_rejects_embedded_consumption_instructions(client, db, meal, monkeypatch, description, same_description):
    if same_description:
        meal[0].food_items = description
        meal[0].calories = 200
        db.commit()
        db.refresh(meal[0])
    estimate = Mock(return_value={"success": True, "foods": [{"name": "整桌菜", "calories": 200, "protein": 20}]})
    monkeypatch.setattr(food_recognition_service, "estimate_nutrition_from_text", estimate)
    response = command(client, meal, 0.2, "ambiguous-inline-portion", food_items=description)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "diet_portion_description_ambiguous"
    estimate.assert_not_called()
    db.refresh(meal[0])
    assert meal[0].calories == (200 if same_description else 1000)


def test_embedded_fraction_is_rejected_even_with_matching_saved_description(client, db, meal):
    meal[0].food_items = "聚餐整桌菜，我只吃了1/5"
    meal[0].calories = 200
    db.commit()
    db.refresh(meal[0])
    response = command(client, meal, 0.2, "existing-ambiguous-meal", food_items=meal[0].food_items)
    assert response.status_code == 422
    db.refresh(meal[0])
    assert meal[0].calories == 200


def test_structured_fraction_allows_item_quantities_without_consumption_instruction(client, meal, monkeypatch):
    estimate = Mock(return_value={"success": True, "foods": [{"name": "米饭青菜", "calories": 500, "protein": 30}]})
    monkeypatch.setattr(food_recognition_service, "estimate_nutrition_from_text", estimate)
    response = command(client, meal, 0.2, "plain-item-quantities", food_items="米饭半碗+青菜一盘")
    assert response.status_code == 200
    assert response.json()["calories"] == 100


@pytest.mark.parametrize("tamper", ["legacy_suffix", "forged_json", "nonascii_signature", "wrong_type_signature", "copied_record_signature", "copied_owner_signature", "changed_nutrition"])
def test_unverified_portion_suffix_requires_whole_meal_reestimate(client, db, meal, monkeypatch, tamper):
    record = meal[0]
    if tamper in {"copied_record_signature", "copied_owner_signature", "changed_nutrition"}:
        assert command(client, meal, 0.2, "signed-original-portion").status_code == 200
        db.refresh(record)
        original_raw = record.ai_raw_result
        if tamper == "copied_record_signature":
            other = DietRecord(user_id=record.user_id, record_date=date.today(), meal_type="lunch",
                               food_items=record.food_items, calories=200, protein=20, carbs=24, fat=8, fiber=2,
                               ai_raw_result=original_raw)
            db.add(other)
            db.commit()
            db.refresh(other)
            meal = (other, meal[1])
        elif tamper == "copied_owner_signature":
            from app.models.user import User
            from app.services.auth import auth_service
            other_user = User(name="Synthetic portion owner", username="portion-other-owner", email="portion-other@example.invalid", hashed_password="synthetic", is_active=True, is_approved=True)
            db.add(other_user)
            db.flush()
            record.user_id = other_user.id
            db.commit()
            db.refresh(record)
            token = auth_service.create_access_token({"sub": str(other_user.id)})
            meal = (record, {"Authorization": f"Bearer {token}"})
        else:
            record.calories = 250
            db.commit()
            db.refresh(record)
    else:
        record.food_items = "合成整桌餐食（按实际食用1/5计）"
        fake_signature = {"forged_json": "0" * 64, "nonascii_signature": "伪" * 64,
                          "wrong_type_signature": {"value": "0" * 64}}.get(tamper)
        record.ai_raw_result = json.dumps({"portion_auth": {"version": 1, "signature": fake_signature}}) if fake_signature is not None else None
        db.commit()
        db.refresh(record)
    estimate = Mock(return_value={"success": True, "foods": [{"name": "合成整桌餐食", "calories": 1500, "protein": 100}]})
    monkeypatch.setattr(food_recognition_service, "estimate_nutrition_from_text", estimate)
    response = command(client, meal, 0.5, "verify-portion-provenance")
    assert response.status_code == 200, response.text
    assert response.json()["calories"] == 750
    estimate.assert_called_once_with("合成整桌餐食")


def test_generic_put_cannot_authorize_portion_baseline(client, db, meal, monkeypatch):
    record, headers = meal
    response = client.put(f"/api/v1/diet/records/{record.id}", headers=headers, json={
        "food_items": "合成整桌餐食（按实际食用1/5计）", "calories": 2000,
        "protein": 150, "carbs": 200, "fat": 80, "fiber": 20,
        "expected_updated_at": None,
    })
    assert response.status_code == 200
    db.refresh(record)
    estimate = Mock(return_value={"success": True, "foods": [{"name": "合成整桌餐食", "calories": 1500, "protein": 100}]})
    monkeypatch.setattr(food_recognition_service, "estimate_nutrition_from_text", estimate)
    result = command(client, meal, 0.5, "generic-put-untrusted-share")
    assert result.status_code == 200
    assert result.json()["calories"] == 750
    estimate.assert_called_once_with("合成整桌餐食")
