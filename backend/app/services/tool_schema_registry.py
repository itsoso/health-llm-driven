"""工具 Schema 注册中心 — 从 SKILL.md 生成 OpenAI 格式的 tool schemas

将 Skill 定义转化为结构化工具，供 Hermes/Claude 等 Agent 使用。
不替换 OpenClaw 的 SKILL.md 执行方式，而是提供并行的结构化接口。
"""
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# ── 核心健康工具定义 ────────────────────────────────────
# 基于 skills/ 目录中最常用的能力，提炼为结构化 tool schemas
# Hermes 模型通过 OpenAI-compatible tool_call 来调用

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
                                 "diet", "exercise", "body_battery", "stress"],
                        "description": "要查询的数据维度",
                    },
                    "days": {
                        "type": "integer",
                        "default": 7,
                        "description": "查询最近几天的数据",
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
            "description": "记录健康数据，包括饮水、体重、血压、运动打卡、饮食、补剂服用、鼻炎症状等。当用户要记录健康信息时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "record_type": {
                        "type": "string",
                        "enum": ["water", "weight", "blood_pressure", "exercise",
                                 "diet", "supplement", "rhinitis", "mood", "medication"],
                        "description": "记录类型",
                    },
                    "data": {
                        "type": "object",
                        "description": """记录的具体数据。各类型必填字段：
- weight: {"weight": 72.2, "record_date": "2026-04-09"}
- diet: {"meal_type": "breakfast|lunch|dinner|snack", "food_items": "牛奶200ml", "calories": 120, "record_date": "2026-04-09"}
- water: {"amount": 300}（毫升）
- blood_pressure: {"systolic": 120, "diastolic": 80, "record_date": "2026-04-09"}
- exercise: {"exercise_type": "pushup", "count": 50}
- rhinitis: {"sneezing": 2, "congestion": 1, "runny_nose": 0}
- mood: {"score": 7, "notes": "心情不错"}
必须调用此工具才能真正保存数据，不要只在回复中说"已记录"而不调用工具。""",
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
            "description": "分析用户的健康趋势、风险因素、睡眠质量、心率变异性等。当用户需要深度分析或健康洞察时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "analysis_type": {
                        "type": "string",
                        "enum": ["comprehensive", "sleep_insight", "heart_rate_insight",
                                 "recovery_status", "risk_factors", "trend"],
                        "description": "分析类型",
                    },
                    "days": {
                        "type": "integer",
                        "default": 7,
                        "description": "分析时间范围",
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
            "description": "查询当前天气、空气质量、花粉指数等环境数据，用于健康建议。",
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
            "description": "获取今日补剂服用指南，包括服用顺序、动态调整建议、药物提醒等。",
            "parameters": {
                "type": "object",
                "properties": {},
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
