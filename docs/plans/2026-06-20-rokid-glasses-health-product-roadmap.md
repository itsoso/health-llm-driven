# Rokid Glasses Health Product Roadmap

> For Claude/Codex: REQUIRED SUB-SKILL: use `executing-plans` before turning any section below into code tasks.
>
> Date: 2026-06-20
> Status: planning draft for `main`
> Scope: Rokid Glasses as an ambient Health OS execution surface

## 0. Executive Decision

Rokid Glasses should become Reva's hands-free capture and execution surface, not a standalone health dashboard.

The winning product shape is:

```text
Rokid Glasses
  -> capture what the user sees / says / is doing
  -> show or speak one short next action
  -> produce an auditable event
  -> let Mobile / Watch / Mac confirm, edit, or review
  -> let Backend Health OS decide, gate, rank, and learn
```

The first three product wedges are:

1. Food photo capture: "拍一下这餐" -> photo -> food draft -> calories / macros -> confirm -> post-meal action.
2. Voice-operated execution: "开始俯卧撑" / "记录午餐" / "今天练什么" -> Reva routes the action without phone taps.
3. Push-up real-data coaching: glasses app uses local camera pose detection -> structured rep / quality events -> Reva saves exercise execution.

Do not build:

- a long health report inside the glasses;
- a general chat UI on the glasses;
- background always-on camera or microphone capture;
- autonomous medication, supplement, diagnosis, or treatment decisions.

## 1. Product Admission

This plan passes `docs/specs/reva-product-governance-spec.md` because it strengthens the Health OS loop:

```text
observed scene / voice / workout
  -> HealthTwin context
  -> SafetyGuardian
  -> LeverageAction / HealthAgendaItem
  -> Rokid / Watch / Mobile execution
  -> ExecutionEvent / WriteIntent
  -> outcome review
```

First-class object mapping:

| Requirement | Health OS object |
|---|---|
| Food photo from glasses | `WriteIntent`, `ExecutionEvent`, `HealthTwin` evidence |
| Food calories / nutrition draft | `WriteIntent`, `SafetyGuardian` for risky claims |
| Voice action trigger | `HealthAgendaItem`, `LeverageAction`, `WriteIntent` |
| Push-up detection | `ExecutionEvent`, `HealthProtocol`, `InterventionCycle` |
| Movement guidance | `LeverageAction`, `SafetyGuardian`, `HealthAgendaItem` |
| Short glasses prompt | `GlanceCard`, `HealthAgendaItem` |
| Lab-record upload entry | Mobile/Mac `WriteIntent`; glasses only as optional quick capture, not document workstation |

Surface ownership:

| Surface | Ownership |
|---|---|
| Rokid Glasses | See, hear, speak, show one short prompt, run a narrow movement app. |
| Mobile | Permissions, SDK bridge, capture confirmation, image/document intake, Rokid launch control. |
| Watch | Final quick confirmation, skip/later, completion heartbeat. |
| Mac | Deep review, lab/document import, agent conversation with pasted images/docs. |
| Backend | Source of truth, user isolation, safety gates, action ranking, audit ledger. |

## 2. Public Device Capability Read

This plan uses public Rokid pages only as capability direction, not as binding SDK contracts.

| Product | Publicly visible capability | Product implication |
|---|---|---|
| Rokid Glasses Display | Official product page lists dual-eye display, 12MP camera, built-in AI assistance, real-time translation, all-day battery, 49g weight, directional microphones, and speaker hardware. | Best target for CustomView / short HUD prompts, food photo, voice-triggered capture, and on-glasses push-up feedback. |
| Rokid AI Glasses Style Non-Display | Official product page labels it non-display, describes practical use cases such as AI questions, real-time translation, AI photo recognition, meeting notes, navigation, calls capture, and says it has no display function. | Good target for capture and voice, but not for HUD. Reva must fall back to voice/audio + phone/watch confirmation. |
| CXR-L SDK | Rokid AR Platform search result says CXR-L lets apps extend Rokid AI APP scenarios and access glasses IO capabilities including image and audio. | Reva should treat image/audio access as SDK-gated and verify each callback on real hardware before product claims. |

Public references:

- [Rokid Glasses Display](https://global.rokid.com/products/rokid-glasses)
- [Rokid AI Glasses Style Non-Display](https://global.rokid.com/products/rokid-ai-glasses-style)
- [Rokid Academy](https://global.rokid.com/pages/academy)
- [Rokid CXR-L SDK](https://ar.rokid.com/sdk?lang=en)

## 3. Current Main Baseline

> ⚠️ Reality check (2026-06-20 device evidence). The CXR-L **command channel is currently non-functional on hardware**. On a real device with BLE connected and authorization granted, `openCustomView` returns `rokid_custom_view_open_callback_missing` with `rawNotify=none` / `running=false` (the SDK callback never fires and no notify comes back), and `installApp` returns `rokid_pushup_app_install_failed`. The assets listed below exist as code, but **none of the three product wedges can run end-to-end today**. Read all of §3 as "wired in code, unproven on hardware" until Phase 0 closes. A pending fix (re-subscribe the CustomView notify cmds on BLE (re)connect, commit `5e3d1ea2`) is in EAS build #167 awaiting device verification; if it still shows `rawNotify=none`, the silence is below the bridge layer (companion / firmware / session) — see §13 and Phase 0.

`main` already has enough infrastructure to plan against real repo assets.

### 3.1 Mobile bridge

`mobile/modules/rokid-bridge/index.ts` exposes:

- `getRokidIntegrationStatus()`
- `openHiRokid()`
- `requestRokidAuthorization()`
- `openRokidCustomView()`
- `updateRokidCustomView()`
- `closeRokidCustomView()`
- `takeRokidPhotoBase64()`
- `queryRokidApp()`
- `openRokidApp()`
- `stopRokidApp()`
- `startRokidRecord()`
- `stopRokidRecord()`

The bridge already has a validation step model for:

- iOS SDK linked;
- Hi Rokid ready;
- CXR-L authorized;
- CustomView running;
- capture ready.

### 3.2 Mobile Rokid health mode

`mobile/app/rokid-health.tsx` already includes:

- Rokid status;
- Hi Rokid launch;
- Rokid authorization;
- Reva glasses CustomView;
- glasses photo capture through `takeRokidPhotoBase64`;
- submission to `/ambient/visual-inputs`;
- glance cards for `surface=rokid_glasses`;
- entry to the push-up coach.

### 3.3 Ambient backend

Backend currently has:

- `/api/v1/ambient/audio-inputs`
- `/api/v1/ambient/visual-inputs`
- `/api/v1/ambient/glance-cards`
- ambient audio / visual / glance models and tests.

This is the right abstraction. Rokid input should not directly create long-term health records; it should create draft evidence and `WriteIntent` candidates first.

### 3.4 Push-up real-data path

`docs/plans/2026-06-18-rokid-pushup-real-data-integration.md` and `apps/rokid-pushup-glasses` define a practical real-data route:

```text
iOS Reva
  -> creates backend push-up session
  -> opens glasses Android CustomApp
  -> glasses app uses camera + MediaPipe Pose
  -> posts pose / rep / session_state events to backend
  -> mobile polls events and updates coach UI
  -> Reva saves exercise execution
```

This route avoids pretending iOS has a pose stream callback when the public iOS CXR-L surface does not prove one.

### 3.5 Voice command baseline

`docs/specs/active/2026-06-19-rokid-voice-control.md` now defines the Rokid voice control plane:

- explicit voice trigger only;
- no continuous background listening;
- transcript -> deterministic command router -> bounded client action;
- supported commands for food photo, push-up start/stop/save, guided movement, confirm, skip, later, unknown;
- audit through ambient audio events.

`mobile/services/rokidVoiceControl.ts` already provides the mobile service layer:

- `startRokidVoiceCommandCapture()`;
- `stopRokidVoiceCommandCapture()`;
- `submitRokidVoiceCommand()`;
- `executeRokidVoiceClientAction()`.

The bridge **declares** an `onRokidTranscript` event (`Events("onRokidTranscript")`) and the backend `/ambient/rokid-voice-commands` intent router exists — but the native side **never emits the event** (`sendEvent` count = 0; there is no audio→transcript step). The SDK exposes a raw `audioEventPublisher`, but the bridge neither subscribes to it nor runs any ASR. So the voice loop is broken at the source: speech is never turned into a transcript, the JS listener never fires, and no command executes. The remaining work is therefore **not** "verify the callback on hardware" — it is to **implement the transcript source first**: on-device ASR (`SFSpeechRecognizer` over the SDK audio stream) or a glasses-side ASR transcript delivered via the notify channel. Until that exists there is nothing for Phase 2 to verify.

### 3.6 Diagnostics baseline

`mobile/services/rokidDiagnostics.ts` and the updated Rokid health screen already expose detailed self-check information:

- bridge ready/missing;
- SDK linked/not linked;
- companion ready/missing;
- authorization state and callback diagnostics;
- session readiness;
- CustomView payload hash, raw notify, callback, retry, and error details;
- recent authorization and native diagnostic timeline.

This should become the user-visible and QA-visible capability truth table for all future Rokid work.

### 3.7 Main gaps

The next work should close these gaps in order:

1. Voice command spec, mobile client service, and backend intent router exist, but the **native transcript source is unimplemented** (the `onRokidTranscript` event is declared but never emitted; no ASR, no audio-stream consumer). This must be **built**, not merely proven, before phone-free voice execution is even testable.
2. Food photo path needs draft confirmation and nutrition write-back, not just visual input submission.
3. Push-up path needs a hardware verification checklist and explicit "test event -> live rep -> saved workout" acceptance flow.
4. Display and non-display Rokid SKUs need different UX fallback rules.
5. Diagnostics should be promoted into a formal capability matrix and release gate, not treated as debug text only.

## 4. Product Pillars

### 4.1 Capture-To-Draft

Goal: make any user-triggered visual or audio capture become a draft health event within seconds.

Primary flows:

- food photo;
- nutrition label photo;
- supplement bottle / medication label photo;
- lab report image/document upload on Mobile/Mac;
- symptom or food voice transcript;
- workout environment capture.

Rules:

- Capture never equals confirmed health record.
- AI extraction creates a `WriteIntent`.
- User confirmation is required for diet, supplement, medication, symptom, lab, and diagnosis-related writes.
- Low-confidence capture should ask one short follow-up or defer to phone/Mac.
- Public/workplace privacy zones default to summary-only unless the user explicitly saves the image.

### 4.2 Voice-To-Action

Goal: the user should not need to touch the phone during hands-busy scenarios.

Initial voice commands:

| User says | Reva action |
|---|---|
| "拍一下这餐" | Trigger Rokid photo, create food draft, show short feedback. |
| "记录午餐: 牛肉面一碗, 鸡蛋一个" | Create food voice draft. |
| "开始俯卧撑" | Create push-up session and launch glasses app if installed. |
| "今天练什么" | Read top safe agenda item and show/speak one action. |
| "暂停" / "结束训练" | Pause or finish current guided session. |
| "稍后提醒" | Convert current action to delayed agenda event. |
| "不用了" | Skip current action with optional reason capture. |

Rules:

- No continuous listening by Reva.
- Voice capture must be explicit: push-to-talk, Rokid OS wake, or a Reva session button.
- Voice transcript is evidence, not command truth. The command router must require confidence and context.
- Medication and supplement commands can confirm already-planned adherence, but cannot create new dosing advice.

### 4.3 Glanceable Execution

Goal: glasses show the next useful thing, not the whole app.

Allowed glasses output:

- one-line current action;
- one-line feedback during exercise;
- capture success/failure;
- safety escalation short text;
- "go to phone/Mac to review" handoff.

Examples:

```text
拍摄完成: 等你在手机确认晚餐
俯卧撑 8/12: 身体线条稳定
今天优先: 饭后走 10 分钟
数据不够: 请在手机补充餐量
```

Do not show:

- a full dashboard;
- detailed lab interpretation;
- long nutrition report;
- multi-turn chat transcript;
- speculative diagnosis.

### 4.4 Movement Coach

Goal: use the glasses where first-person vision is better than phone/watch.

Initial exercise ladder:

1. Push-up: camera can see upper body and count reps.
2. Squat: needs lower-body visibility and posture checks.
3. Plank: needs static hold timer + body line.
4. Mobility drill: glasses show one movement cue; phone supplies video if needed.
5. Outdoor walk/run: glasses provide short route/intensity prompts; Garmin/Watch remain training truth.

Rules:

- Use deterministic state machines for rep counting before adding LLM feedback.
- Never upload raw exercise video by default.
- Store structured pose / rep / quality events.
- SafetyGuardian can downshift intensity based on readiness, symptoms, HR, pain, or training load.

### 4.5 Safety, Privacy, Audit

Goal: make glasses useful without becoming creepy or medically unsafe.

Hard boundaries:

- no passive public capture;
- no always-on microphone owned by Reva;
- no hidden workplace recording;
- no automatic medication changes;
- no medical diagnosis from a glasses photo;
- no raw video upload for push-up coaching;
- all user-owned records must be scoped by `user_id`;
- session tokens must be short-lived and write-only when used by the glasses app.

## 5. Golden Paths

### 5.1 Food Photo

User story:

```text
I am eating and my hands are busy.
I say "拍一下这餐".
Rokid captures a photo.
Reva creates a food draft with calories, protein, carbs, fat, confidence, and uncertainty.
I confirm or edit on phone/watch.
Reva records the meal and suggests the next action if useful.
```

Target flow:

```text
Voice trigger / mobile button
  -> Rokid capture capability check
  -> takeRokidPhotoBase64
  -> POST /ambient/visual-inputs capture_kind=food
  -> food vision parser
  -> FoodWriteIntent
  -> Mobile/Watch confirm card
  -> DietRecord source=rokid_glasses
  -> optional post-meal HealthAgendaItem
```

Acceptance:

- User can initiate without manually opening a nested phone screen after setup.
- Capture-to-draft P50 < 8 seconds, P95 < 20 seconds.
- Draft contains at least dish name, estimated kcal, protein, carb, fat, confidence, and one uncertainty note.
- Confirmation writes exactly one `DietRecord`.
- Failed photo produces a clear glasses/phone error and does not create a phantom diet record.

Implementation slices:

1. Add a `capture_kind=food` end-to-end test for Rokid visual input.
2. Route Rokid food visual input to the existing food image parser or a shared food draft service.
3. Add `source=rokid_glasses` and raw capture metadata to the food draft.
4. Add Mobile confirm/edit UI that reuses existing diet confirmation where possible.
5. Add Watch quick confirm/later/discard for simple high-confidence drafts.
6. Add metrics: `rokid_food_capture_started`, `draft_created`, `confirmed`, `discarded`, `edited`, `failed`.

### 5.2 Voice Food

User story:

```text
I say "记录午餐, 牛肉面一碗, 鸡蛋一个".
Reva turns it into a food draft and asks at most one clarification.
```

Target flow:

```text
Rokid voice transcript
  -> POST /ambient/audio-inputs intent=food
  -> diet voice parser
  -> FoodWriteIntent
  -> confirm on Watch/Mobile
  -> DietRecord
```

Acceptance:

- Voice-to-draft P50 < 6 seconds.
- The parser asks at most one question before deferring to phone.
- No raw transcript is retained longer than policy without user-visible record.
- Low-confidence entries stay as drafts.

Implementation slices:

1. Use the existing Rokid voice command spec and client service as the source contract.
2. Extend command router tests for food, push-up, agenda, pause, finish, skip, later, and unknown.
3. Wire Rokid `startRecord`/`stopRecord` into ambient audio input once SDK transcript callback is proven.
4. Add fallback: if SDK transcript is not available, use Mobile/Watch voice entry with `source=rokid_requested`.

### 5.3 Push-Up Real Data

User story:

```text
I say "开始俯卧撑".
The glasses app starts.
It counts reps and gives short form feedback.
After the set, Reva saves the workout event and updates my protocol.
```

Target flow:

```text
Voice or mobile trigger
  -> create /devices/rokid/pushup-sessions
  -> queryRokidApp life.executor.health.rokid.pushup
  -> openRokidApp reva://rokid/pushup?...ingest_token=...
  -> glasses CameraX + MediaPipe local pose
  -> POST pose / rep / session_state
  -> mobile poll or realtime stream
  -> finish session
  -> ExecutionEvent + workout record
```

Acceptance:

- `queryRokidApp` returns installed before launch.
- `openRokidApp` starts the glasses app.
- The glasses app sends a `session_state=ready` event within 3 seconds.
- At least one synthetic `pose` test event appears in Mobile within 1 second.
- A real set of 5 reps creates 5 `rep` events with monotonic counts.
- Finishing the session stores a workout execution event and does not expose raw video.

Implementation slices:

1. Add a device verification checklist to `apps/rokid-pushup-glasses/README.md`.
2. Add a backend test for event monotonicity and session ownership.
3. Add Mobile state labels: not installed, opening, ready, receiving events, stale, finished.
4. Add a "send test event" developer mode in the glasses app.
5. Persist completed push-up sets into the existing exercise/workout record path.
6. Add post-session coaching summary from deterministic stats first.

### 5.4 Today's Action

User story:

```text
I ask "今天练什么" or "现在该做什么".
Rokid shows one safe top action, not a list.
```

Target flow:

```text
Voice command
  -> agenda summary endpoint
  -> SafetyGuardian readiness gate
  -> top HealthAgendaItem
  -> GlanceCard surface=rokid_glasses
  -> CustomView update or voice reply
  -> user accepts / later / skips
  -> ExecutionEvent
```

Acceptance:

- One answer only.
- The action includes why now, how long, and the next confirmation.
- Red readiness state never pushes strength training.
- Skip/later is captured as an execution event.

### 5.5 Lab Record Intake

User story:

```text
I receive a lab report image or PDF.
I upload it in the Mac/mobile conversation.
Reva extracts structured markers and creates review tasks.
```

Rokid role:

- optional quick photo of a paper report if the user explicitly triggers it;
- not the main lab-document workstation.

Mac/mobile role:

- image/PDF/document upload entry in conversation;
- paste/copy image into the dialog;
- structured extraction;
- confirmation and audit trail.

Acceptance:

- Lab files are handled as L3 health data.
- Extraction creates reviewable structured markers.
- No lab interpretation is sent to glasses as long-form text.

## 6. Capability Matrix

Each runtime should expose a capability matrix instead of a binary connection status.

```ts
type RokidCapabilityMatrix = {
  deviceModel: 'display_glasses' | 'style_non_display' | 'unknown';
  companionReachable: boolean;
  sdkLinked: boolean;
  authorized: boolean;
  customView: 'available' | 'not_supported' | 'unknown';
  photoCapture: 'available' | 'permission_needed' | 'not_supported' | 'unknown';
  audioRecord: 'available' | 'permission_needed' | 'not_supported' | 'unknown';
  transcriptCallback: 'available' | 'not_proven' | 'not_supported' | 'unknown';
  appLaunch: 'available' | 'not_supported' | 'unknown';
  pushupAppInstalled: boolean;
  lastVerifiedAt?: string;
};
```

Product fallback rules:

| Missing capability | Fallback |
|---|---|
| no display | voice response + phone/watch confirmation |
| no photo callback | open phone camera flow with `source=rokid_requested` |
| no transcript callback | mobile/watch voice capture |
| push-up app not installed | show install instructions and allow phone/manual mode |
| SDK not linked | keep scaffold and show build/profile requirement |
| authorization expired | show one authorization step, do not retry silently forever |

## 7. Data Contracts

> Complexity-budget guard. Do **not** persist any new first-class object below until Phase 0 proves the relevant channel. Until then reuse the existing ambient draft objects only (`VisualInputEvent`, ambient audio input, `GlanceCard`). Each new persisted object (`VisualContextCapture`, `RokidVoiceCommand`, `RokidMovementSession`, `RokidMovementEvent`) must pass the first-class-object admission Gate in `docs/specs/reva-product-governance-spec.md` before it is built. The shapes below are target/long-term contracts, not a build list — modelling them ahead of a proven channel is exactly the premature-design the complexity budget forbids.

### 7.1 Visual Capture

The existing `VisualInputEvent` can support v1. Long-term contract:

```text
VisualContextCapture
  user_id
  source_device=rokid_glasses | phone_camera
  source_surface=rokid_health_mode | rokid_voice_command | mobile_capture
  capture_kind=food | nutrition_label | medication_label | supplement_label | lab_report | workout_context
  privacy_zone=private | public | workplace | medical | unknown
  media_ref
  extracted_text
  extracted_entities
  confidence
  resulting_write_intent_id
  user_confirmation_state
```

### 7.2 Voice Command

```text
RokidVoiceCommand
  user_id
  session_id
  source_device
  transcript
  transcript_confidence
  intent=food_capture | food_voice | start_pushup | finish_session | agenda_query | skip | later | unknown
  context
  command_confidence
  resulting_action
  resulting_write_intent_id
  confirmation_required
```

### 7.3 Movement Session

```text
RokidMovementSession
  user_id
  movement_type=pushup | squat | plank | mobility
  target_reps
  source_protocol_id
  readiness_snapshot_id
  safety_gate_result
  started_at
  finished_at
  status
```

Events:

```text
RokidMovementEvent
  session_id
  event_type=pose | rep | session_state | warning
  reps
  phase
  quality_score
  visibility
  payload
```

### 7.4 Glance Card

Existing `GlanceCard` should stay short-lived.

```text
GlanceCard
  surface=rokid_glasses
  title <= 20 chars
  body <= 60 chars
  action_hint
  expires_at
  source_agenda_item_id
```

## 8. Architecture

```text
Rokid Glasses
  camera / mic / display / speaker / CustomApp
      |
      | CXR-L / CXR-S / Hi Rokid
      v
Mobile Reva App
  rokid-bridge
  Rokid health mode
  food / voice / push-up launcher
      |
      v
Backend API
  /ambient/audio-inputs
  /ambient/visual-inputs
  /ambient/glance-cards
  /devices/rokid/pushup-sessions
  /diet/voice or food draft services
  SafetyGuardian
  Agenda / Health OS ledger
      |
      v
Watch / Mobile / Mac
  confirm
  edit
  skip/later
  review
```

Principles:

- Backend remains source of truth.
- Mobile owns SDK bridge and user permissions.
- Glasses only receive session-scoped tokens for narrow writes.
- Watch/Mobile own fast confirmation.
- Mac owns document-heavy review.

## 9. Roadmap

### Phase 0: Capability Truth Table

Duration: 1 week.

Goal: stop guessing what the current device/SDK can do.

Phase 0 is a **hard go/no-go** — it can invalidate or re-scope Phases 1-6, all of which are gated on the CXR command channel actually responding on the target hardware. As of 2026-06-20 the channel is silent (`openCustomView` → `callback_missing` / `rawNotify=none`; `installApp` → failed) even with BLE connected and authorized, so Phase 0 starts from "core channel failing", not "almost done". Do not start Phases 1/3/4 as glasses-native until Phase 0 returns GO.

Tasks:

- **First**: confirm or refute the current failure. With EAS build #167 (notify re-subscribe fix, commit `5e3d1ea2`), re-run `openCustomView` on the target device and record whether `rawNotify` becomes non-`none`. If it stays `none`, the silence is below the bridge → assemble the support package and escalate to Rokid per `docs/plans/2026-06-18-rokid-cxrl-auth-debugging-lessons.md` §6.
- Add `RokidCapabilityMatrix` to bridge status.
- Record exact device model, firmware, Hi Rokid version, SDK dependency mode, authorization state, CustomView state.
- Standardize the existing diagnostics into a "copy capability report" action on the Rokid health screen.
- Document Display vs Style fallbacks.
- Add a manual test script:
  - open Hi Rokid;
  - authorize;
  - open CustomView;
  - update CustomView;
  - take photo;
  - start/stop recording;
  - query/open push-up app;
  - receive test event.

Exit gate (a go/no-go decision, not just documentation):

- For each target device, the team can say exactly which capabilities are proven, missing, or unknown.
- **GO**: CustomView and photo (ideally also a transcript source) are proven on at least one target SKU → proceed to Phase 1+.
- **NO-GO / re-scope**: if CustomView is `not_supported`, or the command channel stays silent after the pending fix, downgrade Rokid to the §16 "optional capture adapter" (voice/photo trigger → phone/watch confirmation) and do not start Phases 1, 3, or 4 as glasses-native.

### Phase 1: Food Photo Golden Path

Duration: 2-4 weeks.

Goal: glasses photo creates a confirmed nutrition record.

Tasks:

- Wire `capture_kind=food` visual input into a food draft service.
- Reuse existing food image / diet parser instead of adding a parallel Rokid-only parser.
- Add confirmation card on Mobile.
- Add Watch quick confirm for high-confidence drafts.
- Add errors for no SDK, no authorization, no CustomView, no capture, parser failure.
- Add post-meal agenda action for useful cases only.

Exit gate:

- A real meal can be captured from Rokid, confirmed, and saved as a diet record.
- No failed capture creates a record.

### Phase 2: Rokid Voice Command Layer

Duration: 2-4 weeks.

Goal: common health workflows can start without phone taps.

Tasks:

- Use `docs/specs/active/2026-06-19-rokid-voice-control.md` as the source spec.
- Extend existing command router and client-action tests for:
  - food photo;
  - food voice;
  - start push-up;
  - finish session;
  - agenda query;
  - skip;
  - later;
  - unknown.
- Verify `onRokidTranscript` on real hardware and wire it to `submitRokidVoiceCommand()` where available.
- Add fallback source when Rokid only initiates a phone/watch voice capture.
- Add short spoken/HUD responses.
- Add audit event for every voice command.

Exit gate:

- The user can say "开始俯卧撑" and reach a ready workout session, or get a precise blocker.
- The user can say "拍一下这餐" and get a food draft or precise blocker.

### Phase 3: Push-Up Real-Data Beta

Duration: 4-6 weeks.

Goal: first movement circuit works end-to-end.

Tasks:

- Build and install `life.executor.health.rokid.pushup` on the target device.
- Add test event mode.
- Add event freshness UI and stale-session handling.
- Add monotonic rep validation.
- Save completed session into exercise/workout execution.
- Add deterministic coaching summary:
  - reps;
  - average quality;
  - visibility stability;
  - failed rep count;
  - one next cue.

Exit gate:

- 5 real push-ups produce 5 rep events, finish cleanly, and save a workout execution event.

### Phase 4: Agenda Glance And Safety Gate

Duration: 3-5 weeks.

Goal: glasses show one top action that passed readiness and safety gating.

Tasks:

- Connect `GlanceCard` to the HealthAgenda top action.
- Add readiness snapshot to the card generation path.
- Add Display/Style rendering rules.
- Add accept/later/skip capture.
- Downshift strength actions on red readiness or symptoms.

Exit gate:

- "今天练什么" returns one safe action and produces an execution event when accepted/later/skipped.

### Phase 5: Multi-Exercise Expansion

Duration: 6-10 weeks.

Goal: extend from push-up to a small safe movement library.

Candidate exercises:

- squat;
- plank;
- wall sit;
- hip hinge drill;
- neck/shoulder mobility;
- post-meal walk.

Entry criteria:

- The movement can be verified with available sensors or simple confirmation.
- The guidance can be deterministic and short.
- Safety downshift rules exist.
- The action maps to an existing protocol or agenda item.

### Phase 6: Health Protocol Outcomes

Duration: quarter-level.

Goal: prove Rokid improves behavior completion and outcomes, not just novelty.

Tasks:

- Add weekly outcome review for Rokid-assisted actions.
- Compare completion rate against phone/watch-only actions.
- Track food capture accuracy corrections over time.
- Track push-up adherence and quality trend.
- Feed learnings into `HealthTwin` and `InterventionCycle`.

Exit gate:

- Rokid-assisted flows increase weekly completed high-leverage actions without increasing privacy complaints or false records.

## 10. Implementation Backlog

### Backend

- Add capability audit ingestion endpoint if mobile diagnostics need server persistence.
- Route `VisualInputEvent(capture_kind=food)` to food draft creation.
- Add `source=rokid_glasses` to diet draft/record audit trail.
- Add voice command endpoint or extend ambient audio input with command routing.
- Add tests for user isolation on every Rokid route.
- Add push-up event monotonicity and stale-session checks.
- Add `ExecutionEvent` creation for completed movement sessions.
- Add metrics events for capture, command, confirmation, and push-up session states.

### Mobile

- Add capability matrix UI.
- Add one-tap "copy diagnostics".
- Add food draft confirmation from Rokid visual input.
- Add voice command entry/fallback.
- Add push-up real-session lifecycle labels.
- Add Style non-display fallback copy.
- Add "go to Mac/mobile review" handoff for lab/doc-heavy flows.

### Rokid Android App

- Add developer test event button/gesture.
- Add session ready event.
- Add stale network retry with bounded queue.
- Add local-only mode label.
- Add model/version fields to event payload.
- Add clear privacy text: structured pose only, no raw video upload.

### Mac

- Keep lab/document upload as a first-class conversation input.
- Support pasted images in the dialog.
- Show Rokid-originated drafts in review mode.
- Do not duplicate glasses-specific controls unless needed for diagnostics.

### Watch

- Confirm/later/discard for simple food drafts.
- Confirm/later/skip for agenda actions.
- Show "finish push-up session" only if session is active and fresh.

## 11. Metrics

North star contribution:

- weekly completed high-leverage health actions that passed safety gating and have a verification plan.

Rokid-specific metrics:

| Metric | Target |
|---|---|
| capture-to-draft latency | P50 < 8s, P95 < 20s |
| food draft confirmation rate | >= 70% after setup |
| food draft discard rate | monitored; high discard means parser/capture issue |
| voice command intent success | >= 85% for supported commands |
| unsupported voice command graceful fallback | >= 95% |
| CustomView open success | >= 90% on supported Display device |
| push-up session ready time | P95 < 3s after app launch |
| push-up event freshness | P95 event visible on phone < 1s after backend ingest |
| push-up rep monotonicity errors | < 1% sessions |
| privacy-zone discard rate | monitored by context |
| phantom record count | must be 0 |

## 12. Verification Gates

### Gate A: Device Capability

Required evidence:

- screenshot or copied diagnostics from Rokid health screen;
- exact device model/firmware/app versions;
- status for authorization, CustomView, photo, audio, app launch;
- one successful and one failed-path log.

### Gate B: Food Photo

Required evidence:

- real Rokid capture;
- visual input row;
- food draft row;
- confirmation action;
- diet record row;
- no duplicate write.

### Gate C: Voice Command

Required evidence:

- transcript or command payload;
- intent classification;
- action routed;
- user-facing short response;
- audit event;
- fallback behavior for unknown command.

### Gate D: Push-Up Circuit

Required evidence:

- backend session;
- glasses app launch;
- `session_state=ready`;
- `pose` event;
- 5 monotonic `rep` events;
- finished session;
- saved exercise execution event.

### Gate E: Safety And Privacy

Required evidence:

- no raw push-up video in backend storage;
- user_id scoped reads;
- session token is write-only and hashed server-side;
- medication/supplement/lab writes require confirmation;
- red readiness downshifts strength actions.

## 13. Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| **CXR command channel silent despite BLE connected (current 2026-06-20 state)** | Blocks every glasses-native wedge — `openCustomView`/`installApp` get no callback/notify | Phase 0 go/no-go; pending notify-resubscribe fix (build #167); if unresolved, escalate to Rokid with the §6 support package and re-scope to capture adapter. |
| **Companion app (Rokid AI / Hi Rokid) BLE contention** | iOS allows one central per peripheral → the CXR link/notify can be starved, or may require a specific companion state | Document whether the companion must be running or fully quit; surface companion state in the capability matrix; resolve as a Phase 0 finding. |
| iOS SDK binary/toolchain mismatch | Blocks direct iOS SDK features | Keep bridge opt-in, Android-first for real app path, document exact build mode. |
| Transcript callback not available | Voice control cannot be fully native | Use Mobile/Watch voice fallback and treat Rokid as trigger until callback is proven. **Note: the transcript source is currently unimplemented, not just unproven (see §3.5).** |
| Display and non-display SKU confusion | Broken UX on Style | Capability matrix and fallback rules. |
| Food image estimates are wrong | Bad nutrition record | Draft-first, confidence, confirmation, easy edit, no phantom writes. |
| Push-up camera angle poor | Low rep accuracy | Visibility score, "adjust view" prompt, deterministic quality thresholds. |
| Privacy concern in public/workplace | User trust loss | Explicit trigger, visible feedback, privacy zones, default no raw media retention. |
| Glasses app network drop | Lost session events | Bounded retry queue, stale state, local summary handoff. |
| Over-scoped health claims | Safety and regulatory risk | SafetyGuardian gates, no diagnosis, clinician-review downgrade where applicable. |

## 14. Open Questions

1. Which exact Rokid device SKU is primary for the first beta: Display or Style?
2. Does the target firmware expose stable SDK transcript callbacks, or only audio recording?
3. Can Hi Rokid wake phrase launch third-party Reva actions, or must Reva use push-to-talk / app-level buttons?
4. Can CustomView receive user actions, or is it display-only in the available iOS SDK?
5. What is the most reliable way to install/update the glasses Android push-up app for beta users?
6. Should lab-report image capture from glasses be allowed in v1, or restricted to Mobile/Mac upload for privacy and quality?
7. Which exercise after push-up has the best sensor geometry on Rokid hardware?

## 15. First Four Engineering Tickets

### Ticket 1: Rokid Capability Matrix

Goal: represent proven device capabilities as data.

Files:

- `mobile/modules/rokid-bridge/index.ts`
- `mobile/modules/rokid-bridge/ios/RokidBridgeModule.swift`
- `mobile/modules/rokid-bridge/android/src/main/java/.../RokidBridgeModule.kt`
- `mobile/app/rokid-health.tsx`
- `mobile/modules/rokid-bridge/__tests__/rokidBridge.test.ts`

Done when:

- UI shows Display/Style/unknown, CustomView/photo/audio/transcript/appLaunch states.
- Diagnostics can be copied.
- Tests cover missing native bridge and partial capabilities.

### Ticket 2: Food Photo To Draft

Goal: Rokid food photo creates a diet draft, not just a raw visual input.

Files:

- `backend/app/api/ambient.py`
- `backend/app/services/ambient_wearables.py`
- diet food draft service files
- `mobile/services/rokidAmbient.ts`
- `mobile/app/rokid-health.tsx`
- backend and mobile tests

Done when:

- `capture_kind=food` produces a food draft.
- Mobile can confirm/edit/discard.
- Confirm creates one diet record with `source=rokid_glasses`.

### Ticket 3: Rokid Voice Command Hardware Loop

Goal: support phone-free command initiation.

Files:

- `docs/specs/active/2026-06-19-rokid-voice-control.md`
- backend voice command router / `/ambient/rokid-voice-commands`
- `mobile/services/rokidVoiceControl.ts`
- `mobile/services/rokidAmbient.ts`
- `mobile/app/rokid-health.tsx`
- tests

Done when:

- Supported commands route to food photo, food voice, start push-up, finish, agenda, later, skip.
- Unsupported commands produce a short fallback.
- Every command has an audit event.
- Real hardware transcript or fallback voice capture can trigger the command without navigating the phone UI.

### Ticket 4: Push-Up Hardware Verification

Goal: make "push-up circuit works" objectively verifiable.

Files:

- `apps/rokid-pushup-glasses`
- `mobile/app/rokid-pushup-coach.tsx`
- `mobile/services/rokidPushupSession.ts`
- `backend/app/api/rokid.py`
- `backend/app/services/rokid_pushup.py`
- tests

Done when:

- Glasses app can emit test event.
- Real reps are monotonic.
- Session finish writes an exercise execution event.
- README contains device install and verification checklist.

## 16. Product North Star For Rokid

Rokid is successful only if it makes health actions happen with less friction.

The product test is not "can Reva run on glasses?"

The product test is:

```text
Can the user capture food, start movement, receive one safe cue,
and complete the action without touching the phone,
while Reva still keeps confirmation, safety, privacy, and audit intact?
```

If yes, Rokid becomes a real Health OS execution surface.

If no, it should remain an optional capture adapter rather than a core surface.
