# Mobile Health Coach Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the mobile app from a data viewer plus chat surface into a daily health coach that tells the user what matters today, what to do next, and whether prior actions worked.

**Architecture:** Keep the current Expo Router tab structure, but change the user journey around a single loop: state -> risk -> action -> evidence -> outcome review. Mobile should consume existing backend capabilities first (`/health-score`, `/safety`, `/action-cards`, `/sleep/spo2`, `/health-consultations`, `/personal-outcome`, `/data-health`) and only add backend contracts where the current API cannot represent an intervention or missing data prompt cleanly.

**Tech Stack:** Expo Router, React Native 0.81, React 19, TanStack Query, TypeScript, existing `Ionicons`, existing design-system components, existing Jest setup. Do not add mobile dependencies in P0 unless the benefit is clear and the dependency is locked to an audited stable version.

---

## Product Principles

The mobile app should answer five questions every day:

1. What is my current state?
2. What is the most important health issue today?
3. What exact action should I take?
4. What evidence supports this recommendation?
5. When will the app verify whether it worked?

The current app already has the ingredients: health score, Garmin data, safety alerts, action cards, sleep SpO2 analysis, consultations, goals, records, notifications, and chat. The next step is to reduce cognitive load and make those systems feel like one assistant.

## Current Mobile Assessment

The current tab structure is good enough and should not be expanded:

- `mobile/app/(tabs)/index.tsx`: chat-first home with metrics header and safety banner.
- `mobile/app/(tabs)/alerts.tsx`: safety alerts and action cards.
- `mobile/app/(tabs)/record.tsx`: dense daily record dashboard.
- `mobile/app/sleep.tsx` and `mobile/app/sleep-spo2-analysis.tsx`: strongest domain-specific health workflow.

The main gaps are product-level:

- Home is chat-centered, but the user's most important daily decision is not always visible without asking.
- Action cards are saved messages, not yet structured health interventions with baseline, due date, metric target, and outcome.
- Data gaps are surfaced as status text, not as actionable prompts placed at the point of decision.
- Sleep breathing analysis is strong, but it is still a separate detail page rather than a recurring intervention workflow.
- Chat generates insight, while the Actions tab tracks action. The transition from "AI said this" to "I am doing this" is still too weak.

## Recommended Approach

Use a four-part mobile architecture:

1. `Today Coach` on the home screen: one primary focus, top evidence, one action, and one verification date.
2. `Intervention Cockpit` in the Actions tab: active interventions, safety alerts, pending verifications, and completed outcomes.
3. `Data Completeness Prompts` in Record and Sleep: the app asks for missing context exactly when that data improves an analysis.
4. `Domain Deep Dives` for sleep, metabolic health, training, and supplements: detailed pages remain available but feed back into Today Coach and Actions.

This avoids a new tab and avoids building another dashboard that competes with existing pages.

---

### Task 1: Add Today Coach Model and Home Panel

**Files:**
- Create: `mobile/services/todayCoach.ts`
- Create: `mobile/hooks/useTodayCoach.ts`
- Create: `mobile/components/dashboard/TodayCoachPanel.tsx`
- Modify: `mobile/app/(tabs)/index.tsx`
- Test: `mobile/services/__tests__/todayCoach.test.ts`

**Step 1: Define the client-side model**

Create `mobile/services/todayCoach.ts` with a small normalized model assembled from existing endpoints. P0 should not require a new backend API.

```ts
import api from './api';
import { getSafetyReport } from './safety';
import { getActiveCards } from './actionCards';

export interface TodayCoachFocus {
  status: 'ok' | 'attention' | 'risk' | 'missing_data';
  title: string;
  reason: string;
  actionLabel: string;
  actionRoute?: string;
  evidence: Array<{ label: string; value: string; tone?: 'good' | 'warn' | 'bad' }>;
  verifyBy?: string;
}

export async function getTodayCoachFocus(today: string): Promise<TodayCoachFocus> {
  const [scoreRes, safety, cards, dataHealth] = await Promise.allSettled([
    api.get(`/health-score/enhanced/me?target_date=${today}`).then(r => r.data),
    getSafetyReport(),
    getActiveCards(),
    api.get('/data-health/status').then(r => r.data),
  ]);

  const score = scoreRes.status === 'fulfilled' ? scoreRes.value : null;
  const alerts = safety.status === 'fulfilled' ? safety.value.alerts || [] : [];
  const activeCards = cards.status === 'fulfilled' ? cards.value || [] : [];
  const health = dataHealth.status === 'fulfilled' ? dataHealth.value : null;

  const highAlert = alerts.find((a: any) => ['critical', 'high'].includes(typeof a.severity === 'string' ? a.severity : a.severity?.label));
  if (highAlert) {
    return {
      status: 'risk',
      title: highAlert.title,
      reason: highAlert.message,
      actionLabel: highAlert.action || '查看处理建议',
      actionRoute: '/(tabs)/alerts',
      evidence: [{ label: '安全告警', value: '高优先', tone: 'bad' }],
    };
  }

  const firstCard = activeCards[0];
  if (firstCard) {
    return {
      status: 'attention',
      title: firstCard.title,
      reason: '你有一个正在执行的健康行动。',
      actionLabel: '查看行动',
      actionRoute: '/(tabs)/alerts',
      evidence: [{ label: '行动卡', value: firstCard.card_type || 'active' }],
    };
  }

  if (health?.garmin?.status !== 'ok') {
    return {
      status: 'missing_data',
      title: '先补齐 Garmin 数据',
      reason: health?.garmin?.message || '关键生理数据不完整，今日判断可信度会下降。',
      actionLabel: '去设置',
      actionRoute: '/settings',
      evidence: [{ label: '数据状态', value: health?.garmin?.status || 'unknown', tone: 'warn' }],
    };
  }

  return {
    status: 'ok',
    title: '今日状态稳定',
    reason: score?.suggestions?.[0] || '暂无高优先级风险，保持记录和执行。',
    actionLabel: '生成今日简报',
    evidence: [{ label: '健康评分', value: String(score?.total_score ?? '--') }],
  };
}
```

**Step 2: Add hook**

Create `mobile/hooks/useTodayCoach.ts`.

```ts
import { useQuery } from '@tanstack/react-query';
import { getTodayCoachFocus } from '@/services/todayCoach';

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function useTodayCoach() {
  const date = today();
  return useQuery({
    queryKey: ['todayCoach', date],
    queryFn: () => getTodayCoachFocus(date),
    staleTime: 120_000,
  });
}
```

**Step 3: Build panel**

Create `mobile/components/dashboard/TodayCoachPanel.tsx`. Use `Pressable` for commands, `Ionicons` for icons, stable row heights, and existing colors. Do not put this inside another card if it is placed directly under `HomeHeader`; make it a first-class home section.

**Step 4: Insert into home**

Modify `mobile/app/(tabs)/index.tsx` to render `TodayCoachPanel` below `HomeHeader` and above the chat list. The panel should call `handleSend('今天健康如何？给我一份简报')` when the focus action is "生成今日简报"; otherwise navigate to `actionRoute`.

**Step 5: Test**

Run:

```bash
cd mobile
npm test -- todayCoach
npm run lint
```

Expected: new service tests pass and lint has no new errors.

---

### Task 2: Upgrade Actions Tab Into Intervention Cockpit

**Files:**
- Modify: `mobile/services/actionCards.ts`
- Modify: `mobile/app/(tabs)/alerts.tsx`
- Create: `mobile/components/actions/InterventionCard.tsx`
- Create: `mobile/components/actions/ActionEvidenceRow.tsx`
- Test: `mobile/services/__tests__/actionCards.test.ts`

**Step 1: Expand `ActionCard` type**

Update the mobile type to include fields already present or planned on the backend:

```ts
export interface ActionCard {
  id: number;
  title: string;
  content: string;
  card_type: string;
  status: string;
  priority: number;
  created_at: string;
  expires_at?: string | null;
  completed_at?: string | null;
  checklist?: Array<{ item: string; done: boolean }>;
  latest_assessment?: {
    score?: number;
    summary?: string;
    evidence?: string[];
    adjustments?: string[];
  } | null;
  source_type?: string;
  source_id?: string | null;
}
```

**Step 2: Replace generic markdown-first card**

Move card rendering out of `alerts.tsx` into `InterventionCard`. Default collapsed view should show:

- title
- type
- due/created date
- verification status if available
- one primary command: complete, review, or continue

Expanded view can still render markdown, but evidence and checklist should appear before the long content.

**Step 3: Add sections**

Keep the existing `SectionList`, but use these sections:

- `需要立即处理`: critical/high safety alerts
- `正在执行`: active action cards
- `等待验证`: cards with `latest_assessment` or `expires_at`
- `日常提示`: low/info alerts

**Step 4: Test**

Run:

```bash
cd mobile
npm test -- actionCards
npm run lint
```

Expected: actions tab renders active cards without crashing when new optional fields are absent.

---

### Task 3: Add Data Completeness Prompts

**Files:**
- Create: `mobile/services/dataHealth.ts`
- Create: `mobile/hooks/useDataHealth.ts`
- Create: `mobile/components/data-health/DataPromptCard.tsx`
- Modify: `mobile/app/(tabs)/record.tsx`
- Modify: `mobile/app/sleep-spo2-analysis.tsx`
- Test: `mobile/services/__tests__/dataHealth.test.ts`

**Step 1: Add service and hook**

Wrap `/data-health/status` in a typed service. Convert backend statuses into prompt objects:

```ts
export interface DataPrompt {
  key: string;
  severity: 'blocking' | 'useful' | 'optional';
  title: string;
  body: string;
  route?: string;
}
```

**Step 2: Place prompts where they matter**

In `record.tsx`, show prompts for missing diet, water, Garmin, genetic data, and notifications near the relevant section. In `sleep-spo2-analysis.tsx`, keep existing `ask_questions`, but replace the generic "去补录" behavior with context-aware destinations such as diet, medication, or sleep note.

**Step 3: Do not over-alert**

Prompts should be dismissible for the session and should not compete visually with critical safety alerts.

**Step 4: Test**

Run:

```bash
cd mobile
npm test -- dataHealth
npm run lint
```

Expected: prompts are generated only when status is warning/error and routes are valid.

---

### Task 4: Make Sleep Breathing the First Complete Deep-Dive Workflow

**Files:**
- Modify: `mobile/app/sleep.tsx`
- Modify: `mobile/app/sleep-spo2-analysis.tsx`
- Modify: `mobile/services/sleepSpo2.ts`
- Create: `mobile/components/sleep/SleepBreathingSummary.tsx`
- Create: `mobile/components/sleep/SleepExperimentCard.tsx`
- Test: `mobile/services/__tests__/sleepSpo2.test.ts`

**Step 1: Add a breathing summary to `sleep.tsx`**

Show latest ODI, min SpO2, event count, and a direct command to open `/sleep-spo2-analysis`. This should be above the generic AI deep analysis block.

**Step 2: Turn action priorities into experiments**

In `sleep-spo2-analysis.tsx`, each `action_priorities` item should have a button:

- `今晚尝试`
- `已完成`
- `不适用`

Initially this can create an ActionCard from the text. Later it should create a structured Intervention.

**Step 3: Prepare for snore events**

Extend `sleepSpo2.ts` types with optional `snore_events` but do not require backend support in P0:

```ts
snore_events?: Array<{
  start_ts: string;
  end_ts: string;
  intensity?: 'low' | 'medium' | 'high';
  confidence?: number;
}>;
```

The chart should ignore missing snore data.

**Step 4: Test**

Run:

```bash
cd mobile
npm test -- sleepSpo2
npm run lint
```

Expected: sleep pages work with and without optional snore event data.

---

### Task 5: Connect Consultations and Outcomes to Mobile

**Files:**
- Modify: `mobile/app/consultations.tsx`
- Modify: `mobile/app/consultations/[id].tsx`
- Create: `mobile/services/personalOutcome.ts`
- Create: `mobile/components/outcome/OutcomeReviewCard.tsx`
- Test: `mobile/services/__tests__/personalOutcome.test.ts`

**Step 1: Surface active consultation status**

Show active hypotheses, actions, predictions, and red flags as separate groups. Do not render them as a long markdown block only.

**Step 2: Add prediction verification UX**

For pending predictions, expose the existing `/health-consultations/me/{id}/verify` action. Show suggested verification result and let the user confirm status.

**Step 3: Add outcome review entry**

Use `/personal-outcome/me/timeline` to show a compact "what changed" card: HRV, resting HR, sleep score, weight, and BP trends.

**Step 4: Test**

Run:

```bash
cd mobile
npm test -- personalOutcome
npm run lint
```

Expected: consultation pages degrade gracefully when there is no active consultation or outcome history.

---

### Task 6: Mobile Performance and Reliability Pass

**Files:**
- Modify: `mobile/app/(tabs)/index.tsx`
- Modify: `mobile/app/(tabs)/alerts.tsx`
- Modify: `mobile/app/(tabs)/record.tsx`
- Modify: `mobile/components/chat/ChatBubble.tsx`
- Modify: `mobile/components/dashboard/TrendMiniCharts.tsx`
- Modify: `mobile/lib/queryClient.ts`
- Test: existing mobile Jest tests

**Step 1: Keep virtualized surfaces virtualized**

Do not replace `FlatList` or `SectionList` with `ScrollView` for feeds. If an action list or chat list becomes large enough to show jank, consider `@shopify/flash-list` only after dependency audit and exact version pinning.

**Step 2: Reduce repeated endpoint calls**

Home currently calls individual queries while Record calls `fetchDashboardData`. Introduce shared query keys and invalidate them consistently after Garmin sync, action completion, or record creation.

**Step 3: Use `expo-image` for remote images**

For chat images and diet images, replace plain `Image` where caching matters. `expo-image` is already installed.

**Step 4: Move inline heavy renderers into components**

Extract large inline render functions from `index.tsx`, `alerts.tsx`, and `record.tsx`. Keep list item components stable and typed.

**Step 5: Test**

Run:

```bash
cd mobile
npm test
npm run lint
```

Expected: all mobile tests pass, no new lint failures, and no large list screen is converted to unvirtualized rendering.

---

## Suggested Delivery Order

P0 should be narrow:

1. Task 1: Today Coach.
2. Task 2: Intervention Cockpit.
3. Task 3: Data Completeness Prompts.

P1 should deepen the highest-value health domain:

1. Task 4: Sleep Breathing workflow.
2. Task 5: Consultations and Outcomes.

P2 should harden the experience:

1. Task 6: Performance and reliability pass.
2. Add mobile analytics for which prompts/actions users actually complete.
3. Add push notification deep links into the exact action or data prompt.

## Success Metrics

- User can open the app and understand the single most important action within 5 seconds.
- At least 80% of AI recommendations shown on mobile can become trackable actions.
- Each active action has a verification date or success criterion.
- Sleep breathing page can explain one night using SpO2, HR, respiration, sleep stage, and optional snore events.
- Record page prompts missing data only when that data changes analysis quality.

## Non-Goals

- Do not add a fourth tab in P0.
- Do not rebuild the visual design system.
- Do not add social, family, or gamification work to this plan.
- Do not make chat the only entry point for structured health decisions.
- Do not add new dependencies unless a specific task cannot be done well with existing Expo/React Native packages.

