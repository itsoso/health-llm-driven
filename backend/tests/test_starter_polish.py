"""Starter polish tests — verify gate battery, JSON defense, endpoint overlay.

The polish layer must keep RULES as the single source of facts: the LLM only
rewrites wording, and a deterministic verify gate rejects anything invented,
falling back to rule template text. Fail-safe is ALWAYS the rule text.

All LLM interaction here uses a fake provider — NO network.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services import starter_polish
from app.services.starter_polish import build_polish_input, polish_starters, verify_polished
from app.services.starter_polish import verify_polished as _vp
from app.services.conversation_starters import SuggestionCandidate


CHINA_TZ = ZoneInfo("Asia/Shanghai")


# Reuse the starters clock freeze so endpoint tests don't fire time generators
# (see test_conversation_starters for the rationale).
@pytest.fixture(autouse=True)
def _freeze_starters_clock(monkeypatch):
    import app.services.conversation_starters as cs

    _RealDT = cs.datetime

    class _FrozenDT(_RealDT):
        @classmethod
        def now(cls, tz=None):
            return _RealDT(2026, 5, 27, 15, 0, tzinfo=tz)

    monkeypatch.setattr(cs, "datetime", _FrozenDT)


class _FakeProvider:
    """Records the messages it was called with and returns a canned raw string."""

    def __init__(self, raw):
        self._raw = raw
        self.calls = 0
        self.last_messages = None

    async def chat(self, messages=None, **kwargs):
        self.calls += 1
        self.last_messages = messages
        return self._raw


# ─────────────────────── Verify gate battery ─────────────────────────────


def test_verify_rejects_fabricated_number():
    # source has 40; output invents 88 (readiness that was never in the rule text)
    assert verify_polished("今天恢复评分 88，要不要歇一歇？", ["今天恢复评分 40，帮我安排休息"]) is False


def test_verify_passes_when_number_anchored_in_source():
    assert verify_polished("恢复评分只有 40，今天怎么歇？", ["今天恢复评分 40，帮我安排轻负荷或休息日方案"]) is True


def test_verify_rejects_red_word_not_in_source():
    # "加量" is a prescriptive red word; the source never said it
    assert verify_polished("要不要给药加量一点？", ["今天恢复评分 40，帮我安排休息"]) is False


def test_verify_passes_red_word_when_present_in_source():
    # source already contains the red word "服用" → the rule said it, so allowed
    src = ["帮我复盘补剂服用情况并优化"]
    assert verify_polished("最近补剂服用得怎么样？", src) is True


def test_verify_rejects_bare_imperative():
    # ends without ？ and carries an imperative marker
    assert verify_polished("你应该立即去医院检查血压", ["最近一次血压 165/100 偏高"]) is False


def test_verify_passes_good_question_rewrite():
    assert verify_polished("最近血压有点高，我要怎么处理？", ["最近一次血压 165/100 偏高，我需要怎么处理？"]) is True


def test_verify_rejects_out_of_length_bounds():
    assert verify_polished("好吗？", ["今天怎么安排训练和恢复"]) is False  # too short (<6)
    long = "今天恢复评分怎么样要不要安排一次完整的休息日方案顺便再看看训练强度以及睡眠情况呢到底该怎么办？"  # >40 chars
    assert len(long) > 40
    assert verify_polished(long, ["今天恢复评分 40"]) is False


def test_verify_number_anchoring_handles_decimals_and_percent():
    src = ["帮我提升补剂依从率（近7天完成率 42.5%）"]
    assert verify_polished("完成率才 42.5%，怎么提上去？", src) is True
    assert verify_polished("完成率才 99.9%，怎么提上去？", src) is False


# ── Synthesis-specific verify behavior ──


def test_verify_synthesis_rejects_third_party_number():
    # union of two sources contains 40 and AQI 210; output invents 50
    sources = ["今天恢复评分 40，帮我安排休息", "北京 AQI 210（重污染），今天能不能出门活动？"]
    assert verify_polished("恢复才 50，加上空气差，今天还能出门吗？", sources) is False


def test_verify_synthesis_valid_against_union():
    sources = ["今天恢复评分 40，帮我安排休息", "北京 AQI 210（重污染），今天能不能出门活动？"]
    assert verify_polished("恢复评分 40，AQI 210，今天该怎么安排？", sources) is True


# ─────────────────────── JSON defense ─────────────────────────────────────


def test_json_defense_strips_code_fence():
    raw = '```json\n[{"key": "readiness", "text": "今天要怎么练？"}]\n```'
    out = starter_polish._parse_json_array(raw)
    assert out == [{"key": "readiness", "text": "今天要怎么练？"}]


def test_json_defense_normalizes_curly_quotes():
    raw = '[{“key”: “readiness”, “text”: “今天怎么安排？”}]'
    out = starter_polish._parse_json_array(raw)
    assert out == [{"key": "readiness", "text": "今天怎么安排？"}]


def test_json_defense_extracts_array_from_surrounding_prose():
    raw = '这是你要的结果:\n[{"key": "aqi", "text": "空气怎样？"}]\n希望有用!'
    out = starter_polish._parse_json_array(raw)
    assert out == [{"key": "aqi", "text": "空气怎样？"}]


def test_json_defense_garbage_returns_none():
    assert starter_polish._parse_json_array("完全不是 JSON 的一段话") is None
    assert starter_polish._parse_json_array("") is None
    assert starter_polish._parse_json_array("{not: valid}") is None


# ─────────────────────── build_polish_input ───────────────────────────────


def test_build_polish_input_extracts_facts_from_template():
    cards = [
        SuggestionCandidate(100, "今天恢复评分 40，帮我安排休息", "readiness"),
        SuggestionCandidate(90, "北京 AQI 210，怎么换室内方案？", "aqi"),
    ]
    payload = build_polish_input(cards)
    items = payload["cards"]
    assert items[0]["key"] == "readiness"
    assert items[0]["template_text"] == "今天恢复评分 40，帮我安排休息"
    assert "40" in items[0]["facts"]["numbers"]
    assert "210" in items[1]["facts"]["numbers"]
    assert "AQI" in items[1]["facts"]["units"]


# ─────────────────────── polish_starters (fake provider) ───────────────────


@pytest.mark.asyncio
async def test_polish_starters_verified_rewrite_is_served():
    cards = [SuggestionCandidate(100, "今天恢复评分 40，帮我安排轻负荷或休息日方案", "readiness")]
    provider = _FakeProvider('[{"key": "readiness", "text": "恢复评分 40，今天怎么歇？"}]')
    out = await polish_starters(cards, now=datetime.now(CHINA_TZ), provider=provider)
    assert provider.calls == 1  # exactly ONE chat call
    assert len(out) == 1
    assert out[0].polished is True
    assert out[0].text == "恢复评分 40，今天怎么歇？"
    assert out[0].key == "readiness"
    assert out[0].priority == 100


@pytest.mark.asyncio
async def test_polish_starters_fabricated_number_falls_back_to_template():
    cards = [SuggestionCandidate(100, "今天恢复评分 40，帮我安排休息", "readiness")]
    # LLM invents 88 → verify rejects → keep template text
    provider = _FakeProvider('[{"key": "readiness", "text": "恢复评分 88，今天怎么歇？"}]')
    out = await polish_starters(cards, now=datetime.now(CHINA_TZ), provider=provider)
    assert out[0].polished is False
    assert out[0].text == "今天恢复评分 40，帮我安排休息"


@pytest.mark.asyncio
async def test_polish_starters_accepts_valid_synthesis():
    cards = [
        SuggestionCandidate(100, "今天恢复评分 40，帮我安排休息", "readiness"),
        SuggestionCandidate(90, "北京 AQI 210，怎么换室内方案？", "aqi"),
    ]
    raw = (
        '[{"key": "readiness", "text": "恢复评分 40，今天怎么歇？"},'
        ' {"key": "aqi", "text": "AQI 210，室内怎么练？"},'
        ' {"key": "synthesis", "combines": ["readiness", "aqi"],'
        '  "text": "恢复评分 40，AQI 210，今天该怎么安排？"}]'
    )
    provider = _FakeProvider(raw)
    out = await polish_starters(cards, now=datetime.now(CHINA_TZ), provider=provider)
    syn = [c for c in out if c.synthesis]
    assert len(syn) == 1
    assert syn[0].key == "synthesis"
    assert syn[0].combines == ("readiness", "aqi")
    assert syn[0].text == "恢复评分 40，AQI 210，今天该怎么安排？"


@pytest.mark.asyncio
async def test_polish_starters_drops_invalid_synthesis():
    cards = [
        SuggestionCandidate(100, "今天恢复评分 40，帮我安排休息", "readiness"),
        SuggestionCandidate(90, "北京 AQI 210，怎么换室内方案？", "aqi"),
    ]
    # synthesis invents a number (50) not in either source → dropped
    raw = (
        '[{"key": "readiness", "text": "恢复评分 40，今天怎么歇？"},'
        ' {"key": "synthesis", "combines": ["readiness", "aqi"],'
        '  "text": "恢复 50，空气差，今天还出门吗？"}]'
    )
    provider = _FakeProvider(raw)
    out = await polish_starters(cards, now=datetime.now(CHINA_TZ), provider=provider)
    assert not any(c.synthesis for c in out)


@pytest.mark.asyncio
async def test_polish_starters_provider_error_returns_none():
    class _Boom:
        async def chat(self, **kwargs):
            raise RuntimeError("provider down")

    cards = [SuggestionCandidate(100, "今天恢复评分 40", "readiness")]
    out = await polish_starters(cards, now=datetime.now(CHINA_TZ), provider=_Boom())
    assert out is None


@pytest.mark.asyncio
async def test_polish_starters_unparseable_returns_none():
    cards = [SuggestionCandidate(100, "今天恢复评分 40", "readiness")]
    provider = _FakeProvider("对不起我帮不了你")
    out = await polish_starters(cards, now=datetime.now(CHINA_TZ), provider=provider)
    assert out is None


# ─────────────────────── signals_hash stability ───────────────────────────


def test_signals_hash_is_stable_and_order_independent():
    a = [
        SuggestionCandidate(100, "今天恢复评分 40", "readiness"),
        SuggestionCandidate(90, "北京 AQI 210", "aqi"),
    ]
    b = list(reversed(a))
    assert starter_polish.signals_hash(a) == starter_polish.signals_hash(b)
    c = [SuggestionCandidate(100, "今天恢复评分 41", "readiness")]  # different data
    assert starter_polish.signals_hash(a) != starter_polish.signals_hash(c)


# ─────────────────────── Endpoint-level behavior ──────────────────────────


def _seed_exam(db, user):
    from app.models.medical_exam import MedicalExam, MedicalExamItem

    exam = MedicalExam(
        user_id=user.id,
        exam_date=date.today() - timedelta(days=3),
        exam_type="comprehensive",
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)
    db.add(
        MedicalExamItem(
            exam_id=exam.id,
            category="lipid",
            item_name="LDL-C",
            value=4.2,
            unit="mmol/L",
            is_abnormal="high",
            source="manual",
        )
    )
    db.commit()


def test_endpoint_flag_on_cache_miss_serves_rules_and_polished_false(
    client, db, auth_user_and_headers, monkeypatch
):
    """Flag ON + cache miss → rule text served immediately, polished=false,
    and a background warm task is scheduled (no blocking LLM call)."""
    monkeypatch.setattr("app.config.settings.starter_llm_polish_enabled", True, raising=False)
    # force a cache miss without touching Redis
    monkeypatch.setattr(starter_polish, "read_cached_polish", lambda *a, **k: None)
    warmed = {"called": False}
    monkeypatch.setattr(
        starter_polish,
        "warm_polish_cache",
        lambda *a, **k: warmed.__setitem__("called", True),
    )

    user, headers = auth_user_and_headers
    _seed_exam(db, user)

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)
    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert suggestions, "expected data-driven chips"
    # rule text served; every card explicitly polished=false on a miss
    assert all(s["polished"] is False for s in suggestions)
    assert any("LDL" in s["text"] or "体检" in s["text"] for s in suggestions)
    # background warm scheduled (TestClient runs BackgroundTasks synchronously)
    assert warmed["called"] is True


def test_endpoint_cache_hit_serves_polished_true(
    client, db, auth_user_and_headers, monkeypatch
):
    """Pre-seeded cache → polished text served with polished=true for the hit key."""
    monkeypatch.setattr("app.config.settings.starter_llm_polish_enabled", True, raising=False)

    def _fake_cache(user_id, sig_hash):
        # polished entry for whatever the exam generator produced
        return [{"key": "exam", "text": "最近体检有异常，要一起看看吗？", "polished": True}]

    monkeypatch.setattr(starter_polish, "read_cached_polish", _fake_cache)

    user, headers = auth_user_and_headers
    _seed_exam(db, user)

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)
    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    exam_cards = [s for s in suggestions if s["key"] == "exam"]
    assert exam_cards, "exam generator should have fired"
    assert exam_cards[0]["polished"] is True
    assert exam_cards[0]["text"] == "最近体检有异常，要一起看看吗？"


def test_cached_synthesis_replaces_the_lowest_priority_chip_within_display_limit():
    from app.api.agent import _merge_cached_polish
    from app.services.conversation_starters import SuggestionCandidate

    cards = [
        SuggestionCandidate(100, "严重读数", "safety"),
        SuggestionCandidate(80, "恢复", "recovery"),
        SuggestionCandidate(60, "饮水", "water"),
        SuggestionCandidate(10, "默认建议", "default"),
    ]
    cached = [
        {"key": "safety", "text": "严重读数", "polished": True},
        {"key": "recovery", "text": "恢复", "polished": True},
        {"key": "water", "text": "饮水", "polished": True},
        {"key": "default", "text": "默认建议", "polished": True},
        {
            "key": "synthesis",
            "text": "恢复和饮水怎么一起安排？",
            "priority": 80,
            "combines": ["recovery", "water"],
        },
    ]

    merged = _merge_cached_polish(cards, cached)

    assert len(merged) == len(cards)
    assert {item["key"] for item in merged} == {"safety", "recovery", "water", "synthesis"}


def test_cached_synthesis_never_replaces_one_of_its_source_chips():
    from app.api.agent import _merge_cached_polish
    from app.services.conversation_starters import SuggestionCandidate

    cards = [
        SuggestionCandidate(80, "代谢", "metabolic"),
        SuggestionCandidate(70, "饮食", "diet"),
        SuggestionCandidate(60, "目标", "goal"),
        SuggestionCandidate(10, "饮水", "water"),
    ]
    cached = [
        {"key": card.key, "text": card.text, "polished": True}
        for card in cards
    ] + [{
        "key": "synthesis",
        "text": "目标和饮水怎么一起安排？",
        "priority": 60,
        "combines": ["goal", "water"],
    }]

    merged = _merge_cached_polish(cards, cached)

    assert {item["key"] for item in merged} == {"metabolic", "diet", "goal", "water"}


def test_endpoint_flag_off_is_byte_identical_to_legacy(
    client, db, auth_user_and_headers, monkeypatch
):
    """Flag OFF → identical to legacy behavior. The only additive field is
    `polished` (Pydantic extra-safe for mobile). Legacy fields unchanged."""
    monkeypatch.setattr("app.config.settings.starter_llm_polish_enabled", False, raising=False)
    # If polish were (wrongly) invoked, this would blow up — proving no LLM path.
    monkeypatch.setattr(
        starter_polish,
        "read_cached_polish",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("polish must not run when flag off")),
    )

    user, headers = auth_user_and_headers
    _seed_exam(db, user)

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)
    assert r.status_code == 200
    payload = r.json()
    assert "opener" in payload
    for s in payload["suggestions"]:
        # legacy fields present + unchanged; polished additive and always False
        assert set(["text", "key", "priority", "polished"]).issubset(s.keys())
        assert s["polished"] is False
        assert isinstance(s["text"], str) and s["text"]


# ── 对抗评审复现 battery (2026-07-04 FIX-FIRST 五修) ─────────────────────
# 每条都是评审员在旧闸上实测放行的 exploit; 修复后必须全部 REJECT。

class TestAdversarialGateHardening:
    def test_substring_number_borrowing_rejected(self):
        # 源 165 → 输出 65; 源 AQI 210 → 输出 21 (exact-run 集合比对)
        assert _vp("心率 65 正常吗？", ["今晨静息心率 165 偏高"]) is False
        assert _vp("身体电量 21 怎么办？", ["本地 AQI 210 污染重"]) is False

    def test_exact_number_still_passes(self):
        assert _vp("AQI 21 空气很好，出门走走？", ["本地 空气质量很好（AQI 21）"]) is True

    def test_word_quantity_fabrication_rejected(self):
        assert _vp("训练量要不要加到两倍？", ["最近训练负荷偏高"]) is False
        assert _vp("补剂只吃三分之一行不行？", ["今天补剂还没打卡"]) is False
        assert _vp("要不要大量喝水？", ["今日饮水 4/8 杯"]) is False

    def test_cjk_qty_unit_fabrication_rejected(self):
        assert _vp("每天走三次怎么样？", ["今天适合户外运动"]) is False
        assert _vp("先停两天训练？", ["ACWR 训练负荷偏高"]) is False

    def test_cjk_qty_with_source_backing_passes(self):
        assert _vp("这周练三次够吗？", ["建议每周三次力量训练"]) is True

    def test_stop_drug_synonyms_rejected(self):
        assert _vp("要不要今天停掉降压药？", ["血压 165/100 偏高"]) is False
        assert _vp("要不要停用这个补剂？", ["今天补剂还没打卡"]) is False
        assert _vp("先断药观察一下？", ["用药依从性 90%"]) is False

    def test_risky_gap_words_rejected(self):
        assert _vp("明早空腹去测血糖好吗？", ["HBA1C 复查已超期"]) is False
        assert _vp("要不要试试断食？", ["今日热量缺口 300"]) is False
        assert _vp("要不要开始注射胰岛素？", ["血糖偏高"]) is False

    def test_directive_as_question_no_longer_exempt(self):
        # 祈使词不再被问号豁免
        assert _vp("是不是必须立刻改变饮食？", ["今日饮食记录 2 餐"]) is False

    def test_plain_rewrite_still_passes(self):
        assert _vp("昨晚睡得怎么样？", ["昨晚睡眠 7.2 小时"]) is True


class TestSynthesisCausalGuard:
    def _sources(self):
        return {
            "readiness": "恢复度 60 一般",
            "acwr": "ACWR 训练负荷偏高",
            "aqi": "本地 空气质量很好（AQI 21）",
            "water": "今日饮水 4/8 杯",
        }

    def _build(self, text, combines):
        from app.services.starter_polish import _build_synthesis_card
        item = {"key": "synthesis", "text": text, "combines": combines}
        return _build_synthesis_card(item, self._sources(), cards=[])

    def test_causal_connective_rejected(self):
        assert self._build("恢复度 60 是不是训练负荷导致的？", ["readiness", "acwr"]) is None
        assert self._build("负荷偏高引起恢复度下降吗？", ["readiness", "acwr"]) is None

    def test_parallel_statement_passes(self):
        card = self._build("AQI 21 空气好，饮水也补一补？", ["aqi", "water"])
        assert card is not None and card.synthesis is True

    def test_colloquial_qty_fast_follow_rejected(self):
        # 复审 round-2 残留: 俩/半/成/顿 同类量级词
        assert _vp("训练量翻俩倍怎么样？", ["ACWR 训练负荷偏高"]) is False
        assert _vp("要不要少睡半个小时？", ["昨晚睡眠 7.2 小时"]) is False
        assert _vp("训练量减三成合适吗？", ["ACWR 训练负荷偏高"]) is False
        assert _vp("每天少吃两顿行吗？", ["今日热量缺口 300"]) is False
