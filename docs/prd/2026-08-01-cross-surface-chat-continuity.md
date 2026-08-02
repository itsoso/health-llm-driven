# PRD: Cross-Surface Chat Continuity

> Status: approved
> Date: 2026-08-01
> Feature Spec: `docs/specs/active/2026-08-01-cross-surface-chat-continuity.md`

## Outcome

A user signed into the same account can continue the newest durable Xiaoba
conversation on Web or Mobile without discovering that each client silently
chose a different thread. Mobile simultaneously becomes a true edge-to-edge
Agent shell with a legible, balanced “小巴” identity.

This supports the Personal Health OS core loop in
`docs/prd/reva-personal-health-os-prd.md`: conversation is the review and
execution surface around persisted `ExecutionEvent` evidence. It does not add a
new health object or medical judgment.

## Current Failure

```text
Mobile boot
  -> local AsyncStorage conversation id
  -> optional daily briefing preference
  -> backend latest

Web boot
  -> explicit ?c=id: load
  -> no ?c: blank draft

same backend history + different selection rules
  -> detached new threads
  -> “Web and Mobile history are not unified”
```

Mobile's root also leaves the status-bar region visually outside the chat
surface. Its title is smaller than the surrounding high-density answer copy,
weakening the top-level hierarchy.

## Requirements

### R1 — Canonical continuity

The newest owner-scoped backend conversation by `updated_at` is the default on
both surfaces. An explicit URL/history choice, explicit new-chat action, or an
active/recoverable local stream takes precedence.

### R2 — One history, no destructive merge

Both surfaces show the backend list in canonical order. Distinct conversation
ids remain distinct: the feature must not concatenate messages, merge by title,
or rewrite existing history.

### R3 — Fail closed

Invalid or unauthorized ids never leak data. A failed history load must be
observable and retryable; it must not manufacture content or treat another
account's local id as valid.

### R4 — Edge-to-edge Mobile shell

The chat background covers the full device viewport including behind the status
bar. Header and composer content still respect notch, keyboard, and home
indicator insets. The root does not look like a form sheet or rounded card.

### R5 — Balanced brand hierarchy

“小巴” and its avatar form a clear primary identity. The title is larger than
the previous 23pt treatment, remains compatible with Dynamic Type/layout
pressure, and does not reduce the 44pt effective action targets.

## Non-Goals

- Server schema, authentication, Agent model, health writes, and message payloads.
- A single never-ending conversation.
- Cross-account or anonymous history transfer.
- Full-screen media viewer or full-screen individual response mode.

## Success Checks

- A Mobile-created latest thread opens by default on Web for the same account.
- A Web-created latest thread opens by default on Mobile even when Mobile stored an older id.
- Explicit deep links, selected history, and new chat preserve user intent.
- Both history lists use backend ordering.
- iPhone screenshot shows no grey/rounded root gap and a balanced 28pt-class title.
- Owner-scoping tests and existing message/history tests remain green.

## Delivery

No backend or native dependency change. Web follows normal deployment; Mobile
uses production OTA. True-device verification is required after release.
