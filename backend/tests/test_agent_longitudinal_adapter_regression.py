"""Independent actual-Pi/actual-read-adapter regression with synthetic DB rows.

Only the provider is scripted. No production data, HTTP, or model calls are used.
The same test can run with the project's isolated PostgreSQL test database.
"""

from datetime import datetime, timedelta
import json

import pytest


@pytest.mark.asyncio
async def test_long_analysis_reads_owned_recent_rows_including_inactive_supplement_history(
    db, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch,
):
    from app.models.agent_conversation import AgentMessage
    from app.models.daily_health import DietRecord, GarminData, WorkoutRecord
    from app.models.supplement import SupplementDefinition, SupplementRecord
    from app.models.user import User
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_kernel.types import ExecutionContext
    from app.twin.schema import HealthTwin, TwinMeta

    user, _ = auth_user_and_headers
    other = User(name="Synthetic other", email="longitudinal-other@example.test")
    db.add(other)
    db.flush()
    now = datetime.fromisoformat("2026-09-13T09:00:00+08:00")
    day = now.date() - timedelta(days=2)
    old = now.date() - timedelta(days=30)
    original_clock = ExecutionContext.now.__func__
    monkeypatch.setattr(ExecutionContext, "now", classmethod(
        lambda cls, **kwargs: original_clock(cls, **{**kwargs, "now_utc": now})
    ))
    monkeypatch.setattr("app.utils.timezone.get_china_today", lambda: now.date())
    monkeypatch.setattr("app.twin.builder.build_twin", lambda _db, uid, **kwargs:
        HealthTwin(meta=TwinMeta(user_id=uid, generated_at=now)))

    inactive = SupplementDefinition(user_id=user.id, name="合成已停用补剂", is_active=False)
    never_taken = SupplementDefinition(user_id=user.id, name="合成仅有计划", is_active=True)
    other_supp = SupplementDefinition(user_id=other.id, name="OTHER_OWNER_SUPPLEMENT", is_active=True)
    db.add_all([inactive, never_taken, other_supp])
    db.flush()
    db.add_all([
        SupplementRecord(user_id=user.id, supplement_id=inactive.id, record_date=day, taken=True),
        SupplementRecord(user_id=other.id, supplement_id=other_supp.id, record_date=day, taken=True),
    ])
    for uid, date_, marker in (
        (user.id, day, "合成近期"), (other.id, day, "OTHER_OWNER"),
        (user.id, old, "OUTSIDE_WINDOW"),
    ):
        db.add_all([
            DietRecord(user_id=uid, record_date=date_, meal_type="dinner",
                       food_name=marker + "餐食", food_items=marker + "餐食", calories=300),
            WorkoutRecord(user_id=uid, workout_date=date_, workout_type="walking",
                          workout_name=marker + "步行", duration_seconds=1800),
            GarminData(user_id=uid, record_date=date_,
                       sleep_score=77 if marker == "合成近期" else 99,
                       total_sleep_duration=420),
        ])
    db.commit()
    expected_workout_id = db.query(WorkoutRecord.id).filter_by(
        user_id=user.id, workout_date=day,
    ).scalar()
    models = (DietRecord, WorkoutRecord, GarminData, SupplementRecord, SupplementDefinition)

    def fingerprint():
        return [[tuple(getattr(row, col.name) for col in model.__table__.columns)
                 for row in db.query(model).order_by(model.id).all()] for model in models]

    before = fingerprint()
    executor = AgentExecutor(db)
    original_dispatch = executor._dispatch_tool_request
    calls, results = [], {}
    dimensions = ("sleep", "diet", "workout", "supplements")

    async def provider(messages, tools):
        calls.append(tools)
        if len(calls) == 1:
            yield {"type": "tool_calls", "tool_calls": [
                {"id": f"adapter-{d}", "type": "function", "function": {
                    "name": "health_query", "arguments": json.dumps({"dimension": d, "days": 7}),
                }} for d in dimensions
            ]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": (
                "已查询最近7天的睡眠、饮食、运动和补剂服用记录。"
                "有合成近期餐食、合成近期步行和合成已停用补剂的服用打卡。"
                "打卡与当前计划不同，缺失记录不能视为未服用。"
            )}
            yield {"type": "finish", "finish_reason": "stop"}

    async def observe_dispatch(request, token):
        result = await original_dispatch(request, token)
        results[request.arguments.get("dimension", request.arguments.get("record_type"))] = result
        return result

    async def read_with_fixture_session(reader, *args, **kwargs):
        # Keep the actual reader while binding its session to this test DB.
        return reader(db, *args, **kwargs)

    monkeypatch.setattr(executor, "_read_in_process", read_with_fixture_session)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "按工具证据回答。")
    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", lambda *a, **k: "")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_dispatch_tool_request", observe_dispatch)
    events = [event async for event in executor.run_stream(
        user.id,
        "请结合我的日常饮食、每天睡眠、运动状态和实际服用的补剂，分析我当前的状况。"
        "要分别调用相关模块的HTTP接口或Skills，依据真实数据给我建议。",
        client_turn_id="longitudinal-actual-adapter",
    )]
    done = next(e["data"] for e in reversed(events) if e.get("event") == "done")
    saved = db.get(AgentMessage, done["message_id"])
    assert done["perf"]["agent_kernel"] == "pi"
    assert set(results) == set(dimensions), results.keys()
    assert "合成近期餐食" in results["diet"], "Recent diet must include days before today"
    workouts = json.loads(results["workout"])["records"]
    assert [(r["id"], r["record_date"]) for r in workouts] == [(expected_workout_id, day.isoformat())]
    sleep = json.loads(results["sleep"])["records"]
    assert [(r["record_date"], r["sleep_score"]) for r in sleep] == [(day.isoformat(), 77)]
    assert "合成已停用补剂" in results["supplements"], "Actual intake survives definition deactivation"
    assert "合成仅有计划" not in results["supplements"], "Unconsumed plan is not actual intake"
    assert "OTHER_OWNER" not in "".join(results.values())
    assert "OUTSIDE_WINDOW" not in "".join(results.values())
    assert not any(result.startswith("Error:") for result in results.values())
    assert "这次查询未执行" not in saved.content
    assert not done.get("write_receipts")
    assert fingerprint() == before
