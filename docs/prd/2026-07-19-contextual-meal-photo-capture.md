# PRD: 上下文餐食照片采集

## Goal

让“小巴收到的食物照片”成为可解释、可撤销、可复盘的饮食事实：在用户当地正常餐时，高可信餐食图可自动进入当天饮食；其余情境在当前对话内提供确认卡，而不是要求用户猜出“记录”口令。

## Product Decision

`DietRecord` 仍是唯一确认后的饮食事实，`HealthTwin` 只消费有 receipt 的记录。照片、视觉识别与语义判断先形成候选；自动化不是模型自由决定，而是受限的 `WriteIntent(auto)`：用户主动上传 + 食物候选 + 用户当地餐时 + 高置信 + 去重。其余一律 `WriteIntent(manual_confirm)`。

这项决策对既有“饮食打卡极致体验”的纯手动确认路径作窄范围升级：直接饮食页和低置信路径继续人工确认；仅小巴聊天中的合格餐时图片允许自动记录并提供撤销。

## User Flow

```text
chat image
  -> structured food vision + semantic visual intent + user-local meal context
  -> non-food / analyze-only: explanation, no draft
  -> qualified auto: private diet asset -> idempotent DietRecord -> receipt + undo card
  -> otherwise: private diet asset -> DietPhotoDraft -> inline confirm/edit card
  -> diet history: signed image_urls -> thumbnail/gallery -> same record on Mobile/Web/Mac
```

### Local Meal Windows

The service resolves `manual_timezone -> detected_timezone -> profile timezone -> Asia/Shanghai` using the existing timezone utility. Initial policy windows are configuration constants, not prompt text:

| Local window | Meal type | Default outcome |
|---|---|---|
| 05:00–10:59 | breakfast | eligible for auto record |
| 11:00–14:59 | lunch | eligible for auto record |
| 17:00–21:59 | dinner | eligible for auto record |
| all other time | snack/extra | confirmation only |

An explicit semantic request to analyze, estimate, compare or ask a question remains `analyze_only`; an explicit semantic request to save is eligible outside these windows but still requires a visual food candidate. The resolver must return structured intent, never use keyword/regular-expression matching as the decision source.

## Database Design

`diet_records.image_url` remains a backward-compatible cover image field. The authoritative media relation becomes `diet_photo_assets`, which supports one or more owner-scoped images per record and pending image drafts.

```sql
CREATE TABLE diet_photo_assets (
    id UUID PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    diet_record_id INTEGER REFERENCES diet_records(id) ON DELETE SET NULL,
    photo_draft_token VARCHAR(64) REFERENCES diet_photo_drafts(token) ON DELETE SET NULL,
    storage_key VARCHAR(1024) NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    media_type VARCHAR(40) NOT NULL,
    origin VARCHAR(40) NOT NULL,
    origin_message_id INTEGER NULL,
    ordinal SMALLINT NOT NULL DEFAULT 0,
    captured_at TIMESTAMPTZ NULL,
    captured_timezone VARCHAR(64) NULL,
    classification VARCHAR(24) NOT NULL,
    recognition_confidence DOUBLE PRECISION NULL,
    intent_decision VARCHAR(24) NOT NULL,
    recognition_snapshot JSONB NULL,
    lifecycle VARCHAR(24) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    attached_at TIMESTAMPTZ NULL,
    deleted_at TIMESTAMPTZ NULL,
    UNIQUE (user_id, origin_message_id, ordinal),
    UNIQUE (diet_record_id, ordinal)
);
CREATE INDEX idx_diet_photo_assets_user_record
  ON diet_photo_assets(user_id, diet_record_id, ordinal);
CREATE INDEX idx_diet_photo_assets_draft
  ON diet_photo_assets(photo_draft_token);
CREATE INDEX idx_diet_photo_assets_hash
  ON diet_photo_assets(user_id, content_sha256, created_at);
```

`storage_key` is an owner-encoded canonical private path, never a pre-signed URL. Read APIs generate short-lived signed URLs at response time. `recognition_snapshot` stores sanitized structured result and policy evidence, not raw chat text or a model chain of thought. The first attached asset mirrors into legacy `DietRecord.image_url`; responses add `image_urls` and `photo_assets` while retaining `image_url` for older clients.

## API Contract

```yaml
DietRecordResponse:
  image_url: string | null        # legacy cover, signed at read time
  image_urls: string[]            # ordered signed URLs
  photo_assets:
    - id: string
      url: string
      ordinal: integer
      captured_at: datetime | null
      origin: chat | camera | library | watch | rokid

MealPhotoDecision:
  decision: auto_record | confirm | analyze_only
  meal_type: breakfast | lunch | dinner | snack | extra
  local_time: datetime
  timezone: string
  reason_codes: string[]
  record_id: integer | null
  photo_draft_token: string | null
```

Only the backend decides `decision`, writes media and returns receipt. Clients do not synthesize success; auto record cards require `record_id`, confirmation cards require an owner-bound draft token, and error cards must state that no record was written.

## Acceptance Criteria

```gherkin
Given a user in America/New_York sends a high-confidence food image at 12:30 without text
When the contextual policy runs
Then exactly one lunch DietRecord is persisted with a receipt and a diet-photo asset
And the response contains a signed image URL owned by that user

Given the same image and client turn are retried after a timeout
When the policy runs again
Then the same DietRecord receipt is returned and no second asset or record is created

Given a high-confidence food image at 23:30 or an ambiguous food image at lunch
When the contextual policy runs
Then no DietRecord is auto-written
And the current chat view offers a correction/confirmation card with the image asset

Given an uploaded screenshot, medication package, supplement bottle or non-food image
When vision and semantic intent run
Then no diet asset is attached to a DietRecord and no diet confirmation is offered

Given a confirmed or auto-recorded diet entry with two attached images
When it is read by Mobile, Web or Mac
Then the API returns ordered owner-signed image URLs and the surface renders the cover plus gallery access

Given a write failure before a database receipt
When the chat responds
Then it does not display “已记录” and preserves a recoverable pending draft or explicit retry action
```

## Privacy, Safety and Rollout

- Photos stay private and owner-scoped; logs contain ids and reason codes, not food content, raw image or signed URLs.
- Nutrition remains an estimate unless independently measured; no diagnosis, prescription, dose or causal claim is introduced.
- Automatic writes are allowlisted to diet records only and have a single-tap undo. There is no automatic notification, sharing or external media transfer.
- Deploy backend and migration first, generate Web/Mobile API types, then ship Mobile OTA. Existing `image_url` readers remain functional during phased client adoption.
