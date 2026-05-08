"""LongitudinalAnalyst specialist 单元测试.

覆盖策略 (同项目其他 specialist 测试风格):
- 纯函数 _direction_text / _correlate_events_with_metrics 边界
- applies_to 正反例
- run() 无 db 时降级返回
- run() 有 mock PersonalOutcomeService 时的输出结构
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

import pytest

from app.agents.longitudinal_analyst.analyst import (
    LongitudinalAnalystSpecialist,
    _correlate_events_with_metrics,
    _direction_text,
)
from app.orchestrator.intent import classify_intent
from app.orchestrator.schema import SpecialistFinding
from app.twin.schema import HealthTwin, TwinMeta


# ───────────────────────── 纯函数 ─────────────────────────


class TestDirectionText:
    def test_small_delta_flat(self):
        assert _direction_text(0.3, "up") == "基本持平"
        assert _direction_text(-0.4, "down") == "基本持平"

    def test_up_desirable_improvement(self):
        # HRV 上升是好事
        assert "✅" in _direction_text(5.0, "up")
        assert "良性" in _direction_text(5.0, "up")

    def test_up_desirable_regression(self):
        # HRV 下降是坏事
        assert "⚠️" in _direction_text(-5.0, "up")
        assert "需要关注" in _direction_text(-5.0, "up")

    def test_down_desirable_improvement(self):
        # RHR 下降是好事
        assert "✅" in _direction_text(-3.0, "down")

    def test_down_desirable_regression(self):
        # RHR 上升是坏事
        assert "⚠️" in _direction_text(3.0, "down")

    def test_context_dependent_no_judgement(self):
        # 体重:不评判方向好坏
        txt = _direction_text(2.0, "context")
        assert "✅" not in txt and "⚠️" not in txt


class TestCorrelateEvents:
    def test_empty_events(self):
        assert _correlate_events_with_metrics({}, []) == []

    def test_supplement_start_generates_narrative(self):
        narratives = _correlate_events_with_metrics(
            {},
            [{"date": "2025-12-01", "kind": "supplement_start", "title": "鱼油"}],
        )
        assert len(narratives) == 1
        assert narratives[0]["type"] == "narrative"
        assert narratives[0]["event"] == "鱼油"
        assert "3-6 个月" in narratives[0]["text"]

    def test_medical_exam_generates_narrative(self):
        narratives = _correlate_events_with_metrics(
            {},
            [{"date": "2026-01-15", "kind": "medical_exam", "title": "年度体检"}],
        )
        assert len(narratives) == 1
        assert "锚点" in narratives[0]["text"]

    def test_unknown_kind_skipped(self):
        narratives = _correlate_events_with_metrics(
            {},
            [{"date": "2026-01-01", "kind": "mystery_kind", "title": "?"}],
        )
        assert narratives == []

    def test_caps_at_5_narratives(self):
        events = [
            {"date": "2026-01-01", "kind": "supplement_start", "title": f"补剂{i}"}
            for i in range(10)
        ]
        narratives = _correlate_events_with_metrics({}, events)
        assert len(narratives) == 5


# ───────────────────────── applies_to ─────────────────────────


def _empty_twin() -> HealthTwin:
    return HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))


class TestAppliesTo:
    def test_applies_on_trend_keyword(self):
        s = LongitudinalAnalystSpecialist()
        intent = classify_intent("最近这几个月的变化趋势")
        assert s.applies_to(intent, _empty_twin()) is True

    def test_applies_on_english_trend(self):
        s = LongitudinalAnalystSpecialist()
        intent = classify_intent("show my long term progress")
        assert s.applies_to(intent, _empty_twin()) is True

    def test_applies_on_general_dashboard(self):
        """没命中 trigger keyword 时, general 场景也要参与 (长期视角)."""
        s = LongitudinalAnalystSpecialist()
        intent = classify_intent("今天整体怎么样")
        # general 被加入 categories 时就 applies
        if "general" in intent.categories:
            assert s.applies_to(intent, _empty_twin()) is True

    def test_does_not_apply_on_unrelated(self):
        s = LongitudinalAnalystSpecialist()
        intent = classify_intent("我现在能跑步吗")
        # 运动 intent 一般不带 general 也没 trigger keyword
        if "general" not in intent.categories:
            assert s.applies_to(intent, _empty_twin()) is False


# ───────────────────────── run() 降级 ─────────────────────────


class TestRunDegraded:
    def test_no_db_returns_degraded_finding(self):
        """没 db 时优雅降级, 不崩."""
        s = LongitudinalAnalystSpecialist()
        finding = s.run(_empty_twin(), context={})  # 没 "db"
        assert isinstance(finding, SpecialistFinding)
        assert finding.specialist_name == "longitudinal_analyst"
        assert finding.findings == []
        assert "数据库" in finding.summary

    def test_exception_in_service_caught(self, monkeypatch):
        """PersonalOutcomeService 抛错时应 catch 成 summary 而非上抛."""
        s = LongitudinalAnalystSpecialist()

        class _BoomService:
            def get_timeline(self, *a, **kw):
                raise RuntimeError("boom")

        # 用 monkeypatch 替换 import 时的类
        import app.agents.longitudinal_analyst.analyst as mod
        monkeypatch.setattr(
            "app.services.personal_outcome_service.PersonalOutcomeService",
            _BoomService,
        )

        finding = s.run(_empty_twin(), context={"db": object()})  # db 随便给一个
        assert isinstance(finding, SpecialistFinding)
        assert "失败" in finding.summary
        assert finding.findings == []


# ───────────────────────── run() 正常路径 ─────────────────────────


class TestRunHappyPath:
    """用 mock PersonalOutcomeService, 验证 finding 结构."""

    @pytest.fixture
    def stub_timeline(self):
        return {
            "points": [{"date": "2026-01"}, {"date": "2026-02"}, {"date": "2026-03"}],
            "events": [
                {"date": "2026-01-10", "kind": "supplement_start", "title": "鱼油"},
                {"date": "2026-02-15", "kind": "medical_exam", "title": "年度体检"},
            ],
            "summary": {
                "covered_days": 75,
                "total_days": 90,
                "metrics": {
                    "hrv": {"first": 50.0, "last": 58.0, "delta": 8.0},
                    "rhr": {"first": 60, "last": 55, "delta": -5},
                    "sleep_score": {"first": 72, "last": 78, "delta": 6},
                    "weight": {"first": 72.0, "last": 71.5, "delta": -0.5},
                },
            },
        }

    def _patch_service(self, monkeypatch, stub_timeline):
        class _StubService:
            def get_timeline(self, db, user_id, range_key=None, granularity=None):
                return stub_timeline

        monkeypatch.setattr(
            "app.services.personal_outcome_service.PersonalOutcomeService",
            _StubService,
        )

    def test_trend_findings_per_metric(self, monkeypatch, stub_timeline):
        self._patch_service(monkeypatch, stub_timeline)
        s = LongitudinalAnalystSpecialist()
        finding = s.run(_empty_twin(), context={"db": object()})

        trends = [f for f in finding.findings if f.get("type") == "trend"]
        # 期望 hrv / rhr / sleep_score / weight 4 条 trend (其他 metric_labels 没数据)
        assert len(trends) == 4

        # 检查 HRV 上升被标记为良性 ✅
        hrv = next(f for f in trends if f["metric"] == "hrv")
        assert "✅" in hrv["direction"]

        # 检查 RHR 下降被标记为良性 ✅
        rhr = next(f for f in trends if f["metric"] == "rhr")
        assert "✅" in rhr["direction"]

    def test_coverage_finding_present(self, monkeypatch, stub_timeline):
        self._patch_service(monkeypatch, stub_timeline)
        s = LongitudinalAnalystSpecialist()
        finding = s.run(_empty_twin(), context={"db": object()})

        coverage = next(f for f in finding.findings if f.get("type") == "coverage")
        assert coverage["covered_days"] == 75
        assert coverage["total_days"] == 90
        assert coverage["months_of_data"] == 3

    def test_narratives_include_supplement_and_exam(self, monkeypatch, stub_timeline):
        self._patch_service(monkeypatch, stub_timeline)
        s = LongitudinalAnalystSpecialist()
        finding = s.run(_empty_twin(), context={"db": object()})

        narratives = [f for f in finding.findings if f.get("type") == "narrative"]
        assert len(narratives) == 2
        events = [n["event"] for n in narratives]
        assert "鱼油" in events
        assert "年度体检" in events

    def test_significant_changes_when_delta_gt_5pct(self, monkeypatch, stub_timeline):
        self._patch_service(monkeypatch, stub_timeline)
        s = LongitudinalAnalystSpecialist()
        finding = s.run(_empty_twin(), context={"db": object()})

        sig = next(
            (f for f in finding.findings if f.get("type") == "significant_changes"),
            None,
        )
        assert sig is not None
        # HRV 50→58 = +16% (>5%); RHR 60→55 = -8.3% (>5%); sleep 72→78 = +8.3% (>5%)
        # weight -0.5/72 = -0.7% (<5%), 不计入
        labels = {c["metric"] for c in sig["changes"]}
        assert "HRV" in labels
        assert "静息心率" in labels
        assert "睡眠评分" in labels
        assert "体重" not in labels

    def test_summary_not_empty_when_has_data(self, monkeypatch, stub_timeline):
        self._patch_service(monkeypatch, stub_timeline)
        s = LongitudinalAnalystSpecialist()
        finding = s.run(_empty_twin(), context={"db": object()})
        assert "6 个月趋势" in finding.summary
        assert finding.summary != "6 个月趋势 · 长期数据暂缺"

    def test_summary_degrades_when_no_metrics(self, monkeypatch):
        self._patch_service(
            monkeypatch,
            {"points": [], "events": [], "summary": {"covered_days": 0, "metrics": {}}},
        )
        s = LongitudinalAnalystSpecialist()
        finding = s.run(_empty_twin(), context={"db": object()})
        assert "长期数据暂缺" in finding.summary
