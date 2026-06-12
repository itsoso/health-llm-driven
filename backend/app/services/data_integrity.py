"""系统自我监控 —— 数据**正确性 / 管线完整性**检查(区别于 data_health 的"完整度")。

动机(止血):本类 bug 反复出现且**全靠人肉发现**,系统对自己毫不知情:
- HRV 以"秒"存进库(应 ms)→ 入库 0.0576
- 睡眠字段被 Pydantic 静默丢弃 / SpO2 以 0–1 小数存(应 0–100)
- biomarker_observations 整张表为空(归一层断连),却有 medical_indicators
- metabolic_90d 周期 target_metrics=[](空目标跑了一个月)

这层做**量纲/范围合理性 + 层断连**检测,产出问题清单推给运维/日志(不打扰用户)。
纯判定逻辑(range_issue)可单测;扫描在 check_user_integrity / Celery 任务。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 合理范围(超出 = 量纲错 / 脏数据嫌疑)。(low, high, 单位说明)
_RANGES = {
    "hrv_ms": (3.0, 250.0, "HRV 应为 ms(典型 20–120);<3 多半是按秒存了"),
    "resting_hr": (25.0, 130.0, "静息心率 bpm"),
    "spo2_pct": (50.0, 100.0, "SpO2 应为百分数 0–100;<=1.5 多半按小数存了"),
    "sleep_minutes": (60.0, 1000.0, "睡眠分钟;>1000 不合理"),
}


class IntegrityIssue(dict):
    """一条数据完整性问题(dict 子类,直接可 JSON)。"""


def range_issue(metric: str, value: Optional[float]) -> Optional[str]:
    """纯函数:某指标值是否越界。返回问题描述或 None。可单测。"""
    if value is None or metric not in _RANGES:
        return None
    low, high, hint = _RANGES[metric]
    if value < low or value > high:
        return f"{value} 超出合理范围 [{low:g},{high:g}] — {hint}"
    return None


def check_user_integrity(db: Session, user_id: int) -> list[IntegrityIssue]:
    """对单用户跑全部完整性检查。返回问题列表(空 = 健康)。"""
    issues: list[IntegrityIssue] = []

    cutoff = date.today() - timedelta(days=90)

    def _add(code: str, severity: str, detail: str, count: int = 1, fix: str = ""):
        issues.append(IntegrityIssue(code=code, severity=severity, detail=detail,
                                     count=count, fix_hint=fix))

    def _count(sql: str, **params) -> int:
        try:
            return int(db.execute(text(sql), {"u": user_id, **params}).scalar() or 0)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[integrity] 查询跳过: {e}")
            return 0

    # ── 量纲/范围(garmin_data 近 90 天;方言无关:日期参数化)──
    hrv_bad = _count(
        "SELECT count(*) FROM garmin_data WHERE user_id=:u AND hrv IS NOT NULL "
        "AND hrv > 0 AND hrv < 3 AND record_date >= :cut", cut=cutoff)
    if hrv_bad:
        _add("hrv_unit_suspect", "error", f"{hrv_bad} 行 HRV 值 <3(疑按秒存,应 ms)", hrv_bad,
             "客户端 ×1000 + 清洗历史(见 appleHealth.ts secondUnit 教训)")

    spo2_bad = _count(
        "SELECT count(*) FROM garmin_data WHERE user_id=:u AND spo2_avg IS NOT NULL "
        "AND spo2_avg > 0 AND spo2_avg <= 1.5 AND record_date >= :cut", cut=cutoff)
    if spo2_bad:
        _add("spo2_unit_suspect", "error", f"{spo2_bad} 行 SpO2 <=1.5(疑按 0–1 小数存,应 0–100)",
             spo2_bad, "导入处 ×100")

    # ── 层断连:有化验指标却无归一观测 ──
    ind = _count("SELECT count(*) FROM medical_indicators WHERE user_id=:u AND value IS NOT NULL")
    obs = _count("SELECT count(*) FROM biomarker_observations WHERE user_id=:u")
    if ind > 0 and obs == 0:
        _add("biomarker_layer_disconnected", "error",
             f"有 {ind} 条 medical_indicators 但 biomarker_observations 为 0(归一层断连)", ind,
             "POST /chronic/biomarker-sync 回填(见 biomarker_sync 根因)")

    # ── 干预周期空目标(方言无关:取出 target_metrics 在 Python 判空)──
    try:
        rows = db.execute(text(
            "SELECT target_metrics FROM intervention_cycles WHERE user_id=:u AND status='active'"
        ), {"u": user_id}).fetchall()
        empty = sum(1 for (tm,) in rows if not tm or (isinstance(tm, (list, str)) and len(tm) <= 2))
        if empty:
            _add("cycle_empty_targets", "warning",
                 f"{empty} 个 active 干预周期无目标指标(无法判定有效)", empty,
                 "POST /chronic/biomarker-sync(顺带 refresh)或 refresh_cycle_targets")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[integrity] cycle 检查跳过: {e}")

    return issues


def integrity_summary(db: Session, user_ids: list[int]) -> dict[str, Any]:
    """批量扫描多用户,汇总问题(给运维/Celery)。"""
    affected: list[dict[str, Any]] = []
    code_counts: dict[str, int] = {}
    for uid in user_ids:
        issues = check_user_integrity(db, uid)
        if issues:
            affected.append({"user_id": uid, "issues": issues})
            for it in issues:
                code_counts[it["code"]] = code_counts.get(it["code"], 0) + 1
    return {
        "scanned": len(user_ids),
        "affected_users": len(affected),
        "by_code": code_counts,
        "details": affected,
    }
