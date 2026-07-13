# -*- coding: utf-8 -*-
"""rank11 深报告并行分专家段落合成 (ORCHESTRATOR_PARALLEL_SYNTHESIS, ships-OFF)。

闸门:
  - 拼接确定性: 严重度排序(safety first) + ## 标题 + 无 LLM。
  - 段落契约对抗: greeting 确定性剥离; 跨段引用容忍。
  - 安全护栏套拼接整体: 某段含黑名单术语 → 与 mega 同样句级遮蔽 + disclaimer。
  - shadow: 服务文本 == mega (逐字节); shadow 落 audit; shadow 失败绝不影响服务回合。
  - off: 逐字节等于 mega。
  - report_shaped gate: 只对报告形深分析启用。
"""
import asyncio
import uuid

import pytest

from app.orchestrator import orchestrator as orch_mod
from app.orchestrator import parallel_synthesis as ps
from app.orchestrator.schema import OrchestratorRequest, SpecialistFinding


# ──────────────────────────── 单元: 纯确定性层 ────────────────────────────


def _mk(name, sev="medium", summary="概括", *, category=None, items=None):
    return SpecialistFinding(
        specialist_name=name,
        category=category or name,
        summary=summary,
        findings=items if items is not None else [{"severity_label": sev, "title": "t", "action": "a"}],
    )


class TestResolveMode:
    def test_known_values(self):
        assert ps.resolve_mode("off") == "off"
        assert ps.resolve_mode("shadow") == "shadow"
        assert ps.resolve_mode("on") == "on"

    def test_case_and_whitespace(self):
        assert ps.resolve_mode("  SHADOW ") == "shadow"
        assert ps.resolve_mode("On") == "on"

    def test_unknown_fail_closed_off(self):
        assert ps.resolve_mode("garbage") == "off"
        assert ps.resolve_mode(None) == "off"
        assert ps.resolve_mode("") == "off"


class TestReportShapedGate:
    def test_two_substantive_non_lite_true(self):
        assert ps.report_shaped(False, [_mk("recovery_coach"), _mk("fuel_strategist")]) is True

    def test_lite_mode_false(self):
        assert ps.report_shaped(True, [_mk("a"), _mk("b")]) is False

    def test_siri_source_false(self):
        assert ps.report_shaped(False, [_mk("a"), _mk("b")], source="siri") is False

    def test_single_substantive_false(self):
        assert ps.report_shaped(False, [_mk("a")]) is False

    def test_empty_findings_false(self):
        assert ps.report_shaped(False, []) is False

    def test_non_substantive_dont_count(self):
        empty = SpecialistFinding(specialist_name="x", category="x", summary="", findings=[])
        assert ps.report_shaped(False, [empty, empty, _mk("a")]) is False


class TestSelectSections:
    def test_safety_first_then_severity_desc(self):
        findings = [
            _mk("recovery_coach", "low"),
            _mk("safety_guardian", "medium"),
            _mk("metabolic_specialist", "high"),
        ]
        specs = ps.select_sections(findings, cap=5)
        assert [s.label for s in specs] == ["安全", "代谢", "恢复"]
        # 严重度单调不增
        sev = [s.severity for s in specs]
        assert sev == sorted(sev, reverse=True)

    def test_cap_and_merge_overflow(self):
        findings = [_mk(f"sp{i}", "medium", category="c") for i in range(7)]
        specs = ps.select_sections(findings, cap=5)
        assert len(specs) == 5
        assert specs[-1].merged is True
        assert specs[-1].label == "其他观察"
        # 并段包含溢出的 3 个 finding (7 - (5-1))
        assert len(specs[-1].findings) == 3

    def test_stable_order_within_tie(self):
        findings = [_mk("recovery_coach", "low"), _mk("fuel_strategist", "low")]
        specs = ps.select_sections(findings, cap=5)
        assert [s.label for s in specs] == ["恢复", "营养"]

    def test_chinese_severity_labels_ranked(self):
        # safety_guardian 用 label_zh (紧急/警告/…)
        findings = [
            _mk("fuel_strategist", "medium"),
            _mk("safety_guardian", category="safety", items=[{"severity_label": "紧急", "title": "急"}]),
        ]
        specs = ps.select_sections(findings, cap=5)
        assert specs[0].label == "安全"


class TestStripGreeting:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("你好！根据你的HRV数据，建议早睡。", "根据你的HRV数据，建议早睡。"),
            ("您好，根据数据分析如下。", "根据数据分析如下。"),
            ("根据你的数据分析如下。", "根据你的数据分析如下。"),
            ("Hi, here is the analysis.", "here is the analysis."),
            ("嗨嗨~ 这是分析", "这是分析"),
            ("", ""),
        ],
    )
    def test_strip(self, raw, expected):
        assert ps.strip_section_greeting(raw) == expected


class TestStitchDeterminism:
    def test_headers_and_order(self):
        out = ps.stitch([("安全", "结论A"), ("恢复", "结论B")])
        assert "## 安全\n\n结论A" in out
        assert "## 恢复\n\n结论B" in out
        assert out.index("## 安全") < out.index("## 恢复")
        # 无仲裁 → 无开场行
        assert ps._OPENING_WITH_ARBITRATION not in out
        # 结束边界确定性追加
        assert out.rstrip().endswith(ps._CLOSING_BOUNDARY)

    def test_opening_only_when_arbitration(self):
        out = ps.stitch([("安全", "结论A"), ("恢复", "结论B")], arb_block="裁决: 以 A 为准")
        assert out.startswith(ps._OPENING_WITH_ARBITRATION)

    def test_empty_sections_returns_empty(self):
        assert ps.stitch([]) == ""
        # 只有开场没有段落正文 → 空
        assert ps.stitch([], arb_block="x") == ""
        assert ps.stitch([("安全", "   ")], arb_block="x") == ""

    def test_no_llm_in_stitch(self):
        # 纯字符串函数, 相同输入恒定输出
        args = [("安全", "a"), ("恢复", "b")]
        assert ps.stitch(args) == ps.stitch(args)


# ──────────────────────── 单元: run_parallel_sectioned (async) ────────────────────────


def _real_twin():
    from datetime import UTC, datetime

    from app.twin.schema import HealthTwin, TwinMeta

    return HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(UTC)))


@pytest.mark.asyncio
async def test_run_parallel_sectioned_assembles():
    findings = [_mk("recovery_coach", "high", "恢复概括"), _mk("fuel_strategist", "low", "营养概括")]
    calls = []

    async def fake_call(system, user):
        calls.append(user)
        # 按段落维度返回不同文本
        if "【本段专家维度】恢复" in user:
            return "恢复维度的分项结论文本。"
        return "营养维度的分项结论文本。"

    text, meta = await ps.run_parallel_sectioned(
        call_llm=fake_call, query="综合分析", twin=_real_twin(), findings=findings,
    )
    assert "## 恢复\n\n恢复维度的分项结论文本。" in text
    assert "## 营养\n\n营养维度的分项结论文本。" in text
    assert meta["sections"] == 2
    assert meta["sections_failed"] == 0
    assert meta["labels"] == ["恢复", "营养"]  # high 在前
    # 每段一次调用
    assert len(calls) == 2
    # 段落 prompt 携带证据契约
    assert all("support_status=" in u for u in calls)


@pytest.mark.asyncio
async def test_run_parallel_sectioned_one_section_fails_soft():
    findings = [_mk("recovery_coach", "high"), _mk("fuel_strategist", "low")]

    async def fake_call(system, user):
        if "【本段专家维度】营养" in user:
            raise RuntimeError("boom")
        return "恢复结论文本。"

    text, meta = await ps.run_parallel_sectioned(
        call_llm=fake_call, query="q", twin=_real_twin(), findings=findings,
    )
    # 失败段被丢, 其余照拼
    assert "## 恢复" in text
    assert "## 营养" not in text
    assert meta["sections"] == 1
    assert meta["sections_failed"] == 1


@pytest.mark.asyncio
async def test_run_parallel_sectioned_all_fail_returns_empty():
    findings = [_mk("recovery_coach"), _mk("fuel_strategist")]

    async def fake_call(system, user):
        raise RuntimeError("all boom")

    text, meta = await ps.run_parallel_sectioned(
        call_llm=fake_call, query="q", twin=_real_twin(), findings=findings,
    )
    assert text == ""
    assert meta["sections"] == 0
    assert meta["sections_failed"] == 2


@pytest.mark.asyncio
async def test_run_parallel_sectioned_strips_greeting_per_section():
    findings = [_mk("recovery_coach", "high"), _mk("fuel_strategist", "low")]

    async def fake_call(system, user):
        return "你好！这是分项结论。"

    text, _ = await ps.run_parallel_sectioned(
        call_llm=fake_call, query="q", twin=_real_twin(), findings=findings,
    )
    assert "你好" not in text
    assert "这是分项结论。" in text


# ──────────────────────── 集成: run_orchestrator 模式分支 ────────────────────────


def _make_user(db):
    from app.models.user import User

    user = User(
        username=f"ps_{uuid.uuid4().hex[:6]}",
        email=f"ps_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="ps test",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


_MEGA_MARK = "请基于以上信息写回答"


def _forced_report_req():
    # 两个 specialist → ≥2 substantive findings, lite_mode=False → report_shaped=True
    return OrchestratorRequest(
        query="让所有健康专家会诊,给出综合结论",
        stream=False,
        specialists=["recovery_coach", "fuel_strategist"],
    )


@pytest.mark.asyncio
async def test_off_mode_byte_identical_mega(monkeypatch, db):
    monkeypatch.setattr(orch_mod.settings, "orchestrator_parallel_synthesis", "off", raising=False)

    async def fake_call_llm(system_prompt, user_prompt, *, lite_mode=False):
        assert _MEGA_MARK in user_prompt  # off → 只走 mega
        return "MEGA综合结论文本, 足够长以通过安全校验的占位文本。"

    monkeypatch.setattr(orch_mod, "_call_llm", fake_call_llm)
    user = _make_user(db)
    resp = await orch_mod.run_orchestrator(db, user.id, _forced_report_req())
    assert resp.synthesis == "MEGA综合结论文本, 足够长以通过安全校验的占位文本。"


@pytest.mark.asyncio
async def test_on_mode_serves_sectioned(monkeypatch, db):
    monkeypatch.setattr(orch_mod.settings, "orchestrator_parallel_synthesis", "on", raising=False)
    seen = []

    async def fake_call_llm(system_prompt, user_prompt, *, lite_mode=False):
        seen.append(user_prompt)
        return "分项结论文本, 足够长的占位。"

    monkeypatch.setattr(orch_mod, "_call_llm", fake_call_llm)
    user = _make_user(db)
    resp = await orch_mod.run_orchestrator(db, user.id, _forced_report_req())
    # 服务的是分段拼接 (含 ## 标题 + 确定性结束边界)
    assert "## 恢复" in resp.synthesis or "## 营养" in resp.synthesis
    assert ps._CLOSING_BOUNDARY in resp.synthesis
    # mega prompt 从未被用来服务 (on 模式不跑 mega)
    assert all(_MEGA_MARK not in u for u in seen)


@pytest.mark.asyncio
async def test_on_mode_safety_wrap_on_assembled_whole(monkeypatch, db):
    """某段含黑名单术语 → 拼接整体过 _safety_wrap, 句级遮蔽 + disclaimer (与 mega 同)。"""
    monkeypatch.setattr(orch_mod.settings, "orchestrator_parallel_synthesis", "on", raising=False)

    async def fake_call_llm(system_prompt, user_prompt, *, lite_mode=False):
        if "【本段专家维度】营养" in user_prompt:
            return "坚持这个补充方案就可以治愈你的高血压问题。"
        return "根据你的恢复数据, 建议今晚早点休息, 保证睡眠七小时以上, 明天再评估训练强度。"

    monkeypatch.setattr(orch_mod, "_call_llm", fake_call_llm)
    user = _make_user(db)
    resp = await orch_mod.run_orchestrator(db, user.id, _forced_report_req())
    # 越界句被句级遮蔽
    assert "可以治愈" not in resp.synthesis
    # 其余段落保留
    assert "根据你的恢复数据" in resp.synthesis
    # 安全动作与 mega 一致 (replace + disclaimer)
    assert resp.safety_action == "replace"
    assert resp.safety_disclaimer


@pytest.mark.asyncio
async def test_shadow_serves_mega_and_persists(monkeypatch, db):
    monkeypatch.setattr(orch_mod.settings, "orchestrator_parallel_synthesis", "shadow", raising=False)
    captured = {}

    def fake_log(db, *, user_id, query, text, meta):
        captured["user_id"] = user_id
        captured["text"] = text
        captured["meta"] = meta
        return 1

    # worker lazy-imports log_shadow_synthesis from audit module → patch there
    monkeypatch.setattr("app.agents.audit.log_shadow_synthesis", fake_log)

    async def fake_call_llm(system_prompt, user_prompt, *, lite_mode=False):
        if _MEGA_MARK in user_prompt:
            return "MEGA服务文本, 足够长的占位以通过校验。"
        return "分项结论文本占位。"

    monkeypatch.setattr(orch_mod, "_call_llm", fake_call_llm)
    user = _make_user(db)
    resp = await orch_mod.run_orchestrator(db, user.id, _forced_report_req())

    # 服务文本 == mega (逐字节, shadow 不改变用户可见行为)
    assert resp.synthesis == "MEGA服务文本, 足够长的占位以通过校验。"

    # 排空后台 shadow task, 断言影子样本落库
    await asyncio.gather(*list(orch_mod._BACKGROUND_STREAM_TASKS), return_exceptions=True)
    assert captured.get("user_id") == user.id
    assert captured["meta"]["sections"] >= 2
    assert "## " in captured["text"]  # 分段拼接文本


@pytest.mark.asyncio
async def test_shadow_failure_never_affects_served_turn(monkeypatch, db):
    monkeypatch.setattr(orch_mod.settings, "orchestrator_parallel_synthesis", "shadow", raising=False)

    async def fake_call_llm(system_prompt, user_prompt, *, lite_mode=False):
        if _MEGA_MARK in user_prompt:
            return "MEGA服务文本占位, 足够长以过校验。"
        raise RuntimeError("section boom in shadow")

    monkeypatch.setattr(orch_mod, "_call_llm", fake_call_llm)
    user = _make_user(db)
    # run_orchestrator 不应因 shadow 失败抛出
    resp = await orch_mod.run_orchestrator(db, user.id, _forced_report_req())
    assert resp.synthesis == "MEGA服务文本占位, 足够长以过校验。"
    # 排空 bg task (即便内部全失败也 fail-soft 不抛)
    await asyncio.gather(*list(orch_mod._BACKGROUND_STREAM_TASKS), return_exceptions=True)


@pytest.mark.asyncio
async def test_on_mode_empty_sections_falls_back_to_mega(monkeypatch, db):
    """'on' 全段失败(空产出)→ fail-closed 回落 mega, 回合仍有正文。"""
    monkeypatch.setattr(orch_mod.settings, "orchestrator_parallel_synthesis", "on", raising=False)

    async def fake_call_llm(system_prompt, user_prompt, *, lite_mode=False):
        if _MEGA_MARK in user_prompt:  # mega 回落
            return "MEGA回落文本占位, 足够长以过校验。"
        raise RuntimeError("all sections boom")  # 段落全失败

    monkeypatch.setattr(orch_mod, "_call_llm", fake_call_llm)
    user = _make_user(db)
    resp = await orch_mod.run_orchestrator(db, user.id, _forced_report_req())
    assert resp.synthesis == "MEGA回落文本占位, 足够长以过校验。"
    assert "## " not in resp.synthesis


@pytest.mark.asyncio
async def test_non_report_shaped_uses_mega_even_when_on(monkeypatch, db):
    """lite/单专家 (非报告形) 即便 flag=on 也走 mega (gate 收窄)。"""
    monkeypatch.setattr(orch_mod.settings, "orchestrator_parallel_synthesis", "on", raising=False)
    seen = []

    async def fake_call_llm(system_prompt, user_prompt, *, lite_mode=False):
        seen.append(user_prompt)
        return "MEGA单专家文本占位, 足够长。"

    monkeypatch.setattr(orch_mod, "_call_llm", fake_call_llm)
    user = _make_user(db)
    req = OrchestratorRequest(
        query="我能同时吃布洛芬和华法林吗", stream=False, specialists=["safety_guardian"],
    )
    resp = await orch_mod.run_orchestrator(db, user.id, req)
    # 单专家 → 非报告形 → mega
    assert any(_MEGA_MARK in u for u in seen)
    assert "## " not in resp.synthesis
