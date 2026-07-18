"""ActionCard outcome grading tests."""
from datetime import datetime, timedelta, timezone, date

from app.tasks.outcome_grader import _parse_numeric, _parse_direction, _grade


class TestParseNumeric:
    def test_plain(self):
        assert _parse_numeric("82.5") == 82.5

    def test_with_unit(self):
        assert _parse_numeric("82kg") == 82.0
        assert _parse_numeric("3.5 mmol/L") == 3.5

    def test_with_prefix(self):
        assert _parse_numeric("<35") == 35.0
        assert _parse_numeric(">90") == 90.0

    def test_blood_pressure(self):
        # "120/80" → 取首数, systolic
        assert _parse_numeric("120/80") == 120.0

    def test_none(self):
        assert _parse_numeric(None) is None
        assert _parse_numeric("") is None
        assert _parse_numeric("abc") is None


class TestParseDirection:
    def test_greater(self):
        assert _parse_direction(">90") == ">"
        assert _parse_direction("≥7000") == ">"
        assert _parse_direction("提高 HRV") == ">"

    def test_less(self):
        assert _parse_direction("<35") == "<"
        assert _parse_direction("减重到 80kg") == "<"
        assert _parse_direction("降低 LDL") == "<"

    def test_equal(self):
        assert _parse_direction("80kg") == "="
        assert _parse_direction(None) == "="


class TestGrade:
    def test_full_progress(self):
        # baseline=82, target=78, actual=78 (达成)
        score, note = _grade(82, 78, 78, "<")
        assert score == 100

    def test_overshot(self):
        # actual 比 target 还更进一步
        score, note = _grade(82, 78, 76, "<")
        assert score == 100

    def test_partial_progress(self):
        # 走了一半
        score, note = _grade(82, 78, 80, "<")
        # progress = (80-82)/(78-82) = 0.5 → 60 分档
        assert 50 <= score <= 70

    def test_no_movement(self):
        score, note = _grade(82, 78, 82, "<")
        assert score == 25
        assert "原地踏步" in note

    def test_reverse_direction(self):
        # 想减重却胖了
        score, note = _grade(82, 78, 84, "<")
        assert score < 30
        assert "反向" in note

    def test_missing_actual(self):
        score, note = _grade(82, 78, None, "<")
        assert score == 0
        assert "缺失" in note

    def test_no_baseline_direction_only(self):
        # 没起点, 只看方向
        score, note = _grade(None, 35, 28, "<")
        assert score == 100  # actual <= target

        score, note = _grade(None, 35, 40, "<")
        assert score == 30  # actual > target


class TestGradeFlow:
    """端到端: ActionCard 创建 → 数据写入 → 评分."""

    def test_grades_due_card_with_actual_data(self, db):
        """到期 + 有数据 → 评分."""
        from app.models.action_card import ActionCard
        from app.models.weight import WeightRecord
        from app.tasks.outcome_grader import _grade_loop

        now = datetime.now(timezone.utc)
        db.add(WeightRecord(user_id=7, record_date=date.today() - timedelta(days=30), weight=82.0))
        db.add(WeightRecord(user_id=7, record_date=date.today(), weight=80.0))

        card = ActionCard(
            user_id=7,
            title="减重 4kg",
            content="...",
            card_type="plan",
            metric_key="weight",
            baseline_value="82",
            target_value="78",
            creator_specialist="fuel_strategist",
            check_back_date=now - timedelta(hours=1),
        )
        db.add(card)
        db.commit()

        result = _grade_loop(db, now)
        assert result["graded"] >= 1

        db.refresh(card)
        assert card.graded_at is not None
        assert card.actual_value == "80"
        assert 50 <= card.accuracy_score <= 70

    def test_postpones_when_no_data(self, db):
        from app.models.action_card import ActionCard
        from app.tasks.outcome_grader import _grade_loop

        now = datetime.now(timezone.utc)
        card = ActionCard(
            user_id=999,
            title="测试",
            content="...",
            metric_key="weight",
            baseline_value="80",
            target_value="75",
            creator_specialist="fuel_strategist",
            check_back_date=now - timedelta(hours=1),
        )
        db.add(card)
        db.commit()

        original_check_back = card.check_back_date
        result = _grade_loop(db, now)
        assert result["skipped_no_data"] >= 1

        db.refresh(card)
        assert card.graded_at is None
        assert card.check_back_date > original_check_back

    def test_clinician_gated_metric_is_recorded_but_not_scored_as_efficacy(self, db):
        from app.models.action_card import ActionCard
        from app.tasks.outcome_grader import grade_single_card

        now = datetime.now(timezone.utc)
        card = ActionCard(
            user_id=7,
            title="降低 LDL",
            content="...",
            metric_key="ldl",
            baseline_value="3.5",
            target_value="<3.0",
            creator_specialist="fuel_strategist",
            check_back_date=now - timedelta(hours=1),
        )
        db.add(card)
        db.commit()

        result = grade_single_card(db, card, now)

        assert result["status"] == "clinician_review"
        assert result["pushed"] is False
        assert card.accuracy_score is None
        assert card.outcome == "inconclusive"
        assert "混杂" in card.grading_notes


class TestP0Fixes:
    """P0 bugs: timezone / stale data floor / BP dual-value."""

    def test_stale_weight_not_used(self, db):
        """体重超过 14 天 max_age → 视为缺失, 不应拿来评分."""
        from app.models.action_card import ActionCard
        from app.models.weight import WeightRecord
        from app.tasks.outcome_grader import _grade_loop

        now = datetime.now(timezone.utc)
        # 30 天前的唯一一条数据
        db.add(WeightRecord(
            user_id=11, record_date=date.today() - timedelta(days=30), weight=82.0,
        ))

        card = ActionCard(
            user_id=11, title="减重", content="...", card_type="plan",
            metric_key="weight", baseline_value="82", target_value="78",
            creator_specialist="fuel_strategist",
            check_back_date=now - timedelta(hours=1),
        )
        db.add(card)
        db.commit()

        result = _grade_loop(db, now)
        assert result["skipped_no_data"] >= 1

        db.refresh(card)
        assert card.graded_at is None, "陈旧数据不应被评分"
        assert "weight 无 14 天内" in (card.grading_notes or "")

    def test_fresh_weight_used(self, db):
        """14 天内有数据 → 正常评分."""
        from app.models.action_card import ActionCard
        from app.models.weight import WeightRecord
        from app.tasks.outcome_grader import _grade_loop

        now = datetime.now(timezone.utc)
        db.add(WeightRecord(
            user_id=12, record_date=date.today() - timedelta(days=5), weight=80.0,
        ))

        card = ActionCard(
            user_id=12, title="减重", content="...", card_type="plan",
            metric_key="weight", baseline_value="82", target_value="78",
            creator_specialist="fuel_strategist",
            check_back_date=now - timedelta(hours=1),
        )
        db.add(card)
        db.commit()

        result = _grade_loop(db, now)
        assert result["graded"] >= 1

        db.refresh(card)
        assert card.graded_at is not None
        assert card.actual_value == "80"

    def test_bp_dual_grading_requires_clinician_review(self, db):
        """血压受临床管理混杂：保留读数，但不生成 Agent 有效性评分。"""
        from app.models.action_card import ActionCard
        from app.models.basic_health import BasicHealthData
        from app.tasks.outcome_grader import _grade_loop

        now = datetime.now(timezone.utc)
        db.add(BasicHealthData(
            user_id=13, record_date=date.today() - timedelta(days=2),
            systolic_bp=120, diastolic_bp=100,  # systolic 达标, diastolic 反向涨
        ))

        card = ActionCard(
            user_id=13, title="降压", content="...", card_type="plan",
            metric_key="bp",
            baseline_value="140/90",  # dual baseline
            target_value="120/80",    # dual target
            creator_specialist="hypertension_specialist",
            check_back_date=now - timedelta(hours=1),
        )
        db.add(card)
        db.commit()

        result = _grade_loop(db, now)
        assert result["graded"] >= 1

        db.refresh(card)
        assert card.actual_value == "120"
        assert card.accuracy_score is None
        assert card.outcome == "inconclusive"
        assert "混杂" in (card.grading_notes or "")

    def test_bp_single_value_requires_clinician_review(self, db):
        """单项收缩压同样不能变成 Agent 命中率。"""
        from app.models.action_card import ActionCard
        from app.models.basic_health import BasicHealthData
        from app.tasks.outcome_grader import _grade_loop

        now = datetime.now(timezone.utc)
        db.add(BasicHealthData(
            user_id=14, record_date=date.today() - timedelta(days=1),
            systolic_bp=125, diastolic_bp=82,
        ))

        card = ActionCard(
            user_id=14, title="降压", content="...", card_type="plan",
            metric_key="systolic_bp",  # 显式收缩压
            baseline_value="140",
            target_value="<130",
            creator_specialist="hypertension_specialist",
            check_back_date=now - timedelta(hours=1),
        )
        db.add(card)
        db.commit()

        result = _grade_loop(db, now)
        assert result["graded"] >= 1

        db.refresh(card)
        assert card.actual_value == "125"
        assert card.accuracy_score is None
        assert card.outcome == "inconclusive"
        assert "混杂" in (card.grading_notes or "")

    def test_timezone_shanghai_date_used(self, db):
        """边界: UTC 23:30 (= Shanghai 07:30 次日).
        今天早上 Shanghai 07:00 记的体重, UTC 日期还停在昨天. 应能被找到."""
        from app.models.action_card import ActionCard
        from app.models.weight import WeightRecord
        from app.tasks.outcome_grader import _grade_loop
        from zoneinfo import ZoneInfo

        # Shanghai 07:30 = UTC 23:30 of previous day
        shanghai_now = datetime(2026, 4, 28, 7, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        utc_now = shanghai_now.astimezone(timezone.utc)
        shanghai_today = shanghai_now.date()

        db.add(WeightRecord(user_id=15, record_date=shanghai_today, weight=80.0))

        card = ActionCard(
            user_id=15, title="减重", content="...", card_type="plan",
            metric_key="weight", baseline_value="82", target_value="78",
            creator_specialist="fuel_strategist",
            check_back_date=utc_now - timedelta(hours=1),
        )
        db.add(card)
        db.commit()

        # 用 UTC 的 utc_now 跑 grader, 应能命中 Shanghai 今天的数据
        result = _grade_loop(db, utc_now)
        assert result["graded"] >= 1

        db.refresh(card)
        assert card.actual_value == "80"


class TestAdherence:
    """Adherence 信号接入 final score 公式."""

    def test_default_no_adherence_no_score_change(self, db):
        """历史卡 adherence_confidence=None → raw_score 不改."""
        from app.models.action_card import ActionCard
        from app.models.weight import WeightRecord
        from app.tasks.outcome_grader import _grade_loop

        now = datetime.now(timezone.utc)
        db.add(WeightRecord(user_id=21, record_date=date.today(), weight=78.0))

        card = ActionCard(
            user_id=21, title="减重", content="...", card_type="plan",
            metric_key="weight", baseline_value="82", target_value="78",
            creator_specialist="fuel_strategist",
            check_back_date=now - timedelta(hours=1),
            # 不设 adherence
        )
        db.add(card)
        db.commit()

        _grade_loop(db, now)
        db.refresh(card)
        # 完全达成, raw=100, 无 adherence 调整, final=100
        assert card.accuracy_score == 100

    def test_low_adherence_cuts_score(self, db):
        """用户没做, confidence=20 → 100 × 0.2 = 20 分."""
        from app.models.action_card import ActionCard
        from app.models.weight import WeightRecord
        from app.tasks.outcome_grader import _grade_loop

        now = datetime.now(timezone.utc)
        db.add(WeightRecord(user_id=22, record_date=date.today(), weight=78.0))

        card = ActionCard(
            user_id=22, title="减重", content="...", card_type="plan",
            metric_key="weight", baseline_value="82", target_value="78",
            creator_specialist="fuel_strategist",
            check_back_date=now - timedelta(hours=1),
            adherence_kind="self_reported",
            adherence_confidence=20,
        )
        db.add(card)
        db.commit()

        _grade_loop(db, now)
        db.refresh(card)
        # raw=100, adh=20% → 20
        assert card.accuracy_score == 20
        assert "adherence=self_reported 20%" in (card.grading_notes or "")

    def test_checklist_fallback_half_done(self, db):
        """没显式 adherence 但 checklist 勾了 50% → self_reported 25 (50% × 50 上限)."""
        from app.models.action_card import ActionCard
        from app.models.weight import WeightRecord
        from app.tasks.outcome_grader import _grade_loop

        now = datetime.now(timezone.utc)
        db.add(WeightRecord(user_id=23, record_date=date.today(), weight=78.0))

        card = ActionCard(
            user_id=23, title="减重", content="...", card_type="plan",
            metric_key="weight", baseline_value="82", target_value="78",
            creator_specialist="fuel_strategist",
            check_back_date=now - timedelta(hours=1),
            checklist=[
                {"item": "a", "done": True},
                {"item": "b", "done": False},
            ],
        )
        db.add(card)
        db.commit()

        _grade_loop(db, now)
        db.refresh(card)
        # raw=100, checklist 50% → confidence=25, final=25
        assert card.accuracy_score == 25
        assert "self_reported" in (card.grading_notes or "")

    def test_device_adherence_high_confidence(self, db):
        """设备证实的 adherence (90%) 应接近 raw score."""
        from app.models.action_card import ActionCard
        from app.models.weight import WeightRecord
        from app.tasks.outcome_grader import _grade_loop

        now = datetime.now(timezone.utc)
        db.add(WeightRecord(user_id=24, record_date=date.today(), weight=78.0))

        card = ActionCard(
            user_id=24, title="减重", content="...", card_type="plan",
            metric_key="weight", baseline_value="82", target_value="78",
            creator_specialist="fuel_strategist",
            check_back_date=now - timedelta(hours=1),
            adherence_kind="device",
            adherence_confidence=90,
        )
        db.add(card)
        db.commit()

        _grade_loop(db, now)
        db.refresh(card)
        # raw=100, adh=90 → 90
        assert card.accuracy_score == 90
        assert "adherence=device 90%" in (card.grading_notes or "")



# ============================================================
# Prediction hit push (Agent Native: AI 主动汇报命中)
# ============================================================

class TestHitPush:
    """评分到 hit (>=70) 时, outcome_grader 应主动推 APNs."""

    def test_hit_triggers_push(self, db):
        """命中卡 (score 100) 应调 PushService.send_notification 一次."""
        from datetime import date as date_type
        from unittest.mock import AsyncMock, patch

        from app.models.action_card import ActionCard
        from app.models.weight import WeightRecord
        from app.tasks.outcome_grader import _grade_loop

        now = datetime.now(timezone.utc)
        db.add(WeightRecord(user_id=101, record_date=date_type.today(), weight=78.0))

        card = ActionCard(
            user_id=101, title="减重 4kg", content="...", card_type="plan",
            metric_key="weight", baseline_value="82", target_value="78",
            creator_specialist="fuel_strategist",
            check_back_date=now - timedelta(hours=1),
            adherence_kind="device", adherence_confidence=90,  # 避免 self_reported 拉低
        )
        db.add(card)
        db.commit()

        with patch("app.services.notification.push_service.PushService") as MockPush:
            instance = MockPush.return_value
            instance.send_notification = AsyncMock(return_value={"success": True})

            result = _grade_loop(db, now)

            assert result["graded"] >= 1
            assert result.get("pushed", 0) >= 1
            instance.send_notification.assert_called_once()
            kw = instance.send_notification.call_args.kwargs
            assert kw["notification_type"] == "prediction_verified"
            assert "命中" in kw["title"]
            assert kw["data"]["specialist"] == "fuel_strategist"
            assert kw["data"]["kind"] == "prediction_verified"
            assert kw["data"]["accuracy_score"] >= 70
            assert kw["data"]["deep_link"] == "/specialist/fuel_strategist"

    def test_miss_no_push(self, db):
        """未命中 (score < 70) 不应推送, 避免负面噪声."""
        from datetime import date as date_type
        from unittest.mock import AsyncMock, patch

        from app.models.action_card import ActionCard
        from app.models.weight import WeightRecord
        from app.tasks.outcome_grader import _grade_loop

        now = datetime.now(timezone.utc)
        # 反向: 想减到 78 但实际涨到 84 → 反向, score < 30
        db.add(WeightRecord(user_id=102, record_date=date_type.today(), weight=84.0))

        card = ActionCard(
            user_id=102, title="减重", content="...", card_type="plan",
            metric_key="weight", baseline_value="82", target_value="78",
            creator_specialist="fuel_strategist",
            check_back_date=now - timedelta(hours=1),
            adherence_kind="device", adherence_confidence=90,
        )
        db.add(card)
        db.commit()

        with patch("app.services.notification.push_service.PushService") as MockPush:
            instance = MockPush.return_value
            instance.send_notification = AsyncMock(return_value={"success": True})

            result = _grade_loop(db, now)

            assert result["graded"] >= 1
            assert result.get("pushed", 0) == 0
            instance.send_notification.assert_not_called()

    def test_no_specialist_no_push(self, db):
        """无 creator_specialist 的卡命中也不推 (没法 deep link)."""
        from datetime import date as date_type
        from unittest.mock import AsyncMock, patch

        from app.models.action_card import ActionCard
        from app.models.weight import WeightRecord
        from app.tasks.outcome_grader import _grade_loop

        now = datetime.now(timezone.utc)
        db.add(WeightRecord(user_id=103, record_date=date_type.today(), weight=78.0))

        card = ActionCard(
            user_id=103, title="减重", content="...", card_type="plan",
            metric_key="weight", baseline_value="82", target_value="78",
            creator_specialist=None,  # ← 无归属
            check_back_date=now - timedelta(hours=1),
            adherence_kind="device", adherence_confidence=90,
        )
        db.add(card)
        db.commit()

        with patch("app.services.notification.push_service.PushService") as MockPush:
            instance = MockPush.return_value
            instance.send_notification = AsyncMock(return_value={"success": True})

            _grade_loop(db, now)

            instance.send_notification.assert_not_called()

    def test_push_failure_does_not_break_grading(self, db):
        """PushService 抛异常不应影响评分主路径."""
        from datetime import date as date_type
        from unittest.mock import AsyncMock, patch

        from app.models.action_card import ActionCard
        from app.models.weight import WeightRecord
        from app.tasks.outcome_grader import _grade_loop

        now = datetime.now(timezone.utc)
        db.add(WeightRecord(user_id=104, record_date=date_type.today(), weight=78.0))

        card = ActionCard(
            user_id=104, title="减重", content="...", card_type="plan",
            metric_key="weight", baseline_value="82", target_value="78",
            creator_specialist="fuel_strategist",
            check_back_date=now - timedelta(hours=1),
            adherence_kind="device", adherence_confidence=90,
        )
        db.add(card)
        db.commit()

        with patch("app.services.notification.push_service.PushService") as MockPush:
            instance = MockPush.return_value
            instance.send_notification = AsyncMock(side_effect=RuntimeError("apns down"))

            result = _grade_loop(db, now)

            assert result["graded"] >= 1
            assert result.get("pushed", 0) == 0  # 推失败计 0

        db.refresh(card)
        assert card.accuracy_score is not None  # 评分不受影响
        assert card.graded_at is not None


class TestOutcomeFieldsWritten:
    """收敛 verify_outcomes → outcome_grader 后, 下游字段必须仍可读 (2026-05-16)."""

    def test_weight_improved_writes_outcome_and_effect(self, db):
        """体重下降 → outcome='improved' + effect_size > 0 (下游 admin_wscla 用)."""
        from app.models.action_card import ActionCard
        from app.models.weight import WeightRecord
        from app.tasks.outcome_grader import _grade_loop

        now = datetime.now(timezone.utc)
        # baseline 82kg, actual 76kg → -7.3% → 朝目标方向显著改善 → improved
        db.add(WeightRecord(user_id=701, record_date=date.today(), weight=76.0))
        card = ActionCard(
            user_id=701, title="减重", content="...", card_type="plan",
            metric_key="weight", baseline_value="82", target_value="76",
            creator_specialist="fuel_strategist",
            check_back_date=now - timedelta(hours=1),
        )
        db.add(card)
        db.commit()

        _grade_loop(db, now)
        db.refresh(card)

        assert card.outcome == "improved"
        assert card.effect_size is not None and card.effect_size > 0

    def test_weight_worsened_writes_outcome(self, db):
        """体重上升 → outcome='worsened' (下游计数器要识别)."""
        from app.models.action_card import ActionCard
        from app.models.weight import WeightRecord
        from app.tasks.outcome_grader import _grade_loop

        now = datetime.now(timezone.utc)
        # baseline 80kg, actual 85kg → +6.25% 反方向 → worsened
        db.add(WeightRecord(user_id=702, record_date=date.today(), weight=85.0))
        card = ActionCard(
            user_id=702, title="减重", content="...", card_type="plan",
            metric_key="weight", baseline_value="80", target_value="76",
            creator_specialist="fuel_strategist",
            check_back_date=now - timedelta(hours=1),
        )
        db.add(card)
        db.commit()

        _grade_loop(db, now)
        db.refresh(card)

        assert card.outcome == "worsened"
        assert card.effect_size is not None and card.effect_size < 0

    def test_hrv_improved_higher_better(self, db):
        """HRV 升高=好 → outcome='improved' (HIGHER_IS_BETTER 表方向正确)."""
        from app.models.action_card import ActionCard
        from app.models.daily_health import GarminData
        from app.tasks.outcome_grader import _grade_loop

        now = datetime.now(timezone.utc)
        db.add(GarminData(
            user_id=703, record_date=date.today(), hrv=58.0,
        ))
        card = ActionCard(
            user_id=703, title="提 HRV", content="...", card_type="plan",
            metric_key="hrv", baseline_value="50", target_value="65",
            creator_specialist="recovery_coach",
            check_back_date=now - timedelta(hours=1),
        )
        db.add(card)
        db.commit()

        _grade_loop(db, now)
        db.refresh(card)

        assert card.outcome == "improved"
        assert card.effect_size is not None and card.effect_size > 0

    def test_no_data_does_not_write_outcome(self, db):
        """无数据 → 顺延复查, outcome 字段保持 NULL (不污染下游统计)."""
        from app.models.action_card import ActionCard
        from app.tasks.outcome_grader import _grade_loop

        now = datetime.now(timezone.utc)
        card = ActionCard(
            user_id=704, title="减重", content="...", card_type="plan",
            metric_key="weight", baseline_value="80", target_value="76",
            creator_specialist="fuel_strategist",
            check_back_date=now - timedelta(hours=1),
        )
        db.add(card)
        db.commit()

        _grade_loop(db, now)
        db.refresh(card)

        assert card.graded_at is None
        assert card.outcome is None
        assert card.effect_size is None
