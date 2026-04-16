"""
Safety Guardian 主入口。

用法：
    from app.twin import build_twin
    from app.agents.safety_guardian import evaluate_safety

    twin = build_twin(db, user_id)
    report = evaluate_safety(twin)
    for alert in sorted(report.alerts, key=lambda a: -int(a.severity)):
        print(alert.title)
"""

import logging
import time
from datetime import UTC, datetime

from app.agents.safety_guardian.engine import evaluate_rules, registry
from app.agents.safety_guardian.schema import SafetyReport
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


def evaluate_safety(twin: HealthTwin) -> SafetyReport:
    """对给定 Twin 运行全部规则，返回结构化报告。"""
    t0 = time.monotonic()
    alerts = evaluate_rules(twin)

    # 按严重度降序（CRITICAL 在最上面）
    alerts.sort(key=lambda a: -int(a.severity))

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    report = SafetyReport(
        user_id=twin.meta.user_id,
        generated_at=datetime.now(UTC),
        alerts=alerts,
        total_rules_evaluated=registry.count(),
        twin_build_ms=twin.meta.build_ms,
        evaluate_ms=elapsed_ms,
    )

    logger.info(
        f"[safety] user={twin.meta.user_id} alerts={len(alerts)} "
        f"(crit={report.critical_count} high={report.high_count} med={report.medium_count}) "
        f"rules={registry.count()} ms={elapsed_ms}"
    )
    return report
