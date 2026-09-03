"""LLM Wiki evidence retrieval for user-facing advice."""

from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)

SAFE_SUMMARY_FIELDS = ("claim_summary", "reviewed_summary", "summary", "safe_summary")
SOURCE_ID_FIELDS = ("source_id", "claim_id", "doc_id", "id")
URL_FIELDS = ("citation_url", "url", "source_url")
MAX_SAFE_SUMMARY_CHARS = 240


DOMAIN_QUERIES = {
    "nutrition": ("nutrition", "代谢健康 饮食 蛋白质 膳食纤维 血糖 血脂 体重管理"),
    "supplement": ("supplement", "补剂 营养素 剂量 禁忌 相互作用 证据等级"),
    "sleep": ("sleep", "睡眠 恢复 咖啡因 褪黑素 镁"),
    "movement": ("exercise", "运动 训练负荷 恢复 Zone 2 力量训练"),
}

CLAIM_BOUNDARY = (
    "LLM Wiki 只作为饮食/补剂健康管理建议的知识依据，不能替代医生诊断、处方、"
    "药物调整或针对孕产、肾病、肝病等特殊情况的个体化医疗建议。"
)


def _safe_metadata_text(metadata: dict[str, Any], fields: Iterable[str]) -> str:
    for field in fields:
        value = str(metadata.get(field) or "").strip()
        if value:
            return value
    return ""


def _safe_https_url(metadata: dict[str, Any]) -> str:
    for field in URL_FIELDS:
        value = str(metadata.get(field) or "").strip()
        if value.startswith("https://"):
            return value
    return ""


def _get_pipeline():
    from app.services.knowledge.rag_pipeline import RAGPipeline

    return RAGPipeline()


def _source_from_result(result: dict[str, Any]) -> dict[str, Any] | None:
    metadata = result.get("metadata") or {}
    summary = _safe_metadata_text(metadata, SAFE_SUMMARY_FIELDS)
    if not summary:
        return None
    source_id = _safe_metadata_text(metadata, SOURCE_ID_FIELDS)
    return {
        "title": metadata.get("title") or "LLM Wiki",
        "category": metadata.get("category") or "",
        "source_id": source_id or metadata.get("source") or "llm_wiki",
        "source": metadata.get("source") or metadata.get("url") or "llm_wiki",
        "license_scope": metadata.get("license_scope") or "unknown",
        "citation_url": _safe_https_url(metadata),
        "relevance": result.get("relevance_score", 0),
        "summary": summary[:MAX_SAFE_SUMMARY_CHARS],
    }


def _dedupe_sources(results: Iterable[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    sources: list[dict[str, Any]] = []
    for result in results:
        source = _source_from_result(result)
        if not source:
            continue
        key = "|".join([source["source_id"], source["category"], source["summary"][:160]])
        if key in seen or not source["summary"]:
            continue
        seen.add(key)
        sources.append(source)
        if len(sources) >= limit:
            break
    return sources


def _render_prompt_context(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return ""
    lines = ["## LLM Wiki evidence for advice"]
    for idx, source in enumerate(sources, 1):
        citation = f" {source['citation_url']}" if source.get("citation_url") else ""
        lines.append(
            f"{idx}. {source['title']} [{source['category']}] "
            f"(source_id={source['source_id']}, license_scope={source['license_scope']}, "
            f"relevance={float(source['relevance'] or 0):.2f}){citation}: {source['summary']}"
        )
    lines.append(f"Boundary: {CLAIM_BOUNDARY}")
    return "\n".join(lines)


def build_advice_knowledge_context(
    *,
    domains: list[str],
    user_signals: list[str] | None = None,
    pipeline: Any | None = None,
    n_results_per_domain: int = 3,
    max_sources: int = 6,
) -> dict[str, Any]:
    """Retrieve LLM Wiki evidence for diet/supplement advice.

    The returned context is evidence support, not an authority override. Callers
    should still run deterministic safety and advice guards.
    """

    if pipeline is None:
        try:
            pipeline = _get_pipeline()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[knowledge_evidence] pipeline unavailable: %s", exc)
            return {
                "available": False,
                "sources": [],
                "prompt_context": "",
                "claim_boundary": CLAIM_BOUNDARY,
            }
    if not pipeline or not pipeline.is_available():
        return {
            "available": False,
            "sources": [],
            "prompt_context": "",
            "claim_boundary": CLAIM_BOUNDARY,
        }

    signals = " ".join(str(s) for s in (user_signals or []) if s)
    all_results: list[dict[str, Any]] = []
    for domain in domains:
        category, base_query = DOMAIN_QUERIES.get(domain, (None, domain))
        query = f"{base_query} {signals}".strip()
        try:
            all_results.extend(
                pipeline.retrieve_relevant_knowledge(
                    query=query,
                    category=category,
                    n_results=n_results_per_domain,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[knowledge_evidence] retrieval failed domain=%s: %s", domain, exc)

    sources = _dedupe_sources(all_results, max_sources)
    return {
        "available": bool(sources),
        "sources": sources,
        "prompt_context": _render_prompt_context(sources),
        "claim_boundary": CLAIM_BOUNDARY,
    }
