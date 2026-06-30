# Dossier: Interactive Chat Cards

| 字段 | 值 |
|---|---|
| slug | `interactive-chat-cards` |
| 创建日期 | 2026-06-30 |
| 当前阶段 | S5 实现 |
| 状态 | building |
| 负责 | Codex |
| 反馈环 | TDD / mobile Jest / backend contract test / backend deploy / mobile OTA |

## S0 Intake

User request: "卡片要支持一些交互".

Product intent:

- Chat should not only display generated cards; cards should become small, safe, user-confirmed action surfaces.
- First supported loops: quick record confirmation and runtime next-action completion.

## G1 · 准入裁决

裁决: PASS.

Reasoning:

- This is a first-class product capability under Chat + dynamic UI card fusion.
- It improves daily health workflows without adding a high-risk autonomous execution path.
- It fits existing card, agenda, and write-intent architecture.

## G2 · 可行性 + 安全压测

裁决: PASS.

Safety boundaries:

- Actions are allowlisted in mobile: `route.open`, `agenda.complete`, `write_intent.confirm`, `write_intent.dismiss`.
- Non-route write actions must include `requires_manual_confirm=true`.
- Backend only emits `agenda.complete` for supported source objects: `health_protocol`, `medication`, `supplement`.
- Missing or unsupported completion sources are rendered as disabled actions with a visible reason.
- LLM output cannot provide arbitrary endpoints for direct execution.

## S4/S5 · 实现

Changed surfaces:

- Mobile action contract now supports `confirmation`, `optimistic`, and `disabled_reason`.
- Card registry renders disabled action states and preserves safe interaction metadata.
- Chat bubble shows a native confirmation alert before dispatching confirmed write actions.
- Backend runtime agenda cards include `next_action.source` and emit either an enabled `agenda.complete` action or a disabled completion action plus route fallback.

Design and plan:

- `docs/plans/2026-06-30-interactive-chat-cards-design.md`
- `docs/plans/2026-06-30-interactive-chat-cards-implementation-plan.md`

## G3 · 测试闸

裁决: PASS.

RED evidence:

- New mobile card-action tests failed before implementation because disabled actions still dispatched.
- New ChatBubble confirmation test failed before implementation because dispatch happened immediately.
- New backend runtime-agenda test failed before implementation because source/action metadata was absent.

GREEN evidence:

```bash
pnpm --dir mobile exec tsc --noEmit
# exit 0
```

```bash
pnpm --dir mobile exec jest mobile/components/chat/cards/__tests__/registry.test.tsx mobile/components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx --runInBand
# Test Suites: 2 passed, 2 total
# Tests: 38 passed, 38 total
```

```bash
DATABASE_URL='sqlite:///:memory:' TZ=Asia/Shanghai backend/.venv/bin/python -m pytest backend/tests/test_inline_cards_runtime_agenda.py
# 7 passed, 9 warnings
```

```bash
git diff --check
# exit 0
```

Known warnings:

- Frontend Jest logs existing unknown-card warnings from fail-closed registry tests.
- Backend pytest logs existing deprecation warnings from dependencies and FastAPI startup hooks.

## G4 · 安全闸

裁决: GO.

Pre-release review notes:

- Write actions remain manual-confirm only.
- Disabled actions are visible but cannot dispatch.
- Route actions remain direct navigation.
- No new high-risk write endpoint was added.

## G5 · 部署健康

Pending.

## G6 · 上线验证

Pending.

## S8 · 沉淀

- Add backend-generated quick-record actions once write-intent IDs are consistently returned in chat tool results.
- Add richer action states: executing, succeeded, failed, and undo when backend semantics are ready.
- Add card-specific interaction analytics for confirmation rate, disabled reason frequency, and dispatch failures.
