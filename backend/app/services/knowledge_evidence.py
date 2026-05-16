"""LLM Wiki evidence retrieval for user-facing advice."""

from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)


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


def _get_pipeline():
    from app.services.knowledge.rag_pipeline import RAGPipeline

    return RAGPipeline()


def _source_from_result(result: dict[str, Any]) -> dict[str, Any]:
    metadata = result.get("metadata") or {}
    content = str(result.get("content") or "").strip()
    return {
        "title": metadata.get("title") or "LLM Wiki",
        "category": metadata.get("category") or "",
        "source": metadata.get("source") or metadata.get("url") or "llm_wiki",
        "relevance": result.get("relevance_score", 0),
        "excerpt": content[:240],
    }


def _dedupe_sources(results: Iterable[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    sources: list[dict[str, Any]] = []
    for result in results:
        source = _source_from_result(result)
        key = "|".join([source["category"], source["excerpt"][:160]])
        if key in seen or not source["excerpt"]:
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
        lines.append(
            f"{idx}. {source['title']} [{source['category']}] "
            f"(relevance={float(source['relevance'] or 0):.2f}): {source['excerpt']}"
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
