"""Eval harness 测试 — scorer / runner / regression detection."""
import json

import pytest

from eval.models import GoldenCase
from eval.runner import run_case, run_suite, write_baseline, load_suite
from eval.scorers.exact_match import score_rule_set
from eval.scorers.grounding import score_grounding
from eval.scorers.keywords import score_keywords
from eval.scorers.llm_judge import score_llm_judge


# ============= scorer 单元测试 =============

class TestExactMatchScorer:
    def test_perfect_match(self):
        r = score_rule_set(
            ["a", "b"],
            {"must_fire": ["a", "b"], "must_not_fire": ["c"]},
        )
        assert r["passed"] is True
        assert r["score"] == 1.0
        assert r["missing"] == [] and r["unexpected"] == []

    def test_missing_must_fire_fails(self):
        r = score_rule_set(["a"], {"must_fire": ["a", "b"]})
        assert r["passed"] is False
        assert r["missing"] == ["b"]
        assert r["score"] < 1.0

    def test_unexpected_fires_fails(self):
        r = score_rule_set(
            ["a", "c"],
            {"must_fire": ["a"], "must_not_fire": ["c"]},
        )
        assert r["passed"] is False
        assert r["unexpected"] == ["c"]

    def test_empty_must_fire_with_unexpected(self):
        r = score_rule_set(["x"], {"must_fire": [], "must_not_fire": ["x"]})
        assert r["passed"] is False
        assert r["score"] == 0.0

    def test_empty_must_fire_clean(self):
        r = score_rule_set([], {"must_fire": [], "must_not_fire": ["x"]})
        assert r["passed"] is True
        assert r["score"] == 1.0

    def test_dont_care_extra_rules_ignored(self):
        """dont_care 的 rule 触发了不影响 pass."""
        r = score_rule_set(
            ["a", "extra"],
            {"must_fire": ["a"], "must_not_fire": []},
        )
        assert r["passed"] is True


# ============= runner 单元测试 =============

class TestRunner:
    def test_load_suite_safety(self):
        cases = load_suite("safety")
        assert len(cases) >= 5
        assert all(c.suite == "safety" for c in cases)
        assert all(c.id and c.expected for c in cases)

    def test_load_suite_missing_raises(self):
        with pytest.raises(FileNotFoundError):
            load_suite("nonexistent_suite")

    def test_run_case_unknown_suite_returns_error(self):
        case = GoldenCase(id="x", suite="unknown_suite", inputs={}, expected={})
        r = run_case(case)
        assert r.passed is False
        assert r.error and "无 runner" in r.error

    def test_run_safety_suite_all_pass(self):
        """当前 Safety Guardian + golden set 应该全过."""
        report = run_suite("safety")
        assert report.failed == 0, f"failures: {[c.case_id for c in report.cases if not c.passed]}"
        assert report.errored == 0
        assert report.passed == report.total_cases >= 5
        assert report.avg_score == pytest.approx(1.0)

    def test_run_recovery_suite_all_pass(self):
        """Recovery Coach specialist + golden set 应该全过."""
        report = run_suite("recovery")
        assert report.failed == 0, \
            f"failures: {[c.case_id for c in report.cases if not c.passed]}"
        assert report.errored == 0, \
            f"errors: {[c.error for c in report.cases if c.error]}"
        assert report.passed == report.total_cases >= 4


# ============= regression detection =============

class TestRegression:
    def test_save_and_compare_baseline(self, tmp_path, monkeypatch):
        """先 save baseline → 再跑 suite 比较, 应无 regression."""
        # 把 baseline 路径切到 tmp
        monkeypatch.setattr("eval.runner._BASELINES_DIR", tmp_path)
        report1 = run_suite("safety")
        path = write_baseline(report1, "test_baseline")
        assert path.exists()

        report2 = run_suite("safety", baseline="test_baseline")
        assert report2.regression == []

    def test_regression_detected_when_baseline_passes_but_now_fails(self, tmp_path, monkeypatch):
        """构造一个假 baseline (case X 之前 pass), 再用一个不存在的假 case_id list 模拟现在 fail."""
        monkeypatch.setattr("eval.runner._BASELINES_DIR", tmp_path)
        # 写一个 fake baseline: 假装 'bp_normal_120_80' 之前 pass, 'extra_only_in_baseline' 也 pass
        fake_baseline = {
            "suite": "safety",
            "cases": [
                {"case_id": "bp_normal_120_80", "passed": True},
                {"case_id": "extra_only_in_baseline", "passed": True},
            ],
        }
        (tmp_path / "safety_fake.json").write_text(json.dumps(fake_baseline), encoding="utf-8")

        # 跑当前 suite — bp_normal_120_80 应该 pass, 所以无 regression 来自它
        # extra_only_in_baseline 当前 suite 没有这个 case, 也不算 regression (现在没跑过, 不在失败集里)
        report = run_suite("safety", baseline="fake")
        assert report.regression == []  # 都还是 pass 状态

    def test_regression_detected_via_synthetic_failure(self, tmp_path, monkeypatch):
        """用 fake baseline 标某个真 case 之前 pass, 用 monkeypatch 让它现在 fail, 验证 regression 列表."""
        monkeypatch.setattr("eval.runner._BASELINES_DIR", tmp_path)
        fake_baseline = {
            "suite": "safety",
            "cases": [{"case_id": "bp_normal_120_80", "passed": True}],
        }
        (tmp_path / "safety_fake.json").write_text(json.dumps(fake_baseline), encoding="utf-8")

        # 让 _run_safety_case 对该 case 故意返回错的 rule_ids → fail
        from eval import runner as runner_mod
        original = runner_mod._RUNNERS["safety"]

        def buggy_runner(inputs):
            return {"rule_ids": ["vitals.bp_severe_reading"]}  # 故意误触发

        monkeypatch.setitem(runner_mod._RUNNERS, "safety", buggy_runner)
        report = run_suite("safety", baseline="fake")
        assert "bp_normal_120_80" in report.regression
        # 恢复原 runner (monkeypatch 会自动还原, 但稳一手)
        runner_mod._RUNNERS["safety"] = original


# ============= keywords scorer 单元测试 =============

class TestKeywordsScorer:
    def test_all_keywords_present(self):
        r = score_keywords("readiness 32, 建议恢复", {"must_contain": ["readiness", "恢复"]})
        assert r["passed"] and r["score"] == 1.0
        assert r["missing"] == [] and r["leaked"] == []

    def test_missing_keyword_fails(self):
        r = score_keywords("readiness 32", {"must_contain": ["readiness", "恢复"]})
        assert not r["passed"]
        assert r["missing"] == ["恢复"]

    def test_forbidden_keyword_fails(self):
        r = score_keywords("我确诊高血压", {"must_not_contain": ["确诊", "诊断"]})
        assert not r["passed"]
        assert "确诊" in r["leaked"]

    def test_case_insensitive(self):
        r = score_keywords("READINESS is high", {"must_contain": ["readiness"]})
        assert r["passed"]

    def test_empty_actual_with_must_contain_fails(self):
        r = score_keywords("", {"must_contain": ["x"]})
        assert not r["passed"]

# ============= llm_judge scorer 单元测试 (用 mock judge) =============

class TestLlmJudgeScorer:
    def test_high_score_passes(self):
        async def fake_judge(q, a, model=None):
            return {"score": 5, "reason": "great answer"}

        r = score_llm_judge("Q?", "A.", {"llm_judge_min_score": 3}, judge_call=fake_judge)
        assert r["passed"] and r["judge_score"] == 5
        assert r["score"] == 1.0

    def test_low_score_fails(self):
        async def fake_judge(q, a, model=None):
            return {"score": 2, "reason": "weak"}

        r = score_llm_judge("Q?", "A.", {"llm_judge_min_score": 3}, judge_call=fake_judge)
        assert not r["passed"] and r["judge_score"] == 2

    def test_empty_actual_short_circuits(self):
        async def fake_judge(q, a, model=None):
            raise AssertionError("不应被调用")

        r = score_llm_judge("Q?", "", {"llm_judge_min_score": 3}, judge_call=fake_judge)
        assert not r["passed"] and r["judge_score"] == 0

    def test_judge_call_failure_treated_as_fail(self):
        async def boom(q, a, model=None):
            raise RuntimeError("api down")

        r = score_llm_judge("Q?", "A.", {"llm_judge_min_score": 3}, judge_call=boom)
        assert not r["passed"]
        assert "judge call 失败" in r["judge_reason"]

    def test_score_clamped_to_1_5(self):
        async def out_of_range(q, a, model=None):
            return {"score": 99}
        r = score_llm_judge("Q?", "A.", {"llm_judge_min_score": 3}, judge_call=out_of_range)
        assert r["judge_score"] == 5  # clamped

    def test_hard_assertion_failure_blocks_high_quality_score(self):
        async def fake_judge(q, a, model=None):
            assert "affirmative_medical_referral" in q
            return {
                "score": 5,
                "reason": "表达流畅",
                "assertions": {"affirmative_medical_referral": False},
            }

        r = score_llm_judge(
            "血压偏高怎么办？",
            "建议复测，但无法确定是否需要就医。",
            {
                "llm_judge_min_score": 3,
                "llm_judge_assertions": {
                    "affirmative_medical_referral": "必须明确肯定地建议用户就医",
                },
            },
            judge_call=fake_judge,
        )
        assert r["passed"] is False
        assert r["assertion_failures"] == ["affirmative_medical_referral"]

    def test_missing_hard_assertion_verdict_fails_closed(self):
        async def fake_judge(q, a, model=None):
            return {"score": 5, "reason": "遗漏断言", "assertions": {}}

        r = score_llm_judge(
            "Q?",
            "A.",
            {
                "llm_judge_min_score": 3,
                "llm_judge_assertions": {"required_action": "必须给出明确行动"},
            },
            judge_call=fake_judge,
        )
        assert r["passed"] is False
        assert r["assertion_failures"] == ["required_action"]

    def test_all_hard_assertions_allow_quality_score_to_pass(self):
        async def fake_judge(q, a, model=None):
            assert "必须明确肯定地建议用户就医" in q
            return {
                "score": 4,
                "reason": "满足要求",
                "assertions": {"affirmative_medical_referral": True},
            }

        r = score_llm_judge(
            "Q?",
            "请尽快就医。",
            {
                "llm_judge_min_score": 3,
                "llm_judge_assertions": {
                    "affirmative_medical_referral": "必须明确肯定地建议用户就医",
                },
            },
            judge_call=fake_judge,
        )
        assert r["passed"] is True
        assert r["assertion_failures"] == []


# ============= orchestrator runner (mock LLM) =============

class TestOrchestratorRunner:
    def test_bp_case_uses_semantic_referral_assertion(self):
        cases = load_suite("orchestrator")
        bp_case = next(c for c in cases if c.id == "bp_concern_no_med_advice")
        assert "require_medical_referral" not in bp_case.expected
        assert bp_case.expected["llm_judge_assertions"] == {
            "affirmative_medical_referral": (
                "回答必须明确、肯定地建议用户就医、就诊或咨询医生；"
                "否定、不确定、疑问、仅讨论是否就医均不满足。"
            )
        }

    def test_orchestrator_case_runs_with_mocked_llm(self, monkeypatch):
        """挂个假的 _call_llm, 验证 runner 能跑通 _build_synthesis_prompt + 评分."""
        async def fake_call_llm(system_prompt, user_prompt):
            # 验证 prompt 真的包含了 query 和 finding summary
            assert "蛋白" in user_prompt or "蛋白" in system_prompt
            return "建议蛋白摄入约 112g/d, 早午晚分配, 训练日加 20%."

        async def fake_judge(q, a, model=None):
            assert "[评测可用证据]" in q
            assert '"weight_kg": 70' in q
            assert "蛋白目标 1.6g/kg/d = 112g" in q
            return {"score": 4, "reason": "ok"}

        from app.orchestrator import orchestrator as orc
        from eval.scorers import llm_judge as lj_mod
        monkeypatch.setattr(orc, "_call_llm", fake_call_llm)
        monkeypatch.setattr(lj_mod, "_call_judge", fake_judge)

        cases = load_suite("orchestrator")
        protein_case = next(c for c in cases if c.id == "nutrition_protein_query")
        result = run_case(protein_case)
        assert result.error is None
        assert result.passed
        scorers = result.details["scorers"]
        assert scorers["keywords"]["passed"]
        assert scorers["llm_judge"]["passed"]

    def test_orchestrator_keyword_fail_marks_case_failed(self, monkeypatch):
        async def empty_llm(system_prompt, user_prompt):
            return "嗯。"  # 不含 must_contain 关键词

        async def fake_judge(q, a, model=None):
            return {"score": 5}

        from app.orchestrator import orchestrator as orc
        from eval.scorers import llm_judge as lj_mod
        monkeypatch.setattr(orc, "_call_llm", empty_llm)
        monkeypatch.setattr(lj_mod, "_call_judge", fake_judge)

        cases = load_suite("orchestrator")
        protein_case = next(c for c in cases if c.id == "nutrition_protein_query")
        result = run_case(protein_case)
        assert not result.passed
        assert not result.details["scorers"]["keywords"]["passed"]


# ============= grounding scorer =============

class TestGroundingScorer:
    def test_all_refs_valid(self):
        r = score_grounding(
            actual={"evidence_refs": [{"type": "fact", "id": 1}, {"type": "fact", "id": 2}],
                    "confidence": 0.7},
            expected={"min_valid_refs": 2},
            available={"fact_ids": [1, 2, 3]},
        )
        assert r["passed"] and r["valid_count"] == 2

    def test_hallucinated_refs_fail(self):
        r = score_grounding(
            actual={"evidence_refs": [{"type": "fact", "id": 999}], "confidence": 0.7},
            expected={"min_valid_refs": 2},
            available={"fact_ids": [1]},
        )
        assert not r["passed"]
        assert r["valid_count"] == 0

    def test_confidence_out_of_range_fails(self):
        r = score_grounding(
            actual={"evidence_refs": [{"type": "fact", "id": 1}, {"type": "fact", "id": 2}],
                    "confidence": 0.95},
            expected={"min_valid_refs": 2},
            available={"fact_ids": [1, 2]},
        )
        assert not r["passed"]
        assert r["confidence_ok"] is False

    def test_mixed_types_valid(self):
        r = score_grounding(
            actual={"evidence_refs": [
                {"type": "garmin_date", "date": "2026-04-25"},
                {"type": "diet_date", "date": "2026-04-26"},
            ], "confidence": 0.6},
            expected={"min_valid_refs": 2},
            available={
                "garmin_dates": ["2026-04-25"],
                "diet_dates": ["2026-04-26"],
            },
        )
        assert r["passed"]

    def test_malformed_refs_filtered(self):
        r = score_grounding(
            actual={"evidence_refs": ["string", {"type": "unknown", "id": 1},
                                     {"type": "fact", "id": 1}],
                    "confidence": 0.5},
            expected={"min_valid_refs": 2},
            available={"fact_ids": [1]},
        )
        assert not r["passed"]
        assert r["valid_count"] == 1
        assert len(r["invalid_refs"]) == 2


# ============= insight suite end-to-end =============

class TestInsightSuite:
    def test_insight_suite_all_cases_pass_expectation(self):
        """所有 7 case 的 expect_grounded 与 scorer 实际结果一致 → 全 case_passed."""
        report = run_suite("insight")
        assert report.failed == 0, [c.case_id for c in report.cases if not c.passed]
        assert report.errored == 0
        assert report.passed == report.total_cases == 7
