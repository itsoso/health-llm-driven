# Arrival and boarding conversation context

## Report and cause

The screenshot statement `10:00 落地北京 10:20 打上车` reached the health-query failure reply following a symptom-record turn. Existing context parser supports a simple arrival and one closed metro timeline but not this two-event clock form. Existing standalone-history guard also excludes recent symptom conversations. No real health or chatlog data was inspected.

## Change

Add a whole-input arrival/boarding grammar with bounded valid clocks and existing known-place catalog. Only this self-contained completed statement may use the same nonwriting context reply path as the existing transit timeline even after a prior clinical turn. Current retry/image/extra-context and ownership guards remain unchanged. Echo only supplied clocks/city; infer no date/timezone/location confirmation/clinical fact. Explicit query/write/hypothetical/third-party/quoted/medical additions do not match and retain ordinary routing. No health tool/model call or medication/symptom mutation; conversation persistence remains normal.

## Evidence

Initial test command encountered local PostgreSQL connection refusal before collection. An isolated load of the immutable pre-change parser then reproduced the exact screenshot admission failure (RED). With isolated test configuration, related context/intent/stream suite passed142 tests. Dedicated UTF8 PostgreSQL run pending. No production deployment or model evaluation has occurred. Independent safety review pending.

## Delivery boundary

Carry forward the unified release: pending medication UI8505d9902 and OTA baseline e3a6fbc72. Do not claim these are deployed; AppReview279 OTA freeze remains pending user's policy choice. This server-side fix does not require a new native binary.
