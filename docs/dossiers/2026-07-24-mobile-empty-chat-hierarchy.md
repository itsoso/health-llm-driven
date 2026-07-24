# Mobile Empty Chat Hierarchy

**Status:** Implementation verified; simulator review pending  
**Owner surface:** Mobile Agent conversation  
**Design:** [Mobile Empty Chat Hierarchy Design](../plans/2026-07-24-mobile-empty-chat-hierarchy-design.md)

## Requirement

Reduce the empty Agent conversation from three competing action layers to one
conversation-first hierarchy, while preserving voice, text, capture, and
attachment capabilities.

## Product Admission

- **Core-loop contribution:** Reduces friction before a health capture or
  conversational action.
- **First-class objects:** `ExecutionEvent`, `WriteIntent`.
- **Surface ownership:** Mobile remains the primary daily capture and execution
  surface.
- **Safety impact:** No medical logic or write autonomy change.
- **Superseded surface:** Generic suggestions are hidden whenever contextual
  opener replies are available; focused composer quick actions are removed from
  the keyboard-open state.

## Gates

| Gate | Status | Evidence |
|---|---|---|
| G1 Requirement admission | PASS | Improves Mobile capture and conversation entry |
| G2 Feasibility and risk | PASS | Client-only presentation contract; no API change |
| G3 Tests | PASS | 110 focused assertions; TypeScript exit 0; lint exit 0 with existing warnings |
| G4 Review | PENDING | Simulator interaction and visual review |
| G5 Deployment health | PENDING | Simulator and OTA health |
| G6 Live verification | PENDING | Production-channel Mobile verification |

## Delivery Notes

- Preserve Alibaba Cloud ASR and composer state machine.
- Do not modify native dependencies.
- Publish as Mobile production OTA only after simulator screenshots verify the
  empty, keyboard-open, and draft states.
