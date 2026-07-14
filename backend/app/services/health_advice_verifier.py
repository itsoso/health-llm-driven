"""Deterministic verifier for user-visible health advice."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


HIGH_RISK_DOMAINS = {"supplement", "medication", "doctor_handoff"}
LOW_RISK_DOMAINS = {"sleep", "movement", "recovery", "emotion", "metabolic", "measurement"}
GUIDELINE_SOURCE_TYPES = {"guideline", "cpic", "fda", "drug_label"}
PAID_CONTENT_LEAK_MARKERS = ("课程原文", "付费课程正文", "逐字稿", "原文如下")
EPIGENETIC_MARKERS = ("甲基化", "表观遗传", "epigenetic", "methylation", "生物年龄", "pace of aging")
EPIGENETIC_OVERCLAIM_MARKERS = (
    "证明",
    "逆转",
    "治愈",
    "抗衰成功",
    "真实衰老速度改变",
    "短期疗效",
    "7 天",
    "7天",
    "一周",
)
DIAGNOSTIC_OVERCLAIM_MARKERS = (
    "确诊",
    "诊断为",
    "就是糖尿病",
    "已经得了",
    "一定会得",
    "不需要再复查",
    "不用复查",
    "不需要医生确认",
    "不用医生确认",
)
SELF_MEDICATION_NEGATIONS = (
    "不自行",
    "不要自行",
    "不得自行",
    "不能自行",
    "避免自行",
    "请勿自行",
    "切勿自行",
    "严禁自行",
    "禁止自行",
    "禁止擅自",
    "不可自行",
    "不应自行",
    "别自行",
    "不要擅自",
    "不得擅自",
    "请勿擅自",
    "切勿擅自",
    "严禁擅自",
    "不自己",
)
MEDICATION_CONTEXT_MARKERS = (
    "用药",
    "服药",
    "药物",
    "药品",
    "处方",
    "停药",
    "换药",
    "吃药",
    "药量",
    "剂量",
    "服用",
    "口服",
    "片剂",
    "胶囊",
    "mg",
)
MEDICATION_CHANGE_PATTERN = re.compile(
    r"停药|停用|停服|停掉|停止服用|不再(?:吃|服用)|别(?:再)?(?:吃|服用)|"
    r"不用(?:吃|服用)|取消|撤掉|去掉|中断用药|"
    r"换药|换(?:成|为|用|服|吃)|改(?:剂量|用|为|成|服|吃)|转(?:为|成|用|服)|"
    r"替(?:换)?(?:成|为|用)|变(?:为|成)|调(?:整剂量|成|为|到|至)|加量|减量|调整剂量|"
    r"剂量(?:加倍|减半)|减半|加倍|增至|减至|上调|下调"
)
MEDICATION_DOSE_TRANSITION_PATTERN = re.compile(
    r"(?:剂量|用量).{0,10}(?:增加|减少|上调|下调|增至|减至)|"
    r"(?:半|[零一二两三四五六七八九十百\d]+(?:\.\d+)?)\s*"
    r"(?:片|粒|毫克|mg|毫升|ml|单位|iu).{0,12}"
    r"(?:增加到|减少到|增加至|减少至|增至|减至|降到|降至|升到|升至|"
    r"改(?:为|成)?|变(?:为|成)?|调(?:为|成|到|至)?|到|至).{0,8}"
    r"(?:半|[零一二两三四五六七八九十百\d]+(?:\.\d+)?)\s*"
    r"(?:片|粒|毫克|mg|毫升|ml|单位|iu)"
)
MEDICATION_CHANGE_BEFORE_REFERENCE_PATTERN = re.compile(
    r"(?:把|将)?(?:停|暂停|中断|取消|撤(?:掉|销)?|去掉|"
    r"不(?:要|用|再)?(?:吃|服|用)|"
    r"改(?:吃|服|用|为|成)|换(?:吃|服|用|为|成)|替(?:换|代|成)|"
    r"转(?:吃|服|用|为|成)|调(?:整剂量|成|为|到|至)|"
    r"减(?:半|量|到|至|[零一二两三四五六七八九十百\d]+\s*(?:片|粒|毫克|mg|毫升|ml|单位|iu))|"
    r"少(?:吃|服|用)\s*[零一二两三四五六七八九十百\d]+\s*(?:片|粒|毫克|mg|毫升|ml|单位|iu)|"
    r"多(?:吃|服|用)\s*[零一二两三四五六七八九十百\d]+\s*(?:片|粒|毫克|mg|毫升|ml|单位|iu)|"
    r"降(?:到|至)|增(?:加|到|至)|"
    r"加(?:量|倍|到|至|[零一二两三四五六七八九十百\d]+\s*(?:片|粒|毫克|mg|毫升|ml|单位|iu))|"
    r"升(?:到|至)|变(?:为|成))\s*$"
)
MEDICATION_CHANGE_AFTER_REFERENCE_PATTERN = re.compile(
    r"^[^。！？!?；;：:\n]{0,16}?(?:都|也)?\s*(?P<action>"
    r"停(?:了|掉|用|服|药)|停(?=$|[\s，,、])|暂停|中断|"
    r"别(?:再)?(?:吃|服|用)|不(?:要|用|再)?(?:吃|服|用)(?:了)?(?=$|[\s，,、])|"
    r"取消|撤(?:掉|销)?|去掉|"
    r"改(?:吃|服|用|为|成)|换(?:吃|服|用|为|成)|替(?:换|代|成)|"
    r"转(?:吃|服|用|为|成)|调(?:整剂量|成|为|到|至)|"
    r"减(?:半|量|到|至|[零一二两三四五六七八九十百\d]+\s*(?:片|粒|毫克|mg|毫升|ml|单位|iu))|"
    r"少(?:吃|服|用)\s*[零一二两三四五六七八九十百\d]+\s*(?:片|粒|毫克|mg|毫升|ml|单位|iu)|"
    r"多(?:吃|服|用)\s*[零一二两三四五六七八九十百\d]+\s*(?:片|粒|毫克|mg|毫升|ml|单位|iu)|"
    r"降(?:到|至)|增(?:加|到|至)|"
    r"加(?:量|倍|到|至|[零一二两三四五六七八九十百\d]+\s*(?:片|粒|毫克|mg|毫升|ml|单位|iu))|"
    r"升(?:到|至)|变(?:为|成))"
)
MEDICATION_CLAUSE_SPLIT_PATTERN = re.compile(
    r"[。！？!?；;：:.\n]+|[,，](?=把|将|立即|直接|现在|开始|执行)|"
    r"(?:并且|但是|但|然而|然后|随后|接着|同时|现在|而)"
    r"(?=把|将|停|换|改|转|替|变|加|减|调|增|取消|撤)|"
    r"后(?=把|将|立即|直接|现在|开始|执行)"
)
MEDICATION_CONSULT_MARKERS = ("咨询医生", "联系医生", "请医生", "由医生")
MEDICATION_EXECUTION_MARKERS = ("执行", "直接", "立即", "现在", "开始", "照做")
MEDICATION_PRE_CONSULT_PATTERN = re.compile(
    r"(?:换药|调整剂量|改剂量|停药|加量|减量).{0,4}(?:前|之前).{0,8}"
    r"(?:请|需|要|必须|务必)?(?:先)?(?:咨询|联系)医生"
)
MEDICATION_REQUIRED_CONSULT_PATTERN = re.compile(
    r"(?:必须|务必|应当|需要|需).{0,6}(?:先)?(?:咨询|联系)医生.{0,6}"
    r"(?:再|之后再|后再)(?:调整剂量|改剂量|换药|停药|加量|减量)"
)
MEDICATION_CONDITIONAL_CONSULT_PATTERN = re.compile(
    r"^(?:如需|若需|如果需要)(?:调整剂量|改剂量|换药|停药|加量|减量)"
    r"[，,]?(?:请|应|需|务必)?(?:先)?(?:咨询|联系)医生(?:后再决定)?$"
)
RED_FLAG_SYMPTOM_MARKERS = (
    "胸痛",
    "呼吸困难",
    "晕厥",
    "呕血",
    "黑便",
    "单侧无力",
    "剧烈头痛",
    "持续高热",
)
RED_FLAG_DOWNGRADE_MARKERS = (
    "先在家观察",
    "不用就医",
    "不需要就医",
    "不用找医生",
    "不需要医生",
    "继续训练",
    "睡眠卫生",
    "放松训练",
    "多喝水",
)
LAB_REPORT_SIGNAL_TYPES = {
    "biomarker",
    "exam_report",
    "lab",
    "lab_report",
    "medical_exam",
    "medical_report",
}
LAB_REPORT_TEXT_MARKERS = (
    "hba1c",
    "糖化血红蛋白",
    "ldl",
    "ldl-c",
    "血脂",
    "alt",
    "ggt",
    "谷丙转氨酶",
    "谷氨酰转肽酶",
    "γ-谷氨酰转肽酶",
    "幽门螺杆菌",
    "h. pylori",
    "hp 阳性",
    "hp阳性",
    "胃镜",
    "内镜",
)
LAB_DIAGNOSIS_CONDITION_MARKERS = (
    "糖尿病",
    "高血压",
    "脂肪肝",
    "肝炎",
    "胃溃疡",
    "溃疡复发",
    "冠心病",
)
LAB_DIAGNOSIS_OVERCLAIM_MARKERS = (
    "确诊",
    "诊断为",
    "已经得了",
    "就是",
    "不需要再复查",
    "不用复查",
    "不需要医生确认",
    "不用医生确认",
)
LAB_MEDICATION_PLAN_MARKERS = (
    "三联",
    "四联",
    "根除方案",
    "阿莫西林",
    "克拉霉素",
    "甲硝唑",
    "抗生素",
    "ppi",
    "p-cab",
    "他汀",
    "二甲双胍",
    "胰岛素",
)
LAB_TREATMENT_ACTION_MARKERS = (
    "直接开始",
    "开始",
    "服用",
    "每天",
    "每晚",
    "疗程",
    "处方",
    "开药",
    "用药方案",
    "按",
    "治疗",
)
HRV_CAUSAL_MARKERS = ("根因", "病因", "导致", "造成", "引起", "引发", "直接原因")


@dataclass(frozen=True)
class AdviceVerification:
    allowed: bool
    decision: str
    reason: str
    required_changes: list[str] = field(default_factory=list)
    audit_tags: list[str] = field(default_factory=list)


def verify_advice(
    candidate: Any,
    evidence_resolution: Any,
    personal_matrix: dict[str, Any] | None,
    contraindications: list[dict[str, Any]] | None,
) -> AdviceVerification:
    evidence_refs = _candidate_list(candidate, "evidence_refs") or _resolution_list(
        evidence_resolution, "evidence_refs"
    )
    source_types = {
        str(item).lower()
        for item in (
            _candidate_list(candidate, "evidence_source_types")
            or _resolution_list(evidence_resolution, "source_types")
        )
    }
    domain = str(getattr(candidate, "domain", "") or "").lower()

    if _looks_like_paid_content_leak(getattr(candidate, "body", "") or ""):
        return AdviceVerification(
            allowed=False,
            decision="blocked",
            reason="paid_content_leakage",
            required_changes=["remove_paid_source_excerpt"],
            audit_tags=["paid_content_leakage"],
        )

    if _is_epigenetic_overclaim(candidate, personal_matrix or {}):
        return AdviceVerification(
            allowed=False,
            decision="blocked",
            reason="epigenetic_overclaim",
            required_changes=["rewrite_as_long_term_proxy"],
            audit_tags=["epigenetic_boundary"],
        )

    lab_report_boundary_changes = _lab_report_boundary_required_changes(
        candidate,
        personal_matrix or {},
    )
    if lab_report_boundary_changes:
        return AdviceVerification(
            allowed=False,
            decision="blocked",
            reason="lab_report_boundary_violation",
            required_changes=lab_report_boundary_changes,
            audit_tags=["lab_report_boundary"],
        )

    medical_boundary_changes = _medical_boundary_required_changes(candidate)
    if medical_boundary_changes:
        return AdviceVerification(
            allowed=False,
            decision="blocked",
            reason="medical_boundary_violation",
            required_changes=medical_boundary_changes,
            audit_tags=["medical_boundary_violation"],
        )

    contraindication = _matching_contraindication(candidate, contraindications or [])
    if contraindication is not None:
        return AdviceVerification(
            allowed=False,
            decision="blocked",
            reason="contraindicated",
            required_changes=["choose_fallback_protocol"],
            audit_tags=[contraindication.get("contraindication_id") or "contraindication"],
        )

    if _is_pgx_medication_advice(candidate, personal_matrix or {}) and not (
        source_types & GUIDELINE_SOURCE_TYPES
    ):
        return AdviceVerification(
            allowed=False,
            decision="blocked",
            reason="pgx_medication_requires_guideline",
            required_changes=["attach_guideline_or_cpic_source"],
            audit_tags=["pgx_medication_boundary"],
        )

    if _is_high_risk(candidate):
        required_changes = []
        if not evidence_refs:
            required_changes.append("evidence_refs")
        if not getattr(candidate, "verification_metric", None):
            required_changes.append("verification_metric")
        if required_changes:
            return AdviceVerification(
                allowed=False,
                decision="blocked",
                reason="high_risk_missing_evidence",
                required_changes=required_changes,
                audit_tags=["unsupported_high_risk_advice"],
            )

    if domain in LOW_RISK_DOMAINS and not evidence_refs and not source_types:
        return AdviceVerification(
            allowed=True,
            decision="downgraded",
            reason="low_risk_missing_external_evidence",
            required_changes=["mark_model_inference"],
            audit_tags=["model_inference"],
        )

    return AdviceVerification(allowed=True, decision="allowed", reason="allowed")


def _is_high_risk(candidate: Any) -> bool:
    domain = str(getattr(candidate, "domain", "") or "").lower()
    explicit_risk = str(getattr(candidate, "risk_level", "") or "").lower()
    text = f"{getattr(candidate, 'title', '')} {getattr(candidate, 'body', '')}".lower()
    return (
        domain in HIGH_RISK_DOMAINS
        or explicit_risk == "high"
        or "pgx" in text
        or "cyp2" in text
        or "用药" in text
    )


def _is_pgx_medication_advice(candidate: Any, personal_matrix: dict[str, Any]) -> bool:
    text = f"{getattr(candidate, 'title', '')} {getattr(candidate, 'body', '')}".lower()
    if "用药" in text or "药" in text or "medication" in text:
        if "pgx" in text or "cyp2" in text:
            return True
        for signal in personal_matrix.get("signals") or []:
            if isinstance(signal, dict) and str(signal.get("signal_type") or "").lower() == "genetics":
                return True
    return False


def _is_epigenetic_overclaim(candidate: Any, personal_matrix: dict[str, Any]) -> bool:
    text = f"{getattr(candidate, 'title', '')} {getattr(candidate, 'body', '')}".lower()
    has_epigenetic_text = any(marker.lower() in text for marker in EPIGENETIC_MARKERS)
    has_epigenetic_signal = any(
        isinstance(signal, dict)
        and str(signal.get("signal_type") or "").lower() == "epigenetic"
        for signal in personal_matrix.get("signals") or []
    )
    if not (has_epigenetic_text or has_epigenetic_signal):
        return False
    return any(marker.lower() in text for marker in EPIGENETIC_OVERCLAIM_MARKERS)


def _medical_boundary_required_changes(candidate: Any) -> list[str]:
    title = str(getattr(candidate, "title", "") or "")
    body = str(getattr(candidate, "body", "") or "")
    text = f"{title} {body}".lower()
    required_changes: list[str] = []

    if any(marker.lower() in text for marker in DIAGNOSTIC_OVERCLAIM_MARKERS):
        required_changes.append("rewrite_without_diagnosis_or_treatment")

    if _has_unreviewed_medication_change(candidate, title=title, body=body):
        required_changes.append("remove_self_medication_change")

    has_red_flag = any(marker in text for marker in RED_FLAG_SYMPTOM_MARKERS)
    downgrades_red_flag = any(marker in text for marker in RED_FLAG_DOWNGRADE_MARKERS)
    if has_red_flag and downgrades_red_flag:
        required_changes.append("escalate_red_flag_symptoms")

    return required_changes


def _has_unreviewed_medication_change(candidate: Any, *, title: str, body: str) -> bool:
    """子句级阻断药物变更；开放文本中的“医生确认”不构成可信授权。"""
    medication_domain = str(getattr(candidate, "domain", "")).lower() == "medication"
    clauses = [
        clause.strip().lower()
        for clause in MEDICATION_CLAUSE_SPLIT_PATTERN.split(f"{title}。{body}")
        if clause.strip()
    ]
    try:
        from app.services.drug_lexicon import medication_reference_spans
    except Exception:
        medication_reference_spans = None

    for clause in clauses:
        direct_matches = [
            *MEDICATION_CHANGE_PATTERN.finditer(clause),
            *MEDICATION_DOSE_TRANSITION_PATTERN.finditer(clause),
        ]
        reference_spans: tuple[tuple[int, int], ...] = ()
        if medication_reference_spans is not None:
            try:
                reference_spans = medication_reference_spans(clause)
            except Exception:
                reference_spans = ()
        near_matches: list[tuple[int, int]] = []
        for reference_start, reference_end in reference_spans:
            before_start = max(0, reference_start - 16)
            before = clause[before_start:reference_start]
            before_match = MEDICATION_CHANGE_BEFORE_REFERENCE_PATTERN.search(before)
            if before_match is not None:
                near_matches.append((before_start + before_match.start(), before_start + before_match.end()))
            after = clause[reference_end:min(len(clause), reference_end + 12)]
            after_match = MEDICATION_CHANGE_AFTER_REFERENCE_PATTERN.search(after)
            if after_match is not None:
                near_matches.append((
                    reference_end + after_match.start("action"),
                    reference_end + after_match.end("action"),
                ))
        raw_matches = sorted(
            {(match.start(), match.end()) for match in direct_matches} | set(near_matches),
        )
        matches: list[tuple[int, int]] = []
        for match_start, match_end in raw_matches:
            if matches and match_start <= matches[-1][1]:
                previous_start, previous_end = matches[-1]
                matches[-1] = (previous_start, max(previous_end, match_end))
            else:
                matches.append((match_start, match_end))
        if not matches:
            continue

        has_context = medication_domain or any(marker in clause for marker in MEDICATION_CONTEXT_MARKERS)
        if not has_context:
            has_context = bool(reference_spans)
        if not has_context and medication_reference_spans is None:
            has_context = True
        if not has_context:
            continue

        single_action_safety_boundary = len(matches) == 1 and (
            MEDICATION_PRE_CONSULT_PATTERN.search(clause) is not None
            or MEDICATION_REQUIRED_CONSULT_PATTERN.search(clause) is not None
        )
        warning_scope = _warning_scope_covers_all_actions(clause, matches)
        for index, (match_start, _match_end) in enumerate(matches):
            conditional_handoff = (
                index == 0 and len(matches) == 1
                and MEDICATION_CONDITIONAL_CONSULT_PATTERN.fullmatch(clause) is not None
            )
            if warning_scope or conditional_handoff or single_action_safety_boundary:
                continue
            return True
    return False


def _warning_scope_covers_all_actions(
    clause: str,
    matches: list[tuple[int, int]],
) -> bool:
    if not matches or any(marker in clause for marker in MEDICATION_EXECUTION_MARKERS):
        return False
    first_action_start = matches[0][0]
    has_prohibition = any(
        (position := clause.find(marker)) >= 0 and position <= first_action_start
        for marker in SELF_MEDICATION_NEGATIONS
    )
    if not has_prohibition or len(matches) == 1:
        return has_prohibition
    for previous, current in zip(matches, matches[1:]):
        bridge = clause[previous[1]:current[0]]
        try:
            from app.services.drug_lexicon import strip_medication_references

            bridge = strip_medication_references(bridge)
        except Exception:
            return False
        bridge = re.sub(r"\s|、|/|或者|或|以及|和|及", "", bridge)
        if bridge:
            return False
    return True


def _lab_report_boundary_required_changes(
    candidate: Any,
    personal_matrix: dict[str, Any],
) -> list[str]:
    text = f"{getattr(candidate, 'title', '')} {getattr(candidate, 'body', '')}".lower()
    if not _has_lab_or_report_context(candidate, personal_matrix, text):
        return []

    required_changes: list[str] = []
    if _turns_lab_fact_into_diagnosis(text):
        required_changes.append("rewrite_lab_fact_without_diagnosis")
    if _turns_lab_fact_into_medication_plan(text):
        required_changes.append("remove_prescription_or_self_medication_plan")
    if _uses_hrv_as_direct_disease_cause(text, personal_matrix):
        required_changes.append("rewrite_hrv_as_correlate_not_cause")
    return required_changes


def _has_lab_or_report_context(candidate: Any, personal_matrix: dict[str, Any], text: str) -> bool:
    if _candidate_list(candidate, "lab_report_facts"):
        return True
    if personal_matrix.get("lab_report_facts"):
        return True
    if any(marker in text for marker in LAB_REPORT_TEXT_MARKERS):
        return True

    for signal in personal_matrix.get("signals") or []:
        if not isinstance(signal, dict):
            continue
        signal_type = str(signal.get("signal_type") or "").lower()
        signal_blob = " ".join(
            str(signal.get(key) or "").lower()
            for key in ("signal_id", "name", "metric_key", "source", "category")
        )
        if signal_type in LAB_REPORT_SIGNAL_TYPES:
            return True
        if any(marker in signal_blob for marker in LAB_REPORT_TEXT_MARKERS):
            return True
    return False


def _turns_lab_fact_into_diagnosis(text: str) -> bool:
    if any(marker in text for marker in ("不需要再复查", "不用复查", "不需要医生确认", "不用医生确认")):
        return True
    if any(marker in text for marker in ("确诊", "诊断为", "已经得了")):
        return True
    has_condition = any(marker in text for marker in LAB_DIAGNOSIS_CONDITION_MARKERS)
    if has_condition and any(marker in text for marker in LAB_DIAGNOSIS_OVERCLAIM_MARKERS):
        return True
    if has_condition and "按" in text and "治疗" in text:
        return True
    return False


def _turns_lab_fact_into_medication_plan(text: str) -> bool:
    has_medication = any(marker in text for marker in LAB_MEDICATION_PLAN_MARKERS)
    has_action = any(marker in text for marker in LAB_TREATMENT_ACTION_MARKERS)
    return has_medication and has_action


def _uses_hrv_as_direct_disease_cause(text: str, personal_matrix: dict[str, Any]) -> bool:
    has_hrv_text = "hrv" in text or "心率变异" in text
    has_hrv_signal = any(
        isinstance(signal, dict)
        and (
            "hrv"
            in " ".join(
                str(signal.get(key) or "").lower()
                for key in ("signal_id", "name", "metric_key")
            )
            or "心率变异"
            in " ".join(
                str(signal.get(key) or "")
                for key in ("signal_id", "name", "metric_key")
            )
        )
        for signal in personal_matrix.get("signals") or []
    )
    if not (has_hrv_text or has_hrv_signal):
        return False
    has_disease = any(marker in text for marker in LAB_DIAGNOSIS_CONDITION_MARKERS)
    has_cause = any(marker in text for marker in HRV_CAUSAL_MARKERS)
    return has_disease and has_cause


def _matching_contraindication(
    candidate: Any,
    contraindications: list[dict[str, Any]],
) -> dict[str, Any] | None:
    target = str(getattr(candidate, "target_value", "") or "").lower()
    title = str(getattr(candidate, "title", "") or "").lower()
    for contraindication in contraindications:
        blocks = {str(item).lower() for item in contraindication.get("blocks") or []}
        if target and target in blocks:
            return contraindication
        if "increase_intensity" in blocks and ("提高运动强度" in title or "高强度" in title):
            return contraindication
        if "protocol:movement:hiit" in blocks and ("hiit" in title or "高强度" in title):
            return contraindication
    return None


def _looks_like_paid_content_leak(text: str) -> bool:
    if any(marker in text for marker in PAID_CONTENT_LEAK_MARKERS):
        return True
    return text.count("得到") >= 20


def _candidate_list(candidate: Any, field_name: str) -> list[Any]:
    value = getattr(candidate, field_name, None)
    if not value:
        return []
    return list(value)


def _resolution_list(evidence_resolution: Any, field_name: str) -> list[Any]:
    if evidence_resolution is None:
        return []
    if isinstance(evidence_resolution, dict):
        value = evidence_resolution.get(field_name)
    else:
        value = getattr(evidence_resolution, field_name, None)
    if not value:
        return []
    return list(value)
