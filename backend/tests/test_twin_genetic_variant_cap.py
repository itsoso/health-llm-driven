"""Twin genetic partition must never drop safety-relevant variants.

Regression (safety review 2026-10-02): ``fetch_genetic_variants_categorized``
kept only the first 15 variants per category (and 10 per drug/risk/protective
bucket). The registry has 18 nutrition SNPs and HFE C282Y (rs1800562) is the
17th, so a full upload silently dropped it and the SupplementAdvisor iron hard
block never fired. Structured Twin data must be complete; only the prompt-blob
formatter may truncate, and it must stay bounded.

All genotypes below are synthetic.
"""
from __future__ import annotations

from datetime import date

from app.agents.supplement_advisor import SupplementAdvisorSpecialist
from app.models.genetic_data import GeneticProfile, GeneticVariant
from app.services.genetic_registry import KNOWN_SNPS
from app.twin import build_twin
from app.twin._collectors import fetch_genetic_variants_categorized
from app.twin.formatter import _format_genetic_variants_blob, twin_to_prompt_blob
from app.twin.schema import HealthTwin, TwinMeta

HFE_RSID = "rs1800562"


def _seed_profile(db, user_id: int, rsids: list[str], *, nature) -> None:
    profile = GeneticProfile(
        user_id=user_id,
        test_provider="synthetic",
        test_date=date(2026, 1, 1),
        notes="synthetic test profile",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    for rsid in rsids:
        snp = KNOWN_SNPS[rsid]
        db.add(
            GeneticVariant(
                user_id=user_id,
                profile_id=profile.id,
                rsid=rsid,
                category=snp["category"],
                gene_name=snp["gene"],
                variant_name=str(snp.get("variant") or rsid),
                genotype="C282Y/C282Y" if rsid == HFE_RSID else "AG",
                result_label="synthetic",
                risk_level="medium",
                variant_nature=nature,
            )
        )
    db.commit()


def _registry_rsids(category: str | None = None) -> list[str]:
    return [r for r, v in KNOWN_SNPS.items() if category is None or v["category"] == category]


def test_registry_order_puts_hfe_past_the_old_cap():
    """Guard the premise: HFE sits beyond index 15 in the nutrition order."""
    nutrition = _registry_rsids("nutrition")
    assert len(nutrition) > 15
    assert nutrition.index(HFE_RSID) >= 15


def test_all_nutrition_variants_reach_twin_partition(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    nutrition = _registry_rsids("nutrition")
    # nature=None → only the category bucket carries them (no risk-bucket rescue)
    _seed_profile(db, user.id, nutrition, nature=None)

    gen = fetch_genetic_variants_categorized(db, user.id)
    assert gen["total"] == len(nutrition)
    assert [v["rsid"] for v in gen["nutrition_variants"]] == nutrition

    twin = build_twin(db, user_id=user.id, use_cache=False)
    rsids = {v.get("rsid") for v in twin.genetic.nutrition_variants}
    assert HFE_RSID in rsids
    assert len(twin.genetic.nutrition_variants) == len(nutrition)


def test_full_registry_upload_keeps_every_bucket_complete(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    every = _registry_rsids()
    _seed_profile(db, user.id, every, nature="risk")

    gen = fetch_genetic_variants_categorized(db, user.id)
    assert gen["total"] == len(every)
    drug = [r for r in every if "drug" in KNOWN_SNPS[r]["category"]]
    non_drug = [r for r in every if r not in drug]
    assert [v["rsid"] for v in gen["drug_sensitivity"]] == drug
    assert [v["rsid"] for v in gen["risk"]] == non_drug
    for cat in ("nutrition", "cognition", "sleep", "recovery", "exercise", "personality"):
        assert len(gen[f"{cat}_variants"]) == len(_registry_rsids(cat))


def test_full_upload_hfe_hard_block_fires(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    _seed_profile(db, user.id, _registry_rsids(), nature=None)

    twin = build_twin(db, user_id=user.id, use_cache=False)
    finding = SupplementAdvisorSpecialist().run(twin, {})
    blocks = [x for x in finding.findings if x.get("type") == "hard_block"]
    assert len(blocks) == 1
    assert "铁" in blocks[0]["supplement"]


def test_prompt_blob_stays_bounded_with_full_registry(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    _seed_profile(db, user.id, _registry_rsids(), nature="risk")
    twin = build_twin(db, user_id=user.id, use_cache=False)
    assert twin.genetic.total_variants == len(KNOWN_SNPS)

    max_genes = 8
    lines = _format_genetic_variants_blob(twin.genetic, max_genes=max_genes)
    assert 0 < len(lines) <= 3
    for line in lines:
        assert line.split(": ", 1)[1].count("; ") <= max_genes - 1

    # Whole blob for a genetics-only twin stays small regardless of variant count.
    gen_only = HealthTwin(meta=TwinMeta(user_id=user.id, generated_at=twin.meta.generated_at))
    gen_only.genetic = twin.genetic
    gen_only.gene_config = None
    assert len(twin_to_prompt_blob(gen_only)) < 2500
