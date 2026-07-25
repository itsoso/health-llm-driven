# Mobile Empty Chat Hierarchy

| 字段 | 值 |
|---|---|
| slug | `mobile-empty-chat-hierarchy` |
| 当前阶段 | G5 已通过；G6 待真机确认 |
| 状态 | shipping |
| 负责 | User / Codex |

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

## G1 · Requirement Admission

- **裁决: PASS**
- 理由：减少 Mobile Agent 首次对话摩擦，不改变健康写入、安全或自治边界。

## Gates

| Gate | Status | Evidence |
|---|---|---|
| G1 Requirement admission | PASS | Improves Mobile capture and conversation entry |
| G2 Feasibility and risk | PASS | Client-only presentation contract; no API change |
| G3 Tests | PASS | 110 focused assertions; TypeScript exit 0; lint exit 0 with existing warnings |
| G4 Review | PASS | iOS simulator empty, keyboard-open, and wrapped-draft states visually verified |
| G5 Deployment health | PASS | Production OTA group `5bc3a53c-5560-4901-a714-ea61cc71a4c0`; iOS update `019f94e6-352a-7d6b-9043-7a96c73184cb`; runtime `1.3.2`; commit `4d580a763cc116a402981db09a9e22328f6fe8b0` |
| G6 Live verification | PENDING | Production-channel Mobile verification |

## Delivery Notes

- Preserve Alibaba Cloud ASR and composer state machine.
- Do not modify native dependencies.
- Simulator evidence (private local artifacts, not committed):
  - `/private/tmp/reva-empty-chat-ui-new-chat.png`
  - `/private/tmp/reva-empty-chat-ui-keyboard.png`
  - `/private/tmp/reva-empty-chat-ui-draft.png`
- Empty state shows one opener, one provenance row, and three de-duplicated
  actions. Keyboard-open and wrapped-draft states hide the actions, preserve the
  conversation viewport, and grow the composer only when content wraps.
- Production OTA was published to the `production` channel with message
  `Simplify empty Agent conversation hierarchy`.
