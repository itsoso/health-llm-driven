"""Exact screenshot request: owned candidate read, never an invented event."""
from datetime import datetime

import pytest

from app.services.agent_kernel.capability_policy import decide_tool_capability, SPECIALIST_READ_ONLY_TOOLS
from app.services.agent_kernel.health_semantics import health_read_has_nonself_subject
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot


def snapshot(text):
    envelope = AgentEnvelope(user_id=41, channel="typed", text=text)
    context = ExecutionContext(user_id=41, channel="typed", timezone="Asia/Shanghai",
                               current_time=datetime.fromisoformat("2026-10-09T17:00:00+00:00"))
    return TurnSnapshot(envelope, context, build_intent_frame(envelope, context))


@pytest.mark.parametrize('text,kind', [
    ('刚才跑的怎么样？', 'running'), ('我刚刚跑得怎么样?', 'running'),
    ('刚才的跑步如何？', 'running'), ('刚刚骑得怎么样？', 'cycling'),
    ('刚才游得怎样？', 'swimming'), ('本人刚才的步行怎么样？', 'walking'),
])
def test_recent_workout_questions_bind_authenticated_owner_and_type(text, kind):
    turn = snapshot(text)
    scope = resolve_owned_read_scope(turn)
    assert scope is not None
    assert scope.workout_selection.workout_type == kind
    assert scope.query('workout') == {
        'dimension': 'workout', 'start_date': '2026-10-10',
        'end_date': '2026-10-10', 'timezone': 'Asia/Shanghai',
    }
    decision = decide_tool_capability(turn, ToolExecutionRequest('health_query', {'dimension': 'workout'}))
    assert decision.action == 'allow', decision.reason


@pytest.mark.parametrize('text', [
    '刚才跑的怎么样？查询妈妈的记录', '小王刚才跑的怎么样？',
    '我朋友刚才跑的怎么样？', '如果问刚才跑的怎么样？',
    '解释“刚才跑的怎么样？”', '不要查询刚才跑的怎么样？',
    '刚才跑的怎么样？只看去年', '刚才跑的怎么样？删除记录',
    '刚才跑的怎么样？同步佳明', '刚才跑的不错',
])
def test_recent_question_modifiers_do_not_grant_owned_reads(text):
    assert decide_tool_capability(snapshot(text), ToolExecutionRequest(
        'health_query', {'dimension': 'workout'})).action == 'block'


@pytest.mark.parametrize('text', ['刚才旅游回来', '刚才跑腿买了东西', '刚才骑马回来'])
def test_short_workout_verbs_do_not_match_other_words(text):
    from app.services.agent_longitudinal_read import has_recent_workout_reference
    assert not has_recent_workout_reference(text)


@pytest.mark.parametrize('zone,day', [('Asia/Shanghai', '2026-10-10'), ('America/Los_Angeles', '2026-10-09')])
def test_recent_question_uses_account_local_day(zone, day):
    from dataclasses import replace
    turn = snapshot('刚才跑的怎么样？')
    turn = replace(turn, context=replace(turn.context, timezone=zone))
    scope = resolve_owned_read_scope(turn)
    assert scope.query('workout')['start_date'] == day
    assert scope.query('workout')['end_date'] == day


def test_unresolved_read_notice_does_not_prove_missing_user_identity():
    from app.services.agent_executor import AgentExecutor
    executor = AgentExecutor(None)
    executor._agent_kernel_snapshot = snapshot('查询运动情况')
    executor._current_user_id = 41
    executor._current_turn_user_message = '查询运动情况'
    executor._agent_kernel_capability_block_reasons = ['health_query_semantics_unresolved']
    assert '本轮数据查询未完成' in executor._unresolved_read_failure_notice()
    executor._agent_kernel_capability_block_reasons = ['health_query_subject_not_current_user']
    assert executor._unresolved_read_failure_notice() is None


@pytest.mark.parametrize("text", [
    "分析刚才的运动", "分析我刚才的运动", "请帮我分析一下刚刚的运动记录。",
    "看看我刚才的锻炼数据", "复盘刚刚的训练",
])
def test_recent_workout_reads_current_local_day_candidates(text):
    turn = snapshot(text)
    assert not health_read_has_nonself_subject(text)
    scope = resolve_owned_read_scope(turn)
    assert scope is not None
    expected = {"dimension": "workout", "start_date": "2026-10-10",
                "end_date": "2026-10-10", "timezone": "Asia/Shanghai"}
    assert scope.query("workout") == expected
    assert "recent_workout_candidates_not_identified_event" in scope.limitations
    decision = decide_tool_capability(turn, ToolExecutionRequest("health_query", {"dimension": "workout"}))
    assert decision.action == "allow", decision.reason
    assert decision.normalized_args == expected


def test_named_two_rides_bind_the_screenshot_without_widening_the_tool_arguments():
    text = '分析青山湖骑行刚才的两段骑行。'
    turn = snapshot(text)
    scope = resolve_owned_read_scope(turn)
    assert scope is not None
    assert scope.workout_selection.workout_type == 'cycling'
    assert scope.workout_selection.reported_location == '青山湖'
    assert scope.workout_selection.expected_count == 2
    decision = decide_tool_capability(turn, ToolExecutionRequest('health_query', {'dimension': 'workout'}))
    assert decision.action == 'allow', decision.reason
    assert decision.normalized_args == scope.query('workout')
    assert decide_tool_capability(turn, ToolExecutionRequest('health_query', {
        'dimension': 'workout', 'workout_type': 'running', 'limit': 2,
    })).action == 'block'


@pytest.mark.parametrize('text', [
    '分析我朋友青山湖骑行刚才的两段骑行。',
    '不要分析青山湖骑行刚才的两段骑行。',
    '例句：“分析青山湖骑行刚才的两段骑行。”',
    '如果有空，分析青山湖骑行刚才的两段骑行。',
    '分析青山湖骑行刚才的两段骑行，并同步佳明。',
    '分析青山湖骑行刚才的两段骑行，仅看去年。',
    '分析青山湖骑行刚才的两段骑行，看看血氧。',
    '分析小王刚才的两段骑行。',
])
def test_named_ride_modifiers_cannot_disappear_into_owned_authority(text):
    assert decide_tool_capability(snapshot(text), ToolExecutionRequest(
        'health_query', {'dimension': 'workout'})).action == 'block'


def test_quoted_ride_request_does_not_block_public_knowledge_explanation():
    turn = snapshot('解释例句：“分析青山湖骑行刚才的两段骑行。”')
    assert decide_tool_capability(turn, ToolExecutionRequest(
        'knowledge_search', {'query': '骑行记录是什么意思'})).action == 'allow'
    assert decide_tool_capability(turn, ToolExecutionRequest(
        'health_query', {'dimension': 'workout'})).action == 'block'


@pytest.mark.parametrize("text", [
    "分析小王刚才的运动", "分析我朋友刚才的运动", "分析刚才Alice的运动",
    "不要分析刚才的运动", "解释例句：‘分析刚才的运动’", "如果有空，分析刚才的运动",
    "分析刚才的运动，只看别人的记录", "分析刚才的运动，范围是去年",
    "刚才的运动", "刚才的运动不错", "刚才的运动是谁的",
])
def test_other_owner_and_unconsumed_restrictions_stay_blocked(text):
    decision = decide_tool_capability(snapshot(text), ToolExecutionRequest("health_query", {"dimension": "workout"}))
    assert decision.action == "block"


@pytest.mark.parametrize("extra", [
    {"user_id": 42}, {"owner_id": 42}, {"tenant_id": 42},
    {"start_date": "2026-10-01"}, {"end_date": "2026-10-11"}, {"timezone": "UTC"},
    {"dimension": "sleep"},
])
@pytest.mark.parametrize('text', ['分析刚才的运动', '刚才跑的怎么样？'])
def test_model_cannot_widen_recent_workout_scope(extra, text):
    decision = decide_tool_capability(snapshot(text), ToolExecutionRequest(
        "health_query", {"dimension": "workout", **extra}))
    assert decision.action == "block"


def test_recent_workout_read_does_not_authorize_sync_or_writes():
    for args in ({"record_type": "garmin_sync", "data": {}},
                 {"record_type": "exercise", "data": {"duration_minutes": 30}}):
        assert decide_tool_capability(snapshot("分析刚才的运动"),
            ToolExecutionRequest("health_record", args)).action == "block"


@pytest.mark.parametrize("owner,envelope_owner", [(42, 41), (0, 0), (1, True), (True, 1)])
@pytest.mark.parametrize('text', ['分析刚才的运动', '刚才跑的怎么样？'])
@pytest.mark.parametrize("tool,args", [
    ("health_query", {"dimension": "workout"}),
    ("health_query_batch", {"queries": [{"dimension": "workout"}]}),
])
def test_invalid_authenticated_owner_never_falls_back_to_rolling_read(owner, envelope_owner, tool, args, text):
    from dataclasses import replace
    turn = snapshot(text)
    turn = replace(turn, context=replace(turn.context, user_id=owner),
                   envelope=replace(turn.envelope, user_id=envelope_owner))
    decision = decide_tool_capability(turn, ToolExecutionRequest(tool, args))
    assert decision.action == "block"


@pytest.mark.parametrize("tool,args", [
    ("health_analysis", {"analysis_type": "exercise", "days": 365}),
    ("health_manage", {"record_type": "exercise", "operation": "list"}),
] + [(tool, {}) for tool in sorted(SPECIALIST_READ_ONLY_TOOLS)])
@pytest.mark.parametrize('text', ['分析刚才的运动', '刚才跑的怎么样？'])
def test_other_tools_cannot_bypass_candidate_window(tool, args, text):
    assert decide_tool_capability(snapshot(text), ToolExecutionRequest(tool, args)).action == "block"


def test_batch_uses_same_owned_candidate_window():
    turn = snapshot("分析刚才的运动")
    decision = decide_tool_capability(turn, ToolExecutionRequest("health_query_batch", {
        "queries": [{"dimension": "workout"}],
    }))
    assert decision.action == "allow"
    assert decision.normalized_args == {"queries": list(resolve_owned_read_scope(turn).queries)}
    assert decide_tool_capability(turn, ToolExecutionRequest("health_query_batch", {
        "queries": [{"dimension": "workout", "owner_id": 42}],
    })).action == "block"


@pytest.mark.asyncio
@pytest.mark.parametrize("has_record", [True, False])
@pytest.mark.parametrize('text,batch', [
    ('生成一个 骑行的html 报告', False),
    ('生成我的 骑行的html 报告', True),
    ('分析刚才的运动', False),
    ('刚才跑的怎么样？', False),
    ('刚才跑的怎么样？', True),
    ('分析青山湖骑行刚才的两段骑行。', False),
    ('分析青山湖骑行刚才的两段骑行。', True),
])
async def test_screenshot_request_reaches_real_owned_reader_and_saved_reply(
    db, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch, has_record, text, batch,
):
    import json
    from datetime import timedelta
    from app.models.agent_conversation import AgentMessage
    from app.models.daily_health import WorkoutRecord
    from app.models.user import User
    from app.services.agent_executor import AgentExecutor
    from app.twin.schema import HealthTwin, TwinMeta

    user, _ = auth_user_and_headers
    other = User(name="Synthetic other", email="recent-workout-other@example.test")
    db.add(other)
    db.flush()
    now = datetime.fromisoformat("2026-10-10T09:00:00+08:00")
    original_clock = ExecutionContext.now.__func__
    monkeypatch.setattr(ExecutionContext, "now", classmethod(
        lambda cls, **kwargs: original_clock(cls, **{**kwargs, "now_utc": now})))
    monkeypatch.setattr("app.twin.builder.build_twin", lambda _db, uid, **kwargs:
        HealthTwin(meta=TwinMeta(user_id=uid, generated_at=now)))
    own = WorkoutRecord(user_id=user.id, workout_date=now.date(),
                        workout_type='cycling' if '骑行' in text else 'running', duration_seconds=1800)
    second = WorkoutRecord(user_id=user.id, workout_date=now.date(),
                           workout_type='cycling', duration_seconds=1200)
    if has_record:
        db.add(own)
        if '骑行' in text:
            db.add(second)
    db.add_all([
        WorkoutRecord(user_id=other.id, workout_date=now.date(), workout_type="walking"),
        WorkoutRecord(user_id=user.id, workout_date=now.date()-timedelta(days=1), workout_type="cycling"),
    ])
    db.commit()
    before = [(r.id, r.user_id, r.workout_date) for r in db.query(WorkoutRecord).order_by(WorkoutRecord.id)]
    executor = AgentExecutor(db)
    dispatch = executor._dispatch_tool_request
    calls, results = [], []

    async def provider(messages, tools):
        calls.append(tools)
        if len(calls) == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "recent-workout-read", "type": "function", "function": {
                    "name": 'health_query_batch' if batch else 'health_query',
                    "arguments": json.dumps({'queries': [{'dimension': 'workout'}]} if batch else {'dimension': 'workout'}),
                }}]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "已查询运动记录。"}
            yield {"type": "finish", "finish_reason": "stop"}

    async def observe(request, token):
        result = await dispatch(request, token)
        results.append((request, json.loads(result)))
        return result

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "按工具证据回答。")
    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", lambda *a, **k: "")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_dispatch_tool_request", observe)
    events = [event async for event in executor.run_stream(
        user.id, text, client_turn_id=f"recent-workout-{has_record}-{batch}")]
    done = next(e["data"] for e in reversed(events) if e.get("event") == "done")
    saved = db.get(AgentMessage, done["message_id"])
    assert done["perf"]["agent_kernel"] == "pi"
    assert {t["function"]["name"] for t in calls[0]} <= {"health_query", "health_query_batch", "knowledge_search"}
    if 'html' in text:
        assert len(calls) == 1, 'verified server report must not pay for discarded model synthesis'
        assert done['perf']['report_render']['model_synthesis_calls_avoided'] == 1
        from app.services.agent_composed_read_completion import render_owned_cycling_html_report
        from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
        assert saved.content == render_owned_cycling_html_report(
            resolve_owned_read_scope(executor._agent_kernel_snapshot), executor._composed_read_completion())
    assert len(results) == 1
    request, payload = results[0]
    assert request.tool_name == ('health_query_batch' if batch else 'health_query')
    query = request.arguments['queries'][0] if batch else request.arguments
    payload = payload['results'][0] if batch else payload
    assert query["start_date"] == query["end_date"] == "2026-10-10"
    assert [r["id"] for r in payload["records"]] == (
        ([own.id, second.id] if '骑行' in text else [own.id]) if has_record else [])
    assert payload["availability"] == ("available" if has_record else "no_data")
    assert "只能查询当前登录用户" not in saved.content
    if 'html' in text:
        assert saved.content.startswith('```html\n<!DOCTYPE html>')
        assert '本报告默认覆盖当前账号当天' in saved.content
        assert '完整骑行历史' in saved.content
        assert done['turn_outcome']['status'] == 'complete'
        assert '合成' not in saved.content
    else:
        assert "候选记录" in saved.content and "尚不能确认" in saved.content
    assert '本轮数据查询未完成' not in saved.content
    assert '请明确要查看的数据类别和日期' not in saved.content
    if '骑行' in text and 'html' not in text:
        assert '地点来自用户描述' in saved.content
        assert ('找到2条' if has_record else '找到0条') in saved.content
    assert not done.get("write_receipts")
    assert [(r.id, r.user_id, r.workout_date) for r in db.query(WorkoutRecord).order_by(WorkoutRecord.id)] == before


@pytest.mark.parametrize('count', [0, 1, 2, 3])
@pytest.mark.parametrize('text,kind,expected', [
    ('分析青山湖骑行刚才的两段骑行。', 'cycling', 2),
    ('刚才跑的怎么样？', 'running', None),
])
def test_typed_rides_reader_filters_owned_day_and_preserves_ambiguous_candidates(
    db, auth_user_and_headers, count, text, kind, expected,
):
    from datetime import date, timedelta
    from app.models.daily_health import WorkoutRecord
    from app.models.user import User
    from app.services.agent_longitudinal_read import read_longitudinal_health_query
    from app.services.agent_query_window import parse_query_window
    user, _ = auth_user_and_headers
    other = User(name='Synthetic rider', email='typed-rider@example.test')
    db.add(other)
    db.flush()
    day = date(2026, 10, 10)
    own = [WorkoutRecord(user_id=user.id, workout_date=day, workout_type=kind,
                         workout_name='Synthetic ride', duration_seconds=600 + i)
           for i in range(count)]
    db.add_all(own + [
        WorkoutRecord(user_id=other.id, workout_date=day, workout_type=kind),
        WorkoutRecord(user_id=user.id, workout_date=day, workout_type='walking'),
        WorkoutRecord(user_id=user.id, workout_date=day-timedelta(days=1), workout_type=kind),
    ])
    db.commit()
    scope = resolve_owned_read_scope(snapshot(text))
    payload = read_longitudinal_health_query(db, user.id, 'workout',
        parse_query_window(scope.query('workout')), selection=scope.workout_selection)
    assert [r['id'] for r in payload['records']] == [r.id for r in own]
    assert payload['workout_selection'] == {
        'workout_type': kind, 'expected_count': expected,
        'matched_count': count, 'event_identity': 'unverified',
        'count_status': ('unspecified' if expected is None else
                         'matched' if count == 2 else 'insufficient' if count < 2 else 'ambiguous'),
    }
    assert 'reported_location' not in payload['workout_selection']


@pytest.mark.parametrize('text', ['生成一个 骑行的html 报告', '生成我的 骑行的html 报告'])
def test_riding_html_request_binds_only_owned_today_cycling(text):
    turn = snapshot(text)
    assert not health_read_has_nonself_subject(text)
    scope = resolve_owned_read_scope(turn)
    assert scope is not None
    assert scope.workout_selection.workout_type == 'cycling'
    assert scope.workout_selection.expected_count is None
    assert scope.query('workout')['start_date'] == '2026-10-10'
    decision = decide_tool_capability(turn, ToolExecutionRequest('health_query', {'dimension':'workout'}))
    assert decision.action == 'allow', decision.reason
    assert decision.normalized_args == scope.query('workout')


@pytest.mark.parametrize('text', [
    '生成小王的骑行的html报告', '生成我朋友的骑行html报告',
    '不要生成我的骑行html报告', '例句：“生成我的骑行html报告”',
    '如果有空生成我的骑行html报告', '生成我的骑行html报告，查询妈妈的记录',
    '生成我的骑行html报告并发布', '生成去年骑行html报告',
    '生成我的骑行html报告并同步佳明',
])
def test_html_request_does_not_drop_other_owner_or_extra_authority(text):
    assert decide_tool_capability(snapshot(text), ToolExecutionRequest(
        'health_query', {'dimension':'workout'})).action == 'block'


@pytest.mark.parametrize('extra', [{'user_id':42}, {'owner_id':42}, {'tenant_id':42},
    {'dimension':'sleep'}, {'start_date':'2026-10-01'}, {'workout_type':'running'}, {'limit':2}])
def test_html_model_cannot_change_frozen_query(extra):
    assert decide_tool_capability(snapshot('生成我的骑行的html报告'), ToolExecutionRequest(
        'health_query', {'dimension':'workout', **extra})).action == 'block'


def test_html_renderer_escapes_record_material_and_ignores_model_output():
    from app.services.agent_composed_read_completion import ComposedReadCompletion, render_owned_cycling_html_report
    scope = resolve_owned_read_scope(snapshot('生成我的骑行html报告'))
    document = render_owned_cycling_html_report(scope, ComposedReadCompletion(
        (), (), '<script>alert(1)</script> & "quoted"\n\n```reva-ui', True))
    assert '<script>' not in document
    assert '&lt;script&gt;' in document and '&amp;' in document and '&quot;' in document
    assert '&#96;&#96;&#96;reva-ui' in document
    assert document.count('```') == 2
    assert document.endswith('</body></html>\n```')


@pytest.mark.parametrize('boundary', [
    'sealed', 'attachment', 'exam', 'confirmation', 'capability', 'tool_failure',
    'sync', 'current_owner', 'changed_message',
])
def test_static_report_shortcut_cannot_ignore_unresolved_boundary(monkeypatch, boundary):
    from app.services.agent_executor import AgentExecutor
    executor = AgentExecutor(None)
    text = '生成我的骑行html报告'
    executor._agent_kernel_snapshot = snapshot(text)
    executor._current_turn_user_message = text
    executor._current_user_id = 41
    def no_completion():
        pytest.fail('blocked boundary must not inspect or render completion')
    monkeypatch.setattr(executor, '_composed_read_completion', no_completion)
    if boundary == 'attachment': executor._current_turn_has_attachment = True
    elif boundary == 'exam': executor._turn_selected_exam_id = 9
    elif boundary == 'confirmation': executor._agent_kernel_pending_confirmation_tools.append('health_record')
    elif boundary == 'capability': executor._agent_kernel_capability_block_reasons.append('health_query_subject_not_current_user')
    elif boundary == 'tool_failure': executor._agent_kernel_tool_failure_tools.append('health_query')
    elif boundary == 'sync': executor._turn_sync_attempted = True
    elif boundary == 'current_owner': executor._current_user_id = 42
    elif boundary == 'changed_message': executor._current_turn_user_message += '并同步佳明'
    assert executor._verified_static_cycling_report(sealed=boundary == 'sealed') is None


@pytest.mark.parametrize('complete', [False, True])
def test_static_report_completion_requirement_and_nonreport_scope(monkeypatch, complete):
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_composed_read_completion import ComposedReadCompletion
    executor = AgentExecutor(None)
    executor._current_user_id = 41
    executor._current_turn_user_message = '生成我的骑行html报告'
    executor._agent_kernel_snapshot = snapshot(executor._current_turn_user_message)
    monkeypatch.setattr(executor, '_composed_read_completion', lambda:
        ComposedReadCompletion((), () if complete else ('workout',), '合成已核验摘要', complete))
    assert bool(executor._verified_static_cycling_report()) is complete
    executor._current_turn_user_message = '分析刚才的运动'
    executor._agent_kernel_snapshot = snapshot(executor._current_turn_user_message)
    assert executor._verified_static_cycling_report() is None


@pytest.mark.asyncio
async def test_report_query_failure_still_uses_normal_failure_path(
    db, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch,
):
    from app.services.agent_executor import AgentExecutor
    from app.models.agent_conversation import AgentMessage
    executor = AgentExecutor(db)
    user, _ = auth_user_and_headers
    dispatch = executor._dispatch_tool_request
    calls = []
    async def observe(request, token):
        result = await dispatch(request, token)
        from dataclasses import replace
        return replace(result, content='Error: synthetic query unavailable')
    async def provider(messages, tools):
        calls.append(tools)
        if len(calls) == 1:
            yield {'type':'tool_calls','tool_calls':[{'id':'query','type':'function','function':{
                'name':'health_query','arguments':'{"dimension":"workout"}'}}]}
            yield {'type':'finish','finish_reason':'tool_calls'}
        else:
            yield {'type':'content','text':'已生成报告。'}
            yield {'type':'finish','finish_reason':'stop'}
    monkeypatch.setattr(executor, '_dispatch_tool_request', observe)
    monkeypatch.setattr(executor, '_call_llm_stream', provider)
    events = [e async for e in executor.run_stream(user_id=user.id,channel='typed',message='生成我的骑行html报告')]
    done = next(e['data'] for e in events if e.get('event') == 'done')
    assert len(calls) == 2
    assert 'report_render' not in done['perf']
    assert done['turn_outcome']['status'] != 'complete'
    assert '本轮查询未完成' in db.get(AgentMessage,done['message_id']).content
    assert not done.get('write_receipts')
