# XiaoBa AIGC Media PRD

Status: building

## Goal

Let a user ask Xiaoba, in the existing conversation flow, to turn an explicitly
attached image or a written health-action story into a private image or a short
video. The result should help communicate or follow through on a health action,
not make health claims or replace health guidance.

## V1 User Outcomes

1. The user attaches a photo and asks for an action-focused visual or a 3-15
   second short video.
2. Xiaoba creates an explicit confirmation card before it sends media to Model
   Studio or creates a billable job. The user must click that card; a sentence
   or a model-generated boolean cannot substitute for the click.
3. The user sees a dynamic job card in the same chat: submitted, generating,
   complete, or failed.
4. The result is privately owned, can be replayed/downloaded by the owner, and
   remains available after the provider's task record expires.

## Non-goals

- A generic social-video editor, a separate AIGC dashboard, public hosting, or
  automated social publishing.
- Medical image interpretation, diagnosis, treatment, drug/dose advice, or
  health outcome transformation claims.
- Silent jobs, background generations, or use of Token Plan keys for media.

## Scope And Models

| Capability | V1 model | Invocation | Input |
| --- | --- | --- | --- |
| Text-to-image / image edit | `wan2.7-image` | synchronous | prompt, optional active-turn image |
| High-quality image | `wan2.7-image-pro` | synchronous | prompt, optional active-turn image |
| Text-to-video | `wan2.7-t2v` | async | prompt |
| First-frame image-to-video | `wan2.7-i2v` | async | active-turn image and prompt |

The model IDs are configuration defaults, not hard-coded product behavior.
Operations must use a Model Studio pay-as-you-go API key and a regional endpoint
that match the configured workspace.

## Product Rules

- The Agent may draft a prompt, but an explicit user confirmation is required
  before any request leaves the product boundary.
- If the source image contains personal health information, the confirmation
  says it will be sent to Alibaba Cloud Model Studio for the requested job.
- Input image bytes and prompt text are never written to operational logs,
  telemetry, SSE, or error messages. Only job IDs, coarse kind/status, model
  ID, timestamps, and non-sensitive error codes are logged.
- Generated outputs are stored under the requesting user, served only through
  authenticated or short-lived signed URLs, and are excluded from public chat
  sharing by default.
- On cancellation/failure the job status is durable and visible. No background
  retry occurs without a fresh user confirmation.
- If the provider request outcome cannot be proved, the job shows "提交待核验"
  and stops automatic retries. The same immutable draft resolves to that job
  rather than creating a possible duplicate billable request.
- A confirmation freezes the selected Wan model. Per-user/global active-job
  limits, a daily dispatch budget, a database-enforced immutable request
  fingerprint, and task/account poll leases protect the shared account before
  an external request is made.

## Cross-surface Contract

```text
Mobile/Web/Mac attachment
  -> Agent request with active-turn media
  -> Agent draft -> encrypted AIGCMediaConfirmation
  -> owner click consumes one-time confirmation ID
  -> internal job dispatch
  -> AIGCMediaJob {dispatching|queued|running|succeeded|failed|cancelled|submission_unknown}
  -> DynamicCard {aigc_media_job}
  -> GET /aigc/media/jobs/{id} polling
  -> private image/video URL
```

The backend is the source of truth. Mobile is the initial first-class rendering
surface; web and Mac can use the same chat tool and job API without receiving
new fixed pages. Transcript cards persist only the durable job identity and
coarse state; each surface refreshes its owner-scoped job endpoint to obtain a
short-lived private media URL at display time.

## Acceptance Criteria

- An unconfigured service fails clearly before creating a job.
- A Token Plan key is not accepted as a media credential.
- A caller cannot access, poll, cancel, or obtain results for another user's job.
- A video job shows an actual provider task ID and polls it; it never returns a
  completed state until the provider succeeds and output is stored privately.
- A user must click a one-time confirmation card before source media crosses
  the provider boundary; confirmation is bound to the original source and
  cannot be replayed or altered by the client/model.
- An uncertain provider submission is never automatically re-sent, and an
  identical second confirmation returns the existing task instead of creating
  another paid task.
- Tests cover text-to-image request construction, image-to-video creation,
  status transitions, cancellation, owner isolation, tool policy, and mobile
  card rendering.
