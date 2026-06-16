"""相关位点计数 + 方向 (locus direction summary)

⚠️ 这**不是**人群校准的多基因风险评分 (PRS)。下面的权重是**手写的序数方向标注**
(命中位点把概率往升/降方向移),既无公开权威效应量来源,也未做祖源校准。
因此本模块**对外不输出 PRS、不输出人群百分位**——只给"命中几个相关位点 + 整体偏哪个方向"。

为什么降级 (见 docs/design-genetic-interpretation-first-principles.md §6 Phase 0):
- 复杂性状的遗传方差被成百上千位点稀释,消费级芯片这几个 SNP 对**个体**几乎无预测力。
- 原 `percentile = raw_score/max_score*100` 是**凭空构造的伪人群百分位**,会被误读为"你比 X% 的人风险高"。
- 原子串匹配 `pattern in geno` 会让 ε2/ε4 等等位互相误配。

在接入任何 agent 先验前,这里必须先替换为带溯源效应量的版本 (见 Phase 2)。当前**仅供展示**。
"""

from typing import Any, Dict, List, Optional

DISCLAIMER = (
    "非人群校准多基因评分,仅为相关位点的方向性提示;"
    "单/少数 SNP 对个体无预测力,非诊断,不可据此判断患病风险。"
)

# 手写序数方向标注:正值=该基因型把概率往"升高方向"移,负值=往"降低方向"移,0=中性。
# 仅用于「命中几个位点 + 整体偏哪个方向」,不构成评分/百分位/风险等级。
# key 是**精确基因型** (大写归一后精确相等匹配,不做子串)。
_LOCUS_DIRECTIONS: Dict[str, Dict[str, Dict[str, float]]] = {
    "cardiovascular": {
        "APOE": {"ε4/ε4": 2.0, "ε3/ε4": 1.0, "ε3/ε3": 0.0, "ε2/ε3": -0.5, "ε2/ε2": -0.5},
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


def _normalize_genotype(geno: str) -> str:
    """归一化基因型字符串以便精确比较 (大写 + 去空白)。

    注意:对希腊字母 ε 等不区分大小写没有意义,但去掉首尾/内部空白可避免
    "ε3 / ε4" vs "ε3/ε4" 这类纯格式差异导致漏配。
    """
    return geno.replace(" ", "").upper()


def _match_direction(geno: str, geno_directions: Dict[str, float]) -> Optional[float]:
    """精确等位/基因型匹配,返回方向值;无匹配返回 None。

    用精确相等 (归一化后) 取代旧的子串包含——后者会让 'ε2' 命中 'ε2/ε4'、
    'AA' 命中 'GAAT' 这类等位/基因型误配。
    """
    if not geno:
        return None
    norm = _normalize_genotype(geno)
    for pattern, direction in geno_directions.items():
        if _normalize_genotype(pattern) == norm:
            return direction
    return None


def compute_locus_summary(
    variants: List[Dict[str, Any]],
    domain: str,
) -> Optional[Dict[str, Any]]:
    """统计某领域命中的相关位点数 + 整体方向。

    **不是 PRS**:不返回 percentile / risk_level / score。
    variants: [{gene_name, genotype, result_label, ...}]
    domain: _LOCUS_DIRECTIONS 的 key
    """
    geno_directions_by_gene = _LOCUS_DIRECTIONS.get(domain)
    if not geno_directions_by_gene:
        return None

    by_gene: Dict[str, str] = {}
    for v in variants:
        name = (v.get("gene_name") or "").upper()
        geno = v.get("genotype") or v.get("result_label") or ""
        if name:
            by_gene.setdefault(name, geno)

    loci_matched = 0          # 命中且方向非中性 (能影响整体方向) 的位点数
    loci_tested = 0           # 用户测过且能精确匹配上的位点数
    raise_count = 0           # 偏"升高方向"的位点
    lower_count = 0           # 偏"降低方向"的位点
    direction_sum = 0.0       # 仅用于决定整体方向符号,不对外输出为分数
    loci: List[Dict[str, Any]] = []

    for gene, geno_directions in geno_directions_by_gene.items():
        geno = by_gene.get(gene, "")
        if not geno:
            continue
        direction = _match_direction(geno, geno_directions)
        if direction is None:
            loci.append({"gene": gene, "genotype": geno, "direction": "unknown", "note": "unmatched"})
            continue

        loci_tested += 1
        direction_sum += direction
        if direction > 0:
            dir_label = "raise"
            raise_count += 1
            loci_matched += 1
        elif direction < 0:
            dir_label = "lower"
            lower_count += 1
            loci_matched += 1
        else:
            dir_label = "neutral"
        loci.append({"gene": gene, "genotype": geno, "direction": dir_label})

    if not loci:
        return None

    if direction_sum > 0:
        overall_direction = "raise"
    elif direction_sum < 0:
        overall_direction = "lower"
    else:
        overall_direction = "neutral"

    return {
        "domain": domain,
        "loci_matched": loci_matched,      # 非中性命中数
        "loci_tested": loci_tested,        # 精确匹配上的位点数
        "loci_available": len(geno_directions_by_gene),
        "overall_direction": overall_direction,  # raise | lower | neutral
        "raise_count": raise_count,
        "lower_count": lower_count,
        "disclaimer": DISCLAIMER,
        "loci": loci,
    }


def compute_all_locus_summaries(variants: List[Dict[str, Any]]) -> Dict[str, Any]:
    """计算所有领域的相关位点方向汇总 (非 PRS)。"""
    results: Dict[str, Any] = {}
    for domain in _LOCUS_DIRECTIONS:
        summary = compute_locus_summary(variants, domain)
        if summary:
            results[domain] = summary
    return results
