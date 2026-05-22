from __future__ import annotations

import json
import subprocess
import sys

from app.services.gene_knowledge_audit import (
    audit_gene_knowledge,
    format_gene_knowledge_audit_markdown,
)


def test_gene_knowledge_audit_reports_tier_coverage_and_missing_required_rules():
    payload = {
        "version": "test-v1",
        "compiled_at": "2026-05-22T12:00:00+08:00",
        "entities": {
            "gene": {
                "CYP2C19": {
                    "entity_id": "CYP2C19",
                    "sources": ["cpic:guideline-cyp2c19-clopidogrel"],
                },
                "MTHFR": {"entity_id": "MTHFR", "sources": ["system:phase0-curated"]},
            },
            "snp": {
                "rs4244285": {"entity_id": "rs4244285", "gene": "CYP2C19"},
                "rs1801133": {"entity_id": "rs1801133", "gene": "MTHFR"},
            },
        },
        "snp_registry": {
            "rs4244285": {"rsid": "rs4244285", "gene": "CYP2C19"},
            "rs1801133": {"rsid": "rs1801133", "gene": "MTHFR"},
        },
        "gene_rules": {
            "CYP2C19": {
                "poor": {
                    "avoid": [{"drug": "clopidogrel", "reason": "reduced activation"}],
                    "substitute": [{"from": "clopidogrel", "to": "ticagrelor"}],
                }
            }
        },
        "claims": [
            {
                "claim_id": "c_cyp2c19_clopidogrel_boundary",
                "entity_id": "CYP2C19",
                "title": "CYP2C19 PM 与氯吡格雷边界",
                "sources": ["cpic:guideline-cyp2c19-clopidogrel"],
                "applies_when": ["twin.genetics.CYP2C19 == 'poor'"],
                "drug_rules": {"phenotype": "poor", "avoid": [{"drug": "clopidogrel"}]},
                "body": "替换药物属于心血管科处方决策。边界：不替代医生。",
            },
            {
                "claim_id": "c_mthfr_boundary",
                "entity_id": "MTHFR",
                "title": "MTHFR 与 Hcy 闭环",
                "sources": ["system:phase0-curated"],
                "applies_when": ["twin.genetics.MTHFR_C677T in ['CT','TT']"],
                "body": "边界：必须结合 Hcy、B12、叶酸。",
            },
        ],
    }

    report = audit_gene_knowledge(payload)

    assert report["summary"]["gene_entities"] == 2
    assert report["summary"]["gene_rules"] == 1
    assert report["tiers"]["tier0_pharmacogenomics"]["covered"] == 1
    assert report["tiers"]["tier0_pharmacogenomics"]["required"] >= 10
    assert "CYP2D6" in report["tiers"]["tier0_pharmacogenomics"]["missing_rule_genes"]
    assert "CFTR" in report["tiers"]["tierx_confirmation_only"]["missing_claim_genes"]
    assert report["quality_gates"]["claims_missing_applies_when"] == []
    assert report["quality_gates"]["drug_claims_missing_clinician_boundary"] == []


def test_gene_knowledge_audit_markdown_highlights_next_actions():
    report = audit_gene_knowledge({
        "version": "empty",
        "compiled_at": "2026-05-22T12:00:00+08:00",
        "entities": {},
        "claims": [],
        "gene_rules": {},
        "snp_registry": {},
    })

    markdown = format_gene_knowledge_audit_markdown(report)

    assert "# Gene Knowledge Audit" in markdown
    assert "Tier 0" in markdown
    assert "CFTR" in markdown
    assert "下一步" in markdown


def test_gene_knowledge_audit_next_action_names_remaining_tierx_gaps():
    payload = {
        "version": "tierx-test",
        "compiled_at": "2026-05-22T12:00:00+08:00",
        "entities": {
            "gene": {
                "CFTR": {"entity_id": "CFTR", "sources": ["gene_reviews:cystic-fibrosis"]},
                "ATP7B": {"entity_id": "ATP7B", "sources": ["gene_reviews:wilson-disease"]},
            }
        },
        "claims": [
            {
                "claim_id": "c_cftr_dtc_confirmation_boundary",
                "entity_id": "CFTR",
                "title": "CFTR DTC 位点命中后的确认边界",
                "sources": ["gene_reviews:cystic-fibrosis"],
                "applies_when": ["twin.genetics.CFTR_rs121908763 == 'GG'"],
                "body": "边界：confirmation_only，不替代临床诊断。",
            },
            {
                "claim_id": "c_atp7b_dtc_confirmation_boundary",
                "entity_id": "ATP7B",
                "title": "ATP7B DTC 位点命中后的确认边界",
                "sources": ["gene_reviews:wilson-disease"],
                "applies_when": ["twin.genetics.ATP7B_rs137853280 == 'GG'"],
                "body": "边界：confirmation_only，不替代临床诊断。",
            },
        ],
        "gene_rules": {},
        "snp_registry": {},
    }

    report = audit_gene_knowledge(payload)

    assert report["tiers"]["tierx_confirmation_only"]["missing_claim_genes"] == ["BRCA1", "BRCA2"]
    assert any("BRCA1/BRCA2" in action for action in report["next_actions"])
    assert not any("CFTR/ATP7B" in action for action in report["next_actions"])


def test_audit_gene_knowledge_cli_writes_markdown_report(tmp_path):
    source = tmp_path / "gene_knowledge.json"
    output = tmp_path / "report.md"
    source.write_text(
        json.dumps({
            "version": "cli-test",
            "compiled_at": "2026-05-22T12:00:00+08:00",
            "entities": {},
            "claims": [],
            "gene_rules": {},
            "snp_registry": {},
        }),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_gene_knowledge.py",
            "--gene-knowledge",
            str(source),
            "--output",
            str(output),
        ],
        cwd=".",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "wrote gene knowledge audit" in result.stdout
    assert "# Gene Knowledge Audit" in output.read_text(encoding="utf-8")
