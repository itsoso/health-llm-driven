"""Synthetic reviewer requests must reach the real authenticated diet API."""

from urllib.parse import urlsplit

import pytest

from app.models.daily_health import DietRecord
from app.services.agent_executor import AgentExecutor


@pytest.mark.parametrize("message, notes", (
    (
        "这是审核账号的测试记录。记录今天午餐：白米饭100克、鸡蛋1个，已经全部吃完。"
        "请估算营养并直接保存这一餐，备注必须保留测试标记 QA-MEAL-A。",
        "测试标记 QA-MEAL-A",
    ),
    ("记录今天午餐：白米饭100克、鸡蛋1个。备注 QA-MEAL-B。", "QA-MEAL-B"),
))
async def test_reviewer_meal_reaches_authenticated_api_and_durable_receipt(
    db, client, auth_user_and_headers, monkeypatch, message, notes,
):
    user, headers = auth_user_and_headers
    executor = AgentExecutor(db)
    posts = []

    async def estimate(food_items):
        assert food_items == "白米饭100克、鸡蛋1个"
        # Synthetic estimator output; this test proves persistence, not accuracy.
        return dict(calories=210, protein=9, carbs=29, fat=6, fiber=1)

    async def no_llm(*args, **kwargs):
        raise AssertionError("A clear single meal must not need tool-decision repair")

    async def no_llm_stream(*args, **kwargs):
        raise AssertionError("A clear single meal must not need tool-decision repair")
        yield  # pragma: no cover

    async def in_process_post(url, headers, data):
        path = urlsplit(url).path
        assert path == "/api/v1/diet/records"
        posts.append(path)
        response = client.post(path, headers=headers, json=data)
        assert response.status_code == 200, response.status_code
        return response.text

    monkeypatch.setattr("app.services.agent_executor._estimate_simple_diet_nutrition", estimate)
    monkeypatch.setattr(executor, "_call_llm", no_llm)
    monkeypatch.setattr(executor, "_call_llm_stream", no_llm_stream)
    monkeypatch.setattr(executor, "_api_post", in_process_post)
    token = headers["Authorization"].removeprefix("Bearer ")
    events = [event async for event in executor.run_stream(
        user_id=user.id, message=message, user_auth_token=token,
        client_turn_id="synthetic-reviewer-meal",
    )]
    done = next(event["data"] for event in events if event.get("event") == "done")
    assert done["turn_outcome"]["category"] == "success"
    assert len(done["write_receipts"]) == 1
    assert posts == ["/api/v1/diet/records"]
    record = db.query(DietRecord).filter_by(user_id=user.id).one()
    assert record.food_items == "白米饭100克、鸡蛋1个"
    assert record.notes == notes
    assert record.calories == 210
    assert str(record.id) == str(done["write_receipts"][0]["resource_id"])

    # Replaying the persisted client turn must not issue another write.
    replay = [event async for event in executor.run_stream(
        user_id=user.id, message=message, user_auth_token=token,
        client_turn_id="synthetic-reviewer-meal",
    )]
    assert any(event.get("event") == "done" for event in replay)
    assert len(posts) == 1
    assert db.query(DietRecord).filter_by(user_id=user.id).count() == 1
