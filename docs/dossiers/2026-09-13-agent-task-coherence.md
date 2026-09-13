# Agent task coherence implementation

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | S5 |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

Status: implementation. Controller: health-harness-orchestrator; overlay: safety-gate.

User authorization: implement the Hermes/OpenClaw comparison recommendations, retaining Pi. Existing conversation authorizes delivery after checks; gates remain mandatory. Unrelated Mac shopping/model work is excluded.

Evidence and design: `docs/analysis/2026-09-13-pi-agent-intelligence-review.md` and `docs/analysis/2026-09-13-hermes-openclaw-architecture-comparison.md`.

## Scope and acceptance

- Unify answer drafting versus durable plan writes and conversational repair.
- Allow composable owned reads and explicit Garmin synchronization without relying on whole-utterance allowlists. Preserve ownership, cancellation, quoted-input and write confirmation boundaries.
- Return actionable recoverable tool errors with bounded retries; preserve hard authorization denials.
- Connect synchronization and subsequent reads through existing task/run state and truthful result evidence.
- Preserve message time provenance and return coherent safe final answers instead of repeated withheld placeholders.
- Reuse existing memory and Skill systems; no automatic alteration of medical policy or blanket write authority.
- Validate unseen paraphrases, multi-turn paths, PostgreSQL isolation and actual Pi trajectories. No production health write fixtures.

## Ownership

- root: read capability, retry/loop integration, Garmin state, integration and delivery.
- completion_contract: utterance classification and its tests.
- quoted_input: guidance validation, conversation history projection and their tests.
- independent safety reviewer: fixed committed diff, after implementation.

## Gates

- G3: pending RED/GREEN and integration evidence.
- G4: pending fixed-diff independent safety review.
- G5/G6: pending release gates and actual production verification; no new release claimed.

## G1 — bounded behavior repair

裁决: PASS

The user accepted the architecture review and explicitly requested implementation. This restores requested owned reads, distinguishes advice drafts from writes, and keeps existing authentication, consent, clinical safety, and persistence contracts. It adds no Health OS object or new data-write authority.

## Candidate integration

The shared checkout contains unrelated Mac work and remains preserved. Delivery uses the independent clean-index candidate checkout `health-coherence-release`, based on upstream `22e2f5775473dd069e8e420857af54a9c8c77633`. Upstream Garmin account-status reads and this change's correlated job observations are separate evidence; a historical success is never a current-job receipt.

Longitudinal actual-record requests cover explicitly requested diet, sleep, workout, and supplement intake. Their default recent window is seven calendar days, disclosed with frozen dates. Historical diagnosis background does not select the read window. Actual supplement intake includes inactive definitions with owned taken logs; plans do not prove intake. Mood and work context without an actual reader remain explicitly unqueried. Ambiguous longer windows are not silently replaced with seven days. A brief authorized continuation retains the frozen window and original expiry.

Independent regressions include the original oral HTTP/MCP/Skills structure, multiple requested domains, negation versus 分别, another person's subject followed by 给我建议, owner/window filtering, and missing-domain completion. Provider-scripted Pi execution is distinct from paid model verification.

## Candidate G3 evidence — 2026-09-13

The fixed candidate source passed 8,884 test executions with seven explicit SQLite skips. This includes 232 PostgreSQL executions, the independent actual Pi/actual adapter longitudinal regression, and preserved upstream Garmin behavior. All application Python fingerprints remained unchanged across the run. Separate independent task validation passed its 32 scenarios against this candidate (SQLite only).

The existing live synthesis regression retained main baselines and passed invariants 12/12, health_agent_core 50/50, orchestrator 5/5 (mean score 0.94), trajectory contract 12/12, and golden contract 9/9. Ten tracked calls reserved 17,211 tokens; consent and quota guards remained active. The initial incorrectly configured harness was rejected before provider transmission; that failed report is retained. Model-specific original oral request and continuation acceptance is still pending, so G3 is not yet a final release verdict.

System Map, dossier consistency, Skill governance, static error lint and tracked-secret checks passed. No migrations, native changes or new public API endpoints are introduced. G4 independent fixed-commit review, current-main CI, candidate exact-revision CI and production validation remain required. Production was read-only verified at `42ba9fcc7667d9f884925f4204bf1563327624d5` with backend and both Celery services active; this is not evidence of this candidate's deployment.

## First independent review — historical rejection

The first review returned NO-GO on the superseded candidate; the active G4 remains pending re-review.

Independent reviewer rejected fixed commit `9b294c2d2af8bb34330292e8a0c3d59b90419554`: an explicit calendar-day prefix could widen to the default week, and a failed new Garmin submission could reuse an old successful receipt. Neither was published. New regressions cover exact-day rejection/binding and actual Pi persistence of a null receipt boundary, including the later follow-up. Current-turn status reads no longer search old receipts when a new sync was requested.

The original oral request with real qwen3.8-max-preview autonomously selected `health_query_batch`; actual four-domain rows, ownership, dates, inactive supplement intake and unchanged health state passed. Final acceptance failed: batch actual-record evidence was not projected, and an information request about an existing supplement regimen was falsely treated as a new prescription. Both are corrected, with malformed/unsafe negative tests retained. The original model also made unsupported recovery, duplicate-record and whole-day-intake assumptions; synthesis instructions now explicitly prohibit those inferences and require calibrated advice. The final medical guard remains active.

The first live oracle also incorrectly required private query arguments in public goal metadata. The oracle was corrected to compare actual normalized dispatches and server-owned task metadata against verified goal IDs; the two false failures are separately recorded, while the three real failures remain failures. No public completion schema was widened to satisfy an evaluation. Original reports are retained. A new fixed-commit independent review and fresh actual-model acceptance are required.


## Second independent review — historical rejection

The second review returned NO-GO on `f72b07613db56eb0230224c7e0ec6e7156e1ed81`; it was not published. Unsupported explicit restrictions such as a morning or event-relative interval could still fall through to a calendar/week read. Restriction clauses must now be completely consumed by the existing date/domain grammar before any single, batch, or list fallback; unrecognized limits require clarification. Positive calendar, recent-window and domain-only cases remain accepted.

The review also found an information-question exception could hide an appended prescription. The exception no longer exempts an entire greedy action match. Only a directed request for existing information is projected; subsequent actions and nominal timing changes remain checked. An additional local/independent probe found broad noun replacement could hide a timing adjustment; that interim approach failed its RED tests and was narrowed before committing.

The second original oral live replay autonomously executed four actual-domain queries successfully but failed final acceptance because a request to supply a recorded服用时间 field was misclassified as prescription. That report remains failed. Fresh scope regression passed 192 cases and guidance regression passed 122, including the new bypass/false-positive pairs. The intervening incorrectly configured SQLite TEST_DATABASE_URL run was rejected by the fixture and is not passing evidence. A new fixed-commit review, original oral plus continuation live acceptance, and revision-bound release checks remain pending.
