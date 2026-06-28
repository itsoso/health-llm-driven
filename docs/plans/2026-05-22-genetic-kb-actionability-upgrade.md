# Genetic KB Actionability Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the down-dedao genetic knowledge base from broad risk notes into an actionability-tiered rule system that prevents DTC genetic false positives and prioritizes medication safety.

**Architecture:** Keep `/Users/liqiuhua/work/personal/down-dedao` as the authoring source, but gate promotion through repeatable audits in `health-llm-driven`. The serving system should consume reviewed `gene_knowledge.json` only after Tier 0 drug-safety coverage, Tier X confirmation-only boundaries, and claim quality gates pass.

**Tech Stack:** Python 3.12, JSON artifacts, Markdown wiki claims/entities, pytest, existing `gene_knowledge.json` registry and System KB V2 import pipeline.

---

## Current Baseline

Latest generated report: `docs/reports/2026-05-23-gene-knowledge-audit.md`

Current `backend/data/gene_knowledge.json` audit result:

- Gene entities: 28
- SNP registry entries: 26
- Claims: 32
- Gene rules: 18
- Tier 0 drug-safety coverage: 12/12
- Tier 1 gene + lab loop coverage: 7/7
- Tier 2 lifestyle coverage: 5/5
- Tier X confirmation-only coverage: 4/4

Main gaps:

- No blocking coverage gaps remain in the promoted artifact.
- Current quality gates pass: no missing `applies_when`, no missing boundary text, no drug claim missing clinician boundary.

Do not edit `down-dedao` blindly: it is still the authoring source and may have user/generated changes. First use the audit report as the shared checklist, then modify source wiki files in small batches.

2026-06-28 re-check:

```bash
PYTHONPATH=backend backend/venv/bin/python backend/scripts/audit_gene_knowledge.py \
  --gene-knowledge backend/data/gene_knowledge.json \
  --output /tmp/gene-knowledge-audit.md
```

Result: Tier 0 `12/12`, Tier 1 `7/7`, Tier 2 `5/5`, Tier X `4/4`; all quality-gate counters are `0`.

## Task 1: Keep The Audit Gate Green

**Files:**

- Modify: `backend/app/services/gene_knowledge_audit.py`
- Modify: `backend/scripts/audit_gene_knowledge.py`
- Test: `backend/tests/test_gene_knowledge_audit.py`

**Steps:**

1. Run `cd backend && source .venv/bin/activate && pytest tests/test_gene_knowledge_audit.py -q`
2. Run `cd backend && source .venv/bin/activate && python scripts/audit_gene_knowledge.py --gene-knowledge ~/work/personal/down-dedao/artifacts/gene_knowledge.json --output ../docs/reports/2026-05-22-gene-knowledge-audit.md`
3. Review Tier 0 and Tier X gaps before adding any new risk claims.

## Task 2: Add Tier X Confirmation-Only Boundaries First

Status: completed. `CFTR`, `ATP7B`, `BRCA1`, and `BRCA2` are all covered by confirmation-only boundaries in the promoted artifact.

**Source files in `down-dedao`:**

- Created: `wiki/entities/gene/CFTR.md`
- Created: `wiki/entities/gene/ATP7B.md`
- Created: `wiki/entities/gene/BRCA1.md`
- Created: `wiki/entities/gene/BRCA2.md`
- Created: `wiki/entities/snp/rs121908763.md`
- Created: `wiki/entities/snp/rs149790377.md`
- Created: `wiki/entities/snp/rs186045772.md`
- Created: `wiki/entities/snp/rs137853280.md`
- Created: `wiki/claims/c_cftr_dtc_confirmation_boundary.md`
- Created: `wiki/claims/c_atp7b_dtc_confirmation_boundary.md`
- Created: `wiki/claims/c_brca1_dtc_confirmation_boundary.md`
- Created: `wiki/claims/c_brca2_dtc_confirmation_boundary.md`

**Rules:**

- `clinical_status` must be `requires_confirmation` or represented in metadata as `actionability_tier: confirmation_only`.
- `applies_when` must match genotype presence, but advice must point to confirmatory testing, not diagnosis.
- Body must explicitly say DTC SNP data is not enough to diagnose cystic fibrosis, Wilson disease, or carrier state.
- Do not create `gene_rules` entries that would appear as medication or disease high-risk rules.

**Verification:**

1. Compile down-dedao artifacts using its existing compiler.
2. Re-run `backend/scripts/audit_gene_knowledge.py`.
3. Expected: Tier X coverage includes `CFTR`, `ATP7B`, `BRCA1`, and `BRCA2`.

## Task 3: Add Highest-Value HLA Medication Rules

Status: completed on 2026-05-22 for `HLA-A*31:01`, `HLA-B*15:02`, and `HLA-B*58:01`.

**Source files in `down-dedao`:**

- Created: `wiki/entities/gene/HLA-A*31:01.md`
- Created: `wiki/entities/gene/HLA-B*15:02.md`
- Created: `wiki/entities/gene/HLA-B*58:01.md`
- Created: `wiki/claims/c_hla_a3101_carbamazepine_boundary.md`
- Created: `wiki/claims/c_hla_b1502_carbamazepine_oxcarbazepine_boundary.md`
- Created: `wiki/claims/c_hla_b5801_allopurinol_boundary.md`
- Created drug entities for `carbamazepine`, `oxcarbazepine`, `allopurinol`, and `febuxostat`.

**Rules:**

- HLA claims must be medication-safety claims, not disease-risk claims.
- Include clinician boundary and avoid self-discontinuation language.
- Prefer CPIC/PharmGKB/FDA/label/guideline source IDs in `sources`.

**Verification:**

1. Audit must reduce missing Tier 0 rules by at least 3.
2. Quality gates must remain zero.
3. User 3 report must keep `HLA-A*31:01` high priority only under drug safety.

## Task 4: Add Core PGx Expansion

Status: completed on 2026-05-22. Tier 0 drug-safety coverage is now 12/12.

**Source files in `down-dedao`:**

- Created: `wiki/entities/gene/VKORC1.md`
- Created: `wiki/entities/gene/G6PD.md`
- Created: `wiki/entities/gene/DPYD.md`
- Created: `wiki/entities/gene/TPMT.md`
- Created: `wiki/entities/gene/NUDT15.md`
- Created: `wiki/claims/c_vkorc1_warfarin_inr_boundary.md`
- Created: `wiki/claims/c_g6pd_oxidant_drug_hemolysis_boundary.md`
- Created: `wiki/claims/c_dpyd_fluoropyrimidine_toxicity_boundary.md`
- Created: `wiki/claims/c_tpmt_thiopurine_myelosuppression_boundary.md`
- Created: `wiki/claims/c_nudt15_thiopurine_myelosuppression_boundary.md`
- Created drug entities for `rasburicase`, `primaquine`, `dapsone`, `fluorouracil`, `capecitabine`, `tegafur`, `azathioprine`, `mercaptopurine`, and `thioguanine`.

**Rules:**

- These belong to Tier 0.
- They require external authority source IDs before promotion.
- Where DTC raw data cannot infer star allele/phenotype reliably, mark the rule as requiring clinical PGx confirmation.

**Verification:**

1. Audit Tier 0 coverage target: at least 10/12.
2. Missing authority source count should be zero for any promoted Tier 0 claim.

## Task 5: Wire Audit Into Promotion Workflow

Status: completed on 2026-05-22. `absorb_down_dedao_wiki.py` now includes the gene knowledge audit in its summary and exits non-zero when quality gates fail.

**Files:**

- Modify: `backend/scripts/absorb_down_dedao_wiki.py`
- Modify or create tests under `backend/tests/`

**Behavior:**

- After absorbing down-dedao gene artifacts, run gene knowledge audit.
- Fail only on quality-gate violations by default.
- Include Tier 0/Tier X gaps in the emitted audit summary until coverage is complete.

**Verification:**

1. Existing down-dedao bridge tests pass.
2. New audit workflow test proves a missing `applies_when` claim blocks promotion.

## Task 6: User 3 Regression Suite

Status: implemented for the core safety regressions. Targeted tests now cover confirmation-only disease handling, BRCA reviewed-KB lookup/eval cases, HLA actionability classification, MTHFR lab-anchored interpretation boundaries, and CYP proxy/star-allele uncertainty guards. Real user 3 re-analysis remains an operational check after artifact promotion, not a blocking implementation gap.

**Files:**

- Modify: `backend/tests/test_genetic_improvements.py`
- Modify: `backend/tests/test_genetic_report.py`
- Modify: `backend/tests/test_genetics_clinical_confirmation_knowledge.py`
- Modify: `backend/tests/test_gene_classification.py`

**Required cases:**

- `CFTR` and `ATP7B` are not counted as high disease risk.
- `HLA-A*31:01` remains high-priority medication safety.
- `MTHFR` is interpreted as lab-anchored, requiring Hcy/B12/folate context.
- CYP phenotype claims that require star-allele confirmation must not overstate certainty.

**Verification:**

1. Run targeted genetic tests.
2. Re-run real user 3 analysis after source artifacts are promoted.
