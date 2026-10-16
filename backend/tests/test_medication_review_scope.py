from dataclasses import replace
import pytest
from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.types import ToolExecutionRequest
from tests.test_recent_workout_read_regression import snapshot

PROMPT = "请基于我的在用药品列表，帮我整理今天的用药执行情况、可能需要向医生确认的问题、近期不适该如何描述。不要建议我自行停药、换药或改剂量。"


def test_medication_review_binds_today_owner():
    decision = decide_tool_capability(
        snapshot(PROMPT),
        ToolExecutionRequest("health_query", {"dimension": "medication"}),
    )
    assert decision.action == "allow", decision.reason
    assert decision.normalized_args == {
        "dimension": "medication",
        "start_date": "2026-10-10",
        "end_date": "2026-10-10",
        "timezone": "Asia/Shanghai",
    }


@pytest.mark.parametrize(
    "text",
    [
        PROMPT.replace("我的", "我妈妈的"),
        "解释“" + PROMPT + "”",
        "不要" + PROMPT,
        PROMPT + "查询我朋友的用药",
        PROMPT.replace("今天", "去年"),
    ],
)
def test_modified_review_not_authority(text):
    assert (
        decide_tool_capability(
            snapshot(text),
            ToolExecutionRequest("health_query", {"dimension": "medication"}),
        ).action
        == "block"
    )


@pytest.mark.parametrize(
    "tool,args",
    [
        ("health_record", {"record_type": "medication"}),
        ("health_query", {"dimension": "illness"}),
        ("health_query", {"dimension": "medication", "user_id": 42}),
        ("health_query", {"dimension": "medication", "days": 365}),
        ("health_manage", {"record_type": "medication", "operation": "delete"}),
    ],
)
def test_review_cannot_widen(tool, args):
    assert (
        decide_tool_capability(
            snapshot(PROMPT), ToolExecutionRequest(tool, args)
        ).action
        == "block"
    )


def test_review_requires_same_authenticated_owner():
    turn = snapshot(PROMPT)
    turn = replace(turn, context=replace(turn.context, user_id=42))
    assert (
        decide_tool_capability(
            turn, ToolExecutionRequest("health_query", {"dimension": "medication"})
        ).action
        == "block"
    )


@pytest.mark.parametrize(
    "zone,day", [("Asia/Shanghai", "2026-10-10"), ("America/Los_Angeles", "2026-10-09")]
)
def test_local_day_and_ascii_product_prompt(zone, day):
    turn = snapshot(PROMPT.replace("，", ", "))
    turn = replace(turn, context=replace(turn.context, timezone=zone))
    decision = decide_tool_capability(
        turn, ToolExecutionRequest("health_query", {"dimension": "medication"})
    )
    assert decision.action == "allow"
    assert decision.normalized_args["start_date"] == day


@pytest.mark.asyncio
async def test_executor_reads_only_owned_today_not_list_as_intake(
    db, auth_user_and_headers
):
    import json
    from datetime import date
    from app.models.medication import Medication, MedicationLog
    from app.models.user import User
    from app.services.agent_executor import AgentExecutor

    user, _ = auth_user_and_headers
    other = User(name="Synthetic other", email="med-review-other@example.test")
    db.add(other)
    db.flush()
    own = Medication(user_id=user.id, name="Synthetic own", is_active=True)
    foreign = Medication(user_id=other.id, name="Foreign secret", is_active=True)
    db.add_all([own, foreign])
    db.flush()
    db.add_all(
        [
            MedicationLog(
                user_id=user.id,
                medication_id=own.id,
                taken_date=date(2026, 10, 10),
                taken_time="08:00",
                status="skipped",
            ),
            MedicationLog(
                user_id=user.id,
                medication_id=own.id,
                taken_date=date(2026, 10, 9),
                taken_time="08:00",
                status="taken",
            ),
            MedicationLog(
                user_id=other.id,
                medication_id=foreign.id,
                taken_date=date(2026, 10, 10),
                taken_time="08:00",
                status="taken",
            ),
            MedicationLog(
                user_id=user.id,
                medication_id=foreign.id,
                taken_date=date(2026, 10, 10),
                taken_time="09:00",
                status="taken",
            ),
        ]
    )
    db.commit()
    turn = snapshot(PROMPT)
    turn = replace(
        turn,
        envelope=replace(turn.envelope, user_id=user.id),
        context=replace(turn.context, user_id=user.id),
    )
    decision = decide_tool_capability(
        turn, ToolExecutionRequest("health_query", {"dimension": "medication"})
    )
    executor = AgentExecutor(db)
    executor._agent_kernel_snapshot = turn
    executor._current_user_id = user.id
    executor._current_turn_user_message = PROMPT
    result = json.loads(
        await executor._exec_health_query("", {}, decision.normalized_args)
    )
    assert [m["id"] for m in result["active_medications"]] == [own.id]
    assert len(result["records"]) == 1
    assert result["records"][0]["status"] == "skipped"
    assert "Foreign secret" not in json.dumps(result)
    assert "无打卡不等于未服用" in "".join(result["limitations"])
    assert db.query(MedicationLog).count() == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["health_query", "health_query_batch"])
@pytest.mark.parametrize("has_active", [False, True])
async def test_product_review_real_gateway_and_saved_response(
    db,
    auth_user_and_headers,
    isolated_agent_protocol_transport,
    monkeypatch,
    tool_name,
    has_active,
):
    import json
    from datetime import datetime
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_kernel.types import ExecutionContext
    from app.models.agent_conversation import AgentMessage
    from app.twin.schema import HealthTwin, TwinMeta

    user, _ = auth_user_and_headers
    if has_active:
        from app.models.medication import Medication

        db.add(Medication(user_id=user.id, name="Synthetic active", is_active=True))
        db.commit()
    now = datetime.fromisoformat("2026-10-10T09:00:00+08:00")
    clock = ExecutionContext.now.__func__
    monkeypatch.setattr(
        ExecutionContext,
        "now",
        classmethod(lambda cls, **kw: clock(cls, **{**kw, "now_utc": now})),
    )
    monkeypatch.setattr(
        "app.twin.builder.build_twin",
        lambda _db, uid, **kw: HealthTwin(meta=TwinMeta(user_id=uid, generated_at=now)),
    )
    executor = AgentExecutor(db)
    count = 0
    results = []
    dispatch = executor._dispatch_tool_request

    async def provider(messages, tools):
        nonlocal count
        count += 1
        if count == 1:
            yield {
                "type": "tool_calls",
                "tool_calls": [
                    {
                        "id": "med-review",
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(
                                {"dimension": "medication"}
                                if tool_name == "health_query"
                                else {"queries": [{"dimension": "medication"}]}
                            ),
                        },
                    }
                ],
            }
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {
                "type": "content",
                "text": "今日未查询到用药执行记录，不能据此判断是否服用。请补充不适表现，整理后向医生确认。",
            }
            yield {"type": "finish", "finish_reason": "stop"}

    async def observe(request, token):
        result = await dispatch(request, token)
        results.append(result)
        return result

    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_dispatch_tool_request", observe)
    monkeypatch.setattr(
        executor,
        "_build_system_prompt",
        lambda *a, **k: "按证据回答，不建议自行调整用药。",
    )
    monkeypatch.setattr(
        executor, "_build_system_knowledge_prompt_context", lambda *a, **k: ""
    )
    events = [
        e
        async for e in executor.run_stream(
            user.id, PROMPT, client_turn_id="med-review-synthetic"
        )
    ]
    done = next(e["data"] for e in reversed(events) if e.get("event") == "done")
    assert done["turn_outcome"]["status"] == "complete", done
    assert results
    payload = json.loads(results[0])
    evidence = payload if tool_name == "health_query" else payload["results"][0]
    assert evidence["dimension"] == "medication"
    assert evidence["availability"] == "no_data" and evidence["records"] == []
    assert len(evidence["active_medications"]) == int(has_active)
    projected = executor._composed_read_completion().verified_evidence["queries"][0]
    assert len(projected["active_medications"]) == int(has_active)
    assert projected["record_count"] == 0
    assert (
        "只能查询当前登录用户" not in db.get(AgentMessage, done["message_id"]).content
    )
    assert not done.get("write_receipts")


def test_batch_and_explicit_window_are_bound_identically():
    args = {"queries": [{"dimension": "medication"}]}
    decision = decide_tool_capability(
        snapshot(PROMPT), ToolExecutionRequest("health_query_batch", args)
    )
    assert decision.action == "allow", decision.reason
    assert decision.normalized_args["queries"][0]["start_date"] == "2026-10-10"


@pytest.mark.parametrize(
    "extra",
    [
        {"start_date": "2026-10-09"},
        {"timezone": "UTC"},
        {"keyword": "foreign"},
        {"medication_id": 1000},
        {"user_id": True},
    ],
)
def test_no_model_filters_or_stale_window(extra):
    assert (
        decide_tool_capability(
            snapshot(PROMPT),
            ToolExecutionRequest("health_query", {"dimension": "medication", **extra}),
        ).action
        == "block"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["owner", "window", "extra"])
async def test_execution_adapter_rejects_tampering_without_database_access(tamper):
    from app.services.agent_executor import AgentExecutor

    turn = snapshot(PROMPT)
    args = decide_tool_capability(
        turn, ToolExecutionRequest("health_query", {"dimension": "medication"})
    ).normalized_args
    executor = AgentExecutor(None)
    executor._agent_kernel_snapshot = turn
    executor._current_user_id = turn.context.user_id
    executor._current_turn_user_message = PROMPT
    if tamper == "owner":
        executor._current_user_id = 42
    elif tamper == "window":
        args = {**args, "start_date": "2020-01-01"}
    else:
        args = {**args, "user_id": 42}
    assert (await executor._exec_health_query("", {}, args)).startswith("Error:")


def test_empty_and_oversize_are_distinct(db, auth_user_and_headers):
    from app.models.medication import Medication
    from app.services.agent_query_window import parse_query_window
    from app.services.medication_review_read import read_medication_review

    user, _ = auth_user_and_headers
    window = parse_query_window(
        {
            "start_date": "2026-10-10",
            "end_date": "2026-10-10",
            "timezone": "Asia/Shanghai",
        }
    )
    empty = read_medication_review(db, user.id, window)
    assert empty["availability"] == "no_data"
    assert empty["records"] == [] and empty["active_medications"] == []
    db.add_all(
        [
            Medication(user_id=user.id, name=f"Synthetic {i}", is_active=True)
            for i in range(201)
        ]
    )
    db.flush()
    with pytest.raises(ValueError, match="result_limit_exceeded"):
        read_medication_review(db, user.id, window)


def test_completion_rejects_malformed_medication_evidence():
    from app.services.agent_composed_read_completion import _validate

    bound = {
        "dimension": "medication",
        "start_date": "2026-10-10",
        "end_date": "2026-10-10",
        "timezone": "Asia/Shanghai",
    }
    payload = {
        "dimension": "medication",
        "window": {k: v for k, v in bound.items() if k != "dimension"},
        "availability": "available",
        "active_medications": [],
        "records": [{"record_date": "2026-10-10", "medication_id": 1, "status": []}],
    }
    assert _validate(bound, payload) == "query_result_unavailable"
