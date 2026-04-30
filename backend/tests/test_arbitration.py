"""LLM 仲裁层单元测试 — 不 mock LLM 也覆盖 prompt / parser / gating 逻辑."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.orchestrator.arbitration import (
    ArbitrationResult,
    _build_arbitration_prompt,
    _parse_arbitration_response,
    _should_arbitrate,
    arbitrate_conflicts,
    render_arbitration_for_prompt,
)
from app.orchestrator.cross_review import Conflict
from app.orchestrator.schema import SpecialistFinding
from app.twin.schema import HealthTwin, TwinMeta, PhysiologicalState


def _mk_twin(hrv=None, rhr=None):
    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(UTC)))
    twin.physiological = PhysiologicalState(hrv_latest=hrv, resting_hr=rhr)
    return twin


def _mk_finding(name, summary="", raw=None):
    return SpecialistFinding(
        specialist_name=name,
        category="general",
        summary=summary,
        findings=[],
        raw=raw or {},
    )


def _mk_conflict(severity="hard", a="fuel", b="metabolic"):
    return Conflict(
        specialist_a=a, specialist_b=b, severity=severity,
        description=f"{a} 推蛋白 vs {b} 肾脏风险",
        resolution_hint="暂按保守方案",
    )


# ───────────────── _should_arbitrate ─────────────────

class TestShouldArbitrate:
    def test_empty_no(self):
        assert _should_arbitrate([]) is False

    def test_single_soft_no(self):
        assert _should_arbitrate([_mk_conflict("soft")]) is False

    def test_single_hard_yes(self):
        assert _should_arbitrate([_mk_conflict("hard")]) is True

    def test_two_soft_yes(self):
        assert _should_arbitrate([_mk_conflict("soft"), _mk_conflict("soft")]) is True

    def test_mixed_yes(self):
        assert _should_arbitrate([_mk_conflict("soft"), _mk_conflict("hard")]) is True


# ───────────────── _build_arbitration_prompt ─────────────────

class TestBuildArbitrationPrompt:
    def test_system_contains_json_contract(self):
        twin = _mk_twin(hrv=45)
        conflicts = [_mk_conflict()]
        findings = [_mk_finding("fuel", "推蛋白"), _mk_finding("metabolic", "限热量")]
        sys, user = _build_arbitration_prompt(conflicts, findings, twin)
        assert "winning_side" in sys
        assert "rationale" in sys
        assert "final_recommendation" in sys
        assert "caveats" in sys
        assert "confidence" in sys

    def test_user_contains_conflict_and_findings(self):
        twin = _mk_twin(hrv=45)
        conflicts = [_mk_conflict()]
        findings = [_mk_finding("fuel", "推蛋白 protein"), _mk_finding("metabolic", "高肌酐")]
        _, user = _build_arbitration_prompt(conflicts, findings, twin)
        assert "fuel" in user
        assert "metabolic" in user
        assert "推蛋白" in user

    def test_twin_digest_in_prompt(self):
        twin = _mk_twin(hrv=45, rhr=65)
        conflicts = [_mk_conflict()]
        _, user = _build_arbitration_prompt(conflicts, [], twin)
        assert "HRV=45" in user or "45" in user

    def test_only_conflict_specialists_findings_included(self):
        """findings 只挑 conflict 涉及的 specialist, 避免 prompt 膨胀."""
        twin = _mk_twin()
        conflicts = [_mk_conflict(a="fuel", b="metabolic")]
        findings = [
            _mk_finding("fuel", "FUEL_SUMMARY"),
            _mk_finding("metabolic", "METABOLIC_SUMMARY"),
            _mk_finding("movement", "MOVEMENT_SUMMARY_UNRELATED"),
        ]
        _, user = _build_arbitration_prompt(conflicts, findings, twin)
        assert "FUEL_SUMMARY" in user
        assert "METABOLIC_SUMMARY" in user
        assert "MOVEMENT_SUMMARY_UNRELATED" not in user


# ───────────────── _parse_arbitration_response ─────────────────

class TestParseArbitrationResponse:
    def test_clean_json(self):
        text = """{"winning_side": "specialist_a", "rationale": "用户肌酐正常 200", "final_recommendation": "优先蛋白", "caveats": ["监测肌酐"], "confidence": 0.82}"""
        r = _parse_arbitration_response(text, conflicts_count=1)
        assert r is not None
        assert r.winning_side == "specialist_a"
        assert r.confidence == 0.82
        assert r.caveats == ["监测肌酐"]
        assert r.conflicts_addressed == 1

    def test_wrapped_in_prose(self):
        text = """这是我的裁决: {"winning_side": "both", "rationale": "两方都成立", "final_recommendation": "分场景", "caveats": [], "confidence": 0.65} 以上."""
        r = _parse_arbitration_response(text, conflicts_count=2)
        assert r is not None
        assert r.winning_side == "both"
        assert r.confidence == 0.65

    def test_invalid_winning_side_defaults_to_neither(self):
        text = '{"winning_side": "random", "rationale": "", "final_recommendation": "", "caveats": [], "confidence": 0.5}'
        r = _parse_arbitration_response(text, 1)
        assert r.winning_side == "neither"

    def test_confidence_out_of_range_clamped(self):
        text = '{"winning_side": "both", "rationale": "", "final_recommendation": "", "caveats": [], "confidence": 1.5}'
        r = _parse_arbitration_response(text, 1)
        assert r.confidence == 1.0

        text2 = '{"winning_side": "both", "rationale": "", "final_recommendation": "", "caveats": [], "confidence": -0.5}'
        r2 = _parse_arbitration_response(text2, 1)
        assert r2.confidence == 0.0

    def test_confidence_non_numeric_fallback(self):
        text = '{"winning_side": "both", "rationale": "", "final_recommendation": "", "caveats": [], "confidence": "high"}'
        r = _parse_arbitration_response(text, 1)
        assert r.confidence == 0.7  # fallback default

    def test_caveats_truncated_to_5(self):
        caveats = [f"c{i}" for i in range(10)]
        import json
        text = json.dumps({
            "winning_side": "both", "rationale": "", "final_recommendation": "",
            "caveats": caveats, "confidence": 0.5,
        })
        r = _parse_arbitration_response(text, 1)
        assert len(r.caveats) == 5

    def test_empty_text_returns_none(self):
        assert _parse_arbitration_response("", 1) is None

    def test_no_json_returns_none(self):
        assert _parse_arbitration_response("我觉得采纳 A 方", 1) is None


# ───────────────── arbitrate_conflicts (integration) ─────────────────

class TestArbitrateConflicts:
    @pytest.mark.asyncio
    async def test_skip_when_no_conflict(self):
        llm = AsyncMock(return_value="{}")
        result = await arbitrate_conflicts([], [], _mk_twin(), llm)
        assert result is None
        llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_when_single_soft(self):
        llm = AsyncMock(return_value="{}")
        result = await arbitrate_conflicts([_mk_conflict("soft")], [], _mk_twin(), llm)
        assert result is None
        llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_trigger_on_hard(self):
        mock_resp = '{"winning_side": "specialist_a", "rationale": "x", "final_recommendation": "y", "caveats": [], "confidence": 0.8}'
        llm = AsyncMock(return_value=mock_resp)
        result = await arbitrate_conflicts(
            [_mk_conflict("hard")], [], _mk_twin(), llm,
        )
        assert result is not None
        assert result.winning_side == "specialist_a"
        llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_on_llm_exception(self):
        llm = AsyncMock(side_effect=RuntimeError("network fail"))
        result = await arbitrate_conflicts(
            [_mk_conflict("hard")], [], _mk_twin(), llm,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_fallback_on_unparseable(self):
        llm = AsyncMock(return_value="LLM 乱说一通没有 JSON")
        result = await arbitrate_conflicts(
            [_mk_conflict("hard")], [], _mk_twin(), llm,
        )
        assert result is None


# ───────────────── render_arbitration_for_prompt ─────────────────

class TestRenderForPrompt:
    def test_render_has_key_sections(self):
        arb = ArbitrationResult(
            winning_side="specialist_a",
            rationale="用户化验正常",
            final_recommendation="每日蛋白 1.5g/kg",
            caveats=["监测肌酐"],
            confidence=0.82,
            conflicts_addressed=1,
        )
        text = render_arbitration_for_prompt(arb)
        assert "LLM 仲裁" in text
        assert "specialist_a" in text
        assert "用户化验正常" in text
        assert "每日蛋白 1.5g/kg" in text
        assert "监测肌酐" in text
        assert "0.82" in text
