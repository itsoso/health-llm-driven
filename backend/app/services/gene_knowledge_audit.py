"""Audit compiled gene_knowledge.json for actionable coverage and guardrails."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


AUTHORITY_SOURCE_PREFIXES = (
    "cpic:",
    "pharmgkb:",
    "clinvar:",
    "clingen:",
    "gene_reviews:",
    "fda:",
    "pubmed:",
)

TIER_DEFINITIONS: dict[str, dict[str, Any]] = {
    "tier0_pharmacogenomics": {
        "label": "Tier 0 用药安全红线",
        "genes": [
            "HLA-A*31:01",
            "HLA-B*15:02",
            "HLA-B*58:01",
            "CYP2C19",
            "CYP2D6",
            "CYP2C9",
            "VKORC1",
            "SLCO1B1",
            "G6PD",
            "DPYD",
            "TPMT",
            "NUDT15",
        ],
        "requires_rule": True,
        "requires_authority": True,
    },
    "tier1_lab_anchored": {
        "label": "Tier 1 基因 + 化验闭环",
        "genes": ["MTHFR", "APOE", "HFE", "ALDH2", "LCT", "FADS1", "9p21"],
        "requires_rule": False,
        "requires_authority": False,
    },
    "tier2_lifestyle": {
        "label": "Tier 2 生活方式倾向",
        "genes": ["FTO", "ACTN3", "ADORA2A", "VDR", "COMT"],
        "requires_rule": False,
        "requires_authority": False,
    },
    "tierx_confirmation_only": {
        "label": "Tier X 待确认筛查",
        "genes": ["CFTR", "ATP7B", "BRCA1", "BRCA2"],
        "requires_rule": False,
        "requires_authority": False,
    },
}

CLINICIAN_BOUNDARY_TERMS = (
    "医生",
    "医师",
    "临床",
    "处方",
    "剂量",
    "决策",
    "不替代",
    "consult",
    "clinician",
    "prescription",
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _norm(value: Any) -> str:
    return str(value or "").strip().upper()


def _claim_id(claim: dict[str, Any]) -> str:
    return str(claim.get("claim_id") or claim.get("id") or claim.get("title") or "unknown")


def _entity_bucket(payload: dict[str, Any], entity_type: str) -> dict[str, dict[str, Any]]:
    bucket = _as_dict(_as_dict(payload.get("entities")).get(entity_type))
    return {str(k): _as_dict(v) for k, v in bucket.items()}


def _claim_text(claim: dict[str, Any]) -> str:
    return " ".join(
        str(claim.get(key) or "")
        for key in ("entity_id", "title", "summary", "body", "claim_text")
    )


def _claims_by_gene(claims: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        entity_id = claim.get("entity_id")
        if entity_id:
            out[_norm(entity_id)].append(claim)
    return out


def _claim_mentions_gene(claim: dict[str, Any], gene: str) -> bool:
    return _norm(gene) in _norm(_claim_text(claim))


def _snps_for_gene(payload: dict[str, Any], gene: str) -> list[str]:
    gene_norm = _norm(gene)
    out: set[str] = set()
    for rsid, snp in _as_dict(payload.get("snp_registry")).items():
        if _norm(_as_dict(snp).get("gene")) == gene_norm:
            out.add(str(_as_dict(snp).get("rsid") or rsid))
    for rsid, snp in _entity_bucket(payload, "snp").items():
        if _norm(snp.get("gene")) == gene_norm:
            out.add(str(snp.get("rsid") or snp.get("entity_id") or rsid))
    return sorted(out)


def _entity_present(gene_entities: dict[str, dict[str, Any]], gene: str) -> bool:
    target = _norm(gene)
    for key, entity in gene_entities.items():
        candidates = [key, entity.get("entity_id"), entity.get("title"), *(_as_list(entity.get("aliases")))]
        if any(_norm(candidate) == target for candidate in candidates):
            return True
    return False


def _sources_for_gene(
    gene_entities: dict[str, dict[str, Any]],
    claims: list[dict[str, Any]],
    gene: str,
) -> list[str]:
    target = _norm(gene)
    sources: set[str] = set()
    for key, entity in gene_entities.items():
        candidates = [key, entity.get("entity_id"), entity.get("title"), *(_as_list(entity.get("aliases")))]
        if any(_norm(candidate) == target for candidate in candidates):
            sources.update(str(src) for src in _as_list(entity.get("sources")))
    for claim in claims:
        if _norm(claim.get("entity_id")) == target or _claim_mentions_gene(claim, gene):
            sources.update(str(src) for src in _as_list(claim.get("sources")))
            metadata = _as_dict(claim.get("metadata"))
            for src in _as_list(metadata.get("external_sources")):
                if isinstance(src, dict):
                    sources.add(str(src.get("id") or src.get("source") or ""))
                else:
                    sources.add(str(src))
    return sorted(src for src in sources if src)


def _has_authority_source(sources: list[str]) -> bool:
    return any(src.lower().startswith(AUTHORITY_SOURCE_PREFIXES) for src in sources)


def _has_boundary(claim: dict[str, Any]) -> bool:
    metadata = _as_dict(claim.get("metadata"))
    text = _claim_text(claim)
    return bool(metadata.get("claim_boundary") or "边界" in text or "not diagnosis" in text.lower())


def _has_clinician_boundary(claim: dict[str, Any]) -> bool:
    text = _claim_text(claim)
    return any(term.lower() in text.lower() for term in CLINICIAN_BOUNDARY_TERMS)


def audit_gene_knowledge(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a structured audit report for a compiled gene_knowledge payload."""
    claims = [_as_dict(item) for item in _as_list(payload.get("claims"))]
    gene_entities = _entity_bucket(payload, "gene")
    gene_rules = _as_dict(payload.get("gene_rules"))
    claims_by_gene = _claims_by_gene(claims)

    report: dict[str, Any] = {
        "version": payload.get("version") or "",
        "compiled_at": payload.get("compiled_at") or "",
        "summary": {
            "gene_entities": len(gene_entities),
            "snp_registry": len(_as_dict(payload.get("snp_registry"))),
            "claims": len(claims),
            "gene_rules": len(gene_rules),
        },
        "tiers": {},
        "quality_gates": {
            "claims_missing_applies_when": [],
            "claims_missing_boundary": [],
            "drug_claims_missing_clinician_boundary": [],
        },
        "next_actions": [],
    }

    for tier_key, tier_def in TIER_DEFINITIONS.items():
        statuses = []
        covered = 0
        missing_rule_genes: list[str] = []
        missing_claim_genes: list[str] = []
        missing_authority_source_genes: list[str] = []

        for gene in tier_def["genes"]:
            gene_claims = [
                *claims_by_gene.get(_norm(gene), []),
                *[claim for claim in claims if _claim_mentions_gene(claim, gene)],
            ]
            claim_present = bool(gene_claims)
            rule_present = gene in gene_rules
            sources = _sources_for_gene(gene_entities, claims, gene)
            authority_source_present = _has_authority_source(sources)
            status = {
                "gene": gene,
                "entity_present": _entity_present(gene_entities, gene),
                "claim_present": claim_present,
                "rule_present": rule_present,
                "snp_count": len(_snps_for_gene(payload, gene)),
                "authority_source_present": authority_source_present,
                "sources": sources,
            }
            if tier_def.get("requires_rule") and not rule_present:
                missing_rule_genes.append(gene)
            if not claim_present:
                missing_claim_genes.append(gene)
            if tier_def.get("requires_authority") and not authority_source_present:
                missing_authority_source_genes.append(gene)

            requirements_met = claim_present
            if tier_def.get("requires_rule"):
                requirements_met = requirements_met and rule_present
            if tier_def.get("requires_authority"):
                requirements_met = requirements_met and authority_source_present
            if requirements_met:
                covered += 1
            statuses.append(status)

        report["tiers"][tier_key] = {
            "label": tier_def["label"],
            "required": len(tier_def["genes"]),
            "covered": covered,
            "coverage_rate": round(covered / len(tier_def["genes"]), 3),
            "genes": statuses,
            "missing_rule_genes": missing_rule_genes,
            "missing_claim_genes": sorted(set(missing_claim_genes)),
            "missing_authority_source_genes": missing_authority_source_genes,
        }

    for claim in claims:
        cid = _claim_id(claim)
        if not _as_list(claim.get("applies_when")):
            report["quality_gates"]["claims_missing_applies_when"].append(cid)
        if not _has_boundary(claim):
            report["quality_gates"]["claims_missing_boundary"].append(cid)
        if claim.get("drug_rules") and not _has_clinician_boundary(claim):
            report["quality_gates"]["drug_claims_missing_clinician_boundary"].append(cid)

    tier0 = report["tiers"]["tier0_pharmacogenomics"]
    tierx = report["tiers"]["tierx_confirmation_only"]
    if tier0["missing_rule_genes"]:
        report["next_actions"].append(
            "补齐 Tier 0 用药安全规则，优先 HLA-B*58:01/HLA-B*15:02/CYP2D6/DPYD/TPMT/NUDT15。"
        )
    if tierx["missing_claim_genes"]:
        report["next_actions"].append(
            "为 CFTR/ATP7B 等罕见病位点建立 confirmation_only 边界，防止 DTC 结果显示为疾病高风险。"
        )
    if report["quality_gates"]["claims_missing_applies_when"]:
        report["next_actions"].append("补齐 claims.applies_when，让 Agent 只在结构化 Twin 命中时使用。")
    if report["quality_gates"]["claims_missing_boundary"]:
        report["next_actions"].append("补齐 claim_boundary/边界，避免课程知识被当成诊断或处方。")

    return report


def format_gene_knowledge_audit_markdown(report: dict[str, Any]) -> str:
    """Render an audit report as a concise Markdown document."""
    lines = [
        "# Gene Knowledge Audit",
        "",
        f"- Version: `{report.get('version') or 'unknown'}`",
        f"- Compiled at: `{report.get('compiled_at') or 'unknown'}`",
        "",
        "## Summary",
    ]
    for key, value in _as_dict(report.get("summary")).items():
        lines.append(f"- `{key}`: {value}")

    lines.extend(["", "## Tier Coverage"])
    for tier_key, tier in _as_dict(report.get("tiers")).items():
        label = tier.get("label") or tier_key
        lines.append("")
        lines.append(f"### {label}")
        lines.append(f"- Coverage: {tier.get('covered', 0)}/{tier.get('required', 0)}")
        missing_rules = tier.get("missing_rule_genes") or []
        missing_claims = tier.get("missing_claim_genes") or []
        missing_sources = tier.get("missing_authority_source_genes") or []
        if missing_rules:
            lines.append(f"- Missing rules: {', '.join(missing_rules)}")
        if missing_claims:
            lines.append(f"- Missing claims: {', '.join(missing_claims)}")
        if missing_sources:
            lines.append(f"- Missing authority sources: {', '.join(missing_sources)}")

    gates = _as_dict(report.get("quality_gates"))
    lines.extend(["", "## Quality Gates"])
    lines.append(f"- Claims missing `applies_when`: {len(gates.get('claims_missing_applies_when') or [])}")
    lines.append(f"- Claims missing boundary: {len(gates.get('claims_missing_boundary') or [])}")
    lines.append(
        "- Drug claims missing clinician boundary: "
        f"{len(gates.get('drug_claims_missing_clinician_boundary') or [])}"
    )

    lines.extend(["", "## 下一步"])
    next_actions = report.get("next_actions") or []
    if next_actions:
        lines.extend(f"- {action}" for action in next_actions)
    else:
        lines.append("- 当前没有阻塞级缺口，继续补外部证据和用户回归评测。")
    lines.append("")
    return "\n".join(lines)
