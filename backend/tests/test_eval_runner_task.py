"""周度 eval cron task 测试 — mock LLM, 不烧钱.

task 现在跑所有 suite (safety / recovery / insight / orchestrator),
返回汇总字典 + 根据回归/失败 push 不同严重度的 Telegram.
"""
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


def _make_report(suite, passed, failed, regression=None, errored=0):
    from eval.models import SuiteReport, CaseResult
    cases = [
        CaseResult(case_id=f"{suite}_c{i}", suite=suite, passed=True, score=1.0)
        for i in range(passed)
    ] + [
        CaseResult(case_id=f"{suite}_f{i}", suite=suite, passed=False, score=0.0)
        for i in range(failed)
    ]
    return SuiteReport(
        suite=suite,
        total_cases=passed + failed + errored,
        passed=passed, failed=failed, errored=errored,
        avg_score=passed / max(passed + failed + errored, 1),
        cases=cases,
        regression=regression or [],
    )


def _patch_multi(monkeypatch, reports_by_suite):
    """把 run_suite 替换成按 suite 名返回不同 report 的函数."""
    def fake_run(suite, baseline=None):
        r = reports_by_suite.get(suite)
        if r is None:
            # 默认全 pass 5 条, 保持 digest 行数稳定
            return _make_report(suite, passed=5, failed=0)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr("eval.runner.run_suite", fake_run)


class TestEvalRunner:
    def test_all_pass_no_alert(self, monkeypatch):
        push = _Push()
        monkeypatch.setattr(eval_runner, "TelegramPushService", lambda: push)
        _patch_multi(monkeypatch, {})  # 默认全 pass

        result = eval_runner.run_orchestrator_eval_weekly()
        assert result["status"] == "ok"
        assert result["suites_run"] == len(eval_runner._SUITES)
        assert result["regressions"] == {}
        assert push.calls == []  # all-green 不打扰

    def test_failure_in_one_suite_warns(self, monkeypatch):
        push = _Push()
        monkeypatch.setattr(eval_runner, "TelegramPushService", lambda: push)
        _patch_multi(monkeypatch, {
            "recovery": _make_report("recovery", passed=4, failed=1),
        })

        result = eval_runner.run_orchestrator_eval_weekly()
        assert result["status"] == "ok"
        assert len(push.calls) == 1
        assert push.calls[0]["severity"] == "warning"
        assert "recovery" in push.calls[0]["message"]
        assert "回归" not in push.calls[0]["message"].split("(非回归)")[1] if "(非回归)" in push.calls[0]["message"] else True

    def test_regression_pushes_critical(self, monkeypatch):
        push = _Push()
        monkeypatch.setattr(eval_runner, "TelegramPushService", lambda: push)
        _patch_multi(monkeypatch, {
            "safety": _make_report("safety", passed=3, failed=2,
                                   regression=["bp_old_case"]),
        })

        result = eval_runner.run_orchestrator_eval_weekly()
        assert result["regressions"] == {"safety": ["bp_old_case"]}
        assert len(push.calls) == 1
        assert push.calls[0]["severity"] == "critical"
        assert "bp_old_case" in push.calls[0]["message"]
        assert "回归" in push.calls[0]["message"]

    def test_one_suite_raises_others_still_run(self, monkeypatch):
        push = _Push()
        monkeypatch.setattr(eval_runner, "TelegramPushService", lambda: push)
        _patch_multi(monkeypatch, {
            "orchestrator": RuntimeError("LLM provider down"),
        })

        result = eval_runner.run_orchestrator_eval_weekly()
        assert result["status"] == "ok"
        assert result["suites_run"] == len(eval_runner._SUITES) - 1
        assert "orchestrator" in result["errors"]
        assert len(push.calls) == 1
        assert push.calls[0]["severity"] == "warning"
        assert "orchestrator" in push.calls[0]["message"]
        assert "LLM provider down" in push.calls[0]["message"]

    def test_telegram_not_configured_skipped(self, monkeypatch):
        push = _Push(configured=False)
        monkeypatch.setattr(eval_runner, "TelegramPushService", lambda: push)
        _patch_multi(monkeypatch, {
            "recovery": _make_report("recovery", passed=3, failed=2),
        })

        # 不应抛异常
        result = eval_runner.run_orchestrator_eval_weekly()
        assert result["status"] == "ok"
        assert push.calls == []  # 没配置就跳过

    def test_regression_overrides_simple_failure(self, monkeypatch):
        """有回归时应推 critical, 即使其他 suite 只是普通失败."""
        push = _Push()
        monkeypatch.setattr(eval_runner, "TelegramPushService", lambda: push)
        _patch_multi(monkeypatch, {
            "safety": _make_report("safety", passed=4, failed=1),  # 仅失败
            "recovery": _make_report("recovery", passed=3, failed=2,
                                     regression=["c_regress"]),   # 回归
        })

        result = eval_runner.run_orchestrator_eval_weekly()
        assert push.calls[0]["severity"] == "critical"
        assert "c_regress" in push.calls[0]["message"]
