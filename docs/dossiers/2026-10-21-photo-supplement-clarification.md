# Photo supplement record clarification

## Scope

User screenshot: a bottle photo with `记录益生菌补剂` received a generic guidance hold. No actual health records or live models were inspected.

## Finding and implementation

The existing deterministic photo supplement parser only supports a closed multi-product/count phrase. Incomplete single-product captions bypassed it and reached general model guidance. Add a separate, non-writing clarification branch for explicit incomplete captions. Ask whether this is an inventory entry or an already-taken event, then request product identity and, for intake, actual amount/unit/time. Never infer ingestion, recipient, or dosage from a label. Preserve the existing complete-request proposal/confirmation path. Persist a `waiting_for_user` outcome rather than claiming success or showing a retryable failure.

The clipped stop-medication message is not resolved by this change. Its exact text and target cannot be recovered reliably from this screenshot; no medication mutation is performed.

## Evidence

- SQLite focused suite: 41 passed (`/tmp/reva-photo-details-tests.log`).
- First test invocation failed during setup because the default local PostgreSQL port was unavailable; not a behavioral red result.
- PostgreSQL focused suite: pending (`/tmp/reva-photo-details-pg.log`).
- System Map gate passed (`/tmp/reva-photo-details-map.log`).
- Safety review, full CI, deployment: pending. No mobile change; no OTA warranted for this patch.
