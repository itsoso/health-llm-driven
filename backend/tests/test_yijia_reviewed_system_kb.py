from __future__ import annotations

import json
import re
from pathlib import Path

from app.models.system_knowledge import KBDocument
from app.services.agent_executor import AgentExecutor
from app.services.system_knowledge_service import search_knowledge


ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "data" / "system_kb_v2_seed"
COLLECTION = "yijia_reviewed"
DOSE_RECIPE_PATTERN = re.compile(
    r"(?:\d+(?:\.\d+)?\s*(?:mg|mcg|µg|μg|IU|毫克|微克|国际单位)(?:\s*/\s*(?:天|日|次))?)",
    re.IGNORECASE,
)
LEGACY_RECIPE_FRAGMENTS = (
    "成人：",
    "缺乏者：",
    "最高安全剂量",
    "早餐后",
    "每日1-2次",
)


def _reviewed_doc(
    doc_id: str,
    title: str,
    body: str,
    *,
    collections: list[str] | None = None,
) -> KBDocument:
    return KBDocument(
        doc_id=doc_id,
        doc_type="claim",
        entity_type="condition",
        entity_id="acute-covid",
        title=title,
        summary=body,
        body=body,
        confidence=0.9,
        evidence_level="B",
        sources=["https://example.test/source"],
        metadata_json={
            "review_status": "reviewed",
            "source_collections": collections or [],
        },
    )


def test_source_scoped_search_returns_only_exact_reviewed_collection(db):
    yijia = _reviewed_doc(
        "claim:yijia-covid-boundary",
        "新冠补剂证据边界",
        "新冠发烧时补剂不能替代治疗评估。",
        collections=[COLLECTION, "益家知研"],
    )
    unrelated = _reviewed_doc(
        "claim:generic-covid-supplements",
        "通用新冠补剂内容",
        "新冠发烧补剂通用结果，不属于指定知识源。",
    )
    db.add_all([yijia, unrelated])
    db.commit()

    payload = search_knowledge(
        db,
        "新冠发烧补剂",
        limit=10,
        source_collection=COLLECTION,
    )

    assert [item["document"]["doc_id"] for item in payload["results"]] == [
        yijia.doc_id,
    ]
    assert payload["retrieval_plan"]["source_collection"] == COLLECTION


def test_source_scoped_zero_hit_never_widens_to_generic_documents(db):
    db.add(
        _reviewed_doc(
            "claim:generic-only",
            "新冠发烧补剂",
            "只有通用知识库收录的结果。",
        )
    )
    db.commit()

    payload = search_knowledge(
        db,
        "新冠发烧补剂",
        limit=10,
        source_collection=COLLECTION,
    )

    assert payload["results"] == []
    assert payload["retrieval_plan"]["source_collection"] == COLLECTION


def test_named_only_collection_documents_do_not_change_generic_search(db):
    named_only = _reviewed_doc(
        "claim:yijia-named-only",
        "睡眠不好吃什么补剂",
        "该条目只允许通过指定来源检索。",
        collections=[COLLECTION],
    )
    named_only.metadata_json["named_collection_only"] = True
    db.add(named_only)
    db.commit()

    generic = search_knowledge(db, "睡眠不好吃什么补剂", limit=10)
    scoped = search_knowledge(
        db,
        "睡眠不好吃什么补剂",
        limit=10,
        source_collection=COLLECTION,
    )

    assert all(
        item["document"]["doc_id"] != named_only.doc_id
        for item in generic["results"]
    )
    assert [item["document"]["doc_id"] for item in scoped["results"]] == [
        named_only.doc_id,
    ]


async def test_agent_searches_released_yijia_collection(db, monkeypatch):
    seen: dict[str, object] = {}

    def _search(_db, query, **kwargs):
        seen.update(query=query, **kwargs)
        return {
            "results": [
                {
                    "score": 0.9,
                    "document": {
                        "doc_id": "claim:c_yijia_covid_supplement_evidence_boundary",
                        "doc_type": "claim",
                        "title": "急性 COVID 补剂证据边界",
                        "summary": "没有充分证据支持用补剂预防或治疗 COVID-19。",
                        "body": "不给出具体剂量。",
                        "evidence_level": "B",
                    },
                    "retrieval": {},
                }
            ]
        }

    monkeypatch.setattr(
        "app.services.system_knowledge_service.search_knowledge",
        _search,
    )

    result = await AgentExecutor(db)._exec_knowledge_search({
        "query": "我有胃溃疡和脂肪肝，新冠发烧时补剂怎么选？",
        "knowledge_source": "益家知研",
    })

    assert seen == {
        "query": "我有胃溃疡和脂肪肝，新冠发烧时补剂怎么选？",
        "limit": 5,
        "source_collection": COLLECTION,
    }
    assert "requested_source=益家知研" in result
    assert f"resolved_source={COLLECTION}" in result
    assert "source_status=released" in result
    assert "没有充分证据支持用补剂预防或治疗 COVID-19" in result


def test_reviewed_yijia_artifacts_have_official_provenance_and_no_dose_recipe():
    rows = [
        json.loads(line)
        for line in (ARTIFACT_DIR / "claims.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    claims = {
        row["doc_id"]: row
        for row in rows
        if COLLECTION in (row.get("metadata") or {}).get("source_collections", [])
    }

    assert set(claims) == {
        "claim:c_yijia_covid_supplement_evidence_boundary",
        "claim:c_yijia_covid_early_treatment_assessment",
    }
    for claim in claims.values():
        metadata = claim["metadata"]
        assert metadata["review_status"] == "reviewed"
        assert metadata["clinical_signoff"] == "not_claimed"
        assert metadata["claim_boundary"]
        assert metadata["review_valid_until"] == "2027-08-29T00:00:00+00:00"
        assert metadata["named_collection_only"] is True
        external_sources = metadata["external_sources"]
        assert external_sources
        assert all(source["source"].startswith("https://") for source in external_sources)
        assert "不给出具体剂量" in claim["body"]
        served_text = "\n".join((
            claim.get("title") or "",
            claim.get("summary") or "",
            claim.get("body") or "",
        ))
        assert DOSE_RECIPE_PATTERN.search(served_text) is None
        assert all(fragment not in served_text for fragment in LEGACY_RECIPE_FRAGMENTS)
