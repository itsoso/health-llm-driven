# Feature Spec: Rokid Voice Control

> Status: draft
> Owner: Reva
> Updated: 2026-06-19
> Related PRD/PDD: `docs/plans/2026-06-17-rokid-sdk-integration-plan.md`, `docs/prd/2026-06-19-proactive-planning-prd.md`
> Related code: `backend/app/api/ambient.py`, `mobile/app/rokid-health.tsx`, `mobile/modules/rokid-bridge/index.ts`

## 1. Decision

Build a Rokid voice command layer that lets glasses users trigger food photo capture, push-up sessions, and guided movement without operating the phone screen.

## 2. Problem

Rokid glasses are useful only if Reva can be controlled while the user's hands and attention are occupied. Current Rokid Health Mode can open Hi Rokid, show CustomView, take explicit photos, and run the push-up coach, but the user still has to tap the phone. If we do nothing, food capture, push-ups, and exercise guidance remain phone-first workflows and fail the wearable-first use case.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: "支持跟 Rokid 语音交互, 饮食拍照、俯卧撑、运动指导"
  classification: execution_surface_extension
  first_user_fit: yes
  core_loop_step: execution_surface
  first_class_objects:
    - ExecutionEvent
    - GlanceCard
    - DietRecord
    - ExerciseRecord
  target_surface: Rokid Glasses
  source_of_truth: backend
  safety_level: health_l3
  prescription_or_causal_verdict: no_new_medical_claims
  autonomy_tier: manual_confirm_by_default
  evidence_provenance: user_triggered_voice_command
  claim_hedging: movement guidance uses existing guided-task safety gate
  verification_window: same_session_event_and_followup_confirmation
  success_metric: user can issue one voice command and get a client action without touching the phone
  added_user_burden: low
  burden_justification: explicit push-to-talk or wake session prevents continuous listening
  non_goals:
    - continuous background listening
    - autonomous medication or supplement writes
    - replacing Rokid SDK ASR implementation
  smallest_end_to_end_slice: transcript -> command router -> Rokid client action -> audit AudioInputEvent
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

## 4. Non-Goals

- Do not build a separate Rokid health dashboard.
- Do not claim the native Rokid ASR callback is stable before SDK evidence proves it.
- Do not continuously listen in the background.
- Do not auto-confirm medication, supplement, or diagnosis-related changes.
- Do not duplicate the existing food recognition, push-up session, or guided movement services.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `HealthAgendaItem` | Movement guidance command opens the existing guided-task execution path. |
| `SafetyGuardian` | Movement guidance stays behind existing readiness and guided-task gates. |
| `ExecutionEvent` | P0 persists voice command provenance as `AudioInputEvent`; later slices can add explicit execution events. |
| `WriteIntent` | Food and nontrivial health writes remain manual-confirm by default. |

## 6. User Flow

```text
explicit Rokid voice trigger
  -> transcript reaches mobile bridge
  -> POST /ambient/rokid-voice-commands
  -> backend deterministic command router
  -> mobile executes one client action: capture_food_photo / open_pushup_coach / open_guided_task
  -> backend stores AudioInputEvent with route result
  -> glasses CustomView or TTS returns a short reply
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Rokid Glasses | User-facing capture and short replies | Only explicit push-to-talk or wake-session commands; no continuous recording. |
| Mobile | Invisible bridge | Start/stop Rokid recording, submit transcripts, run client actions, show debug state when needed. |
| Backend | Source of truth | Route transcripts deterministically, persist `AudioInputEvent`, return bounded client actions. |

## 8. Data Contract

```yaml
apis:
  - POST /ambient/rokid-voice-commands
events:
  - audio_input_events.intent = food | movement | note
fields:
  - command.intent
  - command.client_action
  - command.voice_reply
  - command.requires_confirmation
enums:
  - food_photo
  - pushup_start
  - pushup_stop
  - pushup_save
  - exercise_guidance
  - confirm
  - skip
  - later
  - unknown
backward_compatibility: existing /ambient/audio-inputs remains unchanged except movement intent admission
migration: none
```

## 9. Safety, Privacy, And Medical Boundary

The feature touches L3 health behavior data and food images. It must never run continuous background listening. Food writes should remain draft or manual-confirmed when confidence is low. Movement guidance must route through existing readiness and guided-task gates; pain, symptom, or red-flag transcripts should degrade to symptom/safety paths rather than exercise progression.

## 10. AI Behavior

P0 uses deterministic keyword routing. LLM interpretation may be added later only after deterministic safety checks and with a bounded command enum. The client must not execute arbitrary free-form actions returned by an LLM.

## 11. Acceptance Criteria

```gherkin
Given a user says "拍一下这餐"
When the transcript is submitted to the Rokid command endpoint
Then the response asks the mobile bridge to capture a food photo and stores an AudioInputEvent.

Given a user says "开始俯卧撑"
When the transcript is submitted
Then the response asks the mobile bridge to open the push-up coach and stores a movement AudioInputEvent.

Given a user asks "今天练什么"
When the transcript is submitted
Then the response opens the guided movement task instead of inventing a workout.

Given an unsupported command
When the transcript is submitted
Then the response returns a safe clarification action and still stores the event for audit.
```

## 12. Verification Plan

```bash
# Backend
DATABASE_URL=sqlite:///./backend_test.db PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/test_ambient_wearables.py -q

# Mobile
cd mobile && npm test -- --runTestsByPath services/__tests__/rokidAmbient.test.ts app/__tests__/rokid-health.test.tsx --runInBand
cd mobile && npx tsc --noEmit

# Repo hygiene
git diff --check
```

## 13. Rollout And Rollback

Roll out behind the existing Rokid Health Mode entry. Rollback is removing the mobile voice entry point while leaving the backend endpoint harmless and auditable. Native ASR callback work remains isolated to `mobile/modules/rokid-bridge`.

## 14. Open Questions

- Which exact Rokid SDK ASR callback should deliver transcript events on iOS and Android?
- Should the wake phrase be handled by Rokid OS or Reva push-to-talk only in P0?

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-06-19 | Initial draft | Define P0 voice command control plane. |
