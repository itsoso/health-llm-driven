"""Conversation starters endpoint tests.

Goal: The new-chat empty state should show dynamic prompt chips derived from
recent user data (exams/workouts/supplements/sleep) with a safe default fallback.
"""

import random
from datetime import date, datetime, timedelta, timezone

import pytest


@pytest.fixture(autouse=True)
def _freeze_starters_clock(monkeypatch):
    """Freeze the module wall-clock to a weekday afternoon (Wed 2026-05-27 15:00).

    Endpoint tests go through `_collect_signals`, which reads the real clock to
    decide which time-of-day / weekday generators fire. On a weekend, or at certain
    hours, those add candidates beyond the 4 chip slots, and the endpoint's real
    `random.Random()` weighted sampling then drops an asserted data signal → flaky
    (this is why the suite went red on a Saturday). Freezing to a neutral weekday
    afternoon means no time/weekday generator fires, so endpoint pools are exactly
    the data signals and selection is deterministic. Direct generator tests pass
    `local_hour` explicitly and are unaffected by this.
    """
    import app.services.conversation_starters as cs

    _RealDT = cs.datetime

    class _FrozenDT(_RealDT):
        @classmethod
        def now(cls, tz=None):
            return _RealDT(2026, 5, 27, 15, 0, tzinfo=tz)

    monkeypatch.setattr(cs, "datetime", _FrozenDT)


DEFAULT_SUGGESTIONS = [
    "分析我最近的代谢健康",
    "今天怎么安排训练和恢复",
    "结合基因和体检给我建议",
    "帮我复盘最近的睡眠质量",
]


_EMPTY_SIGNALS_KWARGS = dict(
    latest_exam_date=None,
    latest_exam_abnormal_items=[],
    active_goal_title=None,
    active_goal_current_value=None,
    active_goal_target_value=None,
    active_goal_unit=None,
    water_today_ml=None,
    diet_records_today=None,
    latest_workout_type=None,
    latest_workout_distance_km=None,
    latest_workout_duration_min=None,
    latest_workout_avg_hr=None,
    top_gene_name=None,
    top_gene_genotype=None,
    top_gene_result=None,
    workouts_7d=0,
    active_supplements=0,
    supplement_completion_7d_pct=None,
    avg_sleep_score_7d=None,
    missing_hrv_days_7d=None,
)


def _make_signals(**overrides):
    from app.services.conversation_starters import StarterSignals

    return StarterSignals(**{**_EMPTY_SIGNALS_KWARGS, **overrides})


def test_endpoint_returns_onboarding_suggestions_for_zero_data_user(client, auth_user_and_headers):
    """Cold-start: a brand-new user with no data gets onboarding activation chips
    (connect device / log a meal / upload exam), NOT generic 'analyze my X' prompts
    they have no data for. Chips carry key='onboarding' for activation CTR tracking.

    C1 contract: the response also carries a top-level onboarding=True flag and a
    synthesized cold-start opener (see the dedicated cold-start tests below)."""
    from app.services.conversation_starters import ONBOARDING_SUGGESTIONS

    _, headers = auth_user_and_headers

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)

    assert r.status_code == 200
    payload = r.json()
    assert payload["onboarding"] is True
    assert payload["opener"] is not None  # synthesized cold-start opener
    assert [s["text"] for s in payload["suggestions"]] == ONBOARDING_SUGGESTIONS
    assert all(s["key"] == "onboarding" for s in payload["suggestions"])
    assert all("priority" in s for s in payload["suggestions"])


# ──────────────────────────────────────────────────────────────────────
# C1 cold-start pack — top-level `onboarding` flag + synthesized opener with
# action-bearing quick replies. (P0-3, 2026-07-05)
# ──────────────────────────────────────────────────────────────────────


def test_cold_start_endpoint_synthesizes_opener_with_three_action_quick_replies(
    client, auth_user_and_headers
):
    """Zero-data user → onboarding=True + non-empty opener whose quick_replies are
    exactly the 3 action chips (photo_meal / record_weight / connect_device)."""
    from app.services.conversation_opener import COLD_START_ACTIONS

    _, headers = auth_user_and_headers

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)
    assert r.status_code == 200
    payload = r.json()

    assert payload["onboarding"] is True
    opener = payload["opener"]
    assert opener is not None
    assert opener["source"] == "cold_start"
    assert isinstance(opener["text"], str) and opener["text"].strip()
    # 小巴 self-intro is present in the synthetic greeting.
    assert "小巴" in opener["text"]

    qrs = opener["quick_replies"]
    assert len(qrs) == 3
    assert all(isinstance(q, dict) for q in qrs)  # structured (label+action), not plain str
    assert [q["action"] for q in qrs] == list(COLD_START_ACTIONS)
    assert all(isinstance(q["label"], str) and q["label"].strip() for q in qrs)


def test_established_user_has_no_onboarding_flag_and_normal_opener_channel(
    client, db, auth_user_and_headers
):
    """A user with real data must NOT get onboarding=True and must NOT get the
    cold-start opener — the opener comes from the normal signal channel (here:
    none, since only a water record exists), and the flag is absent (not just
    False)."""
    from app.models.daily_health import WaterIntake

    user, headers = auth_user_and_headers
    db.add(WaterIntake(
        user_id=user.id,
        record_date=date.today(),
        intake_time=datetime.now(timezone.utc),
        amount_ml=300,
        drink_type="water",
    ))
    db.commit()

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)
    assert r.status_code == 200
    payload = r.json()

    # Additive flag: absent for established users (legacy clients unaffected).
    assert "onboarding" not in payload
    # No synthetic cold-start opener leaked onto an established user.
    if payload["opener"] is not None:
        assert payload["opener"]["source"] != "cold_start"
    # Established user still gets real data chips (water), not onboarding chips.
    assert all(s["key"] != "onboarding" for s in payload["suggestions"])


def test_cold_start_opener_quick_reply_labels_are_user_facing(client, auth_user_and_headers):
    """The three action chips read as human first-step invitations, matching the
    contract's user-view labels."""
    _, headers = auth_user_and_headers

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)
    qrs = {q["action"]: q["label"] for q in r.json()["opener"]["quick_replies"]}
    assert "饭" in qrs["photo_meal"]
    assert "体重" in qrs["record_weight"]
    assert "手表" in qrs["connect_device"] or "数据" in qrs["connect_device"]


def test_endpoint_includes_exam_hint_when_recent_exam_exists(client, db, auth_user_and_headers):
    from app.models.medical_exam import MedicalExam, MedicalExamItem

    user, headers = auth_user_and_headers

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
            reference_range="<3.4",
            result="偏高",
            is_abnormal="high",
            source="manual",
        )
    )
    db.commit()

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)

    assert r.status_code == 200
    payload = r.json()
    assert isinstance(payload["suggestions"], list)
    texts = [s["text"] for s in payload["suggestions"]]
    assert any("体检" in t for t in texts)
    assert any("LDL" in t for t in texts)
    # the exam card is attributed to the _suggest_exam generator
    assert any(s["key"] == "exam" for s in payload["suggestions"])


def test_endpoint_surfaces_overdue_lab_recheck_as_chip(client, db, auth_user_and_headers):
    """#4b 增量: chips 复用 push 侧的 _detect_lab_overdue —— 超期未复查的关键化验会作为
    "该复查" chip 出现 (chips↔push 双向统一: push 消费 chip 引擎, chip 消费 push 检测)。"""
    from app.models.medical_exam import MedicalExam, MedicalExamItem

    user, headers = auth_user_and_headers

    # LDL 复查间隔 180 天;200 天前的一次 → 已超期
    exam = MedicalExam(
        user_id=user.id,
        exam_date=date.today() - timedelta(days=200),
        exam_type="blood",
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)
    db.add(MedicalExamItem(
        exam_id=exam.id,
        category="lipid",
        item_name="LDL-C",
        item_code="LDL",
        value=4.0,
        unit="mmol/L",
        source="manual",
    ))
    db.commit()

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)

    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    texts = [s["text"] for s in suggestions]
    assert any("LDL" in t and "复查" in t for t in texts)
    assert any(s["key"] == "lab_recheck" for s in suggestions)


def test_endpoint_prioritizes_goal_water_and_diet_gaps(client, db, auth_user_and_headers, monkeypatch):
    from app.models.daily_health import WaterIntake
    from app.models.goal import Goal, GoalPeriod, GoalStatus, GoalType
    import app.services.conversation_starters as cs

    # This case asserts deterministic rule selection and its factual source text.
    # Cached LLM polish is covered separately and must not make this test depend
    # on whatever Redis contains from a prior run.
    monkeypatch.setattr("app.config.settings.starter_llm_polish_enabled", False, raising=False)

    # Freeze the module clock to a weekday afternoon (Wed 2026-05-27 15:00) so no
    # time-of-day / weekday generator fires. This user already has 3 data signals
    # (goal+water+diet); if a time generator added a 4th/5th, the pool would exceed
    # the 4 chip slots and the weighted-random selection (endpoint uses a real RNG)
    # could drop an asserted signal — that non-determinism made this test flaky.
    _RealDT = cs.datetime

    class _FrozenDT(_RealDT):
        @classmethod
        def now(cls, tz=None):
            return _RealDT(2026, 5, 27, 15, 0, tzinfo=tz)

    monkeypatch.setattr(cs, "datetime", _FrozenDT)

    user, headers = auth_user_and_headers
    today = date.today()

    db.add(Goal(
        user_id=user.id,
        goal_type=GoalType.WEIGHT,
        goal_period=GoalPeriod.MONTHLY,
        title="把体重降到 75kg",
        target_value=75,
        target_unit="kg",
        current_value=78,
        start_date=today - timedelta(days=10),
        status=GoalStatus.ACTIVE,
        priority=9,
    ))
    db.add(WaterIntake(
        user_id=user.id,
        record_date=today,
        intake_time=datetime.now(timezone.utc),
        amount_ml=300,
        drink_type="water",
    ))
    db.commit()

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)

    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert len(suggestions) == 4
    texts = [s["text"] for s in suggestions]
    assert any("把体重降到 75kg" in t for t in texts)
    assert any("饮水 300/2000ml" in t for t in texts)
    assert any("还没记录饮食" in t for t in texts)


def test_endpoint_includes_latest_workout_detail_and_gene_risk(
    client, db, auth_user_and_headers, monkeypatch
):
    from app.models.daily_health import WorkoutRecord
    from app.models.genetic_data import GeneticProfile, GeneticVariant

    user, headers = auth_user_and_headers
    # Assert deterministic signal selection, not wording from a Redis polish cache.
    monkeypatch.setattr("app.config.settings.starter_llm_polish_enabled", False, raising=False)
    today = date.today()

    db.add(WorkoutRecord(
        user_id=user.id,
        workout_date=today,
        workout_type="running",
        workout_name="晨跑",
        duration_seconds=1800,
        distance_meters=5200,
        avg_heart_rate=145,
        training_load=88,
        source="garmin",
    ))
    profile = GeneticProfile(
        user_id=user.id,
        test_provider="WeGene",
        test_date=today - timedelta(days=20),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    db.add(GeneticVariant(
        user_id=user.id,
        profile_id=profile.id,
        rsid="rs1801133",
        category="nutrition",
        gene_name="MTHFR",
        genotype="TT",
        result_label="叶酸代谢关注",
        risk_level="high",
        variant_nature="risk",
    ))
    db.commit()

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)

    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    texts = [s["text"] for s in suggestions]
    assert any("最近一次跑步" in t and "5.2km" in t for t in texts)
    assert any("MTHFR TT" in t for t in texts)


# ──────────────────────────────────────────────────────────────────────
# Twin-driven (today body state + environment) — unit tests on the pure
# selection layer so we don't have to seed half a dozen Garmin/Weather
# rows. Twin overlay is wired in `_collect_signals` and proven by
# `test_endpoint_surfaces_low_readiness_from_garmin` below.
# ──────────────────────────────────────────────────────────────────────


def test_low_readiness_generates_critical_prompt_and_is_always_selected():
    from app.services.conversation_starters import (
        _build_candidates,
        _select,
    )

    signals = _make_signals(readiness_score=32)
    candidates = _build_candidates(signals)
    # The low-readiness candidate should be present and critical (>=100).
    assert any("恢复评分 32" in c.text and c.priority >= 100 for c in candidates)

    # Critical candidate must always survive selection, even with many competitors.
    rng = random.Random(0)
    out = _select(candidates, limit=4, rng=rng)
    assert any("恢复评分 32" in s for s in out)


def test_high_aqi_and_acwr_danger_both_surface_critical():
    from app.services.conversation_starters import _build_candidates, _select

    signals = _make_signals(aqi=180, city="杭州", acwr_zone="danger")
    candidates = _build_candidates(signals)
    out = _select(candidates, limit=4, rng=random.Random(7))
    assert any("AQI 180" in s for s in out)
    assert any("训练负荷进入风险区" in s for s in out)


def test_weather_rain_and_uv_extreme_become_suggestions():
    from app.services.conversation_starters import _build_candidates, _select

    signals = _make_signals(
        temperature_c=22,
        weather_description="雷阵雨",
        uv_index=9,
        city="上海",
    )
    out = _select(_build_candidates(signals), limit=4, rng=random.Random(1))
    assert any("雷阵雨" in s and "室内训练" in s for s in out)
    assert any("UV指数 9" in s for s in out)


def test_acute_illness_suppresses_training_and_marked_critical():
    from app.services.conversation_starters import _build_candidates, _select

    signals = _make_signals(
        should_rest_from_training=True,
        illness_names=["发热"],
    )
    candidates = _build_candidates(signals)
    assert any(c.priority >= 100 and "发热" in c.text for c in candidates)
    out = _select(candidates, limit=4, rng=random.Random(0))
    assert any("发热" in s and "休息" in s for s in out)


def test_acute_illness_dedupes_repeated_names():
    """修 founder 截图 '我有鼻炎发作、鼻炎发作症状': 重复病症名去重。"""
    from app.services.conversation_starters import _build_candidates

    signals = _make_signals(
        should_rest_from_training=True,
        illness_names=["鼻炎发作", "鼻炎发作"],
    )
    cands = [c for c in _build_candidates(signals) if "休息和恢复" in c.text]
    assert cands
    text = cands[0].text
    # 去重: 只出现一次
    assert text.count("鼻炎发作") == 1
    # 已带"发作"结尾 → 不再补"症状" (避免"发作症状"结巴)
    assert "发作症状" not in text
    assert text == "我有鼻炎发作，今天该怎么休息和恢复？"


def test_acute_illness_dedupes_tokens_inside_single_name():
    """单个 name 里含 顿号/逗号 分隔的重复值也去重。"""
    from app.services.conversation_starters import _build_candidates

    signals = _make_signals(
        should_rest_from_training=True,
        illness_names=["鼻炎发作、鼻炎发作"],
    )
    cands = [c for c in _build_candidates(signals) if "休息和恢复" in c.text]
    assert cands
    assert cands[0].text == "我有鼻炎发作，今天该怎么休息和恢复？"


def test_acute_illness_plain_name_still_gets_symptom_suffix():
    """普通病症名 (不带发作/症状) 仍拼'症状' — 保持原措辞契约。"""
    from app.services.conversation_starters import _build_candidates

    signals = _make_signals(should_rest_from_training=True, illness_names=["发热"])
    cands = [c for c in _build_candidates(signals) if "休息和恢复" in c.text]
    assert cands
    assert cands[0].text == "我有发热症状，今天该怎么休息和恢复？"


def test_acute_illness_two_distinct_names_joined():
    """不同病症名保序取前 2, 顿号连接。"""
    from app.services.conversation_starters import _format_illness_phrase

    assert _format_illness_phrase(["感冒", "发烧", "咳嗽"]) == "感冒、发烧"
    assert _format_illness_phrase(["感冒", "感冒", "发烧"]) == "感冒、发烧"


def test_acute_illness_name_ending_in_symptom_no_stutter():
    """name 已以'症状'结尾 → 不再补'症状'。"""
    from app.services.conversation_starters import _build_candidates

    signals = _make_signals(
        should_rest_from_training=True, illness_names=["过敏症状"]
    )
    cands = [c for c in _build_candidates(signals) if "休息和恢复" in c.text]
    assert cands
    assert cands[0].text == "我有过敏症状，今天该怎么休息和恢复？"


def test_bp_severe_reading_is_urgent_and_stage2_is_not_labeled_critical():
    from app.services.conversation_starters import _build_candidates

    severe = _build_candidates(_make_signals(systolic_bp=185, diastolic_bp=115))
    assert any(c.priority >= 100 and "185/115" in c.text and "复测" in c.text for c in severe)

    stage2 = _build_candidates(_make_signals(systolic_bp=165, diastolic_bp=102))
    assert any(c.priority < 100 and "165/102" in c.text for c in stage2)

    norm = _build_candidates(_make_signals(systolic_bp=118, diastolic_bp=76))
    bp_cands = [c for c in norm if "血压" in c.text]
    assert bp_cands and all(c.priority < 100 for c in bp_cands)


def test_default_fallbacks_fill_remaining_slots():
    from app.services.conversation_starters import (
        _build_candidates,
        _select,
    )

    # Only one personalized candidate → defaults must fill the other 3 slots.
    signals = _make_signals(active_goal_title="减重")
    out = _select(_build_candidates(signals), limit=4, rng=random.Random(0))
    assert len(out) == 4
    assert any("减重" in s for s in out)
    # At least 2 of the 4 should be DEFAULT_SUGGESTIONS.
    assert sum(1 for s in out if s in DEFAULT_SUGGESTIONS) >= 2


def test_selection_is_per_request_random_for_non_critical():
    """When there are >4 non-critical candidates, two RNG seeds should yield
    different selections (per-visit variety)."""
    from app.services.conversation_starters import _build_candidates, _select

    # Build a rich, all-non-critical signal set.
    signals = _make_signals(
        latest_exam_date=date.today(),
        latest_exam_abnormal_items=["LDL-C"],
        active_goal_title="把体重降到 75kg",
        active_goal_current_value=78,
        active_goal_target_value=75,
        active_goal_unit="kg",
        water_today_ml=500,
        diet_records_today=0,
        latest_workout_type="cycling",
        latest_workout_distance_km=20.0,
        latest_workout_duration_min=60,
        workouts_7d=3,
        top_gene_name="APOE",
        top_gene_genotype="ε3/ε4",
        top_gene_result="心血管关注",
        active_supplements=2,
        supplement_completion_7d_pct=85.0,
        avg_sleep_score_7d=82,
        readiness_score=70,
        body_battery=85,
        aqi=40,
        city="杭州",
        uv_index=6.5,
    )
    cands = _build_candidates(signals)
    assert len(cands) >= 6  # enough room for variety

    seen = set()
    for seed in range(20):
        out = tuple(_select(cands, limit=4, rng=random.Random(seed)))
        seen.add(out)
    # Across 20 seeds, at least 3 distinct orderings emerge.
    assert len(seen) >= 3


def test_collect_signals_overlays_twin_today_state(db, auth_user_and_headers):
    """Direct check: when Twin returns today's body state, _collect_signals
    surfaces it on StarterSignals. Proves the Twin → StarterSignals wiring."""
    from unittest.mock import patch
    from app.services.conversation_starters import (
        _build_candidates,
        _collect_signals,
        _select,
    )
    from app.twin.schema import (
        BehavioralState,
        EnvironmentalState,
        HealthTwin,
        LabsContext,
        PhysiologicalState,
        TwinMeta,
    )

    user, _ = auth_user_and_headers
    fake_twin = HealthTwin(
        meta=TwinMeta(user_id=user.id, generated_at=datetime.now(timezone.utc)),
        physiological=PhysiologicalState(
            training_readiness_score=32,
            training_readiness_level="poor",
            body_battery_current=25,
            stress_level_current=72,
        ),
        labs=LabsContext(blood_pressure_systolic=165, blood_pressure_diastolic=102),
        behavioral=BehavioralState(acwr_zone="danger"),
        environment=EnvironmentalState(city="杭州", aqi=180, aqi_level="unhealthy"),
    )

    with patch("app.twin.builder.build_twin", return_value=fake_twin):
        signals = _collect_signals(db, user.id)

    assert signals.readiness_score == 32
    assert signals.body_battery == 25
    assert signals.stress_today == 72
    assert signals.systolic_bp == 165
    assert signals.acwr_zone == "danger"
    assert signals.aqi == 180
    assert signals.city == "杭州"

    candidates = _build_candidates(signals)
    out = _select(candidates, limit=4, rng=random.Random(0))
    assert any("恢复评分 32" in s for s in out)


# ──────────────────────────────────────────────────────────────────────
# Time-of-day / weekday generators — pure-function checks. Gated behind
# _has_any_user_signal so they don't trigger for brand-new users.
# ──────────────────────────────────────────────────────────────────────


def test_morning_prompt_includes_last_night_sleep_when_available():
    from app.services.conversation_starters import _suggest_morning

    sig = _make_signals(local_hour=8, sleep_score_today=82)
    cand = _suggest_morning(sig)
    assert cand is not None
    assert "睡眠分 82" in cand.text


def test_morning_prompt_skipped_outside_window():
    from app.services.conversation_starters import _suggest_morning

    sig = _make_signals(local_hour=14, sleep_score_today=82)
    assert _suggest_morning(sig) is None


def test_time_prompts_gated_on_empty_user():
    """A brand-new user with literally no data should still get DEFAULT_SUGGESTIONS,
    not generic time-of-day prompts."""
    from app.services.conversation_starters import (
        _suggest_evening,
        _suggest_morning,
        _suggest_noon,
        _suggest_week_rhythm,
    )

    # Empty user at any time of day — gate suppresses all time prompts.
    for hour in (8, 12, 21, 2):
        sig = _make_signals(local_hour=hour, local_weekday=2, is_weekend=False)
        assert _suggest_morning(sig) is None
        assert _suggest_noon(sig) is None
        assert _suggest_evening(sig) is None
        assert _suggest_week_rhythm(sig) is None


def test_sunday_evening_surfaces_week_planning():
    from app.services.conversation_starters import _suggest_week_rhythm

    sig = _make_signals(
        local_hour=20,
        local_weekday=6,
        is_weekend=True,
        active_goal_title="减重",  # satisfies has_any_user_signal gate
    )
    cand = _suggest_week_rhythm(sig)
    assert cand is not None
    assert "下一周" in cand.text


def test_noon_prompt_adapts_to_diet_records():
    from app.services.conversation_starters import _suggest_noon

    # Already logged something → "怎么补"
    sig_with = _make_signals(local_hour=12, diet_records_today=2, active_goal_title="减重")
    cand = _suggest_noon(sig_with)
    assert cand is not None and "已经吃" in cand.text

    # Nothing logged → "吃点什么"
    sig_without = _make_signals(local_hour=12, diet_records_today=0, active_goal_title="减重")
    cand2 = _suggest_noon(sig_without)
    assert cand2 is not None and "午餐吃点什么" in cand2.text


# ──────────────────────────────────────────────────────────────────────
# Analytics attribution — each card carries a stable generator `key` so the
# client can compute CTR per generator. (Phase 5, 2026-05-29)
# ──────────────────────────────────────────────────────────────────────


def test_cards_carry_generator_key_derived_from_function_name():
    from app.services.conversation_starters import (
        _build_candidates,
        compute_conversation_suggestion_cards,  # noqa: F401  (import smoke)
    )

    # readiness + aqi → keys "readiness" and "aqi" (function name minus _suggest_)
    signals = _make_signals(readiness_score=32, aqi=180, city="杭州")
    cards = _build_candidates(signals)
    keys = {c.key for c in cards}
    assert "readiness" in keys
    assert "aqi" in keys
    # every candidate has a non-empty key
    assert all(c.key for c in cards)


def test_default_cards_use_default_key():
    from app.services.conversation_starters import _default_cards

    cards = _default_cards(4)
    assert len(cards) == 4
    assert all(c.key == "default" for c in cards)


def test_endpoint_returns_structured_cards_with_key_and_priority(client, db, auth_user_and_headers):
    from app.models.daily_health import WaterIntake

    user, headers = auth_user_and_headers
    db.add(WaterIntake(
        user_id=user.id,
        record_date=date.today(),
        intake_time=datetime.now(timezone.utc),
        amount_ml=300,
        drink_type="water",
    ))
    db.commit()

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)
    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert suggestions and isinstance(suggestions[0], dict)
    for s in suggestions:
        # Legacy fields are the stable mobile contract; `polished` is an additive
        # field from the starter-polish overlay (bool), extra-safe for clients.
        assert {"text", "key", "priority"}.issubset(s.keys())
        assert isinstance(s["text"], str) and s["text"]
        assert isinstance(s["key"], str) and s["key"]
        assert isinstance(s["priority"], int)
        assert isinstance(s["polished"], bool)
    # the water card is attributed to _suggest_water
    assert any(s["key"] == "water" for s in suggestions)


def test_collect_signals_populates_local_time_fields(db, auth_user_and_headers):
    """The Asia/Shanghai time context is always populated, independent of Twin."""
    from app.services.conversation_starters import _collect_signals

    user, _ = auth_user_and_headers
    signals = _collect_signals(db, user.id)
    assert signals.local_hour is not None and 0 <= signals.local_hour <= 23
    assert signals.local_weekday is not None and 0 <= signals.local_weekday <= 6
    assert isinstance(signals.is_weekend, bool)


# ──────────────────────────────────────────────────────────────────────
# Registered chronic problems (HealthProblem · R13) — grounded chips for a
# data-rich user whose chronic conditions previously never surfaced unless
# acutely flaring. (2026-07 grounding-reliability improvement)
# ──────────────────────────────────────────────────────────────────────


def test_registered_problem_surfaces_management_chip():
    """A registered chronic problem with no imminent follow-up still opens a
    grounded management thread (previously: nothing → generic template)."""
    from app.services.conversation_starters import _build_candidates

    sig = _make_signals(top_problem_name="鼻炎", top_problem_risk_level="P2")
    cands = _build_candidates(sig)
    problem_cards = [c for c in cands if c.key == "health_problem"]
    assert problem_cards
    assert "鼻炎" in problem_cards[0].text


def test_problem_name_parenthetical_is_stripped_in_chip():
    from app.services.conversation_starters import _build_candidates

    sig = _make_signals(top_problem_name="胃溃疡(Hp 阴性,胃窦后壁)", top_problem_risk_level="P1")
    cands = _build_candidates(sig)
    card = next(c for c in cands if c.key == "health_problem")
    assert "胃溃疡" in card.text
    assert "(Hp" not in card.text


def test_overdue_problem_followup_chip_is_actionable():
    from app.services.conversation_starters import _build_candidates

    sig = _make_signals(
        problem_followup_name="甲状腺结节(TI-RADS 3)",
        problem_followup_overdue=True,
        problem_followup_risk_level="P1",
        problem_followup_what_to_check="甲状腺超声",
    )
    cands = _build_candidates(sig)
    fu = [c for c in cands if c.key == "problem_followup"]
    assert fu
    assert "甲状腺结节" in fu[0].text
    assert "复查" in fu[0].text and "到期" in fu[0].text
    # P1 overdue → high (but non-critical) priority so it reliably surfaces.
    assert fu[0].priority >= 80


def test_problem_followup_and_management_chip_do_not_duplicate_same_problem():
    """When a problem has a due follow-up, only the (more actionable) follow-up
    chip appears — not two chips about the same condition."""
    from app.services.conversation_starters import _build_candidates

    sig = _make_signals(
        top_problem_name="胃溃疡(Hp 阴性)",
        top_problem_risk_level="P1",
        problem_followup_name="胃溃疡(Hp 阴性)",
        problem_followup_overdue=True,
        problem_followup_risk_level="P1",
    )
    cands = _build_candidates(sig)
    keys = [c.key for c in cands]
    assert "problem_followup" in keys
    assert "health_problem" not in keys  # ceded to the follow-up chip


def test_registered_problem_makes_user_not_cold_start():
    """A user with only a registered chronic problem is NOT cold-start — they get
    grounded chips, never onboarding activation chips."""
    from app.services.conversation_starters import _has_any_user_signal

    sig = _make_signals(top_problem_name="鼻炎", top_problem_risk_level="P2")
    assert _has_any_user_signal(sig) is True


def test_endpoint_surfaces_registered_problem_for_data_rich_user(client, db, auth_user_and_headers):
    """End-to-end: a seeded user with a registered health problem sees a grounded
    chip about it (not the generic default template)."""
    from app.models.health_problem import HealthProblem

    user, headers = auth_user_and_headers
    db.add(HealthProblem(
        user_id=user.id, name="过敏性鼻炎", risk_level="P2", status="active",
    ))
    db.commit()

    r = client.get("/api/v1/agent/conversation-starters", headers=headers)
    assert r.status_code == 200
    payload = r.json()
    assert "onboarding" not in payload  # not treated as cold-start
    texts = [s["text"] for s in payload["suggestions"]]
    assert any("鼻炎" in t for t in texts)


# ──────────────────────────────────────────────────────────────────────
# Diversity — the 4 served chips should span distinct themes, not 4 variations
# of one (e.g. all recovery/training). (2026-07 value/diversity improvement)
# ──────────────────────────────────────────────────────────────────────


def test_served_chips_are_diverse_across_themes():
    from app.services.conversation_starters import (
        _build_candidates,
        _category_of,
        _select_cards,
    )

    # A recovery-heavy day: readiness + hrv + body-battery all fire (recovery),
    # plus a lab recheck, a registered problem, and an environment signal.
    sig = _make_signals(
        readiness_score=55,           # recovery
        hrv_today=30, hrv_7d_avg_twin=42,   # recovery (low → fires)
        body_battery=25,              # recovery
        overdue_lab_name="LDL",       # labs
        top_problem_name="鼻炎", top_problem_risk_level="P2",  # chronic
        aqi=40, city="杭州",           # environment
    )
    cands = _build_candidates(sig)
    # Must have enough recovery candidates to prove the guard matters.
    recovery = [c for c in cands if _category_of(c) == "recovery"]
    assert len(recovery) >= 2

    # Across many seeds, the served set should reliably span >=3 distinct themes.
    import random as _r
    max_themes = 0
    for seed in range(20):
        out = _select_cards(cands, limit=4, rng=_r.Random(seed))
        themes = {_category_of(c) for c in out}
        max_themes = max(max_themes, len(themes))
        # No single visit should be 4-of-the-same-theme when >=3 themes exist.
        assert len(themes) >= 2
    assert max_themes >= 3


def test_diversity_relaxes_when_only_one_theme_available():
    """If the user genuinely only has recovery signals, we still fill 4 slots
    (diversity is a preference, not a hard cap that starves the list)."""
    from app.services.conversation_starters import _build_candidates, _select_cards
    import random as _r

    sig = _make_signals(
        readiness_score=55,
        hrv_today=30, hrv_7d_avg_twin=42,
        body_battery=25,
    )
    cands = _build_candidates(sig)
    out = _select_cards(cands, limit=4, rng=_r.Random(0))
    assert len(out) == 4  # defaults backfill; never starved
