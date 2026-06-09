# -*- coding: utf-8 -*-
"""冷启动信息增益 —— 下一步补哪项数据解锁最多价值(Next Horizon Tier 4)。

数据稀疏是冷启动最大摩擦。本服务按"补这项能解锁什么"给出**优先级排序的下一步建议**,
让 day-1 用户知道"先做哪一件"信息回报最高。

诚实:这是启发式"解锁价值"排序(unlock-driven),非严格信息论 info gain;
只读 Twin,不写;缺什么、解锁什么都基于真实字段。
"""
from __future__ import annotations

from typing import Any

# PhenoAge 的 9 项血检(缺得越少、补齐解锁"生物年龄"价值越高)
_PHENOAGE_FIELDS = {
    "albumin": "白蛋白", "creatinine": "肌酐", "blood_glucose": "空腹血糖",
    "crp": "C 反应蛋白", "lymphocyte_pct": "淋巴细胞%", "mcv": "MCV",
    "rdw": "RDW", "alp": "碱性磷酸酶", "wbc": "白细胞",
}


def next_best_data(twin: Any) -> dict[str, Any]:
    """返回按解锁价值排序的"下一步补数据"建议(纯函数,只读 twin)。"""
    labs = getattr(twin, "labs", None)
    phys = getattr(twin, "physiological", None)
    body = getattr(twin, "body_composition", None)

    suggestions: list[dict[str, Any]] = []

    # 1) 生物年龄(PhenoAge):差得越少,补齐 ROI 越高
    if labs is not None and getattr(labs, "phenotypic_age", None) is None:
        missing = [zh for f, zh in _PHENOAGE_FIELDS.items() if getattr(labs, f, None) is None]
        got = len(_PHENOAGE_FIELDS) - len(missing)
        if missing:
            # 已有越多 → priority 越高(补最后几项就解锁)
            priority = 50 + got * 5
            suggestions.append({
                "item": "完成一次常规血检(含 " + "、".join(missing[:4]) + ("…" if len(missing) > 4 else "") + ")",
                "unlocks": "生物年龄(PhenoAge)+ 抗衰 N-of-1 闭环",
                "missing_count": len(missing),
                "have_count": got,
                "priority": priority,
                "route": "/medical-exams",
            })

    # 2) 心肺适能 VO2max / 体能年龄(可穿戴几乎零成本)
    if phys is not None and getattr(phys, "vo2max_running", None) is None \
            and getattr(phys, "vo2max_fitness_age", None) is None:
        suggestions.append({
            "item": "连接 Garmin/可穿戴并做一次有氧(跑/走)",
            "unlocks": "VO2max / 体能年龄(全因死亡率最强单一预测因子)",
            "priority": 40,
            "route": "/import",
        })

    # 3) 体成分基线(体重/腰围)
    if body is not None and getattr(body, "weight_kg", None) is None:
        suggestions.append({
            "item": "记一次体重(可选腰围)",
            "unlocks": "BMI / 代谢基线 + 体重轨迹监测",
            "priority": 30,
            "route": "/indicator-history?type=weight",
        })

    suggestions.sort(key=lambda s: -s["priority"])
    return {
        "suggestions": suggestions,
        "note": "按'补这项能解锁什么'的启发式排序(unlock-driven),非严格信息论 info gain。",
    }
