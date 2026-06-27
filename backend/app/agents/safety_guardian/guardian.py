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

from app.agents.safety_guardian.cross_source_annotation import (
    annotate_cross_source_suspect,
)
from app.agents.safety_guardian.engine import (
    evaluate_rules_with_status,
    make_fail_safe_advisory,
    registry,
)
from app.agents.safety_guardian.schema import SafetyReport
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


def evaluate_safety(twin: HealthTwin) -> SafetyReport:
    """对给定 Twin 运行全部规则，返回结构化报告。

    **fail-loud(不漏报)**：用 `evaluate_rules_with_status` 而非 lossy 的
    `evaluate_rules`，把「有几条规则崩了被跳过」(`failed_rule_count`)透出。任一规则
    在某用户数据 shape 上抛异常被 per-rule try/except 吞掉时，`alerts` 可能退化成空——
    若所有消费方(`/safety/me`、orchestrator、daily_recommendation、notifications、
    medication 等，全都迭代 `report.alerts`)据此当「无告警=安全」就是静默 under-alarm。
    故 `failed_rule_count>0` 时往**主渲染路径** alerts 注入一条 HIGH fail-safe advisory
    (客户端无关，绝不让 under-alarm 依赖客户端读一个可被忽略的 side flag)。
    """
    t0 = time.monotonic()
    alerts, failed_rule_count = evaluate_rules_with_status(twin)

    # 跨源可疑读数 → 给依据它的 vitals 告警附加复测提示(只加不减,绝不改 severity)。
    annotate_cross_source_suspect(alerts, twin)

    if failed_rule_count > 0:
        logger.error(
            f"[safety] user={twin.meta.user_id} {failed_rule_count} 条安全规则执行失败被跳过"
            f"(部分 under-alarm 风险)，注入 fail-safe advisory(severity=HIGH)"
        )
        alerts.append(make_fail_safe_advisory())

    # 按严重度降序（CRITICAL 在最上面；fail-safe advisory 为 HIGH，居真 CRITICAL 之下）
    alerts.sort(key=lambda a: -int(a.severity))

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    report = SafetyReport(
        user_id=twin.meta.user_id,
        generated_at=datetime.now(UTC),
        alerts=alerts,
        total_rules_evaluated=registry.count(),
        failed_rule_count=failed_rule_count,
        twin_build_ms=twin.meta.build_ms,
        evaluate_ms=elapsed_ms,
    )

    logger.info(
        f"[safety] user={twin.meta.user_id} alerts={len(alerts)} "
        f"(crit={report.critical_count} high={report.high_count} med={report.medium_count}) "
        f"rules={registry.count()} failed={failed_rule_count} ms={elapsed_ms}"
    )
    return report
