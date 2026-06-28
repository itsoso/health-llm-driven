"""
Knowledge Librarian Specialist —— 对用户的问题做知识检索 + 引用。

两种用法：
1. 独立回答知识类问题（"什么是 MTHFR"）
2. 为其他 specialist 的建议提供证据支撑（Orchestrator 合成时引用）
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from app.config import settings
from app.orchestrator.schema import Intent, SpecialistFinding
from app.twin.schema import HealthTwin

logger = logging.getLogger(__name__)


class KnowledgeLibrarianSpecialist:
    name = "knowledge_librarian"
    category = "knowledge"

    TRIGGER_KEYWORDS = {
        "什么是", "为什么", "原理", "机制", "怎么回事",
        "科学", "研究", "证据", "文献", "参考",
        "解释", "知识", "学习", "了解",
        "wiki", "知识库",
    }

    def applies_to(self, intent: Intent, twin: HealthTwin) -> bool:
        q = (intent.raw_query or "").lower()
        # 知识类问题
        if any(k in q for k in self.TRIGGER_KEYWORDS):
            return True
        # general 场景下如果知识库可用就参与（提供证据背书）
        if "general" in intent.categories:
            return True
        return False

    def run(self, twin: HealthTwin, context: Dict[str, Any]) -> SpecialistFinding:
        t0 = time.monotonic()
        try:
            query = context.get("query", "")
            if not query:
                return SpecialistFinding(
                    specialist_name=self.name,
                    category=self.category,
                    summary="无查询内容",
                    findings=[],
                    raw={},
                    ms_elapsed=int((time.monotonic() - t0) * 1000),
                )

            system_kb_finding = self._run_system_kb(query, context, t0)
            if system_kb_finding is not None:
                return system_kb_finding

            if not settings.legacy_knowledge_runtime_enabled:
                return SpecialistFinding(
                    specialist_name=self.name,
                    category=self.category,
                    summary="系统知识库暂无 reviewed 证据；legacy Chroma wiki 运行时检索已关闭。",
                    findings=[],
                    raw={
                        "source": "system_kb_v2",
                        "query": query,
                        "results_count": 0,
                        "legacy_chroma_enabled": False,
                    },
                    ms_elapsed=int((time.monotonic() - t0) * 1000),
                )

            from app.agents.knowledge_librarian.indexer import search_knowledge

            # 旧 ChromaDB wiki 检索保留为 fallback。
            results = search_knowledge(query, n_results=5)
            if not results:
                return SpecialistFinding(
                    specialist_name=self.name,
                    category=self.category,
                    summary="知识库暂无相关内容（可能需要先建索引）",
                    findings=[],
                    raw={"query": query, "results_count": 0},
                    ms_elapsed=int((time.monotonic() - t0) * 1000),
                )

            findings: List[Dict[str, Any]] = []
            for i, r in enumerate(results, 1):
                findings.append({
                    "type": "knowledge_reference",
                    "order": i,
                    "title": r.get("title", ""),
                    "source": r.get("source", ""),
                    "text": r.get("text", "")[:500],  # 截断避免 prompt 过长
                    "relevance": 1.0 - (r.get("distance") or 0.5),  # 距离→相关度
                })

            summary = f"找到 {len(results)} 条相关知识（来源：得到 wiki）"

            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=summary,
                findings=findings,
                raw={
                    "query": query,
                    "results_count": len(results),
                    "top_source": results[0].get("source") if results else None,
                },
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[knowledge_librarian] run failed: {e}")
            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=f"知识检索失败: {e}",
                findings=[],
                raw={"error": str(e)},
                ms_elapsed=int((time.monotonic() - t0) * 1000),
            )

    def _run_system_kb(
        self,
        query: str,
        context: Dict[str, Any],
        started_at: float,
    ) -> SpecialistFinding | None:
        db = context.get("db")
        if db is None:
            return None

        try:
            from app.services.system_knowledge_service import (
                build_evidence_card_for_message,
                search_knowledge as search_system_knowledge,
            )

            card = build_evidence_card_for_message(db, query)
            if card:
                data = card.get("data") or {}
                claims = data.get("claims") or []
                entity = data.get("entity") or {}
                refs = [
                    claim.get("doc_id")
                    for claim in claims
                    if isinstance(claim, dict) and str(claim.get("doc_id") or "").startswith("claim:")
                ]
                findings = [
                    {
                        "type": "system_knowledge_reference",
                        "title": claim.get("title") or claim.get("doc_id"),
                        "summary": claim.get("summary"),
                        "evidence_level": claim.get("evidence_level"),
                        "confidence": claim.get("confidence"),
                        "sources": claim.get("sources") or [],
                        "entity": entity,
                        "claim_id": claim.get("doc_id"),
                        "evidence_refs": [claim.get("doc_id")],
                    }
                    for claim in claims
                    if isinstance(claim, dict)
                ]
                return SpecialistFinding(
                    specialist_name=self.name,
                    category=self.category,
                    summary=f"系统知识库命中 {len(claims)} 条结构化证据",
                    findings=findings,
                    raw={
                        "source": "system_kb_v2",
                        "mode": "explicit_entity_card",
                        "query": query,
                        "entity": entity,
                        "claim_boundary": data.get("claim_boundary"),
                    },
                    evidence_refs=refs,
                    ms_elapsed=int((time.monotonic() - started_at) * 1000),
                )

            result = search_system_knowledge(db, query, limit=5)
            results = result.get("results") or []
            claim_results = [
                item for item in results
                if isinstance(item, dict)
                and (item.get("document") or {}).get("doc_type") == "claim"
            ]
            if not claim_results:
                return None

            refs = [
                item["document"]["doc_id"]
                for item in claim_results
                if str(item["document"].get("doc_id") or "").startswith("claim:")
            ]
            findings = []
            for item in claim_results:
                document = item["document"]
                findings.append(
                    {
                        "type": "system_knowledge_reference",
                        "title": document.get("title") or document.get("doc_id"),
                        "summary": document.get("summary"),
                        "evidence_level": document.get("evidence_level"),
                        "confidence": document.get("confidence"),
                        "sources": document.get("sources") or [],
                        "claim_id": document.get("doc_id"),
                        "evidence_refs": [document.get("doc_id")],
                        "score": item.get("score"),
                    }
                )

            return SpecialistFinding(
                specialist_name=self.name,
                category=self.category,
                summary=f"系统知识库找到 {len(claim_results)} 条 claim 证据",
                findings=findings,
                raw={
                    "source": "system_kb_v2",
                    "mode": "db_search",
                    "query": query,
                    "result_count": len(results),
                    "claim_boundary": result.get("claim_boundary"),
                },
                evidence_refs=refs,
                ms_elapsed=int((time.monotonic() - started_at) * 1000),
            )
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[knowledge_librarian] system KB fallback: {e}")
            return None
