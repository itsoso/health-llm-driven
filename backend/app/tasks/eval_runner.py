"""周度 Eval Golden Set runner — 夜间跑 orchestrator suite, 监测 LLM 合成回归.

设计:
- 每周日 03:30 (避开高峰) 跑 orchestrator suite
- 失败 / regression 通过 Telegram 告警
- 不写库 (结果在 Celery 日志 + telegram), 单次成本约 $0.005
"""
import asyncio
import logging

from app.celery_app import celery_app
from app.services.notification.telegram_push import TelegramPushService

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.eval_runner.run_orchestrator_eval_weekly")
def run_orchestrator_eval_weekly() -> dict:
    """周度跑 orchestrator suite, 失败时 Telegram 告警."""
    from eval.runner import run_suite

    logger.info("[eval] 开始周度 orchestrator suite")

    try:
        report = run_suite("orchestrator", baseline="main")
    except Exception as e:
        logger.exception("[eval] orchestrator suite 异常")
        _push_alert(f"⚠️ Eval 异常\n\n{type(e).__name__}: {str(e)[:200]}", severity="warning")
        return {"status": "error", "error": str(e)}

    summary = report.summarize()
    logger.info(f"[eval] {summary}")

    failed = [c.case_id for c in report.cases if not c.passed]

    if report.regression:
        body = (
            f"*Eval Regression*\n\n"
            f"{summary}\n\n"
            f"以下 case 之前 pass, 现在 fail:\n"
            + "\n".join(f"- `{cid}`" for cid in report.regression)
        )
        _push_alert(body, severity="critical")
    elif failed:
        body = (
            f"*Eval 部分失败 (无回归)*\n\n"
            f"{summary}\n\n"
            f"Failing: {', '.join(failed)}"
        )
        _push_alert(body, severity="warning")
    else:
        logger.info(f"[eval] 全部 pass: {summary}")

    return {
        "status": "ok",
        "suite": report.suite,
        "passed": report.passed,
        "failed": report.failed,
        "errored": report.errored,
        "avg_score": report.avg_score,
        "regression": report.regression,
    }


def _push_alert(message: str, severity: str = "warning") -> None:
    """旁路 Telegram, 失败不抛."""
    try:
        push = TelegramPushService()
        if not push.configured:
            logger.warning("[eval] Telegram 未配置, 跳过告警")
            return
        asyncio.run(push.send_health_alert(
            title="Eval Golden Set",
            message=message,
            severity=severity,
        ))
    except Exception as e:
        logger.warning(f"[eval] Telegram 推送失败: {e}")
