"""工具 Schema 注册中心 — 统一健康 Agent 的工具定义

供 Agent 执行器使用的结构化工具接口。覆盖所有健康数据的读/写/分析操作。
"""
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# ── 核心健康工具定义 ────────────────────────────────────

HEALTH_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "health_query",
            "description": "查询用户的健康数据，包括步数、心率、HRV、睡眠、血压、体重、运动、补剂状态等。当用户问起健康指标、体能数据或每日统计时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dimension": {
                        "type": "string",
                        "enum": ["comprehensive", "sleep", "heart_rate", "hrv", "activity",
                                 "spo2", "weight", "blood_pressure", "supplements", "water",
                                 "diet", "exercise", "body_battery", "stress",
                                 "medical_exam", "genetic", "medication"],
                        "description": "要查询的数据维度",
                    },
                    "days": {
                        "type": "integer",
                        "default": 7,
                        "description": "查询最近几天的数据",
                    },
                    "indicator": {
                        "type": "string",
                        "description": "具体指标名称（仅 medical_exam 和 genetic 时使用），如 'HCY'、'MTHFR'、'LDL' 等",
                    },
                },
                "required": ["dimension"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "health_record",
            "description": "记录健康数据。当用户要记录饮水、体重、血压、运动、饮食、补剂服用、鼻炎症状、情绪、用药、生病等信息时使用。必须调用此工具才能真正保存数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "record_type": {
                        "type": "string",
                        "enum": ["water", "weight", "blood_pressure", "exercise",
                                 "diet", "supplement", "supplement_group", "rhinitis",
                                 "mood", "medication", "illness", "symptom",
                                 "garmin_sync", "reminder"],
                        "description": """记录类型：
- water: 饮水（"喝了杯水"、"喝了咖啡"）
- diet: 饮食（"早餐吃了…"、"吃了牛排"）
- supplement: 单个补剂打卡（"吃了鱼油"）
- supplement_group: 按时段批量打卡（"早上的药都吃了"）
- weight: 体重
- blood_pressure: 血压
- exercise: 运动/打卡
- rhinitis: 鼻炎症状（喷嚏/鼻塞/流涕）
- mood: 情绪
- medication: 用药记录
- illness: 生病/急性症状
- symptom: 慢性病症状日志
- garmin_sync: 触发 Garmin 数据同步
- reminder: 设置提醒""",
                    },
                    "data": {
                        "type": "object",
                        "description": """记录的具体数据。各类型示例：
- water: {"amount": 250}（毫升，默认250）
- diet: {"meal_type": "breakfast|lunch|dinner|snack", "food_items": "牛奶200ml、面包1片", "record_date": "2026-04-16"}
- supplement: {"supplement_name": "鱼油"}（按名称匹配已定义补剂）
- supplement_group: {"timing": "morning|noon|evening|bedtime"}
- weight: {"weight": 72.2, "record_date": "2026-04-16"}
- blood_pressure: {"systolic": 120, "diastolic": 80, "record_date": "2026-04-16"}
- exercise: {"exercise_type": "running", "duration": 30, "distance": 5.0}
- rhinitis: {"sneezing": 2, "congestion": 1, "runny_nose": 0}
- mood: {"score": 7, "notes": "心情不错"}
- medication: {"medication_name": "布洛芬", "taken_time": "08:00"}
- illness: {"illness_name": "感冒", "severity": 5, "start_date": "2026-04-16"}
- symptom: {"profile_id": 1, "symptoms": [{"name": "头痛", "severity": 3}]}
- garmin_sync: {}（无需参数）
- reminder: {"title": "吃药提醒", "remind_at": "2026-04-17T08:00:00+08:00"}""",
                    },
                },
                "required": ["record_type", "data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "health_analysis",
            "description": "深度健康分析。当用户需要综合分析、趋势洞察、恢复评估、风险评估时使用。比简单查询更深入。",
            "parameters": {
                "type": "object",
                "properties": {
                    "analysis_type": {
                        "type": "string",
                        "enum": ["comprehensive", "sleep_insight", "heart_rate_insight",
                                 "recovery_status", "risk_factors", "trend",
                                 "supplement_effectiveness", "orchestrator"],
                        "description": """分析类型：
- comprehensive: 综合健康分析
- sleep_insight: 睡眠深度洞察
- heart_rate_insight: 心率/HRV 洞察
- recovery_status: 恢复力评估
- risk_factors: 风险因素分析
- trend: 趋势变化分析
- supplement_effectiveness: 补剂效果评估
- orchestrator: 多专家协作深度分析（最复杂，用于跨领域问题）""",
                    },
                    "days": {
                        "type": "integer",
                        "default": 7,
                        "description": "分析时间范围",
                    },
                    "question": {
                        "type": "string",
                        "description": "用户的具体问题（仅 orchestrator 类型时使用）",
                    },
                },
                "required": ["analysis_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "environment_check",
            "description": "查询当前天气、空气质量、户外运动适宜度等环境数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "check_type": {
                        "type": "string",
                        "enum": ["weather", "air_quality", "outdoor_suitability"],
                        "description": "查询类型",
                    },
                },
                "required": ["check_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "supplement_guide",
            "description": "获取今日补剂服用指南，包括服用顺序、动态调整建议等。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_plan",
            "description": "管理健康计划：生成周计划、完成计划项、保存内容到首页卡片。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["generate_weekly", "complete_item", "save_to_card"],
                        "description": """操作类型：
- generate_weekly: 生成本周/下周健康计划
- complete_item: 标记计划项完成
- save_to_card: 保存内容到首页行动卡片""",
                    },
                    "data": {
                        "type": "object",
                        "description": """操作数据：
- generate_weekly: {"target_week": "current|next", "user_focus": ["睡眠", "运动"]}
- complete_item: {"plan_id": 1, "item_id": 2}
- save_to_card: {"title": "标题", "content": "markdown内容", "card_type": "plan|insight|recommendation"}""",
                    },
                },
                "required": ["action", "data"],
            },
        },
    },
]


def get_health_tools() -> List[Dict[str, Any]]:
    """获取所有健康工具定义"""
    return HEALTH_TOOLS


def get_tool_names() -> List[str]:
    """获取所有工具名称"""
    return [t["function"]["name"] for t in HEALTH_TOOLS]
