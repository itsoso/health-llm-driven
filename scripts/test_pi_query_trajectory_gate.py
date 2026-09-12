"""Offline checks for live trajectory admission and honest result scoring."""
import importlib.util
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


if __name__ == "__main__":
    unittest.main()
