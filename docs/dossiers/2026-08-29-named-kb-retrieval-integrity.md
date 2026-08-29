# Dossier: Named knowledge-source retrieval integrity

| 字段 | 值 |
|---|---|
| slug | `named-kb-retrieval-integrity` |
| 创建日期 | 2026-08-29 |
| 当前阶段 | S6 安全评审 |
| 状态 | awaiting_independent_safety_rereview |
| 负责 | Codex |
| 反馈环 | production evidence -> regression RED -> implementation -> safety review -> backend release -> production replay |

## S0 · User request

> 分析最近的我的这次交互 问题还是挺多的 没有搜索到这个知识库
>
> 修复

## S1 · Discovery

- Production conversation `1903` confirmed that the first named-source turn
  used no tools and the correction turn used generic `knowledge_search` twice.
- `knowledge_search` accepts only query/count and serves reviewed System KB.
- The legacy `backend/knowledge/supplement_knowledge.md` carries the
  "益家知研 / 皮皮妈妈" labels but is not present in production `kb_documents`.
- MyKnowledge readable catalog has no health or named source matching those
  labels, so it cannot be substituted as the runtime source.
- The architecture contract requires reviewed System KB as medical serving
  authority and forbids raw runtime fallback.

## G1 · Admission

- Classification: production bugfix.
- Product objects: `HealthTwin`, `SafetyGuardian` evidence boundary.
- Surface: backend Agent chat.
- Safety: medical boundary; no prescription, dose, or source promotion.
- Feature spec: `docs/specs/active/2026-08-29-named-kb-retrieval-integrity.md`.
- **裁决**: PASS。

## G2 · Feasibility and safety pressure test

- Keep generic reviewed retrieval backward compatible.
- Deterministically route explicit named-source requests even if the model
  returns prose.
- Recover only the nearest preceding user health question.
- Known legacy alias returns `not_released`; unknown alias returns
  `unresolved`; neither may substitute another source.
- Do not expose raw legacy content or add a database migration.
- **裁决**: PASS。

## S4 · Tasks

- [x] T1 RED: named-source parser and continuation query recovery.
- [x] T2 RED: source-aware tool contract and fail-closed legacy/unknown source.
- [x] T3 RED: run-stream deterministic fallback when the model omits retrieval.
- [x] T4 GREEN: minimal implementation.
- [x] T5 G3 focused + LLM/repo gates.
- [ ] T6 G4 independent safety review.
- [ ] T7 commit, push, backend deploy, production replay.

## G3 · Test evidence

- Focused named-source and health-runtime suite: `164 passed`.
- Wider routing, health-evidence, tool-class, plausibility, and false-claim
  regression: `322 passed`.
- Live LLM gate, run through the existing local `health_test` PostgreSQL
  database so the budget guard remained active: invariants `12/12`,
  health-agent core `50/50`, orchestrator `5/5` with score `0.96`, trajectory
  contract `12/12`, trajectory goldens `9/9`.
- `harness_llm_change_gate.py`: PASS with the live-run confirmation.
- `check_doc_drift.py`, `check_dossier_consistency.py`, `py_compile`, targeted
  Ruff undefined-name/syntax checks, and `git diff --check`: PASS.
- The first two live-gate attempts were correctly rejected by environment
  configuration (system Python missing `psycopg2`; then the default local DB
  role was absent and OpenAI fallback returned 429). They are not counted as
  passing evidence; the later real MiniMax run above is the G3 evidence.
- **裁决**: PASS。

## G4 · Independent safety review

- First review of commit `01a03e414`: **BLOCK**, with no Critical and two
  Important findings:
  1. Unknown natural-language source names did not enter the deterministic
     guard, and a released alias could match as a substring of a different
     source name.
  2. Source-only continuation recovery could treat a non-health acknowledgement
     such as `谢谢` as the retrieval query.
- Remediation added RED/GREEN coverage for arbitrary source names, exact source
  preservation (`系统知识库测试版` remains unresolved), acknowledgement skipping,
  and refusal to fold unrelated older turns into a source-only request.
- Independent re-review: pending.

## Gate ledger

| Gate | Status | Evidence |
|---|---|---|
| G1 | PASS | Requirement admission above. |
| G2 | PASS | Fail-closed reviewed-only design above. |
| G3 | PASS | 164 focused + 322 wider tests; live LLM and repo gates passed. |
| G4 | pending | First review BLOCK remediated; independent re-review pending. |
| G5 | pending | Deployment health pending. |
| G6 | pending | Production replay pending. |

## Rollback

Backend code rollback only; no schema or data mutation.
