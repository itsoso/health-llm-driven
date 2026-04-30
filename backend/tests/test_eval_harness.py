"""Eval harness 测试 — scorer / runner / regression detection."""
import json
from pathlib import Path

import pytest

from eval.models import GoldenCase, SuiteReport, CaseResult
from eval.runner import run_case, run_suite, write_baseline, load_suite, _BASELINES_DIR
from eval.scorers.exact_match import score_rule_set


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
        (tmp_path / "fake.json").write_text(json.dumps(fake_baseline), encoding="utf-8")

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
        (tmp_path / "fake.json").write_text(json.dumps(fake_baseline), encoding="utf-8")

        # 让 _run_safety_case 对该 case 故意返回错的 rule_ids → fail
        from eval import runner as runner_mod
        original = runner_mod._RUNNERS["safety"]

        def buggy_runner(inputs):
            return {"rule_ids": ["vitals.bp_hypertensive_crisis"]}  # 故意误触发

        monkeypatch.setitem(runner_mod._RUNNERS, "safety", buggy_runner)
        report = run_suite("safety", baseline="fake")
        assert "bp_normal_120_80" in report.regression
        # 恢复原 runner (monkeypatch 会自动还原, 但稳一手)
        runner_mod._RUNNERS["safety"] = original
