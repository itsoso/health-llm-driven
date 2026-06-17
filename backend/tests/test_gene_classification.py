"""Phase 1 genetic interpretation: two-dimensional static classification.

`classify_variant` overlays an orthogonal (actionability, evidence_grade) axis
on top of the existing gene_knowledge_audit tiers — purely static table-driven,
never an LLM. These tests lock the tier→two-dim mapping and the consumer-chip
proxy guardrail.
"""

from app.services.genetic_registry import (
    DE_EMPHASIZE_PREFIX,
    PROXY_UNCERTAIN_SUFFIX,
    classify_variant,
    is_proxy_variant,
)


class TestClassifyVariantByTier:
    def test_tier0_pgx_gene_is_act_cpic_a(self):
        # CYP2C19 / CYP2D6 are tier0_pharmacogenomics → act + cpic_a
        assert classify_variant("CYP2C19") == ("act", "cpic_a")
        assert classify_variant("CYP2D6") == ("act", "cpic_a")

    def test_tier0_hla_star_allele_is_act_pharmgkb_1a(self):
        # HLA star-alleles carry FDA-label / PharmGKB-1A weight, not a single
        # CPIC dosing guideline.
        assert classify_variant("HLA-B*15:02") == ("act", "pharmgkb_1a")
        assert classify_variant("HLA-A*31:01") == ("act", "pharmgkb_1a")
        assert classify_variant("HLA-B*58:01") == ("act", "pharmgkb_1a")

    def test_tierx_confirmation_only_is_act_clinvar_path_confirm(self):
        # BRCA / CFTR / ATP7B → act + clinvar_path_confirm (refer + confirm seq)
        assert classify_variant("BRCA1") == ("act", "clinvar_path_confirm")
        assert classify_variant("BRCA2") == ("act", "clinvar_path_confirm")
        assert classify_variant("CFTR") == ("act", "clinvar_path_confirm")
        assert classify_variant("ATP7B") == ("act", "clinvar_path_confirm")

    def test_tier1_lab_anchored_is_risk_stratify(self):
        # APOE / MTHFR / ALDH2 / HFE → risk_stratify + clinvar_likely
        assert classify_variant("APOE") == ("risk_stratify", "clinvar_likely")
        assert classify_variant("MTHFR") == ("risk_stratify", "clinvar_likely")
        assert classify_variant("ALDH2") == ("risk_stratify", "clinvar_likely")
        assert classify_variant("HFE") == ("risk_stratify", "clinvar_likely")
        # FADS1 / 9p21 → risk_stratify + gwas_association (association-grade)
        assert classify_variant("FADS1") == ("risk_stratify", "gwas_association")
        assert classify_variant("9p21") == ("risk_stratify", "gwas_association")

    def test_tier2_lifestyle_is_de_emphasize_gwas(self):
        # FTO / ACTN3 / COMT / ADORA2A / VDR → de_emphasize + gwas_association
        assert classify_variant("FTO") == ("de_emphasize", "gwas_association")
        assert classify_variant("ACTN3") == ("de_emphasize", "gwas_association")
        assert classify_variant("COMT") == ("de_emphasize", "gwas_association")
        assert classify_variant("ADORA2A") == ("de_emphasize", "gwas_association")
        assert classify_variant("VDR") == ("de_emphasize", "gwas_association")

    def test_unmapped_gene_defaults_to_de_emphasize(self):
        # Safest bucket for anything not in any tier.
        assert classify_variant("CYP1A2") == ("de_emphasize", "gwas_association")
        assert classify_variant("TOTALLY_UNKNOWN_GENE") == (
            "de_emphasize",
            "gwas_association",
        )

    def test_empty_input_defaults_to_de_emphasize(self):
        assert classify_variant("") == ("de_emphasize", "gwas_association")


class TestClassifyVariantByRsid:
    def test_rsid_resolves_to_gene_tier(self):
        # rs671 → ALDH2 (tier1); rs1801133 → MTHFR (tier1)
        assert classify_variant("rs671") == ("risk_stratify", "clinvar_likely")
        assert classify_variant("rs1801133") == ("risk_stratify", "clinvar_likely")

    def test_unknown_rsid_falls_back_to_default(self):
        assert classify_variant("rs00000000") == ("de_emphasize", "gwas_association")


class TestConsumerChipProxyGuardrail:
    def test_proxy_locus_forces_proxy_uncertain_grade(self):
        # indel / structural / HLA-proxy genotyping cannot confirm or exclude:
        # evidence_grade is forced to proxy_uncertain regardless of tier.
        action, grade = classify_variant("rs5030655")  # CYP2D6 indel proxy
        assert grade == "proxy_uncertain"
        # actionability is preserved from the underlying tier (CYP2D6 = act)
        assert action == "act"

    def test_hla_proxy_marker_keeps_act_and_pharmgkb_grade(self):
        # ADVERSARIAL REGRESSION (safety blocker): rs1265181 is the HLA-B*58:01
        # tag SNP for allopurinol SJS/TEN — a LETHAL pharmacogenomic allele.
        # KNOWN_SNPS spells the gene `HLA-B*5801` (no colon) while the tier0 table
        # uses `HLA-B*58:01`; the colon mismatch previously dropped it to the
        # de_emphasize default. The earlier test discarded actionability and so
        # "stayed green while masking the danger". We now assert the full tuple
        # against the REGISTRY's real spelling, not the idealized colon name.
        action, grade = classify_variant("rs1265181")  # hla_proxy_marker
        assert action == "act", (
            "rs1265181 (HLA-B*58:01, allopurinol SJS/TEN) must be ACT, not "
            f"de_emphasize — got {action!r}"
        )
        # HLA carries FDA-label / PharmGKB-1A weight; the proxy 'negative ≠ no
        # risk' caveat is preserved by is_proxy_variant for the formatter, so the
        # grade itself must NOT be softened to proxy_uncertain for a lethal allele.
        assert grade == "pharmgkb_1a"
        assert is_proxy_variant("rs1265181") is True

    def test_hla_no_colon_and_colon_forms_align_to_act(self):
        # The normalizer must align BOTH spellings of every HLA star-allele to the
        # same tier0 entry — not a single hard-coded id.
        assert classify_variant("HLA-B*5801")[0] == "act"
        assert classify_variant("HLA-B*58:01")[0] == "act"
        assert classify_variant("HLA-B*5801") == ("act", "pharmgkb_1a")
        assert classify_variant("HLA-B*58:01") == ("act", "pharmgkb_1a")

    def test_carbamazepine_hla_tag_snp_is_act_and_proxy(self):
        # rs1061235 is the consumer-chip tag SNP for HLA-A*31:01 (carbamazepine
        # SCAR) — the SECOND lethal tier0 HLA allele alongside rs1265181. It must
        # surface as ACT/pharmgkb_1a AND be flagged as a proxy so the formatter
        # keeps the "negative ≠ no risk" caveat (it previously did not, leaving
        # the allopurinol allele guarded but the carbamazepine one bare).
        assert classify_variant("rs1061235") == ("act", "pharmgkb_1a")
        assert is_proxy_variant("rs1061235") is True

    def test_haplotype_component_is_not_a_proxy_guardrail(self):
        # rs429358 (APOE haplotype component) is NOT in the proxy guardrail set,
        # so it keeps its tier1 evidence grade rather than proxy_uncertain.
        assert classify_variant("rs429358") == ("risk_stratify", "clinvar_likely")


class TestDisclaimerConstants:
    def test_de_emphasize_prefix_text(self):
        assert "群体弱关联" in DE_EMPHASIZE_PREFIX
        assert "个体无预测力" in DE_EMPHASIZE_PREFIX
        assert "非诊断" in DE_EMPHASIZE_PREFIX

    def test_proxy_suffix_text(self):
        assert "阴性不代表无风险" in PROXY_UNCERTAIN_SUFFIX
