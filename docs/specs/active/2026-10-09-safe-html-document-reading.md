# Feature Spec: Mobile static HTML document reading

> Status: implementing
> Updated: 2026-10-09
> Related code: SafeTableMarkdown / safeHtmlDocument

## Decision and admission

Extend the existing observation/review surface so a completed assistant HTML document can be read without exposing raw markup by default. This is a local projection of the existing message, not a new report generator, medical recommendation, data read permission, or executable action. It complements the table-only contract in `2026-09-29-safe-html-table-rendering.md`; that existing table grammar and its fail-closed fallback remain unchanged.

```yaml
RequirementAdmission:
  request: Read the HTML document returned by a health conversation on Mobile.
  classification: engineering-maintenance
  first_user_fit: Existing health conversation users reviewing a plan.
  core_loop_step: Review existing observations and recommendations.
  first_class_objects: HealthTwin observation surface; no new persisted object.
  target_surface: Mobile assistant message body.
  source_of_truth: Original stored message bytes.
  safety_level: Untrusted display content; no execution or data mutation.
  prescription_or_causal_verdict: No new medical or causal claim.
  autonomy_tier: Display only.
  evidence_provenance: Preserve existing reply provenance; do not certify its claims.
  claim_hedging: Label the projection as safe reading mode, not a faithful browser rendering.
  verification_window: Local regression and independent review before integration; release separately gated.
  success_metric: A complete supported document reads as native text with source recoverable.
  added_user_burden: None for reading; one action to inspect original source.
  burden_justification: Source remains available for fidelity review.
  non_goals: Browser execution, CSS fidelity, export, medical inference, stream recovery, native runtime changes.
  smallest_end_to_end_slice: Complete fenced static document to native Text/View with source disclosure.
  stale_surface_to_remove_or_archive: Supported documents no longer use unsupported-source fallback.
  spec_required: yes
```

## Contract and safety

- Only complete html/htm fences in finalized assistant content are eligible. User content, streaming, non-HTML code, incomplete documents, unknown tags, active content and oversized input retain their original source fallback.
- Require complete document structure. Whitelist static layout and text elements; headings, paragraphs and list boundaries remain legible. Source length, nesting, block count and text length are bounded; exceeding a bound rejects the whole preview, never truncates it.
- Head title/meta/style are inert document metadata. No CSS is evaluated. Native properties come from application constants, never from source attributes. No WebView, script, form, URL opening, image fetching, or new dependency/native module.
- Render only native Text/View. Do not feed extracted text back into Markdown, GenUI, action-card extraction, tools or prompts. Existing HTML opacity and action suppression remain in force.
- Label the preview `HTML 文档（安全阅读模式）`; preserve a selectable, expandable original fenced source. Copy/storage are unchanged. A display preview does not prove the model completed the turn or that medical statements are evidence-backed.
- Unsupported tables, including spans, keep their existing source fallback. Arbitrary page layout fidelity, source download/sharing and Mac/Web parity are outside this narrow repair.

## Acceptance, delivery and rollback

1. Synthetic complete document with title, paragraphs and lists displays readable content in the actual ChatBubble pipeline and retains exact source.
2. Scripts, event handlers, remote resources, malformed or unfinished markup and resource exhaustion remain inert and fail closed.
3. User/streaming messages do not preview. HTML text cannot generate action cards or write commands.
4. Parser, real message-path tests and TypeScript pass; independent G4 review checks the fixed commit. UI/simulator evidence remains separate from unit-test evidence.
5. Existing production runtime incompatibility remains an independent release BLOCK. No OTA is claimed from local verification. Rollback is reverting this local display change; no migration or persisted-data transformation.
