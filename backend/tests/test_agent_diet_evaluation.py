"""Single-day diet evaluation uses verified reads without adding health domains."""
import json

import pytest
from tests.test_query_reliability_outcomes import _run_scripted, _calendar_payload


@pytest.fixture(autouse=True)
def isolated(isolated_agent_protocol_transport):
    """Exercise Pi and the real gateway, with no external provider or cache."""


def dietary_rows(request):
    assert request.arguments["dimension"] == "diet"
    return _calendar_payload(request, records=[
        {"record_date": request.arguments["start_date"], "meal_type": meal,
         "food_name": food, "calories": calories}
        for meal, food, calories in [
            ("breakfast", "合成早餐燕麦", 300), ("breakfast", "合成早餐燕麦", 300),
            ("dinner", "合成晚餐番茄蛋饭", 420),
        ]
    ])


@pytest.mark.asyncio
@pytest.mark.parametrize("panel", [False, True])
@pytest.mark.parametrize("query", ["今天我吃的怎么样?", "今天饮食如何", "今日我吃的怎样？", "昨天的餐食怎样", "今天我吃了什么，给我建议"])
async def test_diet_evaluation_injects_verified_facts_and_keeps_single_domain(db, auth_user_and_headers, monkeypatch, query, panel):
    user, _ = auth_user_and_headers
    executor, done, saved, streamed, dispatched = await _run_scripted(
        db, user, monkeypatch, query=query, first_tool="health_query", first_args={"dimension": "diet"},
        dispatch=dietary_rows, reply="建议：下次记录食物的大致份量，以便核对营养信息。",
        turn_id="diet-evaluation", extra_context=json.dumps({"multi_model": panel}), required_context_text="已记录热量合计1020千卡",
    )
    assert executor._turn_daily_read_plan.dimensions == ("diet",)
    assert executor._turn_daily_read_plan.is_summary is False
    assert {r.arguments["dimension"] for r in dispatched} == {"diet"}
    assert done["turn_outcome"]["status"] == "complete"
    for text in (saved.content, streamed):
        assert "已记录热量合计1020千卡" in text
        assert "仅覆盖饮食记录" in text and "睡眠" not in text
        assert "下次记录食物的大致份量" in text
    goals = done["turn_outcome"]["goals"]
    assert [g["goal_id"] for g in goals if g["kind"] == "query"] == ["diet"]
    assert any(g["kind"] == "answer" and g["status"] == "verified" for g in goals)


# The synthetic live candidate reinterpreted duplicate-looking rows, missing
# nutrient fields and a meal label as observations. None is a verified fact.
LIVE_CANDIDATE = """## 今天查到的饮食事实
系统里今天共3条记录，合计1020 kcal。
两条早餐完全一样，很可能是重复录入。如果确实是重复，今天实际摄入是720 kcal。
现在是14:04，却已经有一条晚餐，更像是午餐被标成了晚餐。
## 从14:04往后可执行的建议
到下午两点只有720–1020 kcal，且蛋白数据缺失，缺口大概率在蛋白侧。
要删掉重复那条或改餐次，跟我说一声我直接改。
"""


@pytest.mark.asyncio
@pytest.mark.parametrize("panel", [False, True])
@pytest.mark.parametrize("reply,finish", [
    (LIVE_CANDIDATE, "stop"),
    ("建议：今天只吃了720千卡，摄入不足。", "stop"),
    ("### 建议", "stop"),
    ("建议：我会先查询今天的饮食记录，然后给出建议。", "stop"),
    ("建议：暂无建议。", "stop"),
    ("建议：我会先分析。", "stop"),
    ("建议：我会先查询，然后给出建议。", "stop"),
    ("建议：蛋白数据缺失，说明今天缺口大概率在蛋白侧。建议多吃鸡蛋。", "stop"),
    ("建议：两条早餐名称和热量相同，说明是重复录入，建议删除其中一条。", "stop"),
    ("建议：餐次标签比当前时间晚，午餐被标成了晚餐，建议更正。", "stop"),
    ("建议：缺少蛋白质的记录，说明你的蛋白质摄入不足。", "stop"),
    ("建议：是否存在重复录入需要核对，但这些记录是重复录入。", "stop"),
    ("建议：核对是否完整后确认这是重复录入。", "stop"),
    ("本轮生成失败，请重试。", "error"),
    ("我会先查询今天的饮食记录，然后给出建议。", "stop"),
])
async def test_failed_evaluation_keeps_successful_read_in_stream_and_history(db, auth_user_and_headers, monkeypatch, reply, finish, panel):
    user, _ = auth_user_and_headers
    _, done, saved, streamed, dispatched = await _run_scripted(
        db, user, monkeypatch, query="今天我吃的怎么样?", first_tool="health_query", first_args={"dimension": "diet"},
        dispatch=dietary_rows, reply=reply, turn_id="diet-evaluation-failure", answer_finish_reason=finish, extra_context=json.dumps({"multi_model": panel}),
    )
    assert len(dispatched) == 1
    goals = done["turn_outcome"]["goals"]
    assert any(g["goal_id"] == "diet" and g["status"] == "verified" for g in goals)
    assert any(g["kind"] == "answer" and g["status"] == "failed" for g in goals)
    assert done["turn_outcome"]["status"] == "partial"
    assert done["completion_status"] == "error"
    if finish == "error": assert done["generation_status"] == "error"
    for text in (streamed, saved.content):
        assert reply not in text
        assert "已记录热量合计1020千卡" in text
        assert "建议" in text and "睡眠" not in text
        for false_claim in ("720", "缺口大概率在蛋白侧", "午餐被标成了晚餐", "没有完成数据查询", "查询未执行"):
            assert false_claim not in text


@pytest.mark.asyncio
async def test_plain_diet_query_retains_existing_answer_contract(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    _, done, saved, _, _ = await _run_scripted(
        db, user, monkeypatch, query="今天我吃了什么", first_tool="health_query", first_args={"dimension": "diet"},
        dispatch=dietary_rows, reply="查询到合成早餐燕麦和合成晚餐番茄蛋饭。", turn_id="plain-diet-query",
    )
    assert done["turn_outcome"]["status"] == "complete"
    assert not any(g["kind"] == "answer" for g in done["turn_outcome"]["goals"])
    assert "本次总结" not in saved.content and "仅覆盖" not in saved.content


@pytest.mark.parametrize("query,evaluation", [
    ("今日我吃的怎样？", True), ("昨天的餐食怎样", True),
    ("今天饮食如何", True), ("今天我吃了什么", False),
    ("今天我吃过哪些食物", False), ("今天我吃了什么，给我建议", True),
])
def test_existing_daily_question_grammar_separates_evaluation_from_recall(query, evaluation):
    from datetime import datetime
    from app.services.agent_kernel.daily_read_plan import resolve_daily_read_plan
    plan = resolve_daily_read_plan(query, datetime.fromisoformat("2026-09-13T14:04:00+08:00"))
    assert plan is not None and plan.dimensions == ("diet",) and not plan.is_summary
    assert plan.asks_advice is evaluation


@pytest.mark.asyncio
@pytest.mark.parametrize("unverified_facts", [
    "如果两条早餐确实重复，今天实际摄入是720千卡。",
    "蛋白数据缺失，说明今天缺口大概率在蛋白侧。",
    "现在14:04，却已经有晚餐，更像是午餐被标成了晚餐。",
])
async def test_model_observation_segment_is_replaced_by_verified_rows(db, auth_user_and_headers, monkeypatch, unverified_facts):
    user, _ = auth_user_and_headers
    advice = "建议：可以先核对记录和实际用餐情况是否一致，补全缺失的份量信息。"
    _, done, saved, streamed, _ = await _run_scripted(
        db, user, monkeypatch, query="今天我吃的怎么样?", first_tool="health_query", first_args={"dimension": "diet"},
        dispatch=dietary_rows, reply=unverified_facts + "\n" + advice, turn_id="diet-fact-projection",
    )
    assert done["turn_outcome"]["status"] == "complete"
    for text in (saved.content, streamed):
        assert "已记录热量合计1020千卡" in text
        assert unverified_facts not in text
        assert advice in text


@pytest.mark.asyncio
async def test_explained_evaluation_limit_is_a_substantive_answer(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    reply = "建议：当前记录缺少份量和营养字段，暂不足以评价营养是否均衡；缺少字段不代表实际摄入不足。"
    _, done, saved, _, _ = await _run_scripted(
        db, user, monkeypatch, query="今天我吃的怎么样?", first_tool="health_query", first_args={"dimension": "diet"},
        dispatch=dietary_rows, reply=reply, turn_id="diet-evaluation-limits",
    )
    assert done["turn_outcome"]["status"] == "complete"
    assert reply in saved.content


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", [
    "建议：目前缺少蛋白质的记录，请补充食物份量和营养信息。",
    "建议：是否存在重复录入需要先核对，不能直接删除记录。",
])
async def test_missing_field_noun_and_unresolved_record_question_are_retained(db, auth_user_and_headers, monkeypatch, reply):
    user, _ = auth_user_and_headers
    _, done, saved, streamed, dispatched = await _run_scripted(
        db, user, monkeypatch, query="今天我吃的怎么样?", first_tool="health_query", first_args={"dimension": "diet"},
        dispatch=dietary_rows, reply=reply, turn_id="diet-local-uncertainty",
    )
    assert len(dispatched) == 1 and dispatched[0].arguments["dimension"] == "diet"
    assert done["turn_outcome"]["status"] == "complete"
    assert all(goal["status"] == "verified" for goal in done["turn_outcome"]["goals"])
    for text in (saved.content, streamed):
        assert "已记录热量合计1020千卡" in text and "睡眠" not in text
        assert reply in text
