"""Chat Function Calling Tools 定义

定义健康系统的 tools schema，供 LLM Function Calling 使用。
"""
import logging
from datetime import date, datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


HEALTH_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "record_water",
            "description": "记录用户饮水量",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount_ml": {
                        "type": "integer",
                        "description": "饮水量，单位毫升，默认250",
                    }
                },
                "required": ["amount_ml"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_weight",
            "description": "记录用户体重",
            "parameters": {
                "type": "object",
                "properties": {
                    "weight_kg": {
                        "type": "number",
                        "description": "体重，单位千克",
                    }
                },
                "required": ["weight_kg"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_blood_pressure",
            "description": "记录用户血压",
            "parameters": {
                "type": "object",
                "properties": {
                    "systolic": {"type": "integer", "description": "收缩压（高压）"},
                    "diastolic": {"type": "integer", "description": "舒张压（低压）"},
                    "heart_rate": {"type": "integer", "description": "心率（可选）"},
                },
                "required": ["systolic", "diastolic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_checkin",
            "description": "快速打卡",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_name": {
                        "type": "string",
                        "description": "打卡模板名称，如'俯卧撑'、'深蹲'、'洗鼻'",
                    },
                    "value": {
                        "type": "number",
                        "description": "打卡数值（可选），如俯卧撑30个",
                    },
                },
                "required": ["template_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_diet",
            "description": "记录饮食",
            "parameters": {
                "type": "object",
                "properties": {
                    "meal_type": {
                        "type": "string",
                        "enum": ["breakfast", "lunch", "dinner", "extra"],
                        "description": "餐次：早餐/午餐/晚餐/加餐",
                    },
                    "foods": {
                        "type": "string",
                        "description": "食物描述",
                    },
                    "calories": {
                        "type": "integer",
                        "description": "估算卡路里（可选）",
                    },
                },
                "required": ["meal_type", "foods"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_plan",
            "description": "为用户创建健康周计划",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_week": {
                        "type": "string",
                        "enum": ["current", "next"],
                        "description": "目标周：本周或下周",
                    },
                    "user_focus": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "用户关注重点",
                    },
                },
                "required": ["target_week"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workout_analyze",
            "description": "分析用户最近完成的运动",
            "parameters": {
                "type": "object",
                "properties": {
                    "workout_type": {
                        "type": "string",
                        "description": "运动类型：running/cycling/swimming/hiit/strength/yoga/other",
                    }
                },
                "required": ["workout_type"],
            },
        },
    },
]


def get_tool_by_name(name: str) -> Optional[Dict[str, Any]]:
    """根据名称查找工具定义"""
    for tool in HEALTH_TOOLS:
        if tool["function"]["name"] == name:
            return tool
    return None


async def _record_water(args: Dict, db, user) -> Dict[str, Any]:
    """执行饮水记录"""
    from app.models.daily_health import WaterIntake
    from app.utils.timezone import get_china_now
    amount = args.get("amount_ml", 250)
    now = get_china_now()
    record = WaterIntake(
        user_id=user.id,
        record_date=now.date(),
        amount=amount,
        intake_time=now,
        drink_type="水",
    )
    db.add(record)
    db.commit()
    return {"success": True, "amount": amount, "message": f"已记录饮水 {amount}ml"}


async def _record_weight(args: Dict, db, user) -> Dict[str, Any]:
    """执行体重记录"""
    from app.models.weight import WeightRecord
    from app.utils.timezone import get_china_today
    weight = args["weight_kg"]
    today = get_china_today()
    existing = db.query(WeightRecord).filter(
        WeightRecord.user_id == user.id,
        WeightRecord.record_date == today,
    ).first()
    if existing:
        existing.weight = weight
    else:
        record = WeightRecord(user_id=user.id, record_date=today, weight=weight)
        db.add(record)
    db.commit()
    return {"success": True, "weight": weight, "message": f"已记录体重 {weight}kg"}


async def _record_blood_pressure(args: Dict, db, user) -> Dict[str, Any]:
    """执行血压记录"""
    from app.models.blood_pressure import BloodPressureRecord
    from app.utils.timezone import get_china_now
    now = get_china_now()
    record = BloodPressureRecord(
        user_id=user.id,
        record_date=now.date(),
        systolic=args["systolic"],
        diastolic=args["diastolic"],
        pulse=args.get("heart_rate"),
        measured_at=now,
    )
    db.add(record)
    db.commit()
    return {
        "success": True,
        "message": f"已记录血压 {args['systolic']}/{args['diastolic']}",
    }


async def _record_checkin(args: Dict, db, user) -> Dict[str, Any]:
    """执行打卡"""
    from app.models.checkin import CheckinTemplate, CheckinRecord
    from app.utils.timezone import get_china_today
    template_name = args["template_name"]
    template = db.query(CheckinTemplate).filter(
        CheckinTemplate.user_id == user.id,
        CheckinTemplate.name == template_name,
        CheckinTemplate.is_active == True,
    ).first()
    if not template:
        return {"success": False, "message": f"未找到打卡模板: {template_name}"}

    today = get_china_today()

    # 检查今天是否已打卡
    existing = db.query(CheckinRecord).filter(
        CheckinRecord.template_id == template.id,
        CheckinRecord.user_id == user.id,
        CheckinRecord.checkin_date == today,
    ).first()
    if existing:
        return {"success": True, "message": f"{template_name} 今天已经打过卡了"}

    value = args.get("value") or template.default_target or 1
    target = template.default_target or 1
    completion_rate = (value / target * 100) if target > 0 else 100

    record = CheckinRecord(
        user_id=user.id,
        template_id=template.id,
        checkin_date=today,
        value=value,
        target=target,
        completion_rate=completion_rate,
    )
    db.add(record)

    # 更新模板统计
    template.total_checkins = (template.total_checkins or 0) + 1
    template.total_value = (template.total_value or 0) + value
    template.last_checkin_date = today

    db.commit()
    return {"success": True, "message": f"已完成打卡: {template_name}"}


async def _record_diet(args: Dict, db, user) -> Dict[str, Any]:
    """执行饮食记录"""
    from app.models.daily_health import DietRecord
    from app.utils.timezone import get_china_today
    meal_map = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐", "extra": "加餐"}
    today = get_china_today()
    record = DietRecord(
        user_id=user.id,
        record_date=today,
        meal_type=meal_map.get(args.get("meal_type", "lunch"), "午餐"),
        food_items=args["foods"],
        calories=args.get("calories"),
    )
    db.add(record)
    db.commit()
    return {"success": True, "message": f"已记录饮食: {args['foods']}"}


# 工具名称 → 执行函数映射
TOOL_EXECUTORS = {
    "record_water": _record_water,
    "record_weight": _record_weight,
    "record_blood_pressure": _record_blood_pressure,
    "record_checkin": _record_checkin,
    "record_diet": _record_diet,
}


async def execute_tool(name: str, arguments: Dict[str, Any], db, user) -> Dict[str, Any]:
    """执行工具调用"""
    executor = TOOL_EXECUTORS.get(name)
    if not executor:
        # create_plan 和 workout_analyze 返回特殊标记，由 chat_service 处理
        if name in ("create_plan", "workout_analyze"):
            return {"action_type": name, "arguments": arguments}
        return {"error": f"未知工具: {name}"}
    try:
        return await executor(arguments, db, user)
    except Exception as e:
        logger.error(f"执行工具 {name} 失败: {e}")
        return {"error": str(e)}
