#!/usr/bin/env python3
"""Seed the Phase 0 system knowledge vertical slice.

This script is idempotent and writes only system-level, reviewed seed entries.
It does not ingest user conversations or private user data into the shared KB.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SEED_DATE = datetime(2026, 5, 16, tzinfo=UTC)


def main() -> int:
    from app.database import SessionLocal
    from app.models.system_knowledge import KBDocument, KBEdge

    db = SessionLocal()
    try:
        docs = _seed_documents()
        for doc in docs:
            existing = db.query(KBDocument).filter(KBDocument.doc_id == doc["doc_id"]).first()
            if existing:
                for key, value in doc.items():
                    setattr(existing, key, value)
            else:
                db.add(KBDocument(**doc))
        db.flush()

        for edge in _seed_edges():
            existing = (
                db.query(KBEdge)
                .filter(
                    KBEdge.src_doc_id == edge["src_doc_id"],
                    KBEdge.dst_doc_id == edge["dst_doc_id"],
                    KBEdge.relation == edge["relation"],
                )
                .first()
            )
            if existing:
                existing.confidence = edge["confidence"]
                existing.source_claim_id = edge["source_claim_id"]
            else:
                db.add(KBEdge(**edge))

        db.commit()
        print(f"seeded {len(docs)} kb_documents and {len(_seed_edges())} kb_edges")
        return 0
    finally:
        db.close()


def _entity(entity_type: str, entity_id: str, title: str, summary: str) -> dict:
    return {
        "doc_id": f"entity:{entity_type}:{entity_id}",
        "doc_type": "entity",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "title": title,
        "summary": summary,
        "body": summary,
        "confidence": 0.75,
        "evidence_level": "C",
        "sources": ["system:phase0-curated"],
        "last_confirmed": SEED_DATE,
        "decay_rate": "slow",
        "is_archived": False,
    }


def _claim(
    claim_id: str,
    entity_type: str,
    entity_id: str,
    title: str,
    summary: str,
    applies_when: list[str],
    recommends_lookup: list[str],
    sources: list[str],
    confidence: float = 0.72,
    evidence_level: str = "C",
) -> dict:
    return {
        "doc_id": f"claim:{claim_id}",
        "doc_type": "claim",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "title": title,
        "summary": summary,
        "body": f"{summary}\n\n边界：仅用于健康管理提示，不用于诊断、治疗或用药决策。",
        "confidence": confidence,
        "evidence_level": evidence_level,
        "applies_when": applies_when,
        "recommends_lookup": recommends_lookup,
        "sources": sources,
        "last_confirmed": SEED_DATE,
        "decay_rate": "normal",
        "is_archived": False,
    }


def _seed_documents() -> list[dict]:
    entities = [
        _entity("gene", "MTHFR", "MTHFR", "一碳代谢相关基因，常用于叶酸转化与 Hcy 风险沟通。"),
        _entity("gene", "APOE", "APOE", "脂质代谢和阿尔茨海默病风险沟通中常见的基因。"),
        _entity("gene", "FTO", "FTO", "体重和食欲调节相关的常见遗传风险位点集合。"),
        _entity("gene", "ACTN3", "ACTN3", "运动表现相关基因，常用于力量/耐力倾向沟通。"),
        _entity("gene", "ALDH2", "ALDH2", "乙醛代谢相关基因，影响饮酒反应和健康风险沟通。"),
        _entity("biomarker", "Hcy", "同型半胱氨酸", "一碳代谢和心血管风险沟通中的临床锚点。"),
        _entity("supplement", "5-MTHF", "5-MTHF", "活性叶酸形式，需结合 B12 与 Hcy 结果谨慎使用。"),
    ]
    claims = [
        _claim(
            "c_mthfr_c677t_hcy_folate_boundary",
            "gene",
            "MTHFR",
            "MTHFR C677T 与叶酸转化边界",
            "C677T CT/TT 用户可优先关注同型半胱氨酸、B12 与活性叶酸；补剂建议应结合化验结果。",
            ["twin.genetics.MTHFR_C677T in ['CT', 'TT']", "twin.labs.homocysteine_umol_l >= 15"],
            ["entity:biomarker:Hcy", "entity:supplement:5-MTHF"],
            ["dedao:qiuzilong-genetics-07", "pubmed:19033271"],
            confidence=0.82,
            evidence_level="B",
        ),
        _claim(
            "c_apoe_ldl_diet_boundary",
            "gene",
            "APOE",
            "APOE 与 LDL-C 管理边界",
            "APOE E4 携带者可更重视 LDL-C/ApoB 轨迹和饱和脂肪控制，但不能用基因替代血脂指标。",
            ["twin.genetics.APOE in ['E3/E4', 'E4/E4']", "twin.labs.ldl_c_mmol_l >= 3.4"],
            ["entity:biomarker:LDL-C"],
            ["system:phase0-curated"],
        ),
        _claim(
            "c_fto_weight_risk_boundary",
            "gene",
            "FTO",
            "FTO 与体重管理边界",
            "FTO 风险位点适合用来解释体重管理倾向，但行动仍应落在蛋白、纤维、睡眠和运动闭环。",
            ["twin.genetics.FTO is not null"],
            ["entity:condition:metabolic-health"],
            ["system:phase0-curated"],
        ),
        _claim(
            "c_actn3_training_phenotype_boundary",
            "gene",
            "ACTN3",
            "ACTN3 与训练倾向边界",
            "ACTN3 可作为力量/耐力倾向的辅助解释，不能决定训练能力上限或替代训练负荷反馈。",
            ["twin.genetics.ACTN3 is not null"],
            ["entity:intervention:strength-training"],
            ["system:phase0-curated"],
        ),
        _claim(
            "c_aldh2_alcohol_boundary",
            "gene",
            "ALDH2",
            "ALDH2 与饮酒风险边界",
            "ALDH2 活性降低者应避免把饮酒耐受作为健康信号，并优先采用低酒精或不饮酒策略。",
            ["twin.genetics.ALDH2 in ['GA', 'AA', '*1/*2', '*2/*2']"],
            ["entity:behavior:alcohol-avoidance"],
            ["system:phase0-curated"],
        ),
    ]
    return entities + claims


def _seed_edges() -> list[dict]:
    claim_ids = [
        ("MTHFR", "claim:c_mthfr_c677t_hcy_folate_boundary"),
        ("APOE", "claim:c_apoe_ldl_diet_boundary"),
        ("FTO", "claim:c_fto_weight_risk_boundary"),
        ("ACTN3", "claim:c_actn3_training_phenotype_boundary"),
        ("ALDH2", "claim:c_aldh2_alcohol_boundary"),
    ]
    return [
        {
            "src_doc_id": f"entity:gene:{gene}",
            "dst_doc_id": claim_id,
            "relation": "has_claim",
            "confidence": 0.9,
            "source_claim_id": claim_id,
        }
        for gene, claim_id in claim_ids
    ]


if __name__ == "__main__":
    raise SystemExit(main())
