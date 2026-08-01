"""Fast-model routing for simple 小巴 turns (/api/v1/agent/stream).

Simple record / simple query turns route to the FASTEST reliable-tool-calling
model to cut latency; advice/analysis/复盘 turns keep the user's quality model
(qwen3.7-plus). Explicit UI model choice is always honored (never overridden).

The chosen fast model must have reliable_tool_calling=True — simple record/query
turns almost always call a tool (health_record/health_query/health_manage), and a
fast model that can't tool-call would silently break them.
"""
import json

import pytest

from app.services import agent_executor as ae
from app.services.agent_executor import (
    AgentExecutor,
    _build_fast_record_messages,
    _is_fast_eligible_turn,
    _looks_like_medical_report_image_context,
    _record_intent_needs_detail_message,
)
from app.services.llm import model_registry as reg


# ──── registry: pick_fast_tool_model_id ────

def test_generic_or_food_photo_prompts_skip_medical_report_ocr():
    assert _looks_like_medical_report_image_context("请分析这些图片") is False
    assert _looks_like_medical_report_image_context("记录午餐") is False
    assert _looks_like_medical_report_image_context("吃了一个黄桃") is False
    assert _looks_like_medical_report_image_context("请分析这张胃镜报告") is True
    assert _looks_like_medical_report_image_context("体检化验单指标导入") is True


def test_record_intent_needs_detail_message_is_honest_and_actionable():
    # fast-record 0 工具 = 从未写入。honesty 双约束:①不谎报成功 ②不谎称"写库失败"。
    msg = _record_intent_needs_detail_message("午餐吃了牛肉面")
    assert "还没记下来" in msg  # 如实:未记录
    assert "牛肉面" in msg  # 回显用户意图
    # 绝不谎报成功,也不谎称发生了 DB 写入失败(什么都没写过)
    for forbidden in ("已记录", "已经完成", "写入成功", "没有成功写入数据库", "写库失败"):
        assert forbidden not in msg
    empty = _record_intent_needs_detail_message("")
    assert "还没记下来" in empty
    assert "没有成功写入数据库" not in empty


@pytest.mark.parametrize(
    ("result", "expected_id"),
    [
        ('{"id":701,"message":"已记录晚餐"}', "701"),
        ('{"record_id":"702","message":"已记录"}', "702"),
        ('{"resource":{"type":"diet_record","id":703}}', "703"),
    ],
)
def test_write_receipt_uses_structured_tool_result_identity(result, expected_id):
    receipt = ae._write_receipt_from_tool_result("health_record", "diet", result)

    assert receipt == {
        "operation_id": f"health_record:diet_record:{expected_id}",
        "status": "verified",
        "resource_type": "diet_record",
        "resource_id": expected_id,
        "completed_at": receipt["completed_at"],
        "verified": True,
    }


@pytest.mark.parametrize(
    "result",
    [
        "not-json",
        "Error: API 返回 500",
        "[NEEDS_CONFIRMATION] 请确认后再写入",
        '{"success":false,"message":"记录失败"}',
        '{"id":701,"error":"database timeout"}',
        '{"id":701,"ok":false}',
        '{"id":701,"status":"rejected"}',
        '{"message":"已记录，但缺少资源标识"}',
    ],
)
def test_write_receipt_rejects_malformed_soft_failed_or_identityless_results(result):
    assert ae._write_receipt_from_tool_result("health_record", "diet", result) is None


def test_write_completion_distinguishes_confirmation_and_read_only_operations():
    assert ae._write_tool_attempted(
        "health_record",
        {"record_type": "diet"},
    ) is True
    assert ae._write_tool_attempted(
        "health_manage",
        {"record_type": "diet", "operation": "list"},
    ) is False
    assert ae._write_tool_attempted(
        "health_manage",
        {"record_type": "diet", "operation": "delete"},
    ) is True
    assert ae._write_tool_completed(
        "health_record",
        {"record_type": "diet"},
        '{"id":701}',
    ) is True
    assert ae._write_tool_completed(
        "health_record",
        {"record_type": "medication"},
        "[NEEDS_CONFIRMATION] 请确认用药记录",
    ) is False
    assert ae._write_tool_completed(
        "health_manage",
        {"record_type": "diet", "operation": "list"},
        '[{"id":701}]',
    ) is False
    assert ae._write_tool_completed(
        "health_record",
        {"record_type": "diet"},
        '{"id":701,"error":"database timeout"}',
    ) is False
    assert ae._write_tool_completed(
        "health_record",
        {"record_type": "diet"},
        "记录成功",
    ) is False


def test_pick_fast_tool_model_is_reliable_tool_caller():
    """The fast model chosen must be reliable_tool_calling=True (env-agnostic)."""
    fast_id = reg.pick_fast_tool_model_id(only_available=False)
    assert fast_id is not None
    entry = reg.get_model(fast_id)
    assert entry is not None
    assert entry.reliable_tool_calling is True
    assert entry.speed_tier == "fast"


def test_pick_fast_prefers_fastest_reliable_tier(monkeypatch):
    """Prefer fast tier; skip a fast-but-unreliable model, fall to next reliable tier."""
    monkeypatch.setattr(
        reg, "list_models",
        lambda only_available=False, include_non_chat=False: [
            # fastest tier is unreliable → must be skipped
            reg.ModelEntry("fastbad", "fb", "x", "m", "fast", reliable_tool_calling=False),
            reg.ModelEntry("balrel", "b", "x", "m", "balanced", reliable_tool_calling=True),
            reg.ModelEntry("reasonrel", "r", "x", "m", "reasoning", reliable_tool_calling=True),
        ],
    )
    # no reliable fast model → next fastest reliable = balanced
    assert reg.pick_fast_tool_model_id(only_available=False) == "balrel"


def test_pick_fast_picks_fastest_when_reliable(monkeypatch):
    monkeypatch.setattr(
        reg, "list_models",
        lambda only_available=False, include_non_chat=False: [
            reg.ModelEntry("balrel", "b", "x", "m", "balanced", reliable_tool_calling=True),
            reg.ModelEntry("fastrel", "f", "x", "m", "fast", reliable_tool_calling=True),
        ],
    )
    assert reg.pick_fast_tool_model_id(only_available=False) == "fastrel"


def test_pick_fast_none_when_no_reliable(monkeypatch):
    """No reliable model at all → None (caller keeps default, does not route)."""
    monkeypatch.setattr(
        reg, "list_models",
        lambda only_available=False, include_non_chat=False: [
            reg.ModelEntry("bad", "bad", "x", "m", "fast", reliable_tool_calling=False),
        ],
    )
    assert reg.pick_fast_tool_model_id(only_available=False) is None


# ──── classifier: _is_fast_eligible_turn ────

@pytest.mark.parametrize("msg", [
    "记录我喝了500ml水",
    "帮我打卡今天的体重68kg",
    "我今天喝了多少水",
    "查一下我最近的血压",
    "看一下我今天走了几步",
    "本周体重是多少",
])
def test_record_and_simple_query_are_fast_eligible(msg):
    assert _is_fast_eligible_turn(msg, has_images=False, has_file=False) is True


@pytest.mark.parametrize("msg", [
    "综合分析我的健康趋势",
    "复盘我这周的睡眠",
    "为什么我最近血压偏高",
    "给我一个减脂饮食方案",
    "结合我的基因该怎么补叶酸",
    "帮我评估心血管风险",
])
def test_advice_and_analysis_not_fast_eligible(msg):
    assert _is_fast_eligible_turn(msg, has_images=False, has_file=False) is False


def test_attachments_never_fast_eligible():
    # even a pure record message is not fast-eligible when images/file present
    assert _is_fast_eligible_turn("记录我喝了水", has_images=True, has_file=False) is False
    assert _is_fast_eligible_turn("查一下体重", has_images=False, has_file=True) is False


def test_ambiguous_falls_to_quality_model():
    # neither record nor simple-query nor advice → conservative: not fast-eligible
    assert _is_fast_eligible_turn("你好呀", has_images=False, has_file=False) is False


def test_fast_record_prompt_routes_diet_queries_and_meal_scoped_edits():
    routed = _build_fast_record_messages([
        {"role": "user", "content": "查询全天饮食和热量，修改晚餐实际摄入数据"},
    ])

    system = routed[0]["content"]
    assert "health_query(dimension='diet')" in system
    assert "health_manage" in system
    assert "meal_type" in system
    assert "dinner" in system


# ──── end-to-end routing through run_stream ────

# The concrete fast model id used in these tests. Registry picks it deterministically
# (fastest reliable-tool-calling chat model). We pin the helper so the test does not
# depend on env-gated availability.
_FAST_ID = "deepseek-v4-flash"


def _stub_registry_fast(monkeypatch, fast_id=_FAST_ID):
    monkeypatch.setattr(reg, "pick_fast_tool_model_id", lambda **_k: fast_id)


async def _run(executor, message, extra_context=None, user_id=1):
    return [
        event
        async for event in executor.run_stream(
            user_id=user_id,
            message=message,
            user_auth_token="test-token",
            extra_context=extra_context,
        )
    ]


class _FakeProvider:
    """Answers directly with no tool call (keeps the round loop short)."""

    def __init__(self, model_id):
        self.model = model_id

    async def chat_stream(self, **kwargs):  # noqa: ARG002
        yield {"type": "content", "text": "OK"}
        yield {"type": "finish", "finish_reason": "stop"}

    async def chat(self, **kwargs):  # noqa: ARG002
        return {"content": "OK", "finish_reason": "stop"}


def _wire_common(executor, monkeypatch, provider_factory):
    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    # subset 参数与生产签名对齐(fast 回合传 big-3 白名单;桩固定回 noop 工具)
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [{
        "type": "function",
        "function": {"name": "noop", "description": "x", "parameters": {"type": "object", "properties": {}}},
    }])
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        provider_factory,
    )
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")


@pytest.mark.asyncio
async def test_record_turn_routes_to_fast_model(db, auth_user_and_headers, monkeypatch):
    """(a) A record turn → fast model selected."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    created = []

    def factory(model_id):
        created.append(model_id)
        return _FakeProvider(model_id)

    _stub_registry_fast(monkeypatch)
    _wire_common(executor, monkeypatch, factory)

    events = await _run(executor, "记录我喝了500ml水", user_id=user.id)
    done = events[-1]["data"]

    assert created == [_FAST_ID]
    assert done["model"] == _FAST_ID
    assert done["selected_model"] == _FAST_ID
    assert executor._request_model_id == _FAST_ID


@pytest.mark.asyncio
async def test_simple_query_turn_routes_to_fast_model(db, auth_user_and_headers, monkeypatch):
    """(b) A simple query turn → fast model."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    created = []

    def factory(model_id):
        created.append(model_id)
        return _FakeProvider(model_id)

    _stub_registry_fast(monkeypatch)
    _wire_common(executor, monkeypatch, factory)

    events = await _run(executor, "查一下我今天喝了多少水", user_id=user.id)
    done = events[-1]["data"]

    assert created == [_FAST_ID]
    assert done["model"] == _FAST_ID
    assert executor._request_model_id == _FAST_ID


@pytest.mark.asyncio
async def test_analysis_turn_keeps_quality_model(db, auth_user_and_headers, monkeypatch):
    """(c) An analysis/复盘 turn → quality/preference model (NO fast override)."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)

    # If the code ever routed this to the fast model, create_provider_for_model_id
    # would be called with _FAST_ID — assert it is NOT.
    created = []

    def model_factory(model_id):
        created.append(model_id)
        return _FakeProvider(model_id)

    default_provider = _FakeProvider("qwen3.7-plus")

    _stub_registry_fast(monkeypatch)
    _wire_common(executor, monkeypatch, model_factory)
    # user-preference / default path
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_user",
        lambda uid, db, **k: default_provider,
    )

    events = await _run(executor, "综合分析我的健康趋势", user_id=user.id)
    done = events[-1]["data"]

    assert executor._request_model_id is None  # not overridden to fast
    assert _FAST_ID not in created  # never built the fast provider
    assert done["model"] == "qwen3.7-plus"  # answered by the default/quality model


CLINICIAN_FALLBACK_NONWRITE_MESSAGES = (
    "医生让我记录每天腰痛情况",
    "医生叫我记录每天腰痛情况",
    "大夫交代我记录每天腰痛情况",
    "我让医生记录每天腰痛情况",
    "家属叫医生记录每天腰痛情况",
    "医生说让我记录每天腰痛情况。请记录医生诊断：臀肌无力",
    "医生告诉我记录每天腰痛情况。请记录医生诊断：臀肌无力",
    "医生嘱咐你记录每天腰痛情况。请记录医生诊断：臀肌无力",
    "医生告诉我让我记录每天腰痛情况。请记录医生诊断：臀肌无力",
    "医生要求记录每天腰痛情况。请记录医生诊断：臀肌无力",
    "医生说请记录每天腰痛情况。请记录医生诊断：臀肌无力",
    "不要保存医生诊断",
    "不要写入医生反馈",
    "不需要保存医生诊断",
    "请先不要保存医生诊断",
    "请不要再保存医生诊断",
    "请不要帮我保存医生诊断",
    "不要写入医生体重",
    "不要不保存医生诊断",
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    (
        "医生诊断是大腿和臀部肌肉无力导致腰肌代偿进而导致腰肌痛",
        "医生认为是臀肌无力导致腰痛，我该怎么处理？",
        "请记录医生诊断：臀肌无力导致腰肌代偿",
        "请记录医生诊断：臀肌无力并删除旧记录",
        *CLINICIAN_FALLBACK_NONWRITE_MESSAGES,
    ),
)
async def test_clinician_turns_never_select_fast_record_or_needs_detail_reply(
    db,
    auth_user_and_headers,
    monkeypatch,
    message,
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    provider = _FakeProvider("qwen3.7-plus")

    _stub_registry_fast(monkeypatch)
    _wire_common(executor, monkeypatch, lambda model_id: _FakeProvider(model_id))
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_user",
        lambda uid, db, **kwargs: provider,
    )

    events = await _run(executor, message, user_id=user.id)
    done = events[-1]["data"]
    emitted_text = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert executor._prefer_fast_record_model is False
    assert done["record_intent_no_tool"] is False
    assert emitted_text == "OK"


@pytest.mark.asyncio
async def test_explicit_model_override_is_honored(db, auth_user_and_headers, monkeypatch):
    """(d) Explicit _request_model_id (UI pick) → honored, not overridden by fast route."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    created = []

    def factory(model_id):
        created.append(model_id)
        return _FakeProvider(model_id)

    _stub_registry_fast(monkeypatch)
    _wire_common(executor, monkeypatch, factory)

    # Even though "记录..." is fast-eligible, the user explicitly picked claude.
    events = await _run(
        executor,
        "记录我喝了500ml水",
        extra_context=json.dumps({"client": "mac", "model_id": "claude-opus-4.7"}),
        user_id=user.id,
    )
    done = events[-1]["data"]

    assert executor._request_model_id == "claude-opus-4.7"
    assert created == ["claude-opus-4.7"]
    assert _FAST_ID not in created
    # selected_model is the registry display name (entry.model), not the id
    assert done["selected_model"] == "commercial/Claude-Opus-4.7"


# ──── auto-confirm 分级: _auto_confirm_fast_record_args ────
# symptom/rhinitis 免确认前置(回显+可撤销);医疗级/资金类永远确认;
# unknown kind fail-closed 走确认。对抗:模型预置 confirmed=true 必须被剥掉。


def _auto_confirm(kind: str, *, pre_confirmed: bool = False, channel: str | None = None) -> dict:
    args = {"record_type": kind, "data": {"description": "x", "body_part": "general"}}
    if pre_confirmed:
        args["confirmed"] = True
        args["data"]["confirmed"] = True
    out = ae._auto_confirm_fast_record_args("health_record", args, channel=channel)
    return out


def test_symptom_record_auto_confirms_on_typed_channel():
    out = _auto_confirm("symptom", channel="typed")
    assert out["confirmed"] is True
    assert out["data"]["confirmed"] is True
    assert "_fast_record_requires_confirmation" not in out


def test_symptom_without_channel_fails_closed_to_confirmation():
    # 旧客户端/Siri/未声明通道:症状保留确认前置(传输层 fail-closed)
    out = _auto_confirm("symptom", pre_confirmed=True, channel=None)
    assert out.get("confirmed") is not True
    assert out["_fast_record_requires_confirmation"] is True


def test_rhinitis_record_auto_confirms_on_typed_channel():
    out = _auto_confirm("rhinitis", channel="typed")
    assert out["confirmed"] is True


def test_medication_always_requires_confirmation_even_if_model_preconfirms():
    out = _auto_confirm("medication", pre_confirmed=True)
    assert out.get("confirmed") is not True
    assert out["data"].get("confirmed") is not True
    assert out["_fast_record_requires_confirmation"] is True


def test_dose_and_payment_stay_confirm_first():
    for kind in ("dose", "payment", "prescription", "adherence"):
        out = _auto_confirm(kind, pre_confirmed=True)
        assert out.get("confirmed") is not True, kind
        assert out["_fast_record_requires_confirmation"] is True, kind


def test_unknown_kind_fails_closed_to_confirmation():
    out = _auto_confirm("mystery_kind", pre_confirmed=True)
    assert out.get("confirmed") is not True
    assert out["_fast_record_requires_confirmation"] is True


def test_water_still_auto_confirms():
    out = _auto_confirm("water")
    assert out["confirmed"] is True


def test_symptom_friendly_echo_offers_undo():
    reply = ae._friendly_record_confirmation({"description": "舌头尖溃疡", "body_part": "other"})
    assert "已记录症状" in reply
    assert "撤销" in reply


def test_symptom_friendly_echo_carries_record_id_for_undo_turn():
    # 撤销回合走快路由只带上一行回显 → 回显必须含记录号,否则模型无 id 可删
    reply = ae._friendly_record_confirmation({"id": 19, "description": "舌头尖溃疡", "body_part": "other"})
    assert "记录号 19" in reply
    assert "撤销" in reply


def test_list_tool_result_never_claims_records_created():
    # 对抗评审实测:撤销回合模型 list 查 ID,数组结果曾被答成"✅已记录 2 条"(假写入宣称)
    import json as _json
    msgs = [{"role": "tool", "content": _json.dumps([
        {"id": 18, "description": "a"}, {"id": 19, "description": "b"},
    ], ensure_ascii=False)}]
    reply = ae._fast_record_reply_from_tool_results(msgs)
    assert "已记录" not in reply
    assert "查到 2 条" in reply
    assert "18" in reply and "19" in reply


def test_symptom_via_voice_channels_keeps_confirmation():
    # 语音/siri 通道转写失真率高(且 Siri 单轮无法撤销)→ 症状保留确认前置
    for channel in ("voice", "siri"):
        args = {"record_type": "symptom", "data": {"description": "头痛", "body_part": "head"}}
        out = ae._auto_confirm_fast_record_args("health_record", args, channel=channel)
        assert out["_fast_record_requires_confirmation"] is True, channel
        assert "confirmed" not in out


def test_clear_voice_symptom_statement_skips_confirmation():
    args = {"record_type": "symptom", "data": {"description": "还是有腰疼的症状"}}
    out = ae._auto_confirm_fast_record_args(
        "health_record",
        args,
        channel="voice",
        user_message="还是有腰疼的症状。",
    )

    assert out["confirmed"] is True
    assert out["data"]["confirmed"] is True
    assert "_fast_record_requires_confirmation" not in out


def test_clear_voice_sneeze_statement_skips_confirmation():
    args = {"record_type": "rhinitis", "data": {"sneezing": 1}}
    out = ae._auto_confirm_fast_record_args(
        "health_record",
        args,
        channel="voice",
        user_message="记录下来刚才打了一个喷嚏。",
    )

    assert out["confirmed"] is True
    assert out["data"]["confirmed"] is True
    assert "_fast_record_requires_confirmation" not in out


def test_water_auto_confirms_regardless_of_channel():
    # 通道守卫只作用于症状类;低风险数值记录(water)任何通道免确认
    for channel in (None, "voice", "typed"):
        args = {"record_type": "water", "data": {"amount": 250}}
        out = ae._auto_confirm_fast_record_args("health_record", args, channel=channel)
        assert out["confirmed"] is True, channel


@pytest.mark.asyncio
async def test_typed_symptom_writes_without_confirmation_roundtrip(db):
    # 打字通道症状:auto-confirm 后端到端直达 API 写入(不再 [NEEDS_CONFIRMATION])
    executor = AgentExecutor(db)
    posted = {}

    async def _capture_post(url, headers, payload):
        posted["url"] = url
        posted["payload"] = payload
        return '{"id": 1, "body_part": "other", "description": "舌头尖溃疡"}'

    executor._api_post = _capture_post
    args = ae._auto_confirm_fast_record_args(
        "health_record",
        {"record_type": "symptom", "data": {"body_part": "other", "description": "舌头尖溃疡"}},
        channel="typed",
    )
    result = await executor._exec_health_record("http://x", {}, args)

    assert "NEEDS_CONFIRMATION" not in result
    assert posted["url"].endswith("/symptoms")
    assert posted["payload"]["description"] == "舌头尖溃疡"


# ──── P4: lite system prompt for fast-routed simple turns ────
# fast-route 的简单记录/查询回合应走 lite prompt: 保留核心人格 + R4 边界 + 防回显 +
# 记录参数指引 + 基础画像; 剥掉分析 blob (世界观/肝/原研药/基因/记忆…) 与系统知识库检索。
# 非快路由回合 prompt 逐字节不变。

# 稳定 marker (从 _build_system_prompt 静态 parts / 各 blob 里挑不会漂移的短语):
_R4_MARKER = "## 安全与边界 (R4"          # 医疗边界章节标题
_ANTI_ECHO_MARKER = "绝对不要把工具返回的原始 JSON"   # 防回显规则 (R4 里那条)
_RECORD_GUIDANCE_MARKER = "data 参数必须包含具体内容"  # 记录 worked-example / 单位默认指引
_LITE_HEALTH_MARKER = "当前时段:"           # build_lite_health_context 路径注入
_TURN_TIME_CONTEXT_MARKER = "每轮用户消息前会附带系统生成的本轮时间信息"
# full-only marker (lite 必须不含):
_WORLDVIEW_MARKER = "【健康世界观"          # worldview_prompt_blob (full 恒注入)


def test_lite_prompt_keeps_core_persona_and_record_guidance(db, auth_user_and_headers):
    """(a) fast/lite prompt 含 R4 + 防回显 + 记录指引 + lite_health, 不含 worldview。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)

    lite = executor._build_system_prompt(user.id, 1, "tok", lite=True)

    # KEEP: 核心人格 / R4 边界 / 防回显 / 记录参数指引 / 基础画像
    assert _R4_MARKER in lite
    assert _ANTI_ECHO_MARKER in lite
    assert _RECORD_GUIDANCE_MARKER in lite
    assert _LITE_HEALTH_MARKER in lite
    assert _TURN_TIME_CONTEXT_MARKER in lite
    # SKIP: 分析 blob (世界观是 full 恒注入的最稳 marker)
    assert _WORLDVIEW_MARKER not in lite


def test_full_prompt_unchanged_contains_analysis_blobs(db, auth_user_and_headers):
    """(b) 非快路由 (lite=False) prompt 仍含分析 blob (worldview) + 全部核心 marker。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)

    full = executor._build_system_prompt(user.id, 1, "tok", lite=False)

    # 分析 blob 仍在
    assert _WORLDVIEW_MARKER in full
    # 核心 marker 与 lite 共有
    assert _R4_MARKER in full
    assert _ANTI_ECHO_MARKER in full
    assert _RECORD_GUIDANCE_MARKER in full
    assert _TURN_TIME_CONTEXT_MARKER in full


def test_default_prompt_equals_full_byte_for_byte(db, auth_user_and_headers):
    """非快路由默认调用 (不传 lite) 必须与 lite=False 逐字节等同 (行为零变化)。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    assert executor._build_system_prompt(user.id, 1, "tok") == executor._build_system_prompt(
        user.id, 1, "tok", lite=False
    )


def test_lite_prompt_is_smaller_than_full(db, auth_user_and_headers):
    """lite prompt 必须显著短于 full (prefill 削减)。打印实测削减量供观测。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    lite = executor._build_system_prompt(user.id, 1, "tok", lite=True)
    full = executor._build_system_prompt(user.id, 1, "tok", lite=False)
    cut = len(full) - len(lite)
    print(
        f"\n[P4 prompt char reduction] full={len(full)} lite={len(lite)} "
        f"cut={cut} ({cut / len(full) * 100:.1f}%)"
    )
    assert len(lite) < len(full)


@pytest.mark.asyncio
async def test_fast_turn_skips_system_kb_context(db, auth_user_and_headers, monkeypatch):
    """(c) fast-routed 回合跳过系统知识库检索 (_build_system_knowledge_prompt_context 不被调用)。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)

    kb_calls: list = []

    def _spy_kb(uid, msg):
        kb_calls.append((uid, msg))
        return "SYSTEM_KB_BLOCK"

    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", _spy_kb)

    def factory(model_id):
        return _FakeProvider(model_id)

    _stub_registry_fast(monkeypatch)
    _wire_common(executor, monkeypatch, factory)
    # _wire_common stubs _build_system_prompt to "SYS"; that's fine — we only assert
    # the KB spy is skipped when fast-routed.

    await _run(executor, "记录我喝了500ml水", user_id=user.id)

    assert executor._fast_route_simple_turn is True
    assert kb_calls == []  # KB retrieval skipped for the fast turn


@pytest.mark.asyncio
async def test_analysis_turn_calls_system_kb_context(db, auth_user_and_headers, monkeypatch):
    """对照 (c): 非快路由分析回合仍调用系统知识库检索。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)

    kb_calls: list = []

    def _spy_kb(uid, msg):
        kb_calls.append((uid, msg))
        return ""

    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", _spy_kb)

    default_provider = _FakeProvider("qwen3.7-plus")
    _stub_registry_fast(monkeypatch)
    _wire_common(executor, monkeypatch, lambda mid: _FakeProvider(mid))
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_user",
        lambda uid, db, **k: default_provider,
    )

    await _run(executor, "综合分析我的健康趋势", user_id=user.id)

    assert executor._fast_route_simple_turn is False
    assert len(kb_calls) == 1  # KB retrieval ran for the analysis turn


# ──── Task 2: honest non-streaming UX for LangBridge commercial models ────
# ModelEntry.supports_streaming 默认 True; langbridge-proxy 商用三强 = False。
# 答案轮遇非流式模型多发一条 thinking 状态 detail; 流式模型 detail 恒 None。


def test_supports_streaming_defaults_true():
    """新字段默认 True — 拿不准的模型走正常 token 滚动。"""
    e = reg.ModelEntry("x", "X", "tokenplan", "m", "fast")
    assert e.supports_streaming is True


@pytest.mark.parametrize("model_id", ["claude-opus-4.7", "gpt-5.5", "gemini-3.1-pro"])
def test_langbridge_entries_are_non_streaming(model_id):
    """langbridge-proxy 商用模型标 supports_streaming=False (上游无 SSE, 整段返回)。"""
    entry = reg.get_model(model_id)
    assert entry is not None
    assert entry.provider == "langbridge-proxy"
    assert entry.supports_streaming is False


def test_tokenplan_entries_stay_streaming():
    """tokenplan 直连模型仍是流式 (逐 token)。抽查几个。"""
    for model_id in ("qwen3.7-plus", "deepseek-v4-flash", "deepseek-v4-pro"):
        entry = reg.get_model(model_id)
        assert entry is not None
        assert entry.supports_streaming is True, model_id


def test_status_detail_emitted_for_non_streaming_model(db, monkeypatch):
    """答案模型 resolve 到非流式 entry → thinking 状态带 detail。"""
    executor = AgentExecutor(db)
    executor._request_model_id = "claude-opus-4.7"

    assert executor._resolved_answer_model_is_non_streaming() is True


def test_status_detail_not_emitted_for_streaming_model(db):
    """答案模型 resolve 到流式 entry → 不发 detail (走正常滚动)。"""
    executor = AgentExecutor(db)
    executor._request_model_id = "deepseek-v4-flash"

    assert executor._resolved_answer_model_is_non_streaming() is False


def test_non_streaming_resolve_fail_soft_on_unknown(db):
    """未知 model_id / 无 model → fail-soft 返回 False (不误发提示)。"""
    executor = AgentExecutor(db)
    executor._request_model_id = "nope-not-registered"
    assert executor._resolved_answer_model_is_non_streaming() is False
    executor._request_model_id = None
    executor._current_user_id = None
    assert executor._resolved_answer_model_is_non_streaming() is False


@pytest.mark.asyncio
async def test_run_stream_emits_thinking_detail_for_non_streaming(db, auth_user_and_headers, monkeypatch):
    """端到端: 非流式模型的分析回合, SSE 里出现带 detail 的 thinking 状态事件。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)

    _wire_common(executor, monkeypatch, lambda mid: _FakeProvider(mid))

    events = await _run(
        executor,
        "综合分析我的健康趋势",
        extra_context=json.dumps({"client": "mac", "model_id": "claude-opus-4.7"}),
        user_id=user.id,
    )

    details = [
        e["data"].get("detail")
        for e in events
        if e.get("event") == "status" and e["data"].get("stage") == "thinking"
    ]
    assert "该模型整段生成,需等待完整回答" in details


@pytest.mark.asyncio
async def test_run_stream_no_thinking_detail_for_streaming(db, auth_user_and_headers, monkeypatch):
    """对照: 流式模型的回合, thinking 状态 detail 恒为 None。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)

    _stub_registry_fast(monkeypatch)
    _wire_common(executor, monkeypatch, lambda mid: _FakeProvider(mid))

    # 走 fast-route → deepseek-v4-flash (streaming)
    events = await _run(executor, "记录我喝了500ml水", user_id=user.id)

    thinking_details = [
        e["data"].get("detail")
        for e in events
        if e.get("event") == "status" and e["data"].get("stage") == "thinking"
    ]
    assert thinking_details  # at least one thinking status was emitted
    assert all(d is None for d in thinking_details)
