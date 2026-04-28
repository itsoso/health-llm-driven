"""Clinical Journal — write_soap_entry + case_thread 聚合 + prompt 注入."""
from datetime import datetime, timezone

import pytest

from app.models.clinical_journal import CaseThread, ClinicalJournalEntry
from app.services.clinical_journal_service import (
    _theme_from_metric,
    _build_subjective,
    _build_objective,
    _build_assessment,
    _build_plan,
    _pick_primary_metric,
    write_soap_entry,
    get_recent_case_summary,
)


# ─────────────── pure helpers ───────────────


class TestThemeMap:
    def test_known_metrics(self):
        assert _theme_from_metric("alt") == "liver"
        assert _theme_from_metric("ALT") == "liver"
        assert _theme_from_metric("ldl") == "lipid"
        assert _theme_from_metric("weight") == "weight_loss"
        assert _theme_from_metric("hba1c") == "metabolic"
        assert _theme_from_metric("systolic_bp") == "hypertension"
        assert _theme_from_metric("hrv") == "recovery"

    def test_unknown_metric_falls_through(self):
        assert _theme_from_metric("custom") == "custom"

    def test_none_returns_general(self):
        assert _theme_from_metric(None) == "general"


class TestBuilders:
    def test_subjective_truncated(self):
        long = "a" * 250
        s = _build_subjective(long)
        assert len(s) <= 201
        assert s.endswith("…")

    def test_subjective_short_kept(self):
        assert _build_subjective("我血压最近偏高") == "我血压最近偏高"

    def test_objective_empty_twin(self):
        from app.twin.schema import HealthTwin, TwinMeta
        twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(timezone.utc)))
        # 全 default fields 应输出占位
        out = _build_objective(twin)
        assert "无关键指标" in out

    def test_objective_with_data(self):
        from app.twin.schema import HealthTwin, TwinMeta, PhysiologicalState, BodyCompositionState, LabsContext
        twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(timezone.utc)))
        twin.physiological = PhysiologicalState(hrv_latest=42.0, resting_hr=58, sleep_score_latest=82)
        twin.body_composition = BodyCompositionState(weight_kg=72.5, bmi=23.8)
        twin.labs = LabsContext(blood_pressure_systolic=125, blood_pressure_diastolic=80, ldl=3.2)
        out = _build_objective(twin)
        assert "HRV 42" in out
        assert "RHR 58" in out
        assert "睡眠分 82" in out
        assert "72.5kg" in out
        assert "BP 125/80" in out
        assert "LDL 3.2" in out


class TestPickMetric:
    def test_finds_most_common(self):
        from app.orchestrator.schema import SpecialistFinding, ProposedCard
        f1 = SpecialistFinding(
            specialist_name="x", category="x",
            proposed_cards=[ProposedCard(
                title="a", content="b", metric_key="hrv",
                baseline_value="35", target_value=">42", verification_days=7,
            )],
        )
        f2 = SpecialistFinding(
            specialist_name="y", category="y",
            proposed_cards=[ProposedCard(
                title="a", content="b", metric_key="hrv",
                baseline_value="35", target_value=">42", verification_days=7,
            )],
        )
        f3 = SpecialistFinding(
            specialist_name="z", category="z",
            proposed_cards=[ProposedCard(
                title="a", content="b", metric_key="weight",
                baseline_value="80", target_value="<78", verification_days=14,
            )],
        )
        assert _pick_primary_metric([f1, f2, f3]) == "hrv"

    def test_no_proposed_cards_returns_none(self):
        from app.orchestrator.schema import SpecialistFinding
        f = SpecialistFinding(specialist_name="x", category="x")
        assert _pick_primary_metric([f]) is None


# ─────────────── end-to-end with db ───────────────


class TestWriteSoap:
    def _make_twin_and_findings(self):
        from app.twin.schema import HealthTwin, TwinMeta, PhysiologicalState
        from app.orchestrator.schema import SpecialistFinding, ProposedCard
        twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(timezone.utc)))
        twin.physiological = PhysiologicalState(hrv_latest=28.0, hrv_7d_avg=42.0, sleep_score_latest=55)
        findings = [SpecialistFinding(
            specialist_name="recovery_coach", category="recovery",
            summary="Readiness 43/100, 恢复不足",
            proposed_cards=[ProposedCard(
                title="HRV 回升 7 天实验", content="...",
                metric_key="hrv", baseline_value="28", target_value=">42",
                verification_days=7,
            )],
        )]
        return twin, findings

    def test_creates_thread_and_entry(self, db):
        twin, findings = self._make_twin_and_findings()
        eid = write_soap_entry(
            db, user_id=42, query="最近恢复怎么样", twin=twin,
            findings=findings, persisted_card_ids=[100],
        )
        assert eid is not None

        threads = db.query(CaseThread).filter(CaseThread.user_id == 42).all()
        assert len(threads) == 1
        assert threads[0].theme == "recovery"
        assert threads[0].metric_key == "hrv"

        entries = db.query(ClinicalJournalEntry).filter(
            ClinicalJournalEntry.user_id == 42).all()
        assert len(entries) == 1
        e = entries[0]
        assert e.case_thread_id == threads[0].id
        assert "最近恢复" in e.subjective
        assert "HRV 28" in (e.objective or "")
        assert "recovery_coach" in (e.assessment or "")
        assert "100" in (e.related_action_card_ids or "")

    def test_second_entry_reuses_thread(self, db):
        twin, findings = self._make_twin_and_findings()
        write_soap_entry(db, user_id=42, query="q1", twin=twin, findings=findings,
                        persisted_card_ids=[])
        write_soap_entry(db, user_id=42, query="q2", twin=twin, findings=findings,
                        persisted_card_ids=[])
        threads = db.query(CaseThread).filter(CaseThread.user_id == 42).all()
        assert len(threads) == 1  # 仍然 1 条 thread
        entries = db.query(ClinicalJournalEntry).filter(
            ClinicalJournalEntry.user_id == 42).count()
        assert entries == 2

    def test_different_metric_creates_new_thread(self, db):
        from app.twin.schema import HealthTwin, TwinMeta
        from app.orchestrator.schema import SpecialistFinding, ProposedCard
        twin = HealthTwin(meta=TwinMeta(user_id=42, generated_at=datetime.now(timezone.utc)))
        f_hrv = [SpecialistFinding(
            specialist_name="r", category="r",
            proposed_cards=[ProposedCard(
                title="t", content="c", metric_key="hrv",
                baseline_value="28", target_value=">42", verification_days=7,
            )],
        )]
        f_weight = [SpecialistFinding(
            specialist_name="f", category="f",
            proposed_cards=[ProposedCard(
                title="t", content="c", metric_key="weight",
                baseline_value="80", target_value="<78", verification_days=14,
            )],
        )]
        write_soap_entry(db, user_id=42, query="q1", twin=twin, findings=f_hrv,
                        persisted_card_ids=[])
        write_soap_entry(db, user_id=42, query="q2", twin=twin, findings=f_weight,
                        persisted_card_ids=[])

        threads = db.query(CaseThread).filter(CaseThread.user_id == 42).all()
        themes = sorted(t.theme for t in threads)
        assert themes == ["recovery", "weight_loss"]


class TestPromptInjection:
    def test_no_thread_returns_empty(self, db):
        assert get_recent_case_summary(db, user_id=99, metric_key="hrv") == ""

    def test_no_metric_returns_empty(self, db):
        assert get_recent_case_summary(db, user_id=99, metric_key=None) == ""

    def test_finds_recent_entries(self, db):
        from app.twin.schema import HealthTwin, TwinMeta, PhysiologicalState
        from app.orchestrator.schema import SpecialistFinding, ProposedCard

        twin = HealthTwin(meta=TwinMeta(user_id=99, generated_at=datetime.now(timezone.utc)))
        twin.physiological = PhysiologicalState(hrv_latest=30.0)
        findings = [SpecialistFinding(
            specialist_name="recovery_coach", category="recovery",
            summary="状态偏差",
            proposed_cards=[ProposedCard(
                title="t", content="c", metric_key="hrv",
                baseline_value="30", target_value=">42", verification_days=7,
            )],
        )]
        # 写两条, 用同一个 thread
        write_soap_entry(db, user_id=99, query="昨天好累", twin=twin,
                        findings=findings, persisted_card_ids=[])
        write_soap_entry(db, user_id=99, query="今天 HRV 怎样", twin=twin,
                        findings=findings, persisted_card_ids=[])

        out = get_recent_case_summary(db, user_id=99, metric_key="hrv")
        assert "恢复评估" in out  # 标题中文映射
        # 时间正序 (旧 -> 新), 两条都该出现
        assert "昨天好累" in out
        assert "今天 HRV" in out
