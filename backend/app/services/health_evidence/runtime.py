"""One turn-scoped, backend-owned health evidence runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
import re
from typing import Any, Mapping, Sequence

from sqlalchemy.orm import Session

from app.twin.schema import HealthTwin, TwinMeta

from .authority import AuthorityBundle, route_authority_results
from .contracts import (
    HealthIntentEnvelope,
    PersonalEvidencePacket,
    RiskLevel,
    SafetyProfileContext,
)
from .personal_context import compile_personal_context
from .intent import (
    affirmed_low_back_discriminator_ids,
    has_unilateral_progressive_neurologic_red_flag,
    infer_low_back_population,
)
from .verifier import HealthAnswerVerification, verify_health_answer


logger = logging.getLogger(__name__)

_LOW_BACK_DISCRIMINATORS: dict[str, dict[str, Any]] = {
    "low_back.cauda_equina": {
        "id": "low_back.cauda_equina",
        "question": "是否有排尿困难、大小便失控，或会阴/肛周麻木？",
        "label": "确认膀胱、肠道及会阴感觉是否有新变化",
        "choices": ["有", "没有", "不确定"],
        "priority": "emergency",
        "is_red_flag": True,
    },
    "low_back.progressive_neurologic_deficit": {
        "id": "low_back.progressive_neurologic_deficit",
        "question": "是否有双腿明显或进行性麻木、无力？",
        "label": "确认是否存在进行性下肢神经症状",
        "choices": ["有", "没有", "不确定"],
        "priority": "emergency",
        "is_red_flag": True,
    },
    "low_back.major_trauma": {
        "id": "low_back.major_trauma",
        "question": "近期是否有车祸、高处跌落或其他严重外伤？",
        "label": "确认近期是否有严重外伤",
        "choices": ["有", "没有", "不确定"],
        "priority": "urgent",
        "is_red_flag": True,
    },
    "low_back.systemic_red_flag": {
        "id": "low_back.systemic_red_flag",
        "question": "是否伴发热、不明原因体重下降，或有癌症/严重感染史？",
        "label": "确认是否存在全身性警示线索",
        "choices": ["有", "没有", "不确定"],
        "priority": "urgent",
        "is_red_flag": True,
    },
}
_LOW_BACK_POPULATION_DISCRIMINATOR = {
    "id": "low_back.population_adult_16_plus",
    "question": "你是否已满 16 岁？",
    "label": "确认本轮成人腰痛证据是否适用",
    "choices": ["有", "没有", "不确定"],
    "priority": "context",
    "is_red_flag": False,
}
_URGENT_LOW_BACK_RED_FLAGS = (
    {
        "id": "low_back.emergency_neurologic_boundary",
        "label": (
            "如有排尿困难、大小便失控、会阴/肛周麻木或双腿明显无力，"
            "请立即前往急诊"
        ),
        "priority": "emergency",
        "is_red_flag": True,
    },
)
_DETECTED_DISCRIMINATOR_LABELS = {
    "low_back.cauda_equina": (
        "已检测到排尿/排便功能或会阴感觉相关警示线索"
    ),
    "low_back.progressive_neurologic_deficit": (
        "已检测到双侧或进行性下肢神经警示线索"
    ),
    "low_back.major_trauma": "已检测到近期严重外伤相关警示线索",
    "low_back.systemic_red_flag": "已检测到全身性严重病因警示线索",
}
_DETECTED_GUARDIAN_LABELS = {
    "symptoms.cauda_equina_warning": (
        "已检测到腰背痛伴严重神经压迫警示组合"
    ),
    "symptoms.acute_cardiac_event": "已检测到急性心脏事件警示组合",
    "symptoms.acute_stroke_fast": "已检测到卒中 FAST 警示组合",
    "symptoms.acute_dyspnea": "已检测到急性呼吸困难警示线索",
    "symptoms.acute_abdomen": "已检测到急腹症或消化道出血警示线索",
    "symptoms.red_flag_persistent_warning": (
        "已检测到需要尽快排查的持续性全身警示线索"
    ),
}
_UNILATERAL_PROGRESSIVE_RED_FLAG = {
    "id": "low_back.unilateral_progressive_neurologic_deficit",
    "label": "已检测到单侧下肢进行性无力相关警示线索",
    "priority": "urgent",
    "is_red_flag": True,
}


@dataclass(frozen=True)
class HealthEvidenceTurn:
    intent: HealthIntentEnvelope
    personal_packet: PersonalEvidencePacket
    authority_bundle: AuthorityBundle
    sufficiency: str
    missing_discriminators: tuple[dict[str, Any], ...]

    def private_prompt(self) -> str:
        missing_ids = ", ".join(
            str(item.get("id") or "") for item in self.missing_discriminators
        ) or "none"
        return "\n\n".join(
            (
                (
                    "## 健康证据运行时（本段临床约束高于客户端展示指令）\n"
                    f"intent={self.intent.intent_id}; domain={self.intent.domain}; "
                    f"risk={self.intent.risk_level.value}; "
                    f"sufficiency={self.sufficiency}\n"
                    f"missing_discriminators={missing_ids}\n"
                    "先处理紧急警示征象，再讨论保守建议。不得把缺失信息推断为阴性；"
                    "不得诊断、开处方、建议自行停药/换药/加减量。"
                ),
                self.personal_packet.render_private_prompt(),
                self.authority_bundle.to_prompt(),
                (
                    "## 合成契约\n"
                    "- 只可把上列 personal evidence 用作个性化事实；gap 只能表述为未知。\n"
                    "- 医学依据只可来自上列已审定 claim；没有 claim 就不得编造引用。\n"
                    "- sufficiency=clarify 时，先给安全边界，再询问最少的关键判别项。\n"
                    "- sufficiency=safe_fallback 时，不得给具体治疗方案，只给紧急分流或保守兜底。"
                ),
            )
        )

    def public_manifest(
        self,
        *,
        verification: HealthAnswerVerification | None = None,
    ) -> dict[str, Any]:
        personal = self.personal_packet.to_public_manifest().model_dump(mode="json")
        authority = self.authority_bundle.public_manifest()
        authority_refs = list(authority["evidence_refs"])
        sources = list(authority["sources"])
        if verification is not None:
            used = set(verification.evidence_refs_used)
            authority_refs = [
                evidence.doc_id
                for evidence in self.authority_bundle.accepted
                if evidence.doc_id in used
            ]
            sources = _authority_sources_for_refs(
                self.authority_bundle,
                authority_refs,
            )
        personal_refs = [
            *personal["evidence_refs"],
            *personal["safety_signal_refs"],
        ]
        verdict = verification.verdict if verification is not None else "pending"
        return {
            "version": "health-evidence.v1",
            "intent": self.intent.to_public().model_dump(mode="json"),
            "risk_level": self.intent.risk_level.value,
            "sufficiency": self.sufficiency,
            "verifier_verdict": verdict,
            "context_categories_used": list(personal["context_categories_used"]),
            "personal_evidence_refs": personal_refs,
            "authority_evidence_refs": authority_refs,
            "evidence_refs": [*personal_refs, *authority_refs],
            "authority_sources": sources,
            # Mobile's first renderer shipped with ``sources`` as an alias.
            "sources": sources,
            "missing_discriminators": [
                dict(item) for item in self.missing_discriminators
            ],
            # ``urgent_red_flags`` used to contain conditional precautions, which
            # older Mobile clients rendered as already detected findings. Keep the
            # legacy field empty and publish the conditional language explicitly.
            "urgent_red_flags": [],
            "detected_red_flags": _detected_red_flags(
                self.intent,
                self.personal_packet,
            ),
            "safety_precautions": [
                dict(item) for item in _URGENT_LOW_BACK_RED_FLAGS
            ],
            "gaps": list(personal["gaps"]),
            "conflicts": list(personal["conflicts"]),
            "truncated": bool(personal["truncated"]),
            "limitations": [
                "本轮回答不能替代面诊、体格检查、诊断或处方。",
                *(
                    ["权威证据或关键上下文不足，回答已采用安全兜底。"]
                    if self.sufficiency == "safe_fallback"
                    else []
                ),
            ],
        }

    def card_descriptor(
        self,
        *,
        verification: HealthAnswerVerification | None = None,
    ) -> dict[str, Any]:
        return {
            "type": "health_evidence",
            "data": self.public_manifest(verification=verification),
            "actions": [],
        }

    def verify(self, text: str) -> HealthAnswerVerification:
        organizations = {
            source.organization
            for evidence in self.authority_bundle.accepted
            for source in evidence.sources
        }
        return verify_health_answer(
            text,
            risk_level=self.intent.risk_level.value,
            sufficiency=self.sufficiency,
            allowed_claim_ids={
                evidence.doc_id for evidence in self.authority_bundle.accepted
            },
            authority_organizations=organizations,
            context_categories={
                item.category for item in self.personal_packet.evidence
            },
            grounded_claims={
                evidence.doc_id: evidence.summary
                for evidence in self.authority_bundle.accepted
            },
            missing_discriminators=self.missing_discriminators,
        )

    def verifier_failure(self) -> HealthAnswerVerification:
        """Return a deterministic last-resort answer if the verifier itself fails."""

        if self.intent.risk_level == RiskLevel.EMERGENCY:
            text = (
                "本次健康回答未能通过安全校验。你描述的情况包含需要立即排除的"
                "急症警示征象，请现在前往急诊或联系当地急救服务。"
                "不要自行继续拉伸、训练或调整用药。这是安全分流，不是诊断。"
            )
        elif self.intent.risk_level == RiskLevel.HIGH:
            text = (
                "本次健康回答未能通过安全校验。本轮已发现需要尽快就医评估的"
                "警示线索，请尽快就医；如果刚发生严重外伤或车祸、伴有高热或"
                "严重感染，或症状正在快速加重，请现在前往急诊。"
                "不要自行训练或调整用药。这是安全分流，不是诊断。"
            )
        else:
            text = (
                "本次健康回答未能通过安全校验，暂不提供具体治疗建议。"
                "如有排尿困难、大小便失控、会阴或肛周麻木、双腿明显无力，"
                "请立即前往急诊；否则请稍后重试或咨询医生。"
                "这是安全分流，不是诊断。"
            )
        return HealthAnswerVerification(
            verdict="block",
            text=text,
            reasons=("verifier_error",),
        )


def compile_health_evidence_turn(
    *,
    twin: HealthTwin,
    intent: HealthIntentEnvelope,
    authority_results: Sequence[Mapping[str, Any]] | None,
    safety_profile: SafetyProfileContext | None = None,
    now: datetime | None = None,
) -> HealthEvidenceTurn:
    """Pure turn compilation over one frozen Twin and reviewed search candidates."""

    profile = safety_profile or SafetyProfileContext()
    if profile.population is None:
        inferred_population = infer_low_back_population(intent.query)
        if inferred_population is not None:
            profile = profile.model_copy(
                update={"population": inferred_population}
            )
    packet = compile_personal_context(
        twin=twin,
        intent=intent,
        safety_profile=profile,
    )
    effective_intent = _promote_intent_from_safety_signals(intent, packet)
    if effective_intent != intent:
        packet = packet.model_copy(update={"intent": effective_intent})
    bundle = route_authority_results(
        authority_results,
        domain=effective_intent.domain,
        risk_level=effective_intent.risk_level.value,
        population=profile.population,
        use_case=_authority_use_case(effective_intent),
        now=now,
    )
    missing = _missing_discriminators(
        effective_intent,
        personal_packet=packet,
    )
    if (
        profile.population is None
        and effective_intent.risk_level
        not in {RiskLevel.HIGH, RiskLevel.EMERGENCY}
    ):
        missing = (*missing, dict(_LOW_BACK_POPULATION_DISCRIMINATOR))
    only_population_context_missing = bool(
        bundle.rejections
        and all(
            rejection.reason == "missing_population_context"
            for rejection in bundle.rejections
        )
    )
    if effective_intent.risk_level in {
        RiskLevel.HIGH,
        RiskLevel.EMERGENCY,
    }:
        sufficiency = "safe_fallback"
    elif not bundle.accepted and not only_population_context_missing:
        sufficiency = "safe_fallback"
    elif missing:
        sufficiency = "clarify"
    else:
        sufficiency = "sufficient"
    return HealthEvidenceTurn(
        intent=effective_intent,
        personal_packet=packet,
        authority_bundle=bundle,
        sufficiency=sufficiency,
        missing_discriminators=missing,
    )


def _authority_use_case(intent: HealthIntentEnvelope) -> str:
    if intent.domain != "low_back_pain":
        return "initial_assessment"
    normalized = "".join(intent.query.lower().split())
    if intent.risk_level == RiskLevel.EMERGENCY:
        return "symptom_triage"
    if _explicit_imaging_decision_context(normalized):
        return "imaging_decision"
    if _explicit_chronic_primary_context(normalized):
        return "chronic_primary_care"
    if _all_low_back_red_flags_explicitly_negative(normalized):
        return "self_management_after_red_flag_screen"
    return "initial_assessment"


def _explicit_imaging_decision_context(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "mri",
            "磁共振",
            "核磁",
            "x光",
            "x线",
            "拍片",
            "影像检查",
            "做ct",
            "查ct",
            "ct检查",
        )
    )


def _authority_sources_for_refs(
    bundle: AuthorityBundle,
    evidence_refs: Sequence[str],
) -> list[dict[str, str]]:
    selected = set(evidence_refs)
    sources: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for evidence in bundle.accepted:
        if evidence.doc_id not in selected:
            continue
        for source in evidence.sources:
            key = (source.source, evidence.authority_tier)
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                source.public_dict(authority_tier=evidence.authority_tier)
            )
    return sources


def _explicit_chronic_primary_context(text: str) -> bool:
    duration_confirmed = any(
        marker in text
        for marker in (
            "超过3个月",
            "持续3个月以上",
            "持续超过3个月",
            "三个月以上",
            "超过三个月",
            "持续半年",
            "半年以上",
        )
    )
    specific_cause_excluded = any(
        marker in text
        for marker in (
            "已排除特异性病因",
            "已经排除特异性病因",
            "排除了特异性病因",
            "已排除需要特异处理的病因",
            "医生已排除严重病因",
            "医生已经排除严重病因",
        )
    )
    return duration_confirmed and specific_cause_excluded


def _all_low_back_red_flags_explicitly_negative(text: str) -> bool:
    return _explicitly_negative_discriminator_ids(text) == set(
        _LOW_BACK_DISCRIMINATORS
    )


def _explicitly_negative_discriminator_ids(text: str) -> set[str]:
    negative_ids: set[str] = set()
    bladder_or_bowel = _negated_clause(
        text,
        r"(?:排尿困难|尿失禁|大小便(?:异常|失禁))",
    )
    saddle = _negated_clause(
        text,
        r"(?:会阴|鞍区).{0,5}(?:麻木|感觉异常|感觉减退)",
    )
    progressive_neurologic = _negated_clause(
        text,
        r"(?:双腿|两腿|双下肢).{0,6}(?:麻木|无力|乏力)",
    )
    trauma = _negated_clause(
        text,
        r"(?:严重|重大)?(?:外伤|摔倒|跌倒|车祸)",
    )
    fever_or_infection = _negated_clause(
        text,
        r"(?:发热|高热)(?:或|和|及|、)?(?:严重)?感染?",
    ) or (
        _negated_clause(text, r"(?:发热|高热)")
        and _negated_clause(text, r"(?:严重)?感染")
    )
    weight_loss = _negated_clause(
        text,
        r"(?:不明原因)?(?:体重下降|消瘦|暴瘦)",
    )
    cancer = _negated_clause(text, r"(?:癌症|肿瘤)(?:史)?")
    if bladder_or_bowel and saddle:
        negative_ids.add("low_back.cauda_equina")
    if progressive_neurologic:
        negative_ids.add("low_back.progressive_neurologic_deficit")
    if trauma:
        negative_ids.add("low_back.major_trauma")
    if fever_or_infection and weight_loss and cancer:
        negative_ids.add("low_back.systemic_red_flag")
    return negative_ids


def _negated_clause(text: str, target_pattern: str) -> bool:
    return bool(
        re.search(
            rf"(?:没有|并无|无|未见|未出现|否认|不伴)"
            rf"[^；。！？但]{{0,16}}(?:{target_pattern})",
            text,
        )
    )


def _promote_intent_from_safety_signals(
    intent: HealthIntentEnvelope,
    packet: PersonalEvidencePacket,
) -> HealthIntentEnvelope:
    rank = {
        RiskLevel.LOW: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.HIGH: 2,
        RiskLevel.EMERGENCY: 3,
    }
    risk_level = intent.risk_level
    for signal in packet.safety_signals:
        if rank[signal.risk_level] > rank[risk_level]:
            risk_level = signal.risk_level
    if risk_level == intent.risk_level:
        return intent
    return intent.model_copy(update={"risk_level": risk_level})


def build_health_evidence_turn(
    db: Session,
    *,
    user_id: int,
    query: str,
    intent: HealthIntentEnvelope,
    now: datetime | None = None,
) -> HealthEvidenceTurn:
    """Build one runtime turn using exactly one HealthTwin snapshot."""

    try:
        from app.twin.builder import build_twin

        twin = build_twin(db, user_id, use_cache=True)
    except Exception as exc:  # noqa: BLE001 - fail closed with explicit gaps
        logger.error(
            "[health_evidence] HealthTwin build failed user=%s error_type=%s",
            user_id,
            type(exc).__name__,
        )
        twin = HealthTwin(
            meta=TwinMeta(
                user_id=user_id,
                generated_at=now or datetime.now(UTC),
                failed_partitions=[
                    "acute",
                    "collectors",
                    "medication",
                    "safety_profile",
                    "chronic",
                ],
            )
        )

    profile = SafetyProfileContext()
    try:
        from app.models.user_profile import UserProfile

        row = (
            db.query(UserProfile)
            .filter(UserProfile.user_id == user_id)
            .first()
        )
        allergies = (
            getattr(row, "allergies", None)
            if row is not None
            else None
        )
        age = getattr(row, "age", None) if row is not None else None
        explicit_population = infer_low_back_population(query)
        profile = SafetyProfileContext(
            allergies=tuple(
                str(item).strip()
                for item in (
                    allergies
                    if isinstance(allergies, (list, tuple, set))
                    else ()
                )
                if str(item).strip()
            ),
            population=(
                (
                    "adults_16_plus"
                    if age >= 16
                    else "under_16"
                )
                if isinstance(age, int)
                and not isinstance(age, bool)
                else explicit_population
            )
        )
    except Exception as exc:  # noqa: BLE001 - compiler records missing profile
        logger.warning(
            "[health_evidence] safety profile unavailable user=%s error_type=%s",
            user_id,
            type(exc).__name__,
        )
        twin = _with_failed_partition(twin, "safety_profile")

    results: Sequence[Mapping[str, Any]] = ()
    try:
        from app.services.system_knowledge_service import search_knowledge

        response = search_knowledge(
            db,
            _authority_query(intent, query),
            limit=12,
            doc_type="claim",
        )
        raw_results = response.get("results") if isinstance(response, Mapping) else ()
        if isinstance(raw_results, list):
            results = raw_results
    except Exception as exc:  # noqa: BLE001 - no evidence means safe fallback
        logger.error(
            "[health_evidence] authority search failed user=%s error_type=%s",
            user_id,
            type(exc).__name__,
        )

    return compile_health_evidence_turn(
        twin=twin,
        intent=intent,
        authority_results=results,
        safety_profile=profile,
        now=now,
    )


def _with_failed_partition(
    twin: HealthTwin,
    partition: str,
) -> HealthTwin:
    failed = list(
        dict.fromkeys([*twin.meta.failed_partitions, partition])
    )
    return twin.model_copy(
        update={
            "meta": twin.meta.model_copy(
                update={"failed_partitions": failed}
            )
        }
    )


def _missing_discriminators(
    intent: HealthIntentEnvelope,
    *,
    personal_packet: PersonalEvidencePacket | None = None,
) -> tuple[dict[str, Any], ...]:
    normalized = "".join(intent.query.lower().split())
    known = set()
    known.update(_explicitly_negative_discriminator_ids(normalized))
    known.update(affirmed_low_back_discriminator_ids(intent.query))
    if has_unilateral_progressive_neurologic_red_flag(intent.query):
        known.add("low_back.progressive_neurologic_deficit")
    if personal_packet is not None:
        known.update(
            signal.discriminator_id
            for signal in personal_packet.safety_signals
            if signal.discriminator_id
        )

    return tuple(
        dict(_LOW_BACK_DISCRIMINATORS[discriminator_id])
        for discriminator_id in intent.mandatory_discriminator_ids
        if discriminator_id not in known
        and discriminator_id in _LOW_BACK_DISCRIMINATORS
    )


def _detected_red_flags(
    intent: HealthIntentEnvelope,
    packet: PersonalEvidencePacket,
) -> list[dict[str, Any]]:
    detected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(item_id: str, label: str, priority: str) -> None:
        if item_id in seen:
            return
        seen.add(item_id)
        detected.append(
            {
                "id": item_id,
                "label": label,
                "priority": priority,
                "is_red_flag": True,
            }
        )

    for discriminator_id in sorted(
        affirmed_low_back_discriminator_ids(intent.query)
    ):
        label = _DETECTED_DISCRIMINATOR_LABELS.get(discriminator_id)
        if label:
            add(
                discriminator_id,
                label,
                (
                    "emergency"
                    if discriminator_id
                    in {
                        "low_back.cauda_equina",
                        "low_back.progressive_neurologic_deficit",
                    }
                    else "urgent"
                ),
            )
    if has_unilateral_progressive_neurologic_red_flag(intent.query):
        add(
            str(_UNILATERAL_PROGRESSIVE_RED_FLAG["id"]),
            str(_UNILATERAL_PROGRESSIVE_RED_FLAG["label"]),
            str(_UNILATERAL_PROGRESSIVE_RED_FLAG["priority"]),
        )
    for signal in packet.safety_signals:
        rule_id = str(signal.source_ref or "")
        label = _DETECTED_GUARDIAN_LABELS.get(rule_id)
        if label:
            add(
                (
                    "low_back.cauda_equina"
                    if rule_id == "symptoms.cauda_equina_warning"
                    else f"guardian:{rule_id}"
                ),
                label,
                (
                    "emergency"
                    if signal.risk_level == RiskLevel.EMERGENCY
                    else "urgent"
                ),
            )
    return detected

def _authority_query(intent: HealthIntentEnvelope, query: str) -> str:
    """Return a domain query with no personal values or record identifiers."""

    if intent.domain != "low_back_pain":
        return intent.domain
    terms = [
        "腰痛 下背痛",
        "排尿困难 大小便失禁 会阴麻木 双腿无力 急诊",
        "严重外伤 发热 体重下降 严重病因筛查",
        "继续活动 避免长期卧床 自我管理",
    ]
    normalized = "".join(str(query or "").lower().split())
    if any(marker in normalized for marker in ("拍片", "x光", "ct", "mri", "影像")):
        terms.append("影像检查 非常规 改变管理")
    if any(marker in normalized for marker in ("慢性", "三个月", "3个月", "长期")):
        terms.append("慢性原发性腰痛 整体评估 多模式管理")
    return " ".join(terms)
