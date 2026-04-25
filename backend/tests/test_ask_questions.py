"""ask_questions 数据缺口提示测试。"""
from datetime import date, datetime
from app.api.sleep_spo2_analysis import _compute_ask_questions
from app.services.sleep.correlation_rules import NightContext
from app.services.sleep.nocturnal_spo2_analyzer import NightAnalysis


def _night(odi=8.0, min_spo2=86):
    return NightAnalysis(
        night_date=date(2026, 4, 24),
        odi=odi,
        events_count=12,
        min_spo2=min_spo2,
        avg_spo2=94,
        total_sleep_minutes=480,
        events=[],
    )


def _ctx(**kw):
    base = dict(
        night_date=date(2026, 4, 24),
        med_logs=[],
        active_meds=[],
        supplement_records=[],
        workouts=[],
        diet_records=[],
    )
    base.update(kw)
    return NightContext(**base)


class TestAskQuestionsTrigger:
    def test_no_issue_no_questions(self):
        n = _night(odi=2, min_spo2=95)
        qs = _compute_ask_questions(n, _ctx())
        assert qs == []

    def test_high_odi_triggers(self):
        qs = _compute_ask_questions(_night(odi=8), _ctx())
        assert any('饮酒' in q for q in qs)

    def test_low_spo2_triggers(self):
        qs = _compute_ask_questions(_night(odi=2, min_spo2=82), _ctx())
        assert len(qs) >= 1


class TestAlcoholGap:
    def test_alcohol_recorded_no_question(self):
        ctx = _ctx(diet_records=[
            {'food_items': '红酒', 'meal_type': 'dinner',
             'meal_time': None, 'alcohol_units': 2.0}
        ])
        qs = _compute_ask_questions(_night(), ctx)
        assert not any('饮酒' in q for q in qs)

    def test_zero_alcohol_still_asks(self):
        ctx = _ctx(diet_records=[
            {'food_items': '米饭', 'meal_type': 'dinner',
             'meal_time': None, 'alcohol_units': 0.0}
        ])
        qs = _compute_ask_questions(_night(), ctx)
        assert any('饮酒' in q for q in qs)


class TestIpratropiumGap:
    def test_active_med_not_logged_asks(self):
        ctx = _ctx(active_meds=[{'name': '异丙托溴铵', 'is_active': True}])
        qs = _compute_ask_questions(_night(), ctx)
        assert any('异丙托溴铵' in q for q in qs)

    def test_active_med_logged_no_question(self):
        ctx = _ctx(
            active_meds=[{'name': '异丙托溴铵', 'is_active': True}],
            med_logs=[{'name': '异丙托溴铵', 'taken_time': '21:00', 'status': 'taken'}],
        )
        qs = _compute_ask_questions(_night(), ctx)
        assert not any('异丙托溴铵' in q for q in qs)

    def test_no_active_no_question(self):
        ctx = _ctx()  # no active_meds
        qs = _compute_ask_questions(_night(), ctx)
        assert not any('异丙托溴铵' in q for q in qs)


class TestWorkoutGap:
    def test_no_workout_asks(self):
        qs = _compute_ask_questions(_night(), _ctx())
        assert any('运动' in q for q in qs)

    def test_has_workout_no_question(self):
        ctx = _ctx(workouts=[{'workout_type': '跑步', 'end_time': datetime(2026, 4, 24, 18, 0)}])
        qs = _compute_ask_questions(_night(), ctx)
        assert not any('运动' in q for q in qs)


class TestQuestionsLimit:
    def test_max_3_questions(self):
        # everything missing
        ctx = _ctx(active_meds=[{'name': '异丙托溴铵', 'is_active': True}])
        qs = _compute_ask_questions(_night(), ctx)
        assert len(qs) <= 3
