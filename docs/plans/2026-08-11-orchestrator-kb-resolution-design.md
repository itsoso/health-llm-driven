# Orchestrator Turn-Scoped KB Resolution Design

## Decision

Adopt a turn-scoped system-knowledge resolution inside the Orchestrator. A non-lite turn resolves the compact Health Twin payload once, then reuses that immutable lookup result for specialist evidence attachment and synthesis-prompt rendering. In the same slice, make cross-review state explicit and add stage-level latency metrics without changing routing, safety policy, IQS trigger behavior, or model selection.

This is the first, low-risk step toward the broader hybrid Context architecture approved by the user:

```text
deterministic safety context
        +
query-aware optional context
        +
NO_RAG | ONE_SHOT | CORRECTIVE lanes
```

The typed Context Plan and three-lane router are intentionally deferred because another active Session owns Agent Kernel/Executor files.

## Current Problem

For a non-lite Orchestrator turn, the same Twin-derived system knowledge is currently resolved once per applicable specialist finding and then resolved again while building the synthesis prompt. With `N` applicable findings, this produces roughly `N + 1` calls to `lookup_for_twin`, including repeated claim scans and graph lookups.

Cross-review has a separate state ambiguity: an empty string currently means both “successfully checked and no conflicts” and “detection failed.” The synthesis prompt treats every empty string as “not precomputed” and runs detection again. This creates duplicate DB work on the healthy no-conflict path and hides the difference between a valid empty result and a failed check.

Existing performance telemetry also reports `twin.meta.build_ms`, which can be historical on cache hits, but not the actual wall time paid by the current turn. KB, cross-review, and IQS stages are not independently timed.

## Goals

- Reduce normal non-lite system-KB lookup attempts from `N + 1` to exactly one.
- Ensure findings and the synthesis prompt use the same claim snapshot in a turn.
- Preserve zero-query behavior for lite turns, empty finding lists, and all-`not_applicable` standalone evidence-resolution calls.
- Eliminate the second cross-review pass when the first pass successfully found no conflicts.
- Preserve one controlled fallback when cross-review detection fails.
- Preserve a bounded KB recovery attempt on an exceptional first lookup, rather than relying on accidental `N + 1` retries.
- Record current-turn wall time for Twin, KB, cross-review, and IQS in both non-streaming and streaming audit paths.

## Non-Goals

- No changes to `agent_executor.py`, Agent Kernel, tool schemas, or health-context routing.
- No `ContextPlan`, three-lane RAG router, model-led free search, or post-answer corrective RAG in this slice.
- No change to IQS eligibility; this slice measures IQS but does not gate it.
- No change to specialist selection, evidence ranking, safety rules, prompt wording, output-token limits, or synthesis ownership.
- No new database table, migration, dependency, framework, or external service.

## Runtime Design

### Turn-scoped KB snapshot

The Orchestrator creates one internal value after specialist execution and before evidence policy:

```python
@dataclass(frozen=True)
class _TurnKBResolution:
    lookup_result: dict[str, Any]
    prompt_text: str
    lookup_ms: int
    lookup_count: int
    lookup_ok: bool
    claim_count: int
```

For `lite_mode = not specialists`, the value is empty and `lookup_count == 0`. For a non-lite turn, the Orchestrator:

1. maps the current `HealthTwin` to the compact KB payload;
2. opens a caller-bind-compatible, independently owned DB Session and calls `lookup_for_twin` once on the healthy path;
3. renders the bounded prompt block from that result with a pure formatter;
4. supplies the same result to `EvidenceResolver.apply_to_findings`;
5. supplies the already rendered text to `_build_synthesis_prompt`.

`None` is the only “not precomputed” sentinel. An empty lookup result and an empty rendered string are valid computed results and must never trigger another query through truthiness.

### EvidenceResolver compatibility

`EvidenceResolver.resolve_for_finding` and `apply_to_findings` accept an optional precomputed lookup result. Existing callers remain valid. When no precomputed result is supplied, `apply_to_findings` lazily performs at most one lookup for all applicable findings. It performs zero lookups for:

- an empty findings list;
- findings whose evidence status is `not_applicable` (record/data-gap shapes).

Existing evidence metadata, ref ordering, deduplication, support status, unsupported reason, and item-level propagation remain unchanged.

### Pure prompt formatter

Extract `format_system_knowledge_result_for_prompt(result, ...)` from the existing DB wrapper. The existing `format_system_knowledge_for_prompt(db, twin, ...)` remains public and delegates to:

```text
lookup_for_twin(db, twin) -> format_system_knowledge_result_for_prompt(result)
```

The pure formatter preserves claim order, limits, truncation, confidence formatting, and `CLAIM_BOUNDARY`, and does not mutate its input.

### Failure semantics

KB setup and lookup are fail-soft but observable. Import or Twin-payload mapping failure returns a valid empty snapshot with `lookup_ok = False` and `lookup_count = 0`; deterministic setup failures are not retried. Lookup performs one normal attempt and at most one immediate controlled retry on exception. Each attempt uses an independent Session on the caller's Engine, copies the tenant identity, rolls back only its own failed transaction, and always closes. It never commits or rolls back the caller's pending unit of work. If both attempts fail, findings remain model inference unless evidence is not applicable, and the prompt receives no system-KB block. Operational logs contain only stage and exception type, not health content. Normal zero-hit is `lookup_ok = True` with zero claims.

This replaces accidental per-finding retries with a bounded policy: one attempt normally, no more than two during an exceptional failure.

### Cross-review three-state contract

Use the following contract end to end:

- `None`: detection was not computed or failed; run one deterministic fallback.
- `""`: detection completed successfully and found no conflicts; do not run again.
- non-empty string: precomputed conflict/arbitration block; inject it unchanged.

`_run_cross_review_and_arbitration` returns `None` only on detection failure and `""` on a successful no-conflict result. The Orchestrator resolves `None` to a final string before invoking either mega synthesis or parallel synthesis, so both paths receive identical conflict context. Direct legacy callers of `_build_synthesis_prompt` retain fallback behavior when they omit the argument.

## Observability Contract

Both non-streaming and streaming `perf_breakdown` add:

- `twin_wall_ms`: actual wall time of this turn's `build_twin` call;
- `kb_lookup_ms`: total centralized KB resolution time, including exceptional retry;
- `kb_lookup_count`: actual lookup attempts (`0` lite, `1` healthy, at most `2` on exception);
- `kb_lookup_reuse_count`: legacy per-finding-plus-prompt lookup attempts minus actual lookup attempts; an exceptional retry therefore reduces the reported saving;
- `kb_lookup_ok`: distinguishes a valid zero-hit from an exception;
- `kb_claim_count`: matched claims in the shared snapshot;
- `cross_review_ms`: initial detection, optional arbitration, and exceptional deterministic fallback;
- `iqs_ms`: time spent in `fetch_realtime_evidence`, or `0` when not triggered.

Keep the existing `twin_build_ms` field for compatibility. Streaming exposes the same values through audit and the existing `done.perf` payload.

## Safety Invariants

- `lite_mode` remains based on `not specialists`, never `not findings`.
- Mandatory specialist and Safety Guardian behavior is unchanged.
- The system-KB snapshot is treated as immutable at the Orchestrator boundary and scoped to one turn; lookup Sessions use the caller's Engine and tenant but own their transactions.
- No personalized final answer is cached or shared across users.
- A lookup failure never invents refs; it degrades to explicit unsupported/model-inference status.
- A cross-review detection failure cannot be mistaken for a successful no-conflict result.
- Both synthesis implementations receive the same resolved conflict block.
- No user health content is added to performance logs.

## Alternatives Considered

1. **Keep per-finding lookup and cache at the DB/service layer.** Rejected for this slice because it still permits snapshot drift within a turn and does not remove prompt-stage duplication.
2. **Introduce the full query-aware Context compiler now.** Deferred because it changes routing and overlaps another active Session's Agent Kernel/Executor ownership.
3. **Make retrieval fully agentic.** Rejected as the default path: it adds model/tool turns and variable tail latency, and it lets a model omit mandatory medical safety context.
4. **Run a second RAG pass after every answer.** Rejected: corrective retrieval should be conditional on evidence insufficiency or high-risk unsupported claims.
5. **Adopt LangGraph/Haystack/LlamaIndex runtime dependencies.** Rejected for this change; their routing, async DAG, and evidence-compression patterns are useful, but the existing code can implement this bounded optimization directly.

## Verification And Rollout

- TDD tests cover lookup cardinality, precomputed zero-hit, no-query not-applicable paths, formatter equivalence, cross-review three-state behavior, failure fallback, and non-stream/stream metrics.
- Focused Orchestrator/System-KB/Cross-review suites must remain green.
- Repository hygiene, compile, doc drift, dossier consistency, and a broader relevant Backend regression run are required before integration.
- Implementation stays on `codex/orchestrator-kb-resolution` until both active Sessions release their integration/deploy windows.
- Rollback is a code revision only; there is no schema or data rollback.

## Industry References

- LangChain retrieval modes: <https://docs.langchain.com/oss/python/langchain/retrieval>
- LangGraph agentic RAG (slow-path reference): <https://docs.langchain.com/oss/python/langgraph/agentic-rag>
- Haystack async pipeline: <https://docs.haystack.deepset.ai/docs/asyncpipeline>
- Anthropic context engineering: <https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents>
- OpenAI latency optimization: <https://developers.openai.com/api/docs/guides/latency-optimization>
- pgvector hybrid search: <https://github.com/pgvector/pgvector#hybrid-search>
