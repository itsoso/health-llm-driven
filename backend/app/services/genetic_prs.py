"""多基因风险评分 (Polygenic Risk Score, PRS)

基于用户已检测 SNP 位点的加权评分，评估特定疾病领域的遗传风险。
仅使用消费级基因芯片常见位点（非全基因组），结果供参考。
"""

from typing import Any, Dict, List, Optional

PRS_WEIGHTS: Dict[str, Dict[str, Dict[str, float]]] = {
    "cardiovascular": {
        "APOE": {"ε4/ε4": 2.0, "ε3/ε4": 1.0, "ε3/ε3": 0.0, "ε2": -0.5},
        "9P21": {"AA": 1.2, "AG": 0.6, "GG": 0.0},
        "CETP": {"GG": 0.0, "AG": -0.2, "AA": -0.4},
        "NOS3": {"Asp/Asp": 0.6, "Glu/Asp": 0.3, "Glu/Glu": 0.0},
    },
    "diabetes": {
        "TCF7L2": {"TT": 1.5, "CT": 0.7, "CC": 0.0},
        "FTO": {"AA": 0.8, "AT": 0.4, "TT": 0.0},
        "PPARG": {"Pro/Pro": 0.3, "Pro/Ala": 0.0, "Ala/Ala": -0.2},
        "CDKN2A/B": {"CC": 1.0, "CT": 0.5, "TT": 0.0},
        "IGF2BP2": {"TT": 0.8, "GT": 0.4, "GG": 0.0},
    },
    "obesity": {
        "FTO": {"AA": 1.2, "AT": 0.6, "TT": 0.0},
        "PPARG": {"Pro/Pro": 0.4, "Pro/Ala": 0.0, "Ala/Ala": -0.3},
    },
    "inflammation": {
        "IL-6": {"GG": 1.0, "GC": 0.4, "CC": 0.0},
        "TNF-α": {"AA": 1.2, "AG": 0.6, "GG": 0.0},
        "SOD2": {"Val/Val": 0.8, "Val/Ala": 0.3, "Ala/Ala": 0.0},
        "GPX1": {"Pro/Pro": 0.6, "Pro/Leu": 0.2, "Leu/Leu": 0.0},
    },
    "cognition": {
        "BDNF": {"Met/Met": 1.0, "Val/Met": 0.5, "Val/Val": 0.0},
        "KIBRA": {"TT": 0.8, "CT": 0.4, "CC": 0.0},
        "SNAP25": {"AA": 0.6, "AG": 0.3, "GG": 0.0},
        "COMT": {"Met/Met": 0.4, "Val/Met": 0.0, "Val/Val": -0.3},
    },
}

_RISK_THRESHOLDS = {
    "cardiovascular": [(2.5, "high"), (1.2, "moderate"), (0.5, "mild"), (0.0, "low")],
    "diabetes": [(2.5, "high"), (1.5, "moderate"), (0.7, "mild"), (0.0, "low")],
    "obesity": [(1.5, "high"), (0.8, "moderate"), (0.3, "mild"), (0.0, "low")],
    "inflammation": [(2.0, "high"), (1.2, "moderate"), (0.5, "mild"), (0.0, "low")],
    "cognition": [(2.0, "high"), (1.0, "moderate"), (0.4, "mild"), (0.0, "low")],
}


def compute_prs(
    variants: List[Dict[str, Any]],
    domain: str,
) -> Optional[Dict[str, Any]]:
    """计算某领域的多基因风险评分。

    variants: [{gene_name, genotype, result_label, ...}]
    domain: PRS_WEIGHTS 的 key
    """
    weights = PRS_WEIGHTS.get(domain)
    if not weights:
        return None

    by_gene: Dict[str, str] = {}
    for v in variants:
        name = (v.get("gene_name") or "").upper()
        geno = v.get("genotype") or v.get("result_label") or ""
        if name:
            by_gene.setdefault(name, geno)

    raw_score = 0.0
    max_score = 0.0
    matched_genes = []

    for gene, geno_weights in weights.items():
        geno = by_gene.get(gene, "")
        max_weight = max(geno_weights.values())
        max_score += max(max_weight, 0)

        matched = False
        for pattern, w in geno_weights.items():
            if pattern.upper() in geno.upper():
                raw_score += w
                matched_genes.append({"gene": gene, "genotype": geno, "weight": w})
                matched = True
                break

        if not matched and geno:
            matched_genes.append({"gene": gene, "genotype": geno, "weight": 0, "note": "unmatched"})

    if not matched_genes:
        return None

    percentile = int(min(99, max(1, (raw_score / max_score * 100) if max_score > 0 else 50)))

    thresholds = _RISK_THRESHOLDS.get(domain, [])
    risk_level = "unknown"
    for threshold, level in thresholds:
        if raw_score >= threshold:
            risk_level = level
            break

    return {
        "domain": domain,
        "raw_score": round(raw_score, 2),
        "max_possible": round(max_score, 2),
        "percentile": percentile,
        "risk_level": risk_level,
        "genes_evaluated": len(matched_genes),
        "genes_available": len(weights),
        "details": matched_genes,
    }


def compute_all_prs(variants: List[Dict[str, Any]]) -> Dict[str, Any]:
    """计算所有领域的 PRS。"""
    results = {}
    for domain in PRS_WEIGHTS:
        prs = compute_prs(variants, domain)
        if prs:
            results[domain] = prs
    return results
