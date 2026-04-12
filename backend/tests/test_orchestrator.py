"""
Orchestrator 测试。

覆盖：
- Intent 分类器
- SafetyGuardianSpecialist 独立执行
- run_orchestrator 完整路径（LLM 被 monkeypatch 成固定字符串）
- SSE stream 基本 shape
"""

from datetime import datetime
from typing import List

import pytest

from app.orchestrator import (
    OrchestratorRequest,
    run_orchestrator,
)
from app.orchestrator.intent import classify_intent
from app.orchestrator.specialists import (
    SafetyGuardianSpecialist,
    all_specialists,
    get_specialist,
)
from app.twin.schema import (
    GeneticContext,
    HealthTwin,
    LabsContext,
    MedicationState,
    PhysiologicalState,
    TwinMeta,
)


def _twin(**kw) -> HealthTwin:
    t = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    for k, v in kw.items():
        setattr(t, k, v)
    return t


# ─────────────────────── Intent ─────────────────────


class TestIntent:
    def test_safety_via_drug_name(self):
        intent = classify_intent("我能同时吃华法林和布洛芬吗")
        assert "safety" in intent.categories

    def test_safety_via_explicit_kw(self):
        intent = classify_intent("这两个药有相互作用吗")
        assert "safety" in intent.categories

    def test_fuel_does_not_catch_random_chi(self):
        """之前 '吃' 会错匹配 fuel —— 现在应该不会。"""
        intent = classify_intent("我能同时吃布洛芬和华法林吗")
        assert "fuel" not in intent.categories

    def test_movement(self):
        intent = classify_intent("我的训练强度怎么样")
        assert "movement" in intent.categories

    def test_recovery(self):
        intent = classify_intent("最近睡眠质量差")
        assert "recovery" in intent.categories

    def test_labs(self):
        intent = classify_intent("我最近的肝酶偏高，怎么办")
        assert "labs" in intent.categories

    def test_general_fallback(self):
        intent = classify_intent("你好")
        assert "general" in intent.categories


# ─────────────────────── Specialists 注册 ──────


class TestSpecialistRegistry:
    def test_safety_registered(self):
        names = [s.name for s in all_specialists()]
        assert "safety_guardian" in names

    def test_get_specialist(self):
        s = get_specialist("safety_guardian")
        assert s is not None
        assert s.name == "safety_guardian"

    def test_unknown_specialist(self):
        assert get_specialist("does_not_exist") is None


# ─────────────────────── SafetyGuardianSpecialist ──────


class TestSafetySpecialist:
    def test_applies_when_drug_in_query(self):
        twin = _twin()
        intent = classify_intent("华法林和布洛芬能一起吃吗")
        s = SafetyGuardianSpecialist()
        assert s.applies_to(intent, twin) is True

    def test_applies_when_bp_high(self):
        twin = _twin()
        twin.labs = LabsContext(blood_pressure_systolic=160, blood_pressure_diastolic=100)
        intent = classify_intent("你好")
        s = SafetyGuardianSpecialist()
        assert s.applies_to(intent, twin) is True

    def test_applies_when_meds_and_genetic(self):
        twin = _twin()
        twin.medication = MedicationState(active_meds=[{"name": "华法林"}], has_any=True)
        twin.genetic = GeneticContext(has_profile=True, total_variants=5)
        intent = classify_intent("你好")
        assert SafetyGuardianSpecialist().applies_to(intent, twin) is True

    def test_does_not_apply_to_unrelated(self):
        twin = _twin()
        intent = classify_intent("今天天气怎么样")
        assert SafetyGuardianSpecialist().applies_to(intent, twin) is False

    def test_run_produces_finding_shape(self):
        twin = _twin()
        twin.labs = LabsContext(blood_pressure_systolic=185, blood_pressure_diastolic=125)
        s = SafetyGuardianSpecialist()
        finding = s.run(twin, {})
        assert finding.specialist_name == "safety_guardian"
        assert finding.category == "safety"
        assert len(finding.findings) >= 1
        # 有严重告警时必有 summary
        assert finding.summary
        assert finding.ms_elapsed >= 0


# ─────────────────────── run_orchestrator end-to-end ──


@pytest.mark.asyncio
async def test_run_orchestrator_monkeypatched_llm(monkeypatch, db):
    """端到端，LLM 被替换为固定字符串。"""

    # 创建一个用户
    import uuid
    from app.models.user import User

    user = User(
        username=f"orch_{uuid.uuid4().hex[:6]}",
        email=f"orch_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="orch test",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Monkeypatch LLM 调用
    async def fake_call_llm(system_prompt, user_prompt):
        return "这是伪造的 LLM 合并结果：建议复查肝功能。"

    from app.orchestrator import orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "_call_llm", fake_call_llm)

    req = OrchestratorRequest(
        query="我能同时吃布洛芬和华法林吗",
        stream=False,
    )
    resp = await orch_mod.run_orchestrator(db, user.id, req)

    assert resp.query == req.query
    assert "safety" in resp.intent.categories
    assert "safety_guardian" in resp.used_specialists
    assert resp.synthesis == "这是伪造的 LLM 合并结果：建议复查肝功能。"
    assert resp.total_ms >= 0


# ─────────────────────── API shape ────────────────────


class TestOrchestratorAPI:
    def test_unauthenticated(self, client):
        resp = client.post("/api/v1/orchestrator/chat", json={"query": "test"})
        assert resp.status_code in (401, 403)

    def test_authenticated_empty_user(self, client, db, monkeypatch):
        """空用户 + 伪造 LLM → 返回 200，结构完整。"""
        from tests.conftest import create_authenticated_user

        # Monkeypatch LLM
        from app.orchestrator import orchestrator as orch_mod

        async def fake_call(system, user):
            return "(test fake synthesis)"

        monkeypatch.setattr(orch_mod, "_call_llm", fake_call)

        _, token = create_authenticated_user(db)
        resp = client.post(
            "/api/v1/orchestrator/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": "分析我的安全告警"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "query" in body
        assert "intent" in body
        assert "findings" in body
        assert "synthesis" in body
        assert "used_specialists" in body
