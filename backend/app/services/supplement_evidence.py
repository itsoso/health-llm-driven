"""Structured evidence and safety checks for supplement advice.

This module is the runtime adapter between free-form recommendation text and
reviewed evidence claims.  The seed catalog is intentionally small and
conservative; later it can be generated from the system KB / LLM Wiki compiler.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Iterable


SUPPLEMENT_EVIDENCE_CATALOG_VERSION = "supplement_evidence_mvp_v1"


@dataclass(frozen=True)
class SupplementEvidenceProfile:
    key: str
    display_name: str
    aliases: tuple[str, ...]
    evidence_level: str
    evidence_summary: str
    standard_dose: str
    timing: str
    sources: tuple[str, ...]
    requires_labs: tuple[str, ...] = ()
    contraindications: tuple[str, ...] = ()
    interactions: tuple[str, ...] = ()
    verification_metrics: tuple[str, ...] = ()
    upper_limit: float | None = None
    upper_limit_unit: str | None = None


@dataclass(frozen=True)
class EvidenceSourceProfile:
    source_id: str
    title: str
    source_type: str
    authority_level: str
    evidence_rank: int
    url: str
    license_scope: str = "public_reference"
    review_status: str = "reviewed"
    notes: str = ""


@dataclass(frozen=True)
class SupplementSafetyContext:
    medications: tuple[str, ...] = ()
    chronic_conditions: tuple[str, ...] = ()
    allergies: tuple[str, ...] = ()
    labs: dict[str, float] = field(default_factory=dict)
    data_warnings: tuple[str, ...] = ()

    @classmethod
    def from_profile(
        cls,
        profile: Any | None,
        *,
        labs: dict[str, float] | None = None,
        data_warnings: tuple[str, ...] = (),
    ) -> "SupplementSafetyContext":
        if profile is None:
            return cls(labs=dict(labs or {}), data_warnings=data_warnings)
        return cls(
            medications=tuple(_extract_names(getattr(profile, "current_medications", None))),
            chronic_conditions=tuple(_as_text_list(getattr(profile, "chronic_conditions", None))),
            allergies=tuple(_as_text_list(getattr(profile, "allergies", None))),
            labs=dict(labs or {}),
            data_warnings=data_warnings,
        )


SUPPLEMENT_EVIDENCE_SOURCES: dict[str, EvidenceSourceProfile] = {
    "nih_ods:vitamin-d": EvidenceSourceProfile(
        source_id="nih_ods:vitamin-d",
        title="NIH Office of Dietary Supplements: Vitamin D Fact Sheet for Health Professionals",
        source_type="government_fact_sheet",
        authority_level="high",
        evidence_rank=1,
        url="https://ods.od.nih.gov/factsheets/VitaminD-HealthProfessional/",
        notes="Used for vitamin D status, dosing boundaries, toxicity, and medication interactions.",
    ),
    "guideline:chinese-dris-2023": EvidenceSourceProfile(
        source_id="guideline:chinese-dris-2023",
        title="中国居民膳食营养素参考摄入量（2023版）",
        source_type="national_reference_intake",
        authority_level="high",
        evidence_rank=1,
        url="https://www.cnsoc.org/drpostand/",
        notes="Used for China-context intake ranges and tolerable upper intake boundaries.",
    ),
    "nih_ods:magnesium": EvidenceSourceProfile(
        source_id="nih_ods:magnesium",
        title="NIH Office of Dietary Supplements: Magnesium Fact Sheet for Health Professionals",
        source_type="government_fact_sheet",
        authority_level="high",
        evidence_rank=1,
        url="https://ods.od.nih.gov/factsheets/Magnesium-HealthProfessional/",
        notes="Used for magnesium intake limits, deficiency context, renal cautions, and interactions.",
    ),
    "nih_ods:omega-3": EvidenceSourceProfile(
        source_id="nih_ods:omega-3",
        title="NIH Office of Dietary Supplements: Omega-3 Fatty Acids Fact Sheet for Health Professionals",
        source_type="government_fact_sheet",
        authority_level="high",
        evidence_rank=1,
        url="https://ods.od.nih.gov/factsheets/Omega3FattyAcids-HealthProfessional/",
        notes="Used for EPA/DHA dosing context, triglyceride evidence, and bleeding-risk cautions.",
    ),
    "nih_ods:exercise-performance": EvidenceSourceProfile(
        source_id="nih_ods:exercise-performance",
        title="NIH Office of Dietary Supplements: Dietary Supplements for Exercise and Athletic Performance",
        source_type="government_fact_sheet",
        authority_level="high",
        evidence_rank=2,
        url="https://ods.od.nih.gov/factsheets/ExerciseAndAthleticPerformance-HealthProfessional/",
        notes="Used for exercise-performance supplement evidence and safety boundaries.",
    ),
    "issn:creatine-position-stand": EvidenceSourceProfile(
        source_id="issn:creatine-position-stand",
        title="International Society of Sports Nutrition Position Stand: Creatine Supplementation",
        source_type="sports_nutrition_position_stand",
        authority_level="high",
        evidence_rank=2,
        url="https://jissn.biomedcentral.com/articles/10.1186/s12970-017-0173-z",
        notes="Used for creatine monohydrate efficacy, dosing, and safety framing.",
    ),
    "guideline:acsm-sports-nutrition": EvidenceSourceProfile(
        source_id="guideline:acsm-sports-nutrition",
        title="ACSM/AND/DC Joint Position Statement: Nutrition and Athletic Performance",
        source_type="sports_nutrition_position_statement",
        authority_level="high",
        evidence_rank=2,
        url="https://pubmed.ncbi.nlm.nih.gov/26891166/",
        notes="Used for protein, recovery, and sports-nutrition context.",
    ),
    "issn:protein-exercise": EvidenceSourceProfile(
        source_id="issn:protein-exercise",
        title="International Society of Sports Nutrition Position Stand: Protein and Exercise",
        source_type="sports_nutrition_position_stand",
        authority_level="high",
        evidence_rank=2,
        url="https://jissn.biomedcentral.com/articles/10.1186/s12970-017-0177-8",
        notes="Used for protein supplementation, resistance training, and recovery context.",
    ),
    "nccih:melatonin": EvidenceSourceProfile(
        source_id="nccih:melatonin",
        title="NCCIH: Melatonin, What You Need To Know",
        source_type="government_health_topic",
        authority_level="high",
        evidence_rank=2,
        url="https://www.nccih.nih.gov/health/melatonin-what-you-need-to-know",
        notes="Used for melatonin benefit boundaries, safety cautions, and short-term use framing.",
    ),
    "aasm:sleep-guidance": EvidenceSourceProfile(
        source_id="aasm:sleep-guidance",
        title="American Academy of Sleep Medicine Practice Guidelines",
        source_type="clinical_practice_guideline_index",
        authority_level="high",
        evidence_rank=2,
        url="https://aasm.org/clinical-resources/practice-standards/practice-guidelines/",
        notes="Used for sleep-medicine guideline alignment; specific claims should resolve to topic guidelines later.",
    ),
    "nih_ods:iron": EvidenceSourceProfile(
        source_id="nih_ods:iron",
        title="NIH Office of Dietary Supplements: Iron Fact Sheet for Health Professionals",
        source_type="government_fact_sheet",
        authority_level="high",
        evidence_rank=1,
        url="https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/",
        notes="Used for iron-deficiency testing, supplementation boundaries, and overload cautions.",
    ),
    "nih_ods:vitamin-k": EvidenceSourceProfile(
        source_id="nih_ods:vitamin-k",
        title="NIH Office of Dietary Supplements: Vitamin K Fact Sheet for Health Professionals",
        source_type="government_fact_sheet",
        authority_level="high",
        evidence_rank=1,
        url="https://ods.od.nih.gov/factsheets/VitaminK/",
        notes="Used for vitamin K forms, bone-health context, and anticoagulant interactions.",
    ),
    "nih_ods:b-vitamins": EvidenceSourceProfile(
        source_id="nih_ods:b-vitamins",
        title="NIH Office of Dietary Supplements: Vitamin B Fact Sheets",
        source_type="government_fact_sheet_collection",
        authority_level="high",
        evidence_rank=2,
        url="https://ods.od.nih.gov/factsheets/list-all/",
        notes="B-complex advice should resolve to nutrient-specific B6, B12, folate, and related pages in the compiler.",
    ),
}


SUPPLEMENT_EVIDENCE_CATALOG: dict[str, SupplementEvidenceProfile] = {
    "vitamin_d": SupplementEvidenceProfile(
        key="vitamin_d",
        display_name="维生素 D3",
        aliases=("维生素d", "维生素d3", "vitamin d", "vitamin d3", "d3"),
        evidence_level="A",
        evidence_summary="用于骨骼健康和维生素 D 缺乏纠正的证据较强；剂量应结合 25(OH)D、血钙和风险因素调整。",
        standard_dose="一般 400-2000 IU/日；缺乏或高风险人群需结合化验调整。",
        timing="随含脂肪餐服用",
        sources=("nih_ods:vitamin-d", "guideline:chinese-dris-2023"),
        requires_labs=("25-OH-D", "血钙"),
        contraindications=("高钙血症", "活动性结节病", "严重肾病需医生评估"),
        verification_metrics=("25-OH-D", "血钙", "肾功能"),
        upper_limit=4000,
        upper_limit_unit="IU",
    ),
    "magnesium": SupplementEvidenceProfile(
        key="magnesium",
        display_name="镁",
        aliases=("镁", "甘氨酸镁", "柠檬酸镁", "苏糖酸镁", "magnesium", "mg-glycinate"),
        evidence_level="C",
        evidence_summary="补镁对缺镁、肌肉紧张和部分睡眠/压力场景可作为辅助；睡眠获益证据有限，安全边界更重要。",
        standard_dose="100-350 mg/日元素镁，从低剂量开始。",
        timing="睡前或晚餐后",
        sources=("nih_ods:magnesium", "guideline:chinese-dris-2023"),
        requires_labs=("肾功能/eGFR",),
        contraindications=("eGFR < 30 时避免自行补镁",),
        interactions=("喹诺酮/四环素类抗生素、甲状腺素需错开 2-4 小时",),
        verification_metrics=("睡眠评分", "入睡时长", "胃肠道反应"),
        upper_limit=350,
        upper_limit_unit="mg",
    ),
    "omega_3": SupplementEvidenceProfile(
        key="omega_3",
        display_name="Omega-3 鱼油",
        aliases=("omega-3", "omega 3", "鱼油", "epa", "dha", "epa+dha"),
        evidence_level="A",
        evidence_summary="降低甘油三酯证据强；一般心血管预防和情绪/抗炎场景需结合剂量、饮食和个人风险解释。",
        standard_dose="一般健康维护 250-500 mg/日 EPA+DHA；高甘油三酯剂量需医生指导。",
        timing="随餐服用",
        sources=("nih_ods:omega-3", "nih_ods:exercise-performance"),
        requires_labs=("甘油三酯", "LDL-C/ApoB"),
        contraindications=("出血风险高或手术前需医生评估",),
        interactions=("华法林、氯吡格雷、阿司匹林等抗凝/抗血小板药需谨慎",),
        verification_metrics=("甘油三酯", "ApoB/LDL-C", "出血倾向"),
        upper_limit=5000,
        upper_limit_unit="mg",
    ),
    "creatine": SupplementEvidenceProfile(
        key="creatine",
        display_name="肌酸一水合物",
        aliases=("肌酸", "creatine", "creatine monohydrate"),
        evidence_level="A",
        evidence_summary="对力量、爆发力和高强度间歇运动表现证据较强；不是兴奋剂，重点是剂量、饮水和肾功能边界。",
        standard_dose="3-5 g/日，无需冲击期也可。",
        timing="每日固定时间；训练日前后均可",
        sources=("issn:creatine-position-stand", "nih_ods:exercise-performance"),
        requires_labs=("肾功能/eGFR",),
        contraindications=("已知严重肾功能异常需医生评估",),
        verification_metrics=("训练容量", "主观恢复", "体重", "肾功能"),
        upper_limit=5,
        upper_limit_unit="g",
    ),
    "protein": SupplementEvidenceProfile(
        key="protein",
        display_name="蛋白粉",
        aliases=("蛋白粉", "乳清", "whey", "protein"),
        evidence_level="A",
        evidence_summary="当饮食蛋白不足或训练恢复需求增加时，蛋白粉只是补足蛋白目标的便利食品。",
        standard_dose="每次 20-30 g；总量按每日蛋白目标分配。",
        timing="训练后或作为加餐",
        sources=("guideline:acsm-sports-nutrition", "issn:protein-exercise"),
        requires_labs=("肾功能/eGFR（肾病人群）",),
        contraindications=("慢性肾病或蛋白限制饮食需医生/营养师指导",),
        verification_metrics=("每日蛋白 g/kg", "训练恢复", "胃肠道耐受"),
    ),
    "melatonin": SupplementEvidenceProfile(
        key="melatonin",
        display_name="褪黑素",
        aliases=("褪黑素", "melatonin"),
        evidence_level="A",
        evidence_summary="对入睡困难和时差调整证据较好；不应替代睡眠节律、光照、咖啡因等基础干预。",
        standard_dose="0.5-3 mg，短期或按需使用，从低剂量开始。",
        timing="睡前 30-60 分钟",
        sources=("nccih:melatonin", "aasm:sleep-guidance"),
        contraindications=("孕期、备孕、癫痫或自身免疫疾病需医生评估",),
        interactions=("镇静药、酒精同用需谨慎",),
        verification_metrics=("入睡时长", "夜醒次数", "次日困倦"),
        upper_limit=3,
        upper_limit_unit="mg",
    ),
    "iron": SupplementEvidenceProfile(
        key="iron",
        display_name="铁剂",
        aliases=("铁剂", "补铁", "iron", "ferrous"),
        evidence_level="A",
        evidence_summary="补铁应以铁蛋白、转铁蛋白饱和度、血红蛋白等指标为依据；不建议无指标常规补铁。",
        standard_dose="缺铁时按化验和医生/营养师建议；常见元素铁 25-36 mg/日。",
        timing="空腹或两餐间，必要时配维 C；与钙、茶咖啡错开。",
        sources=("nih_ods:iron", "guideline:chinese-dris-2023"),
        requires_labs=("铁蛋白", "转铁蛋白饱和度", "血红蛋白"),
        contraindications=("血色病/铁过载", "铁蛋白正常时不建议自行补铁"),
        interactions=("左甲状腺素、部分抗生素、钙剂需错开",),
        verification_metrics=("铁蛋白", "血红蛋白", "胃肠道反应"),
        upper_limit=45,
        upper_limit_unit="mg",
    ),
    "vitamin_k2": SupplementEvidenceProfile(
        key="vitamin_k2",
        display_name="维生素 K2",
        aliases=("维生素k2", "k2", "mk-7", "mk7", "vitamin k2"),
        evidence_level="B",
        evidence_summary="常作为维生素 D/骨健康方案的协同项，但抗凝药使用者必须优先处理相互作用。",
        standard_dose="90-180 μg/日。",
        timing="随含脂肪餐服用",
        sources=("nih_ods:vitamin-k", "guideline:chinese-dris-2023"),
        contraindications=("正在使用华法林等维生素 K 拮抗剂时避免自行使用",),
        interactions=("华法林",),
        verification_metrics=("抗凝 INR 稳定性（如适用）",),
        upper_limit=180,
        upper_limit_unit="μg",
    ),
    "b_complex": SupplementEvidenceProfile(
        key="b_complex",
        display_name="B 族维生素",
        aliases=("维生素b", "b族", "b-complex", "b complex", "复合维生素b"),
        evidence_level="B",
        evidence_summary="适合饮食不足、素食、二甲双胍使用者或明确 B 族缺乏风险；不要把压力疲劳简单归因为缺 B。",
        standard_dose="按产品建议，避免长期高剂量 B6。",
        timing="早餐后",
        sources=("nih_ods:b-vitamins", "guideline:chinese-dris-2023"),
        requires_labs=("B12", "叶酸", "同型半胱氨酸（按需）"),
        interactions=("左旋多巴等药物需专业评估",),
        verification_metrics=("B12/叶酸", "同型半胱氨酸", "症状变化"),
    ),
}


def enrich_supplement_recommendations(
    recommendations: list[dict[str, Any]],
    context: SupplementSafetyContext | None = None,
) -> dict[str, Any]:
    """Attach evidence and safety metadata to recommendation dictionaries."""

    context = context or SupplementSafetyContext()
    summary = {
        "catalog_version": SUPPLEMENT_EVIDENCE_CATALOG_VERSION,
        "total": len(recommendations),
        "matched": 0,
        "blocked": 0,
        "warnings": [],
        "unsupported": [],
        "safety_context_warnings": list(context.data_warnings),
    }

    for rec in recommendations:
        key = resolve_supplement_key(str(rec.get("name") or ""))
        if not key:
            rec["support_status"] = "unmapped"
            rec["evidence_profile"] = None
            summary["unsupported"].append(rec.get("name"))
            continue

        profile = SUPPLEMENT_EVIDENCE_CATALOG[key]
        safety = _evaluate_safety(profile, rec, context)
        rec["evidence_profile"] = _profile_payload(profile)
        rec["evidence_refs"] = list(profile.sources)
        rec["support_status"] = "blocked" if safety["blocked"] else "supported"
        rec["safety_review"] = safety
        rec["requires_labs"] = list(profile.requires_labs)
        rec["verification_metrics"] = list(profile.verification_metrics)

        summary["matched"] += 1
        if safety["blocked"]:
            summary["blocked"] += 1
        for warning in safety["warnings"]:
            summary["warnings"].append({
                "supplement": profile.display_name,
                "message": warning,
            })

    return summary


def list_supplement_evidence_catalog(include_sources: bool = True) -> list[dict[str, Any]]:
    """Return reviewed supplement evidence profiles for API/runtime inspection."""

    items: list[dict[str, Any]] = []
    for profile in sorted(SUPPLEMENT_EVIDENCE_CATALOG.values(), key=lambda item: item.key):
        payload = _profile_payload(profile)
        if include_sources:
            payload["source_details"] = _source_details(profile.sources)
            unresolved = [source_id for source_id in profile.sources if source_id not in SUPPLEMENT_EVIDENCE_SOURCES]
            if unresolved:
                payload["unresolved_sources"] = unresolved
        items.append(payload)
    return items


def list_supplement_evidence_sources() -> list[dict[str, Any]]:
    """Return source metadata only; no raw source text is stored in this registry."""

    return [
        _source_payload(source)
        for source in sorted(
            SUPPLEMENT_EVIDENCE_SOURCES.values(),
            key=lambda item: (item.evidence_rank, item.source_id),
        )
    ]


def get_supplement_evidence_profile(name_or_key: str) -> dict[str, Any] | None:
    key = _resolve_profile_key(name_or_key)
    if not key:
        return None
    profile = SUPPLEMENT_EVIDENCE_CATALOG[key]
    payload = _profile_payload(profile)
    payload["source_details"] = _source_details(profile.sources)
    unresolved = [source_id for source_id in profile.sources if source_id not in SUPPLEMENT_EVIDENCE_SOURCES]
    if unresolved:
        payload["unresolved_sources"] = unresolved
    return payload


def get_unresolved_supplement_source_ids() -> list[str]:
    referenced = {
        source_id
        for profile in SUPPLEMENT_EVIDENCE_CATALOG.values()
        for source_id in profile.sources
    }
    return sorted(referenced - set(SUPPLEMENT_EVIDENCE_SOURCES))


def evidence_warnings_to_precautions(summary: dict[str, Any], limit: int = 4) -> list[str]:
    """Render safety warnings into short user-facing precaution lines."""

    lines: list[str] = []
    if "lab_fetch_failed" in (summary.get("safety_context_warnings") or []):
        lines.append("⚠️ 近期化验数据暂不可用；涉及肾功能、铁蛋白、维生素 D 等边界时先核对化验。")
    if summary.get("blocked"):
        lines.append("🚫 有补剂建议命中硬性安全边界，标记为 blocked 的项目不要自行开始。")
    for item in (summary.get("warnings") or [])[:limit]:
        supplement = item.get("supplement") or "补剂"
        message = item.get("message") or ""
        if message:
            lines.append(f"⚠️ {supplement}: {message}")
    return lines


def resolve_supplement_key(name: str) -> str | None:
    return _resolve_profile_key(name)


def _resolve_profile_key(name: str) -> str | None:
    normalized = _normalize_text(name)
    if not normalized:
        return None
    for key, profile in SUPPLEMENT_EVIDENCE_CATALOG.items():
        if normalized in {_normalize_text(key), _normalize_text(profile.display_name)}:
            return key
    for key, profile in SUPPLEMENT_EVIDENCE_CATALOG.items():
        if any(_normalize_text(alias) in normalized for alias in profile.aliases):
            return key
    return None


def _source_details(source_ids: Iterable[str]) -> list[dict[str, Any]]:
    return [
        _source_payload(SUPPLEMENT_EVIDENCE_SOURCES[source_id])
        for source_id in source_ids
        if source_id in SUPPLEMENT_EVIDENCE_SOURCES
    ]


def _source_payload(source: EvidenceSourceProfile) -> dict[str, Any]:
    return asdict(source)


def _profile_payload(profile: SupplementEvidenceProfile) -> dict[str, Any]:
    payload = asdict(profile)
    payload["aliases"] = list(profile.aliases)
    payload["sources"] = list(profile.sources)
    payload["requires_labs"] = list(profile.requires_labs)
    payload["contraindications"] = list(profile.contraindications)
    payload["interactions"] = list(profile.interactions)
    payload["verification_metrics"] = list(profile.verification_metrics)
    return payload


def _evaluate_safety(
    profile: SupplementEvidenceProfile,
    recommendation: dict[str, Any],
    context: SupplementSafetyContext,
) -> dict[str, Any]:
    warnings: list[str] = []
    blockers: list[str] = []

    med_text = " ".join(context.medications).lower()
    condition_text = " ".join(context.chronic_conditions).lower()

    if profile.key == "vitamin_k2" and _has_any(med_text, ("华法林", "warfarin")):
        blockers.append("正在使用华法林时不应自行添加维生素 K2，需由医生管理 INR 和抗凝方案。")

    if profile.key == "omega_3" and _has_any(
        med_text, ("华法林", "warfarin", "氯吡格雷", "clopidogrel", "阿司匹林", "aspirin")
    ):
        warnings.append("正在使用抗凝/抗血小板药时，Omega-3 尤其是高剂量应先和医生确认出血风险。")

    egfr = _get_lab(context.labs, "egfr")
    if profile.key in {"magnesium", "creatine", "protein"}:
        if egfr is not None and egfr < 30:
            message = f"最近 eGFR={egfr:g}，肾功能明显下降时不建议自行使用或加量 {profile.display_name}。"
            if profile.key == "magnesium":
                blockers.append(message)
            else:
                warnings.append(message)
        elif _has_any(condition_text, ("肾病", "肾功能", "肾衰", "ckd", "kidney")):
            warnings.append(f"有肾脏相关病史时，{profile.display_name} 建议先核对 eGFR/肌酐。")

    if profile.key == "iron":
        ferritin = _get_lab(context.labs, "ferritin")
        if _has_any(condition_text, ("血色病", "铁过载", "hemochromatosis")):
            blockers.append("血色病或铁过载风险下不应自行补铁。")
        elif ferritin is None:
            warnings.append("补铁前建议先确认铁蛋白、转铁蛋白饱和度和血红蛋白。")
        elif ferritin >= 50:
            warnings.append(f"铁蛋白 {ferritin:g} 不低，补铁必要性不足，需避免铁过载。")

    dose_warning = _check_dose_limit(profile, str(recommendation.get("dosage") or ""))
    if dose_warning:
        warnings.append(dose_warning)

    return {
        "blocked": bool(blockers),
        "blockers": blockers,
        "warnings": warnings,
        "contraindications": list(profile.contraindications),
        "interactions": list(profile.interactions),
    }


def _check_dose_limit(profile: SupplementEvidenceProfile, dosage: str) -> str | None:
    if profile.upper_limit is None or not dosage:
        return None
    value = _extract_largest_number(dosage)
    if value is None:
        return None
    unit = (profile.upper_limit_unit or "").lower()
    text = dosage.lower()
    if unit == "g" and "mg" in text:
        value = value / 1000
    if unit == "mg" and re.search(r"\bg\b", text):
        value = value * 1000
    if unit in {"μg", "mcg"} and "mg" in text:
        value = value * 1000
    if value > profile.upper_limit:
        return (
            f"当前剂量 {dosage} 可能超过 {profile.display_name} 的保守上限 "
            f"{profile.upper_limit:g}{profile.upper_limit_unit or ''}/日，建议复核。"
        )
    return None


def _extract_largest_number(text: str) -> float | None:
    nums = [float(match) for match in re.findall(r"\d+(?:\.\d+)?", text)]
    return max(nums) if nums else None


def _get_lab(labs: dict[str, float], key: str) -> float | None:
    for raw_key, value in labs.items():
        if raw_key.lower() == key.lower() and value is not None:
            return float(value)
    return None


def _has_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle.lower() in text for needle in needles)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def _extract_names(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        names: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                name = item.get("name") or item.get("medication_name")
                if name:
                    names.append(str(name))
            else:
                names.append(str(item))
        return names
    return [str(raw)]


def _as_text_list(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw if item]
    return [str(raw)]
