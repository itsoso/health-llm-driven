"""
简单意图分类器。

MVP 用纯关键字匹配，后续可升级为小 LLM 或 embedding 分类。
"""

import re
from typing import List

from app.orchestrator.schema import Intent


# 类别 → 关键字（中英）
# 顺序重要：优先级高的类别排在前面（safety 永远优先）
_CATEGORY_KEYWORDS = {
    "safety": [
        # 明确的安全/药物关键词（单独出现即命中）
        "药物", "用药", "相互作用", "能吃", "停药", "副作用", "禁忌",
        "风险", "安全", "告警", "警报",
        "基因", "cyp", "mthfr", "aldh2", "pgx",
        "drug interaction", "safe to", "risk of",
        # 常见药物名 —— 提到具体药名一律走 safety
        "华法林", "warfarin", "阿司匹林", "aspirin", "布洛芬", "ibuprofen",
        "他汀", "statin", "莫米松", "西替利嗪", "替尔泊肽", "tirzepatide",
        "胰岛素", "insulin", "格列", "sulfonyl", "可待因", "codeine",
        "咪唑", "mazole",
        # 补剂相关
        "补剂", "益生菌", "维生素",
    ],
    "labs": [
        "化验", "体检", "肝酶", "肝功", "肾功", "血脂", "血糖", "胆固醇",
        "hba1c", "ldl", "alt", "ast", "ggt", "报告", "lab",
    ],
    "recovery": [
        "恢复", "累", "疲劳", "睡眠质量", "睡不着", "hrv", "休息", "疲惫",
        "sleep quality", "recover", "fatigue", "rested",
    ],
    "fuel": [
        "吃什么", "饮食", "营养", "热量", "卡路里", "蛋白质", "碳水水化合物",
        "减脂餐", "增肌餐", "早餐", "午餐", "晚餐", "吃饭",
        "what to eat", "diet", "nutrition", "protein", "carb",
    ],
    "movement": [
        "训练计划", "训练", "跑步", "健身", "锻炼", "力量训练", "有氧",
        "workout", "exercise plan", "train", "running",
    ],
    "mental": [
        "情绪", "压力大", "压力很大", "压力好大", "压力太大",
        "焦虑", "抑郁", "心情", "心情不好", "情绪低落", "情绪不好",
        "心烦", "烦躁", "难过", "沮丧", "低落",
        "stress", "mood", "anxiety", "depression", "down", "overwhelmed",
    ],
    "chronic": [
        "鼻炎", "喷嚏不停", "过敏性鼻炎", "高血压", "糖尿病", "甲状腺",
        "rhinitis", "diabetes", "thyroid",
    ],
    "longevity": [
        "抗衰", "抗老", "逆龄", "衰老",
        "生物年龄", "身体年龄", "表型年龄", "phenoage", "phenotypic age",
        "longevity", "aging", "biological age",
    ],
}


def classify_intent(query: str) -> Intent:
    """对用户 query 做关键字意图分类。"""
    q = (query or "").lower()
    categories: List[str] = []
    matched_keywords: List[str] = []

    for cat, kws in _CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in q:
                if cat not in categories:
                    categories.append(cat)
                matched_keywords.append(kw)
                break

    # 如果没匹配到任何类别，默认 general（让所有 specialist 自行决定）
    if not categories:
        categories.append("general")

    return Intent(raw_query=query, categories=categories, keywords=matched_keywords)
