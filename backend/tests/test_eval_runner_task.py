"""周度 orchestrator eval cron task 测试 — mock LLM, 不烧钱."""
import pytest

from app.tasks import eval_runner


class _Push:
    """记录 push 调用的 mock TelegramPushService."""
    def __init__(self, configured=True):
        self.configured = configured
        self.calls = []

    async def send_health_alert(self, title, message, severity="warning"):
        self.calls.append({"title": title, "message": message, "severity": severity})
        return {"success": True}


def _patch_run_suite(monkeypatch, fake_report):
    """把 run_suite 替换成返回固定 SuiteReport 的 fn."""
    monkeypatch.setattr("eval.runner.run_suite", lambda suite, baseline=None: fake_report)


def _make_report(passed: int, failed: int, regression=None, errored: int = 0,
                 case_results=None):
    from eval.models import SuiteReport, CaseResult
    cases = case_results or [
        CaseResult(case_id=f"c{i}", suite="orchestrator", passed=True, score=1.0)
        for i in range(passed)
    ] + [
        CaseResult(case_id=f"f{i}", suite="orchestrator", passed=False, score=0.0)
        for i in range(failed)
    ]
    return SuiteReport(
        suite="orchestrator",
        total_cases=passed + failed + errored,
        passed=passed, failed=failed, errored=errored,
        avg_score=passed / max(passed + failed + errored, 1),
        cases=cases,
        regression=regression or [],
    )


class TestEvalRunner:
    def test_all_pass_no_alert(self, monkeypatch):
        push = _Push()
        monkeypatch.setattr(eval_runner, "TelegramPushService", lambda: push)
        _patch_run_suite(monkeypatch, _make_report(passed=5, failed=0))

        result = eval_runner.run_orchestrator_eval_weekly()
        assert result["status"] == "ok"
        assert result["passed"] == 5 and result["failed"] == 0
        assert push.calls == []  # 无告警

    def test_failure_without_regression_pushes_warning(self, monkeypatch):
        push = _Push()
        monkeypatch.setattr(eval_runner, "TelegramPushService", lambda: push)
        _patch_run_suite(monkeypatch, _make_report(passed=4, failed=1))

        result = eval_runner.run_orchestrator_eval_weekly()
        assert result["failed"] == 1
        assert len(push.calls) == 1
        assert push.calls[0]["severity"] == "warning"
        assert "无回归" in push.calls[0]["message"]

    def test_regression_pushes_critical(self, monkeypatch):
        push = _Push()
        monkeypatch.setattr(eval_runner, "TelegramPushService", lambda: push)
        _patch_run_suite(monkeypatch,
                         _make_report(passed=3, failed=2, regression=["c_old"]))

        result = eval_runner.run_orchestrator_eval_weekly()
        assert result["regression"] == ["c_old"]
        assert push.calls[0]["severity"] == "critical"
        assert "c_old" in push.calls[0]["message"]
        assert "Regression" in push.calls[0]["message"]

    def test_run_suite_exception_pushes_warning(self, monkeypatch):
        push = _Push()
        monkeypatch.setattr(eval_runner, "TelegramPushService", lambda: push)
        def boom(suite, baseline=None):
            raise RuntimeError("LLM provider down")
        monkeypatch.setattr("eval.runner.run_suite", boom)

        result = eval_runner.run_orchestrator_eval_weekly()
        assert result["status"] == "error"
        assert "LLM provider down" in result["error"]
        assert push.calls[0]["severity"] == "warning"
        assert "Eval 异常" in push.calls[0]["message"]

    def test_telegram_not_configured_skipped(self, monkeypatch, caplog):
        push = _Push(configured=False)
        monkeypatch.setattr(eval_runner, "TelegramPushService", lambda: push)
        _patch_run_suite(monkeypatch, _make_report(passed=3, failed=2))

        # 不应抛异常
        result = eval_runner.run_orchestrator_eval_weekly()
        assert result["status"] == "ok"
        assert push.calls == []  # 没配置就跳过
