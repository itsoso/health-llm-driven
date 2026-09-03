from app.services.knowledge_evidence import build_advice_knowledge_context


class FakePipeline:
    def __init__(self, available=True):
        self.available = available
        self.queries = []

    def is_available(self):
        return self.available

    def retrieve_relevant_knowledge(self, query, category=None, n_results=5):
        self.queries.append({"query": query, "category": category, "n_results": n_results})
        return [
            {
                "content": "这段模拟付费文章原文不应进入运行时建议证据。",
                "metadata": {
                    "title": "蛋白质与代谢健康",
                    "category": "nutrition",
                    "source": "llm_wiki",
                    "source_id": "claim:protein-gap",
                    "license_scope": "internal_summary_only",
                    "claim_summary": "蛋白粉只应用于补足日常饮食蛋白缺口。",
                },
                "relevance_score": 0.82,
            },
            {
                "content": "这段模拟付费文章原文不应进入运行时建议证据。",
                "metadata": {
                    "title": "重复片段",
                    "category": "nutrition",
                    "source": "llm_wiki",
                    "source_id": "claim:protein-gap",
                    "license_scope": "internal_summary_only",
                    "claim_summary": "蛋白粉只应用于补足日常饮食蛋白缺口。",
                },
                "relevance_score": 0.75,
            },
        ]


def test_build_advice_knowledge_context_retrieves_and_deduplicates_sources():
    pipeline = FakePipeline()

    result = build_advice_knowledge_context(
        domains=["nutrition", "supplement"],
        user_signals=["蛋白不足", "睡眠偏少"],
        pipeline=pipeline,
    )

    assert result["available"] is True
    assert len(pipeline.queries) == 2
    assert pipeline.queries[0]["category"] == "nutrition"
    assert pipeline.queries[1]["category"] == "supplement"
    assert len(result["sources"]) == 1
    assert result["sources"][0]["title"] == "蛋白质与代谢健康"
    assert result["sources"][0]["source_id"] == "claim:protein-gap"
    assert result["sources"][0]["license_scope"] == "internal_summary_only"
    assert result["sources"][0]["summary"] == "蛋白粉只应用于补足日常饮食蛋白缺口。"
    assert "excerpt" not in result["sources"][0]
    assert "不能替代医生诊断" in result["claim_boundary"]
    assert "蛋白粉只应用于补足日常饮食蛋白缺口" in result["prompt_context"]
    assert "模拟付费文章原文" not in result["prompt_context"]


def test_build_advice_knowledge_context_drops_raw_content_without_reviewed_summary():
    class RawOnlyPipeline(FakePipeline):
        def retrieve_relevant_knowledge(self, query, category=None, n_results=5):
            self.queries.append({"query": query, "category": category, "n_results": n_results})
            return [{
                "content": "这是一段没有审校摘要授权的原文片段，不能被返回给模型或前端。",
                "metadata": {
                    "title": "仅原文来源",
                    "category": "supplement",
                    "source": "dedao:paid-course",
                    "license_scope": "internal_summary_only",
                },
                "relevance_score": 0.91,
            }]

    result = build_advice_knowledge_context(
        domains=["supplement"],
        user_signals=["镁"],
        pipeline=RawOnlyPipeline(),
    )

    assert result["available"] is False
    assert result["sources"] == []
    assert result["prompt_context"] == ""


def test_build_advice_knowledge_context_handles_unavailable_pipeline():
    result = build_advice_knowledge_context(
        domains=["nutrition"],
        user_signals=["蛋白不足"],
        pipeline=FakePipeline(available=False),
    )

    assert result["available"] is False
    assert result["sources"] == []
    assert result["prompt_context"] == ""


def test_build_advice_knowledge_context_handles_pipeline_init_failure(monkeypatch):
    def fail_pipeline():
        raise RuntimeError("vector store unavailable")

    monkeypatch.setattr("app.services.knowledge_evidence._get_pipeline", fail_pipeline)

    result = build_advice_knowledge_context(
        domains=["nutrition"],
        user_signals=["蛋白不足"],
    )

    assert result["available"] is False
    assert result["sources"] == []
    assert result["prompt_context"] == ""
