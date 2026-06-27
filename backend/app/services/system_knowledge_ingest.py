"""Deterministic LLM Wiki V2 ingest pipeline for reviewed Dedao health artifacts.

The pipeline is intentionally conservative: it reads local course files only to
detect topics, then writes transformed claims. It never serves raw paid-course
body text and marks generated content as draft for human review.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any

from app.services.system_knowledge_pipeline import scan_health_sources


ARTIFACT_FILES = (
    "pages.jsonl",
    "entities.jsonl",
    "claims.jsonl",
    "protocols.jsonl",
    "contraindications.jsonl",
    "eval_cases.jsonl",
    "relations.jsonl",
)
CLAIM_BOUNDARY = "Health management guidance only; not diagnosis, prescription, or treatment."


@dataclass(frozen=True)
class ClaimTemplate:
    topic_id: str
    entity_type: str
    entity_id: str
    title: str
    summary: str
    domains: tuple[str, ...]
    keywords: tuple[str, ...]
    applies_when: tuple[str, ...]
    source_keys: tuple[str, ...] = ()
    recommends_lookup: tuple[str, ...] = ()
    evidence_level: str = "C"
    confidence: float = 0.64
    decay_rate: str = "normal"
    relation_confidence: float = 0.82
    safety_tags: tuple[str, ...] = ()
    external_sources: tuple[dict[str, str], ...] = ()


@dataclass
class IngestResult:
    source_root: Path
    base_artifact_dir: Path
    pages: list[dict[str, Any]] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    archived_claims: list[dict[str, Any]] = field(default_factory=list)
    protocols: list[dict[str, Any]] = field(default_factory=list)
    contraindications: list[dict[str, Any]] = field(default_factory=list)
    eval_cases: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    diff: dict[str, int] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)
    source_stats: list[dict[str, Any]] = field(default_factory=list)


ENTITY_CATALOG: dict[str, dict[str, Any]] = {
    "entity:condition:metabolic-health": {
        "doc_type": "entity",
        "entity_type": "condition",
        "entity_id": "metabolic-health",
        "title": "代谢健康",
        "summary": "围绕体重、腰围、血糖、血脂、血压、尿酸、脂肪肝和恢复能力的长期轨迹管理。",
        "domains": ["metabolic_health"],
    },
    "entity:condition:hypertension-risk": {
        "doc_type": "entity",
        "entity_type": "condition",
        "entity_id": "hypertension-risk",
        "title": "血压风险",
        "summary": "以家庭血压、多次测量趋势、盐摄入、体重、睡眠和运动为锚点的血压风险管理。",
        "domains": ["cardiovascular"],
    },
    "entity:condition:glycemic-risk": {
        "doc_type": "entity",
        "entity_type": "condition",
        "entity_id": "glycemic-risk",
        "title": "血糖风险",
        "summary": "以 HbA1c、空腹血糖、餐后反应、体重和运动为锚点的血糖轨迹管理。",
        "domains": ["metabolic_health"],
    },
    "entity:condition:dyslipidemia-risk": {
        "doc_type": "entity",
        "entity_type": "condition",
        "entity_id": "dyslipidemia-risk",
        "title": "血脂风险",
        "summary": "以 LDL-C、ApoB、TG 和生活方式为临床锚点的血脂轨迹管理。",
        "domains": ["metabolic_health", "cardiovascular"],
    },
    "entity:condition:hyperuricemia-risk": {
        "doc_type": "entity",
        "entity_type": "condition",
        "entity_id": "hyperuricemia-risk",
        "title": "尿酸风险",
        "summary": "围绕尿酸、饮酒、含糖饮料、体重、肾功能和痛风症状的轨迹管理。",
        "domains": ["metabolic_health"],
    },
    "entity:condition:sleep-recovery": {
        "doc_type": "entity",
        "entity_type": "condition",
        "entity_id": "sleep-recovery",
        "title": "睡眠与恢复",
        "summary": "以睡眠时长、规律性、HRV、静息心率和训练负荷为短周期反馈的恢复管理。",
        "domains": ["sleep_recovery"],
    },
    "entity:condition:microbiome-dysbiosis": {
        "doc_type": "entity",
        "entity_type": "condition",
        "entity_id": "microbiome-dysbiosis",
        "title": "菌群失衡风险",
        "summary": "用于解释饮食、睡眠、药物和肠道反应的长期风险框架，不直接推出确定性补剂处方。",
        "domains": ["microbiome", "nutrition"],
    },
    "entity:condition:medical-boundary": {
        "doc_type": "entity",
        "entity_type": "condition",
        "entity_id": "medical-boundary",
        "title": "医学边界",
        "summary": "健康管理建议必须保留诊断、治疗、处方和急症处理边界。",
        "domains": ["safety"],
    },
    "entity:condition:medication-safety": {
        "doc_type": "entity",
        "entity_type": "condition",
        "entity_id": "medication-safety",
        "title": "用药安全",
        "summary": "围绕药品、剂量、频次、禁忌、相互作用和医生/药师核对的安全边界。",
        "domains": ["medication_safety"],
    },
    "entity:intervention:weight-waist-tracking": {
        "doc_type": "entity",
        "entity_type": "intervention",
        "entity_id": "weight-waist-tracking",
        "title": "体重与腰围追踪",
        "summary": "在固定时间、固定条件下记录体重和腰围，用趋势而不是单点判断变化。",
        "domains": ["metabolic_health"],
    },
    "entity:intervention:energy-deficit": {
        "doc_type": "entity",
        "entity_type": "intervention",
        "entity_id": "energy-deficit",
        "title": "可持续能量缺口",
        "summary": "减重阶段用温和、可持续的能量缺口管理体重，同时保护蛋白、训练和恢复。",
        "domains": ["metabolic_health", "nutrition"],
    },
    "entity:intervention:protein-target": {
        "doc_type": "entity",
        "entity_type": "intervention",
        "entity_id": "protein-target",
        "title": "蛋白质目标",
        "summary": "减重阶段优先保证蛋白质摄入和力量训练，以降低瘦体重流失风险。",
        "domains": ["nutrition", "metabolic_health"],
    },
    "entity:intervention:fiber-intake": {
        "doc_type": "entity",
        "entity_type": "intervention",
        "entity_id": "fiber-intake",
        "title": "膳食纤维摄入",
        "summary": "用蔬菜、全谷物、豆类等提高膳食纤维，支持饱腹感、血糖和血脂管理。",
        "domains": ["nutrition", "metabolic_health"],
    },
    "entity:intervention:salt-reduction": {
        "doc_type": "entity",
        "entity_type": "intervention",
        "entity_id": "salt-reduction",
        "title": "减盐策略",
        "summary": "血压风险管理中优先识别高钠来源，并用可持续的饮食替换降低钠摄入。",
        "domains": ["cardiovascular", "nutrition"],
    },
    "entity:intervention:zone2-training": {
        "doc_type": "entity",
        "entity_type": "intervention",
        "entity_id": "zone2-training",
        "title": "中等强度有氧",
        "summary": "以可持续、可恢复的中等强度有氧活动支持代谢健康和心肺能力。",
        "domains": ["movement", "metabolic_health"],
    },
    "entity:intervention:strength-training": {
        "doc_type": "entity",
        "entity_type": "intervention",
        "entity_id": "strength-training",
        "title": "力量训练",
        "summary": "通过渐进式力量训练支持肌肉量、胰岛素敏感性、体重管理和长期功能能力。",
        "domains": ["movement", "metabolic_health"],
    },
    "entity:intervention:sleep-regularity": {
        "doc_type": "entity",
        "entity_type": "intervention",
        "entity_id": "sleep-regularity",
        "title": "固定睡眠窗口",
        "summary": "保持稳定入睡和起床窗口，用短周期恢复指标观察反应。",
        "domains": ["sleep_recovery"],
    },
    "entity:intervention:medication-review": {
        "doc_type": "entity",
        "entity_type": "intervention",
        "entity_id": "medication-review",
        "title": "用药核对",
        "summary": "药品记录应与补剂、食品、保健品分开，处方/非处方药需关注相互作用和医生建议。",
        "domains": ["medication_safety"],
    },
    "entity:intervention:doctor-handoff": {
        "doc_type": "entity",
        "entity_type": "intervention",
        "entity_id": "doctor-handoff",
        "title": "医生交接",
        "summary": "异常指标、红旗症状和用药问题应转化为清晰的医生沟通材料。",
        "domains": ["safety"],
    },
    "entity:intervention:microbiome-diet": {
        "doc_type": "entity",
        "entity_type": "intervention",
        "entity_id": "microbiome-diet",
        "title": "菌群友好饮食",
        "summary": "用多样化植物性食物、膳食纤维和规律作息支持肠道生态，避免确定性个性化承诺。",
        "domains": ["microbiome", "nutrition"],
    },
    "entity:biomarker:weight": {
        "doc_type": "entity",
        "entity_type": "biomarker",
        "entity_id": "weight",
        "title": "体重",
        "summary": "体重是代谢轨迹的高频趋势指标，应结合腰围、饮食、运动和睡眠解释。",
        "domains": ["metabolic_health"],
    },
    "entity:biomarker:waist": {
        "doc_type": "entity",
        "entity_type": "biomarker",
        "entity_id": "waist",
        "title": "腰围",
        "summary": "腰围是中心性脂肪和代谢风险的重要趋势指标，适合与体重共同追踪。",
        "domains": ["metabolic_health"],
    },
    "entity:biomarker:BP": {
        "doc_type": "entity",
        "entity_type": "biomarker",
        "entity_id": "BP",
        "title": "血压",
        "summary": "家庭血压和诊室血压需要区分记录，并结合趋势和就医边界解释。",
        "domains": ["cardiovascular"],
    },
    "entity:biomarker:HbA1c": {
        "doc_type": "entity",
        "entity_type": "biomarker",
        "entity_id": "HbA1c",
        "title": "HbA1c",
        "summary": "糖化血红蛋白用于反映较长周期血糖暴露，是血糖轨迹管理的临床锚点之一。",
        "domains": ["metabolic_health"],
    },
    "entity:biomarker:LDL-C": {
        "doc_type": "entity",
        "entity_type": "biomarker",
        "entity_id": "LDL-C",
        "title": "LDL-C",
        "summary": "LDL-C 是血脂和心血管风险沟通中的常用临床锚点。",
        "domains": ["cardiovascular"],
    },
    "entity:biomarker:TG": {
        "doc_type": "entity",
        "entity_type": "biomarker",
        "entity_id": "TG",
        "title": "甘油三酯",
        "summary": "TG 对饮食、酒精、体重和胰岛素抵抗较敏感，适合用于短中期代谢反馈。",
        "domains": ["metabolic_health"],
    },
    "entity:biomarker:uric-acid": {
        "doc_type": "entity",
        "entity_type": "biomarker",
        "entity_id": "uric-acid",
        "title": "尿酸",
        "summary": "尿酸需结合肾功能、痛风症状、饮食、酒精和体重变化解释。",
        "domains": ["metabolic_health"],
    },
    "entity:biomarker:eGFR": {
        "doc_type": "entity",
        "entity_type": "biomarker",
        "entity_id": "eGFR",
        "title": "eGFR",
        "summary": "eGFR 用于评估肾功能，是蛋白、尿酸、用药和补剂建议的重要安全边界。",
        "domains": ["metabolic_health", "safety"],
    },
    "entity:drug:metformin": {
        "doc_type": "entity",
        "entity_type": "drug",
        "entity_id": "metformin",
        "title": "二甲双胍",
        "summary": "常见降糖药物；系统只能做用药记录和就医沟通提示，不提供处方调整。",
        "domains": ["medication_safety", "metabolic_health"],
    },
    "entity:drug:statin": {
        "doc_type": "entity",
        "entity_type": "drug",
        "entity_id": "statin",
        "title": "他汀",
        "summary": "常见降脂药物；任何启停和剂量问题应由医生决定。",
        "domains": ["medication_safety", "cardiovascular"],
    },
    "entity:gene:MTHFR": {
        "doc_type": "entity",
        "entity_type": "gene",
        "entity_id": "MTHFR",
        "title": "MTHFR",
        "summary": "与一碳代谢和叶酸转化相关的基因；解释必须结合 Hcy、B12、叶酸和医学边界。",
        "domains": ["genetics"],
    },
    "entity:gene:APOE": {
        "doc_type": "entity",
        "entity_type": "gene",
        "entity_id": "APOE",
        "title": "APOE",
        "summary": "与脂质代谢和部分疾病风险相关；不能以基因结果直接替代临床评估。",
        "domains": ["genetics", "cardiovascular"],
    },
}

ENTITY_CATALOG.update(
    {
        "entity:condition:obesity-risk": {
            "doc_type": "entity",
            "entity_type": "condition",
            "entity_id": "obesity-risk",
            "title": "肥胖风险",
            "summary": "体重、腰围、饮食、运动、睡眠和心理压力共同塑造的代谢风险轨迹。",
            "domains": ["metabolic_health"],
        },
        "entity:condition:insulin-resistance": {
            "doc_type": "entity",
            "entity_type": "condition",
            "entity_id": "insulin-resistance",
            "title": "胰岛素抵抗风险",
            "summary": "解释血糖、腰围、TG、脂肪肝和运动反应时常用的代谢风险框架。",
            "domains": ["metabolic_health"],
        },
        "entity:condition:fatty-liver-risk": {
            "doc_type": "entity",
            "entity_type": "condition",
            "entity_id": "fatty-liver-risk",
            "title": "脂肪肝风险",
            "summary": "与体重、腰围、TG、ALT/GGT、饮酒和胰岛素抵抗相关的长期风险轨迹。",
            "domains": ["metabolic_health"],
        },
        "entity:condition:gout-risk": {
            "doc_type": "entity",
            "entity_type": "condition",
            "entity_id": "gout-risk",
            "title": "痛风风险",
            "summary": "尿酸、饮酒、含糖饮料、体重、肾功能和关节症状共同决定的风险沟通框架。",
            "domains": ["metabolic_health"],
        },
        "entity:condition:cardiovascular-risk": {
            "doc_type": "entity",
            "entity_type": "condition",
            "entity_id": "cardiovascular-risk",
            "title": "心血管风险",
            "summary": "整合血压、血脂、血糖、家族史、睡眠和运动表现的长期风险框架。",
            "domains": ["cardiovascular"],
        },
        "entity:condition:sleep-apnea-risk": {
            "doc_type": "entity",
            "entity_type": "condition",
            "entity_id": "sleep-apnea-risk",
            "title": "睡眠呼吸风险",
            "summary": "夜间低氧、打鼾、日间嗜睡、体重和血压共同提示的医生沟通线索。",
            "domains": ["sleep_recovery", "safety"],
        },
        "entity:condition:sarcopenia-risk": {
            "doc_type": "entity",
            "entity_type": "condition",
            "entity_id": "sarcopenia-risk",
            "title": "肌少风险",
            "summary": "减重、年龄、蛋白摄入、力量训练和肌肉量共同影响的功能能力风险。",
            "domains": ["movement", "metabolic_health"],
        },
        "entity:condition:stress-load": {
            "doc_type": "entity",
            "entity_type": "condition",
            "entity_id": "stress-load",
            "title": "压力负荷",
            "summary": "压力、情绪、睡眠、HRV 和饮食执行力共同构成的短中期恢复负荷。",
            "domains": ["mental_health", "sleep_recovery"],
        },
        "entity:condition:brain-health": {
            "doc_type": "entity",
            "entity_type": "condition",
            "entity_id": "brain-health",
            "title": "大脑健康",
            "summary": "睡眠、运动、血压、血糖、情绪和认知表现共同影响的大脑健康轨迹。",
            "domains": ["longevity", "mental_health"],
        },
        "entity:condition:orthopedic-function": {
            "doc_type": "entity",
            "entity_type": "condition",
            "entity_id": "orthopedic-function",
            "title": "骨骼肌肉功能",
            "summary": "力量、活动能力、疼痛、体重和训练负荷共同影响的功能能力轨迹。",
            "domains": ["movement"],
        },
        "entity:condition:chronic-kidney-risk": {
            "doc_type": "entity",
            "entity_type": "condition",
            "entity_id": "chronic-kidney-risk",
            "title": "肾功能风险",
            "summary": "尿酸、肌酐、eGFR、血压、用药和蛋白/补剂建议都需要共同参考的安全边界。",
            "domains": ["metabolic_health", "safety"],
        },
        "entity:condition:kidney-stone-risk": {
            "doc_type": "entity",
            "entity_type": "condition",
            "entity_id": "kidney-stone-risk",
            "title": "肾结石风险",
            "summary": "结石史、尿酸、饮水、饮食、尿路症状和影像变化共同决定的医生沟通线索。",
            "domains": ["metabolic_health", "safety"],
        },
        "entity:condition:liver-function-risk": {
            "doc_type": "entity",
            "entity_type": "condition",
            "entity_id": "liver-function-risk",
            "title": "肝功能风险",
            "summary": "ALT、GGT、TG、饮酒、体重和脂肪肝共同塑造的肝代谢风险轨迹。",
            "domains": ["metabolic_health", "safety"],
        },
        "entity:intervention:meal-timing": {
            "doc_type": "entity",
            "entity_type": "intervention",
            "entity_id": "meal-timing",
            "title": "进食时间管理",
            "summary": "用规律进食、晚餐时间和睡眠窗口协调血糖、体重和恢复。",
            "domains": ["nutrition", "sleep_recovery"],
        },
        "entity:intervention:post-meal-walk": {
            "doc_type": "entity",
            "entity_type": "intervention",
            "entity_id": "post-meal-walk",
            "title": "餐后步行",
            "summary": "餐后低强度活动可作为血糖和消化反馈的低门槛行动。",
            "domains": ["movement", "metabolic_health"],
        },
        "entity:intervention:alcohol-reduction": {
            "doc_type": "entity",
            "entity_type": "intervention",
            "entity_id": "alcohol-reduction",
            "title": "减少酒精",
            "summary": "酒精摄入需结合血脂、尿酸、睡眠、肝功能和基因代谢风险解释。",
            "domains": ["nutrition", "metabolic_health"],
        },
        "entity:intervention:sugar-drink-reduction": {
            "doc_type": "entity",
            "entity_type": "intervention",
            "entity_id": "sugar-drink-reduction",
            "title": "减少含糖饮料",
            "summary": "含糖饮料是血糖、尿酸和体重管理中优先排查的可干预变量。",
            "domains": ["nutrition", "metabolic_health"],
        },
        "entity:intervention:purine-management": {
            "doc_type": "entity",
            "entity_type": "intervention",
            "entity_id": "purine-management",
            "title": "嘌呤和尿酸饮食管理",
            "summary": "尿酸风险管理中应关注酒精、含糖饮料、总能量、体重和部分高嘌呤食物。",
            "domains": ["nutrition", "metabolic_health"],
        },
        "entity:intervention:home-bp-monitoring": {
            "doc_type": "entity",
            "entity_type": "intervention",
            "entity_id": "home-bp-monitoring",
            "title": "家庭血压监测",
            "summary": "用规范家庭血压记录降低单次测量噪声，辅助医生沟通。",
            "domains": ["cardiovascular"],
        },
        "entity:intervention:lab-recheck": {
            "doc_type": "entity",
            "entity_type": "intervention",
            "entity_id": "lab-recheck",
            "title": "复查闭环",
            "summary": "把生活方式行动和 8-12 周或医生建议周期的复查结果连接起来。",
            "domains": ["metabolic_health", "safety"],
        },
        "entity:intervention:pharmacist-review": {
            "doc_type": "entity",
            "entity_type": "intervention",
            "entity_id": "pharmacist-review",
            "title": "药师核对",
            "summary": "新增药品、联合用药、补剂和不良反应问题应优先由医生或药师核对。",
            "domains": ["medication_safety"],
        },
        "entity:intervention:stress-management": {
            "doc_type": "entity",
            "entity_type": "intervention",
            "entity_id": "stress-management",
            "title": "压力管理",
            "summary": "通过睡眠窗口、运动降载、正念和任务边界降低长期压力负荷。",
            "domains": ["mental_health", "sleep_recovery"],
        },
        "entity:intervention:mindfulness": {
            "doc_type": "entity",
            "entity_type": "intervention",
            "entity_id": "mindfulness",
            "title": "正念练习",
            "summary": "作为压力和睡眠管理的辅助行为工具，不替代心理或医学诊疗。",
            "domains": ["mental_health"],
        },
        "entity:intervention:light-exposure": {
            "doc_type": "entity",
            "entity_type": "intervention",
            "entity_id": "light-exposure",
            "title": "晨间光照",
            "summary": "晨间光照和固定起床时间可用于支持昼夜节律和睡眠规律。",
            "domains": ["sleep_recovery"],
        },
        "entity:intervention:bedtime-routine": {
            "doc_type": "entity",
            "entity_type": "intervention",
            "entity_id": "bedtime-routine",
            "title": "睡前流程",
            "summary": "用稳定睡前流程降低入睡摩擦，帮助恢复指标形成可解释反馈。",
            "domains": ["sleep_recovery"],
        },
        "entity:intervention:mobility-training": {
            "doc_type": "entity",
            "entity_type": "intervention",
            "entity_id": "mobility-training",
            "title": "灵活性与活动能力训练",
            "summary": "结合力量和低强度活动支持关节、疼痛和长期功能能力。",
            "domains": ["movement"],
        },
        "entity:intervention:hydration": {
            "doc_type": "entity",
            "entity_type": "intervention",
            "entity_id": "hydration",
            "title": "补水策略",
            "summary": "补水建议应结合运动、天气、肾功能、尿酸和结石史，避免用单一饮水目标解释所有情况。",
            "domains": ["metabolic_health", "movement"],
        },
        "entity:intervention:nutrition-label-reading": {
            "doc_type": "entity",
            "entity_type": "intervention",
            "entity_id": "nutrition-label-reading",
            "title": "营养标签识别",
            "summary": "识别钠、添加糖、能量密度、蛋白和膳食纤维，是外卖和包装食品选择的低摩擦入口。",
            "domains": ["nutrition", "metabolic_health"],
        },
        "entity:intervention:recovery-deload": {
            "doc_type": "entity",
            "entity_type": "intervention",
            "entity_id": "recovery-deload",
            "title": "恢复降载",
            "summary": "当睡眠、HRV、静息心率或主观疲劳提示恢复不足时，训练建议应先降低强度或缩短时长。",
            "domains": ["sleep_recovery", "movement"],
        },
        "entity:intervention:doctor-red-flag-triage": {
            "doc_type": "entity",
            "entity_type": "intervention",
            "entity_id": "doctor-red-flag-triage",
            "title": "红旗转诊",
            "summary": "胸痛、晕厥、突发神经症状、严重低氧、严重血压或检验异常应触发就医而不是生活方式建议。",
            "domains": ["safety"],
        },
        "entity:biomarker:BMI": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "BMI",
            "title": "BMI",
            "summary": "BMI 可作为人群层面的体重指标，个体解释需结合腰围和体成分。",
            "domains": ["metabolic_health"],
        },
        "entity:biomarker:waist-height-ratio": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "waist-height-ratio",
            "title": "腰高比",
            "summary": "腰高比可辅助解释中心性脂肪和代谢风险趋势。",
            "domains": ["metabolic_health"],
        },
        "entity:biomarker:ApoB": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "ApoB",
            "title": "ApoB",
            "summary": "ApoB 是血脂风险沟通中的重要颗粒数锚点。",
            "domains": ["cardiovascular"],
        },
        "entity:biomarker:HDL-C": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "HDL-C",
            "title": "HDL-C",
            "summary": "HDL-C 需要放在总体血脂、TG、运动、饮酒和心血管风险框架中解释。",
            "domains": ["cardiovascular", "metabolic_health"],
        },
        "entity:biomarker:fasting-glucose": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "fasting-glucose",
            "title": "空腹血糖",
            "summary": "空腹血糖应结合 HbA1c、餐后反应和生活方式趋势解释。",
            "domains": ["metabolic_health"],
        },
        "entity:biomarker:postprandial-glucose": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "postprandial-glucose",
            "title": "餐后血糖",
            "summary": "餐后血糖受碳水质量、运动、睡眠和压力影响，适合做行为反馈。",
            "domains": ["metabolic_health"],
        },
        "entity:biomarker:fasting-insulin": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "fasting-insulin",
            "title": "空腹胰岛素",
            "summary": "空腹胰岛素可作为胰岛素抵抗风险沟通线索，需结合医生解释。",
            "domains": ["metabolic_health"],
        },
        "entity:biomarker:ALT": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "ALT",
            "title": "ALT",
            "summary": "ALT 可作为肝功能和脂肪肝风险沟通中的指标之一。",
            "domains": ["metabolic_health", "safety"],
        },
        "entity:biomarker:GGT": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "GGT",
            "title": "GGT",
            "summary": "GGT 常与酒精、肝胆代谢和脂肪肝风险沟通相关。",
            "domains": ["metabolic_health", "safety"],
        },
        "entity:biomarker:hsCRP": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "hsCRP",
            "title": "hsCRP",
            "summary": "hsCRP 可作为炎症负荷线索，需要结合感染、运动和医生评估解释。",
            "domains": ["cardiovascular", "safety"],
        },
        "entity:biomarker:SpO2": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "SpO2",
            "title": "血氧",
            "summary": "夜间血氧异常需要结合症状、设备可靠性和医生评估。",
            "domains": ["sleep_recovery", "safety"],
        },
        "entity:biomarker:HRV": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "HRV",
            "title": "HRV",
            "summary": "HRV 适合看个体基线和趋势，不适合跨设备绝对值比较。",
            "domains": ["sleep_recovery", "movement"],
        },
        "entity:biomarker:resting-hr": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "resting-hr",
            "title": "静息心率",
            "summary": "静息心率可反映恢复、压力、训练负荷和心肺状态变化。",
            "domains": ["sleep_recovery", "cardiovascular"],
        },
        "entity:biomarker:sleep-duration": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "sleep-duration",
            "title": "睡眠时长",
            "summary": "睡眠时长需要和规律性、主观精力、HRV 与训练负荷一起解释。",
            "domains": ["sleep_recovery"],
        },
        "entity:biomarker:VO2max": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "VO2max",
            "title": "VO2max",
            "summary": "VO2max 是心肺能力的趋势指标，需结合设备估算误差和训练背景解释。",
            "domains": ["movement", "cardiovascular"],
        },
        "entity:biomarker:muscle-mass": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "muscle-mass",
            "title": "肌肉量",
            "summary": "肌肉量趋势适合与蛋白摄入、力量训练和体重变化一起解释。",
            "domains": ["movement", "metabolic_health"],
        },
        "entity:biomarker:creatinine": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "creatinine",
            "title": "肌酐",
            "summary": "肌酐和 eGFR 是肾功能、蛋白、尿酸、药品和补剂建议的重要边界。",
            "domains": ["metabolic_health", "safety"],
        },
        "entity:biomarker:vitamin-b12": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "vitamin-b12",
            "title": "维生素 B12",
            "summary": "B12 状态是解释 Hcy、叶酸补充和 MTHFR 相关建议时必须核对的安全边界。",
            "domains": ["nutrition", "genetics", "safety"],
        },
        "entity:biomarker:folate": {
            "doc_type": "entity",
            "entity_type": "biomarker",
            "entity_id": "folate",
            "title": "叶酸状态",
            "summary": "叶酸状态需要和 Hcy、B12、饮食、补剂剂量以及医生建议一起解释。",
            "domains": ["nutrition", "genetics"],
        },
        "entity:gene:ALDH2": {
            "doc_type": "entity",
            "entity_type": "gene",
            "entity_id": "ALDH2",
            "title": "ALDH2",
            "summary": "乙醛代谢相关基因，饮酒建议需要保持风险沟通边界。",
            "domains": ["genetics", "metabolic_health"],
        },
        "entity:gene:FTO": {
            "doc_type": "entity",
            "entity_type": "gene",
            "entity_id": "FTO",
            "title": "FTO",
            "summary": "体重倾向相关基因，只能作为行为管理线索，不能决定个体结果。",
            "domains": ["genetics", "metabolic_health"],
        },
        "entity:gene:ACTN3": {
            "doc_type": "entity",
            "entity_type": "gene",
            "entity_id": "ACTN3",
            "title": "ACTN3",
            "summary": "运动表现相关基因，不能替代训练反馈和恢复数据。",
            "domains": ["genetics", "movement"],
        },
        "entity:gene:CYP2D6": {
            "doc_type": "entity",
            "entity_type": "gene",
            "entity_id": "CYP2D6",
            "title": "CYP2D6",
            "summary": "药物代谢相关基因，结果应交给医生或药师用于用药核对。",
            "domains": ["genetics", "medication_safety"],
        },
        "entity:gene:CYP2C19": {
            "doc_type": "entity",
            "entity_type": "gene",
            "entity_id": "CYP2C19",
            "title": "CYP2C19",
            "summary": "药物代谢相关基因，不能直接推出个人启停药或剂量调整。",
            "domains": ["genetics", "medication_safety"],
        },
        "entity:drug:antihypertensive": {
            "doc_type": "entity",
            "entity_type": "drug",
            "entity_id": "antihypertensive",
            "title": "降压药",
            "summary": "降压药相关内容仅用于记录和医生沟通，不提供处方调整。",
            "domains": ["medication_safety", "cardiovascular"],
        },
        "entity:drug:urate-lowering-drug": {
            "doc_type": "entity",
            "entity_type": "drug",
            "entity_id": "urate-lowering-drug",
            "title": "降尿酸药",
            "summary": "降尿酸药相关内容仅用于记录和医生沟通，不提供处方调整。",
            "domains": ["medication_safety", "metabolic_health"],
        },
        "entity:drug:nsaid": {
            "doc_type": "entity",
            "entity_type": "drug",
            "entity_id": "nsaid",
            "title": "NSAID 止痛药",
            "summary": "止痛药需要结合胃肠、肾功能、心血管和联合用药风险进行专业核对。",
            "domains": ["medication_safety"],
        },
        "entity:supplement:omega-3": {
            "doc_type": "entity",
            "entity_type": "supplement",
            "entity_id": "omega-3",
            "title": "Omega-3",
            "summary": "Omega-3 只适合作为证据分级后的营养干预线索，不能替代药物或医生建议。",
            "domains": ["nutrition", "cardiovascular"],
        },
        "entity:supplement:vitamin-d": {
            "doc_type": "entity",
            "entity_type": "supplement",
            "entity_id": "vitamin-d",
            "title": "维生素 D",
            "summary": "维生素 D 建议应结合检测结果、剂量边界和医生建议。",
            "domains": ["nutrition", "safety"],
        },
        "entity:supplement:magnesium": {
            "doc_type": "entity",
            "entity_type": "supplement",
            "entity_id": "magnesium",
            "title": "镁",
            "summary": "镁补充需要结合睡眠、运动恢复、肾功能和剂量边界解释。",
            "domains": ["nutrition", "sleep_recovery"],
        },
        "entity:supplement:5-MTHF": {
            "doc_type": "entity",
            "entity_type": "supplement",
            "entity_id": "5-MTHF",
            "title": "5-MTHF",
            "summary": "活性叶酸相关建议必须结合 Hcy、B12、叶酸状态、剂量边界和医生建议。",
            "domains": ["nutrition", "genetics", "safety"],
        },
    }
)

TEMPLATE_RELATED_ENTITIES: dict[str, tuple[str, ...]] = {
    "weight_waist_tracking": (
        "entity:condition:obesity-risk",
        "entity:biomarker:BMI",
        "entity:biomarker:waist-height-ratio",
    ),
    "energy_deficit": (
        "entity:condition:obesity-risk",
        "entity:intervention:meal-timing",
        "entity:condition:stress-load",
    ),
    "protein_target": (
        "entity:condition:sarcopenia-risk",
        "entity:biomarker:muscle-mass",
        "entity:biomarker:creatinine",
        "entity:condition:chronic-kidney-risk",
    ),
    "fiber_intake": (
        "entity:condition:insulin-resistance",
        "entity:intervention:sugar-drink-reduction",
        "entity:biomarker:postprandial-glucose",
        "entity:intervention:nutrition-label-reading",
    ),
    "bp_home_monitoring": (
        "entity:intervention:home-bp-monitoring",
        "entity:condition:cardiovascular-risk",
        "entity:drug:antihypertensive",
    ),
    "salt_reduction": (
        "entity:intervention:home-bp-monitoring",
        "entity:condition:cardiovascular-risk",
        "entity:drug:antihypertensive",
        "entity:intervention:nutrition-label-reading",
    ),
    "hba1c_feedback": (
        "entity:biomarker:fasting-glucose",
        "entity:biomarker:postprandial-glucose",
        "entity:condition:insulin-resistance",
        "entity:intervention:lab-recheck",
    ),
    "diabetes_recheck_8_12_weeks": (
        "entity:biomarker:fasting-glucose",
        "entity:biomarker:fasting-insulin",
        "entity:intervention:post-meal-walk",
        "entity:intervention:lab-recheck",
    ),
    "post_meal_glucose": (
        "entity:biomarker:postprandial-glucose",
        "entity:intervention:post-meal-walk",
        "entity:intervention:meal-timing",
    ),
    "ldl_apob_anchor": (
        "entity:biomarker:ApoB",
        "entity:biomarker:HDL-C",
        "entity:condition:cardiovascular-risk",
        "entity:supplement:omega-3",
    ),
    "triglyceride_carbs_alcohol": (
        "entity:intervention:alcohol-reduction",
        "entity:intervention:sugar-drink-reduction",
        "entity:condition:fatty-liver-risk",
        "entity:condition:liver-function-risk",
        "entity:biomarker:HDL-C",
    ),
    "uric_acid_context": (
        "entity:condition:gout-risk",
        "entity:condition:kidney-stone-risk",
        "entity:condition:chronic-kidney-risk",
        "entity:intervention:alcohol-reduction",
        "entity:intervention:sugar-drink-reduction",
        "entity:intervention:purine-management",
        "entity:intervention:hydration",
        "entity:drug:urate-lowering-drug",
    ),
    "zone2_recovery_constraint": (
        "entity:biomarker:HRV",
        "entity:biomarker:resting-hr",
        "entity:biomarker:VO2max",
        "entity:intervention:recovery-deload",
    ),
    "strength_training": (
        "entity:condition:sarcopenia-risk",
        "entity:biomarker:muscle-mass",
        "entity:condition:orthopedic-function",
        "entity:intervention:mobility-training",
    ),
    "sleep_regular_window": (
        "entity:biomarker:sleep-duration",
        "entity:biomarker:HRV",
        "entity:biomarker:SpO2",
        "entity:condition:sleep-apnea-risk",
        "entity:intervention:light-exposure",
        "entity:intervention:bedtime-routine",
    ),
    "drug_records_exclude_non_drugs": (
        "entity:intervention:pharmacist-review",
        "entity:drug:nsaid",
        "entity:supplement:vitamin-d",
        "entity:supplement:magnesium",
    ),
    "drug_interaction_review": (
        "entity:intervention:pharmacist-review",
        "entity:drug:nsaid",
        "entity:drug:antihypertensive",
    ),
    "metformin_medication_boundary": (
        "entity:biomarker:fasting-glucose",
        "entity:condition:insulin-resistance",
        "entity:intervention:lab-recheck",
    ),
    "statin_medication_boundary": (
        "entity:biomarker:ApoB",
        "entity:condition:cardiovascular-risk",
        "entity:intervention:lab-recheck",
    ),
    "medical_boundary": (
        "entity:intervention:lab-recheck",
        "entity:intervention:doctor-red-flag-triage",
        "entity:condition:cardiovascular-risk",
        "entity:condition:sleep-apnea-risk",
    ),
    "microbiome_behavior_boundary": (
        "entity:intervention:stress-management",
        "entity:intervention:meal-timing",
        "entity:supplement:omega-3",
    ),
    "mthfr_boundary": (
        "entity:supplement:5-MTHF",
        "entity:biomarker:vitamin-b12",
        "entity:biomarker:folate",
        "entity:supplement:vitamin-d",
        "entity:supplement:magnesium",
        "entity:gene:ALDH2",
    ),
    "apoe_lipid_boundary": (
        "entity:biomarker:ApoB",
        "entity:condition:cardiovascular-risk",
        "entity:supplement:omega-3",
    ),
    "gene_pharmacogenomics_boundary": (
        "entity:gene:CYP2D6",
        "entity:gene:CYP2C19",
        "entity:drug:nsaid",
        "entity:intervention:pharmacist-review",
    ),
}


CLAIM_TEMPLATES: tuple[ClaimTemplate, ...] = (
    ClaimTemplate(
        topic_id="weight_waist_tracking",
        entity_type="intervention",
        entity_id="weight-waist-tracking",
        title="晨起体重和腰围用于代谢轨迹反馈",
        summary="体重或代谢风险管理中，应在固定时间、固定条件下记录体重和腰围，用 7 天以上趋势判断变化，避免被单日波动误导。",
        domains=("metabolic_health",),
        keywords=("体重", "腰围", "效果评价", "家庭健康管理", "减肥"),
        applies_when=("twin.goals.weight_loss.active == true", "twin.goals.metabolic_health.active == true"),
        recommends_lookup=("entity:biomarker:weight", "entity:biomarker:waist"),
        evidence_level="B",
        confidence=0.78,
    ),
    ClaimTemplate(
        topic_id="energy_deficit",
        entity_type="intervention",
        entity_id="energy-deficit",
        title="减重行动应采用可持续能量缺口",
        summary="减重阶段应建立可持续能量缺口，并同时关注蛋白、运动、睡眠和心理能量，避免极端节食造成反弹或恢复下降。",
        domains=("metabolic_health", "nutrition"),
        keywords=("能量缺口", "守恒", "科学减肥", "轻断食", "饮食选择"),
        applies_when=("twin.goals.weight_loss.active == true",),
        recommends_lookup=("entity:intervention:energy-deficit", "entity:intervention:protein-target"),
        evidence_level="B",
        confidence=0.76,
    ),
    ClaimTemplate(
        topic_id="protein_target",
        entity_type="intervention",
        entity_id="protein-target",
        title="减重阶段优先保护蛋白和肌肉量",
        summary="减重阶段不应只追求热量缺口，还要保证蛋白质摄入和力量训练，以降低瘦体重流失和恢复变差的风险。",
        domains=("nutrition", "metabolic_health"),
        keywords=("蛋白", "肌肉", "瘦体重", "力量", "蛋白质"),
        applies_when=("twin.goals.weight_loss.active == true", "twin.labs.eGFR >= 60"),
        recommends_lookup=("entity:intervention:protein-target", "entity:biomarker:eGFR"),
        evidence_level="B",
        confidence=0.76,
        safety_tags=("kidney_function_check",),
    ),
    ClaimTemplate(
        topic_id="fiber_intake",
        entity_type="intervention",
        entity_id="fiber-intake",
        title="膳食纤维支持血糖和血脂管理",
        summary="提高来自蔬菜、豆类、全谷物等食物的膳食纤维，有助于饱腹感和代谢指标管理，但应循序渐进以减少胃肠不适。",
        domains=("nutrition", "metabolic_health"),
        keywords=("膳食纤维", "纤维", "蔬菜", "全谷", "豆类", "饱腹"),
        applies_when=("twin.goals.metabolic_health.active == true", "twin.labs.hba1c_percent >= 5.7"),
        recommends_lookup=("entity:intervention:fiber-intake", "entity:biomarker:HbA1c", "entity:biomarker:LDL-C"),
        evidence_level="B",
        confidence=0.75,
    ),
    ClaimTemplate(
        topic_id="bp_home_monitoring",
        entity_type="condition",
        entity_id="hypertension-risk",
        title="血压建议优先基于家庭血压趋势",
        summary="血压风险沟通应优先看家庭血压和多次测量趋势；单次偏高不应直接推导为诊断或用药建议。",
        domains=("cardiovascular",),
        keywords=("家庭血压", "血压", "诊断高血压", "分级", "延缓"),
        applies_when=("twin.labs.systolic_bp >= 130", "twin.labs.diastolic_bp >= 80"),
        recommends_lookup=("entity:biomarker:BP", "entity:condition:hypertension-risk"),
        evidence_level="B",
        confidence=0.76,
        decay_rate="slow",
        safety_tags=("doctor_if_severe_bp",),
    ),
    ClaimTemplate(
        topic_id="salt_reduction",
        entity_type="intervention",
        entity_id="salt-reduction",
        title="血压风险管理先识别高钠来源",
        summary="血压偏高或有血压风险时，应优先识别外卖、加工食品、酱料等高钠来源，再做可持续替换。",
        domains=("cardiovascular", "nutrition"),
        keywords=("盐", "钠", "降血压", "饮食", "高钠"),
        applies_when=("twin.labs.systolic_bp >= 130", "twin.goals.metabolic_health.active == true"),
        recommends_lookup=("entity:intervention:salt-reduction", "entity:biomarker:BP"),
        evidence_level="B",
        confidence=0.74,
    ),
    ClaimTemplate(
        topic_id="hba1c_feedback",
        entity_type="biomarker",
        entity_id="HbA1c",
        title="HbA1c 适合作为 8-12 周复查闭环",
        summary="HbA1c 更适合做中周期血糖反馈，日常行动应结合饮食、运动、睡眠和体重趋势，8-12 周后复查更有解释价值。",
        domains=("metabolic_health",),
        keywords=("HbA1c", "糖化", "血糖", "高血糖", "糖尿病", "病程管理", "复查"),
        applies_when=("twin.labs.hba1c_percent >= 5.7", "twin.labs.fasting_glucose_mmol_l >= 5.6"),
        recommends_lookup=("entity:biomarker:HbA1c", "entity:condition:glycemic-risk"),
        evidence_level="B",
        confidence=0.76,
        decay_rate="slow",
    ),
    ClaimTemplate(
        topic_id="diabetes_recheck_8_12_weeks",
        entity_type="condition",
        entity_id="glycemic-risk",
        title="血糖风险干预需要 8-12 周复查闭环",
        summary="血糖风险管理应把饮食、运动、睡眠和体重行动放入 8-12 周复查闭环；HbA1c 和空腹血糖用于评估趋势，不用于单次自我诊断。",
        domains=("metabolic_health",),
        keywords=("糖尿病", "血糖", "HbA1c", "糖化血红蛋白", "复查", "8-12"),
        applies_when=("twin.labs.hba1c_percent >= 5.7", "twin.labs.fasting_glucose_mmol_l >= 5.6"),
        source_keys=("dedao:busy-diabetes", "dedao:fengxue-gaoxuetang-yixueke"),
        recommends_lookup=("entity:condition:glycemic-risk", "entity:biomarker:HbA1c"),
        evidence_level="B",
        confidence=0.76,
        decay_rate="slow",
        safety_tags=("recheck_loop", "medical_boundary"),
        external_sources=(
            {
                "source": "guideline:ada-standards-of-care-diabetes-2026",
                "kind": "guideline",
                "review_status": "reviewed",
                "note": "HbA1c and fasting glucose fit medium-cycle glycemic follow-up, not single-point self-diagnosis.",
            },
        ),
    ),
    ClaimTemplate(
        topic_id="post_meal_glucose",
        entity_type="condition",
        entity_id="glycemic-risk",
        title="餐后血糖反应应结合饮食结构和活动解释",
        summary="餐后血糖波动应结合碳水质量、纤维、蛋白、餐后活动、睡眠和体重解释，不应只看单餐峰值做长期判断。",
        domains=("metabolic_health", "nutrition"),
        keywords=("餐后", "血糖波动", "碳水", "营养处方", "运动处方"),
        applies_when=("twin.labs.fasting_glucose_mmol_l >= 5.6", "twin.goals.metabolic_health.active == true"),
        recommends_lookup=("entity:condition:glycemic-risk", "entity:intervention:fiber-intake"),
        evidence_level="B",
        confidence=0.72,
    ),
    ClaimTemplate(
        topic_id="ldl_apob_anchor",
        entity_type="condition",
        entity_id="dyslipidemia-risk",
        title="血脂风险以 LDL-C/ApoB 轨迹为锚点",
        summary="血脂风险沟通应以 LDL-C、ApoB 和 TG 等指标趋势为锚点，饮食建议不能替代医生对高风险人群的评估。",
        domains=("cardiovascular", "metabolic_health"),
        keywords=("LDL", "ApoB", "胆固醇", "高血脂", "降脂", "心梗", "脂质"),
        applies_when=("twin.labs.ldl_c_mmol_l >= 3.4", "twin.labs.apob_g_l >= 1.0"),
        recommends_lookup=("entity:biomarker:LDL-C", "entity:condition:dyslipidemia-risk"),
        evidence_level="B",
        confidence=0.77,
        decay_rate="slow",
        safety_tags=("doctor_if_high_risk_lipids",),
    ),
    ClaimTemplate(
        topic_id="triglyceride_carbs_alcohol",
        entity_type="biomarker",
        entity_id="TG",
        title="TG 升高时优先核对酒精和精制碳水",
        summary="甘油三酯升高时，应优先核对饮酒、含糖饮料、精制碳水和体重变化，再制定饮食与运动闭环。",
        domains=("metabolic_health", "nutrition"),
        keywords=("甘油三酯", "TG", "酒", "含糖", "精制碳水"),
        applies_when=("twin.labs.triglycerides_mmol_l >= 1.7",),
        recommends_lookup=("entity:biomarker:TG", "entity:intervention:fiber-intake"),
        evidence_level="B",
        confidence=0.73,
    ),
    ClaimTemplate(
        topic_id="uric_acid_context",
        entity_type="condition",
        entity_id="hyperuricemia-risk",
        title="尿酸偏高需结合酒精、含糖饮料、体重和肾功能",
        summary="尿酸偏高时，生活方式建议应优先核对饮酒、含糖饮料、体重变化、肾功能和痛风症状；严重异常或症状应就医。",
        domains=("metabolic_health",),
        keywords=("尿酸", "痛风", "嘌呤", "降尿酸", "高尿酸"),
        applies_when=("twin.labs.uric_acid_umol_l >= 420",),
        recommends_lookup=("entity:biomarker:uric-acid", "entity:biomarker:eGFR"),
        evidence_level="C",
        confidence=0.68,
        safety_tags=("doctor_if_gout_symptoms",),
    ),
    ClaimTemplate(
        topic_id="zone2_recovery_constraint",
        entity_type="intervention",
        entity_id="zone2-training",
        title="中等强度有氧是代谢基础但需受恢复状态约束",
        summary="代谢健康目标下，中等强度有氧可作为基础活动；若睡眠不足、HRV 低或近期负荷过高，应先降低强度。",
        domains=("movement", "metabolic_health", "sleep_recovery"),
        keywords=("燃脂运动", "运动处方", "中等强度", "有氧", "恢复", "睡眠不足"),
        applies_when=("twin.goals.metabolic_health.active == true", "twin.wearable.sleep_duration_hours < 6.5"),
        recommends_lookup=("entity:intervention:zone2-training", "entity:condition:sleep-recovery"),
        evidence_level="B",
        confidence=0.73,
        safety_tags=("recovery_constraint",),
    ),
    ClaimTemplate(
        topic_id="strength_training",
        entity_type="intervention",
        entity_id="strength-training",
        title="减重阶段需要力量训练保护功能能力",
        summary="减重阶段应保留渐进式力量训练，用于保护肌肉量、功能能力和长期代谢基础，但需按恢复状态调整负荷。",
        domains=("movement", "metabolic_health"),
        keywords=("力量", "肌肉", "运动", "训练", "功能能力"),
        applies_when=("twin.goals.weight_loss.active == true",),
        recommends_lookup=("entity:intervention:strength-training",),
        evidence_level="B",
        confidence=0.74,
    ),
    ClaimTemplate(
        topic_id="sleep_regular_window",
        entity_type="intervention",
        entity_id="sleep-regularity",
        title="恢复不足时优先固定睡眠窗口",
        summary="当睡眠不足或恢复指标偏低时，优先固定睡眠窗口、降低晚间刺激和训练强度，再推动更高负荷计划。",
        domains=("sleep_recovery",),
        keywords=("睡眠", "卧室环境", "咖啡", "午觉", "微习惯", "睡眠效率", "睡眠时长"),
        applies_when=("twin.wearable.sleep_duration_hours < 7", "twin.goals.sleep.active == true"),
        recommends_lookup=("entity:intervention:sleep-regularity", "entity:condition:sleep-recovery"),
        evidence_level="B",
        confidence=0.72,
    ),
    ClaimTemplate(
        topic_id="drug_records_exclude_non_drugs",
        entity_type="intervention",
        entity_id="medication-review",
        title="药品记录应排除非药品",
        summary="用药状态只应记录处方药和非处方药；维生素、矿物质、蛋白粉、食品和普通补剂应进入补剂或饮食记录，避免用药提醒混乱。",
        domains=("medication_safety",),
        keywords=("日常用药", "药物", "药品", "处方", "用药", "保健品"),
        applies_when=("twin.medications.0.name is not null", "twin.supplements.0.name is not null"),
        recommends_lookup=("entity:intervention:medication-review",),
        evidence_level="C",
        confidence=0.70,
        safety_tags=("interaction_check",),
    ),
    ClaimTemplate(
        topic_id="drug_interaction_review",
        entity_type="intervention",
        entity_id="medication-review",
        title="新增药品前应核对药物相互作用",
        summary="新增处方药或非处方药前，应与现有药品、补剂、饮酒和基础疾病一起做相互作用核对；系统只提供核对清单，不替代医生或药师判断。",
        domains=("medication_safety",),
        keywords=("相互作用", "用药", "药品", "处方", "非处方", "药师"),
        applies_when=("twin.medications.0.name is not null",),
        source_keys=("dedao:wangjiawei-medication-safety",),
        recommends_lookup=("entity:intervention:medication-review", "entity:intervention:doctor-handoff"),
        evidence_level="B",
        confidence=0.74,
        safety_tags=("interaction_check", "doctor_or_pharmacist_review"),
    ),
    ClaimTemplate(
        topic_id="metformin_medication_boundary",
        entity_type="drug",
        entity_id="metformin",
        title="二甲双胍相关建议必须停留在记录和医生沟通",
        summary="涉及二甲双胍等降糖药时，系统只应帮助记录、提醒复查和整理问题，不能建议启停药或调整剂量。",
        domains=("medication_safety", "metabolic_health"),
        keywords=("二甲双胍", "降糖药", "药物处方", "糖尿病"),
        applies_when=("twin.medications.0.name is not null",),
        recommends_lookup=("entity:drug:metformin", "entity:intervention:doctor-handoff"),
        evidence_level="B",
        confidence=0.72,
        safety_tags=("no_medication_adjustment",),
    ),
    ClaimTemplate(
        topic_id="statin_medication_boundary",
        entity_type="drug",
        entity_id="statin",
        title="他汀类药物建议必须保留医生决策边界",
        summary="涉及他汀类药物时，系统可以帮助整理 LDL-C/ApoB 趋势、肌肉症状和复查问题，但不能替代医生做启停或剂量决定。",
        domains=("medication_safety", "cardiovascular"),
        keywords=("他汀", "降脂药", "药物治疗", "高血脂"),
        applies_when=("twin.medications.0.name is not null", "twin.labs.ldl_c_mmol_l >= 3.4"),
        recommends_lookup=("entity:drug:statin", "entity:biomarker:LDL-C"),
        evidence_level="B",
        confidence=0.72,
        safety_tags=("no_medication_adjustment",),
        external_sources=(
            {
                "source": "guideline:acc-aha-cholesterol-management",
                "kind": "guideline",
                "review_status": "reviewed",
                "note": "Statin initiation, stopping, and dose decisions require clinician-led risk assessment.",
            },
        ),
    ),
    ClaimTemplate(
        topic_id="medical_boundary",
        entity_type="condition",
        entity_id="medical-boundary",
        title="健康建议必须保留医学边界",
        summary="系统可以做健康管理、风险沟通和复查提醒，但不能把课程知识包装成诊断、治疗、处方或替代医生的确定性结论。",
        domains=("safety", "general_wellness"),
        keywords=("医学", "诊断", "医患", "循证", "治疗", "生命第一", "医学通识"),
        applies_when=("twin.goals.metabolic_health.active == true", "twin.goals.weight_loss.active == true"),
        recommends_lookup=("entity:intervention:doctor-handoff", "entity:condition:medical-boundary"),
        evidence_level="B",
        confidence=0.82,
        decay_rate="slow",
        safety_tags=("medical_boundary",),
    ),
    ClaimTemplate(
        topic_id="microbiome_behavior_boundary",
        entity_type="condition",
        entity_id="microbiome-dysbiosis",
        title="菌群建议应优先落到饮食和生活方式而非确定性补剂",
        summary="菌群相关知识适合解释饮食、睡眠、药物和肠道反应，但个性化补剂或菌群干预证据复杂，应避免确定性承诺。",
        domains=("microbiome", "nutrition"),
        keywords=("微生物组", "菌群", "肠道", "共生", "药效", "过劳肥"),
        applies_when=("twin.goals.metabolic_health.active == true",),
        recommends_lookup=("entity:condition:microbiome-dysbiosis", "entity:intervention:microbiome-diet"),
        evidence_level="C",
        confidence=0.62,
        safety_tags=("avoid_microbiome_overclaim",),
    ),
    ClaimTemplate(
        topic_id="mthfr_boundary",
        entity_type="gene",
        entity_id="MTHFR",
        title="MTHFR 相关建议必须结合 Hcy/B12/叶酸状态",
        summary="MTHFR 相关基因解释只能作为叶酸代谢风险沟通线索，建议必须结合 Hcy、B12、叶酸状态和医生边界。",
        domains=("genetics",),
        keywords=("MTHFR", "叶酸", "一碳", "甲基化", "基因"),
        applies_when=("twin.genetics.MTHFR_C677T in ['CT', 'TT']",),
        recommends_lookup=("entity:gene:MTHFR", "entity:biomarker:Hcy"),
        evidence_level="C",
        confidence=0.66,
        safety_tags=("genetic_boundary",),
        external_sources=(
            {
                "source": "pubmed:19033271",
                "kind": "research",
                "review_status": "reviewed",
                "note": "MTHFR C677T should be interpreted with folate, B12, and homocysteine context.",
            },
        ),
    ),
    ClaimTemplate(
        topic_id="apoe_lipid_boundary",
        entity_type="gene",
        entity_id="APOE",
        title="APOE 风险解释不能替代血脂临床锚点",
        summary="APOE 相关解释应作为长期风险沟通线索，不能替代 LDL-C、ApoB、家族史和医生评估。",
        domains=("genetics", "cardiovascular"),
        keywords=("APOE", "脂质", "胆固醇", "基因"),
        applies_when=("twin.genetics.APOE is not null",),
        recommends_lookup=("entity:gene:APOE", "entity:biomarker:LDL-C"),
        evidence_level="C",
        confidence=0.64,
        safety_tags=("genetic_boundary",),
        external_sources=(
            {
                "source": "pubmed:23400713",
                "kind": "research",
                "review_status": "reviewed",
                "note": "APOE interpretation should be anchored to lipid markers and clinical risk context.",
            },
        ),
    ),
    ClaimTemplate(
        topic_id="gene_pharmacogenomics_boundary",
        entity_type="condition",
        entity_id="medication-safety",
        title="药物代谢基因结果只用于用药核对边界",
        summary="CYP2D6、CYP2C19 等药物代谢基因结果可作为用药核对线索，但不能直接推出启停药或剂量调整；应结合正在使用的药品、病史和医生/药师意见。",
        domains=("genetics", "medication_safety"),
        keywords=("CYP2D6", "CYP2C19", "药物基因", "药物代谢", "华法林"),
        applies_when=("twin.genetics.CYP2D6 is not null", "twin.genetics.CYP2C19 is not null"),
        source_keys=("dedao:qiuzilong-genetics-20", "dedao:wangjiawei-medication-safety"),
        recommends_lookup=("entity:condition:medication-safety", "entity:intervention:medication-review"),
        evidence_level="C",
        confidence=0.66,
        decay_rate="slow",
        safety_tags=("genetic_boundary", "no_medication_adjustment"),
    ),
)


def compile_dedao_ingest_artifacts(
    *,
    source_root: str | Path,
    base_artifact_dir: str | Path,
    course_names: list[str] | None = None,
    max_courses: int | None = None,
    max_lessons_per_course: int | None = None,
    now: datetime | None = None,
) -> IngestResult:
    now = now or datetime.now(UTC)
    source_root = Path(source_root)
    base_artifact_dir = Path(base_artifact_dir)
    existing = _load_existing_artifacts(base_artifact_dir)
    sources = _select_sources(source_root, course_names, max_courses)

    pages: dict[str, dict[str, Any]] = {}
    entities: dict[str, dict[str, Any]] = {}
    claims: dict[str, dict[str, Any]] = {}
    archived_claims: dict[str, dict[str, Any]] = {}
    protocols: dict[str, dict[str, Any]] = {}
    relations: dict[tuple[str, str, str], dict[str, Any]] = {}
    source_stats: list[dict[str, Any]] = []

    existing_claim_index = {
        _claim_key(claim): claim
        for claim in existing["claims"].values()
        if claim.get("doc_type") == "claim" and not claim.get("is_archived")
    }

    for source in sources:
        lessons = _load_lessons(Path(source.path), max_lessons=max_lessons_per_course)
        haystack = _build_haystack(source.course_name, lessons)
        page = _page_for_source(source, now)
        pages[page["doc_id"]] = page
        matched = 0
        protocol_matched = 0
        for template in CLAIM_TEMPLATES:
            if not _template_matches_source(template, source.source_key, source.domains, haystack):
                continue
            matched += 1
            claim = _claim_for_template(template, source.source_key, now)
            related_entities = TEMPLATE_RELATED_ENTITIES.get(template.topic_id, ())
            old = None if claim["doc_id"] in existing["claims"] else existing_claim_index.get(_claim_key(claim))
            if old and old.get("doc_id") != claim["doc_id"]:
                if _can_supersede_existing(old):
                    claim["supersedes"] = [old["doc_id"]]
                    archived = dict(old)
                    archived["is_archived"] = True
                    metadata = dict(archived.get("metadata") or {})
                    metadata["superseded_by"] = claim["doc_id"]
                    metadata["superseded_at"] = now.isoformat()
                    archived["metadata"] = metadata
                    archived_claims[archived["doc_id"]] = archived
                else:
                    claim["metadata"]["candidate_duplicates"] = [old["doc_id"]]
            claims[claim["doc_id"]] = claim
            for doc_id in [
                f"entity:{template.entity_type}:{template.entity_id}",
                *template.recommends_lookup,
                *related_entities,
            ]:
                if doc_id.startswith("entity:"):
                    entities[doc_id] = _entity_for_doc_id(doc_id, now)
            _add_relation(
                relations,
                src_doc_id=f"entity:{template.entity_type}:{template.entity_id}",
                dst_doc_id=claim["doc_id"],
                relation="has_claim",
                confidence=template.relation_confidence,
                source_claim_id=claim["doc_id"],
            )
            _add_relation(
                relations,
                src_doc_id=page["doc_id"],
                dst_doc_id=claim["doc_id"],
                relation="supports",
                confidence=0.68,
                source_claim_id=claim["doc_id"],
            )
            for lookup in template.recommends_lookup:
                if lookup.startswith("entity:"):
                    _add_relation(
                        relations,
                        src_doc_id=claim["doc_id"],
                        dst_doc_id=lookup,
                        relation="recommends_lookup",
                        confidence=0.72,
                        source_claim_id=claim["doc_id"],
                    )
            for related_doc_id in related_entities:
                if related_doc_id.startswith("entity:") and related_doc_id not in template.recommends_lookup:
                    _add_relation(
                        relations,
                        src_doc_id=claim["doc_id"],
                        dst_doc_id=related_doc_id,
                        relation="mentions",
                        confidence=0.62,
                        source_claim_id=claim["doc_id"],
                    )
            _add_entity_context_relations(
                relations,
                primary_entity_doc_id=f"entity:{template.entity_type}:{template.entity_id}",
                context_entity_doc_ids=[*template.recommends_lookup, *related_entities],
                source_claim_id=claim["doc_id"],
            )
            protocol = _protocol_for_claim_template(template, source, claim, lessons, now)
            if protocol:
                protocol_matched += 1
                protocols[protocol["doc_id"]] = protocol
                _add_relation(
                    relations,
                    src_doc_id=claim["doc_id"],
                    dst_doc_id=protocol["doc_id"],
                    relation="compiled_to_protocol",
                    confidence=0.64,
                    source_claim_id=claim["doc_id"],
                )
        source_stats.append(
            {
                "course_name": source.course_name,
                "source_key": source.source_key,
                "domains": source.domains,
                "lessons_read": len(lessons),
                "claims_generated": matched,
                "protocols_generated": protocol_matched,
            }
        )

    result = IngestResult(
        source_root=source_root,
        base_artifact_dir=base_artifact_dir,
        pages=sorted(pages.values(), key=lambda item: item["doc_id"]),
        entities=sorted(entities.values(), key=lambda item: item["doc_id"]),
        claims=sorted(claims.values(), key=lambda item: item["doc_id"]),
        archived_claims=sorted(archived_claims.values(), key=lambda item: item["doc_id"]),
        protocols=sorted(protocols.values(), key=lambda item: item["doc_id"]),
        relations=sorted(relations.values(), key=lambda item: (item["src_doc_id"], item["relation"], item["dst_doc_id"])),
        source_stats=source_stats,
    )
    result.diff = _diff_counts(existing, result)
    result.manifest = _manifest_for_result(result, now)
    return result


def write_reviewed_artifacts(result: IngestResult, output_dir: str | Path) -> dict[str, int]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    existing = _load_existing_artifacts(output)
    merged_pages = _merge_by_doc_id(existing["pages"], result.pages)
    merged_entities = _merge_by_doc_id(existing["entities"], result.entities)
    merged_claims = _merge_by_doc_id(existing["claims"], [*result.archived_claims, *result.claims])
    merged_protocols = _merge_by_doc_id(existing["protocols"], result.protocols)
    merged_contraindications = _merge_by_doc_id(existing["contraindications"], result.contraindications)
    merged_eval_cases = _merge_by_doc_id(existing["eval_cases"], result.eval_cases)
    merged_relations = _merge_relations(existing["relations"], result.relations)

    _write_jsonl(output / "pages.jsonl", merged_pages.values())
    _write_jsonl(output / "entities.jsonl", merged_entities.values())
    _write_jsonl(output / "claims.jsonl", merged_claims.values())
    _write_jsonl(output / "protocols.jsonl", merged_protocols.values())
    _write_jsonl(output / "contraindications.jsonl", merged_contraindications.values())
    _write_jsonl(output / "eval_cases.jsonl", merged_eval_cases.values())
    _write_jsonl(output / "relations.jsonl", merged_relations.values())

    manifest = dict(result.manifest)
    manifest["counts"] = {
        "pages": len(merged_pages),
        "entities": len(merged_entities),
        "claims": len(merged_claims),
        "protocols": len(merged_protocols),
        "contraindications": len(merged_contraindications),
        "eval_cases": len(merged_eval_cases),
        "relations": len(merged_relations),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest["counts"]


def write_draft_artifacts(
    result: IngestResult,
    output_dir: str | Path,
    *,
    extractor: str,
    created_at: datetime | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Write extracted knowledge as draft-only artifacts for human review."""
    if not extractor.strip():
        raise ValueError("extractor is required for draft artifact audit")

    created_at = created_at or datetime.now(tz=UTC)
    root = Path(output_dir)
    draft_result = _copy_ingest_result_with_review_status(result, "draft")
    counts = write_reviewed_artifacts(draft_result, root)

    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest.setdefault("ingest", {})["review_status"] = "draft"
    manifest["draft_gate"] = {
        "status": "draft",
        "extractor": extractor,
        "created_at": created_at.isoformat(),
        "requires_review": True,
        "serving_allowed": False,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    draft_manifest: dict[str, Any] = {
        "artifact_dir": str(root),
        "status": "draft",
        "extractor": extractor,
        "created_at": created_at.isoformat(),
        "counts": counts,
        "requires_review": True,
        "serving_allowed": False,
    }
    if note:
        draft_manifest["note"] = note
    (root / "draft_manifest.json").write_text(
        json.dumps(draft_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return draft_manifest


def validate_artifact_review_gate(artifact_dir: str | Path) -> dict[str, Any]:
    """Return whether an artifact directory is eligible for serving import."""
    root = Path(artifact_dir)
    documents = _artifact_review_status_counts(root, ARTIFACT_FILES[:-1])
    relations = _artifact_review_status_counts(root, ("relations.jsonl",))
    total = documents["total"] + relations["total"]

    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest_status = (manifest.get("review") or {}).get("status") or (manifest.get("ingest") or {}).get(
        "review_status"
    )

    blocking_reasons: list[str] = []
    if total == 0:
        blocking_reasons.append("empty_artifact_dir")
    if documents["draft"] or relations["draft"]:
        blocking_reasons.append("draft_artifacts_present")
    if documents["missing"] or relations["missing"] or documents["other"] or relations["other"]:
        blocking_reasons.append("unreviewed_artifacts_present")
    if manifest_status != "reviewed":
        blocking_reasons.append("manifest_not_reviewed")

    serving_allowed = not blocking_reasons
    return {
        "artifact_dir": str(root),
        "serving_allowed": serving_allowed,
        "requires_review": not serving_allowed,
        "manifest_status": manifest_status,
        "documents": documents,
        "relations": relations,
        "blocking_reasons": blocking_reasons,
    }


def review_draft_artifacts(
    artifact_dir: str | Path,
    *,
    reviewer: str,
    reviewed_at: datetime | None = None,
) -> dict[str, Any]:
    """Promote draft artifacts after human review and attach gate validation."""
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("reviewer is required to promote draft artifacts")

    review_manifest = promote_artifact_review_status(
        artifact_dir,
        reviewer=reviewer,
        reviewed_at=reviewed_at,
        from_status="draft",
        to_status="reviewed",
    )
    validation = validate_artifact_review_gate(artifact_dir)
    review_manifest["validation"] = validation
    review_manifest["serving_allowed"] = validation["serving_allowed"]

    root = Path(artifact_dir)
    (root / "review_manifest.json").write_text(
        json.dumps(review_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    draft_manifest_path = root / "draft_manifest.json"
    if draft_manifest_path.exists():
        draft_manifest = json.loads(draft_manifest_path.read_text(encoding="utf-8"))
        draft_manifest["status"] = "reviewed" if validation["serving_allowed"] else "review_blocked"
        draft_manifest["reviewer"] = reviewer
        draft_manifest["reviewed_at"] = review_manifest["reviewed_at"]
        draft_manifest["serving_allowed"] = validation["serving_allowed"]
        draft_manifest["requires_review"] = not validation["serving_allowed"]
        draft_manifest_path.write_text(
            json.dumps(draft_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return review_manifest


def promote_artifact_review_status(
    artifact_dir: str | Path,
    *,
    reviewer: str,
    reviewed_at: datetime | None = None,
    from_status: str = "draft",
    to_status: str = "reviewed",
) -> dict[str, Any]:
    """Promote generated artifacts after human review and write an audit manifest."""
    root = Path(artifact_dir)
    reviewed_at = reviewed_at or datetime.now(tz=UTC)
    reviewed_at_text = reviewed_at.isoformat()

    counts = {
        "pages_reviewed": _promote_jsonl_file(root / "pages.jsonl", reviewer, reviewed_at_text, from_status, to_status),
        "entities_reviewed": _promote_jsonl_file(
            root / "entities.jsonl", reviewer, reviewed_at_text, from_status, to_status
        ),
        "claims_reviewed": _promote_jsonl_file(root / "claims.jsonl", reviewer, reviewed_at_text, from_status, to_status),
        "protocols_reviewed": _promote_jsonl_file(
            root / "protocols.jsonl", reviewer, reviewed_at_text, from_status, to_status
        ),
        "contraindications_reviewed": _promote_jsonl_file(
            root / "contraindications.jsonl", reviewer, reviewed_at_text, from_status, to_status
        ),
        "eval_cases_reviewed": _promote_jsonl_file(
            root / "eval_cases.jsonl", reviewer, reviewed_at_text, from_status, to_status
        ),
        "relations_reviewed": _promote_jsonl_file(
            root / "relations.jsonl", reviewer, reviewed_at_text, from_status, to_status
        ),
    }
    counts["documents_reviewed"] = (
        counts["pages_reviewed"]
        + counts["entities_reviewed"]
        + counts["claims_reviewed"]
        + counts["protocols_reviewed"]
        + counts["contraindications_reviewed"]
        + counts["eval_cases_reviewed"]
    )

    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest.setdefault("ingest", {})["review_status"] = to_status
    manifest["review"] = {
        "status": to_status,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at_text,
        "documents_reviewed": counts["documents_reviewed"],
        "relations_reviewed": counts["relations_reviewed"],
        "from_status": from_status,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    review_manifest = {
        "artifact_dir": str(root),
        "reviewer": reviewer,
        "reviewed_at": reviewed_at_text,
        "from_status": from_status,
        "to_status": to_status,
        **counts,
    }
    (root / "review_manifest.json").write_text(
        json.dumps(review_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return review_manifest


def build_pr_style_diff(result: IngestResult, output_dir: str | Path) -> str:
    """Render a review-friendly diff without mutating output_dir."""
    output_dir = Path(output_dir)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        if output_dir.exists():
            for file_name in [*ARTIFACT_FILES, "manifest.json"]:
                src = output_dir / file_name
                if src.exists():
                    shutil.copy2(src, tmp_path / file_name)
        write_reviewed_artifacts(result, tmp_path)
        chunks: list[str] = _build_review_queue_summary(result, output_dir)
        for file_name in [*ARTIFACT_FILES, "manifest.json"]:
            before = (output_dir / file_name).read_text(encoding="utf-8").splitlines(keepends=True) if (output_dir / file_name).exists() else []
            after = (tmp_path / file_name).read_text(encoding="utf-8").splitlines(keepends=True) if (tmp_path / file_name).exists() else []
            if before == after:
                continue
            import difflib

            chunks.extend(
                difflib.unified_diff(
                    before,
                    after,
                    fromfile=str(output_dir / file_name),
                    tofile=str(output_dir / file_name),
                    lineterm="",
                )
            )
        return "\n".join(chunks)


def _build_review_queue_summary(result: IngestResult, output_dir: Path) -> list[str]:
    existing = _load_existing_artifacts(output_dir)
    new_draft_claims = [
        claim
        for claim in result.claims
        if claim["doc_id"] not in existing["claims"] and (claim.get("metadata") or {}).get("review_status") == "draft"
    ]
    missing_external_evidence = [claim for claim in new_draft_claims if not _claim_has_external_evidence(claim)]
    candidate_duplicates = [
        claim
        for claim in result.claims
        if (claim.get("metadata") or {}).get("candidate_duplicates")
    ]
    if not new_draft_claims and not missing_external_evidence and not candidate_duplicates:
        return []

    lines = [
        "Review queue:",
        f"- New draft claims: {len(new_draft_claims)}",
        f"- Missing external evidence: {len(missing_external_evidence)}",
        f"- Candidate duplicates: {len(candidate_duplicates)}",
    ]
    if new_draft_claims:
        lines.append("- Claims needing review:")
        for claim in new_draft_claims:
            external_status = "yes" if _claim_has_external_evidence(claim) else "no"
            lines.append(
                f"  - {claim['doc_id']} | {claim.get('title', '')} | "
                f"evidence={claim.get('evidence_level', 'C')} | external={external_status}"
            )
    if candidate_duplicates:
        lines.append("- Candidate duplicate claims:")
        for claim in candidate_duplicates:
            duplicate_ids = ", ".join((claim.get("metadata") or {}).get("candidate_duplicates") or [])
            lines.append(f"  - {claim['doc_id']} -> {duplicate_ids}")
    lines.append("")
    return lines


def _claim_has_external_evidence(claim: dict[str, Any]) -> bool:
    metadata = claim.get("metadata") or {}
    if metadata.get("external_sources"):
        return True
    return any(str(source).startswith(("pubmed:", "guideline:")) for source in claim.get("sources") or [])


def _select_sources(source_root: Path, course_names: list[str] | None, max_courses: int | None) -> list[Any]:
    all_sources = scan_health_sources(source_root)
    if course_names:
        wanted = set(course_names)
        selected = [source for source in all_sources if source.course_name in wanted]
    else:
        selected = all_sources
    if max_courses is not None:
        selected = selected[:max_courses]
    return selected


def _load_lessons(course_dir: Path, max_lessons: int | None = None) -> list[dict[str, str]]:
    paths = [
        path
        for path in sorted(course_dir.rglob("*"), key=lambda item: str(item.relative_to(course_dir)))
        if path.is_file() and path.suffix.lower() in {".md", ".txt", ".pdf"}
    ]
    lessons: list[dict[str, str]] = []
    for path in paths[: max_lessons or len(paths)]:
        lessons.append(
            {
                "title": path.stem,
                "path": str(path),
                "text": _read_lesson_text(path),
            }
        )
    return lessons


def _read_lesson_text(path: Path) -> str:
    if path.suffix.lower() in {".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="ignore")[:8000]
    if path.suffix.lower() == ".pdf":
        return _read_pdf_text(path)[:8000]
    return ""


def _read_pdf_text(path: Path) -> str:
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        try:
            proc = subprocess.run(
                [pdftotext, "-f", "1", "-l", "2", "-layout", str(path), "-"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout.decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            pass
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:2])
    except Exception:  # noqa: BLE001
        return ""


def _build_haystack(course_name: str, lessons: list[dict[str, str]]) -> str:
    return "\n".join([course_name, *[lesson["title"] for lesson in lessons], *[lesson["text"] for lesson in lessons]]).lower()


def _template_matches_source(template: ClaimTemplate, source_key: str, domains: list[str], haystack: str) -> bool:
    if template.source_keys and source_key not in template.source_keys:
        return False
    if not set(template.domains).intersection(domains):
        return False
    return any(keyword.lower() in haystack for keyword in template.keywords)


def _page_for_source(source: Any, now: datetime) -> dict[str, Any]:
    doc_id = f"page:{source.source_key}"
    title = source.course_name
    return {
        "doc_id": doc_id,
        "doc_type": "article",
        "entity_type": "course",
        "entity_id": source.source_key.split(":", 1)[1],
        "title": title,
        "summary": f"{title} 的系统知识库课程页；仅保存转化后的主题索引和来源元数据。",
        "confidence": 0.60,
        "evidence_level": "C",
        "sources": [source.source_key],
        "last_confirmed": now.isoformat(),
        "decay_rate": "normal",
        "metadata": {
            "domains": source.domains,
            "lesson_count": source.lesson_count,
            "file_count": source.file_count,
            "license_scope": "internal_transformed_claims",
            "review_status": "draft",
        },
    }


def _claim_for_template(template: ClaimTemplate, source_key: str, now: datetime) -> dict[str, Any]:
    claim_id = f"claim:c_{_source_suffix(source_key)}_{template.topic_id}"
    metadata: dict[str, Any] = {
        "domain": template.domains[0],
        "domains": list(template.domains),
        "license_scope": "internal_transformed_claims",
        "review_status": "draft",
        "claim_boundary": CLAIM_BOUNDARY,
        "extraction_method": "deterministic_topic_template_v1",
    }
    if template.safety_tags:
        metadata["safety_tags"] = list(template.safety_tags)
    if template.external_sources:
        metadata["external_sources"] = [dict(source) for source in template.external_sources]
    sources = [source_key, *[source["source"] for source in metadata.get("external_sources", [])]]
    return {
        "doc_id": claim_id,
        "doc_type": "claim",
        "entity_type": template.entity_type,
        "entity_id": template.entity_id,
        "title": template.title,
        "summary": template.summary,
        "body": template.summary,
        "confidence": template.confidence,
        "evidence_level": template.evidence_level,
        "applies_when": list(template.applies_when),
        "recommends_lookup": list(template.recommends_lookup),
        "sources": sources,
        "last_confirmed": now.isoformat(),
        "decay_rate": template.decay_rate,
        "supersedes": [],
        "metadata": metadata,
    }


def _protocol_for_claim_template(
    template: ClaimTemplate,
    source: Any,
    claim: dict[str, Any],
    lessons: list[dict[str, str]],
    now: datetime,
) -> dict[str, Any] | None:
    if template.entity_type != "intervention":
        return None
    if not template.recommends_lookup:
        return None

    domain = _protocol_domain(template)
    protocol_id = f"protocol:{domain}:{template.topic_id}"
    verification = _protocol_verification(template)
    source_chapters = _source_chapters_for_template(template, lessons)
    title = f"{template.title}行动协议"
    summary = f"{template.summary} 执行时必须记录验证指标，并保留健康管理边界。"

    return {
        "doc_id": protocol_id,
        "doc_type": "protocol",
        "entity_type": template.entity_type,
        "entity_id": template.entity_id,
        "title": title,
        "summary": summary,
        "body": summary,
        "protocol_id": protocol_id,
        "domain": domain,
        "source_claims": [claim["doc_id"]],
        "applies_when": list(template.applies_when),
        "forbidden_when": _protocol_forbidden_when(template),
        "risk_level": _protocol_risk_level(template),
        "action_template": {
            "title": template.title,
            "domain": domain,
            "metric_key": verification["metric"],
            "target_value": verification["expected_direction"],
            "claim_boundary": CLAIM_BOUNDARY,
        },
        "verification": verification,
        "paid_source_policy": "transformed_summary_only",
        "confidence": min(template.confidence, 0.70),
        "evidence_level": template.evidence_level,
        "sources": claim.get("sources") or [source.source_key],
        "last_confirmed": now.isoformat(),
        "decay_rate": template.decay_rate,
        "metadata": {
            "domain": domain,
            "domains": list(template.domains),
            "license_scope": "internal_transformed_claims",
            "review_status": "draft",
            "source_course": source.course_name,
            "source_key": source.source_key,
            "source_chapters": source_chapters,
            "extraction_method": "deterministic_protocol_candidate_v1",
            "claim_boundary": CLAIM_BOUNDARY,
        },
    }


def _protocol_domain(template: ClaimTemplate) -> str:
    for domain in template.domains:
        if domain in {"sleep_recovery", "movement", "nutrition", "cardiovascular", "metabolic_health"}:
            return domain
    return template.domains[0] if template.domains else "general_wellness"


def _protocol_verification(template: ClaimTemplate) -> dict[str, Any]:
    by_topic = {
        "salt_reduction": ("systolic_bp", 7, "decrease"),
        "fiber_intake": ("hba1c_percent", 84, "decrease"),
        "protein_target": ("protein_intake_g", 7, "increase"),
        "energy_deficit": ("weight", 14, "decrease"),
        "weight_waist_tracking": ("waist_cm", 7, "observe"),
        "zone2_recovery_constraint": ("training_readiness_score", 7, "stable_or_increase"),
        "strength_training": ("strength_sessions", 14, "increase"),
        "sleep_regular_window": ("sleep_duration_hours", 7, "increase"),
        "microbiome_behavior_boundary": ("gi_symptom_score", 14, "observe"),
    }
    metric, window_days, expected_direction = by_topic.get(
        template.topic_id,
        ("self_report_adherence", 7, "observe"),
    )
    return {
        "metric": metric,
        "window_days": window_days,
        "expected_direction": expected_direction,
    }


def _protocol_forbidden_when(template: ClaimTemplate) -> list[str]:
    tags = set(template.safety_tags)
    forbidden = []
    if "recovery_constraint" in tags or "movement" in template.domains:
        forbidden.append("twin.acute.should_rest_from_training == true")
    if "doctor_if_severe_bp" in tags or "cardiovascular" in template.domains:
        forbidden.append("twin.labs.systolic_bp >= 160")
    return forbidden


def _protocol_risk_level(template: ClaimTemplate) -> str:
    domains = set(template.domains)
    tags = set(template.safety_tags)
    if domains.intersection({"medication_safety", "genetics"}) or "no_medication_adjustment" in tags:
        return "high"
    if domains.intersection({"cardiovascular"}) or template.entity_id in {"HbA1c", "LDL-C", "TG"}:
        return "moderate"
    return "low"


def _source_chapters_for_template(template: ClaimTemplate, lessons: list[dict[str, str]]) -> list[dict[str, str]]:
    matched = []
    for lesson in lessons:
        haystack = f"{lesson.get('title', '')}\n{lesson.get('text', '')}".lower()
        if any(keyword.lower() in haystack for keyword in template.keywords):
            matched.append(
                {
                    "title": lesson.get("title", ""),
                }
            )
        if len(matched) >= 3:
            break
    if matched:
        return matched
    if not lessons:
        return []
    first = lessons[0]
    return [{"title": first.get("title", "")}]


def _entity_for_doc_id(doc_id: str, now: datetime) -> dict[str, Any]:
    base = dict(ENTITY_CATALOG.get(doc_id) or {})
    if not base:
        _, entity_type, entity_id = doc_id.split(":", 2)
        base = {
            "doc_type": "entity",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "title": entity_id,
            "summary": f"{entity_id} 的系统知识库实体。",
            "domains": ["general_wellness"],
        }
    domains = base.pop("domains", ["general_wellness"])
    return {
        "doc_id": doc_id,
        "confidence": 0.70,
        "evidence_level": "C",
        "sources": ["system:dedao-ingest-v1"],
        "last_confirmed": now.isoformat(),
        "decay_rate": "normal",
        "metadata": {
            "domains": domains,
            "license_scope": "internal_transformed_claims",
            "review_status": "draft",
        },
        **base,
    }


def _add_relation(
    relations: dict[tuple[str, str, str], dict[str, Any]],
    *,
    src_doc_id: str,
    dst_doc_id: str,
    relation: str,
    confidence: float,
    source_claim_id: str,
) -> None:
    relations[(src_doc_id, dst_doc_id, relation)] = {
        "src_doc_id": src_doc_id,
        "dst_doc_id": dst_doc_id,
        "relation": relation,
        "confidence": confidence,
        "source_claim_id": source_claim_id,
        "metadata": {"review_status": "draft"},
    }


def _add_entity_context_relations(
    relations: dict[tuple[str, str, str], dict[str, Any]],
    *,
    primary_entity_doc_id: str,
    context_entity_doc_ids: list[str] | tuple[str, ...],
    source_claim_id: str,
) -> None:
    """Link Dedao-mined entities into a navigable graph.

    Claim-to-entity edges are useful for evidence sheets, but entity-to-entity
    edges let graph traversal answer questions such as "what does uric acid
    connect to?" without first keyword-matching the exact claim.
    """

    for context_doc_id in context_entity_doc_ids:
        if not context_doc_id.startswith("entity:"):
            continue
        if context_doc_id == primary_entity_doc_id:
            continue
        _add_relation(
            relations,
            src_doc_id=primary_entity_doc_id,
            dst_doc_id=context_doc_id,
            relation="contextualizes",
            confidence=0.58,
            source_claim_id=source_claim_id,
        )


def _load_existing_artifacts(root: Path) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "pages": _read_doc_jsonl(root / "pages.jsonl"),
        "entities": _read_doc_jsonl(root / "entities.jsonl"),
        "claims": _read_doc_jsonl(root / "claims.jsonl"),
        "protocols": _read_doc_jsonl(root / "protocols.jsonl"),
        "contraindications": _read_doc_jsonl(root / "contraindications.jsonl"),
        "eval_cases": _read_doc_jsonl(root / "eval_cases.jsonl"),
        "relations": _read_relation_jsonl(root / "relations.jsonl"),
    }


def _read_doc_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    result = {}
    for payload in _read_jsonl(path):
        result[payload["doc_id"]] = payload
    return result


def _read_relation_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    result = {}
    for payload in _read_jsonl(path):
        result[_relation_key(payload)] = payload
    return result


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path}:{line_no}: {exc}") from exc
    return rows


def _write_jsonl(path: Path, rows: Any) -> None:
    ordered = sorted(rows, key=lambda item: item.get("doc_id") or _relation_key(item))
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in ordered),
        encoding="utf-8",
    )


def _copy_ingest_result_with_review_status(result: IngestResult, status: str) -> IngestResult:
    copied = IngestResult(
        source_root=result.source_root,
        base_artifact_dir=result.base_artifact_dir,
        pages=_rows_with_review_status(result.pages, status),
        entities=_rows_with_review_status(result.entities, status),
        claims=_rows_with_review_status(result.claims, status),
        archived_claims=_rows_with_review_status(result.archived_claims, status),
        protocols=_rows_with_review_status(result.protocols, status),
        contraindications=_rows_with_review_status(result.contraindications, status),
        eval_cases=_rows_with_review_status(result.eval_cases, status),
        relations=_rows_with_review_status(result.relations, status),
        diff=deepcopy(result.diff),
        manifest=deepcopy(result.manifest),
        source_stats=deepcopy(result.source_stats),
    )
    copied.manifest.setdefault("ingest", {})["review_status"] = status
    return copied


def _rows_with_review_status(rows: list[dict[str, Any]], status: str) -> list[dict[str, Any]]:
    copied = deepcopy(rows)
    for row in copied:
        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            row["metadata"] = metadata
        metadata["review_status"] = status
    return copied


def _artifact_review_status_counts(root: Path, file_names: tuple[str, ...]) -> dict[str, int]:
    counts = {"total": 0, "reviewed": 0, "draft": 0, "missing": 0, "other": 0}
    for file_name in file_names:
        for row in _read_jsonl(root / file_name):
            counts["total"] += 1
            metadata = row.get("metadata")
            if not isinstance(metadata, dict) or "review_status" not in metadata:
                counts["missing"] += 1
                continue
            review_status = metadata.get("review_status")
            if review_status == "reviewed":
                counts["reviewed"] += 1
            elif review_status == "draft":
                counts["draft"] += 1
            else:
                counts["other"] += 1
    return counts


def _promote_jsonl_file(path: Path, reviewer: str, reviewed_at: str, from_status: str, to_status: str) -> int:
    if not path.exists():
        return 0
    rows = _read_jsonl(path)
    promoted = 0
    for row in rows:
        metadata = row.setdefault("metadata", {})
        if metadata.get("review_status", from_status) != from_status:
            continue
        metadata["review_status"] = to_status
        metadata["reviewed_by"] = reviewer
        metadata["reviewed_at"] = reviewed_at
        promoted += 1
    _write_jsonl(path, rows)
    return promoted


def _merge_by_doc_id(existing: dict[str, dict[str, Any]], generated: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    merged = dict(existing)
    for item in generated:
        merged[item["doc_id"]] = item
    return dict(sorted(merged.items()))


def _merge_relations(existing: dict[str, dict[str, Any]], generated: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    merged = dict(existing)
    for item in generated:
        merged[_relation_key(item)] = item
    return dict(sorted(merged.items()))


def _diff_counts(existing: dict[str, dict[str, dict[str, Any]]], result: IngestResult) -> dict[str, int]:
    return {
        "pages_added": sum(1 for item in result.pages if item["doc_id"] not in existing["pages"]),
        "entities_added": sum(1 for item in result.entities if item["doc_id"] not in existing["entities"]),
        "claims_added": sum(1 for item in result.claims if item["doc_id"] not in existing["claims"]),
        "protocols_added": sum(1 for item in result.protocols if item["doc_id"] not in existing["protocols"]),
        "relations_added": sum(1 for item in result.relations if _relation_key(item) not in existing["relations"]),
        "claims_superseded": len(result.archived_claims),
    }


def _manifest_for_result(result: IngestResult, now: datetime) -> dict[str, Any]:
    return {
        "protocol": "akbp",
        "version": "2.1",
        "compiled_at": now.isoformat(),
        "source_root": str(result.source_root),
        "license_scope": "internal_transformed_claims",
        "policy": "No full paid-course text is served. Claims are synthesized, short, and boundary-marked.",
        "ingest": {
            "pipeline": "deterministic_topic_template_v1",
            "review_status": "draft",
            "source_count": len(result.source_stats),
            "sources": result.source_stats,
        },
        "counts": {
            "pages": len(result.pages),
            "entities": len(result.entities),
            "claims": len(result.claims) + len(result.archived_claims),
            "protocols": len(result.protocols),
            "contraindications": len(result.contraindications),
            "eval_cases": len(result.eval_cases),
            "relations": len(result.relations),
        },
        "diff": result.diff,
    }


def _claim_key(claim: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    return (claim.get("entity_type"), claim.get("entity_id"), claim.get("title"))


def _relation_key(item: dict[str, Any]) -> str:
    return f"{item['src_doc_id']}|{item['relation']}|{item['dst_doc_id']}"


def _source_suffix(source_key: str) -> str:
    prefix, _, suffix = source_key.partition(":")
    suffix = f"{prefix}_{suffix}" if prefix else suffix
    return re.sub(r"[^a-zA-Z0-9]+", "_", suffix).strip("_").lower()


def _can_supersede_existing(claim: dict[str, Any]) -> bool:
    metadata = claim.get("metadata") or {}
    if metadata.get("review_status") == "draft":
        return True
    return any(str(source).startswith("system:old") for source in claim.get("sources") or [])
