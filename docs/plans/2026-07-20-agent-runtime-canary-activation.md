# Agent Runtime Internal Canary Activation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable the deployed Agent Runtime for one verified internal production account with zero hash-bucket traffic, prove recovery and write-receipt invariants, and retain a one-command rollback to the legacy path.

**Architecture:** Reuse the deployed `off/canary/enforce` control plane. Production configuration selects `canary`, `0%`, and one internal user ID; the database circuit remains the emergency stop. All validation uses aggregate Runtime state or the selected account's normal first-party Agent API, without storing prompt, response, health text, tool arguments, or tool results in the Runtime ledger.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, Celery, JWT administrator API, `deploy.sh` environment deployment.

---

## Safety Invariants

1. No percentage traffic is admitted: `AGENT_RUNTIME_CANARY_PERCENT=0`.
2. Exactly one verified internal account is allowlisted.
3. No production database row is edited manually; rollout changes use the administrator API and configuration changes use `deploy.sh`.
4. Runtime tables and rollout audit remain content-free.
5. A write drill must use a reversible, non-clinical test record and verify both the receipt and cleanup.
6. Any reconciliation, stale lease, duplicate side effect, user-visible regression, service error, or monitoring gap triggers immediate hard rollback to `AGENT_RUNTIME_MODE=off`.
7. No move to 1% traffic is part of this plan.

## Task 1: Establish the `off` Baseline

1. Confirm production services and public health are green.
2. Query the administrator rollout endpoint and record only aggregate state.
3. Confirm mode `off`, circuit `active`, no unacknowledged reconciliation generation, no stale active Run, and no recent Runtime failures.
4. Confirm the recovery task is inert while mode is `off`.

## Task 2: Verify the Internal Account

1. Enumerate active administrator/internal candidates without printing email, phone, name, health data, or conversation content.
2. Select an account that owns a recent first-party Agent conversation and can authenticate through the normal JWT contract.
3. Confirm there is exactly one selected user ID and retain it only in deployment configuration.
4. If no safe existing account exists, stop; do not create or guess a production identity.

## Task 3: Exercise the Circuit While Runtime Is Off

1. Create a short-lived administrator token through the production auth service.
2. POST the administrator pause endpoint; verify one `manual_pause` audit event and `paused` state.
3. Repeat pause; verify idempotence and no duplicate event.
4. POST resume; verify `active`, acknowledged reconciliation generation equals current generation, and one `manual_resume` event.
5. Repeat resume; verify idempotence and no duplicate event.
6. Confirm user Agent traffic remains unmanaged throughout because mode is still `off`.

## Task 4: Activate the Zero-Percent Internal Canary

1. Back up the local production `.env`.
2. Set `AGENT_RUNTIME_MODE=canary`, `AGENT_RUNTIME_CANARY_PERCENT=0`, and the single verified ID in `AGENT_RUNTIME_CANARY_USER_IDS`.
3. Validate configuration locally without exposing the allowlisted ID.
4. Deploy environment through `./deploy.sh -e`.
5. Verify services, public health, administrator rollout status, circuit state, threshold configuration, and Celery recovery evaluation.
6. Confirm a non-allowlisted decision remains unmanaged.

## Task 5: Prove the Read-Only Run Lifecycle

1. Send one short read-only Agent turn from the allowlisted account using a fresh `client_turn_id`.
2. Verify one canonical Run, one Attempt, ordered content-free events, one assistant message binding, and a terminal success state.
3. Retry the same `client_turn_id`; verify the same Run identity and no duplicate assistant message.
4. Verify Runtime rows contain no prompt, response, health text, tool arguments, or tool results.

## Task 6: Prove a Reversible Write Receipt

1. Use a dedicated reversible, non-clinical test record through the normal Agent API.
2. Verify exactly one business side effect, one `AgentToolOperation`, and a verified resource receipt.
3. Retry the same client turn and verify receipt replay without a second side effect.
4. Remove the test record through the normal first-party API and verify cleanup.
5. If a reversible record cannot be isolated safely, stop this task and do not substitute real health data.

## Task 7: Prove Pause and Recovery

1. Pause via the administrator endpoint.
2. Confirm a new allowlisted turn falls back to the unmanaged path while existing managed Runs remain queryable/cancellable.
3. Resume manually only after aggregate metrics and reconciliation generation are clean.
4. Exercise one bounded cancellation or interruption path and verify terminal settlement without duplicate output or side effect.

## Task 8: Observe and Close the Gate

1. Observe at least one complete rollout window using aggregate metrics and service logs.
2. Require zero reconciliation Runs, zero stale active Runs, zero duplicate effects, and no new user-visible errors.
3. Leave production at `canary + 0% + one internal account` only when every invariant passes.
4. Otherwise deploy `AGENT_RUNTIME_MODE=off`, verify recovery is inert, and record the failed Gate.
5. Update the activation Dossier, run Dossier/doc-drift checks, commit, push, and verify main CI.

## Promotion Boundary

Moving from the internal allowlist to 1%, 5%, or any broader traffic is a new operational Gate. It requires a fresh baseline, explicit success/error budgets, and a separate production observation window.
