# Intake Intent Router Design

> Status: approved for implementation
> Date: 2026-07-04
> Scope: text chat and server-generated dynamic cards for intake logging

## Problem

Chinese intake wording is ambiguous. "吃了" can mean food, prescription medication, supplement, or a record-management action such as "delete this meal". The current system now has local guards in `inline_cards.py` and `tool_validator.py`, but those rules are duplicated and will drift.

The product requirement is not just to avoid one bad card. Reva should classify the user's intake intent once, route it to the right Health OS object, and only present the user with a card they can safely confirm.

## Product Mapping

This feature maps to these first-class product objects:

- `WriteIntent`: proposed write-back action that must stay manually confirmed for diet, medication, and supplement writes.
- `ExecutionEvent`: confirmed food, medication, supplement, water, or management action.
- `HealthAgendaItem`: downstream agenda completion can consume medication/supplement execution events.
- `SafetyGuardian`: deterministic gates must beat LLM guesses for medication and dose-like text.

It strengthens the core loop by reducing wrong write-backs and making health records more trustworthy.

## Recommended Approach

Create a shared deterministic intake intent classifier used by all server write-adjacent paths.

The classifier returns:

- `kind`: `diet`, `medication`, `supplement`, `water`, `diet_management`, or `unknown`.
- `confidence`: conservative 0-1 value.
- `reason`: short machine-readable reason for logs and tests.
- `text`: normalized extracted item text.
- `slots`: optional hints such as `meal_type`, `amount_ml`, `dose`, or `timing`.

The classifier should be deliberately conservative. If a string contains medication names, medication suffixes, dose units, or drug forms, it must not become `diet`. If a string looks like a common food item, it can become `diet`. If it is ambiguous, it should become `unknown` and produce a clarification card rather than a false write.

## UX Behavior

For user text such as:

- "记录午餐吃了牛肉面" -> show diet draft card.
- "记录刚吃了替普瑞酮" -> show medication draft card.
- "刚吃了鱼油" -> show supplement draft card.
- "喝了 300ml 水" -> no diet draft; water path can handle it.
- "删除这一餐" -> no diet draft; route to diet management path.
- "刚吃了一个东西" -> low-confidence clarification instead of a write card.

The medication draft card should show:

- title: "用药待确认"
- medication name
- dose/timing if present
- confidence and source
- safety boundary: "确认后记录为已服用；不替代医嘱，不调整剂量"
- actions: confirm medication, open medication page, or ask Aheng

Phase 1 can reuse existing generic card rendering if a custom card is not yet present, but the implementation plan should add a mobile native card so the flow feels first-class.

## Safety And Error Handling

- All medication writes remain `manual_confirm`.
- The shared classifier is not a clinical parser. It only routes record type.
- Medication/dose-like strings must fail closed away from `diet`.
- Builder failures remain fail-loud in logs and should not block assistant text.
- Unknown/low-confidence classification should ask one short clarification, not create a record.

## Testing Strategy

Use a golden test matrix for intake phrases. It should cover:

- food records
- medication records
- supplement records
- water records
- diet-management phrases
- ambiguous phrases

Add tests at three seams:

- classifier unit tests;
- inline card routing tests;
- tool validator tests.

Mobile tests should verify that the new medication card renders and dispatches only safe manual-confirm actions.

## Non-Goals

- No image recognition changes in this slice.
- No automatic medication dose inference beyond extracting text hints.
- No autonomous medication write-back.
- No broad LLM prompt rewrite beyond schema guidance needed to route correctly.
