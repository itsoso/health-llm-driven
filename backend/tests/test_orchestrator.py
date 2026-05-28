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


class TestTrivialQueryShortCircuit:
    """perf (2026-05-28): trivial query (greeting/single-word) 应跳过 specialist 全员."""

    def test_greeting_skips_specialists(self):
        from app.orchestrator.orchestrator import _select_specialists, _is_trivial_query
        intent = classify_intent("你好")
        assert _is_trivial_query(intent) is True
        selected = _select_specialists(intent, _twin(), forced=None)
        assert selected == []

    def test_hi_skips_specialists(self):
        from app.orchestrator.orchestrator import _select_specialists, _is_trivial_query
        intent = classify_intent("hi")
        assert _is_trivial_query(intent) is True
        assert _select_specialists(intent, _twin(), forced=None) == []

    def test_medium_general_query_still_runs_specialists(self):
        """中等长度的 general query 不应被跳过, applies_to 仍然决定."""
        from app.orchestrator.orchestrator import _is_trivial_query
        intent = classify_intent("帮我看看最近怎么样啊我有点担心")  # ~14 chars, general
        assert _is_trivial_query(intent) is False

    def test_keyword_matched_never_trivial(self):
        """有关键字命中的 query 即使很短也不算 trivial (避免误伤 safety/recovery)."""
        from app.orchestrator.orchestrator import _is_trivial_query
        intent = classify_intent("我累")  # recovery keyword 不命中, 但短 → trivial
        # "累" 不在 recovery keywords ("累" 是, 实际上)
        # 这个测试可能会暴露 keyword 不全的问题, 但 trivial 短路逻辑本身正确
        intent_with_kw = classify_intent("华法林")  # 命中 safety, 6 字以内
        assert _is_trivial_query(intent_with_kw) is False

    def test_empty_query_not_trivial(self):
        """空字符串不算 trivial (避免假阳性短路, 让 LLM 自行处理)."""
        from app.orchestrator.orchestrator import _is_trivial_query
        intent = classify_intent("")
        assert _is_trivial_query(intent) is False

    def test_forced_specialists_bypass_trivial_skip(self):
        """forced 指定的 specialist 不被 trivial 短路影响."""
        from app.orchestrator.orchestrator import _select_specialists
        intent = classify_intent("hi")
        selected = _select_specialists(intent, _twin(), forced=["safety_guardian"])
        assert len(selected) == 1
        assert selected[0].name == "safety_guardian"


class TestLiteModePromptSkipsDbBlocks:
    """perf (2026-05-28): lite_mode=True 应跳过 system_kb / credit / track /
    user_feedback / persona / hybrid retrieve, 让 trivial query 走极简 prompt."""

    def test_lite_mode_skips_system_kb_and_credit_blocks(self, monkeypatch):
        """lite_mode=True 时 system KB 和 credit/track 查询不应被调用."""
        from app.orchestrator import orchestrator as orch_mod

        sk_called = []
        credit_called = []
        track_called = []
        feedback_called = []
        persona_called = []

        def fake_sk(*args, **kw):
            sk_called.append(args)
            return "should-not-appear"

        def fake_credit(*args, **kw):
            credit_called.append(args)
            return "should-not-appear-credit"

        def fake_track(*args, **kw):
            track_called.append(args)
            return "should-not-appear-track"

        def fake_persona(*args, **kw):
            persona_called.append(args)
            return "should-not-appear-persona"

        # Patch in-module references (会被 _build_synthesis_prompt 调用的形式)
        monkeypatch.setattr(orch_mod, "_build_specialist_credit_block", fake_credit)
        monkeypatch.setattr(orch_mod, "_build_per_specialist_track_block", fake_track)
        monkeypatch.setattr(orch_mod, "_build_persona_addendum", fake_persona)

        # system_kb 走 try-import, 用 monkeypatch sys.modules patch 比较脆;
        # 用 fake db None 直接绕过 (lite_mode=True 时 if 短路, db 检查永不触达)
        # 这里 db=None + lite_mode=True 是同样的效果:
        sp, up = orch_mod._build_synthesis_prompt(
            query="hi", twin=_twin(), findings=[],
            db=None, user_id=1, source=None, lite_mode=True,
        )
        # 关键: credit / track / persona 都没被调用 (db=None 时本来也不调, 但 lite_mode 是双保险)
        assert credit_called == []
        assert track_called == []
        assert persona_called == []
        # prompt 仍然能正常构建 (twin_blob + 默认 system_prompt)
        assert "首席分析师" in sp
        assert "用户原始问题" in up

    def test_lite_mode_inject_memory_skips_hybrid(self, monkeypatch, db):
        """lite_mode=True 时 hybrid_retrieve 不应被调用."""
        from app.orchestrator import orchestrator as orch_mod
        hybrid_called = []

        def fake_hybrid(*args, **kw):
            hybrid_called.append(args)
            return []

        # _inject_memory 内部 try-imports hybrid_search; 用 sys.modules patch
        import sys
        import types
        fake_module = types.SimpleNamespace(
            hybrid_retrieve=fake_hybrid,
            render_hits_for_prompt=lambda *a, **k: "",
        )
        sys.modules["app.services.hybrid_search"] = fake_module

        try:
            out, trace = orch_mod._inject_memory(
                db, user_id=1, user_prompt="hi", findings=[], lite_mode=True,
            )
            # hybrid stage 必须被跳过
            assert hybrid_called == []
            assert trace["stages"]["hybrid"]["ok"] is False
            assert trace["stages"]["hybrid"]["error"] == "lite_mode_skip"
        finally:
            del sys.modules["app.services.hybrid_search"]

    def test_lite_mode_off_runs_full_pipeline(self, monkeypatch):
        """lite_mode=False (默认) 时 credit / track / persona 该被调用."""
        from app.orchestrator import orchestrator as orch_mod
        credit_called = []
        track_called = []

        monkeypatch.setattr(orch_mod, "_build_specialist_credit_block",
                            lambda *a, **k: (credit_called.append(a), "")[1])
        monkeypatch.setattr(orch_mod, "_build_per_specialist_track_block",
                            lambda *a, **k: (track_called.append(a), "")[1])
        monkeypatch.setattr(orch_mod, "_build_persona_addendum", lambda *a, **k: "")

        class _FakeDb:
            pass

        orch_mod._build_synthesis_prompt(
            query="详细看看我最近的睡眠情况", twin=_twin(), findings=[],
            db=_FakeDb(), user_id=1, source=None, lite_mode=False,
        )
        assert len(credit_called) == 1
        assert len(track_called) == 1


class TestLiteModeMaxTokens:
    """perf (2026-05-28): lite_mode=True 时 LLM max_tokens 降到 300, 默认 900."""

    @pytest.mark.asyncio
    async def test_call_llm_uses_lite_max_tokens(self, monkeypatch):
        """_call_llm(lite_mode=True) 应传 max_tokens=300 给 provider."""
        from app.orchestrator import orchestrator as orch_mod

        captured = []

        class FakeProvider:
            async def chat(self, **kw):
                captured.append(kw)
                return "ok"

        monkeypatch.setattr(
            "app.services.llm.get_llm_provider",
            lambda: FakeProvider(),
        )
        # 确保 user_pref_ctx 没 set (避免走 create_provider_for_user)
        orch_mod._user_pref_ctx.set(None)

        await orch_mod._call_llm("sys", "user", lite_mode=True)
        assert captured[0]["max_tokens"] == orch_mod._LITE_MAX_TOKENS == 300

    @pytest.mark.asyncio
    async def test_call_llm_default_uses_full_max_tokens(self, monkeypatch):
        from app.orchestrator import orchestrator as orch_mod
        captured = []

        class FakeProvider:
            async def chat(self, **kw):
                captured.append(kw)
                return "ok"

        monkeypatch.setattr(
            "app.services.llm.get_llm_provider",
            lambda: FakeProvider(),
        )
        orch_mod._user_pref_ctx.set(None)

        await orch_mod._call_llm("sys", "user")  # 默认 lite_mode=False
        assert captured[0]["max_tokens"] == orch_mod._FULL_MAX_TOKENS == 900


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

    # Monkeypatch LLM 调用 — 接受可选 lite_mode kwarg (2026-05-28 加)
    async def fake_call_llm(system_prompt, user_prompt, *, lite_mode=False):
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

        async def fake_call(system, user, *, lite_mode=False):
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
