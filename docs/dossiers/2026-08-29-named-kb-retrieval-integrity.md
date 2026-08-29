# Dossier: Named knowledge-source retrieval integrity

| 字段 | 值 |
|---|---|
| slug | `named-kb-retrieval-integrity` |
| 创建日期 | 2026-08-29 |
| 当前阶段 | S8 上线验证 |
| 状态 | complete |
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
- [x] T6 G4 independent safety review.
- [x] T7 commit, push, backend deploy, production replay.

## G3 · Test evidence

- Focused named-source and health-runtime suite: `171 passed`.
- Wider routing, health-evidence, tool-class, plausibility, and false-claim
  regression: `322 passed`.
- Live LLM gate, run through the existing local `health_test` PostgreSQL
  database so the budget guard remained active: invariants `12/12`,
  health-agent core `50/50`, orchestrator `5/5` with score `0.92`, trajectory
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
- Second review: **BLOCK**, with no Critical and one Important finding. The
  extraction pattern still treated negated or historical prose such as
  `不要用系统知识库回答` and `小王根据蓝鲸健康库回答了...` as live retrieval
  instructions.
- Second remediation anchored the instruction grammar to the start of the user
  turn with a bounded polite prefix (`请` / `麻烦` / `帮我`). Five negated or
  historical examples first failed and then passed; positive direct and polite
  instructions remain covered.
- Third independent review of commit `5e20e0530`: **GO**, with no Critical or
  Important findings. The reviewer independently verified the five rejection
  examples, the three positive instruction forms, focused tests, static checks,
  and the earlier unknown-source/query-recovery/emergency coverage.
- Non-blocking follow-up: compound or continuation phrasing such as `请帮我用...`
  and `再用...` is not yet deterministic; the model schema path remains available.
- **裁决**: PASS。

## G5 · Deployment evidence

- Release code commit: `3d4b98e47aedd2593c809414dd1422ff0dca9eb5`.
- GitHub Actions run `33252752683`: `52/52` jobs completed successfully after
  rerunning the timed-out backend shard; there were no test assertion failures.
- Clean-main backend deployment completed with exit code `0`; remote revision
  matched `3d4b98e47aed`.
- Production health checks: `60/60` PASS before and after the staged runtime
  transaction.
- Runtime-only KB serving contract passed in guard and staged phases:
  `packs=1 targets=11 matched=11 generic=0 runtime=5`.
- Database backup, restore drill, encrypted offsite upload, hash verification,
  and HMAC authenticity verification completed before activation. No schema
  migration or KB content mutation was applied.
- **裁决**: PASS。

## G6 · Production replay

- Ran a read-only replay against the deployed production Python environment;
  it created no conversation or health record.
- `益家知研 这个在我知识库中` preserved `knowledge_source=益家知研` and
  recovered the nearest preceding health question.
- The deployed executor returned the canonical source
  `益家知研 / 皮皮妈妈补剂知识库` with `source_status=not_released` and the
  explicit no-substitution boundary.
- An unknown named source returned `source_status=unresolved` without generic
  KB fallback; `不要使用系统知识库回答` created no deterministic retrieval call.
- Replay marker:
  `NAMED_KB_PRODUCTION_REPLAY_OK source=益家知研 query_recovered=1 legacy_fail_closed=1 unknown_fail_closed=1 negation_not_triggered=1`.
- This verifies retrieval integrity, not publication of the legacy knowledge
  asset. The named content remains unavailable until it passes a separate
  medical-review and System KB ingestion lifecycle.
- **裁决**: PASS。

## Gate ledger

| Gate | Status | Evidence |
|---|---|---|
| G1 | PASS | Requirement admission above. |
| G2 | PASS | Fail-closed reviewed-only design above. |
| G3 | PASS | 171 focused + 322 wider tests; live LLM and repo gates passed. |
| G4 | PASS | Third independent review GO; no Critical or Important findings. |
| G5 | PASS | CI 52/52; clean-main deployment; production health 60/60. |
| G6 | PASS | Read-only production named-source replay passed. |

## Rollback

Backend code rollback only; no schema or data mutation.
