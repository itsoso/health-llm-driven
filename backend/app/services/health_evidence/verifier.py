"""Deterministic final-text verification for the health-evidence runtime.

Health-advice model output is untrusted until this module returns it.  The gate is
deliberately small and auditable: it rejects unsafe clinical claims and repairs a
missing clarification prompt without attempting to become a second language model.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from types import SimpleNamespace
from typing import Any, Collection, Iterable, Mapping

from app.services.health_advice_verifier import (
    _has_unreviewed_medication_change,
    _looks_like_paid_content_leak,
)


_CLAIM_REF_RE = re.compile(r"claim:[a-z0-9:_-]+", re.IGNORECASE)
_MEDICATION_CONTEXT = (
    "药",
    "剂量",
    "处方",
    "服用",
    "口服",
    "mg",
    "毫克",
)
_MEDICATION_CLAUSE_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")
_MEDICATION_START_OR_ADMIN_RE = re.compile(
    r"(?:建议|可以|可|应该|应当|请|立即|直接|现在).{0,10}"
    r"(?:开始)?(?:口服|服用|吃|使用)|"
    r"(?:开始|直接|立即|现在)(?:口服|服用|吃|使用)"
)
_MEDICATION_DOSE_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:mg|毫克|g|克|ml|毫升|片|粒|单位|iu)",
    re.IGNORECASE,
)
_MEDICATION_FREQUENCY_RE = re.compile(
    r"(?:每\s*\d+\s*小时|每隔\s*\d+\s*小时|每天|每日|每晚|"
    r"每次|一日\s*[一二两三四五六\d]+\s*次|"
    r"每天\s*[一二两三四五六\d]+\s*次)"
)
_MEDICATION_RECOMMEND_RE = re.compile(
    r"(?:建议|可以|可|应该|应当|请|开始|直接|立即|现在)"
)
_MEDICATION_PROHIBITION_RE = re.compile(
    r"(?:不|不要|不得|不能|不可|避免|请勿|切勿|严禁|禁止)"
    r"(?:自行|擅自)?(?:开始|口服|服用|吃|使用|开药)"
)
_MEDICATION_EXISTING_PLAN_BOUNDARY_RE = re.compile(
    r"(?:遵医嘱|按医嘱|按现有处方|由医生决定|先(?:咨询|联系)"
    r"(?:医生|药师)|让(?:医生|药师).{0,8}(?:判断|决定))"
)
_RED_FLAG_TERMS = (
    "会阴麻木",
    "鞍区麻木",
    "排不出尿",
    "排尿困难",
    "尿潴留",
    "大小便失禁",
    "双腿无力",
    "双下肢无力",
)
_RED_FLAG_DOWNGRADES = (
    "先在家观察",
    "不用就医",
    "不需要就医",
    "不用急诊",
    "不需要急诊",
    "继续训练",
    "忍一忍",
)
_UNCONDITIONAL_OVERCLAIMS = (
    "不需要医生确认",
    "不用医生确认",
    "无需医生确认",
    "不需要再复查",
    "不用复查",
)
_DIAGNOSTIC_MARKERS = ("确诊", "诊断为", "已经得了", "这就是", "那就是")
_DIAGNOSTIC_NEGATIONS = ("不", "不能", "无法", "不可", "未", "并非", "不能仅凭")
_KNOWN_AUTHORITIES = {
    "NICE": (
        "National Institute for Health and Care Excellence",
        "英国国家卫生与临床优化研究所",
    ),
    "NHS": ("National Health Service", "英国国家医疗服务体系"),
    "WHO": ("World Health Organization", "世界卫生组织"),
    "ACR": ("American College of Radiology", "美国放射学会"),
    "CDC": (
        "Centers for Disease Control and Prevention",
        "美国疾病控制与预防中心",
    ),
    "FDA": ("Food and Drug Administration", "美国食品药品监督管理局"),
    "MAYO": ("Mayo Clinic", "Mayo", "梅奥诊所", "梅奥"),
}
_PERSONAL_CONTEXT_MARKERS = {
    "genetic": ("你的基因", "根据你的基因", "基因结果显示"),
    "lab": (
        "你的化验",
        "根据你的化验",
        "你的体检报告",
        "你的检查报告",
        "你的报告显示",
    ),
    "wearable": (
        "你的可穿戴",
        "根据你的可穿戴",
        "你的手表数据",
        "你的garmin",
        "你的ringconn",
        "你的hrv",
    ),
    "diet": ("你的饮食记录", "根据你的饮食"),
    "medication": ("你的用药记录", "根据你的用药"),
}


@dataclass(frozen=True)
class HealthAnswerVerification:
    verdict: str
    text: str
    reasons: tuple[str, ...] = ()
    evidence_refs_used: tuple[str, ...] = ()

    def public_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reasons": list(self.reasons),
            "evidence_refs_used": list(self.evidence_refs_used),
            "released_text_sha256": health_answer_text_sha256(self.text),
        }


def health_answer_text_sha256(text: str) -> str:
    """Bind persisted verification metadata to the exact released answer."""

    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def verify_health_answer(
    text: str,
    *,
    risk_level: str,
    sufficiency: str,
    allowed_claim_ids: Collection[str],
    authority_organizations: Collection[str],
    context_categories: Collection[str],
    grounded_claims: Mapping[str, str] | None = None,
    missing_discriminators: Iterable[Mapping[str, Any]] = (),
) -> HealthAnswerVerification:
    """Return the only text that may be persisted or streamed for this turn."""

    candidate = str(text or "").strip()
    missing = tuple(
        item for item in missing_discriminators if isinstance(item, Mapping)
    )
    reasons: list[str] = []

    if not candidate:
        reasons.append("empty_answer")
    if _looks_like_paid_content_leak(candidate):
        reasons.append("paid_content_leakage")
    if _has_diagnostic_overclaim(candidate):
        reasons.append("diagnostic_overclaim")
    if _has_self_medication_change(candidate):
        reasons.append("self_medication_change")
    if _has_medication_prescribing(candidate):
        reasons.append("medication_prescribing")
    if _downgrades_red_flags(candidate, risk_level=risk_level):
        reasons.append("red_flag_downgrade")
    if _unsupported_claim_refs(candidate, allowed_claim_ids):
        reasons.append("unsupported_claim_reference")
    if _unsupported_authorities(candidate, authority_organizations):
        reasons.append("unsupported_authority_reference")
    if _claims_unselected_personal_context(candidate, context_categories):
        reasons.append("unsupported_personal_context")

    normalized_risk = str(risk_level).strip().lower()
    normalized_sufficiency = str(sufficiency).strip().lower()
    grounded = _normalized_grounded_claims(
        grounded_claims,
        allowed_claim_ids=allowed_claim_ids,
    )

    # Emergency and insufficient-evidence turns are release policies, not model
    # writing styles. Never let arbitrary model prose decide whether or when the
    # user should seek urgent care.
    if normalized_risk == "emergency":
        reasons.append("emergency_safe_fallback_required")
        return HealthAnswerVerification(
            verdict="block",
            text=_safe_fallback_text(
                risk_level=risk_level,
                sufficiency=sufficiency,
                missing_discriminators=missing,
            ),
            reasons=tuple(dict.fromkeys(reasons)),
            evidence_refs_used=_urgent_grounding_ids(grounded),
        )
    if normalized_sufficiency == "safe_fallback":
        reasons.append("insufficient_evidence_safe_fallback_required")
        return HealthAnswerVerification(
            verdict="block",
            text=_safe_fallback_text(
                risk_level=risk_level,
                sufficiency=sufficiency,
                missing_discriminators=missing,
            ),
            reasons=tuple(dict.fromkeys(reasons)),
        )

    if reasons:
        return HealthAnswerVerification(
            verdict="block",
            text=_safe_fallback_text(
                risk_level=risk_level,
                sufficiency=sufficiency,
                missing_discriminators=missing,
            ),
            reasons=tuple(dict.fromkeys(reasons)),
            evidence_refs_used=_urgent_grounding_ids(grounded),
        )

    if normalized_sufficiency == "clarify":
        return HealthAnswerVerification(
            verdict="repair",
            text=_clarification_text(missing),
            reasons=("clarification_safe_render_required",),
            evidence_refs_used=_urgent_grounding_ids(grounded),
        )

    if normalized_sufficiency != "sufficient":
        return HealthAnswerVerification(
            verdict="block",
            text=_safe_fallback_text(
                risk_level=risk_level,
                sufficiency="safe_fallback",
                missing_discriminators=missing,
            ),
            reasons=("unknown_sufficiency",),
        )
    if not grounded:
        return HealthAnswerVerification(
            verdict="block",
            text=_safe_fallback_text(
                risk_level=risk_level,
                sufficiency="safe_fallback",
                missing_discriminators=missing,
            ),
            reasons=("missing_grounded_claims",),
        )

    referenced = _referenced_allowed_claim_ids(candidate, grounded)
    selected_ids = referenced or tuple(grounded)
    rendered = _grounded_answer_text(
        tuple((claim_id, grounded[claim_id]) for claim_id in selected_ids)
    )
    if _normalized_text(candidate) == _normalized_text(rendered):
        return HealthAnswerVerification(
            verdict="pass",
            text=rendered,
            evidence_refs_used=selected_ids,
        )
    return HealthAnswerVerification(
        verdict="repair",
        text=rendered,
        reasons=("grounded_claim_render_required",),
        evidence_refs_used=selected_ids,
    )


def _has_diagnostic_overclaim(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in _UNCONDITIONAL_OVERCLAIMS):
        return True
    for marker in _DIAGNOSTIC_MARKERS:
        start = 0
        while (index := lowered.find(marker, start)) >= 0:
            prefix = lowered[max(0, index - 8):index]
            if not any(prefix.endswith(negation) for negation in _DIAGNOSTIC_NEGATIONS):
                return True
            start = index + len(marker)
    return False


def _has_self_medication_change(text: str) -> bool:
    lowered = text.lower()
    if not any(marker in lowered for marker in _MEDICATION_CONTEXT):
        return False
    candidate = SimpleNamespace(domain="medication")
    return _has_unreviewed_medication_change(
        candidate,
        title="",
        body=text,
    )


def _has_medication_prescribing(text: str) -> bool:
    """Detect a new medication start or concrete regimen in model-authored text."""

    lowered = text.lower()
    for clause in _MEDICATION_CLAUSE_SPLIT_RE.split(lowered):
        clause = clause.strip()
        if not clause or not any(marker in clause for marker in _MEDICATION_CONTEXT):
            continue
        if _MEDICATION_PROHIBITION_RE.search(clause):
            continue
        if (
            _MEDICATION_EXISTING_PLAN_BOUNDARY_RE.search(clause)
            and not _MEDICATION_START_OR_ADMIN_RE.search(clause)
        ):
            continue
        direct_start = _MEDICATION_START_OR_ADMIN_RE.search(clause) is not None
        concrete_regimen = (
            _MEDICATION_RECOMMEND_RE.search(clause) is not None
            and (
                _MEDICATION_DOSE_RE.search(clause) is not None
                or _MEDICATION_FREQUENCY_RE.search(clause) is not None
            )
        )
        if direct_start or concrete_regimen:
            return True
    return False


def _downgrades_red_flags(text: str, *, risk_level: str) -> bool:
    lowered = text.lower()
    downgrade = any(marker in lowered for marker in _RED_FLAG_DOWNGRADES)
    if not downgrade:
        return False
    return str(risk_level).lower() in {"high", "emergency"} or any(
        marker in lowered for marker in _RED_FLAG_TERMS
    )


def _unsupported_claim_refs(
    text: str,
    allowed_claim_ids: Collection[str],
) -> bool:
    allowed = {str(item).lower() for item in allowed_claim_ids}
    referenced = {match.group(0).lower() for match in _CLAIM_REF_RE.finditer(text)}
    return bool(referenced - allowed)


def _unsupported_authorities(
    text: str,
    authority_organizations: Collection[str],
) -> bool:
    lowered = text.lower()
    allowed = {
        canonical
        for item in authority_organizations
        if (canonical := _canonical_authority(str(item))) is not None
    }
    mentioned = {
        canonical
        for canonical, full_names in _KNOWN_AUTHORITIES.items()
        if _mentions_authority(
            text,
            lowered=lowered,
            canonical=canonical,
            full_names=full_names,
        )
    }
    return bool(mentioned - allowed)


def _mentions_authority(
    text: str,
    *,
    lowered: str,
    canonical: str,
    full_names: Collection[str],
) -> bool:
    ascii_boundary = r"(?<![A-Za-z0-9]){}(?![A-Za-z0-9])"
    if re.search(ascii_boundary.format(re.escape(canonical)), text):
        return True
    for name in full_names:
        if name.isascii():
            if re.search(
                ascii_boundary.format(re.escape(name)),
                text,
                re.IGNORECASE,
            ):
                return True
        elif name.lower() in lowered:
            return True
    return False


def _canonical_authority(value: str) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    upper = normalized.upper()
    if upper in _KNOWN_AUTHORITIES:
        return upper
    lowered = normalized.lower()
    for canonical, full_names in _KNOWN_AUTHORITIES.items():
        if lowered in {name.lower() for name in full_names}:
            return canonical
    return None


def _claims_unselected_personal_context(
    text: str,
    context_categories: Collection[str],
) -> bool:
    lowered = text.lower()
    selected = {str(item).strip().lower() for item in context_categories}
    return any(
        category not in selected
        and any(marker in lowered for marker in markers)
        for category, markers in _PERSONAL_CONTEXT_MARKERS.items()
    )


def _normalized_grounded_claims(
    grounded_claims: Mapping[str, str] | None,
    *,
    allowed_claim_ids: Collection[str],
) -> dict[str, str]:
    allowed = {str(item).strip().lower() for item in allowed_claim_ids}
    normalized: dict[str, str] = {}
    for raw_id, raw_summary in (grounded_claims or {}).items():
        claim_id = str(raw_id).strip()
        summary = str(raw_summary).strip()
        if claim_id.lower() in allowed and summary:
            normalized[claim_id] = summary
    return normalized


def _referenced_allowed_claim_ids(
    text: str,
    grounded_claims: Mapping[str, str],
) -> tuple[str, ...]:
    canonical = {claim_id.lower(): claim_id for claim_id in grounded_claims}
    selected: list[str] = []
    for match in _CLAIM_REF_RE.finditer(text):
        claim_id = canonical.get(match.group(0).lower())
        if claim_id and claim_id not in selected:
            selected.append(claim_id)
    return tuple(selected)


def _urgent_grounding_ids(
    grounded_claims: Mapping[str, str],
) -> tuple[str, ...]:
    urgent_markers = ("emergency", "neurologic", "red_flag", "serious_cause")
    return tuple(
        claim_id
        for claim_id in grounded_claims
        if any(marker in claim_id.lower() for marker in urgent_markers)
    )


def _clarification_text(
    missing_discriminators: tuple[Mapping[str, Any], ...],
) -> str:
    questions = [
        str(item.get("question") or "").strip()
        for item in missing_discriminators
        if str(item.get("question") or "").strip()
    ][:4]
    lines = [
        "为了安全分流，我还不能把未提及的症状当作“没有”。",
        (
            "如果已有排尿困难、大小便失控、会阴或肛周麻木，或双腿明显无力，"
            "请立即前往急诊。这是安全分流，不是诊断。"
        ),
    ]
    if questions:
        lines.append("")
        lines.append("请先确认：")
    lines.extend(f"- {question}" for question in questions)
    lines.extend(
        (
            "",
            "这些关键信息明确前，我不会给出具体训练、影像或用药方案。",
        )
    )
    return "\n".join(lines)


def _grounded_answer_text(
    claims: tuple[tuple[str, str], ...],
) -> str:
    lines = [
        "基于本轮已确认的信息，下面只列出通过适用性审查的健康管理边界：",
    ]
    lines.extend(
        f"- {summary} [{claim_id}]"
        for claim_id, summary in claims
    )
    lines.extend(
        (
            "",
            (
                "这些内容不是诊断或处方；如果症状持续、加重或出现新的警示征象，"
                "请及时就医评估。不要据此自行开始、停用或调整药物。"
            ),
        )
    )
    return "\n".join(lines)


def _normalized_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip()


def _safe_fallback_text(
    *,
    risk_level: str,
    sufficiency: str,
    missing_discriminators: tuple[Mapping[str, Any], ...],
) -> str:
    if str(risk_level).lower() == "emergency":
        return (
            "你描述的情况包含需要立即处理的急症警示征象。"
            "请现在前往急诊或联系当地急救服务；不要自行继续拉伸、训练，"
            "也不要自行停药或加量。这是安全分流，不是诊断。"
        )
    if str(risk_level).lower() == "high":
        return (
            "本轮已发现需要尽快就医评估的警示线索，请尽快就医。"
            "如果刚发生严重外伤或车祸、伴有高热或严重感染，"
            "或症状正在快速加重，请现在前往急诊或联系当地急救服务。"
            "在完成评估前不要自行训练，也不要自行开始、停用或调整药物。"
            "这是安全分流，不是诊断。"
        )
    questions = [
        str(item.get("question") or "").strip()
        for item in missing_discriminators
        if str(item.get("question") or "").strip()
    ][:4]
    parts = [
        "原回答未通过健康安全校验，我先给出保守边界："
        "如有排尿困难、大小便失控、会阴或肛周麻木、双腿明显无力，"
        "请立即前往急诊。这是安全分流，不是诊断，也不能据此自行调整用药。"
    ]
    if str(sufficiency).lower() == "safe_fallback":
        parts.append("本轮权威证据或关键上下文不足，暂不提供具体治疗建议。")
    if questions:
        parts.append("请补充：" + "；".join(questions) + "。")
    return "\n\n".join(parts)
