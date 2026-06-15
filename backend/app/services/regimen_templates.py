"""用药方案模板 —— 「录入脚手架」,不是「用药建议」。

定位(安全边界,务必读):
- 这些模板的唯一目的是帮用户 30 秒把「医生已经开好的」常见方案录全,而不是一个个手填十几个时点。
- 系统**永不**用模板自动开方 / 调量 / 换药。用户选模板后必须核对剂量(医生可能调过)并确认
  「这是我医生开的」,才会实例化。
- 具体几种药、剂量、疗程长短一律以医生处方为准;模板只提供常见组合的预填值。

数据结构(纯数据,无副作用):
  TEMPLATES[template_id] = {
    "name": 中文方案名,
    "indication": 适应症(展示用),
    "phases": [ {"name","duration_days","meds":[MED, ...]}, ... ],
    "review_on_complete": 疗程结束复查说明(接 medication_course_service),
  }
  MED = {"name","dosage","times_per_day","reminder_times","timing_relation","meal_anchor"}
  timing_relation ∈ empty_stomach/before_meal_30/before_meal/with_meal/after_meal/bedtime/anytime
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional


# 默认早晚两次的提醒时间(用户可改);相对吃饭的真实触发由 P2 智能提醒细化
_BID = ["07:00", "19:00"]
_QD_MORNING = ["07:00"]


TEMPLATES: Dict[str, Dict[str, Any]] = {
    # 幽门螺杆菌根除 · 铋剂四联(14 天)+ PPI 愈合 —— 当前一线方案
    "hp_bismuth_quad_14d": {
        "name": "幽门螺杆菌根除·铋剂四联 + PPI 愈合",
        "indication": "胃溃疡 / 幽门螺杆菌阳性",
        "hp_status": "positive",   # 仅 Hp 阳性适用;Hp 阴性不要用根除抗生素
        "phases": [
            {
                "name": "根除期",
                "duration_days": 14,
                "meds": [
                    {"name": "PPI(雷贝拉唑)", "dosage": "10mg", "times_per_day": 2,
                     "reminder_times": _BID, "timing_relation": "before_meal_30", "meal_anchor": None},
                    {"name": "铋剂(枸橼酸铋钾)", "dosage": "220mg", "times_per_day": 2,
                     "reminder_times": _BID, "timing_relation": "before_meal_30", "meal_anchor": None},
                    {"name": "阿莫西林", "dosage": "1000mg", "times_per_day": 2,
                     "reminder_times": _BID, "timing_relation": "after_meal", "meal_anchor": None},
                    {"name": "克拉霉素", "dosage": "500mg", "times_per_day": 2,
                     "reminder_times": _BID, "timing_relation": "after_meal", "meal_anchor": None},
                ],
            },
            {
                "name": "愈合期",
                "duration_days": 42,  # 4–8 周,取 6 周
                "meds": [
                    {"name": "PPI(雷贝拉唑)", "dosage": "10mg", "times_per_day": 1,
                     "reminder_times": _QD_MORNING, "timing_relation": "before_meal_30", "meal_anchor": "breakfast"},
                ],
            },
        ],
        "review_on_complete": "根除结束后约消化内科复查:停药≥4 周做 C13/C14 呼气试验确认根除;胃溃疡需复查胃镜确认愈合。",
    },

    # 幽门螺杆菌根除 · 三联变体(去铋剂)+ PPI 愈合
    "hp_triple_14d": {
        "name": "幽门螺杆菌根除·三联 + PPI 愈合",
        "indication": "胃溃疡 / 幽门螺杆菌阳性(三联)",
        "hp_status": "positive",
        "phases": [
            {
                "name": "根除期",
                "duration_days": 14,
                "meds": [
                    {"name": "PPI(雷贝拉唑)", "dosage": "10mg", "times_per_day": 2,
                     "reminder_times": _BID, "timing_relation": "before_meal_30", "meal_anchor": None},
                    {"name": "阿莫西林", "dosage": "1000mg", "times_per_day": 2,
                     "reminder_times": _BID, "timing_relation": "after_meal", "meal_anchor": None},
                    {"name": "克拉霉素", "dosage": "500mg", "times_per_day": 2,
                     "reminder_times": _BID, "timing_relation": "after_meal", "meal_anchor": None},
                ],
            },
            {
                "name": "愈合期",
                "duration_days": 42,
                "meds": [
                    {"name": "PPI(雷贝拉唑)", "dosage": "10mg", "times_per_day": 1,
                     "reminder_times": _QD_MORNING, "timing_relation": "before_meal_30", "meal_anchor": "breakfast"},
                ],
            },
        ],
        "review_on_complete": "根除结束后约消化内科复查:停药≥4 周做 C13/C14 呼气试验确认根除;胃溃疡需复查胃镜确认愈合。",
    },

    # Hp 阴性胃溃疡:PPI 愈合疗程(无抗生素)。锚点用户潘宝坤即此型(活检 HP-)。
    "gu_ppi_healing_8w": {
        "name": "胃溃疡 PPI 愈合疗程(Hp 阴性)",
        "indication": "胃溃疡 / 幽门螺杆菌阴性 —— 不需根除抗生素,PPI 愈合 + 去除诱因(NSAID/应激)",
        "hp_status": "negative",
        "phases": [
            {
                "name": "愈合期",
                "duration_days": 56,  # 8 周
                "meds": [
                    {"name": "PPI(雷贝拉唑)", "dosage": "10–20mg", "times_per_day": 1,
                     "reminder_times": _QD_MORNING, "timing_relation": "before_meal_30", "meal_anchor": "breakfast"},
                ],
            },
        ],
        "review_on_complete": "短期治疗后复查胃镜/活检确认愈合(医生医嘱);排查并去除诱因:NSAID/阿司匹林、酒精、应激;长期 PPI 者评估 B12/镁/骨密度。",
    },
}


# 录入时强制展示的免责声明 —— API 必须把它带回前端,确认页必须显示
TEMPLATE_DISCLAIMER = (
    "此为常见方案的预填模板,仅用于快速录入医生已开具的处方。"
    "请逐项核对药名、剂量、疗程是否与医生处方一致;系统不提供用药建议,有疑问请咨询医生或药师。"
)


def list_templates() -> List[Dict[str, Any]]:
    """列出可选模板(轻量,给前端选择页)。"""
    return [
        {
            "template_id": tid,
            "name": t["name"],
            "indication": t.get("indication"),
            "hp_status": t.get("hp_status"),   # positive/negative —— 前端/agent 据 HP 状态分流
            "phase_count": len(t["phases"]),
            "phase_names": [p["name"] for p in t["phases"]],
        }
        for tid, t in TEMPLATES.items()
    ]


def templates_for_hp_status(hp_status: Optional[str]) -> List[Dict[str, Any]]:
    """按 Hp 状态过滤模板:
    - "positive" → 只返回根除方案;
    - "negative" → 只返回 PPI 愈合(不含抗生素根除);
    - None/未知 → 返回全部,让用户/医生自行选(不替医生分流)。
    """
    items = list_templates()
    if hp_status in ("positive", "negative"):
        return [t for t in items if t.get("hp_status") == hp_status]
    return items


def get_template(template_id: str) -> Optional[Dict[str, Any]]:
    """取模板深拷贝(防调用方改到模块级常量)。未知 id → None。"""
    t = TEMPLATES.get(template_id)
    return deepcopy(t) if t else None


def phase_med_names(phases: List[Dict[str, Any]], phase_index: int = 0) -> List[str]:
    """某阶段的全部药名(给 DDI 预检用)。越界 → 空列表。"""
    if not phases or phase_index < 0 or phase_index >= len(phases):
        return []
    return [m.get("name", "") for m in (phases[phase_index].get("meds") or []) if m.get("name")]
