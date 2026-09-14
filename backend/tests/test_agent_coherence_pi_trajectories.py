"""Real Pi/gateway/owned DB adapter trajectories; provider and broker are synthetic."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import json
import pytest

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.daily_health import DietRecord, GarminData
from app.models.medical_exam import MedicalExam
from app.models.smart_plan import WeeklyPlan, PlanItem
from app.models.user import GarminCredential, User
from app.services.agent_executor import AgentExecutor
from app.services.agent_kernel.types import ExecutionContext


@pytest.fixture(autouse=True)
def _isolate_twin_cache(isolated_agent_protocol_transport, monkeypatch):
    from app.twin.schema import HealthTwin, TwinMeta

    monkeypatch.setattr(
        "app.twin.builder.build_twin",
        lambda _db, user_id, **kwargs: HealthTwin(
            meta=TwinMeta(user_id=user_id, generated_at=datetime.now().astimezone()),
        ),
    )


@pytest.fixture
def clock(monkeypatch):
    now = [datetime.fromisoformat("2026-09-13T23:30:00+08:00")]
    original = ExecutionContext.now.__func__

    def frozen(cls, **kwargs):
        return original(cls, **{**kwargs, "now_utc": now[0]})

    monkeypatch.setattr(ExecutionContext, "now", classmethod(frozen))
    return now


@pytest.fixture
def owned_data(db, auth_user_and_headers, clock):
    user, _ = auth_user_and_headers
    other = User(name="Synthetic other owner", email="coherence-other@example.test")
    db.add(other)
    db.flush()
    today = clock[0].date()
    db.add_all(
        [
            GarminData(
                user_id=user.id,
                record_date=today,
                sleep_score=80,
                total_sleep_duration=420,
            ),
            GarminData(
                user_id=user.id,
                record_date=today + timedelta(days=1),
                sleep_score=11,
                total_sleep_duration=111,
            ),
            GarminData(
                user_id=other.id,
                record_date=today,
                sleep_score=99,
                total_sleep_duration=599,
            ),
            DietRecord(
                user_id=user.id,
                record_date=today - timedelta(days=1),
                meal_type="dinner",
                food_name="合成番茄",
                food_items="合成番茄",
                calories=200,
            ),
        ]
    )
    db.commit()
    return user


@pytest.fixture
def broker(monkeypatch):
    import app.tasks.garmin_sync as task

    enqueued, observed = [], []
    job_id = str(uuid4())

    def enqueue(*args, **kwargs):
        enqueued.append((args, kwargs))
        return SimpleNamespace(id=job_id)

    def result_reader(requested_job):
        observed.append(requested_job)
        return {"task_id": requested_job, "status": "PENDING"}

    monkeypatch.setattr(task.sync_user_garmin_data, "delay", enqueue)
    monkeypatch.setattr(
        "app.services.agent_garmin_sync_status._read_task_meta", result_reader
    )
    return SimpleNamespace(enqueued=enqueued, observed=observed, job_id=job_id)


def script_executor(db, monkeypatch, steps):
    executor = AgentExecutor(db)
    provider_calls, dispatches, results, unexpected = [], [], [], []
    original = executor._dispatch_tool_request

    async def dispatch(request, token):
        dispatches.append(request)
        result = await original(request, token)
        results.append((request, result))
        return result

    async def provider(messages, tools):
        provider_calls.append((messages, tools))
        index = len(provider_calls) - 1
        if index >= len(steps):
            unexpected.append(index)
            yield {"type": "content", "text": "本轮尚未完成，请核实缺失项目。"}
            yield {"type": "finish", "finish_reason": "stop"}
            return
        step = steps[index]
        if isinstance(step, str):
            yield {"type": "content", "text": step}
            yield {"type": "finish", "finish_reason": "stop"}
        else:
            name, args = step
            yield {
                "type": "tool_calls",
                "tool_calls": [
                    {
                        "id": f"coherence-{index}",
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    }
                ],
            }
            yield {"type": "finish", "finish_reason": "tool_calls"}

    monkeypatch.setattr(
        executor, "_build_system_prompt", lambda *a, **k: "根据当前会话和工具证据回答。"
    )
    monkeypatch.setattr(
        executor, "_build_system_knowledge_prompt_context", lambda *a, **k: ""
    )
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)
    return SimpleNamespace(
        executor=executor,
        calls=provider_calls,
        dispatches=dispatches,
        results=results,
        unexpected=unexpected,
    )


async def run(db, trace, user, message, **kwargs):
    events = [
        event
        async for event in trace.executor.run_stream(
            user.id, message, channel="typed", client_turn_id=str(uuid4()), **kwargs
        )
    ]
    done = next(
        event["data"] for event in reversed(events) if event.get("event") == "done"
    )
    assert not trace.unexpected, "The scripted provider should not hide extra retries"
    assert done["perf"]["agent_kernel"] == "pi"
    saved = db.get(AgentMessage, done["message_id"])
    assert saved.meta["turn_outcome"] == done["turn_outcome"]
    assert saved.meta["completion_status"] == done["completion_status"]
    return done, saved


@pytest.mark.asyncio
async def test_sync_then_owned_sleep_followup_preserves_date_and_does_not_enqueue_again(
    db,
    owned_data,
    broker,
    clock,
    monkeypatch,
):
    user = owned_data
    db.add(
        GarminCredential(
            user_id=user.id,
            garmin_email="synthetic@example.test",
            encrypted_password="synthetic",
            sync_enabled=True,
            credentials_valid=True,
            requires_mfa=False,
        )
    )
    db.commit()
    first = script_executor(
        db,
        monkeypatch,
        [
            ("health_record", {"record_type": "garmin_sync", "data": {}}),
            ("health_query", {"dimension": "sleep"}),
            "已查询昨晚睡眠。同步已提交，尚未核实完成。",
        ],
    )
    done, saved = await run(db, first, user, "同步一下佳明，再分析昨晚睡眠。")
    assert len(broker.enqueued) == 1
    assert {r.tool_name for r in first.dispatches} == {"health_record", "health_query"}
    assert saved.meta["read_task"]["queries"] == [
        {
            "dimension": "sleep",
            "start_date": "2026-09-13",
            "end_date": "2026-09-13",
            "timezone": "Asia/Shanghai",
        }
    ]
    assert saved.meta["garmin_sync_job"]["job_id"] == broker.job_id
    clock[0] = datetime.fromisoformat("2026-09-14T00:30:00+08:00")
    second = script_executor(
        db,
        monkeypatch,
        [
            ("health_query", {"dimension": "sleep"}),
            "已重新查询原日期的睡眠，仍未确认同步完成。",
        ],
    )
    again, persisted = await run(
        db, second, user, "再查一下", conversation_id=saved.conversation_id
    )
    assert len(broker.enqueued) == 1
    assert len(second.dispatches) == 1
    request, raw = second.results[0]
    assert (
        request.arguments["start_date"] == request.arguments["end_date"] == "2026-09-13"
    )
    payload = json.loads(raw)
    assert [(row["record_date"], row["sleep_score"]) for row in payload["records"]] == [
        ("2026-09-13", 80)
    ]
    assert payload["sync_job"]["job_id"] == broker.job_id
    assert payload["sync_job"]["job_success_verified"] is False
    assert broker.observed and set(broker.observed) == {broker.job_id}
    assert (
        persisted.meta["read_task"]["created_at"]
        == saved.meta["read_task"]["created_at"]
    )
    assert {
        goal["goal_id"]: goal["status"] for goal in again["turn_outcome"]["goals"]
    } == {"sleep": "verified"}
    assert "同步完成，所有数据已更新" not in persisted.content


@pytest.mark.asyncio
async def test_broad_retrospective_reading_only_diet_is_partial_not_complete(
    db, owned_data, monkeypatch
):
    trace = script_executor(
        db,
        monkeypatch,
        [
            ("health_query", {"dimension": "diet"}),
            "昨天饮食和睡眠都已分析完成。",
        ],
    )
    done, saved = await run(db, trace, owned_data, "分析我昨天的行动。")
    assert (
        len(trace.dispatches) == 1
        and trace.dispatches[0].arguments["dimension"] == "diet"
    )
    assert json.loads(trace.results[0][1])["records"][0]["food_name"] == "合成番茄"
    assert done["turn_outcome"]["status"] == "partial"
    assert (
        done["completion_status"] == "error" and done["generation_status"] == "complete"
    )
    assert {
        goal["goal_id"]: goal["status"] for goal in done["turn_outcome"]["goals"]
    } == {
        "diet": "verified",
        "sleep": "failed",
    }
    assert "饮食和睡眠都已分析完成" not in saved.content


@pytest.mark.asyncio
async def test_status_question_reads_actual_status_without_enqueuing(
    db, owned_data, broker, monkeypatch
):
    trace = script_executor(
        db,
        monkeypatch,
        [
            ("health_query", {"dimension": "garmin"}),
            "没有核实本会话同步完成，已有记录不能证明同步成功。",
        ],
    )
    done, _ = await run(db, trace, owned_data, "佳明的数据同步完了吗？")
    assert not broker.enqueued and not broker.observed
    assert len(trace.dispatches) == 1, [
        m for messages, _ in trace.calls for m in messages if m.get("role") == "tool"
    ]
    status = json.loads(trace.results[0][1])
    assert (
        status["job_success_verified"] is False
        and status["submission_status"] == "unverified"
    )
    assert not done["write_receipts"]


@pytest.mark.asyncio
async def test_status_question_rejects_model_proposed_sync_even_with_valid_credentials(
    db,
    owned_data,
    broker,
    monkeypatch,
):
    db.add(
        GarminCredential(
            user_id=owned_data.id,
            garmin_email="synthetic@example.test",
            encrypted_password="synthetic",
            sync_enabled=True,
            credentials_valid=True,
            requires_mfa=False,
        )
    )
    db.commit()
    trace = script_executor(
        db,
        monkeypatch,
        [
            ("health_record", {"record_type": "garmin_sync", "data": {}}),
            "本轮只是询问状态，尚未确认同步完成。",
        ],
    )
    done, saved = await run(db, trace, owned_data, "佳明的数据同步完了吗？")
    assert not broker.enqueued and not trace.dispatches and not done["write_receipts"]
    assert "garmin_sync_job" not in saved.meta


@pytest.mark.asyncio
async def test_plan_draft_is_an_answer_without_plan_database_write(
    db, owned_data, monkeypatch
):
    before = (db.query(WeeklyPlan).count(), db.query(PlanItem).count())
    trace = script_executor(
        db, monkeypatch, ["今天的计划草稿：按时用餐，睡前减少屏幕使用。"]
    )
    done, saved = await run(db, trace, owned_data, "给我起草今天的计划")
    assert not trace.dispatches and not done["write_receipts"]
    assert before == (db.query(WeeklyPlan).count(), db.query(PlanItem).count())
    assert done["turn_outcome"]["status"] == "complete"
    assert "计划草稿" in saved.content


@pytest.mark.parametrize(
    "message",
    (
        "给我计划这周我应该怎么吃怎么运动。",
        "定我本周的运动计划。",
        "制定我本周的运动的计划。",
    ),
)
@pytest.mark.asyncio
async def test_plan_advice_recovers_when_model_proposes_weekly_plan_write(
    db, owned_data, monkeypatch, message
):
    trace = script_executor(
        db,
        monkeypatch,
        [
            ("manage_plan", {"action": "generate_weekly", "data": {}}),
            "以下只是计划草稿，尚未保存。",
        ],
    )
    done, saved = await run(db, trace, owned_data, message)
    assert not trace.dispatches and not done["write_receipts"]
    assert db.query(WeeklyPlan).count() == db.query(PlanItem).count() == 0
    assert "已保存" not in saved.content
    assert "计划草稿" in saved.content
    assert done["turn_outcome"]["status"] == "complete"
    assert len(trace.calls) == 2
    assert "manage_plan" not in {
        (tool.get("function") or {}).get("name")
        for tool in trace.calls[0][1]
    }
    assert not trace.calls[1][1]


@pytest.mark.asyncio
async def test_plan_advice_recovery_cannot_claim_an_unverified_save(
    db, owned_data, monkeypatch
):
    trace = script_executor(
        db,
        monkeypatch,
        [
            ("manage_plan", {"action": "generate_weekly"}),
            "你的本周运动计划已经保存成功。",
        ],
    )

    done, saved = await run(db, trace, owned_data, "定我本周的运动计划。")

    assert not trace.dispatches and not done["write_receipts"]
    assert db.query(WeeklyPlan).count() == db.query(PlanItem).count() == 0
    assert "保存成功" not in saved.content
    assert "没有执行" in saved.content or "未执行" in saved.content
    assert done["turn_outcome"]["status"] != "complete"


@pytest.mark.asyncio
async def test_owned_medical_exam_advice_reads_report_before_synthesis(
    db, owned_data, monkeypatch, clock
):
    db.add(
        MedicalExam(
            user_id=owned_data.id,
            exam_date=clock[0].date(),
            exam_type="comprehensive",
            overall_assessment="合成体检报告：低密度脂蛋白偏高，建议复核。",
        )
    )
    db.commit()
    trace = script_executor(
        db,
        monkeypatch,
        [
            ("health_query", {"dimension": "medical_exam"}),
            "基于这份报告，可以先复核血脂并与医生确认长期目标。",
        ],
    )

    done, saved = await run(
        db,
        trace,
        owned_data,
        "给我一些建议，基于我的体检报告。",
    )

    assert len(trace.dispatches) == 1
    assert trace.dispatches[0].arguments == {"dimension": "medical_exam"}
    assert "合成体检报告" in trace.results[0][1]
    assert done["turn_outcome"]["status"] == "complete"
    assert "基于这份报告" in saved.content


@pytest.mark.asyncio
async def test_conversation_feedback_keeps_history_but_has_no_tools(
    db, owned_data, monkeypatch
):
    conversation = AgentConversation(user_id=owned_data.id, title="Synthetic dialogue")
    db.add(conversation)
    db.flush()
    db.add_all(
        [
            AgentMessage(
                conversation_id=conversation.id,
                role="user",
                content="我想要的是今天的计划草稿。",
            ),
            AgentMessage(
                conversation_id=conversation.id,
                role="assistant",
                content="请先明确要查询的疾病和日期。",
            ),
        ]
    )
    db.commit()
    trace = script_executor(
        db,
        monkeypatch,
        ["我误把起草计划理解成了疾病查询。我会结合前面的要求重新处理。"],
    )
    done, _ = await run(
        db,
        trace,
        owned_data,
        "这么差，你为什么这么不能理解我呢",
        conversation_id=conversation.id,
    )
    assert trace.calls and all(not tools for _, tools in trace.calls)
    history = trace.calls[0][0]
    assert any(
        m.get("role") == "user" and "今天的计划草稿" in str(m.get("content"))
        for m in history
    )
    assert any(
        m.get("role") == "assistant" and "疾病和日期" in str(m.get("content"))
        for m in history
    )
    assert not trace.dispatches and not done["write_receipts"]
    assert done["turn_outcome"]["status"] == "complete"


@pytest.mark.asyncio
async def test_sync_only_followup_observes_same_job_without_reading_sleep(
    db, owned_data, broker, clock, monkeypatch,
):
    db.add(GarminCredential(
        user_id=owned_data.id, garmin_email='synthetic@example.test',
        encrypted_password='synthetic', sync_enabled=True,
        credentials_valid=True, requires_mfa=False,
    ))
    db.commit()
    calendar_reads = []

    def forbidden_calendar_read(*args, **kwargs):
        calendar_reads.append((args, kwargs))
        raise AssertionError('Sync status alone must not read health records')

    monkeypatch.setattr('app.services.agent_query_window.read_calendar_health_query', forbidden_calendar_read)
    monkeypatch.setattr('app.services.agent_garmin_sync_status.read_calendar_health_query', forbidden_calendar_read)
    first = script_executor(db, monkeypatch, [
        ('health_record', {'record_type': 'garmin_sync', 'data': {}}),
        '同步任务已提交，尚未确认完成。',
    ])
    _, saved = await run(db, first, owned_data, '帮我同步佳明数据')
    assert len(broker.enqueued) == 1
    assert saved.meta['garmin_sync_job']['job_id'] == broker.job_id
    task = saved.meta['read_task']
    assert task['version'] == 'owned-read-task.v2'
    assert task['queries'] == [] and task['sync_status'] is True
    assert task['sync_window'] == {
        'start_date': '2026-09-13', 'end_date': '2026-09-13', 'timezone': 'Asia/Shanghai',
    }
    clock[0] = datetime.fromisoformat('2026-09-14T00:30:00+08:00')
    followup = script_executor(db, monkeypatch, [
        ('health_query', {'dimension': 'garmin'}),
        '同一同步任务仍未核实完成。',
    ])
    done, repeated = await run(db, followup, owned_data, '好了吗', conversation_id=saved.conversation_id)
    assert len(broker.enqueued) == 1
    assert len(followup.dispatches) == 1, [
        m for messages, _ in followup.calls for m in messages if m.get('role') == 'tool'
    ]
    request, raw = followup.results[0]
    assert request.arguments == {'dimension': 'garmin', **task['sync_window']}
    status = json.loads(raw)
    assert status['job_id'] == broker.job_id and status['submission_status'] == 'accepted'
    assert status['job_success_verified'] is False
    assert status['data']['availability'] == status['data']['source_scope'] == 'not_requested'
    assert broker.observed and set(broker.observed) == {broker.job_id}
    assert repeated.meta['read_task'] == task
    assert not calendar_reads and not done['write_receipts']


@pytest.mark.asyncio
async def test_explicit_calendar_batch_reads_both_owned_domains_and_verifies_both(
    db, owned_data, clock, monkeypatch,
):
    db.add(DietRecord(
        user_id=owned_data.id, record_date=clock[0].date(), meal_type='dinner',
        food_name='合成当日批查询番茄', food_items='合成当日批查询番茄', calories=250,
    ))
    db.commit()
    queries = [{
        'dimension': dimension, 'start_date': '2026-09-13',
        'end_date': '2026-09-13', 'timezone': 'Asia/Shanghai',
    } for dimension in ('diet', 'sleep')]
    trace = script_executor(db, monkeypatch, [
        ('health_query_batch', {'queries': queries}),
        '已按指定日期核对饮食和睡眠记录。',
    ])
    done, _ = await run(db, trace, owned_data, '复盘我2026-09-13的饮食和睡眠。')
    assert len(trace.dispatches) == 1, [
        m for messages, _ in trace.calls for m in messages if m.get('role') == 'tool'
    ]
    request, raw = trace.results[0]
    assert request.tool_name == 'health_query_batch' and request.arguments == {'queries': queries}
    payload = json.loads(raw)
    assert payload['status'] == 'success'
    results = {result['dimension']: result for result in payload['results']}
    assert set(results) == {'diet', 'sleep'}
    assert [row['food_name'] for row in results['diet']['records']] == ['合成当日批查询番茄']
    assert [row['sleep_score'] for row in results['sleep']['records']] == [80]
    assert done['turn_outcome']['status'] == done['completion_status'] == 'complete'
    assert {goal['goal_id']: goal['status'] for goal in done['turn_outcome']['goals']} == {
        'diet': 'verified', 'sleep': 'verified',
    }
    assert not done['write_receipts']


@pytest.mark.asyncio
@pytest.mark.parametrize("mixed_raw_parameters", [False, True])
async def test_four_domain_batch_evidence_uses_executed_scope_and_review_has_no_training_ban(
    db, owned_data, clock, monkeypatch, mixed_raw_parameters,
):
    from app.models.daily_health import WorkoutRecord
    from app.models.supplement import SupplementDefinition, SupplementRecord

    definition = SupplementDefinition(user_id=owned_data.id, name="Synthetic evidence fixture", is_active=False)
    db.add(definition)
    db.flush()
    db.add_all([
        WorkoutRecord(user_id=owned_data.id, workout_date=clock[0].date(),
                      workout_name="Synthetic walk", workout_type="walking", duration_seconds=1200,
                      source="synthetic"),
        SupplementRecord(user_id=owned_data.id, supplement_id=definition.id,
                         record_date=clock[0].date(), taken=True),
    ])
    db.commit()
    dimensions = ("diet", "sleep", "workout", "supplements")
    queries = [{"dimension": dimension, "days": 7} for dimension in dimensions]
    if mixed_raw_parameters:
        for query in queries[:2]:
            query.update(start_date="2026-09-07", end_date="2026-09-13", timezone="Asia/Shanghai")
    trace = script_executor(db, monkeypatch, [
        ("health_query_batch", {"queries": queries}),
        "已核对本轮饮食、睡眠、运动与实际服用记录。记录未覆盖的部分仍未知。",
    ])
    done, saved = await run(db, trace, owned_data,
        "我的既往诊断是几个月前的事情。请基于诊断时间判断当前状况，"
        "结合我每天实际服用的补剂、睡眠、运动、情绪、工作和饮食，先调用工具查询已有记录，再给建议。")
    assert len(trace.dispatches) == 1
    assert {q["dimension"] for q in trace.dispatches[0].arguments["queries"]} == set(dimensions)
    assert all(q["start_date"] == "2026-09-07" and q["end_date"] == "2026-09-13"
               for q in trace.dispatches[0].arguments["queries"])
    for evidence in (done["answer_evidence"], saved.meta["answer_evidence"]):
        assert {item["label"].split(" · ")[0] for item in evidence["basis"]} == {"饮食", "睡眠", "运动", "补剂"}
    tool_messages = [m["content"] for messages, _ in trace.calls for m in messages if m.get("role") == "tool"]
    assert tool_messages
    assert not any("[系统恢复数据安全闸]" in content for content in tool_messages)
    assert "recovery_data_guard" not in done
    assert done["turn_outcome"]["status"] == "complete"


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", ["separate", "batch", "mixed"])
async def test_multiline_four_domain_evidence_survives_real_pi_call_grouping(
    db, owned_data, clock, monkeypatch, shape,
):
    from app.models.daily_health import WorkoutRecord
    from app.models.supplement import SupplementDefinition, SupplementRecord

    definition = SupplementDefinition(
        user_id=owned_data.id, name="Synthetic multirow evidence", is_active=False,
    )
    db.add(definition)
    db.flush()
    for offset in range(3):
        day = clock[0].date() - timedelta(days=offset)
        db.add_all([
            DietRecord(user_id=owned_data.id, record_date=day, meal_type="breakfast",
                       food_name="合成早餐", food_items="合成早餐", calories=300),
            WorkoutRecord(user_id=owned_data.id, workout_date=day,
                          workout_name="Synthetic walk", workout_type="walking",
                          duration_seconds=1200, source="synthetic"),
            SupplementRecord(user_id=owned_data.id, supplement_id=definition.id,
                             record_date=day, taken=True),
        ])
        if offset:
            db.add(GarminData(user_id=owned_data.id, record_date=day,
                              sleep_score=80, total_sleep_duration=420))
    db.commit()
    dimensions = ("diet", "sleep", "workout", "supplements")
    queries = [{"dimension": dimension, "days": 7} for dimension in dimensions]
    if shape == "batch":
        calls = [("health_query_batch", {"queries": queries})]
    elif shape == "mixed":
        calls = [("health_query_batch", {"queries": queries[:2]}),
                 *(("health_query", query) for query in queries[2:])]
    else:
        calls = [("health_query", query) for query in queries]
    trace = script_executor(db, monkeypatch, [*calls,
        "已核对本轮饮食、睡眠、运动与实际服用记录。记录未覆盖的部分仍未知。",
    ])
    done, saved = await run(db, trace, owned_data,
        "我的既往诊断是几个月前的事情。请基于诊断时间判断当前状况，"
        "结合我每天实际服用的补剂、睡眠、运动、情绪、工作和饮食，先调用工具查询已有记录，再给建议。")
    assert len(trace.dispatches) == len(calls)
    executed = [query for request in trace.dispatches
                for query in request.arguments.get("queries", [request.arguments])]
    assert {query["dimension"] for query in executed} == set(dimensions)
    assert all(query == {"dimension": query["dimension"], "days": 7,
                         "start_date": "2026-09-07", "end_date": "2026-09-13",
                         "timezone": "Asia/Shanghai"} for query in executed)
    for evidence in (done["answer_evidence"], saved.meta["answer_evidence"]):
        assert len(evidence["basis"]) == 4
        assert {item["label"].split(" · ")[0] for item in evidence["basis"]} == {
            "饮食", "睡眠", "运动", "补剂",
        }
    assert {goal["goal_id"]: goal["status"] for goal in done["turn_outcome"]["goals"]} == {
        dimension: "verified" for dimension in dimensions
    }
    assert done["turn_outcome"]["status"] == done["completion_status"] == "complete"
    assert not done["write_receipts"]
