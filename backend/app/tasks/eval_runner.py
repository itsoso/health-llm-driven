"""周度 Eval Golden Set runner — 夜间跑所有 suite, 监测回归.

设计:
- 每周日 03:30 (避开高峰) 跑 safety / recovery / insight (确定性, 零 LLM 成本)
  + orchestrator (真实 LLM 合成, ~$0.005/run)
- 失败 / regression 通过 Telegram 告警
- 结果写 Celery 日志, 不另起 DB 表 (baseline JSON 已承担历史)
"""
import asyncio
import logging

from app.celery_app import celery_app
from app.services.notification.telegram_push import TelegramPushService

logger = logging.getLogger(__name__)


# 要跑的 suite + 对应的 baseline 名
_SUITES = [
    ("safety", "main"),
    ("recovery", "main"),
    ("insight", "main"),
    ("orchestrator", "main"),
]


@celery_app.task(name="app.tasks.eval_runner.run_orchestrator_eval_weekly")
def run_orchestrator_eval_weekly() -> dict:
    """周度跑全部 suite, 汇总失败 + 回归 → Telegram 一条 digest."""
    from eval.runner import run_suite

    reports = []
    errors = []

    for suite, baseline in _SUITES:
        logger.info(f"[eval] 开始 {suite} suite")
        try:
            report = run_suite(suite, baseline=baseline)
            reports.append(report)
            logger.info(f"[eval] {report.summarize()}")
        except Exception as e:
            logger.exception(f"[eval] {suite} suite 异常")
            errors.append((suite, str(e)[:200]))

    # 汇总
    regressions = [(r.suite, r.regression) for r in reports if r.regression]
    failings = [(r.suite, [c.case_id for c in r.cases if not c.passed]) for r in reports
                if r.failed or r.errored]

    lines = [f"*Eval Weekly · {len(reports)}/{len(_SUITES)} suites ran*", ""]
    for r in reports:
        mark = "✅" if (r.failed == 0 and r.errored == 0 and not r.regression) else "❌"
        lines.append(f"{mark} `{r.suite}`: {r.passed}/{r.total_cases} pass · avg={r.avg_score}")

    severity = "info"
    if regressions:
        severity = "critical"
        lines.append("")
        lines.append("*回归 (baseline pass → now fail)*:")
        for suite, cids in regressions:
            lines.extend([f"- {suite}:"] + [f"  · `{c}`" for c in cids])
    elif any(f for _, f in failings if f):
        severity = "warning"
        lines.append("")
        lines.append("*失败 case (非回归)*:")
        for suite, cids in failings:
            if cids:
                lines.append(f"- {suite}: {', '.join(cids[:5])}"
                             + (" ..." if len(cids) > 5 else ""))

    if errors:
        severity = "warning" if severity == "info" else severity
        lines.append("")
        lines.append("*Suite 运行异常*:")
        for suite, msg in errors:
            lines.append(f"- {suite}: {msg}")

    body = "\n".join(lines)

    # 只有 critical / warning 才 push, all-green 不打扰
    if severity != "info":
        _push_alert(body, severity=severity)

    return {
        "status": "ok",
        "suites_run": len(reports),
        "suites_total": len(_SUITES),
        "errors": [s for s, _ in errors],
        "regressions": {s: cs for s, cs in regressions},
        "avg_scores": {r.suite: r.avg_score for r in reports},
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
