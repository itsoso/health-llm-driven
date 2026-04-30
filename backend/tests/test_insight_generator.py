"""Insight Generator 单元测试."""
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.daily_insight import DailyInsight
from app.models.daily_health import GarminData
from app.models.family_health import MedicalIndicator
from app.models.genetic_data import GeneticProfile, GeneticVariant
from app.models.medication import Medication
from app.services.insight_generator import (
    InsightCandidate,
    _gen_abnormal_lab_trend,
    _gen_hrv_stressor_pattern,
    _gen_pgx_medication_caution,
    _gen_profile_summary,
    generate_daily_insight,
)


def _mk_user(db):
    from app.models.user import User
    u = User(name="test")
    db.add(u)
    db.commit()
    return u


# ─────────────────── PGx 规则 ───────────────────

class TestPGxRule:
    def test_no_genes_returns_none(self, db):
        u = _mk_user(db)
        assert _gen_pgx_medication_caution(db, u.id) is None

    def test_genes_but_no_meds_returns_none(self, db):
        u = _mk_user(db)
        # 需要 profile
        p = GeneticProfile(user_id=u.id, test_provider="test", test_date=date.today())
        db.add(p); db.commit()
        db.add(GeneticVariant(
            user_id=u.id, profile_id=p.id, category="drug_sensitivity",
            gene_name="CYP2D6", genotype="慢", risk_level="high",
        ))
        db.commit()
        assert _gen_pgx_medication_caution(db, u.id) is None

    def test_cyp2d6_plus_metoprolol_matches(self, db):
        u = _mk_user(db)
        p = GeneticProfile(user_id=u.id, test_provider="test", test_date=date.today())
        db.add(p); db.commit()
        db.add(GeneticVariant(
            user_id=u.id, profile_id=p.id, category="drug_sensitivity",
            gene_name="CYP2D6", genotype="慢", risk_level="high",
        ))
        db.add(Medication(user_id=u.id, name="美托洛尔", category="prescription", is_active=True))
        db.commit()
        result = _gen_pgx_medication_caution(db, u.id)
        assert result is not None
        assert result.kind == "gene_pgx"
        assert "CYP2D6" in result.title
        assert "美托洛尔" in result.body
        assert result.severity == "medium"  # high risk level
        assert result.evidence["gene_name"] == "CYP2D6"

    def test_no_matching_drug_returns_none(self, db):
        """CYP2D6 位点 + 在服药 (非 β 阻滞剂/阿片类) → 不匹配."""
        u = _mk_user(db)
        p = GeneticProfile(user_id=u.id, test_provider="test", test_date=date.today())
        db.add(p); db.commit()
        db.add(GeneticVariant(
            user_id=u.id, profile_id=p.id, category="drug_sensitivity",
            gene_name="CYP2D6", genotype="慢", risk_level="high",
        ))
        # 与 CYP2D6 无关的药
        db.add(Medication(user_id=u.id, name="AKK益生菌", category="supplement", is_active=True))
        db.commit()
        assert _gen_pgx_medication_caution(db, u.id) is None


# ─────────────────── Lab Trend 规则 ───────────────────

class TestLabTrendRule:
    def test_single_measurement_returns_none(self, db):
        u = _mk_user(db)
        db.add(MedicalIndicator(user_id=u.id, name="LDL", value=3.5, unit="mmol/L",
                                 record_date=date.today(), is_abnormal=False))
        db.commit()
        assert _gen_abnormal_lab_trend(db, u.id) is None

    def test_abnormal_rising_trend_matches(self, db):
        u = _mk_user(db)
        today = date.today()
        db.add(MedicalIndicator(user_id=u.id, name="LDL", value=3.2, unit="mmol/L",
                                 record_date=today - timedelta(days=120), is_abnormal=False,
                                 reference_high=3.4))
        db.add(MedicalIndicator(user_id=u.id, name="LDL", value=4.2, unit="mmol/L",
                                 record_date=today - timedelta(days=3), is_abnormal=True,
                                 reference_high=3.4))
        db.commit()
        result = _gen_abnormal_lab_trend(db, u.id)
        assert result is not None
        assert result.kind == "lab_trend"
        assert "LDL" in result.title
        assert "上升" in result.title
        assert result.severity == "medium"

    def test_stable_normal_returns_none(self, db):
        """两次都在范围内, 变化 < 20% → 不触发."""
        u = _mk_user(db)
        today = date.today()
        db.add(MedicalIndicator(user_id=u.id, name="HbA1c", value=5.5,
                                 record_date=today - timedelta(days=120), is_abnormal=False))
        db.add(MedicalIndicator(user_id=u.id, name="HbA1c", value=5.6,
                                 record_date=today - timedelta(days=3), is_abnormal=False))
        db.commit()
        assert _gen_abnormal_lab_trend(db, u.id) is None


# ─────────────────── HRV Pattern 规则 ───────────────────

class TestHRVPatternRule:
    def test_too_few_days_returns_none(self, db):
        u = _mk_user(db)
        for i in range(3):
            db.add(GarminData(user_id=u.id, record_date=date.today() - timedelta(days=i),
                              hrv=50, sleep_score=80))
        db.commit()
        assert _gen_hrv_stressor_pattern(db, u.id) is None

    def test_sleep_correlates_with_low_hrv(self, db):
        u = _mk_user(db)
        today = date.today()
        # 14 天数据: 3 天 HRV 低 + 睡眠差, 其他天 HRV 正常 + 睡眠好
        for i in range(14):
            d = today - timedelta(days=i)
            if i < 3:  # 最近 3 天 HRV 最低 + 睡眠差
                db.add(GarminData(user_id=u.id, record_date=d, hrv=35, sleep_score=55))
            else:
                db.add(GarminData(user_id=u.id, record_date=d, hrv=60, sleep_score=85))
        db.commit()
        result = _gen_hrv_stressor_pattern(db, u.id)
        assert result is not None
        assert result.kind == "hrv_pattern"
        assert "最低 3 天" in result.title
        assert "睡眠" in result.body


# ─────────────────── Profile Summary Fallback ───────────────────

class TestProfileSummaryFallback:
    def test_empty_user_returns_none(self, db):
        u = _mk_user(db)
        assert _gen_profile_summary(db, u.id) is None

    def test_with_some_data_returns_candidate(self, db):
        u = _mk_user(db)
        p = GeneticProfile(user_id=u.id, test_provider="test", test_date=date.today())
        db.add(p); db.commit()
        from app.services.memory_extractor import extract_kg_from_medication, extract_kg_from_gene_variant
        db.add(Medication(user_id=u.id, name="美托洛尔", category="prescription", is_active=True))
        db.commit()
        med = db.query(Medication).filter_by(user_id=u.id).first()
        extract_kg_from_medication(db, u.id, med)
        # 3 个不同基因 (避免 canonical 合并)
        for gene in ["CYP2D6", "SLCO1B1", "VKORC1"]:
            db.add(GeneticVariant(
                user_id=u.id, profile_id=p.id, category="drug_sensitivity",
                gene_name=gene, genotype="变异", risk_level="high",
            ))
        db.commit()
        for g in db.query(GeneticVariant).filter_by(user_id=u.id).all():
            extract_kg_from_gene_variant(db, u.id, g)
        db.commit()

        result = _gen_profile_summary(db, u.id)
        assert result is not None
        assert result.kind == "profile_summary"
        assert result.confidence < 0.6  # fallback 故意低分


# ─────────────────── 主入口: generate_daily_insight ───────────────────

class TestGenerateDailyInsight:
    def test_idempotent_returns_existing(self, db):
        u = _mk_user(db)
        # 手动写一条
        existing = DailyInsight(
            user_id=u.id, insight_date=date.today(),
            kind="test", rule_id="test", title="t", body="b",
            confidence=0.5, severity="info",
        )
        db.add(existing); db.commit()

        result_id = generate_daily_insight(db, u.id, date.today())
        assert result_id == existing.id

    def test_no_candidates_returns_none(self, db):
        u = _mk_user(db)
        # 无数据
        assert generate_daily_insight(db, u.id, date.today()) is None

    def test_picks_highest_score(self, db):
        u = _mk_user(db)
        today = date.today()
        p = GeneticProfile(user_id=u.id, test_provider="test", test_date=today)
        db.add(p); db.commit()
        # PGx 规则能 match (high score): CYP2D6 + 美托洛尔
        db.add(GeneticVariant(
            user_id=u.id, profile_id=p.id, category="drug_sensitivity",
            gene_name="CYP2D6", genotype="慢", risk_level="high",
        ))
        db.add(Medication(user_id=u.id, name="美托洛尔", category="prescription", is_active=True))
        db.commit()

        new_id = generate_daily_insight(db, u.id, today)
        assert new_id is not None
        row = db.query(DailyInsight).filter_by(id=new_id).first()
        # 应该选 PGx (score 0.85*1.0=0.85) 而不是 profile_summary (0.5*0.5=0.25)
        assert row.kind == "gene_pgx"
        assert row.rule_id == "pgx_caution_cyp2d6"


# ─────────────────── LLM Pattern Mining (v2) ───────────────────

class TestLLMPatternMining:
    def _seed_data(self, db):
        """建足够触发 LLM 的数据: 10+ fact + 7+ Garmin."""
        from app.models.memory_fact import MemoryFact
        from app.models.daily_health import GarminData
        u = _mk_user(db)
        # 12 条 fact
        for i in range(12):
            db.add(MemoryFact(
                user_id=u.id, tier="semantic",
                subject=f"指标{i}", predicate="is_value",
                object_value=str(100 + i), decay_rate=0.01, confidence=0.7,
            ))
        # 10 天 Garmin
        for i in range(10):
            db.add(GarminData(
                user_id=u.id, record_date=date.today() - timedelta(days=i),
                hrv=50 - i, sleep_score=80 - i, resting_heart_rate=65,
            ))
        db.commit()
        return u

    def test_insufficient_facts_returns_none(self, db, monkeypatch):
        """<10 fact → 直接返回 None (不调 LLM)."""
        from app.services.insight_generator import _gen_llm_pattern_mining
        from app.models.memory_fact import MemoryFact
        from app.models.daily_health import GarminData
        u = _mk_user(db)
        for i in range(5):  # 只 5 条
            db.add(MemoryFact(
                user_id=u.id, tier="semantic",
                subject=f"x{i}", predicate="is_value", object_value="1",
                decay_rate=0.01, confidence=0.7,
            ))
        for i in range(10):
            db.add(GarminData(user_id=u.id, record_date=date.today() - timedelta(days=i), hrv=50))
        db.commit()

        called = {"n": 0}
        def fake_run_async(*a, **kw): called["n"] += 1; return "{}"
        monkeypatch.setattr("app.utils.async_helpers.run_async", fake_run_async)
        assert _gen_llm_pattern_mining(db, u.id) is None
        assert called["n"] == 0  # 没调 LLM

    def test_llm_valid_response_returns_candidate(self, db, monkeypatch):
        """LLM 返回有效 JSON + evidence_refs 都真实 → 产出 InsightCandidate."""
        from app.services.insight_generator import _gen_llm_pattern_mining
        from app.models.memory_fact import MemoryFact
        u = self._seed_data(db)
        fact_id = db.query(MemoryFact).filter_by(user_id=u.id).first().id
        garmin_date = date.today().isoformat()

        # Mock LLM 返回合法 JSON
        fake_json = (
            '{"found_pattern": true, '
            '"title": "HRV 连日下降", '
            '"body": "过去 10 天 HRV 逐日下降, 可能睡眠质量下滑. 可以关注晚间咖啡摄入.", '
            f'"evidence_refs": [{{"type": "fact", "id": {fact_id}}}, '
            f'{{"type": "garmin_date", "date": "{garmin_date}"}}], '
            '"confidence": 0.7}'
        )
        class FakeProvider:
            async def chat(self, **kwargs):
                return {"content": fake_json}

        monkeypatch.setattr(
            "app.services.llm.get_llm_provider",
            lambda *a, **kw: FakeProvider(),
        )

        result = _gen_llm_pattern_mining(db, u.id)
        assert result is not None
        assert result.kind == "llm_pattern"
        assert result.rule_id == "llm_pattern_mining_v1"
        assert "HRV 连日下降" in result.title
        assert len(result.evidence["evidence_refs"]) == 2
        assert result.confidence == 0.7

    def test_llm_fake_evidence_rejected(self, db, monkeypatch):
        """LLM 编造 evidence_refs (fact_id 不存在) → grounding 拒绝."""
        from app.services.insight_generator import _gen_llm_pattern_mining
        u = self._seed_data(db)

        fake_json = (
            '{"found_pattern": true, "title": "编造的 pattern", '
            '"body": "说有 pattern 但 evidence 都是假的.", '
            '"evidence_refs": [{"type": "fact", "id": 99999}, '
            '{"type": "garmin_date", "date": "2099-01-01"}], '
            '"confidence": 0.9}'
        )
        class FakeProvider:
            async def chat(self, **kwargs):
                return {"content": fake_json}
        monkeypatch.setattr(
            "app.services.llm.get_llm_provider",
            lambda *a, **kw: FakeProvider(),
        )
        assert _gen_llm_pattern_mining(db, u.id) is None  # 全假, 拒绝

    def test_llm_found_pattern_false_returns_none(self, db, monkeypatch):
        """LLM 明确说没 pattern → None."""
        from app.services.insight_generator import _gen_llm_pattern_mining
        u = self._seed_data(db)
        class FakeProvider:
            async def chat(self, **kwargs):
                return {"content": '{"found_pattern": false}'}
        monkeypatch.setattr(
            "app.services.llm.get_llm_provider",
            lambda *a, **kw: FakeProvider(),
        )
        assert _gen_llm_pattern_mining(db, u.id) is None

    def test_llm_invalid_json_returns_none(self, db, monkeypatch):
        from app.services.insight_generator import _gen_llm_pattern_mining
        u = self._seed_data(db)
        class FakeProvider:
            async def chat(self, **kwargs):
                return {"content": "LLM 乱说一通 no JSON here"}
        monkeypatch.setattr(
            "app.services.llm.get_llm_provider",
            lambda *a, **kw: FakeProvider(),
        )
        assert _gen_llm_pattern_mining(db, u.id) is None

    def test_llm_exception_returns_none(self, db, monkeypatch):
        from app.services.insight_generator import _gen_llm_pattern_mining
        u = self._seed_data(db)
        class FakeProvider:
            async def chat(self, **kwargs):
                raise RuntimeError("network down")
        monkeypatch.setattr(
            "app.services.llm.get_llm_provider",
            lambda *a, **kw: FakeProvider(),
        )
        assert _gen_llm_pattern_mining(db, u.id) is None
