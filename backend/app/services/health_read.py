"""Canonical 归一读层 — agent health_query 各维度的统一读取入口.

设计来源: docs/design-canonical-read-layer.md.

问题: health_query 各维度过去走 `_api_get`(进程内 HTTP 调 /xxx/me)+ >3000 字符
截断, 与 Twin 的 service/repo 读路径分叉 → 同一份数据多条不一致读路径 → 查空/截断丢数据.

本模块把"直读 service/repo 层 + 紧凑摘要 + user_id 隔离 + 不截断"做成可复用结构:

    canonical_read(db, user_id, dimension, days=..., indicator=...) -> str | None

返回紧凑 LLM 文本; 返回 None 表示"此维度未迁移到 canonical 层" —— 调用方
(agent_executor) 据此回退到旧 `_api_get` 路径. 这样可以逐维度增量迁移, 不 big-bang.

已迁维度:
  - medical_exam → 读 MedicalIndicator (与 twin/_collectors.fetch_latest_labs 同源)
  - wearable / 可穿戴 daily → 读 GarminData + device_source_priority 多源合并
    (与 twin/_fill_integrated_profile → MultiSourceIntegrationService 同源)

未迁维度 (genetic / diet / spo2 / cgm / weight / blood_pressure / ...) 返回 None,
由 agent_executor 走旧路径. 见设计文档 §5 迁移步骤.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy import desc as sa_desc
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ── 维度 → canonical reader 分发 ──────────────────────────────────────────
# 把 health_query 的 dimension 别名归一到 canonical reader.
# wearable daily 的多个别名(activity/heart_rate/hrv/...)指向同一份 GarminData,
# 经多源合并后一次性给出紧凑摘要 (旧逻辑每个别名各自 /garmin-analysis/me/xxx HTTP).
_WEARABLE_DIMS = {
    "wearable",
    "garmin",
    "activity",
    "heart_rate",
    "hrv",
    "body_battery",
    "stress",
}


def canonical_read(
    db: Session,
    user_id: Optional[int],
    dimension: str,
    *,
    days=7,
    indicator: str = "",
) -> Optional[str]:
    """统一 canonical 读入口. 返回紧凑文本; None = 此维度未迁移(调用方回退旧路径)."""
    if dimension == "medical_exam":
        return read_medical_indicators(db, user_id, indicator=indicator, days=days)
    if dimension in _WEARABLE_DIMS:
        return read_wearable_daily(db, user_id, days=days, focus=dimension)
    return None


# ── 化验/体检 → MedicalIndicator (与 Twin fetch_latest_labs 同源) ─────────
def read_medical_indicators(
    db: Session, user_id: Optional[int], *, indicator: str = "", days=7
) -> str:
    """化验/体检维度: 直接读 MedicalIndicator (与 Twin fetch_latest_labs 同源).

    - 带 indicator (如 LDL/HCY): 返回该指标最近 20 条时间序列.
    - 不带 indicator: 返回指标清单 + 每项最新值, 紧凑文本, 不丢给会截断的 _api_get.

    user_id 隔离: 只查传入 user_id 的记录.
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法查询化验指标"

    window_days = _window_days(days, floor=365)  # 化验低频, 放宽到 >=365 天
    since = date.today() - timedelta(days=window_days)

    from app.models.family_health import MedicalIndicator

    name = (indicator or "").strip()
    try:
        if name:
            up = name.upper()
            rows = (
                db.query(MedicalIndicator)
                .filter(
                    MedicalIndicator.user_id == user_id,
                    MedicalIndicator.record_date >= since,
                    or_(
                        MedicalIndicator.name == name,
                        MedicalIndicator.name_en == up,
                        MedicalIndicator.name.ilike(f"%{name}%"),
                        MedicalIndicator.name_en.ilike(f"%{name}%"),
                        MedicalIndicator.item_code.ilike(f"%{up}%"),
                    ),
                )
                .order_by(sa_desc(MedicalIndicator.record_date), sa_desc(MedicalIndicator.id))
                .limit(20)
                .all()
            )
            if not rows:
                return f"未找到化验指标「{name}」(最近 {window_days} 天内)。可能未录入, 或换个指标名再试。"
            lines = [f"化验指标「{rows[0].name}」时间序列 (最近 {len(rows)} 条):"]
            lines.extend(_format_indicator_line(r) for r in rows)
            return "\n".join(lines)

        # 无 indicator: 指标清单 + 每项最新值. 按 name 取最新一条.
        latest_date = (
            db.query(
                MedicalIndicator.name.label("name"),
                func.max(MedicalIndicator.record_date).label("md"),
            )
            .filter(
                MedicalIndicator.user_id == user_id,
                MedicalIndicator.record_date >= since,
            )
            .group_by(MedicalIndicator.name)
            .subquery()
        )
        rows = (
            db.query(MedicalIndicator)
            .join(
                latest_date,
                (MedicalIndicator.name == latest_date.c.name)
                & (MedicalIndicator.record_date == latest_date.c.md),
            )
            .filter(MedicalIndicator.user_id == user_id)
            .order_by(MedicalIndicator.is_abnormal.desc(), MedicalIndicator.name)
            .all()
        )
        seen: set = set()
        uniq = []
        for r in rows:
            if r.name in seen:
                continue
            seen.add(r.name)
            uniq.append(r)
        if not uniq:
            return (
                f"未找到任何化验/体检指标 (最近 {window_days} 天内)。"
                "用户可能还没录入体检报告; 可让用户拍照上传体检单或口述化验结果。"
            )
        abnormal = [r for r in uniq if r.is_abnormal]
        header = f"共有 {len(uniq)} 项化验指标 (取每项最新值"
        header += f", 其中 {len(abnormal)} 项异常):" if abnormal else "):"
        lines = [header]
        lines.extend(_format_indicator_line(r) for r in uniq)
        return "\n".join(lines)
    except Exception as e:
        logger.error("[health_read] 查询 MedicalIndicator 失败: %s", e)
        _safe_rollback(db)
        return f"Error: 查询化验指标失败: {e}"


def _format_indicator_line(r) -> str:
    """单条 MedicalIndicator → 紧凑一行: 名称 值 单位 (日期) [偏高/偏低/正常]."""
    date_s = r.record_date.isoformat() if r.record_date else "?"
    stale = ""
    if r.record_date:
        age_days = (date.today() - r.record_date).days
        if age_days > 180:
            stale = f" (较旧·约{age_days}天前)"
    val = r.value if r.value is not None else (r.value_text or "—")
    unit = f" {r.unit}" if r.unit else ""
    flag = "正常"
    if r.is_abnormal:
        flag = "异常"
        try:
            if r.value is not None:
                if r.reference_high is not None and r.value > r.reference_high:
                    flag = "偏高"
                elif r.reference_low is not None and r.value < r.reference_low:
                    flag = "偏低"
        except (TypeError, ValueError):
            pass
    ref = ""
    if r.reference_low is not None or r.reference_high is not None:
        lo = r.reference_low if r.reference_low is not None else ""
        hi = r.reference_high if r.reference_high is not None else ""
        ref = f" 参考 {lo}-{hi}"
    return f"- {r.name}: {val}{unit} ({date_s}){stale} [{flag}]{ref}"


# ── 可穿戴 daily → GarminData + 多源合并 (与 Twin 同源) ────────────────────
# 紧凑摘要要列的字段 → (中文标签, 单位). 顺序即输出顺序.
# 字段全部来自 GarminData 列名, 复用 device_source_priority 的 per-metric 优先级.
_WEARABLE_FIELDS: list[tuple[str, str, str]] = [
    ("steps", "步数", ""),
    ("resting_heart_rate", "静息心率", "bpm"),
    ("avg_heart_rate", "平均心率", "bpm"),
    ("hrv", "HRV", "ms"),
    ("sleep_score", "睡眠评分", ""),
    ("total_sleep_duration", "总睡眠", "min"),
    ("body_battery_current", "身体电量", ""),
    ("stress_level", "压力", ""),
    ("spo2_avg", "血氧均值", "%"),
    ("active_minutes", "活动分钟", "min"),
    ("calories_burned", "总消耗", "kcal"),
]


def read_wearable_daily(
    db: Session, user_id: Optional[int], *, days=7, focus: str = "wearable"
) -> str:
    """可穿戴 daily 维度: 直读 GarminData, 多源(garmin/apple-watch/ringconn/…)
    按 device_source_priority 逐字段合并 (与 Twin 的 MultiSourceIntegrationService 同源).

    紧凑摘要: 每天一行, 列关键指标 + 值 + 来源标注; 多天不截断.
    user_id 隔离 + DB 异常 rollback 不静默吞.
    """
    if user_id is None:
        return "Error: 当前会话无 user_id, 无法查询可穿戴数据"

    window_days = _window_days(days, floor=1)
    since = date.today() - timedelta(days=window_days)

    from app.models.daily_health import GarminData
    from app.services.multi_source_merger import merge_rows

    fields = [f for f, _, _ in _WEARABLE_FIELDS]
    try:
        rows = (
            db.query(GarminData)
            .filter(
                GarminData.user_id == user_id,
                GarminData.record_date >= since,
            )
            .order_by(sa_desc(GarminData.record_date))
            .all()
        )
        if not rows:
            return (
                f"未找到可穿戴(Garmin/Apple Watch/RingConn)数据 (最近 {window_days} 天内)。"
                "可能设备未同步; 可提醒用户打开 App 同步或检查授权。"
            )

        # 同一 (user, record_date) 可能有多源多行 → 按日期分组, 每组逐字段挑优先源.
        by_date: dict = {}
        for r in rows:
            by_date.setdefault(r.record_date, []).append(r)

        date_keys = sorted(by_date.keys(), reverse=True)
        all_sources: set = set()
        lines: list[str] = []
        for d in date_keys:
            merged = merge_rows(by_date[d], fields)
            vals = merged["values"]
            srcs = merged["sources"]
            all_sources.update(srcs.values())
            parts: list[str] = []
            for field, label, unit in _WEARABLE_FIELDS:
                v = vals.get(field)
                if v is None:
                    continue
                u = f"{unit}" if unit else ""
                parts.append(f"{label} {v}{u}")
            if not parts:
                continue
            lines.append(f"- {d.isoformat()}: " + ", ".join(parts))

        if not lines:
            return (
                f"可穿戴数据存在但关键指标均为空 (最近 {window_days} 天)。"
                "可能仅同步了部分维度; 建议检查设备同步完整性。"
            )

        src_note = ""
        if all_sources:
            src_note = f" 数据源: {', '.join(sorted(all_sources))}。"
        header = (
            f"可穿戴 daily 数据 (最近 {len(lines)} 天, 多源按设备优先级合并):" + src_note
        )
        return "\n".join([header, *lines])
    except Exception as e:
        logger.error("[health_read] 查询 GarminData 失败: %s", e)
        _safe_rollback(db)
        return f"Error: 查询可穿戴数据失败: {e}"


# ── 工具 ──────────────────────────────────────────────────────────────────
def _window_days(days, *, floor: int) -> int:
    try:
        w = int(days)
    except (TypeError, ValueError):
        w = floor
    return max(w, floor)


def _safe_rollback(db: Session) -> None:
    try:
        db.rollback()
    except Exception:
        pass
