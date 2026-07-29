# XiaoBa AIGC Media Feature Spec

Status: building

## API

The Agent's internal `draft_aigc_media` tool creates an encrypted,
owner/source/model-bound `AIGCMediaConfirmation`; it never calls the provider.
There is intentionally no public client `POST /api/v1/aigc/media/jobs` route.
The only client write is `POST /api/v1/aigc/media/confirmations/{id}/confirm`:
an authenticated user's card click sends no prompt, media, model, or source
parameter and atomically consumes the short-lived server record. `GET
/api/v1/aigc/media/jobs/{job_id}` and `POST
/api/v1/aigc/media/jobs/{job_id}/cancel` are owner-scoped.

Responses contain no raw prompt/source input. A live owner-scoped response may
contain a short-lived private result URL; that URL is never persisted into the
conversation card. Responses expose only an `AIGCMediaJob` projection:

```json
{
  "id": "uuid",
  "kind": "image_to_video",
  "status": "running",
  "progress": 25,
  "model": "wan2.7-i2v",
  "result": {"media_type": "video", "url": null},
  "created_at": "2026-07-17T00:00:00Z"
}
```

## Data Model

`aigc_media_jobs` is an owner-scoped job ledger. It stores requested
kind/model/status/progress and provider task ID; a source reference to the
user message/image index; an HMAC request fingerprint; private output object
key/media type/result metadata; and terminal timestamps/error state.

`aigc_media_confirmations` stores the one-time draft: owner/conversation/source
reference, kind/purpose/model, encrypted prompt, HMAC prompt fingerprint,
duration/ratio, expiry, consumption state, and linked job ID. The selected Wan
model is frozen before the user confirms and participates in the fingerprint;
runtime configuration changes cannot silently change a confirmed billable job.
Raw prompt text is never accepted from the confirmation endpoint or written to
audit records.

`aigc_media_jobs` enforces a unique `(user_id, request_fingerprint)` pair. The
service repeats its fingerprint lookup under a PostgreSQL advisory transaction
lock before capacity reservation, and the database constraint is the final
cross-process guarantee against a second charge for an immutable request.

## State Machine

```text
confirmation: pending -> dispatching -> dispatched
                                -> deduplicated (same immutable draft already has a job)
job: dispatching -> queued -> running -> succeeded
                   |          |          -> failed
                   |          -> cancelled
                   -> submission_unknown
```

Only the server moves these states. Terminal job transitions use conditional
updates, so cancellation cannot later become success. `succeeded` requires a
provider result and a successful private-output persistence receipt. Temporary
polling errors keep the job active for retry; only a provider terminal failure
marks it failed. A request transport failure, malformed successful provider
response, or process failure after external submission becomes
`submission_unknown`: the system does not automatically retry it or create a
second task for the same immutable fingerprint.

## Agent Contract

`draft_aigc_media` is allowed only for explicit media-creation intent and can
only use an image attached to the active user message. It returns a
transcript-safe confirmation card. It cannot express or consume provider
consent. A separate owner card click creates the job, and the accepted dispatch
writes a prompt-free audit record with job ID, kind, model, and whether a source
image crossed the provider boundary.

## Dynamic Capability

`aigc_media_confirmation.v1` is a manual-confirm dynamic card for
`mobile.chat`, `web.chat`, and `mac.chat`; it discloses that the user's creative
description and optional current image will go to Wan, then submits only its
opaque confirmation ID. `aigc_media_job.v1` is the owner-scoped private result
projection. Neither card persists a signed result URL, raw prompt, or source
URL.

## Provider Boundary

`DASHSCOPE_AIGC_API_KEY` is mandatory and distinct from `TOKENPLAN_API_KEY`;
the service rejects equality with the Token Plan credential. It uses the
official Wan 2.7 image endpoint for synchronous images and asynchronous video
task endpoint for video. The provider boundary deterministically allows only
bounded wellness-action purposes and rejects diagnosis, prescription, dose,
treatment-decision, medication entity, and health-outcome guarantee media
before any external request. This deterministic check is a narrow provider
authorization backstop, not Xiaoba's conversational intent classifier. Result
downloads are streamed with image/video size caps and accepted only from
Alibaba Cloud HTTPS hosts.

Provider dispatch enforces configuration-backed per-user and global active-job
limits, a per-user daily dispatch budget, and a minimum task-poll interval.
Task and account poll leases are claimed atomically before each provider HTTP
request; PostgreSQL serializes those claims with advisory transaction locks.
Default limits keep the account below the documented task-query rate ceiling. A
public valid-HTTPS `SITE_BASE_URL` is additionally required for image-to-video
source retrieval; it must be deployed and verified before that capability is
enabled.

## Mobile Playback And Sharing

Completed image and video cards render the existing private result in the Agent
conversation. Video playback and media sharing are read-only actions: neither
is allowed to call confirmation, retry, or generation endpoints.

Before sharing, Mobile refreshes the owner-scoped job projection to obtain a
fresh short-lived URL, downloads the image or MP4 into the application cache,
and opens the iOS share sheet with the local media file. The temporary file is
deleted after sharing or a failed download. Repeated taps while one share is
active are coalesced, so sharing cannot create a second provider task or charge.

The shared image utility also accepts authenticated Agent-conversation images
and local screenshot paths. Protected images are downloaded with the active
authorization header; bare iOS temporary paths are normalized to `file://`
before opening the native share sheet.

The WeChat and Xiaohongshu buttons use compact platform artwork. Xiaohongshu
uses its official application artwork instead of a generic book icon. Platform
labels are an entry hint; the installed iOS share extensions decide the final
destination.
