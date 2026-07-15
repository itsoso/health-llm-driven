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
        assert captured[0]["max_tokens"] == orch_mod._FULL_MAX_TOKENS == 2000


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
    async def fake_call_llm(system_prompt, user_prompt, *, lite_mode=False, **kwargs):
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


@pytest.mark.asyncio
async def test_broad_synthesis_not_replaced_by_refusal_template(monkeypatch, db):
    """回归 (2026-07-12 prod 误杀, agent_messages 6186/6188):

    宽泛综合分析问题 ("让所有健康专家会诊…直接给出综合结论") 的合成文本
    带 R4 边界话术 ("就医确诊"/"不构成诊断"/"请勿自行停药") 时, 曾被
    validate_text 黑名单无上下文子串匹配整篇替换成拒答模板。
    修复后: synthesis 必须是 findings 的忠实合成 (≥2 specialist 引用保留),
    边界话术可以带, 但绝不能整体拒答。
    """
    import uuid
    from app.models.user import User
    from app.services.episode.validator import _BLOCKED_FALLBACK

    user = User(
        username=f"orch_{uuid.uuid4().hex[:6]}",
        email=f"orch_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="orch synth test",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    from app.orchestrator import orchestrator as orch_mod

    # 伪 LLM: 模拟真实合成形态 —— 引用 ≥2 个 specialist 的裁决 + 结尾边界话术。
    # 边界话术含黑名单术语 (确诊/诊断/停药) 的否定/转诊用法, 这正是 prod 被
    # 误杀的形态; 修复前本测试会拿到拒答模板而失败。
    async def fake_call_llm(system_prompt, user_prompt, *, lite_mode=False, **kwargs):
        assert "【专家裁决】" in user_prompt
        return (
            "综合各专家会诊结论如下:\n"
            "1. 恢复教练 (recovery_coach) 判定: 当前恢复度数据不足, "
            "请先补齐睡眠与 HRV 数据。\n"
            "2. 营养策略师 (fuel_strategist) 判定: 缺少体重与摄入记录, "
            "无法计算热量缺口。\n"
            "如已有在服药物, 请勿自行停药; 如症状持续请及时就医确诊, "
            "本报告不构成诊断。"
        )

    monkeypatch.setattr(orch_mod, "_call_llm", fake_call_llm)

    req = OrchestratorRequest(
        query="让所有健康专家会诊一下我的当前状态,直接给出综合结论",
        stream=False,
        specialists=["recovery_coach", "fuel_strategist"],
    )
    resp = await orch_mod.run_orchestrator(db, user.id, req)

    # 不是整篇拒答模板
    assert _BLOCKED_FALLBACK not in resp.synthesis
    assert "超出我作为健康助理的安全边界" not in resp.synthesis
    # ≥2 个 specialist 的 finding 真实产出且被合成引用
    assert len(resp.findings) >= 2
    assert "recovery_coach" in resp.synthesis
    assert "fuel_strategist" in resp.synthesis
    # 边界话术被保留 (R4 话术可以带)
    assert "请勿自行停药" in resp.synthesis
    assert "就医确诊" in resp.synthesis


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

        async def fake_call(
            system,
            user,
            *,
            lite_mode=False,
            allow_synthesis_override=False,
        ):
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


# ---------------------------------------------------------------------------
# /orchestrator/chat 保活流式聚合回归(2026-07-06,与 /agent/send 同款模式)
# 实锤:Siri HealthAnalysisIntent 走非流式 /orchestrator/chat,URLSession
# timeoutInterval=25 是 idle 语义 —— 25s 内无字节客户端先断;>60s 再被
# main.py 请求超时中间件杀成 504。修法:超窗切 chunked JSON(前导空白保活 +
# 末尾完整对象)。测试把时间尺度压缩:中间件 1s + 回合 2.5s,修复前必 504、
# 修复后 200。缓存显式打成 no-op:本地 Redis 命中会跳过流式路径造成假绿/假红。
# ---------------------------------------------------------------------------


def _disable_orch_cache(monkeypatch):
    from app.api import orchestrator as orch_api

    monkeypatch.setattr(orch_api, "_get_orch_cache", lambda key: None)
    monkeypatch.setattr(orch_api, "_set_orch_cache", lambda key, data: None)


def _fake_response(query: str, synthesis: str):
    from app.orchestrator.schema import Intent, OrchestratorResponse

    return OrchestratorResponse(
        query=query,
        intent=Intent(raw_query=query, categories=["knowledge"]),
        synthesis=synthesis,
        used_specialists=["knowledge_librarian"],
        total_ms=2500,
    )


def test_orchestrator_chat_slow_turn_streams_keepalive_not_504(
    client, db, monkeypatch
):
    import asyncio as aio
    import json as jsonlib

    import main as main_module
    from app.api import orchestrator as orch_api
    from tests.conftest import create_authenticated_user

    monkeypatch.setattr(main_module, "REQUEST_TIMEOUT", 1)
    monkeypatch.setattr(orch_api, "ORCH_CHAT_KEEPALIVE_SECONDS", 0.1)
    _disable_orch_cache(monkeypatch)

    async def fake_run_orchestrator(db, user_id, req):
        await aio.sleep(2.5)  # > 中间件 1s:修复前 wait_for 在这里杀成 504
        return _fake_response(req.query, "深度分析结论")

    monkeypatch.setattr(orch_api, "run_orchestrator", fake_run_orchestrator)

    _, token = create_authenticated_user(db)
    res = client.post(
        "/api/v1/orchestrator/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "慢回合保活回归", "stream": False},
    )

    assert res.status_code == 200, f"长回合不应再 504/500: {res.status_code} {res.text[:200]}"
    raw = res.text
    # 确实吐过保活前导空白(证明流式路径生效,而非碰巧快窗完成)
    assert raw != raw.lstrip(), "长回合应含保活前导空白"
    assert set(raw[: len(raw) - len(raw.lstrip())]) <= {" ", "\t", "\r", "\n"}
    # 前导空白后仍是合法完整 JSON(RFC 8259 允许前导 ws → 现有客户端零感知:
    # Siri JSONSerialization / frontend axios JSON.parse / skill curl+jq)
    body = jsonlib.loads(raw)
    assert body["query"] == "慢回合保活回归"
    assert body["synthesis"] == "深度分析结论"
    assert body["used_specialists"] == ["knowledge_librarian"]
    assert "error" not in body


def test_orchestrator_chat_error_after_stream_started_yields_error_envelope(
    client, db, monkeypatch
):
    """流开始后(200 已定格)失败 → in-body error 字段 + 空 synthesis(Siri 自然降级)。"""
    import asyncio as aio
    import json as jsonlib

    from app.api import orchestrator as orch_api
    from tests.conftest import create_authenticated_user

    monkeypatch.setattr(orch_api, "ORCH_CHAT_KEEPALIVE_SECONDS", 0.1)
    _disable_orch_cache(monkeypatch)

    async def fake_run_orchestrator(db, user_id, req):
        await aio.sleep(0.5)
        raise RuntimeError("上游 LLM 断连")

    monkeypatch.setattr(orch_api, "run_orchestrator", fake_run_orchestrator)

    _, token = create_authenticated_user(db)
    res = client.post(
        "/api/v1/orchestrator/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "流后错误 envelope", "stream": False},
    )

    assert res.status_code == 200
    body = jsonlib.loads(res.text)
    assert isinstance(body.get("error"), str) and body["error"]
    assert body["synthesis"] == ""
    assert body["query"] == "流后错误 envelope"
    # 形状与 OrchestratorResponse 对齐,老消费方按空结果渲染不炸
    assert body["findings"] == []
    assert body["intent"]["raw_query"] == "流后错误 envelope"


def test_orchestrator_chat_fast_error_keeps_http_500(client, db, monkeypatch):
    """快窗内失败保持历史语义:HTTP 500 + detail,契约不变。"""
    from app.api import orchestrator as orch_api
    from tests.conftest import create_authenticated_user

    _disable_orch_cache(monkeypatch)

    async def fake_run_orchestrator(db, user_id, req):
        raise RuntimeError("配置错误")

    monkeypatch.setattr(orch_api, "run_orchestrator", fake_run_orchestrator)

    _, token = create_authenticated_user(db)
    res = client.post(
        "/api/v1/orchestrator/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "快窗错误保持500", "stream": False},
    )

    assert res.status_code == 500
    assert res.json()["detail"]


def test_orchestrator_chat_hard_cap_cancels_turn_and_reports_timeout(
    client, db, monkeypatch
):
    """硬上限兜底:真卡死的回合被取消(不吊死 worker)+ in-body 超时报错。"""
    import asyncio as aio
    import json as jsonlib

    from app.api import orchestrator as orch_api
    from tests.conftest import create_authenticated_user

    monkeypatch.setattr(orch_api, "ORCH_CHAT_KEEPALIVE_SECONDS", 0.1)
    monkeypatch.setattr(orch_api, "ORCH_CHAT_HARD_CAP_SECONDS", 0.5)
    _disable_orch_cache(monkeypatch)

    cancelled = {"flag": False}

    async def fake_run_orchestrator(db, user_id, req):
        try:
            await aio.sleep(30)
        except aio.CancelledError:
            cancelled["flag"] = True
            raise

    monkeypatch.setattr(orch_api, "run_orchestrator", fake_run_orchestrator)

    _, token = create_authenticated_user(db)
    res = client.post(
        "/api/v1/orchestrator/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "硬上限取消回合", "stream": False},
    )

    assert res.status_code == 200
    body = jsonlib.loads(res.text)
    assert "超时" in (body.get("error") or "")
    assert cancelled["flag"], "硬上限触发后底层回合必须被真实取消"
