"""Deterministic, user-visible citations for medical information in chat.

The model is not trusted to invent or format citations.  This module maps a
bounded set of health topics to reviewed public sources and also projects URLs
already admitted by the health-evidence and system-KB runtimes.  Only HTTPS
links cross the client boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
import re
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit


@dataclass(frozen=True)
class MedicalCitation:
    source_id: str
    title: str
    organization: str
    url: str
    topic: str
    claim_scope: str

    def public_dict(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "organization": self.organization,
            "url": self.url,
            "topic": self.topic,
            "claim_scope": self.claim_scope,
        }


@dataclass(frozen=True)
class MedicalCitationBundle:
    required: bool
    topics: tuple[str, ...]
    citations: tuple[MedicalCitation, ...]

    @property
    def public_citations(self) -> list[dict[str, str]]:
        return [citation.public_dict() for citation in self.citations]


_TOPIC_SOURCES: dict[str, tuple[MedicalCitation, ...]] = {
    "bmi": (
        MedicalCitation(
            source_id="nhc:adult-weight-standard",
            title="中国成人体重判定标准（WS/T 428—2013）",
            organization="国家卫生健康委员会",
            url=(
                "https://www.nhc.gov.cn/ylyjs/zcwj/202412/"
                "75cb79c171c94def9e768193e65484f7/files/"
                "1736390749000_59785.pdf"
            ),
            topic="bmi",
            claim_scope="中国成人（18 岁及以上）BMI 判定：18.5–23.9 为体重正常范围。",
        ),
        MedicalCitation(
            source_id="cdc:adult-bmi-categories",
            title="成人 BMI 计算方法与分类",
            organization="美国疾病控制与预防中心",
            url="https://www.cdc.gov/bmi/adult-calculator/bmi-categories.html",
            topic="bmi",
            claim_scope="BMI 按体重（kg）除以身高（m）的平方计算；BMI 仅是筛查指标。",
        ),
    ),
    "nutrition_energy": (
        MedicalCitation(
            source_id="usda:fooddata-central",
            title="FoodData Central 食物营养数据库",
            organization="美国农业部",
            url="https://fdc.nal.usda.gov/",
            topic="nutrition_energy",
            claim_scope="用于核对食物能量和营养素数据；图片或文字记餐结果仍是份量估算。",
        ),
    ),
    "blood_pressure": (
        MedicalCitation(
            source_id="who:hypertension-fact-sheet",
            title="高血压事实与管理要点",
            organization="世界卫生组织",
            url="https://www.who.int/news-room/fact-sheets/detail/hypertension",
            topic="blood_pressure",
            claim_scope="用于核对成人高血压风险、复测和就医沟通边界。",
        ),
    ),
    "blood_glucose": (
        MedicalCitation(
            source_id="ada:standards-of-care",
            title="糖尿病诊疗标准",
            organization="美国糖尿病协会",
            url="https://professional.diabetes.org/standards-of-care",
            topic="blood_glucose",
            claim_scope="用于核对血糖与糖尿病管理建议；单次读数不能替代临床诊断。",
        ),
    ),
    "lab_results": (
        MedicalCitation(
            source_id="nlm:understand-lab-results",
            title="如何理解化验结果",
            organization="美国国立医学图书馆",
            url="https://medlineplus.gov/lab-tests/how-to-understand-your-lab-results/",
            topic="lab_results",
            claim_scope="参考范围会因实验室、检测方法和人群而异，应优先核对原报告范围。",
        ),
    ),
    "sleep": (
        MedicalCitation(
            source_id="cdc:about-sleep",
            title="睡眠时长、质量与健康",
            organization="美国疾病控制与预防中心",
            url="https://www.cdc.gov/sleep/about/index.html",
            topic="sleep",
            claim_scope="用于核对成人睡眠时长和睡眠健康建议。",
        ),
    ),
    "physical_activity": (
        MedicalCitation(
            source_id="who:physical-activity",
            title="身体活动指南与健康建议",
            organization="世界卫生组织",
            url="https://www.who.int/news-room/fact-sheets/detail/physical-activity",
            topic="physical_activity",
            claim_scope="用于核对成人身体活动建议；个人疾病限制需由专业人员评估。",
        ),
    ),
    "supplement": (
        MedicalCitation(
            source_id="nlm:herbs-and-supplements",
            title="草药与膳食补充剂资料库",
            organization="美国国立医学图书馆",
            url="https://medlineplus.gov/druginfo/herb_All.html",
            topic="supplement",
            claim_scope="用于核对补充剂功效、安全性、推荐摄入量和药物相互作用。",
        ),
    ),
    "medication": (
        MedicalCitation(
            source_id="nlm:dailymed",
            title="DailyMed 药品说明书数据库",
            organization="美国国立医学图书馆",
            url="https://dailymed.nlm.nih.gov/dailymed/",
            topic="medication",
            claim_scope="用于核对 FDA 在用药品标签；用药调整必须由医生或药师确认。",
        ),
    ),
    "general_health": (
        MedicalCitation(
            source_id="nlm:medlineplus-health-topics",
            title="MedlinePlus 健康主题索引",
            organization="美国国立医学图书馆",
            url="https://medlineplus.gov/healthtopics.html",
            topic="general_health",
            claim_scope="用于核对具体症状和疾病主题；不替代医生诊断。",
        ),
    ),
}


_TOPIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "bmi",
        re.compile(
            r"(?<![A-Za-z0-9])BMI(?![A-Za-z0-9])|体质指数|体重指数|"
            r"身高.{0,30}体重|体重.{0,30}身高",
            re.I,
        ),
    ),
    (
        "nutrition_energy",
        re.compile(
            r"热量|卡路里|千卡|kcal|营养|蛋白质|碳水|脂肪|"
            r"基础代谢|\bBMR\b|\bTDEE\b|能量消耗",
            re.I,
        ),
    ),
    ("blood_pressure", re.compile(r"血压|收缩压|舒张压|高血压|低血压", re.I)),
    (
        "blood_glucose",
        re.compile(r"血糖|糖化血红蛋白|HbA1c|糖尿病|胰岛素", re.I),
    ),
    (
        "lab_results",
        re.compile(
            r"化验|检验|体检报告|检查报告|实验室参考范围|化验参考范围|"
            r"转氨酶|胆固醇|甘油三酯|肌酐|尿酸|铁蛋白|白细胞|红细胞",
            re.I,
        ),
    ),
    ("sleep", re.compile(r"睡眠|失眠|入睡|早醒|睡不着|睡多久|深睡|REM", re.I)),
    (
        "physical_activity",
        re.compile(r"运动建议|运动量|锻炼|训练量|有氧|力量训练|步行多久|运动多久", re.I),
    ),
    (
        "supplement",
        re.compile(
            r"补剂|膳食补充剂|维生素|鱼油|镁|褪黑素|叶酸|辅酶|肌酸|"
            r"omega[- ]?3|magnesium|melatonin|vitamin",
            re.I,
        ),
    ),
    (
        "medication",
        re.compile(
            r"用药|药物|药品|处方|剂量|副作用|相互作用|停药|换药|服药|"
            r"吃药|吃什么药",
            re.I,
        ),
    ),
)

_HEALTH_ADVICE_MARKERS = re.compile(
    r"怎么办|怎么处理|怎么改善|怎么缓解|建议|正常吗|是否正常|"
    r"风险|诊断|治疗|病因|原因|为什么|严重吗|要不要就医|看什么科|"
    r"应该|能不能|可以吃|可以用|解读|解释|分析|计算|帮我算|估算",
    re.I,
)
_GENERAL_HEALTH_MARKERS = re.compile(
    r"疼|痛|发热|发烧|咳嗽|头晕|恶心|呕吐|腹泻|皮疹|过敏|"
    r"感冒|口腔溃疡|便秘|鼻炎|哮喘|"
    r"症状|疾病|感染|炎症|肿瘤|癌|心脏|肝|肾|肺|胃|肠|"
    r"健康|医学|医生|医院|急诊",
    re.I,
)

_KNOWN_EXTERNAL_SOURCES: dict[str, MedicalCitation] = {
    "guideline:ada-standards-of-care-diabetes-2026": _TOPIC_SOURCES["blood_glucose"][0],
    "guideline:acc-aha-cholesterol-management": MedicalCitation(
        source_id="guideline:acc-aha-cholesterol-management",
        title="胆固醇临床管理指南",
        organization="美国心脏协会 / 美国心脏病学会",
        url="https://professional.heart.org/en/guidelines-and-statements",
        topic="cardiovascular",
        claim_scope="用于核对血脂风险沟通与医生决策边界。",
    ),
}


def _safe_https_url(value: Any) -> str | None:
    url = str(value or "").strip()
    if not url:
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
    ):
        return None
    try:
        if not ip_address(hostname).is_global:
            return None
    except ValueError:
        pass
    return url


def _source_id_citation(source_id: Any, *, title: str = "") -> MedicalCitation | None:
    normalized = str(source_id or "").strip()
    if not normalized:
        return None
    known = _KNOWN_EXTERNAL_SOURCES.get(normalized)
    if known is not None:
        return known
    if normalized.startswith("pubmed:"):
        pubmed_id = normalized.removeprefix("pubmed:").strip()
        if pubmed_id.isdigit():
            return MedicalCitation(
                source_id=normalized,
                title=title.strip() or f"PubMed 文献 {pubmed_id}",
                organization="美国国立医学图书馆",
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/",
                topic="clinical_research",
                claim_scope="用于核对本轮系统知识条目的外部研究依据。",
            )
    try:
        from app.services.supplement_evidence import SUPPLEMENT_EVIDENCE_SOURCES

        profile = SUPPLEMENT_EVIDENCE_SOURCES.get(normalized)
        if profile is not None:
            return MedicalCitation(
                source_id=profile.source_id,
                title=profile.title,
                organization="权威健康机构",
                url=profile.url,
                topic="supplement",
                claim_scope="用于核对本轮补充剂信息与安全边界。",
            )
    except (ImportError, AttributeError):
        return None
    return None


def _external_source_citation(
    source: Mapping[str, Any],
    *,
    topic: str,
    fallback_title: str,
    fallback_scope: str,
) -> MedicalCitation | None:
    source_id = str(source.get("source_id") or source.get("source") or "").strip()
    url = _safe_https_url(source.get("url") or source.get("source"))
    known = _source_id_citation(source_id, title=fallback_title)
    if url is None and known is not None:
        return known
    if url is None:
        return None
    title = str(source.get("title") or fallback_title or "权威医学来源").strip()
    organization = str(source.get("organization") or "权威健康机构").strip()
    return MedicalCitation(
        source_id=source_id or url,
        title=title,
        organization=organization,
        url=url,
        topic=topic,
        claim_scope=str(source.get("claim_scope") or fallback_scope).strip(),
    )


def _manifest_citations(manifest: Mapping[str, Any] | None) -> Iterable[MedicalCitation]:
    for source in (manifest or {}).get("authority_sources") or []:
        if not isinstance(source, Mapping):
            continue
        citation = _external_source_citation(
            source,
            topic="health_evidence",
            fallback_title=str(source.get("title") or "权威医学指南"),
            fallback_scope="用于核对本轮健康建议中的风险分流和行动边界。",
        )
        if citation is not None:
            yield citation


def _system_card_citations(card: Mapping[str, Any] | None) -> Iterable[MedicalCitation]:
    data = (card or {}).get("data") or {}
    if not isinstance(data, Mapping):
        return
    for claim in data.get("claims") or []:
        if not isinstance(claim, Mapping):
            continue
        claim_title = str(claim.get("title") or "系统知识条目").strip()
        metadata = claim.get("metadata") or {}
        external_sources = (
            metadata.get("external_sources")
            if isinstance(metadata, Mapping)
            else []
        )
        resolved_ids: set[str] = set()
        for source in external_sources or []:
            if not isinstance(source, Mapping):
                continue
            citation = _external_source_citation(
                source,
                topic="system_knowledge",
                fallback_title=claim_title,
                fallback_scope="用于核对本轮系统知识条目的外部依据。",
            )
            if citation is not None:
                resolved_ids.add(citation.source_id)
                yield citation
        for source_id in claim.get("sources") or []:
            citation = _source_id_citation(source_id, title=claim_title)
            if citation is not None and citation.source_id not in resolved_ids:
                yield citation


def _detect_topics(text: str) -> tuple[str, ...]:
    return tuple(
        topic
        for topic, pattern in _TOPIC_PATTERNS
        if pattern.search(text)
    )


def _looks_like_general_health_advice(text: str) -> bool:
    return bool(
        _GENERAL_HEALTH_MARKERS.search(text)
        and _HEALTH_ADVICE_MARKERS.search(text)
    )


def _dedupe(citations: Iterable[MedicalCitation], *, limit: int = 4) -> tuple[MedicalCitation, ...]:
    output: list[MedicalCitation] = []
    seen_urls: set[str] = set()
    for citation in citations:
        url = _safe_https_url(citation.url)
        if url is None or url in seen_urls:
            continue
        seen_urls.add(url)
        output.append(citation)
        if len(output) >= limit:
            break
    return tuple(output)


def build_medical_citation_bundle(
    message: str,
    *,
    answer_text: str = "",
    health_evidence_manifest: Mapping[str, Any] | None = None,
    system_evidence_card: Mapping[str, Any] | None = None,
) -> MedicalCitationBundle:
    """Build the citation contract for one assistant turn.

    Request text controls prompt grounding.  Final answer text is considered at
    terminal time so deterministic cards/calculations cannot silently bypass
    the same citation UI.
    """

    combined = f"{message or ''}\n{answer_text or ''}".strip()
    topics = list(_detect_topics(combined))
    evidence = [
        *_manifest_citations(health_evidence_manifest),
        *_system_card_citations(system_evidence_card),
    ]
    if _looks_like_general_health_advice(combined) and "general_health" not in topics:
        topics.append("general_health")
    if not topics and evidence:
        topics.append("health_evidence")

    required = bool(topics)
    citations: list[MedicalCitation] = []
    for topic in topics:
        citations.extend(_TOPIC_SOURCES.get(topic, ()))
    citations.extend(evidence)
    if required and not citations:
        topics = ["general_health"]
        citations.extend(_TOPIC_SOURCES["general_health"])

    return MedicalCitationBundle(
        required=required,
        topics=tuple(topics),
        citations=_dedupe(citations),
    )


def render_medical_citation_prompt(bundle: MedicalCitationBundle) -> str:
    if not bundle.required or not bundle.citations:
        return ""
    lines = [
        "## 本轮医学引用（强制）",
        "客户端会在回答下方直接展示以下可点击来源。回答中的公式、范围、风险或建议只能在这些来源支持的范围内表达；不要编造其他来源。",
    ]
    for citation in bundle.citations:
        lines.append(
            f"- {citation.organization}《{citation.title}》：{citation.claim_scope} "
            f"({citation.url})"
        )
    if "bmi" in bundle.topics:
        lines.append(
            "必须说明 BMI 是筛查指标，不是诊断；做医疗决定前请咨询医生。"
        )
    else:
        lines.append(
            "必须说明这些信息用于健康管理，不替代诊断；做医疗决定前请咨询医生。"
        )
    return "\n".join(lines)
