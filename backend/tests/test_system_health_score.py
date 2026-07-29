"""系统健康度评分脚本测试 — scripts/system_health_score.py"""
from unittest.mock import patch, MagicMock

import sys
import os

# 确保 scripts 目录可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from scripts.system_health_score import (
    score_tests,
    score_health_check,
    score_agent_runtime_circuit,
    calculate_health_score,
    FAIL_THRESHOLD,
)


class TestScoreTests:
    """score_tests() 函数"""

    def test_parses_pytest_output(self):
        """解析 pytest 输出并计算分数"""
        mock_result = MagicMock()
        mock_result.stdout = "100 passed, 5 failed in 30.5s\n"
        mock_result.returncode = 1

        with patch("scripts.system_health_score.subprocess.run", return_value=mock_result):
            result = score_tests()

        assert result["passed"] == 100
        assert result["total"] == 105
        assert result["score"] > 0
        assert result["score"] <= 40

    def test_all_passed(self):
        """全部通过得满分 40"""
        mock_result = MagicMock()
        mock_result.stdout = "50 passed in 10.0s\n"

        with patch("scripts.system_health_score.subprocess.run", return_value=mock_result):
            result = score_tests()

        assert result["passed"] == 50
        assert result["total"] == 50
        assert result["score"] == 40.0

    def test_no_tests_found(self):
        """无测试时返回 0 分"""
        mock_result = MagicMock()
        mock_result.stdout = "no tests ran\n"

        with patch("scripts.system_health_score.subprocess.run", return_value=mock_result):
            result = score_tests()

        assert result["score"] == 0
        assert result["total"] == 0

    def test_timeout_returns_zero(self):
        """超时返回 0 分"""
        import subprocess

        with patch(
            "scripts.system_health_score.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=300),
        ):
            result = score_tests()

        assert result["score"] == 0
        assert "timed out" in result["detail"]


class TestScoreHealthCheck:
    """score_health_check() 函数"""

    def test_healthy_response(self):
        """健康端点正常返回 30 分"""
        import json

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"status": "healthy"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = score_health_check("http://localhost:8000")

        assert result["score"] == 30

    def test_unreachable_returns_zero(self):
        """不可达时返回 0 分"""
        with patch("urllib.request.urlopen", side_effect=ConnectionError("refused")):
            result = score_health_check("http://localhost:9999")

        assert result["score"] == 0
        assert "unreachable" in result["detail"]


class TestCalculateHealthScore:
    """calculate_health_score() 综合评分"""

    def test_skip_tests_structure(self):
        """skip_tests=True 返回正确结构"""
        with patch("scripts.system_health_score.score_health_check", return_value={"score": 30, "detail": "ok"}), \
             patch("scripts.system_health_score.score_api_latency", return_value={"score": 20, "detail": "ok"}), \
             patch("scripts.system_health_score.score_error_rate_from_logs", return_value={"score": 10, "detail": "ok"}), \
             patch("scripts.system_health_score.score_agent_runtime_circuit", return_value={"score": 0, "detail": "active", "healthy": True}):
            result = calculate_health_score(skip_tests=True)

        assert "total_score" in result
        assert "max_possible" in result
        assert "pass" in result
        assert "threshold" in result
        assert "dimensions" in result
        assert result["max_possible"] == 60
        assert result["dimensions"]["test_pass_rate"]["detail"] == "skipped"

    def test_full_score_passes(self):
        """满分应通过阈值"""
        with patch("scripts.system_health_score.score_tests", return_value={"score": 40, "detail": "ok"}), \
             patch("scripts.system_health_score.score_health_check", return_value={"score": 30, "detail": "ok"}), \
             patch("scripts.system_health_score.score_api_latency", return_value={"score": 20, "detail": "ok"}), \
             patch("scripts.system_health_score.score_error_rate_from_logs", return_value={"score": 10, "detail": "ok"}), \
             patch("scripts.system_health_score.score_agent_runtime_circuit", return_value={"score": 0, "detail": "active", "healthy": True}):
            result = calculate_health_score()

        assert result["total_score"] == 100
        assert result["pass"] is True

    def test_low_score_fails(self):
        """低分应不通过"""
        with patch("scripts.system_health_score.score_tests", return_value={"score": 10, "detail": "bad"}), \
             patch("scripts.system_health_score.score_health_check", return_value={"score": 0, "detail": "down"}), \
             patch("scripts.system_health_score.score_api_latency", return_value={"score": 0, "detail": "slow"}), \
             patch("scripts.system_health_score.score_error_rate_from_logs", return_value={"score": 0, "detail": "errors"}), \
             patch("scripts.system_health_score.score_agent_runtime_circuit", return_value={"score": 0, "detail": "active", "healthy": True}):
            result = calculate_health_score()

        assert result["total_score"] == 10
        assert result["pass"] is False

    def test_threshold_value(self):
        """部署健康门槛与 G5 契约保持一致。"""
        assert FAIL_THRESHOLD == 35

    def test_threshold_boundary(self):
        """刚好达到部署健康门槛时应通过。"""
        with patch("scripts.system_health_score.score_tests", return_value={"score": 15, "detail": "ok"}), \
             patch("scripts.system_health_score.score_health_check", return_value={"score": 10, "detail": "ok"}), \
             patch("scripts.system_health_score.score_api_latency", return_value={"score": 5, "detail": "ok"}), \
             patch("scripts.system_health_score.score_error_rate_from_logs", return_value={"score": 5, "detail": "ok"}), \
             patch("scripts.system_health_score.score_agent_runtime_circuit", return_value={"score": 0, "detail": "active", "healthy": True}):
            result = calculate_health_score()

        assert result["total_score"] == 35
        assert result["pass"] is True

    def test_paused_agent_runtime_circuit_blocks_health_gate(self):
        with patch(
            "scripts.system_health_score.score_health_check",
            return_value={"score": 30, "detail": "ok"},
        ), patch(
            "scripts.system_health_score.score_api_latency",
            return_value={"score": 20, "detail": "ok"},
        ), patch(
            "scripts.system_health_score.score_error_rate_from_logs",
            return_value={"score": 10, "detail": "ok"},
        ), patch(
            "scripts.system_health_score.score_agent_runtime_circuit",
            return_value={
                "score": 0,
                "detail": "paused:reconciliation_detected",
                "healthy": False,
            },
        ):
            result = calculate_health_score(skip_tests=True)

        assert result["total_score"] == 60
        assert result["pass"] is False
        assert result["critical_failures"] == ["agent_runtime_circuit"]


def test_agent_runtime_circuit_score_is_content_free(db, monkeypatch):
    from app.models.agent_runtime import AgentRuntimeRolloutState
    from app.config import settings

    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    state = db.query(AgentRuntimeRolloutState).filter_by(id=1).first()
    if state is None:
        state = AgentRuntimeRolloutState(id=1, version=1)
        db.add(state)
    state.status = "paused"
    state.reason_code = "reconciliation_detected"
    state.reconciliation_generation = 1
    state.reconciliation_acknowledged_generation = 0
    db.commit()

    result = score_agent_runtime_circuit(session_factory=lambda: db)

    assert result == {
        "score": 0,
        "detail": "paused:reconciliation_detected:generation=1:ack=0",
        "healthy": False,
    }
