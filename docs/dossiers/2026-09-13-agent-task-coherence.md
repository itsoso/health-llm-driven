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


## Sixth scope review and fourth diet review — historical rejections

Fixed `54a7d8b3` passed final policy/coherence and an independent thirty-two-case original-request run, but independent G4 found quoted object restrictions were erased before default-week authorization. Sixteen actual gateway failures cover quoted subday dates, past dates and another named subject across single/batch and enforce/shadow; this proves incorrect replacement with the current-user scope, not a demonstrated tenant-data leak. The original forty-eight cases and 355 nearby cases pass. The candidate was not published. Its CI-mode run was stopped after the rejection, with unfinished shards explicitly retained; a separate existing empty-answer test failed. That failure exposed a composed-read preface implying records when no diet result was verified, and facts replacing a generation-failure notice. The repair preserves both read and generation failure; the original assertion remains unchanged. Its RED run had four failures, and the focused repair passed 121 cases.

Fixed daily `a239238d8` passed the original thirteen malformed-result oracle cases, and new real meal-list/no-data/read-failure/generation-failure checks. Its new G4 nevertheless found a previous uncertain proposition could exempt a subsequent affirmative nutrient or duplicate-record claim joined by 且. Six failures share that one local-binding defect. The independent PostgreSQL run passed ninety-three cases with no skips, using the same isolated PostgreSQL database for application and fixtures; unlike the earlier mixed SQLite/PG run, it did not stall. CI was explicitly terminated after the rejection. This candidate also remains unpublished; the uncertainty operator must bind its own proposition rather than an arbitrary earlier prefix.


## Quote-role and empty-answer repair — fixed review candidate

The shared read projection preserves quotation spans and their host clauses. Complete standalone reported material may be excluded as context; embedded owners, objects and restrictions remain unresolved unless safely bound. The same projection feeds authorization and longitudinal scope construction. Original manage-list limits on reported third-party context remain unchanged, independently reproduced from the previous committed helper.

Final unchanged-source validation passed 5,602 policy cases, 860 coherence/failure cases with eight explicit skips, and 214 PostgreSQL cases with no skips. The unchanged independent matrix passed eighty-four cases. The existing no-false-write/empty-answer test remains unmodified and now passes. All application fingerprints stayed fixed; static, map and tracked-secret checks passed. Fixed-commit independent G4, CI-mode and real-model acceptance remain required; no deployment has occurred.


## Shared sync quotation and uncertainty alternatives — review follow-up

Fixed `8d034c68` passed the read quote matrices and independent 405-case safety/empty-answer checks, but G4 returned NO-GO because the sync scope's separate active-text helper still erased quoted owners and dates. Four actual gateway probes incorrectly authorized a current-user sync. The repair reuses the pure quote-role projection before sync authorization; it must not call the full read resolver recursively or revive the old sync fallback. The independent CI run stopped gracefully after 1,202 passes and no failures, with eighteen unstarted groups explicitly retained. This is not a completed CI gate.

Daily `2daeec4b` fixed the prior affirmative-claim escape and passed the old twenty-six-case oracle. Independent review found two valid alternative complements under the same uncertainty operator were over-rejected, producing six failures across the three colloquial queries. This remains a local proposition-binding compatibility defect; it is not waived by the successful prior cases. The repair must admit complete coordinated uncertain claims while preserving all subsequent independent-assertion denials. Subsequent fixed candidates will undergo new G4 before broad CI/PG and paid acceptance run in parallel, avoiding repeated broad validation of rejected candidates. No batch has been pushed or deployed.


## Shared quotation authority — fixed review candidate

Sync and status reads now reuse the same pure quote-role projection as read scope. Every optional-projection consumer explicitly denies unresolved text; the full read resolver is deliberately not invoked recursively by sync binding. The focused repair passed 402 cases, the original sync matrix twelve, and the unchanged read matrix eighty-four. Source hashes are fixed in the validation manifest. New independent fixed-commit G4 precedes the final wide CI-mode/PostgreSQL and actual-model checks; those final gates remain pending.


## Real-model dietary evidence projection — remaining acceptance failure

Daily `3782b313` passed new independent G4 (62 narrow Pi cases), then fresh CI-mode 754 cases with ten skips and PostgreSQL 103 cases without skips. Its real-provider replay used four calls and 39,954 reserved tokens on unchanged source. The first max-model colloquial answer passed the finite automatic oracle, but independent review of the full public SSE and owner-bound persisted answer found an unsupported definite duplicate reference and assumptions about meal timing. The second paraphrase correctly retained verified diet facts while rejecting the generated advice; the model had also used unrequested step/water/history context and inferred dietary priorities from missing fields. The replay therefore failed and stopped before remaining cases. Both final texts exactly matched their public token stream. The initial capture-wrapper TypeError happened before the run function/provider invocation, was retained, and was corrected only after that process exited.

The runtime cause is input scope: adding verified facts to an existing system message leaves raw tool results, personal snapshots, historical messages and entry context available to the synthesis model. The repair is a bounded provider-input projection for this single-day dietary evaluation round, retaining same-source static safety/identity rules and existing consent/authorization/model-quality/output gates. It will supply only the explicit question and verified dietary facts, with no additional synthesis tools. Normal recall, summary and sealed medical paths retain their existing behavior. No additional claim-word veto is proposed as a substitute for this evidence boundary. New fixed-source review and real-model acceptance remain mandatory; neither batch has been deployed.

### Diet advice provider-input isolation candidate

- Minimal batch `7972e1eaed18e2bb11a5a399c03533f862c09c3f` replaces the advice provider input with static rules from the existing prompt builder, the current question, frozen daily scope and verified diet facts. It excludes historical messages, dynamic personal context and raw tool text only from non-sealed single-day diet synthesis; the Pi transcript, permission ledger, routing floor and final output guards retain their original paths. The advice provider receives no tools.
- Provider-boundary sentinels first failed against the previous source, then the dedicated integration suite passed through the actual prompt builder and provider adapter. Related checks passed (`692` tests, one PostgreSQL-only skip); this proves code paths, not model-answer semantics. Artifact: `/tmp/reva-minimal-diet-synthesis-projection-report.json`.
- Fixed-source independent review `minimal_diet_independent_review7` is pending. Fresh CI-mode/PostgreSQL and paid original-query/final-answer acceptance follow only after G4 GO. No source has been pushed or deployed.

### Complete sync authorization after withdrawal and constraints

- Full candidate `3abbcf4482cc8ef9df49959bfb0e5dfbe2e84f6c` was rejected by independent G4 review8: a withdrawn sync request could still dispatch in enforce and shadow modes. A subsequent root probe also found unconsumed date, event-time and confirmation constraints. Prior read/quote matrices passing did not cover these failures.
- The repair reuses the existing complete owned-sync binder after bounded full-clause normalization, consumes each clause as an explicit command, cancellation or complete independent read/status/analysis role, and rejects unknown residue. A later read cannot revive cancelled sync authority; a new explicit owned sync can. Quote-role projection still precedes ownership and cancellation checks.
- RED-to-GREEN evidence covers cancellation and complete consumption through the actual gateway in enforce/shadow. Focused suites passed (`446` plus `78` tests); independent read/quote/sync/cancellation/complete-consumption matrices also passed. New fixed-source independent G4 is required before broad CI-mode/PostgreSQL and the original oral query with same-conversation continuation. No production sync or health-data mutation was used.

### Subsequent real-provider acceptance boundaries

- Minimal `7972e1ea` passed independent G4, fresh CI-mode (`767` passed, ten skips), and isolated PostgreSQL (`116` passed, no skips). Real original-query advice was semantically appropriate but its standalone `建议` heading was rejected by the section extractor, leaving the final SSE and persisted answer partial. The implementation retained this failure and added a bounded line-level heading alternative; factual, empty-answer and promise guards were not weakened. Candidate `d3462bef71d4d93e51b3dbd0976789b0b60ea0b6` subsequently passed independent G4 (`35` narrow checks) and awaits fresh real-model/CI/PG acceptance.
- Full `1d07b3e0` passed independent G4, original-query independent checks and PostgreSQL (`214` passed). Its first actual long-query turn completed the four owner-scoped reads with the frozen seven-day window and matching SSE/history, but failed the four-domain answer-evidence check; real prose also inferred synchronization causes and exercise restrictions from missing fields. The same-conversation continuation was not run after fail-fast. Two provider calls reserved `22403` tokens.
- The broad full CI run was gracefully stopped after this actual failure (`1651` tests passed, no failures; unstarted groups remain unverified). Its source hashes stayed unchanged and all test processes ended. This is not a passing CI result or a released outcome. Evidence: `/tmp/reva-longitudinal-live-1d07.json`, `/tmp/reva-longitudinal-live-1d07.final-answers.json`, and `/tmp/reva-longitudinal-live-1d07-candidates.json`. Investigation targets normalized batch arguments in evidence collection and overly broad recovery/exercise guard admission; no further sync grammar expansion is planned.

### Known dietary fields and recovery decision review

- Minimal `d3462bef` passed all six actual colloquial cases and the existing live regression suite, plus CI-mode and PostgreSQL, but the independent final-answer review was superseded by a P2 NO-GO after checking the actual fixture: the provider had been denied existing food names/items and then incorrectly asked the user to supply them again. Automatic completion checks did not detect this. The next candidate `39213671df1abb8e99d1ffbc7c53c29e89f086ec` retains the adapter's verified dietary fields per row as explicitly non-authoritative user data, separates known values from result-level unknown states, and retains unrelated-context isolation. G4 and actual complete-answer acceptance remain required.
- Full `69e43e08` fixed executed batch arguments feeding the evidence collector; independent real Pi checks confirmed four-domain evidence for different model argument shapes. Independent review10 nevertheless rejected the revised recovery classifier: splitting on commas lost a real interval-training decision, while short exercise tokens still misread full record nouns. That candidate was not sent to broad CI or paid evaluation. The repair now preserves cross-clause decision context after excluding complete existing read objects, using the registered exercise/domain vocabulary. The old general-state vocabulary limitation remains separately recorded; it is not claimed as fixed.


### Separate-read evidence selection and safe prohibition acceptance

- Full `dc9ec716` passed independent G4 and the unchanged original thirty-two scenarios. Actual max-model execution made four successful owner/window-bound individual reads, with a complete outcome and identical SSE/persisted answer. Final evidence acceptance nevertheless failed: the global display cap was filled by diet rows before the later domains were considered. The same payloads packed as a batch preserved all domains. The unchanged offline permutation oracle reproduced thirty failures and one control pass; a second independent six-case shape oracle reproduced three failures and three passes. The repair must group strictly validated query objects including their canonical windows, preserve each available group before extra rows, and never promote invalid or failed results into facts. It preserves the existing cap and single-domain behavior.
- Minimal `39213671` passed G4 and fresh CI-mode (813 passed, ten skips). Five of six real-model answers passed; the sixth correctly prohibited inferring whole-day under/overconsumption but was rejected because the existing uncertainty vocabulary omitted 不要 and 不得. Fixed `d77c89714` adds only those operators, preserving proposition, alternatives, contrast and double-negation boundaries. The unchanged eighteen-case external oracle, sixty-nine nearby tests and old thirty-four-case oracle pass; fresh independent G4 and actual-answer acceptance remain pending.
- Concurrent local PostgreSQL-consuming runs exhausted the shared cluster connection limit. The minimal run retained 118 passes, two failures and one error; the full run retained 213 passes and one setup error. Both exited nonzero and all owned processes/connections ended. Full CI was gracefully drained after 7,459 passes, with remaining groups unstarted; it is not a passing gate. Subsequent PostgreSQL checks and paid fixture runs are serialized across batches, and the minimal PostgreSQL lane uses a bounded fresh process per file. No global database capacity changes or production fixture writes were made. Neither batch has been pushed or deployed.


### Answer usefulness and context provenance — bounded final follow-up

- A second independent product review of the five safe actual answers from `39213671` found they still offered only data-quality limitations, despite known food names supporting a bounded qualitative observation. The code review GO and safety/field checks are not evidence that “今天吃得怎么样” was answered usefully. This is retained separately as a P2 request-fulfillment finding, with no claim that `d77c89714` had a new actual-model run. The bounded repair will ask for an observation grounded in known foods before its limits, without inferring portions, nutritional adequacy or complete daily intake; it retains typed provider-input isolation and all output/authorization guards. Unknown food names legitimately limit evaluation.
- Independent read-only inspection of the synthetic profile confirmed the referenced sleep/step targets exist but may be ORM defaults; their existence does not prove user confirmation. The step mean had only three effective dates within the seven-day requested window. The actual provider prompt was not captured in that earlier run, so profile existence alone does not attest its model input. Source inspection independently found the lite context used an open-ended lower date bound and labeled row means as seven-day means without coverage. The bounded repair will freeze both calendar bounds, reuse existing per-day source merging, disclose per-metric valid-date coverage and describe target-confirmation uncertainty. The next actual run will record only relevant synthetic prompt excerpts alongside existing SSE/persistence observations, with no extra provider call.


- Minimal `d77c89714` subsequently passed independent G4 (eighteen external and sixty-nine adjacent executions), fresh CI-mode (814 passed, ten skips), and serialized PostgreSQL (122 passed, no skips). Each PostgreSQL file ran in a fresh process; all exits were zero, connections were zero between files and after completion, and the isolated database was removed. This validates the prohibited-inference fix, not the separate usefulness finding. No actual-model call was made on this revision; the narrow known-food evaluation instruction is being applied after all processes drained.


### Global evidence and bounded context — fixed review candidate

The evidence selector now reserves one actual observation per validated query scope (dimension plus canonical dates/timezone) only when at least two nonempty scopes are available. Failed/invalid scopes cannot gain basis, distinct comparison windows remain separate, and single/no-scope packet ordering remains compatible. The unchanged permutation oracle passed all thirty-one cases; eighty-two focused/actual-Pi-scripted executions passed, and twenty comparisons against the prior committed single/no-scope output were byte-identical. This is execution and projection evidence, not paid-model acceptance.

The lite-context repair passed nine RED-to-GREEN cases and all thirty-four adjacent tests, with unchanged source/dependency fingerprints. It uses the existing per-field source merger before per-day statistics, preserves valid zero values, excludes nonfinite readings and dates outside the frozen inclusive seven-day window, and exposes date range and per-metric coverage. Directional comparisons require complete first/last three-day calendar coverage. Profile targets remain available with confirmation uncertainty, and the neighboring wearable summary receives the same frozen day. Existing process-timezone and cache behavior remain unchanged.

Minimal diet usefulness candidate `86f3c3ab1` changes only its isolated synthesis instruction and two neighboring transport/guard cases. It passed 269 targeted executions, including unchanged prior assertions; no scripted pass is presented as product-quality acceptance. Independent fixed-source review and the same six real-model answers plus full-text product review remain required. Full integrated G4, fresh release checks and original oral/continuation acceptance also remain pending; no new deployment is claimed.


### Minimal batch published; full model-batch budget defect

Minimal `86f3c3ab1` passed its six actual model answers and independent full-text review, then the existing live gate (invariants twelve, core fifty, orchestrator five, mean 0.98). The bounded formal run used ten calls and 17,225 reserved tokens on unchanged source. The exact live-change gate passed. It was pushed and read back on main; exact CI run `34751726466` and production deployment remain pending at this checkpoint.

Full `14db2a918` passed independent G4, unchanged original thirty-two plus six external shape cases, and 248 PostgreSQL tests without skips. The serial PG run exited zero and removed its isolated database after all connections ended. Its first actual max-model oral request nevertheless failed before dispatch: the first model response proposed eight calls; two parameter failures consumed the per-tool repair counter, causing the remaining calls to be blocked before normal validation. No continuation or flash run followed fail-fast. Two provider calls reserved 21,170 tokens. This is a failed acceptance result; the correct new profile-target and valid-day coverage text was independently observed in the actual system input but did not establish task completion.

The full CI environment had temporary-root import and Git-directory failures, retained as failed receipts. Fixing only the external launcher and resuming failed/unstarted groups yielded twenty-one completed groups with 14,693 passes and twenty-nine skips before graceful cancellation after the actual failure. Three groups remained unstarted; it is not a completed CI gate. All source hashes stayed unchanged and all processes drained before integrating current main.

The next repair must count genuine model feedback batches rather than individual queued calls, preserve the existing finite limit and hard authorization checks, and avoid clearing an existing terminal decision. The observed failure answer also repeats scope notices because a trusted composed summary already contains them before the executor prepends them again. Separately, actual legacy system context still labels dietary row count as meals and unknown protein as zero; this is confirmed input contamination, not proof of a generated nutrient conclusion in the failed run. A bounded composed-read profile projection should retain static safety and owned clinician context while reserving current facts for real query results. No new model run or production release of the full candidate is authorized by passing its earlier gates alone.


### Minimal batch production acceptance; full feedback repair still pending

Minimal main `86f3c3ab179316bd2cf5cf69aeb704fa7cbf6dc3` passed exact GitHub CI `34751726466`. The sole backend deploy exited zero after backup/restore/offsite integrity, rollback-schema compatibility, runtime transaction commit/finalize, exact-SHA readback, health checks and staged KB contract. The production host fetched GitHub successfully; this current observation does not diagnose the earlier fetch failure. Independent readback matched the three runtime file hashes and confirmed the restarted service at 2026-09-13 18:49:54 Asia/Shanghai.

The authorized existing-owner production question `今天我吃的怎么样?` used the real Pi executor and normal authenticated diet adapter. Both diet read and advice goals verified, generation/outcome completed, and streamed text equalled the owned persisted answer. The diagnostic exited zero with two provider calls and 18,048 reserved tokens; no health writes or synthetic fixtures were used. This verifies backend execution and persistence, not client UI operation. The deployment separately reported an embedding-provider connection error and zero dense vectors with sparse retrieval remaining active; health and KB contract success do not prove vector retrieval availability.

The full candidate remains unpublished. Its pending repairs count failed model-feedback batches with the existing finite limit and preserve terminal authorization decisions; use a server-owned composed-read profile projection with static safety and clinician context; and avoid duplicate scope notices. A new real-entry counterexample found query validation erased proposed owner fields before the existing capability policy could reject them. It proves a policy-observation defect, not cross-user data disclosure. The original failing oracle is retained while the normalization boundary is repaired and reviewed. Fresh fixed-source G4, complete CI/PG and actual original oral plus continuation acceptance remain required.


### Feedback-batch and normalization repair candidate

The fixed repair keeps the existing limit of two failed attempts, settling actual Pi feedback batches at model boundaries so queued siblings still receive normal validation. Replayed rejected arguments count as unsuccessful feedback without re-dispatch. Direct facade calls without a model boundary retain their existing conservative per-call limit; terminal decisions cannot be cleared by a later repairable failure. Existing enforce-mode semantics remain, and production configuration was read back as enforce. Shadow-mode observation semantics and the existing global Pi caps are unchanged.

Owned composed-read context now selects a separate profile budget with clinician feedback and static safety; current observations come from validated tool results. Canonical failure summaries no longer receive duplicate notices. The context and notice suite passed 319 tests; the subsequent owner normalization, validator and complete retry suite passed 183 with zero failures/skips and unchanged source. Six owner-bearing single-query entry counterexamples failed before removing the premature parameter clear; batch and canonical positive controls remained valid. The external two-case feedback oracle passed unchanged. These local receipts were recovered after the implementation agents were interrupted; they do not replace the next fixed-source independent review or real-model acceptance.

The resumed integrated nine-module run passed 255 tests with zero skips/failures and unchanged service hashes. Its first launcher attempt collected no tests because of an incorrect test filename; that exit-four receipt is preserved separately. Static blocking lint, dossier consistency, Skill governance, secret scan and System Map checks passed.


### Four-domain execution repaired; synthesis acceptance still failed

Candidate `59be21b08` passed fresh independent G4 (eight adversarial plus sixty-eight neighboring unique cases), and two separately reported independent runs passed thirty-four and six cases. Its actual original max-model request used three calls and 34,119 reserved tokens. The first failed parameter batch no longer cut off queued valid siblings: all four domains dispatched with exact owned rows and calendar scope, and all four read goals verified. Source hashes and streamed/persisted equality held. Final generation/outcome acceptance nevertheless failed, so continuation and flash were not run and broad CI/PG were not started.

The actual blocking code was `unverified_dose_action` on a statement that the existing supplement quantity was unknown. It was not the separate citation-anchor shadow observation about the trusted activity total. Independently, the unpublished candidate misstated a possibly default target as definitely default, overclaimed recovery/HRV relationships, flattened differing food records, proposed unrequested scheduling and promised uncovered readers. Fixing the information-object false positive alone therefore cannot establish answer quality.

The next bounded change reuses the full existing composed-result validation to give the provider typed per-row facts only after all requested reads verify, disables tools for this synthesis phase, retains safety/clinician context and final medical checks, and keeps partial and sealed paths intact. The original Pi transcript and permission ledger remain authoritative. A separate minimal guidance correction distinguishes explicitly unknown existing quantities from prescriptions; appended doses and timing instructions still fail. Its new negative counterexample additionally requires an explicit bare dose-change instruction to remain blocked without repeating the medicine name. Original failed model/test receipts remain available for independent review.


### Composed answer projection — local candidate freeze, 2026-09-13

The final answer provider now receives typed evidence only after every authorized query verifies. Actual field units, record multiplicity, food names and distinct unknown-value reasons survive projection. Existing owner profile and clinician background remain explicitly lower-authority user data alongside static safety rules. A valid continuation includes only the exact previous assistant answer from the same owned conversation, as continuity rather than current evidence or new consent. Main and panel paths preserve the Pi transcript, permission state, trusted fact summary, final medical guard and streamed/persisted answer contract.

The reproduced unknown-regimen quantity sentence no longer masquerades as a prescription. Its narrow quantity-object rewrite preserves appended actions, and bare explicit dose increases/decreases are now recognized without requiring a repeated medicine name. Positive information requests and negative dose/timing directions are retained together.

Initial projection regressions failed seven cases before implementation. The first broad run retained 867 passes and two failures from old assertions requiring dynamic profile in system and raw records in tool messages. The updated assertions verify the complete profile plus safety rules, user-data authority, exact food fields and null provenance at the new projection locations; partial/error assertions and outcome checks remain intact. Final combined fifteen-module execution passed 1,014 tests with zero failures/skips (true exit zero, unchanged application source hashes), including medical output/stream boundaries. Receipt: `/var/folders/yh/7jqptt7j1830pzzc1zfr529m0000gp/T/reva-feedback-integrated-eips06g1/receipt.json`. System Map, dossier consistency, Skill governance, blocking static lint and secret checks also passed.

This freezes a local candidate for independent acceptance only. Prior `59be21b` actual-model NO-GO remains valid historical evidence and is not overturned by scripted tests. Fresh fixed-source G4, PostgreSQL, original oral request plus same-conversation continuation on both actual models, independent complete-answer review and release gates remain pending. This checkpoint performs no push, deployment, paid provider call or production mutation.


### Panel stage completion — independent blocker repaired locally

Independent review rejected `1638b808` because nonempty perspective or final synthesis output with `finish_reason=length/error` could still complete. Its earlier truncation tests covered only the lead stage. New stage-specific injections reproduced all six failures (both perspective models and final synthesis, each with length/error), while three empty-output controls passed. RED receipt: `/var/folders/yh/7jqptt7j1830pzzc1zfr529m0000gp/T/reva-feedback-integrated-f4xapttm/receipt.json`.

Two local checks now require dictionary provider metadata to end with `stop` before accepting perspective or synthesis content. Existing empty-text checks, medical guards, settled concurrent calls and blocked-error prioritization remain unchanged. Regressions assert that failed perspectives do not start synthesis, truncated content never reaches the saved/streamed answer, verified read facts remain visible and the overall turn does not claim completion.

Final fifteen-module regression passed 1,023 tests; a separate panel output-boundary module passed twenty-three, including consent/quota blocking, medical/protocol filtering and normal completion. Both true exits were zero, with no failures/skips and unchanged application source hashes. Receipts: `/var/folders/yh/7jqptt7j1830pzzc1zfr529m0000gp/T/reva-feedback-integrated-449ko_zn/receipt.json` and `/var/folders/yh/7jqptt7j1830pzzc1zfr529m0000gp/T/reva-feedback-integrated-7irxnmex/receipt.json`. Static lint, System Map, Skill governance, dossier consistency and staged secret checks passed. A new local revision is frozen for independent review; G4/PG/actual-model/release gates remain pending, with no push, paid call or deployment at this checkpoint.


### Fixed-source G4 rejection and incomplete-answer/bare-regimen repair

The sole independent G4 rejected `7a9a82ec` with two blockers (`/tmp/reva-coherence-review15-g4.json`): single-model composed non-stop content still reached the user despite an incomplete status; and separate/bare supplement dose or timing directions evaded sentence-local tripwires. The prior green tests did not disprove either defect.

The strengthened Pi tests now require the unique incomplete-candidate sentinel to be absent from the persisted and equal streamed answer for both length and error. Complete read facts remain, with a fixed incomplete notice. New positive/negative guidance cases distinguish bare administration directions from food portions, water, walking, information requests and negation. The first targeted run reproduced eight failures and forty-nine passes; the minimum repairs made all fifty-seven pass. A subsequent root check found that a neutral preceding sentence could bypass the whole-text sensitivity precheck, before the correct sentence-level rule ran. Three additional period/semicolon/newline cases failed, then the command boundary was aligned with existing sentence delimiters. These failures are retained in `reva-feedback-integrated-vi_be1ar` and `reva-feedback-integrated-pxt8b1ld` under the local temporary evidence directory.

Final sixteen-module execution passed 1,067 tests with zero failures/skips, true exit zero and unchanged application hashes (`/var/folders/yh/7jqptt7j1830pzzc1zfr529m0000gp/T/reva-feedback-integrated-crjn67rh/receipt.json`). Blocking lint, System Map, Skill governance, dossier consistency and staged secret checks passed. Only this new local candidate can enter a fresh independent fixed-source G4; no inherited GO is claimed. PostgreSQL, real-model quality, wide CI and all release/production gates remain pending; no push, paid call or deployment occurred during this repair.


### Missing stream completion and bare mass-unit directions

The next independent fixed-archive review rejected `d2a5c734`: the new bare-eating branch omitted mass units, and absent single-stream finish metadata was promoted to `stop` even for nonempty unfinished text. The fresh targeted RED reproduced twenty-six failures among eighty-four cases: twenty-four dose/unit/prefix combinations and two real Pi stream cases (missing finish event versus explicit null metadata). All eighty-four passed after the minimum repair. RED/GREEN receipts are in `reva-feedback-integrated-ijz7b99w` and `reva-feedback-integrated-n06cej_t` under the local temporary evidence directory.

An answer without a reported finish reason now defaults to error, so the existing composed non-stop boundary keeps verified facts and withholds the candidate. Explicit structured tool proposals retain their existing tool-call handoff. Bare administration quantities now include mg/IU/毫克/微克, existing case-insensitive matching, whitespace and decimal/Chinese numeric forms. Food portions, water, walking, unknown quantities, directed questions and negations remain controls.

Final eighteen-module execution passed 1,109 tests with no failures/skips, true exit zero and unchanged application hashes, including direct Pi executor and synthesis-passthrough tests. Receipt: `/var/folders/yh/7jqptt7j1830pzzc1zfr529m0000gp/T/reva-feedback-integrated-m40beyr6/receipt.json`. Blocking lint, System Map, Skill governance, dossier and staged secret checks passed. This new local source still requires a fresh independent G4; PG, paid-model acceptance, CI and release remain paused. No push or deployment was performed.


### Provider completion contract — end-to-end repair

Review17 formally rejected `0f4cc802` (`/tmp/reva-coherence-review17-g4.json`, SHA256 `bd08c38f9621d9fc5f7a321f86747a3a0073c9d9cff294a0291c7640c7d87d62`): panel stages accepted plain strings, and the default provider stream adapter invented `stop` from plain text before Pi could detect missing metadata. The direct-gateway result adapter had the same conversion and is included in this repair.

Agent and default provider stream calls now request completion metadata; neither stream adapter creates success from a legacy string. Panel lead distinguishes an explicitly completed tool-call response from a completed answer, and all panel answer stages require dictionary metadata with `finish_reason=stop`. Missing/invalid metadata fails before downstream synthesis; existing blocked-error priority, concurrent-call settlement, verified fact summaries and final output guards remain.

Ollama returns its observed completion status only when `return_metadata=True`; ordinary non-streaming chat still returns a string. Its metadata requires literal `done=True` plus a nonempty string `done_reason`, without inferring success from response text. These fields are documented in the [official Ollama chat API](https://docs.ollama.com/api/chat). The base and both provider return types/documentation reflect the existing metadata response shape. No new tools or health-write authority are introduced.

The stage/default-provider/Ollama matrix first produced twenty-four failures and fifty-five passes, then all seventy-nine passed. RED and GREEN receipts: `/var/folders/yh/7jqptt7j1830pzzc1zfr529m0000gp/T/reva-feedback-integrated-3mehwwxl/receipt.json` and `/var/folders/yh/7jqptt7j1830pzzc1zfr529m0000gp/T/reva-feedback-integrated-ug7bsy0c/receipt.json`. Final twenty-six-module regression passed 1,210 tests with no failures/skips, true exit zero and unchanged application source hashes (`/var/folders/yh/7jqptt7j1830pzzc1zfr529m0000gp/T/reva-feedback-integrated-um3nx2nw/receipt.json`). It includes prior query/medical/Pi coverage plus provider, budget, stream, failover and reasoning-stream checks. Static lint, System Map, governance, dossier consistency and staged secret checks passed. This remains a local candidate for fresh fixed-archive G4; PG, actual-model, wide CI and release gates remain pending. No push, paid call or deployment occurred.

## Medical assertion presentation normalization — review 18 repair

Independent review 18 rejected `bf7af883128a4604166ce9ae41a60bfdefac2956`: early medical-boundary detection did not normalize fullwidth/compatibility dosage units, and list prefixes could bypass the bare-regimen matcher. The provider completion-metadata paths had no new blocker in that review. Its immutable receipt remains `/tmp/reva-coherence-review18-g4.json` (SHA-256 `4680d49b55d44c9912caaa7aa022b5dc354c41e43bf0f92fb0241a0069a5890b`).

The early gate and sentence guard now share one NFKC and bounded list-prefix matching view. Output text and exact trusted clinician-relay comparison retain their original spelling. This is a bounded repair for confirmed presentation bypasses, not a claim that lexical tripwires establish medical safety for all language.

Added paired negative and benign cases for fullwidth/compatibility units, plain and list-prefixed instructions, questions, uncertainty, food, water, walking, and negated instructions. The focused RED run had 31 failures and 139 passes (`reva-feedback-integrated-lostx44_`); after the repair, all 170 passed (`reva-feedback-integrated-r2q5d9mq`). The final unchanged application source passed all 1,298 tests across 26 modules, with zero failures/errors/skips, exit 0, in `reva-feedback-integrated-lfc4sa2k/receipt.json` under the local temporary-directory evidence root.

This local result is ready for a fresh fixed-revision independent G4. PostgreSQL, paid actual-model answer quality, full CI, push, deployment, and production acceptance remain pending for this revision; prior NO-GO receipts and actual-model failures remain retained.


## Actual-model field-request false positive — 2026-09-14

Candidate `97c07b7e46ea158dd55a267cf5d697f7cc19cc39` received independent fixed-archive G4 GO (`/tmp/reva-coherence-review19-g4.json`, SHA-256 `02bdb4c54fa3a67da4c91098b0563696c35f867adb557238ee6552c738b384dc`). Its PostgreSQL evidence covered 395 tests across 12 files: the first ten passed, the initial 600-second batch deadline terminated file eleven, and the remaining two passed in a fresh isolated database. Both databases were removed with zero remaining processes/connections. The failed batch is retained; the combined evidence is `/tmp/reva-coherence-97c07b7e-pg-combined.json`.

The subsequent actual Max oral request failed after two provider calls / 23,597 reserved tokens. All four authorized domain reads, exact owned rows, frozen dates, no health writes, and SSE/persisted equality passed. Final generation/outcome failed because a request to provide missing record fields was misclassified as a dose action. The other three model/continuation cases did not run. The full synthetic candidate received independent content-quality GO, but this did not override the failed user-visible outcome. Preserved artifacts and hashes are listed in `/tmp/reva-coherence-97c07b7e-actual-failure-manifest.json`. No full-candidate publication or deployment occurred.

The repair projects only colon-delimited, recognized record-field objects in the assertion-matching view. Original output is retained. Bare intake commands appended to these requests remain detectable. Directed intake questions project only the questioned object, so later instructions remain visible; the same assertion view is used by both scoped and unscoped regimen checks. This remains bounded lexical detection, not general medical verification.

RED evidence is retained: `reva-feedback-integrated-hy8g_kgg` had five failures / 192 passes; `reva-feedback-integrated-rn38vf_b` had one additional question-control failure / 270 passes; `reva-feedback-integrated-0lpn5z3s` had one additional inquiry-prefix failure / 221 passes. Intermediate runs `hk_g671y` (197), `dil9nt52` (274) passed. These temporary directories are under the host temporary evidence root. Added tests cover unchanged benign output, same/next-clause dose and timing commands, question/punctuation separation, and actual Pi main/panel outcomes with SSE/persisted equality. Fresh final regression and independent G4 are required before resuming release gates.


Final field-request repair verification: 293/293 focused tests passed (`reva-feedback-integrated-anw4ivcg/receipt.json`), followed by 1,354/1,354 tests across the 26-module unchanged-source run (`reva-feedback-integrated-85h5rddz/receipt.json`), both exit 0 with no failures/errors/skips. System Map, Skill governance, dossier consistency, blocking Ruff, and diff checks passed. This freezes the repair for a new independent G4; it does not transfer the prior revision's PostgreSQL/actual/CI verdicts or claim deployment.


## Independent administration predicates — review 20 repair

Fresh independent G4 rejected `cacfe041cc4faf2746394b445c4562c93e130a45` as critical (`/tmp/reva-coherence-review20-g4.json`, SHA-256 `8c935213792f48bd67da31df296352c23b50b7b84f2a129f226812089e212f78`). The information projection removed an earlier false signal, but an actual later administration command beyond the leading request's bounded window could escape. The independent oracle had 16 failures / 46 passes; the two exact examples were incorrectly complete in both main and panel execution. No PG, paid actual, wide CI, push, or deployment proceeded for that candidate.

The independent oracle is retained as `backend/tests/test_guidance_appended_administration.py` with additional punctuation, connector-length, explicit-action, and unknown-intake controls. The initial expanded RED run `reva-feedback-integrated-g8u20apm` had 76 failures / 50 passes. Administration predicates now match independently of the original request's position: explicit oral dose, mass-unit dose change, and frequency/timing administration each remain visible after local information-object projection. Food quantity wording is not promoted to a medication solely by this new mass-unit branch.

A subsequent existing positive control, an unknown whether-intake statement, exposed a false positive (`reva-feedback-integrated-380y3hzr`: one failure / 418 passes). Its object is now handled by the same local inquiry projection; no global negation or sentence exemption was added. Four unknown-object positive controls and eight appended-command negatives were added. The resulting focused run `reva-feedback-integrated-x0_iscng/receipt.json` passed all 431 tests, source unchanged, exit 0. All prior red receipts remain retained. Full regression and a new fixed-revision G4 are pending before further release activity.


Final unchanged-source verification for the administration repair passed 1,492/1,492 tests across the existing 26 modules plus the new independent-administration regression module (`reva-feedback-integrated-g_2yvuu9/receipt.json`), exit 0 with no failures/errors/skips. System Map, governance, blocking Ruff, dossier, and diff checks passed. The candidate is ready for fresh independent G4; PostgreSQL, actual-model quality, CI, push, deployment and production acceptance remain subsequent gates.
