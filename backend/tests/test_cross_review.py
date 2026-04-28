"""Cross-Review specialist 矛盾检测测试."""
from datetime import datetime, timezone

import pytest

from app.orchestrator.cross_review import (
    detect_conflicts,
    render_conflicts_for_prompt,
    Conflict,
    _check_protein_vs_kidney,
    _check_movement_vs_recovery,
    _check_alcohol_directive,
)
from app.orchestrator.schema import SpecialistFinding


def _twin(creatinine=None, user_id=1):
    from app.twin.schema import HealthTwin, TwinMeta, LabsContext
    twin = HealthTwin(meta=TwinMeta(user_id=user_id, generated_at=datetime.now(timezone.utc)))
    if creatinine is not None:
        twin.labs = LabsContext()
        # creatinine 不在标准字段, 用动态 setattr 模拟
        try:
            twin.labs.creatinine = creatinine
        except Exception:
            pass
    return twin


# ─────────── 蛋白 vs 肾 ───────────


class TestProteinVsKidney:
    def test_high_protein_advice_with_high_creatinine_conflicts(self):
        fuel = SpecialistFinding(
            specialist_name="fuel_strategist", category="fuel",
            summary="蛋白每日 ≥ 1.6g/kg, 增加红肉",
        )
        twin = _twin(creatinine=140)
        out = _check_protein_vs_kidney([fuel], twin)
        assert len(out) == 1
        assert out[0].severity == "hard"
        assert "肾" in out[0].description

    def test_no_high_protein_advice_no_conflict(self):
        fuel = SpecialistFinding(
            specialist_name="fuel_strategist", category="fuel",
            summary="今日热量正常, 注意水分",
        )
        twin = _twin(creatinine=140)
        assert _check_protein_vs_kidney([fuel], twin) == []

    def test_high_protein_normal_creatinine_no_conflict(self):
        fuel = SpecialistFinding(
            specialist_name="fuel_strategist", category="fuel",
            summary="蛋白每日 ≥ 1.6g/kg",
        )
        twin = _twin(creatinine=80)
        assert _check_protein_vs_kidney([fuel], twin) == []

    def test_no_fuel_finding_no_conflict(self):
        twin = _twin(creatinine=140)
        assert _check_protein_vs_kidney([], twin) == []


# ─────────── 训练 vs 恢复 ───────────


class TestMovementVsRecovery:
    def _make(self, rec_zone, mov_status):
        rec = SpecialistFinding(
            specialist_name="recovery_coach", category="recovery",
            summary="x", raw={"zone": rec_zone, "score": 30 if rec_zone == "rest" else 70},
        )
        mov = SpecialistFinding(
            specialist_name="movement_coach", category="movement",
            summary="x", raw={"status": mov_status},
        )
        return [rec, mov]

    def test_undertrained_with_rest_conflicts(self):
        twin = _twin()
        out = _check_movement_vs_recovery(self._make("rest", "undertrained"), twin)
        assert len(out) == 1
        assert out[0].severity == "soft"

    def test_optimal_with_moderate_no_conflict(self):
        twin = _twin()
        assert _check_movement_vs_recovery(self._make("moderate", "optimal"), twin) == []

    def test_only_one_specialist_no_conflict(self):
        # 没 movement
        rec = SpecialistFinding(specialist_name="recovery_coach", category="recovery",
                               raw={"zone": "rest"})
        twin = _twin()
        assert _check_movement_vs_recovery([rec], twin) == []


# ─────────── 戒酒 directive vs Fuel finding ───────────


class TestAlcoholDirective:
    def test_directive_active_fuel_mentions_alcohol_conflicts(self, db):
        from app.models.user_directive import UserDirective
        # 先创建 user directive
        d = UserDirective(
            user_id=42, kind="lifestyle",
            instruction="严格戒酒 30 天", severity="strong",
            status="active", source="user_self",
        )
        db.add(d)
        db.commit()

        fuel = SpecialistFinding(
            specialist_name="fuel_strategist", category="fuel",
            summary="今日热量超标, 包含红酒一杯",
        )
        twin = _twin(user_id=42)
        out = _check_alcohol_directive([fuel], twin, db)
        assert len(out) == 1
        assert "戒酒" in out[0].description

    def test_no_directive_no_conflict(self, db):
        fuel = SpecialistFinding(
            specialist_name="fuel_strategist", category="fuel",
            summary="今日含红酒一杯",
        )
        twin = _twin(user_id=42)
        assert _check_alcohol_directive([fuel], twin, db) == []

    def test_fuel_already_says_quit_no_conflict(self, db):
        from app.models.user_directive import UserDirective
        d = UserDirective(user_id=42, kind="lifestyle", instruction="戒酒",
                         severity="strong", status="active", source="user_self")
        db.add(d)
        db.commit()

        fuel = SpecialistFinding(
            specialist_name="fuel_strategist", category="fuel",
            summary="戒酒维持中, 未饮酒",
        )
        twin = _twin(user_id=42)
        # fuel 没违反, 不应触发
        assert _check_alcohol_directive([fuel], twin, db) == []


# ─────────── render ───────────


class TestRender:
    def test_empty_returns_empty(self):
        assert render_conflicts_for_prompt([]) == ""

    def test_renders_severity_emoji(self):
        c = Conflict(specialist_a="x", specialist_b="y", severity="hard",
                     description="desc", resolution_hint="hint")
        out = render_conflicts_for_prompt([c])
        assert "🔴 hard" in out
        assert "x vs y" in out
        assert "desc" in out
        assert "hint" in out

    def test_renders_soft(self):
        c = Conflict(specialist_a="x", specialist_b="y", severity="soft",
                     description="d", resolution_hint="h")
        out = render_conflicts_for_prompt([c])
        assert "🟡 soft" in out


# ─────────── 端到端 detect_conflicts ───────────


class TestDetectConflicts:
    def test_aggregates_multiple_checks(self):
        # 触发蛋白+肾 + 训练+恢复 两个矛盾
        fuel = SpecialistFinding(
            specialist_name="fuel_strategist", category="fuel",
            summary="蛋白每日 ≥ 1.8g/kg",
        )
        rec = SpecialistFinding(
            specialist_name="recovery_coach", category="recovery",
            raw={"zone": "rest"},
        )
        mov = SpecialistFinding(
            specialist_name="movement_coach", category="movement",
            raw={"status": "undertrained"},
        )
        twin = _twin(creatinine=145)
        out = detect_conflicts([fuel, rec, mov], twin, db=None)
        # 至少 2 (protein-kidney + movement-recovery)
        assert len(out) >= 2
