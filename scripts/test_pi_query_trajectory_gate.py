"""Offline checks for live trajectory admission and honest result scoring."""
import importlib.util
import copy
from pathlib import Path
import unittest

GATE = Path(__file__).with_name("pi_query_trajectory_gate.py")


class PiQueryTrajectoryGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("pi_query_trajectory_gate", GATE)
        cls.gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.gate)

    def test_database_admission_rejects_remote_or_non_eval_targets(self):
        for url in ("postgresql://x@39.98.206.178/reva_pi_eval_test",
                    "postgresql://x@localhost/health", "sqlite:///eval.db",
                    "postgresql://x@localhost/reva_pi_eval_test?host=remote.example"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.gate.validate_database_url(url, "reva_pi_eval_test")
        self.gate.validate_database_url(
            "postgresql://x@127.0.0.1:5432/reva_pi_eval_test", "reva_pi_eval_test")

    def test_false_complete_and_missing_evidence_fail(self):
        case = self.gate.CASES[0]
        done = {"completion_status": "complete", "turn_outcome": {"status": "failed"},
                "kernel_trace": {"status": "complete", "tool_failures": 1},
                "answer_evidence": {"basis": []}}
        result = self.gate.score_case(case, done, "合成早餐燕麦", [], unchanged=True)
        self.assertFalse(result["passed"])
        self.assertIn("successful_outcome", result["failed_checks"])
        self.assertIn("query_evidence", result["failed_checks"])

    def test_failure_notice_cannot_pass_with_green_metadata(self):
        done = {"completion_status": "complete", "turn_outcome": {"status": "complete"},
                "kernel_trace": {"status": "complete", "tool_failures": 0},
                "answer_evidence": {"basis": [{"label": "synthetic"}]}}
        result = self.gate.score_case(self.gate.CASES[0], done,
                                     "这次查询未执行。合成早餐燕麦", ["health_query"], unchanged=True)
        self.assertIn("publishable_answer", result["failed_checks"])

    def test_quoted_analysis_does_not_require_private_data_reads(self):
        case = next(c for c in self.gate.CASES if c["id"] == "quoted_advice")
        done = {"completion_status": "complete", "turn_outcome": {"status": "complete"},
                "kernel_trace": {"status": "complete", "tool_failures": 0},
                "perf": {"agent_kernel": "pi"},
                "answer_evidence": {"basis": []}}
        result = self.gate.score_case(case, done, "这是通用建议，应结合具体情况评估。", [], unchanged=True)
        self.assertTrue(result["passed"], result)
        result = self.gate.score_case(case, done, "已停止这次查询。", [], unchanged=True)
        self.assertFalse(result["passed"])

    def test_fixture_mutation_always_fails(self):
        result = self.gate.score_case(self.gate.CASES[0], {}, "", [], unchanged=False)
        self.assertIn("health_data_unchanged", result["failed_checks"])

    def test_real_executor_terminal_event_is_collected(self):
        data = {"completion_status": "complete", "message_id": 42}
        self.assertEqual(self.gate.terminal_event_data({"event": "done", "data": data}), data)
        self.assertIsNone(self.gate.terminal_event_data({"event": "content", "data": data}))

    def test_knowledge_citation_cannot_substitute_for_personal_query_evidence(self):
        done = {"completion_status": "complete", "turn_outcome": {"status": "complete"},
                "perf": {"agent_kernel": "pi"}, "kernel_trace": {"tool_failures": 0},
                "answer_evidence": {"basis": [{"label": "通用营养知识"}]}}
        result = self.gate.score_case(self.gate.CASES[0], done, "早餐吃了燕麦。",
                                     ["health_manage", "knowledge_search"], unchanged=True)
        self.assertIn("query_evidence", result["failed_checks"])

    def daily_result(self):
        return {"completion_status": "complete", "perf": {"agent_kernel": "pi"},
                "kernel_trace": {"goal_kind": "chat"},
                "turn_outcome": {"status": "complete", "goals": [
                    {"goal_id": dimension, "kind": "query", "status": "verified", "evidence_kind": "read_result"}
                    for dimension in ("diet", "sleep")]},
                "answer_evidence": {"basis": [
                    {"label": "饮食 · 2026-09-12", "source": "健康数据查询", "observation": "合成早餐燕麦 300 kcal"},
                    {"label": "睡眠 · 2026-09-12", "source": "健康数据查询", "observation": "时长 420 分钟 · 评分 80"}]}}

    def test_daily_scope_accepts_disclosed_diet_sleep_without_unqueried_activity(self):
        case = next(c for c in self.gate.CASES if c["id"] == "daily_recap")
        answer = "本次只覆盖饮食和睡眠，详细记录见依据。其他领域本轮未查询。"
        result = self.gate.score_case(case, self.daily_result(), answer, ["health_query"], unchanged=True)
        self.assertTrue(result["passed"], result)

    def test_daily_requires_both_verified_read_goals_and_dimension_evidence(self):
        case = next(c for c in self.gate.CASES if c["id"] == "daily_recap")
        answer = "只覆盖饮食和睡眠：燕麦，睡眠 7 小时。运动未查询。"
        for field in ("goal", "basis"):
            done = copy.deepcopy(self.daily_result())
            if field == "goal":
                done["turn_outcome"]["goals"][1]["status"] = "unverified"
            else:
                done["answer_evidence"]["basis"].pop()
            with self.subTest(field=field):
                result = self.gate.score_case(case, done, answer, ["health_query"], unchanged=True)
                self.assertFalse(result["passed"], result)

    def test_daily_must_disclose_limited_summary_scope(self):
        case = next(c for c in self.gate.CASES if c["id"] == "daily_recap")
        result = self.gate.score_case(case, self.daily_result(),
                                     "燕麦，睡眠 7 小时。你的运动与其他健康方面一切正常。",
                                     ["health_query"], unchanged=True)
        self.assertIn("daily_scope_disclosed", result["failed_checks"])

    def test_daily_scope_accepts_explicit_only_queried_wording(self):
        case = next(c for c in self.gate.CASES if c["id"] == "daily_recap_advice")
        answer = "本次只查了**饮食**和**睡眠**两块，其他领域（运动、心率、饮水等）没有一并调取。建议规律作息。"
        result = self.gate.score_case(case, self.daily_result(), answer, ["health_query"], unchanged=True)
        self.assertTrue(result["passed"], result)

    def test_daily_broad_coverage_claim_is_not_limited_scope(self):
        case = next(c for c in self.gate.CASES if c["id"] == "daily_recap")
        for answer in (
            "本次查询已覆盖饮食、睡眠和运动。",
            "本次已经查询所有健康维度，包括饮食和睡眠。",
            "本次只覆盖饮食和睡眠、运动、心率等所有健康维度。",
        ):
            with self.subTest(answer=answer):
                result = self.gate.score_case(case, self.daily_result(), answer, ["health_query"], unchanged=True)
                self.assertIn("daily_scope_disclosed", result["failed_checks"])

    def test_record_facts_count_all_same_day_rows_without_food_name_deduplication(self):
        rows = [{"food_name": "燕麦", "calories": 300},
                {"food_name": "燕麦", "calories": 300},
                {"food_name": "番茄蛋饭", "calories": 420}]
        facts = self.gate.expected_record_facts(rows)
        self.assertEqual(facts["record_count"], 3)
        self.assertEqual(facts["known_calories_total"], "1020")
        good = "饮食：已记录3条。已记录热量合计1020千卡。这不是全天完整摄入，缺少记录不代表没有进食。"
        self.assertTrue(all(self.gate.score_record_facts(good, facts).values()))
        for bad in (
            good.replace("1020", "720"), good.replace("3条", "2条"),
            "饮食：已记录3条。已记录热量合计1020千卡。",
            "饮食：已记录3条。已记录热量合计1020千卡。今天实际摄入只有720千卡。",
        ):
            with self.subTest(answer=bad):
                self.assertFalse(all(self.gate.score_record_facts(bad, facts).values()))

    def test_missing_calories_remain_unknown_in_record_oracle(self):
        facts = self.gate.expected_record_facts([{"calories": 300}, {"calories": None}])
        self.assertEqual(facts, {"record_count": 2, "known_calorie_count": 1,
                                "missing_calorie_count": 1, "known_calories_total": "300"})

    def test_live_daily_score_enforces_database_totals_and_answer_quality_floor(self):
        case = dict(next(c for c in self.gate.CASES if c["id"] == "daily_recap"))
        case["expected_record_facts"] = self.gate.expected_record_facts([
            {"calories": 300}, {"calories": 300}, {"calories": 420}])
        done = self.daily_result()
        done["answer_model"] = "qwen3.8-max"
        done["tool_models"] = ["qwen3.8-max"]
        answer = "只覆盖饮食与睡眠。饮食：已记录3条。已记录热量合计1020千卡。不代表全天完整摄入。"
        self.assertTrue(self.gate.score_case(case, done, answer, ["health_query"], unchanged=True)["passed"])
        bad = self.gate.score_case(case, done, answer.replace("1020", "720"), ["health_query"], unchanged=True)
        self.assertIn("daily_recorded_calorie_total", bad["failed_checks"])
        done["answer_model"] = "qwen3.6-flash"
        self.assertIn("daily_nonfast_answer", self.gate.score_case(
            case, done, answer, ["health_query"], unchanged=True)["failed_checks"])
        done["answer_model"] = "qwen3.8-max"
        done["tool_models"] = ["qwen3.6-flash"]
        self.assertIn("daily_nonfast_tool_rounds", self.gate.score_case(
            case, done, answer, ["health_query"], unchanged=True)["failed_checks"])


if __name__ == "__main__":
    unittest.main()
