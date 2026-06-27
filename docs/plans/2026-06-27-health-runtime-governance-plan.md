# Health Runtime Governance Product Plan

> Status: draft
> Updated: 2026-06-27
> Owner: Reva / Personal Health OS
> Related PRD: `docs/prd/2026-06-27-code-derived-product-prd-and-10m-goal.md`
> Related docs/code: `docs/specs/reva-product-governance-spec.md`, `docs/design-personal-predictive-model.md`, `docs/PRODUCT_ROADMAP.md`, `docs/plans/2026-06-15-smart-bedroom-sleep-environment-devices.md`, `docs/specs/active/2026-06-19-p3-reorder-detection.md`, `docs/specs/active/2026-06-22-p5-reorder-ordering.md`, `backend/app/services/health_trajectory.py`, `backend/app/services/personal_models/`, `backend/app/services/action_ranker.py`, `backend/app/services/agenda_service.py`, `backend/app/services/causal_memory.py`, `backend/app/models/bedroom_environment.py`

## 1. Planning Thesis

本计划把“健康是可观测、可预测、可干预、可治理的运行时系统”落成 Reva 下一阶段产品主线。

核心判断：

- Reva 当前能力已经足够多，下一阶段不是继续增加健康功能，而是把现有 Health Twin、HealthTrajectory、SafetyGuardian、ActionRanker、Agenda、InterventionCycle、CausalMemory 和 personal_models 收束成一个用户每天能理解和执行的治理闭环。
- 预测能力不能成为独立炫技模块。预测必须服务于行动排序、安全边界、复测计划和个人规律沉淀。
- 基因、甲基化、VO2max、生物年龄、血糖、血压等都不能被包装成宿命或确定性抗衰承诺。它们只能作为边界、倾向、代理指标、运行时信号或验证反馈。
- IoT、补剂补货、环境控制和个性化供应链不能绕过治理。它们是低摩擦采集、环境默认和受控执行层，不是独立医疗判断层。

## 2. Requirement Admission

```yaml
RequirementAdmission:
  request: 基于健康运行时治理世界观修改 PRD 并制定新规划
  classification: docs | product_change | planning
  first_user_fit: 35-60 岁高强度工作者, 有代谢/恢复/睡眠/慢病风险和多源健康数据
  core_loop_step: Health Twin -> Health Trajectory -> Safety Gate -> ActionRanker -> Agenda -> Execution -> Outcome Review
  first_class_objects:
    - HealthTwin
    - DomainKnowledgeBase
    - RealtimeHealthSignal
    - HealthTrajectory
    - PersonalPrediction
    - SafetyGuardian
    - LeverageAction
    - HealthAgendaItem
    - InterventionCycle
    - ExecutionEvent
    - CausalMemory
    - IoTActuationIntent
    - SupplyIntent
    - OrganSystemProgram
  target_surface: Backend source of truth, Mobile Today/Agenda/Review, Watch top action, Mac workbench
  source_of_truth: backend objects and services
  safety_level: medical_boundary | privacy_sensitive
  prescription_or_causal_verdict: clinician_review_downgraded
  autonomy_tier: manual_confirm
  evidence_provenance: reviewed knowledge, user data, device signals, clinical anchors, per-user observations
  claim_hedging: hedged
  verification_window: 1 day, 7 days, 4 weeks, 8-12 weeks, retest date
  success_metric: weekly completed safe high-leverage actions with attached verification plan
  added_user_burden: low
  burden_justification: use existing data and current daily loop; ask only for data that changes decisions
  non_goals:
    - fine-tune personal LLM on health facts
    - deterministic gene destiny claims
    - autonomous clinical or medication changes
    - new standalone prediction dashboard
    - more specialist pages without execution or review
    - LLM-only IoT control
    - silent supplement purchase or recurring order
    - personalized supplement manufacturing without regulatory, quality and safety review
  smallest_end_to_end_slice: Today top action shows target state variable, trajectory reason, safety boundary, execution control, and verification signal
  stale_surface_to_remove_or_archive: duplicate Web/Mobile daily prediction pages not tied to Agenda or Review
  spec_required: yes
```

## 3. Product Architecture Target

```text
Static priors
  genes / age / sex / family history / medical history

Professional knowledge
  diet / sleep / exercise / supplements / medication / chronic conditions / organ systems / safety rules

Runtime inputs
  sleep / diet / exercise / stress / medication / supplements / weather / calendar / social constraints

Sensors
  labs / wearables / CGM / symptoms / imaging / retests / user feedback / home devices / office devices

State model
  Health Twin

Trajectory model
  baseline deviation / trend / risk drift / forecast with uncertainty / data gaps

Safety boundary
  SafetyGuardian / evidence boundary / clinician escalation

LLM and tool synthesis
  explanation / question asking / tool use / plan drafting / object creation

Control input and actuation
  Agenda top action / protocol / write intent / environment default / IoT scene / supply intent / passive capture

Feedback
  ExecutionEvent / OutcomeReview / CausalMemory / prediction backtest
```

## 4. Phase 0: PRD And Product Language Alignment

Timebox: now to 1 week.

Goal: make the team and future agents use the same product language.

Work:

- Treat `docs/prd/2026-06-27-code-derived-product-prd-and-10m-goal.md` as the current code-derived baseline PRD.
- Adopt “Health Runtime Governance” as product thesis, but keep public language medically conservative.
- Standardize three user-facing concepts:
  - Health Twin: what is true now.
  - Health Trajectory: where the state may drift.
  - Health Action: what safe control input we choose next.
- Add governance rule: every prediction must name horizon, uncertainty, evidence tier, claim boundary, and the action/review it affects.
- Stop introducing standalone prediction views unless they feed Agenda, InterventionCycle, or Review.
- Treat the five system layers as the architecture vocabulary: verified personal data, reviewed knowledge, realtime monitoring, model/tool synthesis, controlled IoT/environment execution.

Acceptance:

- New product specs can fill `state_variable_to_change` and `prediction_or_trajectory_claim`.
- Future docs avoid “destiny”, “guaranteed anti-aging”, “gene determines outcome”, and absolute causal claims.
- PRD explicitly maps HealthTrajectory and PersonalPrediction to first-class product objects.
- PRD explicitly maps IoT/environment and supply-chain actions to controlled execution objects, not autonomous health judgment.

## 5. Phase 1: Make Trajectory Influence Today

Timebox: 1-4 weeks.

Goal: turn trajectory from a workbench/report concept into daily action selection.

Backend work to plan next:

- Audit `backend/app/services/health_trajectory.py` output fields and align them with Agenda item fields.
- Add a product contract for trajectory risk:
  - `domain`
  - `state_variable`
  - `level`
  - `horizon`
  - `signals`
  - `modifiable_levers`
  - `confidence`
  - `uncertainty`
  - `evidence_tier`
  - `claim_boundary`
  - `primary_action`
  - `verification_window`
- Make ActionRanker consume trajectory risk as a scoring input, not a parallel recommendation source.
- Ensure low-confidence trajectory risks become data-gap or watchlist items rather than urgent actions.

Mobile/Watch work to plan next:

- Today top action shows:
  - target state variable;
  - why this trajectory matters now;
  - safety boundary;
  - exact action;
  - expected verification signal.
- Watch summary keeps this compressed into one sentence plus confirm/later/skip.

Acceptance:

- A metabolic/recovery top action can explain which future drift it is trying to change.
- The same item can be completed from Mobile or Watch through the Agenda contract.
- No new daily route is required.

## 6. Phase 2: Make Prediction Backtesting Visible

Timebox: 1-2 months.

Goal: make trust compound visibly through “prediction vs actual”.

Work:

- Define a prediction record shape that can be attached to InterventionCycle, HealthAgendaItem, Specialist output, or HealthProblem follow-up.
- Store:
  - predicted direction or range;
  - horizon;
  - baseline;
  - expected signal;
  - actual result;
  - met / not_met / inconclusive;
  - confidence change after observation.
- Surface prediction backtests in Review, not as a vanity score.
- Keep wording observational:
  - allowed: “这次观察支持继续当前策略。”
  - allowed: “数据不足，不能判断。”
  - disallowed: “这证明某补剂让你降低 LDL。”

Acceptance:

- User can see at least one completed loop: prediction, action, actual, interpretation, next step.
- Specialist hit-rate or prediction confidence is visible to system maintainers.
- Low-confidence or confounded metrics are downgraded to clinician_review or inconclusive.

## 7. Phase 3: Personal Prediction Models Without Personal LLM Fine-Tuning

Timebox: 2-4 months, after enough closed-loop data exists.

Goal: introduce small, auditable prediction models only where data supports them.

Priority order:

1. Personal baseline and anomaly detection from wearable/lab time series.
2. N-of-1 intervention effect estimate after enough InterventionCycle data.
3. CGM + meal response only after paired CGM and diet records exist.

Rules:

- Do not fine-tune an LLM on personal health facts.
- Keep personal model parameters server-side and user-scoped.
- Feed LLM only summary predictions, uncertainty and boundaries.
- Each model must fail gracefully to baseline, data gap or human review.
- Every model output must have tests around confidence, boundary text and unsafe escalation.

Acceptance:

- `personal_models` produces at least one model output with uncertainty and version.
- Twin or trajectory includes the prediction in a structured section.
- ActionRanker can use the output without relying on LLM-only reasoning.

## 8. Phase 4: Scale Governance For 10M Users

Timebox: starts after dogfood and paid wedge prove retention and outcome signal.

Goal: make health runtime governance safe, cheap and trustworthy at large scale.

Work:

- Track cost and latency per Today/Agenda/Trajectory call.
- Add safety event dashboards for trajectory-driven actions.
- Add audit logs for prediction inputs and decisions.
- Add per-user data source quality and source preference.
- Add user controls for pausing prediction categories and deleting derived memory.
- Add multi-region privacy, deletion and export paths before broad consumer rollout.

Acceptance:

- The system can explain why a trajectory action was shown to a user.
- The user can correct, pause or delete derived predictions/memories.
- Operators can audit prediction-driven actions without seeing unnecessary raw sensitive data.

## 9. Phase 5: IoT, Environment And Supply Chain Execution

Timebox: after Today/Trajectory and Review loops are stable; narrow pilots can start earlier for bedroom environment.

Goal: turn Reva from “suggesting behavior” into a governed execution layer that changes the user's physical and logistical environment.

Priority order:

1. Bedroom sleep environment: CO2, PM2.5, humidity, temperature, lights, curtains, sleep protection window.
2. Measurement devices: smart blood pressure cuff, smart scale, CGM and other ground-truth capture devices.
3. Low-risk adherence devices: smart water cup, pill box observations, desk posture/screen break observations.
4. Supplement inventory and replenishment: logistics reminder first, manual purchase later, no silent recurring order.
5. Personalized supplement pairing or manufacturing: long-term only, after reviewed knowledge, DDI/DSI/PGx safety, quality control, regulatory review and audit model exist.

Rules:

- Reva emits health intents and scenes; Home Assistant, manufacturer apps or device ecosystems execute real-time control.
- LLM must not directly control devices.
- Device observations are structured scalar facts; no raw image/audio/video persistence unless a separate privacy spec authorizes it.
- Every actuation path has manual override, audit, downgrade behavior and notification budget.
- Financial actions and supplement supply-chain actions are `manual_confirm` by default; clinical, prescription and dose-changing actions remain manual forever.
- IoT data must not enter generic LLM context unless privacy classification and minimization rules allow it.

Acceptance:

- A bedroom environment loop can show sensor state, executed scene, next morning sleep/recovery outcome and manual override history.
- A supplement low-stock loop can propose a replenishment intent without medicalizing the purchase.
- A device observation can complete or inform an Agenda item without creating an independent recommendation path.

## 10. Organ And System Program Map

Goal: organize health improvement around body systems without losing whole-person interactions.

Initial domains:

- Cardiovascular: blood pressure, resting HR, HRV, VO2max, lipids, activity.
- Metabolic/endocrine: weight, waist, HbA1c, CGM, triglycerides, liver fat risk, meal timing.
- Sleep/recovery: sleep duration, sleep quality, HRV, training readiness, bedroom environment.
- Respiratory/allergy: SpO2, rhinitis, AQI, humidity, pollen, nasal wash, medication adherence.
- Digestive/liver: gastritis, PPI safety, liver enzymes, alcohol, meal composition, medication/supplement interactions.
- Musculoskeletal: strength, mobility, sarcopenia prevention, injury recovery, posture and workstation.
- Neurocognitive/mental: stress, screen load, sleep, social connection, mood and cognitive burden.
- Immune/inflammation and oral health: infection signals, periodontal care, inflammatory markers where available.

Rules:

- Each domain program must still map to global HealthTwin, SafetyGuardian, Agenda and InterventionCycle.
- No organ-level optimization can override cross-system contraindications.
- Domain programs must define writable variables, not only outcome metrics.

## 11. Immediate Next Implementation Plan

The next implementation spec should be small:

> Build the smallest end-to-end “trajectory-informed top action” slice.

Proposed scope:

- Backend: adapt existing `health_trajectory.py` output into an Agenda/ActionRanker input contract.
- Mobile: show target state variable and verification signal on the Today top action.
- Watch: preserve one-line action, no new complex UI.
- Review: add one placeholder for later prediction backtest.
- Tests: contract test for trajectory risk shape, ActionRanker scoring test, Agenda item serialization test, Mobile unit test for top action copy.

Out of scope:

- New ML model.
- New prediction dashboard.
- Medication, dose or clinical treatment prediction.
- CGM meal-response model.
- Autonomous write actions.
- IoT device control.
- Supplement ordering or personalized production.

## 12. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-06-27 | Initial plan | Align PRD and roadmap around Health Runtime Governance. |
| 2026-06-27 | Added system substrate, IoT/environment, supply-chain and organ-system planning | Capture expanded system philosophy while preserving safety and execution boundaries. |
