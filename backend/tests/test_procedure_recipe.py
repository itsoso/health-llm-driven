"""程序性记忆/配方(Harness 自由度升级 Slice 3)测试。

核心不变量(违反 = 返工):
1. 配方 = 确定性重放的工具序列 —— 重放零 LLM,步骤顺序与 args_template
   确定性填充({{today}} → 当天)。
2. **每步确认策略沿用该 kind 既有 confirm tier** —— 对抗测试:配方里塞
   never_auto kind(medication,且 args_template 被恶意灌入 confirmed=true)
   重放仍返回 [NEEDS_CONFIRMATION] 且**绝不静默写库**。
3. 触发短语精确匹配(strip 后等值),近似短语不命中 —— 控误触发。
4. 跨用户隔离:匹配/列表/删除/save-from-conversation 都只见自己的数据。
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.procedure_recipe import ProcedureRecipe
from app.services import procedure_recipe_service as recipe_svc
from app.services.agent_executor import AgentExecutor
from tests.conftest import create_authenticated_user

BEIJING_TZ = timezone(timedelta(hours=8))


def _today() -> str:
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")


def _insert_recipe(db, user_id, *, name="早餐套餐", phrases=None, steps=None):
    """直插 DB(绕过 create_recipe 校验)— 专给对抗测试灌"毒化"步骤用。"""
    recipe = ProcedureRecipe(
        user_id=user_id,
        name=name,
        trigger_phrases=phrases or ["早餐套餐打卡"],
        steps=steps or [],
        use_count=0,
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


async def _run(executor, user_id, message, channel=None):
    return [
        event
        async for event in executor.run_stream(
            user_id=user_id,
            message=message,
            user_auth_token="test-token",
            channel=channel,
        )
    ]


def _mock_llm_never_called(executor, monkeypatch):
    """配方命中应先于 LLM;若走到 LLM = 匹配层坏了,fail-loud。"""

    async def _boom(*args, **kwargs):
        raise AssertionError("recipe turn must not reach the LLM")
        yield  # pragma: no cover — 使其成为 async generator

    monkeypatch.setattr(executor, "_call_llm_stream", _boom)


def _capture_api(executor, monkeypatch, response='{"id": 11, "message": "已记录"}'):
    """把所有出站 HTTP 写捕获到列表,替代真实 API。"""
    calls = []

    async def fake_post(url, headers, data):
        calls.append({"method": "POST", "url": url, "data": data})
        return response

    async def fake_post_json(url, headers, data):
        calls.append({"method": "POST_JSON", "url": url, "data": data})
        return {"id": 11}, None

    async def fake_get_json(url, headers):
        calls.append({"method": "GET_JSON", "url": url})
        return [], None

    monkeypatch.setattr(executor, "_api_post", fake_post)
    monkeypatch.setattr(executor, "_api_post_json", fake_post_json)
    monkeypatch.setattr(executor, "_api_get_json", fake_get_json)
    return calls


# ─────────────────────────── 模板与 sanitize ───────────────────────────

def test_sanitize_strips_confirm_flags_top_level_and_data():
    args = {
        "record_type": "medication",
        "confirmed": True,
        "confirm": True,
        "_fast_record_requires_confirmation": True,
        "data": {"name": "华法林", "confirmed": True, "confirm": True},
    }
    cleaned = recipe_svc.sanitize_step_args(args)
    assert "confirmed" not in cleaned and "confirm" not in cleaned
    assert "_fast_record_requires_confirmation" not in cleaned
    assert "confirmed" not in cleaned["data"] and "confirm" not in cleaned["data"]
    # 原 dict 不被 mutate(深拷贝)
    assert args["confirmed"] is True and args["data"]["confirmed"] is True


def test_template_and_fill_today_roundtrip():
    today = _today()
    args = {
        "record_type": "diet",
        "data": {"record_date": today, "start_date": "2020-01-01", "food_items": "鸡蛋"},
    }
    templated = recipe_svc.template_step_args(args)
    assert templated["data"]["record_date"] == recipe_svc.TODAY_PLACEHOLDER
    # 非当天日期与普通字段原样保留 —— 模板化是确定性收窄,不是自由改写
    assert templated["data"]["start_date"] == "2020-01-01"
    assert templated["data"]["food_items"] == "鸡蛋"

    filled = recipe_svc.fill_step_args(templated)
    assert filled["data"]["record_date"] == today
    assert filled["data"]["start_date"] == "2020-01-01"


def test_fill_step_args_strips_poisoned_confirmed_flag():
    """重放侧防御纵深:即便库里被灌了 confirmed=true,填模板时也剥掉。"""
    filled = recipe_svc.fill_step_args({
        "record_type": "medication",
        "confirmed": True,
        "data": {"name": "华法林", "confirmed": True},
    })
    assert "confirmed" not in filled
    assert "confirmed" not in filled["data"]


def test_validate_steps_rejects_non_allowlisted_tools_and_bad_shapes():
    with pytest.raises(ValueError, match="不允许入配方"):
        recipe_svc.validate_steps([{"tool": "health_manage", "args_template": {"operation": "delete"}}])
    with pytest.raises(ValueError, match="不允许入配方"):
        recipe_svc.validate_steps([{"tool": "intervention_cycle", "args_template": {"action": "start"}}])
    with pytest.raises(ValueError, match="至少需要一个步骤"):
        recipe_svc.validate_steps([])
    with pytest.raises(ValueError, match="缺少 args_template"):
        recipe_svc.validate_steps([{"tool": "health_record"}])
    with pytest.raises(ValueError, match="最多"):
        recipe_svc.validate_steps([
            {"tool": "health_record", "args_template": {"record_type": "water", "data": {"amount": 100}}}
        ] * (recipe_svc.MAX_STEPS + 1))


# ─────────────────────────── 触发匹配(精确) ───────────────────────────

def test_match_trigger_exact_only_no_fuzzy(db):
    user, _ = create_authenticated_user(db)
    recipe = recipe_svc.create_recipe(
        db, user.id,
        name="早餐套餐",
        trigger_phrases=["早餐套餐打卡"],
        steps=[{"tool": "health_record", "args_template": {"record_type": "water", "data": {"amount": 300}}}],
    )

    assert recipe_svc.match_trigger(db, user.id, "早餐套餐打卡").id == recipe.id
    assert recipe_svc.match_trigger(db, user.id, "  早餐套餐打卡  ").id == recipe.id
    # 近似短语一律不命中(前缀/超集/子串/换字)
    assert recipe_svc.match_trigger(db, user.id, "早餐套餐打卡一下") is None
    assert recipe_svc.match_trigger(db, user.id, "早餐套餐") is None
    assert recipe_svc.match_trigger(db, user.id, "帮我早餐套餐打卡") is None
    assert recipe_svc.match_trigger(db, user.id, "午餐套餐打卡") is None
    assert recipe_svc.match_trigger(db, user.id, "") is None


def test_match_trigger_cross_user_isolation(db):
    user_a, _ = create_authenticated_user(db)
    user_b, _ = create_authenticated_user(db)
    recipe_svc.create_recipe(
        db, user_a.id,
        name="A 的配方",
        trigger_phrases=["晚间打卡"],
        steps=[{"tool": "health_record", "args_template": {"record_type": "water", "data": {"amount": 200}}}],
    )
    assert recipe_svc.match_trigger(db, user_a.id, "晚间打卡") is not None
    assert recipe_svc.match_trigger(db, user_b.id, "晚间打卡") is None


def test_trigger_phrase_guards(db):
    user, _ = create_authenticated_user(db)
    step = [{"tool": "health_record", "args_template": {"record_type": "water", "data": {"amount": 100}}}]
    # 单字短语拒绝(误触发风险)
    with pytest.raises(ValueError, match="太短"):
        recipe_svc.create_recipe(db, user.id, name="X", trigger_phrases=["好"], steps=step)
    # 同用户短语冲突拒绝(命中歧义)
    recipe_svc.create_recipe(db, user.id, name="一号", trigger_phrases=["晨间打卡"], steps=step)
    with pytest.raises(ValueError, match="已被配方"):
        recipe_svc.create_recipe(db, user.id, name="二号", trigger_phrases=["晨间打卡"], steps=step)


def test_recipe_count_cap_fail_loud(db):
    """安全评审必改:per-user 配方数量上限 — 超限 fail-loud 拒绝(防表膨胀 + 每消息匹配开销无界)。"""
    user, _ = create_authenticated_user(db)
    step = [{"tool": "health_record", "args_template": {"record_type": "water", "data": {"amount": 100}}}]
    for i in range(recipe_svc.MAX_RECIPES_PER_USER):
        recipe_svc.create_recipe(
            db, user.id, name=f"配方{i}", trigger_phrases=[f"触发短语{i:02d}"], steps=step,
        )
    with pytest.raises(ValueError, match="上限"):
        recipe_svc.create_recipe(
            db, user.id, name="超限", trigger_phrases=["超限短语"], steps=step,
        )
    # 隔离:另一个用户不受影响
    other, _ = create_authenticated_user(db)
    recipe_svc.create_recipe(db, other.id, name="别人", trigger_phrases=["别人的短语"], steps=step)


def test_validate_steps_rejects_never_auto_kind_at_save(db):
    """安全评审硬化:never_auto kind(用药等)存入时即拒 —— 重放永远要求确认=纯死重量,
    且避免药名/剂量多写进一处明文 JSONB。"""
    user, _ = create_authenticated_user(db)
    med_step = [{
        "tool": "health_record",
        "args_template": {"record_type": "medication", "data": {"name": "替普瑞酮", "dose": "50mg"}},
    }]
    with pytest.raises(ValueError, match="人工确认"):
        recipe_svc.create_recipe(
            db, user.id, name="毒配方", trigger_phrases=["吃药打卡"], steps=med_step,
        )
    # kind 藏进 data 层同样拒(与确认门同一 kind 推导)
    nested = [{
        "tool": "health_record",
        "args_template": {"data": {"record_type": "dose", "name": "华法林"}},
    }]
    with pytest.raises(ValueError, match="人工确认"):
        recipe_svc.create_recipe(
            db, user.id, name="毒配方2", trigger_phrases=["换个说法"], steps=nested,
        )


@pytest.mark.parametrize("record_type", ["reminder", "goal", "garmin_sync", "remember"])
def test_validate_steps_rejects_persistent_or_external_record_types(db, record_type):
    """配方不得固化提醒、目标、同步或个人档案等跨本轮副作用。"""
    user, _ = create_authenticated_user(db)
    with pytest.raises(ValueError, match="不支持存入配方"):
        recipe_svc.create_recipe(
            db,
            user.id,
            name=f"{record_type} 配方",
            trigger_phrases=[f"执行 {record_type} 配方"],
            steps=[{
                "tool": "health_record",
                "args_template": {"record_type": record_type, "data": {"title": "不应执行"}},
            }],
        )


# ─────────────────────────── 确定性重放 ───────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "needs_confirmation"),
    [
        ("cancelled", False),
        ("not_found", False),
        ("uncertain", False),
        ("needs_confirmation", True),
    ],
)
async def test_replay_uses_shared_structured_write_outcome_classifier(
    status,
    needs_confirmation,
):
    class FakeExecutor:
        async def _execute_recipe_step(self, *_args, **_kwargs):
            return json.dumps({"status": status})

    recipe = SimpleNamespace(steps=[{
        "tool": "health_record",
        "args_template": {"record_type": "water", "data": {"amount": 250}},
    }])

    outcomes = [
        outcome
        async for outcome in recipe_svc.replay(
            recipe,
            FakeExecutor(),
            user_auth_token=None,
            channel="typed",
        )
    ]

    assert outcomes[-1]["error"] is True
    assert outcomes[-1]["needs_confirmation"] is needs_confirmation

@pytest.mark.asyncio
async def test_replay_never_auto_medication_still_requires_confirmation(
    db, auth_user_and_headers, monkeypatch
):
    """对抗测试(不变量 2):配方里塞 never_auto kind(medication),且
    args_template 被恶意灌入 confirmed=true —— 重放仍要求确认,绝不静默写。"""
    user, _ = auth_user_and_headers
    _insert_recipe(
        db, user.id,
        phrases=["早餐套餐打卡"],
        steps=[
            {"tool": "health_record",
             "args_template": {"record_type": "water", "data": {"amount": 300}}},
            {"tool": "health_record",
             "args_template": {
                 "record_type": "medication",
                 "confirmed": True,  # 毒化:试图继承一次性确认
                 "data": {"name": "华法林", "dosage": "2.5mg", "confirmed": True},
             }},
        ],
    )
    executor = AgentExecutor(db)
    _mock_llm_never_called(executor, monkeypatch)
    calls = _capture_api(executor, monkeypatch)

    events = await _run(executor, user.id, "早餐套餐打卡", channel="typed")

    # medication 一步:结果是 NEEDS_CONFIRMATION,没有任何用药 API 调用
    tool_results = [e["data"] for e in events if e.get("event") == "tool_result"]
    assert len(tool_results) == 2
    med_result = tool_results[1]
    assert med_result["result"].startswith("[NEEDS_CONFIRMATION]")
    assert med_result["write_completed"] is False
    assert all("medication" not in c["url"] for c in calls)
    # water(AUTO 档)正常写入
    assert any("/water/records/quick" in c["url"] for c in calls)
    assert tool_results[0]["write_completed"] is True

    # 回复如实告知未写入,不冒充成功
    done = next(e["data"] for e in events if e.get("event") == "done")
    assert done["mode"] == "recipe_replay"
    assert done["completion_status"] == "complete"
    final_text = "".join(
        e["data"]["content"] for e in events if e.get("event") == "token"
    )
    assert "需要你确认" in final_text
    assert "用药" in final_text


@pytest.mark.asyncio
async def test_replay_steps_in_order_and_fills_today_placeholder(
    db, auth_user_and_headers, monkeypatch
):
    """不变量 1:步骤按序确定性重放;{{today}} 填充为当天,无 LLM 参与。"""
    user, _ = auth_user_and_headers
    _insert_recipe(
        db, user.id,
        phrases=["晨间套餐"],
        steps=[
            {"tool": "health_record",
             "args_template": {
                 "record_type": "diet",
                 "data": {"food_items": "鸡蛋, 燕麦", "meal_type": "breakfast",
                          "record_date": recipe_svc.TODAY_PLACEHOLDER},
             }},
            {"tool": "health_record",
             "args_template": {"record_type": "water", "data": {"amount": 250}}},
        ],
    )
    executor = AgentExecutor(db)
    _mock_llm_never_called(executor, monkeypatch)
    calls = _capture_api(executor, monkeypatch)

    events = await _run(executor, user.id, "晨间套餐", channel="typed")

    posts = [c for c in calls if c["method"] == "POST"]
    assert len(posts) == 2
    assert "/diet/records" in posts[0]["url"]
    assert "/water/records/quick" in posts[1]["url"]
    assert posts[0]["data"]["record_date"] == _today()
    assert posts[0]["data"]["food_items"] == "鸡蛋, 燕麦"

    done = next(e["data"] for e in events if e.get("event") == "done")
    assert done["tools_used"] == ["health_record"]
    assert len(done["write_receipts"]) == 2

    # use_count 确定性 +1
    recipe = db.query(ProcedureRecipe).filter(ProcedureRecipe.user_id == user.id).one()
    assert recipe.use_count == 1


@pytest.mark.asyncio
async def test_replay_typed_only_kind_respects_channel(
    db, auth_user_and_headers, monkeypatch
):
    """typed_only 档(symptom):typed 通道放行;未声明通道 fail-closed 要求确认
    —— 与直接调用完全一致的 channel 语义。"""
    user, _ = auth_user_and_headers
    _insert_recipe(
        db, user.id,
        phrases=["记录眼痒"],
        steps=[{
            "tool": "health_record",
            "args_template": {
                "record_type": "symptom",
                "data": {"body_part": "eye", "description": "眼睛痒"},
            },
        }],
    )

    # 未声明通道(旧客户端/语音)→ fail-closed 保留确认,不写
    executor = AgentExecutor(db)
    _mock_llm_never_called(executor, monkeypatch)
    calls = _capture_api(executor, monkeypatch)
    events = await _run(executor, user.id, "记录眼痒", channel=None)
    tool_results = [e["data"] for e in events if e.get("event") == "tool_result"]
    assert tool_results[0]["result"].startswith("[NEEDS_CONFIRMATION]")
    assert calls == []

    # typed 通道 → 免确认写入(与快路由直接调用同一分级)
    executor2 = AgentExecutor(db)
    _mock_llm_never_called(executor2, monkeypatch)
    calls2 = _capture_api(executor2, monkeypatch)
    await _run(executor2, user.id, "记录眼痒", channel="typed")
    assert any("/symptoms" in c["url"] for c in calls2)


@pytest.mark.asyncio
async def test_replay_rejects_non_allowlisted_tool_in_db(
    db, auth_user_and_headers, monkeypatch
):
    """库里被手改出白名单外工具 → fail-loud 拒执行该步,绝不静默跳过或执行。"""
    user, _ = auth_user_and_headers
    _insert_recipe(
        db, user.id,
        phrases=["删掉记录"],
        steps=[{"tool": "health_manage",
                "args_template": {"operation": "delete", "record_type": "diet", "record_id": 1}}],
    )
    executor = AgentExecutor(db)
    _mock_llm_never_called(executor, monkeypatch)
    calls = _capture_api(executor, monkeypatch)

    events = await _run(executor, user.id, "删掉记录", channel="typed")

    tool_results = [e["data"] for e in events if e.get("event") == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0]["result"].startswith("Error")
    assert calls == []


@pytest.mark.asyncio
async def test_replay_rejects_persistent_record_type_in_poisoned_db(
    db, auth_user_and_headers, monkeypatch
):
    """历史/手改数据库中的提醒步骤也不得借精确触发创建长期副作用。"""
    user, _ = auth_user_and_headers
    _insert_recipe(
        db,
        user.id,
        phrases=["执行晚间提醒"],
        steps=[{
            "tool": "health_record",
            "args_template": {
                "record_type": "reminder",
                "data": {"title": "喝水", "remind_at": "2026-07-18T20:00:00+08:00"},
            },
        }],
    )
    executor = AgentExecutor(db)
    _mock_llm_never_called(executor, monkeypatch)
    calls = _capture_api(executor, monkeypatch)

    events = await _run(executor, user.id, "执行晚间提醒", channel="typed")

    tool_results = [e["data"] for e in events if e.get("event") == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0]["result"].startswith("Error")
    assert calls == []


@pytest.mark.asyncio
async def test_recipe_execution_source_is_not_shared_with_parallel_tool_execution(db, monkeypatch):
    """配方的内部来源只绑定该调用，不能跨 await 赋权给普通工具调用。"""
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "晨间套餐"
    executor._turn_channel = "typed"
    recipe_started = asyncio.Event()
    allow_recipe_to_finish = asyncio.Event()
    observed_sources = []

    async def fake_execute_tool_impl(tool_name, args_raw, user_token, *, source=None):
        observed_sources.append(source)
        if source == "procedure_recipe_replay":
            recipe_started.set()
            await allow_recipe_to_finish.wait()
        return "{}"

    monkeypatch.setattr(executor, "_execute_tool_impl", fake_execute_tool_impl)

    recipe_task = asyncio.create_task(
        executor._execute_recipe_step("health_record", {"record_type": "water"}, "test-token")
    )
    await asyncio.wait_for(recipe_started.wait(), timeout=0.2)
    await executor._execute_tool("health_record", {"record_type": "water"}, "test-token")
    allow_recipe_to_finish.set()
    await recipe_task

    assert observed_sources == ["procedure_recipe_replay", "structured_or_recovered"]


# ─────────────────────────── 「存为配方」入口 ───────────────────────────

def _wire_llm_turn(executor, monkeypatch, tool_calls_rounds):
    """让 run_stream 走到 round loop:第 1 轮吐 tool_calls,第 2 轮吐正文。"""
    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr(
        "app.services.agent_executor.get_health_tools",
        lambda subset=None: [{
            "type": "function",
            "function": {"name": "health_record", "description": "x",
                         "parameters": {"type": "object", "properties": {}}},
        }],
    )
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")
    state = {"round": 0}

    async def fake_stream(messages, round_tools):
        state["round"] += 1
        if state["round"] == 1 and round_tools:
            yield {"type": "tool_calls", "tool_calls": tool_calls_rounds}
            yield {"type": "finish", "finish_reason": "tool_calls"}
            return
        yield {"type": "content", "text": "都记好了。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)

    async def fake_execute_tool(name, args, token):
        return '{"id": 21, "message": "已记录"}'

    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)


@pytest.mark.asyncio
async def test_turn_with_two_writes_offers_save_recipe_descriptor(
    db, auth_user_and_headers, monkeypatch
):
    """一轮完成 ≥2 个写类工具 → done.cards 出现 save_recipe 描述符;候选步骤
    持久化到 message.meta.recipe_candidate 且剥掉 confirmed(不继承一次性确认)。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    today = _today()
    _wire_llm_turn(executor, monkeypatch, [
        {"id": "t1", "type": "function", "function": {
            "name": "health_record",
            "arguments": json.dumps({
                "record_type": "diet",
                "data": {"food_items": "鸡蛋", "meal_type": "breakfast",
                         "record_date": today},
            }),
        }},
        {"id": "t2", "type": "function", "function": {
            "name": "health_record",
            "arguments": json.dumps({
                "record_type": "water",
                "confirmed": True,  # 用户在本轮确认过 —— 不能进模板
                "data": {"amount": 300, "confirmed": True},
            }),
        }},
    ])

    events = await _run(executor, user.id, "记录早餐鸡蛋和喝水300ml")

    done = next(e["data"] for e in events if e.get("event") == "done")
    save_cards = [c for c in done["cards"] if c.get("type") == "save_recipe"]
    assert len(save_cards) == 1
    card = save_cards[0]
    assert card["data"]["step_count"] == 2
    assert card["data"]["conversation_id"] == done["conversation_id"]
    assert len(card["data"]["steps_preview"]) == 2

    from app.models.agent_conversation import AgentMessage
    ai_msg = db.query(AgentMessage).get(done["message_id"])
    candidate = ai_msg.meta["recipe_candidate"]
    assert candidate["step_count"] == 2
    steps = candidate["steps"]
    assert [s["tool"] for s in steps] == ["health_record", "health_record"]
    # confirmed 双层剥除 + 当天日期已模板化
    water_args = steps[1]["args_template"]
    assert "confirmed" not in water_args
    assert "confirmed" not in water_args["data"]
    diet_args = steps[0]["args_template"]
    assert diet_args["data"]["record_date"] == recipe_svc.TODAY_PLACEHOLDER


@pytest.mark.asyncio
async def test_turn_with_single_write_offers_no_save_recipe(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_llm_turn(executor, monkeypatch, [
        {"id": "t1", "type": "function", "function": {
            "name": "health_record",
            "arguments": json.dumps({"record_type": "water", "confirmed": True,
                                     "data": {"amount": 300, "confirmed": True}}),
        }},
    ])

    events = await _run(executor, user.id, "记录喝水300ml")

    done = next(e["data"] for e in events if e.get("event") == "done")
    assert all(c.get("type") != "save_recipe" for c in done["cards"])
    from app.models.agent_conversation import AgentMessage
    ai_msg = db.query(AgentMessage).get(done["message_id"])
    assert "recipe_candidate" not in (ai_msg.meta or {})


# ─────────────────────────── API ───────────────────────────

def _step_water(amount=300):
    return {"tool": "health_record",
            "args_template": {"record_type": "water", "data": {"amount": amount}}}


def test_recipes_crud_api(client, db):
    user, token = create_authenticated_user(db)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post("/api/v1/agent/recipes", headers=headers, json={
        "name": "晨间打卡",
        "trigger_phrases": ["晨间打卡走一遍"],
        "steps": [_step_water()],
    })
    assert created.status_code == 200, created.text
    recipe_id = created.json()["id"]
    assert created.json()["trigger_phrases"] == ["晨间打卡走一遍"]
    assert created.json()["use_count"] == 0

    listed = client.get("/api/v1/agent/recipes", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["recipes"][0]["name"] == "晨间打卡"

    # 校验失败 fail-loud 400
    bad = client.post("/api/v1/agent/recipes", headers=headers, json={
        "name": "坏配方",
        "trigger_phrases": ["删库跑路"],
        "steps": [{"tool": "health_manage", "args_template": {"operation": "delete"}}],
    })
    assert bad.status_code == 400
    assert "不允许入配方" in bad.json()["detail"]

    # 跨用户删除 404
    _, other_token = create_authenticated_user(db)
    other_headers = {"Authorization": f"Bearer {other_token}"}
    assert client.delete(
        f"/api/v1/agent/recipes/{recipe_id}", headers=other_headers
    ).status_code == 404

    deleted = client.delete(f"/api/v1/agent/recipes/{recipe_id}", headers=headers)
    assert deleted.status_code == 200
    assert client.get("/api/v1/agent/recipes", headers=headers).json()["count"] == 0


def test_save_from_conversation_api(client, db):
    from app.services.agent_conversation_service import AgentConversationService

    user, token = create_authenticated_user(db)
    headers = {"Authorization": f"Bearer {token}"}
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title="打卡")
    svc.save_message(conv.id, "user", "记录早餐和喝水")
    ai_msg = svc.save_message(conv.id, "assistant", "都记好了")
    ai_msg.meta = {"recipe_candidate": {
        "steps": [_step_water(250), _step_water(300)],
        "step_count": 2,
    }}
    db.commit()

    saved = client.post(
        f"/api/v1/agent/recipes/{conv.id}/save-from-conversation",
        headers=headers,
        json={"name": "早餐流程", "trigger_phrases": ["早餐流程打卡"]},
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["created_from_conversation_id"] == conv.id
    assert len(body["steps"]) == 2

    # 触发短语立即可精确匹配
    assert recipe_svc.match_trigger(db, user.id, "早餐流程打卡") is not None

    # 无候选的对话 → 404
    conv2 = svc.get_or_create_conversation(user.id, None, title="闲聊")
    svc.save_message(conv2.id, "assistant", "你好")
    db.commit()
    assert client.post(
        f"/api/v1/agent/recipes/{conv2.id}/save-from-conversation",
        headers=headers,
        json={"name": "x配方", "trigger_phrases": ["随便打卡"]},
    ).status_code == 404

    # 别人的对话 → 404(不泄露存在性)
    _, other_token = create_authenticated_user(db)
    assert client.post(
        f"/api/v1/agent/recipes/{conv.id}/save-from-conversation",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"name": "偷配方", "trigger_phrases": ["偷来的打卡"]},
    ).status_code == 404


def test_recipes_appear_in_task_ledger(db):
    from app.services.task_ledger_service import build_ledger

    user, _ = create_authenticated_user(db)
    recipe_svc.create_recipe(
        db, user.id, name="晚间流程", trigger_phrases=["晚间流程打卡"],
        steps=[_step_water()],
    )
    ledger = build_ledger(user.id, db)
    recipe_items = [i for i in ledger["items"] if i["source"] == "recipe"]
    assert len(recipe_items) == 1
    assert recipe_items[0]["title"] == "晚间流程"
    assert recipe_items[0]["status"] == "saved"
