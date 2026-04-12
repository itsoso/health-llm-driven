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
            from app.agents.knowledge_librarian.indexer import search_knowledge

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

            # 搜索知识库
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
