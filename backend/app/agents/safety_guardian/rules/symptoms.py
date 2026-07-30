"""症状级急症红线 —— 大病前兆 / 危及生命的急性症状识别。

与 vitals/labs(指标级)互补:这层匹配用户**自由文本症状记录**里危及生命的表现,
命中即 CRITICAL + requires_medical_attention,直接建议急救/急诊。

来源:冯雪·家庭健康管理100讲(第95讲大病前兆)+ 临床急症共识(ACS/卒中 FAST/急腹症)。
诚实边界:关键词匹配是兜底,会有漏判;对话层(orchestrator/agent prompt 的红线清单)
做自由文本兜底。自伤/自杀由 MentalHealthCompanion 处理,本文件不重复。

匹配数据:twin.acute.symptom_texts_all(近 72h 全部症状描述,未按呼吸道过滤)。
"""
import re
from typing import List, Optional

from app.agents.safety_guardian.engine import register
from app.agents.safety_guardian.schema import Alert, Severity
from app.config import settings
from app.services.health_evidence.intent import (
    affirmed_low_back_discriminator_ids,
    classify_health_intent,
)
from app.twin.schema import HealthTwin


def _symptom_blob(twin: HealthTwin) -> str:
    parts = list(twin.acute.symptom_texts_all or [])
    parts += list(twin.acute.illness_names or [])
    return " ".join(parts)


def _hit(blob: str, keywords: List[str]) -> bool:
    return any(k in blob for k in keywords)


_NEGATED_PREFIXES = (
    "没有",
    "并没有",
    "完全没有",
    "没有任何",
    "没有出现",
    "没有发生",
    "并无",
    "未见",
    "未出现",
    "未发生",
    "从未",
    "否认",
    "不伴",
    "不存在",
    "不是",
    "并不",
    "没",
    "不",
    "无",
)
_NEGATION_BEFORE_TERM = re.compile(
    r"(?:没有|并没有|完全没有|并无|无|未见|未出现|未发生|从未|"
    r"否认|不伴|不存在|并不是|不是|并不|没|不)"
    r"(?:出现|发生|任何|明显|相关|的)*$"
)
_NEGATED_RED_FLAG_IN_MATCH = re.compile(
    r"(?:没有|并没有|完全没有|没有任何|并无|未见|未出现|未发生|"
    r"从未|否认|不伴|不存在|并不|不是|没|不)"
    r".{0,5}"
    r"(?:发麻|麻木|刺痛|无力|乏力|没力|疼痛|疼|痛|困难|费力|"
    r"不畅|感觉减退|感觉迟钝)"
)


def _prefix_is_negated(prefix: str) -> bool:
    return bool(_NEGATION_BEFORE_TERM.search(prefix)) or any(
        prefix.endswith(item) for item in _NEGATED_PREFIXES
    )


def _affirmed_hit(blob: str, keywords: List[str]) -> bool:
    """Match a symptom term unless its occurrence is explicitly negated."""

    for keyword in keywords:
        start = 0
        while (index := blob.find(keyword, start)) >= 0:
            prefix = blob[max(0, index - 12):index]
            if not _prefix_is_negated(prefix):
                return True
            start = index + len(keyword)
    return False


def _affirmed_pattern(blob: str, pattern: str) -> bool:
    """Match a composite red-flag phrase with negation scoped to its region."""

    for match in re.finditer(pattern, blob):
        prefix = blob[max(0, match.start() - 12):match.start()]
        matched = match.group(0)
        if (
            not _prefix_is_negated(prefix)
            and not _NEGATED_RED_FLAG_IN_MATCH.search(matched)
        ):
            return True
    return False


# ─────────────────────── 可疑心脏事件 (ACS) ───────────────────────
@register
def acute_cardiac_event(twin: HealthTwin) -> Optional[Alert]:
    """胸痛/胸闷 + 放射痛/冷汗/濒死感 → 可疑急性冠脉综合征。"""
    blob = _symptom_blob(twin)
    if not blob:
        return None
    chest = _affirmed_hit(
        blob,
        ["胸痛", "胸闷", "心前区", "胸口痛", "胸口闷"],
    )
    danger = _affirmed_hit(
        blob,
        [
            "放射",
            "左臂",
            "肩膀痛",
            "下颌",
            "后背痛",
            "冷汗",
            "濒死",
            "压榨",
            "大汗",
        ],
    )
    if chest and danger:
        return Alert(
            rule_id="symptoms.acute_cardiac_event",
            category="symptoms",
            severity=Severity.CRITICAL,
            title="可疑急性心脏事件",
            message="记录到胸痛/胸闷伴放射痛或冷汗等表现,这是急性冠脉综合征(心梗)的典型警示组合,不能等待观察。",
            action="立即停止活动、原地休息,马上拨打 120 急救;若曾医嘱备有硝酸甘油可遵嘱舌下含服。不要自行开车去医院。",
            data_citation={"symptoms": twin.acute.symptom_texts_all[:6]},
            requires_medical_attention=True,
        )
    return None


# ─────────────────────── 可疑卒中 (FAST) ───────────────────────
@register
def acute_stroke_fast(twin: HealthTwin) -> Optional[Alert]:
    """突发面瘫/言语不清/单侧无力/视物异常 → 可疑卒中(FAST)。"""
    blob = _symptom_blob(twin)
    if not blob:
        return None
    if _affirmed_hit(
        blob,
        [
            "口角歪",
            "面瘫",
            "嘴歪",
            "言语不清",
            "说话不清",
            "半身",
            "单侧无力",
            "一侧无力",
            "肢体无力",
            "突然看不清",
            "视物模糊伴",
            "口齿不清",
        ],
    ):
        return Alert(
            rule_id="symptoms.acute_stroke_fast",
            category="symptoms",
            severity=Severity.CRITICAL,
            title="可疑卒中(中风)征象",
            message="记录到面瘫/言语不清/单侧肢体无力等表现,符合卒中 FAST 警示。卒中救治有时间窗,越早越好。",
            action="立即拨打 120,记下症状出现的准确时间(溶栓有 4.5 小时窗口)。让患者平卧、不要进食进水。",
            data_citation={"symptoms": twin.acute.symptom_texts_all[:6]},
            requires_medical_attention=True,
        )
    return None


# ─────────────────────── 急性呼吸困难 ───────────────────────
@register
def acute_dyspnea(twin: HealthTwin) -> Optional[Alert]:
    """突发呼吸困难/端坐呼吸/口唇发绀 → 急救。"""
    blob = _symptom_blob(twin)
    if not blob:
        return None
    if _affirmed_hit(
        blob,
        [
            "呼吸困难",
            "喘不上气",
            "喘不过气",
            "无法平卧",
            "端坐呼吸",
            "口唇发绀",
            "嘴唇发紫",
            "憋气严重",
            "呼吸费力",
        ],
    ):
        return Alert(
            rule_id="symptoms.acute_dyspnea",
            category="symptoms",
            severity=Severity.CRITICAL,
            title="急性呼吸困难",
            message="记录到突发呼吸困难/无法平卧/口唇发绀等表现,可能是心肺急症(急性心衰、肺栓塞、重症哮喘等)。",
            action="立即拨打 120,采取最舒适的半坐位,松开衣领,保持冷静;有医嘱吸入药(如沙丁胺醇)可遵嘱使用。",
            data_citation={"symptoms": twin.acute.symptom_texts_all[:6]},
            requires_medical_attention=True,
        )
    return None


# ─────────────────────── 可疑急腹症 ───────────────────────
@register
def acute_abdomen(twin: HealthTwin) -> Optional[Alert]:
    """突发剧烈腹痛/板状腹/呕血黑便 → 急诊。"""
    blob = _symptom_blob(twin)
    if not blob:
        return None
    severe_abd = _affirmed_hit(
        blob,
        ["剧烈腹痛", "腹痛难忍", "刀割样腹痛", "板状腹", "腹部僵硬"],
    )
    gi_bleed = _affirmed_hit(blob, ["呕血", "黑便", "便血", "柏油样便"])
    if severe_abd or gi_bleed:
        return Alert(
            rule_id="symptoms.acute_abdomen",
            category="symptoms",
            severity=Severity.CRITICAL,
            title="可疑急腹症 / 消化道出血",
            message="记录到剧烈腹痛伴腹肌紧张,或呕血/黑便等表现,可能是急腹症或消化道出血,需急诊处理。",
            action="立即就医/拨打 120;在明确诊断前**不要进食进水、不要自行用止痛药**(会掩盖病情)。",
            data_citation={"symptoms": twin.acute.symptom_texts_all[:6]},
            requires_medical_attention=True,
        )
    return None


# ─────────────────────── 腰背痛严重神经压迫警示 ───────────────────────
@register
def cauda_equina_warning(twin: HealthTwin) -> Optional[Alert]:
    """腰背痛 + 双侧神经/鞍区/膀胱肠道异常 → 立即急诊。

    这是关键词组合分流,不是马尾综合征诊断。要求先有腰背痛语境,再命中至少一个
    高特异警示组,避免把孤立泌尿或单侧坐骨神经症状误报成急症。
    """
    if not getattr(settings, "health_evidence_runtime_enabled", False):
        return None

    blob = _symptom_blob(twin)
    if (
        not blob
        or classify_health_intent(blob).domain != "low_back_pain"
    ):
        return None

    discriminator_ids = affirmed_low_back_discriminator_ids(blob)
    cauda_or_bilateral_neurologic = bool(
        discriminator_ids.intersection(
            {
                "low_back.cauda_equina",
                "low_back.progressive_neurologic_deficit",
            }
        )
    )
    sexual_neurologic_change = _affirmed_hit(
        blob,
        ["突然勃起困难", "突然无法勃起", "性交感觉消失", "性器官感觉消失"],
    )

    if cauda_or_bilateral_neurologic or sexual_neurologic_change:
        return Alert(
            rule_id="symptoms.cauda_equina_warning",
            category="symptoms",
            severity=Severity.CRITICAL,
            title="腰背痛伴严重神经压迫警示",
            message=(
                "记录到腰背痛伴双腿神经症状、会阴感觉异常或膀胱/肠道功能改变。"
                "这组表现需要立即排除严重神经压迫,不能先在家观察。"
            ),
            action=(
                "立即去急诊或拨打 120;不要自行开车。告知医护症状开始时间、"
                "双腿/会阴感觉变化以及排尿排便变化。"
            ),
            data_citation={"symptoms": twin.acute.symptom_texts_all[:6]},
            references=[
                (
                    "https://www.nice.org.uk/guidance/ng127/chapter/"
                    "Recommendations-for-adults-aged-over-16"
                ),
                "https://www.nhs.uk/conditions/back-pain/",
            ],
            requires_medical_attention=True,
        )
    return None


# ─────────────────────── 大病前兆(亚急性) ───────────────────────
@register
def red_flag_persistent_warning(twin: HealthTwin) -> Optional[Alert]:
    """不明原因持续发热 / 异常出血 / 体重骤降等大病前兆 → 尽快就医。"""
    blob = _symptom_blob(twin)
    if not blob:
        return None
    if _affirmed_hit(
        blob,
        [
            "持续发热",
            "反复发烧",
            "不明原因发热",
            "异常出血",
            "牙龈出血不止",
            "皮下出血",
            "体重骤降",
            "暴瘦",
            "不明原因消瘦",
            "淋巴结肿大",
        ],
    ):
        return Alert(
            rule_id="symptoms.red_flag_persistent_warning",
            category="symptoms",
            severity=Severity.HIGH,
            title="大病前兆征象",
            message="记录到不明原因持续发热/异常出血/体重骤降等表现,这类'大病前兆'需要医学排查,不宜自行观察拖延。",
            action="尽快到正规医院就诊,完善血常规等基础检查;就诊时把症状的起始时间、变化趋势告诉医生。",
            data_citation={"symptoms": twin.acute.symptom_texts_all[:6]},
            requires_medical_attention=True,
        )
    return None
