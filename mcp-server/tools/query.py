"""健康数据只读查询工具。"""
import json
import logging
from datetime import date, datetime
from typing import Optional

from client import HealthAPIClient
from config import Config

logger = logging.getLogger(__name__)

_client: Optional[HealthAPIClient] = None


def get_client() -> HealthAPIClient:
    """获取单例 HealthAPIClient 实例（懒初始化）"""
    global _client
    if _client is None:
        _client = HealthAPIClient()
    return _client


def _json(data) -> str:
    """将数据序列化为 JSON 字符串"""
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _today() -> str:
    """返回今天的日期字符串 (YYYY-MM-DD)"""
    return date.today().isoformat()


def _period_to_days(period: str) -> int:
    """将 period 字符串转换为天数"""
    mapping = {"today": 1, "week": 7, "month": 30}
    return mapping.get(period, 1)


async def get_health_summary(period: str = "today") -> str:
    """获取健康数据综合摘要，包括睡眠、心率、压力、Body Battery、活动等。

    Args:
        period: 时间范围，可选值: "today"(今天), "week"(最近7天), "month"(最近30天)
    """
    client = get_client()
    days = _period_to_days(period)
    data = await client.get("/garmin-analysis/me/comprehensive", params={"days": days})
    return _json(data)


async def get_weight_history(days: int = 7) -> str:
    """获取体重记录历史。

    Args:
        days: 获取最近多少条记录，默认7条
    """
    client = get_client()
    data = await client.get("/weight/records/me", params={"limit": days})
    return _json(data)


async def get_blood_pressure_history(days: int = 7) -> str:
    """获取血压记录历史。

    Args:
        days: 获取最近多少条记录，默认7条
    """
    client = get_client()
    data = await client.get("/blood-pressure/records/me", params={"limit": days})
    return _json(data)


async def get_water_intake(date: Optional[str] = None) -> str:
    """获取某天的饮水记录汇总。

    Args:
        date: 日期字符串，格式 YYYY-MM-DD，默认今天
    """
    client = get_client()
    target_date = date or _today()
    data = await client.get(f"/water/records/me/date/{target_date}")
    return _json(data)


async def get_sleep_data(days: int = 7) -> str:
    """获取睡眠数据分析，包括睡眠时长、深睡/浅睡/REM 比例、睡眠评分等。

    Args:
        days: 获取最近多少天的数据，默认7天
    """
    client = get_client()
    data = await client.get("/garmin-analysis/me/sleep", params={"days": days})
    return _json(data)


async def get_heart_rate(days: int = 7) -> str:
    """获取心率数据分析，包括静息心率、平均心率、最大心率、HRV 等。

    Args:
        days: 获取最近多少天的数据，默认7天
    """
    client = get_client()
    data = await client.get("/garmin-analysis/me/heart-rate", params={"days": days})
    return _json(data)


async def get_workout_history(days: int = 7, workout_type: Optional[str] = None) -> str:
    """获取运动记录历史，包括跑步、骑行、力量训练等各类运动。

    Args:
        days: 获取最近多少天的记录，默认7天
        workout_type: 运动类型筛选，如 "running", "cycling", "strength" 等，为空则返回全部
    """
    client = get_client()
    params = {"days": days}
    if workout_type:
        params["workout_type"] = workout_type
    data = await client.get("/workout/me", params=params)
    return _json(data)


async def get_diet_records(days: int = 3) -> str:
    """获取饮食记录，包括每餐食物、热量和营养素（蛋白质、碳水、脂肪）。

    Args:
        days: 获取最近多少天的饮食记录，默认3天
    """
    client = get_client()
    # 每天最多 3 餐，用 days*3 作为 limit
    data = await client.get("/diet/records/me", params={"limit": days * 3})
    return _json(data)


async def get_checkin_status(date: Optional[str] = None) -> str:
    """获取打卡状态汇总，包括各打卡模板的完成情况。

    Args:
        date: 日期字符串，格式 YYYY-MM-DD，默认今天。目前仅支持查询今日打卡状态。
    """
    client = get_client()
    data = await client.get("/checkin/records/today")
    return _json(data)


async def get_achievements() -> str:
    """获取用户成就徽章列表，包括已解锁的徽章和各徽章的进度。"""
    client = get_client()
    data = await client.get("/achievements/me")
    return _json(data)


_REPORT_EVIDENCE_NOTE = (
    "来源为已存储的报告文本，可能包含 OCR 摘要；未核验原始影像。"
    "摘要未提及某项不代表该项正常或没有病史；解读具体分级前读取报告详情。"
)


def _report_read_error() -> str:
    # Never turn HTTP/permission/schema failures into an empty medical history.
    return _json({"status": "error", "code": "medical_report_read_failed",
                  "message": "报告读取失败，本次未确认报告内容，不能据此判断没有相关病史。"})


def _valid_report(value) -> bool:
    return (isinstance(value, dict) and "error" not in value and "detail" not in value
            and type(value.get("id")) is int and value["id"] > 0
            and "overall_assessment" in value
            and (value["overall_assessment"] is None
                 or isinstance(value["overall_assessment"], str)))


async def get_medical_exam_reports(limit: int = 20, skip: int = 0) -> str:
    """分页查询认证本人的体检/影像报告摘要，不代表完整病史。

    摘要有明确截断标记；具体结论/分级请用 get_medical_exam_report(id)
    读取全文。limit 为 1..100，skip 为非负整数。失败不能解释为没有报告。
    """
    if type(limit) is not int or not 1 <= limit <= 100 or type(skip) is not int or skip < 0:
        raise ValueError("limit must be 1..100 and skip must be a nonnegative integer")
    data = await get_client().get("/medical-exams/me", params={"limit": limit, "skip": skip})
    if not isinstance(data, list) or len(data) > limit or not all(_valid_report(row) for row in data):
        return _report_read_error()
    reports = []
    for row in data:
        summary = row["overall_assessment"]
        truncated = summary is not None and len(summary) > 500
        reports.append({
            **{key: row[key] for key in ("id", "exam_date", "exam_type", "body_system") if key in row},
            "overall_assessment": summary[:500] + "..." if truncated else summary,
            "overall_assessment_truncated": truncated,
            "detail_tool": "get_medical_exam_report",
            "detail_path": f"/medical-exams/me/{row['id']}",
        })
    return _json({"status": "ok", "reports": reports, "limit": limit, "skip": skip,
                  "may_have_more": len(data) == limit,
                  "next_skip": skip + limit if len(data) == limit else None,
                  "message": "本页报告摘要。" if reports else "本页未返回报告记录。",
                  "original_image_verified": False, "evidence_note": _REPORT_EVIDENCE_NOTE})


async def get_medical_exam_report(exam_id: int) -> str:
    """读取认证本人的指定报告全文，保留完整 overall_assessment 和已记录来源字段。

    exam_id 来自报告列表。不核验原影像、不修改报告；拒绝/失败不代表无病史。
    """
    if type(exam_id) is not int or exam_id <= 0:
        raise ValueError("exam_id must be a positive integer")
    data = await get_client().get(f"/medical-exams/me/{exam_id}")
    if not _valid_report(data) or data["id"] != exam_id:
        return _report_read_error()
    return _json({"status": "ok", "report": data,
                  "original_image_verified": False, "evidence_note": _REPORT_EVIDENCE_NOTE})
