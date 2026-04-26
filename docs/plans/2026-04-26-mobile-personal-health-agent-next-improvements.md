# Mobile Personal Health Agent Next Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move the mobile app from "daily health coach" to a personal health Agent that remembers context, proactively asks for missing evidence, turns advice into measurable interventions, and closes the loop with outcomes.

**Architecture:** Keep the existing Expo Router tab structure and the state -> risk -> action -> evidence -> outcome loop introduced by the prior mobile health coach work. Add a thin mobile Agent layer that normalizes existing backend data (`/action-cards`, `/health-consultations`, `/personal-outcome`, `/notifications`, `/reminders`, `/profile`, `/data-health`, `/safety`) into an agenda, check-ins, and intervention review surfaces. Add backend contracts only where mobile cannot represent Agent memory, intervention verification, or prompt snoozing cleanly.

**Tech Stack:** Expo Router, React Native 0.81, React 19, TanStack Query, TypeScript, existing `expo-image`, existing `Ionicons`, existing design-system components, existing Jest setup. Do not add new mobile dependencies unless a task proves it is not feasible with existing Expo/RN packages; any dependency must be stable, exact-version pinned, and security reviewed.

---

## Product Framing

The personal health Agent should feel less like a dashboard and more like a competent, conservative health operator. It should:

1. Know what it is watching today.
2. Ask for one missing piece of context at the moment it matters.
3. Convert advice into a measurable experiment or intervention.
4. Remember user constraints and preferences.
5. Escalate safely when deterministic rules say the situation is serious.
6. Explain whether an action helped, using actual metrics.

The previous plan added Today Coach, Intervention Cockpit, data prompts, sleep breathing workflow, consultations, outcomes, and query invalidation. This plan builds on that foundation rather than adding more tabs.

## Current Gaps After The Last Commit

- Today Coach identifies one focus, but there is no full "Agent agenda" showing what the Agent is monitoring, waiting for, and scheduled to verify.
- Action cards can be created and completed, but they are still weakly structured. They need baseline, success metric, target, verification window, and next review state.
- Chat can produce insight, but the mobile user still needs a stronger path from message -> proposed action -> editable intervention.
- Data prompts exist, but there is no snooze/resolve memory. Dismissal is session-local and not Agent-aware.
- Consultations can verify predictions, but the verification UX is still isolated from Actions and Today Coach.
- Mobile does not expose a clear Agent memory/preferences surface. Profile, medications, constraints, goals, and "do not suggest" rules are scattered.
- Safety alerts exist, but escalation UX should be more operational: what to do now, what to monitor, and what to tell a clinician.

## Recommended Delivery Order

P0 should improve Agent coherence without new native dependencies:

1. Task 1: Add Agent Agenda model and home section.
2. Task 2: Add structured intervention draft flow from chat and sleep/actions.
3. Task 3: Add persistent prompt snooze/resolve state.

P1 should deepen health-agent behavior:

1. Task 4: Add Agent Memory and Preferences surface.
2. Task 5: Unify prediction verification with ActionCard outcome review.
3. Task 6: Add Safety Escalation Mode.

P2 should improve convenience and proactivity:

1. Task 7: Add quick check-in command palette.
2. Task 8: Add mobile notification deep-link handling into exact Agent tasks.
3. Task 9: Add weekly Agent review narrative on mobile.

---

### Task 1: Add Agent Agenda Model And Home Section

**Files:**
- Create: `mobile/services/agentAgenda.ts`
- Create: `mobile/hooks/useAgentAgenda.ts`
- Create: `mobile/components/dashboard/AgentAgendaPanel.tsx`
- Modify: `mobile/app/(tabs)/index.tsx`
- Modify: `mobile/lib/queryKeys.ts`
- Test: `mobile/services/__tests__/agentAgenda.test.ts`

**Step 1: Write the failing service test**

Create `mobile/services/__tests__/agentAgenda.test.ts`.

```ts
jest.mock('../todayCoach', () => ({ getTodayCoachFocus: jest.fn() }));
jest.mock('../actionCards', () => ({ getActiveCards: jest.fn() }));
jest.mock('../consultations', () => ({ listConsultations: jest.fn() }));
jest.mock('../dataHealth', () => ({ fetchDataHealthStatus: jest.fn(), buildDataPrompts: jest.fn() }));

import { getActiveCards } from '../actionCards';
import { listConsultations } from '../consultations';
import { buildDataPrompts, fetchDataHealthStatus } from '../dataHealth';
import { getTodayCoachFocus } from '../todayCoach';
import { getAgentAgenda } from '../agentAgenda';

describe('getAgentAgenda', () => {
  beforeEach(() => jest.clearAllMocks());

  it('summarizes focus, active interventions, pending verifications, and missing data', async () => {
    (getTodayCoachFocus as jest.Mock).mockResolvedValue({
      status: 'attention',
      title: '今晚提前晚餐',
      reason: '正在执行睡眠实验',
      actionLabel: '查看行动',
      evidence: [],
    });
    (getActiveCards as jest.Mock).mockResolvedValue([
      { id: 1, title: '提前晚餐', status: 'active', expires_at: null },
      { id: 2, title: '侧睡实验', status: 'active', expires_at: '2026-04-28T00:00:00Z' },
    ]);
    (listConsultations as jest.Mock).mockResolvedValue([
      { id: 9, title: '鼻炎复盘', status: 'active', pending_count: 1, verification_scheduled_at: '2026-04-29' },
    ]);
    (fetchDataHealthStatus as jest.Mock).mockResolvedValue({ diet: { status: 'warning', message: '缺饮食' } });
    (buildDataPrompts as jest.Mock).mockReturnValue([{ key: 'diet', severity: 'useful', title: '记录饮食', body: '缺饮食', route: '/diet' }]);

    const agenda = await getAgentAgenda('2026-04-26');

    expect(agenda.focus.title).toBe('今晚提前晚餐');
    expect(agenda.sections.map(s => s.key)).toEqual(['watching', 'waiting', 'missing_data']);
    expect(agenda.sections.find(s => s.key === 'waiting')?.items[0].route).toBe('/(tabs)/alerts');
  });
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd mobile
npm test -- agentAgenda
```

Expected: FAIL because `mobile/services/agentAgenda.ts` does not exist.

**Step 3: Implement the service**

Create `mobile/services/agentAgenda.ts`.

```ts
import { getActiveCards } from './actionCards';
import { listConsultations } from './consultations';
import { buildDataPrompts, fetchDataHealthStatus } from './dataHealth';
import { getTodayCoachFocus, type TodayCoachFocus } from './todayCoach';

export interface AgentAgendaItem {
  id: string;
  title: string;
  subtitle?: string;
  route?: string;
  tone?: 'default' | 'good' | 'warn' | 'bad';
}

export interface AgentAgendaSection {
  key: 'watching' | 'waiting' | 'missing_data';
  title: string;
  items: AgentAgendaItem[];
}

export interface AgentAgenda {
  date: string;
  focus: TodayCoachFocus;
  sections: AgentAgendaSection[];
}

export async function getAgentAgenda(today: string): Promise<AgentAgenda> {
  const [focus, cards, consultations, dataHealth] = await Promise.all([
    getTodayCoachFocus(today),
    getActiveCards().catch(() => []),
    listConsultations(10).catch(() => []),
    fetchDataHealthStatus().catch(() => null),
  ]);

  const watching = cards
    .filter(card => !card.expires_at && !card.latest_assessment)
    .slice(0, 3)
    .map(card => ({
      id: `card-${card.id}`,
      title: card.title,
      subtitle: '正在执行',
      route: '/(tabs)/alerts',
    }));

  const waiting = [
    ...cards
      .filter(card => card.expires_at || card.latest_assessment)
      .slice(0, 3)
      .map(card => ({
        id: `verify-card-${card.id}`,
        title: card.title,
        subtitle: card.expires_at ? `验证 ${card.expires_at.slice(0, 10)}` : '已有评估',
        route: '/(tabs)/alerts',
        tone: 'warn' as const,
      })),
    ...consultations
      .filter(item => item.pending_count > 0 || item.verification_scheduled_at)
      .slice(0, 2)
      .map(item => ({
        id: `consult-${item.id}`,
        title: item.title,
        subtitle: item.verification_scheduled_at ? `预测复盘 ${item.verification_scheduled_at.slice(0, 10)}` : `${item.pending_count} 条待确认`,
        route: `/consultations/${item.id}`,
        tone: 'warn' as const,
      })),
  ];

  const missingData = buildDataPrompts(dataHealth)
    .slice(0, 3)
    .map(prompt => ({
      id: `data-${prompt.key}`,
      title: prompt.title,
      subtitle: prompt.body,
      route: prompt.route,
      tone: prompt.severity === 'blocking' ? 'bad' as const : 'warn' as const,
    }));

  return {
    date: today,
    focus,
    sections: [
      { key: 'watching', title: 'Agent 正在观察', items: watching },
      { key: 'waiting', title: '等待验证', items: waiting },
      { key: 'missing_data', title: '需要补证据', items: missingData },
    ].filter(section => section.items.length > 0),
  };
}
```

**Step 4: Add hook and query key**

Modify `mobile/lib/queryKeys.ts`.

```ts
agentAgendaRoot: ['agentAgenda'] as const,
```

Create `mobile/hooks/useAgentAgenda.ts`.

```ts
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { getAgentAgenda } from '@/services/agentAgenda';

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function useAgentAgenda() {
  const date = today();
  return useQuery({
    queryKey: [...queryKeys.agentAgendaRoot, date],
    queryFn: () => getAgentAgenda(date),
    staleTime: 120_000,
  });
}
```

Also add `queryKeys.agentAgendaRoot` to health snapshot invalidation.

**Step 5: Build panel**

Create `mobile/components/dashboard/AgentAgendaPanel.tsx`.

Requirements:
- Use `Pressable`, `Ionicons`, `StyleSheet.create`.
- Show at most three sections.
- Each row has stable height, title, optional subtitle, and route affordance.
- Do not introduce another oversized card under Today Coach; make this compact.

**Step 6: Insert into Home**

Modify `mobile/app/(tabs)/index.tsx`.

Place `AgentAgendaPanel` below `TodayCoachPanel` and above critical alert banner. It should navigate to row routes using `router.push(route as any)`.

**Step 7: Verify**

Run:

```bash
cd mobile
npm test -- agentAgenda todayCoach
npx tsc --noEmit
npm run lint
```

Expected: tests pass, TypeScript passes, lint has no new errors.

**Step 8: Commit**

```bash
git add mobile/services/agentAgenda.ts mobile/hooks/useAgentAgenda.ts mobile/components/dashboard/AgentAgendaPanel.tsx mobile/app/\(tabs\)/index.tsx mobile/lib/queryKeys.ts mobile/services/__tests__/agentAgenda.test.ts
git commit -m "feat(mobile): add agent agenda panel"
```

---

### Task 2: Add Structured Intervention Draft Flow

**Files:**
- Modify: `mobile/services/actionCards.ts`
- Create: `mobile/services/interventionDraft.ts`
- Create: `mobile/components/actions/InterventionDraftSheet.tsx`
- Modify: `mobile/components/chat/ChatBubble.tsx`
- Modify: `mobile/app/sleep-spo2-analysis.tsx`
- Test: `mobile/services/__tests__/interventionDraft.test.ts`

**Step 1: Write failing tests**

Create `mobile/services/__tests__/interventionDraft.test.ts`.

```ts
import { buildInterventionDraft, normalizeInterventionDraft } from '../interventionDraft';

describe('interventionDraft', () => {
  it('builds a measurable intervention draft from plain advice', () => {
    const draft = buildInterventionDraft({
      title: '提前晚餐',
      sourceType: 'chat',
      sourceId: 'msg-1',
      advice: '未来7天把晚餐提前到19:00前',
      metricHint: 'sleep_score',
    });

    expect(draft).toMatchObject({
      title: '提前晚餐',
      source_type: 'chat',
      source_id: 'msg-1',
      metric_key: 'sleep_score',
      verification_days: 7,
    });
    expect(draft.checklist.length).toBeGreaterThan(0);
  });

  it('normalizes empty optional fields before submission', () => {
    const input = buildInterventionDraft({ title: '侧睡', advice: '今晚侧睡', sourceType: 'sleep_spo2' });
    const payload = normalizeInterventionDraft({ ...input, target_value: '' });

    expect(payload.target_value).toBeUndefined();
    expect(payload.card_type).toBe('plan');
  });
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd mobile
npm test -- interventionDraft
```

Expected: FAIL because service does not exist.

**Step 3: Implement draft service**

Create `mobile/services/interventionDraft.ts`.

Core model:

```ts
export interface InterventionDraft {
  title: string;
  content: string;
  card_type: 'plan';
  source_type?: string;
  source_id?: string | null;
  priority: number;
  metric_key?: 'sleep_score' | 'hrv' | 'rhr' | 'weight' | 'bp' | 'spo2_odi' | 'custom';
  baseline_value?: string;
  target_value?: string;
  verification_days: number;
  checklist: { item: string; done: boolean }[];
}
```

The initial backend may ignore unknown fields. Keep the draft service separate so future backend schema support can be added without rewriting the UI.

**Step 4: Add create wrapper**

Modify `mobile/services/actionCards.ts`.

Add:

```ts
export async function createInterventionDraft(draft: InterventionDraft): Promise<ActionCard> {
  return createActionCard(normalizeInterventionDraft(draft));
}
```

Import the types carefully to avoid circular runtime imports; use `import type`.

**Step 5: Build draft sheet**

Create `mobile/components/actions/InterventionDraftSheet.tsx`.

Requirements:
- Use `Modal`, `Pressable`, `TextInput`.
- Editable fields: title, success metric, baseline, target, verification days, checklist preview.
- Primary command: `加入行动`.
- Secondary command: cancel.
- No new dependency.

**Step 6: Add chat entry point**

Modify `mobile/components/chat/ChatBubble.tsx`.

For AI messages only, add a compact `加入行动` button below non-empty AI content. It opens the sheet with draft built from message content. Do not show this for card-rendered messages or user messages.

**Step 7: Replace sleep experiment direct creation**

Modify `mobile/app/sleep-spo2-analysis.tsx`.

Instead of immediately creating an ActionCard when tapping `今晚尝试`, open the draft sheet prefilled with:
- `source_type = sleep_spo2`
- `source_id = selectedDate`
- `metric_key = spo2_odi`
- `verification_days = 1`

**Step 8: Verify**

Run:

```bash
cd mobile
npm test -- interventionDraft actionCards sleepSpo2
npx tsc --noEmit
npm run lint
```

Expected: all pass, no new lint errors.

**Step 9: Commit**

```bash
git add mobile
git commit -m "feat(mobile): add intervention draft flow"
```

---

### Task 3: Persist Data Prompt Snooze And Resolve State

**Files:**
- Modify: `mobile/services/dataHealth.ts`
- Create: `mobile/hooks/usePromptSnooze.ts`
- Modify: `mobile/components/data-health/DataPromptCard.tsx`
- Modify: `mobile/app/(tabs)/record.tsx`
- Modify: `mobile/app/sleep-spo2-analysis.tsx`
- Test: `mobile/services/__tests__/dataHealth.test.ts`
- Test: `mobile/hooks/__tests__/usePromptSnooze.test.ts`

**Step 1: Add service tests**

Extend `mobile/services/__tests__/dataHealth.test.ts`.

```ts
import { filterSnoozedPrompts } from '../dataHealth';

it('filters prompts snoozed until a future timestamp', () => {
  const prompts = [{ key: 'diet', severity: 'useful', title: '记录饮食', body: '缺饮食' }];
  const filtered = filterSnoozedPrompts(prompts as any, { diet: '2026-04-27T00:00:00.000Z' }, new Date('2026-04-26T10:00:00.000Z'));

  expect(filtered).toEqual([]);
});

it('keeps prompts after snooze expires', () => {
  const prompts = [{ key: 'diet', severity: 'useful', title: '记录饮食', body: '缺饮食' }];
  const filtered = filterSnoozedPrompts(prompts as any, { diet: '2026-04-25T00:00:00.000Z' }, new Date('2026-04-26T10:00:00.000Z'));

  expect(filtered).toHaveLength(1);
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd mobile
npm test -- dataHealth
```

Expected: FAIL because `filterSnoozedPrompts` is missing.

**Step 3: Implement pure helper**

Modify `mobile/services/dataHealth.ts`.

```ts
export type PromptSnoozeMap = Record<string, string>;

export function filterSnoozedPrompts(
  prompts: DataPrompt[],
  snoozedUntil: PromptSnoozeMap,
  now = new Date(),
): DataPrompt[] {
  return prompts.filter(prompt => {
    const until = snoozedUntil[prompt.key];
    return !until || new Date(until).getTime() <= now.getTime();
  });
}
```

**Step 4: Add hook**

Create `mobile/hooks/usePromptSnooze.ts`.

Use `@react-native-async-storage/async-storage`, already installed.

API:

```ts
export function usePromptSnooze(scope: 'record' | 'sleep') {
  return { snoozedUntil, snoozeForToday, clearSnooze, isLoaded };
}
```

Store key: `healthpilot.promptSnooze.${scope}`.

**Step 5: Add hook tests**

Create `mobile/hooks/__tests__/usePromptSnooze.test.ts`.

Mock AsyncStorage and verify:
- initial load reads stored map
- `snoozeForToday('diet')` writes an ISO timestamp in the future
- `clearSnooze('diet')` removes one key

**Step 6: Update prompt card actions**

Modify `mobile/components/data-health/DataPromptCard.tsx`.

Replace single dismiss `X` with two compact commands:
- `今天忽略`
- `已处理`

Keep visual weight below safety alerts.

**Step 7: Wire Record and Sleep**

Modify `mobile/app/(tabs)/record.tsx` and `mobile/app/sleep-spo2-analysis.tsx`.

Use `filterSnoozedPrompts` with `usePromptSnooze`. `已处理` should clear the current prompt and trigger relevant query invalidation where possible.

**Step 8: Verify**

Run:

```bash
cd mobile
npm test -- dataHealth usePromptSnooze
npx tsc --noEmit
npm run lint
```

Expected: tests pass, prompt dismissal persists across app reloads.

**Step 9: Commit**

```bash
git add mobile
git commit -m "feat(mobile): persist data prompt snoozes"
```

---

### Task 4: Add Agent Memory And Preferences Surface

**Files:**
- Create: `mobile/services/agentMemory.ts`
- Create: `mobile/hooks/useAgentMemory.ts`
- Create: `mobile/app/agent-memory.tsx`
- Modify: `mobile/app/settings.tsx`
- Modify: `mobile/app/(tabs)/index.tsx`
- Test: `mobile/services/__tests__/agentMemory.test.ts`

**Step 1: Write failing tests**

Create `mobile/services/__tests__/agentMemory.test.ts`.

Test a mobile-normalized model that can initially be assembled from profile plus local preferences.

```ts
jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn(), patch: jest.fn() },
}));

import api from '../api';
import { getAgentMemory, updateAgentPreference } from '../agentMemory';

const mockGet = api.get as jest.Mock;
const mockPatch = api.patch as jest.Mock;

describe('agentMemory', () => {
  it('loads health constraints and preference fields from profile', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        target_sleep_hours: 7.5,
        usual_sleep_time: '23:00',
        sleep_environment: { room_temp: 22 },
        health_goals: ['改善睡眠'],
      },
    });

    const memory = await getAgentMemory();

    expect(memory.sleep.targetHours).toBe(7.5);
    expect(memory.goals).toContain('改善睡眠');
  });

  it('patches profile preference updates', async () => {
    mockPatch.mockResolvedValueOnce({ data: {} });

    await updateAgentPreference({ usual_sleep_time: '22:45' });

    expect(mockPatch).toHaveBeenCalledWith('/profile/me', { usual_sleep_time: '22:45' });
  });
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd mobile
npm test -- agentMemory
```

Expected: FAIL because service is missing.

**Step 3: Implement service**

Create `mobile/services/agentMemory.ts`.

Normalize:
- goals
- sleep target and usual bedtime
- sleep environment
- location
- dietary constraints if present
- "do not suggest" rules as local-only fallback until backend supports it

Do not log sensitive health data.

**Step 4: Add screen**

Create `mobile/app/agent-memory.tsx`.

Sections:
- `Agent 关注目标`
- `睡眠与作息`
- `饮食/补剂偏好`
- `不要建议`
- `数据来源`

Use editable compact rows, not a long form.

**Step 5: Link from Settings and Home**

Modify `mobile/app/settings.tsx` with a settings row "Agent 记忆".

Modify `mobile/app/(tabs)/index.tsx` so Today Coach/Agent Agenda can include a small settings icon that routes to `/agent-memory`.

**Step 6: Verify**

Run:

```bash
cd mobile
npm test -- agentMemory
npx tsc --noEmit
npm run lint
```

Expected: profile-backed Agent memory loads and updates.

**Step 7: Commit**

```bash
git add mobile
git commit -m "feat(mobile): add agent memory preferences"
```

---

### Task 5: Unify Prediction Verification With Action Outcomes

**Files:**
- Modify: `mobile/services/actionCards.ts`
- Modify: `mobile/services/consultations.ts`
- Create: `mobile/services/outcomeReview.ts`
- Create: `mobile/components/actions/OutcomeVerificationSheet.tsx`
- Modify: `mobile/components/actions/InterventionCard.tsx`
- Modify: `mobile/app/consultations/[id].tsx`
- Test: `mobile/services/__tests__/outcomeReview.test.ts`

**Step 1: Write failing test**

Create `mobile/services/__tests__/outcomeReview.test.ts`.

```ts
import { buildOutcomeReviewDraft } from '../outcomeReview';

describe('outcomeReview', () => {
  it('creates a review draft from a consultation prediction suggestion', () => {
    const draft = buildOutcomeReviewDraft({
      item_id: 7,
      item_code: 'P1',
      title: 'HRV 提升',
      actual_value: 48,
      suggested_status: 'met',
      target: '>=45',
      note: 'garmin_data.hrv 均值',
    });

    expect(draft.status).toBe('met');
    expect(draft.actualValue).toBe('48');
    expect(draft.summary).toContain('HRV 提升');
  });
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd mobile
npm test -- outcomeReview
```

Expected: FAIL because service is missing.

**Step 3: Implement outcome review draft**

Create `mobile/services/outcomeReview.ts`.

Keep it pure and backend-agnostic:
- input from ActionCard latest assessment or consultation prediction suggestion
- output common review draft with `status`, `actualValue`, `summary`, `evidence`

**Step 4: Add verification sheet**

Create `mobile/components/actions/OutcomeVerificationSheet.tsx`.

Fields:
- suggested status segmented control: met / not_met / inconclusive / pending
- actual value
- summary
- evidence notes
- confirm button

**Step 5: Use sheet from Action Cards**

Modify `mobile/components/actions/InterventionCard.tsx`.

When a card has `latest_assessment` or `expires_at`, primary command should be `复盘结果`, opening `OutcomeVerificationSheet`.

**Step 6: Use sheet from consultation predictions**

Modify `mobile/app/consultations/[id].tsx`.

Replace inline "确认写入结果" block with the same `OutcomeVerificationSheet`.

**Step 7: Verify**

Run:

```bash
cd mobile
npm test -- outcomeReview actionCards consultations
npx tsc --noEmit
npm run lint
```

Expected: action and consultation verification share one UX and degrade when no actual data exists.

**Step 8: Commit**

```bash
git add mobile
git commit -m "feat(mobile): unify outcome verification"
```

---

### Task 6: Add Safety Escalation Mode

**Files:**
- Modify: `mobile/services/safety.ts`
- Create: `mobile/components/safety/SafetyEscalationCard.tsx`
- Create: `mobile/app/safety-escalation.tsx`
- Modify: `mobile/app/(tabs)/alerts.tsx`
- Modify: `mobile/app/(tabs)/index.tsx`
- Test: `mobile/services/__tests__/safety.test.ts`

**Step 1: Write failing service test**

Create `mobile/services/__tests__/safety.test.ts`.

```ts
import { buildSafetyEscalation } from '../safety';

describe('buildSafetyEscalation', () => {
  it('builds immediate steps for critical alerts', () => {
    const escalation = buildSafetyEscalation({
      rule_id: 'spo2_low',
      severity: 'critical',
      category: 'vitals',
      title: '夜间血氧过低',
      message: '最低血氧低于阈值',
      action: '联系医生',
    });

    expect(escalation.level).toBe('urgent');
    expect(escalation.steps[0]).toContain('停止');
    expect(escalation.clinicianSummary).toContain('夜间血氧过低');
  });
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd mobile
npm test -- safety
```

Expected: FAIL because helper is missing.

**Step 3: Implement deterministic helper**

Modify `mobile/services/safety.ts`.

Do not use LLM. Build from alert severity:
- critical -> urgent
- high -> same_day
- medium -> monitor
- low/info -> informational

Return:
- level
- immediate steps
- monitor list
- clinician summary
- route suggestions

**Step 4: Build escalation card**

Create `mobile/components/safety/SafetyEscalationCard.tsx`.

Requirements:
- Large enough for urgent cases, not shown for low/info.
- Buttons: `查看处理步骤`, `复制给医生`, optional `拨打急救电话` only for critical.
- Use `Clipboard` for clinician summary.

**Step 5: Add escalation screen**

Create `mobile/app/safety-escalation.tsx`.

Read route params `rule_id` if supplied, load latest safety report, select matching alert, render deterministic escalation. If missing, show the highest-severity alert.

**Step 6: Wire Home and Alerts**

Modify:
- `mobile/app/(tabs)/index.tsx`: critical banner routes to `/safety-escalation`.
- `mobile/app/(tabs)/alerts.tsx`: critical/high alert expanded state shows `查看处理步骤`.

**Step 7: Verify**

Run:

```bash
cd mobile
npm test -- safety
npx tsc --noEmit
npm run lint
```

Expected: critical alerts have an operational escalation path without relying on generated text.

**Step 8: Commit**

```bash
git add mobile
git commit -m "feat(mobile): add safety escalation mode"
```

---

### Task 7: Add Quick Check-In Command Palette

**Files:**
- Create: `mobile/services/checkInCommands.ts`
- Create: `mobile/components/check-in/CheckInCommandPalette.tsx`
- Modify: `mobile/app/(tabs)/record.tsx`
- Modify: `mobile/app/(tabs)/index.tsx`
- Test: `mobile/services/__tests__/checkInCommands.test.ts`

**Step 1: Write failing test**

Create `mobile/services/__tests__/checkInCommands.test.ts`.

```ts
import { getContextualCheckInCommands } from '../checkInCommands';

describe('checkInCommands', () => {
  it('prioritizes missing data prompts and active interventions', () => {
    const commands = getContextualCheckInCommands({
      prompts: [{ key: 'diet', title: '记录饮食', route: '/diet' } as any],
      activeCards: [{ id: 1, title: '提前晚餐' } as any],
      nowHour: 20,
    });

    expect(commands.map(c => c.key)).toEqual(['diet', 'action-1', 'water', 'sleep-note']);
  });
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd mobile
npm test -- checkInCommands
```

Expected: FAIL because service is missing.

**Step 3: Implement command service**

Create `mobile/services/checkInCommands.ts`.

Return compact commands:
- record diet
- water
- medication
- sleep note
- symptom note
- complete active action
- verify intervention

Make command selection deterministic and testable.

**Step 4: Build palette**

Create `mobile/components/check-in/CheckInCommandPalette.tsx`.

Use bottom modal with icons, labels, and route/action callback. Keep it one-handed and dense.

**Step 5: Wire Home and Record**

Modify:
- `mobile/app/(tabs)/index.tsx`: add small command button near chat input/welcome empty state.
- `mobile/app/(tabs)/record.tsx`: add command palette button near title.

**Step 6: Verify**

Run:

```bash
cd mobile
npm test -- checkInCommands
npx tsc --noEmit
npm run lint
```

Expected: command palette uses no new dependency and routes into existing record flows.

**Step 7: Commit**

```bash
git add mobile
git commit -m "feat(mobile): add quick check-in palette"
```

---

### Task 8: Add Notification Deep Links Into Agent Tasks

**Files:**
- Modify: `mobile/services/notifications.ts`
- Modify: `mobile/hooks/useNotifications.ts`
- Modify: `mobile/app/_layout.tsx`
- Modify: `mobile/app/notification-history.tsx`
- Test: `mobile/services/__tests__/notifications.test.ts`

**Step 1: Write failing service test**

Create or extend `mobile/services/__tests__/notifications.test.ts`.

```ts
import { resolveNotificationDeepLink } from '../notifications';

describe('resolveNotificationDeepLink', () => {
  it('routes action card notifications to Actions tab', () => {
    expect(resolveNotificationDeepLink({ type: 'action_card_followup', action_card_id: 7 })).toBe('/(tabs)/alerts');
  });

  it('routes sleep spo2 notifications to analysis page', () => {
    expect(resolveNotificationDeepLink({ type: 'sleep_spo2', night_date: '2026-04-25' })).toBe('/sleep-spo2-analysis?night_date=2026-04-25');
  });
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd mobile
npm test -- notifications
```

Expected: FAIL because resolver is missing.

**Step 3: Implement resolver**

Modify `mobile/services/notifications.ts`.

Map notification payload types:
- `health_alert` -> `/safety-escalation`
- `action_card_followup` -> `/(tabs)/alerts`
- `sleep_spo2` -> `/sleep-spo2-analysis?night_date=...`
- `consultation_verification` -> `/consultations/{id}`
- `data_health` -> route from prompt key

**Step 4: Wire notification response handler**

Modify `mobile/hooks/useNotifications.ts` and/or `mobile/app/_layout.tsx`.

When user taps a notification, call resolver and route with Expo Router.

**Step 5: Show route affordance in history**

Modify `mobile/app/notification-history.tsx`.

Rows with resolvable links show `打开任务`.

**Step 6: Verify**

Run:

```bash
cd mobile
npm test -- notifications
npx tsc --noEmit
npm run lint
```

Expected: notification taps route to exact Agent task when payload contains enough data.

**Step 7: Commit**

```bash
git add mobile
git commit -m "feat(mobile): route notifications to agent tasks"
```

---

### Task 9: Add Weekly Agent Review Narrative

**Files:**
- Create: `mobile/services/weeklyAgentReview.ts`
- Create: `mobile/hooks/useWeeklyAgentReview.ts`
- Create: `mobile/components/outcome/WeeklyAgentReviewCard.tsx`
- Modify: `mobile/app/consultations.tsx`
- Modify: `mobile/app/(tabs)/index.tsx`
- Test: `mobile/services/__tests__/weeklyAgentReview.test.ts`

**Step 1: Write failing service test**

Create `mobile/services/__tests__/weeklyAgentReview.test.ts`.

```ts
import { buildWeeklyAgentReview } from '../weeklyAgentReview';

describe('weeklyAgentReview', () => {
  it('summarizes actions, outcomes, and next focus', () => {
    const review = buildWeeklyAgentReview({
      completedActions: [{ title: '提前晚餐', latest_assessment: { summary: '睡眠改善' } } as any],
      outcomeMetrics: [{ key: 'sleep_score', label: '睡眠评分', value: '83', delta: '+7', unit: '分', desirable: 'up' }],
      safetyAlerts: [],
    });

    expect(review.sections.map(s => s.title)).toEqual(['本周做了什么', '指标怎么变了', '下周关注']);
  });
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd mobile
npm test -- weeklyAgentReview
```

Expected: FAIL because service is missing.

**Step 3: Implement pure review builder**

Create `mobile/services/weeklyAgentReview.ts`.

Do not call LLM in P0. Build deterministic narrative from:
- completed action cards
- latest assessments
- personal outcome metrics
- safety alerts
- data gaps

**Step 4: Add hook**

Create `mobile/hooks/useWeeklyAgentReview.ts`.

Fetch:
- active/completed action cards if backend supports status filter
- personal outcome timeline
- safety report
- data health

If completed action cards are not available through current mobile service, add `getActionCards(status, limit)` in `mobile/services/actionCards.ts`.

**Step 5: Build card**

Create `mobile/components/outcome/WeeklyAgentReviewCard.tsx`.

Show:
- one sentence summary
- three sections
- command to open consultations/outcomes

**Step 6: Place in Home and Consultations**

Modify:
- `mobile/app/(tabs)/index.tsx`: show compact card only once per week or when there are completed actions.
- `mobile/app/consultations.tsx`: show full review above outcome card.

**Step 7: Verify**

Run:

```bash
cd mobile
npm test -- weeklyAgentReview personalOutcome actionCards
npx tsc --noEmit
npm run lint
```

Expected: weekly review renders without LLM and degrades when outcome history is empty.

**Step 8: Commit**

```bash
git add mobile
git commit -m "feat(mobile): add weekly agent review"
```

---

## Final Verification

After all tasks:

```bash
cd mobile
npm test
npx tsc --noEmit
npm run lint
```

Expected:
- Jest: all suites pass.
- TypeScript: exit 0.
- Lint: exit 0. Existing warnings may remain, but no new errors.

## Non-Goals

- Do not add a new bottom tab.
- Do not add a new mobile dependency in P0.
- Do not let the LLM override deterministic safety escalation.
- Do not ask the user for more than one new data point at a time.
- Do not make every prompt urgent. Agent prompts must be ranked and snoozable.
- Do not build a generic "AI dashboard"; every surface must map to action, evidence, or outcome.

## Success Metrics

- The user can see what the Agent is watching and waiting for within 5 seconds of opening Home.
- At least 80% of health advice shown in chat can become an editable, measurable intervention.
- Data prompts survive app restarts and respect snooze state.
- Safety alerts have deterministic escalation instructions.
- Prediction verification and action outcome review use the same mobile UX.
- Weekly review can explain what changed without relying on a fresh LLM call.
