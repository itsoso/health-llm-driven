# Genetic KB Actionability Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the down-dedao genetic knowledge base from broad risk notes into an actionability-tiered rule system that prevents DTC genetic false positives and prioritizes medication safety.

**Architecture:** Keep `/Users/liqiuhua/work/personal/down-dedao` as the authoring source, but gate promotion through repeatable audits in `health-llm-driven`. The serving system should consume reviewed `gene_knowledge.json` only after Tier 0 drug-safety coverage, Tier X confirmation-only boundaries, and claim quality gates pass.

**Tech Stack:** Python 3.12, JSON artifacts, Markdown wiki claims/entities, pytest, existing `gene_knowledge.json` registry and System KB V2 import pipeline.

---

## Current Baseline

Generated report: `docs/reports/2026-05-22-gene-knowledge-audit.md`

Current `down-dedao/artifacts/gene_knowledge.json`:

- Gene entities: 14
- SNP registry entries: 22
- Claims: 18
- Gene rules: 10
- Tier 0 drug-safety coverage: 4/12
- Tier 1 gene + lab loop coverage: 7/7
- Tier X confirmation-only coverage: 0/4

Main gaps:

- Missing Tier 0 rules: `HLA-A*31:01`, `HLA-B*15:02`, `HLA-B*58:01`, `VKORC1`, `G6PD`, `DPYD`, `TPMT`, `NUDT15`
- Missing confirmation-only boundaries: `CFTR`, `ATP7B`, `BRCA1`, `BRCA2`
- Current quality gates pass for existing claims: no missing `applies_when`, no missing boundary text, no drug claim missing clinician boundary

Do not edit `down-dedao` blindly right now: its worktree already has many user/generated changes. First use the audit report as the shared checklist, then modify source wiki files in small batches.

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

**Source files in `down-dedao`:**

- Create: `wiki/entities/gene/CFTR.md`
- Create: `wiki/entities/gene/ATP7B.md`
- Create: `wiki/claims/c_cftr_dtc_confirmation_boundary.md`
- Create: `wiki/claims/c_atp7b_dtc_confirmation_boundary.md`

**Rules:**

- `clinical_status` must be `requires_confirmation` or represented in metadata as `actionability_tier: confirmation_only`.
- `applies_when` must match genotype presence, but advice must point to confirmatory testing, not diagnosis.
- Body must explicitly say DTC SNP data is not enough to diagnose cystic fibrosis, Wilson disease, or carrier state.
- Do not create `gene_rules` entries that would appear as medication or disease high-risk rules.

**Verification:**

1. Compile down-dedao artifacts using its existing compiler.
2. Re-run `backend/scripts/audit_gene_knowledge.py`.
3. Expected: Tier X coverage includes `CFTR` and `ATP7B`.

## Task 3: Add Highest-Value HLA Medication Rules

**Source files in `down-dedao`:**

- Create: `wiki/entities/gene/HLA-A*31:01.md`
- Create: `wiki/entities/gene/HLA-B*15:02.md`
- Create: `wiki/entities/gene/HLA-B*58:01.md`
- Create claims for carbamazepine and allopurinol safety boundaries.

**Rules:**

- HLA claims must be medication-safety claims, not disease-risk claims.
- Include clinician boundary and avoid self-discontinuation language.
- Prefer CPIC/PharmGKB/FDA/label/guideline source IDs in `sources`.

**Verification:**

1. Audit must reduce missing Tier 0 rules by at least 3.
2. Quality gates must remain zero.
3. User 3 report must keep `HLA-A*31:01` high priority only under drug safety.

## Task 4: Add Core PGx Expansion

**Source files in `down-dedao`:**

- `VKORC1` + warfarin dose boundary
- `G6PD` + oxidant drugs / hemolysis boundary
- `DPYD` + fluoropyrimidine toxicity boundary
- `TPMT` and `NUDT15` + thiopurine myelosuppression boundary

**Rules:**

- These belong to Tier 0.
- They require external authority source IDs before promotion.
- Where DTC raw data cannot infer star allele/phenotype reliably, mark the rule as requiring clinical PGx confirmation.

**Verification:**

1. Audit Tier 0 coverage target: at least 10/12.
2. Missing authority source count should be zero for any promoted Tier 0 claim.

## Task 5: Wire Audit Into Promotion Workflow

**Files:**

- Modify: `backend/scripts/absorb_down_dedao_wiki.py`
- Modify or create tests under `backend/tests/`

**Behavior:**

- After absorbing down-dedao gene artifacts, run gene knowledge audit.
- Fail only on quality-gate violations by default.
- Print Tier 0/Tier X gaps as warnings until coverage is complete.

**Verification:**

1. Existing down-dedao bridge tests pass.
2. New audit workflow test proves a missing `applies_when` claim blocks promotion.

## Task 6: User 3 Regression Suite

**Files:**

- Modify: `backend/tests/test_genetic_improvements.py`
- Modify: `backend/tests/test_genetic_report.py`

**Required cases:**

- `CFTR` and `ATP7B` are not counted as high disease risk.
- `HLA-A*31:01` remains high-priority medication safety.
- `MTHFR` is interpreted as lab-anchored, requiring Hcy/B12/folate context.
- CYP phenotype claims that require star-allele confirmation must not overstate certainty.

**Verification:**

1. Run targeted genetic tests.
2. Re-run real user 3 analysis after source artifacts are promoted.

