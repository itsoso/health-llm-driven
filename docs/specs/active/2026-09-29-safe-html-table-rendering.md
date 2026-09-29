# Feature Spec: Safe HTML table display

> Status: locally verified; release pending main alignment
> Updated: 2026-09-29
> Related code: Mobile ChatBubble / Mac ChatTranscriptHTML

## Decision and admission

Engineering maintenance: show existing assistant HTML tables as readable tables on Mobile and Mac, without changing health data, model instructions, persistence, or medical advice. This restores the HealthTwin observation/review surface rather than adding a product object or action. Source of truth remains the original stored message. No new autonomy or data access.

## Surface and data contract

- Final assistant replies: complete html/htm code fences or standalone raw tables can become a preview. Other code languages remain code. Streaming stays text until complete.
- Accept one bounded table per block: table, caption, thead/tbody/tfoot, tr, th/td; b/strong/i/em/span/br inside text cells. Preserve caption, order, empty cells, literal pipes, entities, line breaks, and header markers.
- Source ≤32,000 UTF-16 units; ≤100 rows, ≤20 columns, ≤2,000 units per text cell/caption, nesting ≤32. Reject malformed nesting, unequal row widths, spans, unknown/duplicate attributes, unknown tags, oversized input. Never truncate a table into apparently complete data.
- Presentation attributes style/border/cellpadding/cellspacing/width/height/align/valign/class are discarded, not executed. No links, images, CSS, scripts, callbacks, native bridge actions, or network requests from table content.
- Mobile uses native Text/View + horizontal ScrollView; Mac regenerates fixed table tags and escapes every cell. HTML parsing never inserts raw model markup into a WebView.
- Successful previews offer a collapsed source disclosure. Unsupported/incomplete HTML remains literal source, including all content. Copy/storage remain original.
- Message cleanup treats HTML as opaque before legacy artifact removal and GenUI extraction. HTML-bearing messages cannot generate prose-derived action cards, including separate reva-ui/menu_share fences elsewhere in the message (these remain literal source). Only independently structured server message fields such as cardData/dynamicCard remain unchanged; a fence in message text is not such a field.
- Backend, Web, Watch, API/schema/database, notifications and authentication unchanged. No new dependency or native module.

## Safety and AI boundary

Untrusted health text is only projected locally. No inference, numerical rounding, unit conversion, claim, medication decision or write is added. Existing display content is preserved; unsupported tables explicitly fall back to source. Attributes never reach native properties/DOM. Entity decoding is one pass and text is escaped again on Mac. Synthetic fixtures only; no production health payloads in tests/logs.

## Acceptance and verification

1. Screenshot-shaped synthetic sleep table displays in rows/columns on both clients with surrounding prose intact.
2. Empty cells and pipes do not shift columns; wide Mobile tables scroll horizontally and source can be inspected.
3. Unsafe/unsupported/incomplete tables do not execute and retain source. Other fenced languages, user messages and streaming do not gain previews.
4. Unit/parser, real message-path component tests, Swift transcript/cache tests, Mobile typecheck and applicable integration gates pass. Independent safety review before release.
5. Simulator/Mac UI checks are separate from unit-test claims; gaps explicitly recorded.

## Rollout / rollback and non-goals

No arbitrary HTML document renderer, interactive widgets, CSS fidelity, rowspan/colspan, remote resources or server prompt rewrite. HTML documents outside this table subset remain source. Mobile is JS-only and OTA-eligible after release gates; Mac requires a separately verified desktop build. Publication is not performed with unresolved main divergence or unrelated release scope. Rollback is reverting only this display change; no data migration.
