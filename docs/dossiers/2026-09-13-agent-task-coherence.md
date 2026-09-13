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


## Third independent review — historical rejection

The third reviewer rejected `6ff1196b6ceb811ae71775a0c477607ca8f45125`: restriction markers behind polite prefixes or scope labels were missed, domain conjunctions were over-restricted, and the new unresolved-scope denial could dispatch in shadow mode. The revised rejection boundary discovers markers independent of position, fully consumes calendar/domain scope, retains subject semantics, and rejects unrepresentable subday limits. It only guards its supported domains/retrospective scope, preserving existing unrelated illness and step readers. Unbound scope now requires new user clarification, is terminal across policy modes, and is never automatic parameter repair.

On the third fixed source, the broad policy lane had six regressions (5,594 passed); they exposed unrelated-domain overblocking and remain recorded as failed. Other lanes passed: 625 coherence, 1,136 evidence/guidance/executor and 129 PostgreSQL, with seven explicit SQLite skips. Fingerprints were stable. This is not a final G3 acceptance.

The third original oral live run again passed actual four-domain reads but failed final response acceptance: the noun补充剂 in a reference title matched the action补充. Lexical disambiguation preserves actual action/dose/timing-change guards and does not exempt sentences or quoted references. The old candidate is retained; offline revalidation of that exact candidate and 126 guidance tests passed after the fix. The new restriction regression passed 225 tests; shadow/enforce gateway and retry tests passed 58. Fresh fixed-source integration and live gates remain required.

An independently produced production-query fix `fce0e92f302e64f1745fc23a3a1f747335d20b15` was cherry-picked as `a6ea838f6`: dated colloquial吃的/吃得怎么样 questions now bind to the existing exact-day reader. Its independent review passed, and its author verified 30 PostgreSQL cases, including owner/day isolation. Final integrated review still applies. The reported false已取得健康数据 progress was separately reproduced: JSON rejection was considered success by three SSE producers. They now reuse the existing structured failure classifier; real Pi/gateway and persisted progress regressions passed 12 cases plus 89 adjacent tests, including valid zero values and row-level error text.


## Fourth independent review — historical rejection

The independent review of `55557ffc33bafda2507f5e671c957e8ae90fae21` returned NO-GO. A day substring could still discard an evening or event-relative restriction, while unrelated narrative morning context could incorrectly block an explicit recent read. The replacement projects query/scope clauses once and requires complete scope consumption. Unknown fragments cannot silently select the default week. Existing domain, ownership, cancellation, quote and sync semantics must remain authoritative.

That fixed revision passed 7,629 test executions with eight explicit SQLite skips, including 184 PostgreSQL executions; all application fingerprints stayed unchanged. This did not override the independent review. Its real original oral request with qwen3.8-max-preview completed four actual owned reads, verified goals, evidence and final generation. The same-conversation continuation also read successfully, then exceeded the provider's 120-second generation limit while producing a long report. This is a generation failure, not a medical rejection or unexecuted query. Flash acceptance was not run after the first failure. The final source must complete both models and continuation before release.

The next projection attempt was independently tested before freezing: unknown nominal scopes could disappear and were corrected. Fresh broad integration then exposed false denials on existing sync, retrospective and illness readers. Those failing results are retained; the active gates remain pending. Ordinary review synthesis now requests a concise complete answer and incremental continuation without changing provider timeouts or hiding incomplete generation.

## Colloquial production repair — release validation in progress

The separate minimal candidate `fce0e92f302e64f1745fc23a3a1f747335d20b15` passed its independent review, exact-date/owner PostgreSQL tests and CI-mode lanes (520 passed, ten explicit skips). It has not been pushed or deployed. A real-model replay confirmed the original colloquial request reaches the correct diet read. The initial external oracle mistakenly reused a two-domain daily-summary contract and overly narrow count/total wording; those oracle failures are distinguished from product defects. The candidate correctly stated three records totaling 1020 kcal, then speculated that matching records were duplicates and used a conditional 720 kcal as actual intake, inferred missing nutrients from missing fields, and suggested actions from those assumptions. No health rows changed. The corrected single-diet oracle accepts the count and recorded total but rejects the missing complete-day distinction. The daily evaluation repair will reuse existing deterministic facts without querying sleep or treating generation failure as query failure. This smaller release does not complete the long-request/continuation objective.


Production verification preparation confirmed the existing screenshot run belongs to its conversation owner and that current AI consent is accepted. The server is still on `42ba9fcc7667d9f884925f4204bf1563327624d5`. This was a read-only preflight with no provider call. After a successful release, the bounded diagnostic will use that owner, normal short-lived authentication and consent, and only read-classified tools. It will persist the normal conversation/audit/usage result, seed no health fixtures, and output metadata rather than health content. Backend executor/adapters are the explicit verification boundary; this cannot stand in for client UI acceptance.


## Daily evaluation independent review — historical rejection

The minimal diet candidate was fixed as `a6238bc81e21c0245d556e99f01d5b2d459f7762`. Fresh synthetic Pi/nearby tests passed 394 executions with one PostgreSQL-only skip. Independent CI-mode validation passed 716 executions with ten explicit skips; a separate PostgreSQL run passed 65. Start/end revision, tree and runtime hashes matched. Static, System Map and tracked-secret checks also passed.

Independent G4 still returned NO-GO. A valid advice heading could carry the same observed unsupported nutrient-deficit or duplicate-record/deletion inference; those outputs were persisted and falsely marked completed. Future-work statements with no verb object were also falsely verified. All four independent synthetic Pi probes failed. These are unresolved behavior defects, not waived by the passing tests. This revision has not been pushed, deployed, or subjected to another paid replay. It returns to implementation and requires a new independent fixed-commit review.

The broader projection compatibility repair passed its 253 focused cases, then completed the full policy lane without truncation: 5,587 passed and thirteen failed. The remaining failures cover already-supported multiple comparison windows and ordinary sleep/read-plus-draft frames. They remain blockers. An initial coherence runner used the wrong cwd for source-inspection tests; those nine FileNotFoundError cases are harness failures and are rerun only after that process exited, using the candidate backend with no environment file. No failing execution is counted as passing evidence.


## Projection compatibility repair — fixed source ready for review

The shared projection now defers only fully resolved existing comparison windows/clinical entities to their original binders, consumes unknown restrictions completely, and uses the existing read-act/draft/sync semantics. Full policy revalidation passed 5,600 tests; the complete coherence lane plus query outcomes passed 791 with eight explicit skips. Both processes exited zero and every application source fingerprint stayed unchanged. The previous thirteen failures and wrong-cwd runner remain retained historical failures. Additional unchanged-source evidence/guidance and PostgreSQL verification is running before final G3 acceptance.

The larger read/continuation repair does not depend on the newer daily evaluation synthesis experiment. These are independently reviewed release batches under this same controller. The first batch to pass its own fixed-source review, live acceptance and exact-revision CI may release serially; success in one batch does not complete the other user's acceptance path. No concurrent push or deployment is authorized by this arrangement.


## Fifth independent review — historical rejection

Fixed `36c7cb32fb1133a374ca488c4f5ea9348158d204` passed the full 5,600 policy cases, 791 coherence/outcome cases with eight skips, 1,152 evidence/guidance cases and 214 PostgreSQL cases. Source hashes remained stable; independent original-request coverage also passed 32 cases. Nevertheless, new G4 returned NO-GO: the query projection still conditioned complete consumption on a recognized time token. A post-domain parenthesis or modifier could disappear, and a request predicate shaped like 我是要早餐后的 was erased as narrative. The independent gateway matrix recorded twenty failures and twenty-eight passes across enforce/shadow and single/batch dispatch; the existing nearby 331 cases passed. No paid run or deployment was started. The repair now requires complete query-object/modifier consumption instead of detecting additional time keywords.

The separate daily-evaluation repair is fixed as `5a2e539310df1ff9b0421ab887c448649a309ffd`, with 430 passing executions and one PostgreSQL-only skip. The original independent four negative cases pass unchanged; this is regression evidence, not a replacement for a new independent review. The new reviewer and fresh CI-mode/PostgreSQL checks are running. That batch remains unpublished.


## Projection and daily qualifier repairs — verification in progress

The broader projection now consumes every relevant query object and modifier regardless of temporal keyword presence. Historical diagnosis background requires a complete past diagnostic statement; a request such as 我是要三个月前的 remains a restriction. Existing comparison scopes and non-longitudinal blood-pressure query binders retain their own behavior; the new restriction gate applies only to requested longitudinal domains. Night-only sleep is rejected because the available wake-date aggregate cannot prove that filter across sources. The unchanged independent gateway matrix passes all forty-eight cases. Fresh full regression remains in progress on frozen application bytes.

The second independent daily-evaluation review rejected `5a2e5393` on two false positives: missing nutrient records and a question about possible duplicate entries. That revision passed CI-mode 726 cases with ten skips and PostgreSQL 75 cases, but remained unpublished. The local qualifier repair is now fixed at `628e713f7ed24292f355d607469882860bd1354a`; 453 nearby cases pass with one PostgreSQL-only skip, and the prior independent oracle passes 277 with one skip. A new independent reviewer and new CI-mode/PostgreSQL runs are active. Neither passing unit tests nor a producer replay substitutes for their verdict or real-model acceptance.


## Daily evaluation third review — historical rejection

Fixed `628e713f7` independently passed the original 277-case oracle (one PostgreSQL-only skip) and nine new qualifier pairs. A separate thirteen-case Pi check failed three malformed/unprojectable result cases: missing record dates, an unsupported payload key, and a no-data flag contradicting nonempty rows. The presentation correctly withheld facts, but the query goal and whole turn still claimed completion. G4 returned NO-GO on this common result-contract mismatch. The repair must reuse the same existing projection requirement for single-day evaluation and summaries while preserving plain query behavior. No paid replay, push or deployment occurred for this revision.


## Complete query-object repair — fixed review candidate

Fresh final-source policy validation passed 5,602 cases; coherence and complete query outcomes passed 810 with eight explicit skips. The unchanged independent gateway matrix passed forty-eight. Both test processes exited zero and all application hashes remained stable. The preceding 1,152 evidence/guidance and 214 PostgreSQL checks passed before the final owner-denial reason-only change; their boundary is retained rather than claimed as identical final-source evidence. Independent fixed-SHA original-request and CI-mode verification will cover the final source. Static error lint, System Map, tracked-secret, governance and dossier checks pass. Fixed-commit G4 and real-model original-request/continuation acceptance remain pending; this candidate is not released.
