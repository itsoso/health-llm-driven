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


class DataIntegrityScanError(RuntimeError):
    """A required integrity ledger could not be scanned reliably."""


def _is_empty_targets(tm: Any) -> bool:
    """target_metrics 是否为空。list 判元素数==0;str(JSON 列)判 '[]'/'null'/空。

    注意:list 不能用 len(tm)<=2 判空 —— 那会把 1–2 个真实目标误判为空(实测误报)。
    """
    if not tm:  # None / 空 list / 空 str
        return True
    if isinstance(tm, list):
        return len(tm) == 0
    if isinstance(tm, str):
        return tm.strip().lower() in ("[]", "null", "")
    return False


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

    def _strict_count(sql: str, **params) -> int:
        return int(db.execute(text(sql), {"u": user_id, **params}).scalar() or 0)

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
        empty = sum(1 for (tm,) in rows if _is_empty_targets(tm))
        if empty:
            _add("cycle_empty_targets", "warning",
                 f"{empty} 个 active 干预周期无目标指标(无法判定有效)", empty,
                 "POST /chronic/biomarker-sync(顺带 refresh)或 refresh_cycle_targets")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[integrity] cycle 检查跳过: {e}")

    # ── 拍照记餐会话:一个 source message 只能落到一个父对象 ──
    try:
        rows = db.execute(text(
            "SELECT id, origin_message_id, ordinal, diet_record_id, photo_draft_token "
            "FROM diet_photo_assets "
            "WHERE user_id=:u AND origin='chat' AND lifecycle!='deleted' "
            "AND origin_message_id IS NOT NULL"
        ), {"u": user_id}).mappings().all()
        invalid_parent = sum(
            1
            for row in rows
            if bool(row["diet_record_id"]) == bool(row["photo_draft_token"])
        )
        if invalid_parent:
            _add(
                "diet_photo_asset_parent_invalid",
                "error",
                f"{invalid_parent} 个餐食图片资源没有且仅有一个父记录",
                invalid_parent,
                "核对 diet_photo_assets 的 record/draft 关联后再补偿",
            )

        from app.models.daily_health import DietPhotoDraft, DietRecord

        record_ids = {
            int(row["diet_record_id"])
            for row in rows
            if row["diet_record_id"] is not None
        }
        draft_tokens = {
            str(row["photo_draft_token"])
            for row in rows
            if row["photo_draft_token"]
        }
        record_parents = {
            int(record_id): (int(owner_id), str(client_action_id or ""))
            for record_id, owner_id, client_action_id in (
                db.query(
                    DietRecord.id,
                    DietRecord.user_id,
                    DietRecord.client_action_id,
                )
                .filter(DietRecord.id.in_(record_ids))
                .all()
                if record_ids
                else []
            )
        }
        draft_parents = {
            str(token): (int(owner_id), source_message_id)
            for token, owner_id, source_message_id in (
                db.query(
                    DietPhotoDraft.token,
                    DietPhotoDraft.user_id,
                    DietPhotoDraft.source_message_id,
                )
                .filter(DietPhotoDraft.token.in_(draft_tokens))
                .all()
                if draft_tokens
                else []
            )
        }
        missing_parents = 0
        owner_mismatches = 0
        draft_source_mismatches = 0
        record_source_mismatches = 0
        for row in rows:
            source_message_id = int(row["origin_message_id"])
            if row["diet_record_id"] is not None:
                record_id = int(row["diet_record_id"])
                parent = record_parents.get(record_id)
                if parent is None:
                    missing_parents += 1
                    continue
                parent_owner_id, client_action_id = parent
                if parent_owner_id != int(user_id):
                    owner_mismatches += 1
                contextual_prefix = "contextual-meal-photo:"
                if client_action_id.startswith(contextual_prefix):
                    raw_source_id = client_action_id[len(contextual_prefix):]
                    if not raw_source_id.isdigit() or int(raw_source_id) != source_message_id:
                        record_source_mismatches += 1
            elif row["photo_draft_token"]:
                draft_token = str(row["photo_draft_token"])
                parent = draft_parents.get(draft_token)
                if parent is None:
                    missing_parents += 1
                    continue
                parent_owner_id, draft_source_message_id = parent
                if parent_owner_id != int(user_id):
                    owner_mismatches += 1
                if (
                    draft_source_message_id is not None
                    and int(draft_source_message_id) != source_message_id
                ):
                    draft_source_mismatches += 1
        if missing_parents:
            _add(
                "diet_photo_parent_missing",
                "error",
                f"{missing_parents} 个餐食图片资源引用了不存在的父对象",
                missing_parents,
                "停止自动补偿并从 capture session 账本核对父关系",
            )
        if owner_mismatches:
            _add(
                "diet_photo_parent_owner_mismatch",
                "error",
                f"{owner_mismatches} 个餐食图片资源与父对象用户不一致",
                owner_mismatches,
                "隔离资源并审计跨用户关联来源",
            )
        if draft_source_mismatches:
            _add(
                "diet_photo_draft_source_mismatch",
                "error",
                f"{draft_source_mismatches} 个餐食图片资源与草稿 source message 不一致",
                draft_source_mismatches,
                "按 owner/source_message_id 恢复唯一草稿会话",
            )
        if record_source_mismatches:
            _add(
                "diet_photo_record_source_mismatch",
                "error",
                f"{record_source_mismatches} 个餐食图片资源与记录幂等来源不一致",
                record_source_mismatches,
                "核对 contextual-meal-photo 幂等键后再恢复关联",
            )

        parents_by_session: dict[int, set[str]] = {}
        ordinals_by_session: dict[int, list[int]] = {}
        for row in rows:
            source_message_id = int(row["origin_message_id"])
            parent = (
                f"record:{row['diet_record_id']}"
                if row["diet_record_id"]
                else f"draft:{row['photo_draft_token']}"
            )
            parents_by_session.setdefault(source_message_id, set()).add(parent)
            ordinals_by_session.setdefault(source_message_id, []).append(int(row["ordinal"]))
        split_sessions = sum(
            1
            for parents in parents_by_session.values()
            if len(parents) > 1
        )
        if split_sessions:
            _add(
                "diet_photo_session_split_parent",
                "error",
                f"{split_sessions} 个拍照记餐会话被拆到多个父记录",
                split_sessions,
                "按 origin_message_id 合并到唯一记录并核对营养总量",
            )
        duplicate_ordinal_sessions = sum(
            1
            for ordinals in ordinals_by_session.values()
            if len(ordinals) != len(set(ordinals))
        )
        if duplicate_ordinal_sessions:
            _add(
                "diet_photo_session_duplicate_ordinal",
                "error",
                f"{duplicate_ordinal_sessions} 个拍照记餐会话含重复图片序号",
                duplicate_ordinal_sessions,
                "保留唯一资源并恢复 user/source/ordinal 唯一约束",
            )
    except Exception as e:  # noqa: BLE001
        logger.exception(
            "[integrity] diet photo session scan failed user_id=%s",
            user_id,
        )
        raise DataIntegrityScanError(
            f"diet_photo_integrity_scan_failed user_id={user_id}",
        ) from e

    try:
        contextual_records_without_asset = _strict_count(
            "SELECT count(*) FROM diet_records r "
            "WHERE r.user_id=:u "
            "AND r.client_action_id LIKE 'contextual-meal-photo:%' "
            "AND NOT EXISTS ("
            "SELECT 1 FROM diet_photo_assets a "
            "WHERE a.user_id=r.user_id AND a.diet_record_id=r.id AND a.lifecycle!='deleted'"
            ")"
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(
            "[integrity] contextual meal photo record scan failed user_id=%s",
            user_id,
        )
        raise DataIntegrityScanError(
            f"diet_photo_integrity_scan_failed user_id={user_id}",
        ) from e
    if contextual_records_without_asset:
        _add(
            "diet_photo_record_asset_missing",
            "error",
            f"{contextual_records_without_asset} 条拍照饮食记录缺少图片资源关联",
            contextual_records_without_asset,
            "从 owner-scoped 媒体记录恢复关联；无法恢复时保留饮食并标记媒体不可用",
        )

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
