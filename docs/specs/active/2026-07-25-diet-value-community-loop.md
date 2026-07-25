---
title: Diet Value Receipt And Peer Support
status: implementing
date: 2026-07-25
owner: mobile-health-os
---

# Feature Spec: 饮食价值回执与同行支持

## 1. 问题

饮食记录成功后，用户已经能看到营养和下一餐建议，但仍缺少两个关键反馈：

1. 这次记录与自己的减脂目标有什么关系；
2. 是否能把一个经过隐私裁剪的进展主动分享给同行，并获得支持。

本功能不建设泛内容社区，也不把点赞、连续天数或停留时长作为健康结果。

## 2. Requirement Admission

```yaml
RequirementAdmission:
  request: 饮食打卡后提供社区、支持反应、减脂目标距离和实时价值反馈
  classification: new_product_behavior
  first_user_fit: 有明确减脂目标且持续记录饮食和体重的高强度工作者
  core_loop_step: ExecutionEvent -> next LeverageAction -> InterventionCycle review
  first_class_objects:
    - HealthProgram
    - ExecutionEvent
    - LeverageAction
    - InterventionCycle
  target_surface: Mobile primary, Backend source of truth
  source_of_truth: DietRecord + WeightRecord + UserProfile/HealthProgram
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: verified record receipt and user-owned measurements
  claim_hedging: hedged
  verification_window: immediate receipt plus seven-day weight observation window
  success_metric: next-action completion and weekly verified progress review
  added_user_burden: one optional share confirmation
  burden_justification: sharing is never automatic
  non_goals:
    - public leaderboards
    - calorie deficit competitions
    - automatic posting
    - comments or direct messages
    - causal weight attribution to one meal
  smallest_end_to_end_slice: one verified diet write returns goal progress and can be posted to an anonymous peer feed
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

Gate G1: **PASS after reframe**. “点赞社区”被约束为可选同行支持，不参与健康建议排序。

## 3. Product Contract

### 3.1 Value Receipt

`post_record_quality` remains the only post-write value receipt. A verified diet
write may add `goal_progress`:

```json
{
  "goal_type": "weight_loss",
  "current_kg": 73.1,
  "target_kg": 70,
  "remaining_kg": 3.1,
  "baseline_kg": 75,
  "progress_pct": 62,
  "change_7d_kg": -0.2,
  "measured_on": "2026-07-25",
  "freshness": "fresh",
  "status": "active"
}
```

Rules:

- latest owned `WeightRecord` wins over profile cache;
- target comes from an active metabolic `HealthProgram`, then profile fallback;
- missing values are omitted, never guessed;
- progress percentage requires a valid baseline above target;
- a target implying BMI below 18.5 is not promoted and returns
  `status=target_requires_review`;
- one meal is never credited with a weight change;
- stale weight data is labelled, not presented as current.

### 3.2 Peer Post

A peer post is an explicit projection of an owned `DietRecord`.

- user presses “发到同行圈”;
- backend verifies ownership and creates a privacy-minimized snapshot;
- display identity is anonymous in v1;
- weight, diagnosis, medication, location, notes, and original health context are
  excluded;
- original meal photo is excluded in v1;
- supported reactions are `support`, `same_path`, and `learned`;
- no comments, followers, rankings, or direct messages;
- owners can delete their post; authenticated users can report a post.

### 3.3 Incentive Contract

The card may show:

- immediate: record verified and next action;
- process: recorded days in the last seven days;
- outcome: weight goal distance and seven-day observed change.

Reaction counts never affect Agent recommendations, risk decisions, or progress.

## 4. State And Failure Behaviour

```text
diet write verified
  -> value receipt available
  -> private by default
  -> user explicitly publishes
      -> published -> reactions enabled
      -> failed -> keep private receipt, allow retry
```

- A receipt is rendered only after a verified write.
- Community failure never changes the diet record.
- Duplicate publish requests use an idempotency key.
- Duplicate reactions update the existing reaction instead of incrementing twice.

## 5. Surfaces

- Mobile chat: compact goal progress inside `RecordQualityCard`.
- Mobile community: anonymous feed, publish confirmation, support reactions.
- Backend: all ownership, projection, deduplication, moderation and counts.
- Watch/Mac/Web: intentionally unchanged in this slice.

## 6. Acceptance

- Goal progress unit tests cover missing target, stale data, trend, achieved goal,
  invalid low-BMI target, and owner isolation.
- Community API tests cover ownership, idempotent posting, privacy minimization,
  reaction uniqueness, delete, and report.
- Mobile tests cover goal progress rendering, stale state, explicit publish,
  reaction state and failure recovery.
- No health field outside the allowlist appears in peer post responses.
- Existing diet write, correction, share, and duplicate-write tests remain green.

## 7. Changelog

- 2026-07-25: accepted and implementation started.
