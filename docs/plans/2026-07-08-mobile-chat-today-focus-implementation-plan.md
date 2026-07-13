# Mobile Chat Today Focus Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the mobile chat briefing strip with a compact Today Focus surface that shows one primary action, a reason, clear next taps, and deduped secondary status.

**Architecture:** Add a small resolver plus a chat-only presentational component. `ChatScreen` owns data fetching and navigation callbacks; `ChatTodayFocusCard` renders the selected focus action, expandable evidence, and status strip. No fake weather, air quality, summary, or plan data should be shown.

**Tech Stack:** React Native, Expo Router, React Query-backed hooks already used by mobile, Jest with `@testing-library/react-native`, Reva design tokens.

---

## Task 1: Add the Focus Resolver

**Files:**
- Create: `mobile/components/chat/todayFocus.ts`
- Test: `mobile/components/chat/__tests__/todayFocus.test.ts`

**Step 1: Write the failing tests**

Create `mobile/components/chat/__tests__/todayFocus.test.ts`.

Cover these cases:

```ts
import {
  buildTodayFocusModel,
  normalizeTodayFocusKey,
} from '../todayFocus';
import type { TodayDynamicView } from '../../../services/todayDynamicView';
import type { DailyOperatingPlan } from '../../../services/dailyPlan';
import type { TodayTimelineResponse } from '../../../services/todayTimeline';

const dynamicView = (title: string): TodayDynamicView => ({
  view_id: 'v1',
  surface: 'mobile.today',
  trigger: 'open',
  generated_by: 'test',
  context_hash: 'hash',
  sections: [{
    slot: 'primary',
    priority: 10,
    cards: [{
      id: 'card-1',
      type: 'agent_atom',
      render: { atom: 'daily_artifact' },
      data: {
        title,
        summary: '今天优先降低训练负荷。',
        why_now: '睡眠恢复偏弱。',
        next_action: { title, deep_link: '/fitness-plan' },
        evidence: ['睡眠恢复偏弱', 'HRV 低于近期基线'],
        verification: ['今晚睡眠', '主观疲劳'],
      },
    }],
  }],
});

const dailyPlan = (title: string): DailyOperatingPlan => ({
  plan_date: '2026-07-08',
  primary_goal: 'metabolic_health',
  status: 'active',
  state_summary: {},
  actions: [{
    action_key: 'movement.recovery',
    domain: 'movement',
    title,
    why: '训练负荷偏高。',
  }],
});

const timeline = (title: string): TodayTimelineResponse => ({
  date: '2026-07-08',
  current_window: 'afternoon',
  now: 'timeline-1',
  items: [{
    id: 'timeline-1',
    kind: 'action',
    time_window: 'afternoon',
    title,
    subtitle: '现在可以做',
    icon: 'walk-outline',
    color: '#1F8A5B',
    status: 'pending',
    priority: 9,
    can_complete: true,
    complete_ref: null,
    deep_link: '/agenda',
    severity: null,
    proof: null,
  }],
  past: { completed_count: 1, events: [] },
  counts: { actionable: 2, overdue: 0, info: 0 },
});

describe('todayFocus resolver', () => {
  it('prefers dynamic Today primary action over daily plan and timeline', () => {
    const model = buildTodayFocusModel({
      dynamicView: dynamicView('暂停高强度训练'),
      dailyPlan: dailyPlan('补水并轻活动'),
      timeline: timeline('餐后步行 10 分钟'),
    });

    expect(model.primary?.title).toBe('暂停高强度训练');
    expect(model.primary?.source).toBe('dynamic_today');
    expect(model.primary?.deepLink).toBe('/fitness-plan');
  });

  it('falls back to daily plan when dynamic Today has no renderable primary action', () => {
    const model = buildTodayFocusModel({
      dailyPlan: dailyPlan('晨起补水并看今日重点'),
      timeline: timeline('餐后步行 10 分钟'),
    });

    expect(model.primary?.title).toBe('晨起补水并看今日重点');
    expect(model.primary?.source).toBe('daily_plan');
  });

  it('falls back to timeline now item when no dynamic or daily plan action exists', () => {
    const model = buildTodayFocusModel({
      timeline: timeline('餐后步行 10 分钟'),
    });

    expect(model.primary?.title).toBe('餐后步行 10 分钟');
    expect(model.primary?.source).toBe('timeline');
  });

  it('returns honest empty state when no real action exists', () => {
    const model = buildTodayFocusModel({});

    expect(model.primary).toBeNull();
    expect(model.emptyTitle).toBe('今日暂无重点行动');
  });

  it('normalizes duplicate keys consistently', () => {
    expect(normalizeTodayFocusKey('  晨起启动：补水并看今日重点 ')).toBe('晨起启动:补水并看今日重点');
  });
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
pnpm --dir mobile exec jest --runTestsByPath components/chat/__tests__/todayFocus.test.ts --runInBand
```

Expected: fail because `../todayFocus` does not exist.

**Step 3: Write minimal implementation**

Create `mobile/components/chat/todayFocus.ts`.

Implementation shape:

```ts
import type { TodayDynamicView } from '../../services/todayDynamicView';
import type { DailyOperatingPlan, DailyPlanAction } from '../../services/dailyPlan';
import type { TodayTimelineItem, TodayTimelineResponse } from '../../services/todayTimeline';

export type TodayFocusSource = 'dynamic_today' | 'daily_plan' | 'timeline';

export interface TodayFocusPrimary {
  key: string;
  source: TodayFocusSource;
  title: string;
  reason?: string | null;
  deepLink?: string | null;
  evidence: string[];
  verification: string[];
}

export interface TodayFocusModel {
  primary: TodayFocusPrimary | null;
  emptyTitle: string;
  status: {
    actionable: number;
    completed: number;
    overdue: number;
  };
}

export function normalizeTodayFocusKey(value: string | null | undefined): string {
  return (value ?? '')
    .replace(/[：]/g, ':')
    .replace(/\s+/g, '')
    .trim();
}

export function buildTodayFocusModel(args: {
  dynamicView?: TodayDynamicView | null;
  dailyPlan?: DailyOperatingPlan | null;
  timeline?: TodayTimelineResponse | null;
}): TodayFocusModel {
  const primary =
    readDynamicPrimary(args.dynamicView) ??
    readDailyPlanPrimary(args.dailyPlan) ??
    readTimelinePrimary(args.timeline);

  return {
    primary,
    emptyTitle: '今日暂无重点行动',
    status: {
      actionable: Math.max(0, Math.round(args.timeline?.counts?.actionable ?? 0)),
      completed: Math.max(0, Math.round(args.timeline?.past?.completed_count ?? 0)),
      overdue: Math.max(0, Math.round(args.timeline?.counts?.overdue ?? 0)),
    },
  };
}

function readDynamicPrimary(view?: TodayDynamicView | null): TodayFocusPrimary | null {
  const cards = view?.sections?.flatMap(section => section.cards) ?? [];
  for (const card of cards) {
    const atom = typeof card.render?.atom === 'string' ? card.render.atom : '';
    if (atom !== 'daily_artifact') continue;
    const data = card.data as Record<string, any>;
    const title = readText(data?.next_action?.title) || readText(data.title);
    if (!title) continue;
    return {
      key: card.id || normalizeTodayFocusKey(title),
      source: 'dynamic_today',
      title,
      reason: readText(data.why_now) || readText(data.summary),
      deepLink: readText(data?.next_action?.deep_link),
      evidence: readStringList(data.evidence),
      verification: readStringList(data.verification),
    };
  }
  return null;
}

function readDailyPlanPrimary(plan?: DailyOperatingPlan | null): TodayFocusPrimary | null {
  const action = (plan?.actions ?? []).find(item => item?.title);
  if (!action) return null;
  return fromPlanAction(action);
}

function fromPlanAction(action: DailyPlanAction): TodayFocusPrimary {
  const title = action.title;
  return {
    key: action.action_key || normalizeTodayFocusKey(title),
    source: 'daily_plan',
    title,
    reason: action.why ?? null,
    deepLink: null,
    evidence: readStringList(action.evidence_refs),
    verification: [
      action.verification?.cycle_target_metric_label,
      action.verification?.metric,
    ].filter((item): item is string => Boolean(item)),
  };
}

function readTimelinePrimary(timeline?: TodayTimelineResponse | null): TodayFocusPrimary | null {
  const nowId = timeline?.now;
  const item = (timeline?.items ?? []).find(row => row.id === nowId) ?? (timeline?.items ?? [])[0];
  if (!item?.title) return null;
  return fromTimelineItem(item);
}

function fromTimelineItem(item: TodayTimelineItem): TodayFocusPrimary {
  return {
    key: item.id || normalizeTodayFocusKey(item.title),
    source: 'timeline',
    title: item.title,
    reason: item.subtitle,
    deepLink: item.deep_link,
    evidence: item.proof?.label ? [item.proof.label] : [],
    verification: [],
  };
}

function readText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function readStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map(item => typeof item === 'string' ? item.trim() : '')
    .filter(Boolean)
    .slice(0, 4);
}
```

**Step 4: Run test to verify it passes**

Run:

```bash
pnpm --dir mobile exec jest --runTestsByPath components/chat/__tests__/todayFocus.test.ts --runInBand
```

Expected: pass.

**Step 5: Commit**

Do not use `git add -A`. Commit only the resolver files if the worktree is safe:

```bash
git add mobile/components/chat/todayFocus.ts mobile/components/chat/__tests__/todayFocus.test.ts
git commit -m "feat(mobile): resolve chat today focus action"
```

If unrelated staged changes exist, skip commit and report the blocker.

---

## Task 2: Build the ChatTodayFocusCard Component

**Files:**
- Create: `mobile/components/chat/ChatTodayFocusCard.tsx`
- Test: `mobile/components/chat/__tests__/ChatTodayFocusCard.test.tsx`
- Read: `mobile/constants/revaTheme.ts`

**Step 1: Write the failing tests**

Create `mobile/components/chat/__tests__/ChatTodayFocusCard.test.tsx`.

Test default, expanded, empty, and actions:

```tsx
import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import ChatTodayFocusCard from '../ChatTodayFocusCard';
import type { TodayFocusModel } from '../todayFocus';

const model: TodayFocusModel = {
  emptyTitle: '今日暂无重点行动',
  primary: {
    key: 'recovery',
    source: 'dynamic_today',
    title: '恢复/休息：暂停高强度',
    reason: '昨晚恢复偏弱，今天优先降低训练负荷。',
    deepLink: '/fitness-plan',
    evidence: ['睡眠恢复偏弱', 'HRV 低于近期基线'],
    verification: ['今晚睡眠', '主观疲劳'],
  },
  status: { actionable: 3, completed: 1, overdue: 0 },
};

describe('ChatTodayFocusCard', () => {
  it('renders one primary action and compact status', () => {
    const { getByText, queryByText } = render(
      <ChatTodayFocusCard model={model} onExecute={jest.fn()} onAsk={jest.fn()} />,
    );

    expect(getByText('现在最重要')).toBeTruthy();
    expect(getByText('恢复/休息：暂停高强度')).toBeTruthy();
    expect(getByText('昨晚恢复偏弱，今天优先降低训练负荷。')).toBeTruthy();
    expect(getByText('待办 3 · 已完成 1')).toBeTruthy();
    expect(queryByText('睡眠恢复偏弱')).toBeNull();
  });

  it('expands why-now evidence locally', () => {
    const { getByText } = render(
      <ChatTodayFocusCard model={model} onExecute={jest.fn()} onAsk={jest.fn()} />,
    );

    fireEvent.press(getByText('为什么'));

    expect(getByText('依据')).toBeTruthy();
    expect(getByText('睡眠恢复偏弱')).toBeTruthy();
    expect(getByText('验证')).toBeTruthy();
    expect(getByText('今晚睡眠')).toBeTruthy();
  });

  it('calls execute and ask callbacks with the selected primary action', () => {
    const onExecute = jest.fn();
    const onAsk = jest.fn();
    const { getByText } = render(
      <ChatTodayFocusCard model={model} onExecute={onExecute} onAsk={onAsk} />,
    );

    fireEvent.press(getByText('去执行'));
    fireEvent.press(getByText('问小巴'));

    expect(onExecute).toHaveBeenCalledWith(model.primary);
    expect(onAsk).toHaveBeenCalledWith(model.primary);
  });

  it('renders honest empty state', () => {
    const { getByText, queryByText } = render(
      <ChatTodayFocusCard
        model={{ primary: null, emptyTitle: '今日暂无重点行动', status: { actionable: 0, completed: 0, overdue: 0 } }}
        onExecute={jest.fn()}
        onAsk={jest.fn()}
      />,
    );

    expect(getByText('今日暂无重点行动')).toBeTruthy();
    expect(queryByText('去执行')).toBeNull();
  });
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
pnpm --dir mobile exec jest --runTestsByPath components/chat/__tests__/ChatTodayFocusCard.test.tsx --runInBand
```

Expected: fail because component does not exist.

**Step 3: Write minimal implementation**

Create `mobile/components/chat/ChatTodayFocusCard.tsx`.

Implementation requirements:

- Use `revaColors`, `revaRadii`, `revaSpacing`, `revaShadows`, `revaFonts`.
- Keep card compact: margin horizontal `revaSpacing.s3`, vertical padding `10-12`.
- Render only one primary title.
- `为什么` toggles local expanded state.
- Do not render empty evidence headings when arrays are empty.

**Step 4: Run test to verify it passes**

Run:

```bash
pnpm --dir mobile exec jest --runTestsByPath components/chat/__tests__/ChatTodayFocusCard.test.tsx --runInBand
```

Expected: pass.

**Step 5: Commit**

```bash
git add mobile/components/chat/ChatTodayFocusCard.tsx mobile/components/chat/__tests__/ChatTodayFocusCard.test.tsx
git commit -m "feat(mobile): add chat today focus card"
```

Skip commit if unrelated staged changes exist.

---

## Task 3: Wire Focus Card Into ChatScreen

**Files:**
- Modify: `mobile/app/(tabs)/chat.tsx`
- Modify/Test: `mobile/app/(tabs)/__tests__/chat.test.tsx`
- Remove later only if unused: `mobile/components/chat/BriefingStrip.tsx`

**Step 1: Write the failing test**

In `mobile/app/(tabs)/__tests__/chat.test.tsx`, add or update a test that asserts:

- `ChatTodayFocusCard` is rendered under `ChatHeader`.
- `BriefingStrip` is not rendered on the chat main surface.
- Pressing `问小巴` creates focused input context or sends a prompt, depending on final callback choice.

Use a mock component to expose props:

```tsx
jest.mock('../../../components/chat/ChatTodayFocusCard', () => {
  const React = require('react');
  const { Text, TouchableOpacity, View } = require('react-native');
  return function MockChatTodayFocusCard(props: any) {
    return (
      <View testID="chat-today-focus-card">
        <Text>{props.model.primary?.title ?? props.model.emptyTitle}</Text>
        <TouchableOpacity onPress={() => props.onAsk(props.model.primary)} accessibilityLabel="问小巴今日焦点">
          <Text>问小巴</Text>
        </TouchableOpacity>
      </View>
    );
  };
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
pnpm --dir mobile exec jest --runTestsByPath app/'(tabs)'/__tests__/chat.test.tsx --runInBand
```

Expected: fail because `ChatScreen` still renders `BriefingStrip`.

**Step 3: Wire the component**

In `mobile/app/(tabs)/chat.tsx`:

- Import `ChatTodayFocusCard`.
- Import `buildTodayFocusModel` and `TodayFocusPrimary`.
- Add daily plan / dynamic Today data only if already available in `ChatScreen`; otherwise start with timeline-only model in this task.
- Replace:

```tsx
{!briefingHidden && (
  <BriefingStrip timeline={todayTimeline.data} onDismiss={() => setBriefingHidden(true)} />
)}
```

with:

```tsx
<ChatTodayFocusCard
  model={todayFocusModel}
  onExecute={handleTodayFocusExecute}
  onAsk={handleTodayFocusAsk}
/>
```

Add:

```ts
const todayFocusModel = useMemo(
  () => buildTodayFocusModel({ timeline: todayTimeline.data }),
  [todayTimeline.data],
);
```

Add callbacks:

```ts
const handleTodayFocusExecute = useCallback((primary: TodayFocusPrimary | null) => {
  if (primary?.deepLink) {
    router.push(primary.deepLink as any);
    return;
  }
  router.push('/(tabs)/today' as any);
}, []);

const handleTodayFocusAsk = useCallback((primary: TodayFocusPrimary | null) => {
  const text = primary
    ? `为什么今天最重要的是「${primary.title}」？请给我执行步骤和验证方式。`
    : '今天我最应该先做什么？请基于真实数据说明原因。';
  setInitialInput(text);
  setInitialInputKey(key => key + 1);
  setComposerFocusToken(token => token + 1);
}, []);
```

**Step 4: Run test to verify it passes**

Run:

```bash
pnpm --dir mobile exec jest --runTestsByPath app/'(tabs)'/__tests__/chat.test.tsx --runInBand
```

Expected: pass. Existing `act(...)` warnings may remain; do not treat them as new failures if exit code is 0.

**Step 5: Commit**

```bash
git add mobile/app/'(tabs)'/chat.tsx mobile/app/'(tabs)'/__tests__/chat.test.tsx
git commit -m "feat(mobile): show today focus on chat home"
```

Skip commit if unrelated staged changes exist.

---

## Task 4: Add Dedupe and Status Strip Details

**Files:**
- Modify: `mobile/components/chat/todayFocus.ts`
- Modify/Test: `mobile/components/chat/__tests__/todayFocus.test.ts`
- Modify/Test: `mobile/components/chat/__tests__/ChatTodayFocusCard.test.tsx`

**Step 1: Write failing resolver tests**

Add tests that assert:

- Promoted primary action is not included in secondary items.
- Secondary status counts still show queue totals.
- Duplicate titles normalize across punctuation and whitespace.

Example:

```ts
it('dedupes secondary items against promoted primary action', () => {
  const model = buildTodayFocusModel({
    dailyPlan: dailyPlan('晨起启动：补水并看今日重点'),
    timeline: {
      ...timeline('晨起启动: 补水并看今日重点'),
      counts: { actionable: 2, overdue: 1, info: 0 },
    },
  });

  expect(model.primary?.title).toBe('晨起启动：补水并看今日重点');
  expect(model.status.actionable).toBe(2);
  expect(model.secondaryItems?.some(item => normalizeTodayFocusKey(item.title) === model.primary?.key)).toBe(false);
});
```

**Step 2: Run tests to verify failure**

Run:

```bash
pnpm --dir mobile exec jest --runTestsByPath components/chat/__tests__/todayFocus.test.ts components/chat/__tests__/ChatTodayFocusCard.test.tsx --runInBand
```

Expected: fail on missing secondary model.

**Step 3: Implement secondary model**

Extend `TodayFocusModel`:

```ts
secondaryItems: Array<{
  key: string;
  title: string;
  source: TodayFocusSource | 'status';
  deepLink?: string | null;
}>;
```

Build secondary items from timeline/daily plan, excluding the primary key.

Keep the card compact: status strip should remain a single row, not a list.

**Step 4: Run tests**

Run the same focused tests. Expected: pass.

**Step 5: Commit**

```bash
git add mobile/components/chat/todayFocus.ts mobile/components/chat/__tests__/todayFocus.test.ts mobile/components/chat/__tests__/ChatTodayFocusCard.test.tsx
git commit -m "feat(mobile): dedupe chat today focus status"
```

Skip commit if unrelated staged changes exist.

---

## Task 5: Add Richer Data Sources Without Fabrication

**Files:**
- Modify: `mobile/app/(tabs)/chat.tsx`
- Modify: `mobile/components/chat/todayFocus.ts`
- Test: `mobile/components/chat/__tests__/todayFocus.test.ts`
- Test: `mobile/app/(tabs)/__tests__/chat.test.tsx`

**Step 1: Write failing tests**

Add tests that assert:

- Dynamic Today evidence renders when provided.
- Weather/air quality labels do not render when absent.
- Empty state does not invent summary text.

**Step 2: Run tests to verify failure**

Run:

```bash
pnpm --dir mobile exec jest --runTestsByPath components/chat/__tests__/todayFocus.test.ts app/'(tabs)'/__tests__/chat.test.tsx --runInBand
```

Expected: fail on missing dynamic data hookup.

**Step 3: Hook available Today data**

Use existing hooks/services only. If `ChatScreen` does not already fetch `getTodayDynamicView` or `getDailyOperatingPlan`, add React Query calls carefully:

- Query keys should match existing Today screen conventions where possible.
- Do not block chat render on these queries.
- Resolver should accept `undefined` and return timeline/empty fallback.

**Step 4: Run tests**

Run:

```bash
pnpm --dir mobile exec jest --runTestsByPath components/chat/__tests__/todayFocus.test.ts components/chat/__tests__/ChatTodayFocusCard.test.tsx app/'(tabs)'/__tests__/chat.test.tsx --runInBand
```

Expected: pass.

**Step 5: Commit**

```bash
git add mobile/app/'(tabs)'/chat.tsx mobile/components/chat/todayFocus.ts mobile/components/chat/__tests__/todayFocus.test.ts mobile/app/'(tabs)'/__tests__/chat.test.tsx
git commit -m "feat(mobile): enrich chat today focus evidence"
```

Skip commit if unrelated staged changes exist.

---

## Task 6: Visual and Type Verification

**Files:**
- No source changes expected.
- Optional artifact: `artifacts/chat-today-focus/`

**Step 1: Run focused tests**

Run:

```bash
pnpm --dir mobile exec jest --runTestsByPath components/chat/__tests__/todayFocus.test.ts components/chat/__tests__/ChatTodayFocusCard.test.tsx components/chat/__tests__/ChatInputBar.test.tsx app/'(tabs)'/__tests__/chat.test.tsx --runInBand
```

Expected: all pass. Existing `act(...)` warnings in `chat.test.tsx` may remain.

**Step 2: Run TypeScript**

Run:

```bash
pnpm --dir mobile exec tsc --noEmit
```

Expected: exit code 0.

**Step 3: Simulator screenshot**

Start dev client:

```bash
pnpm --dir mobile start --dev-client --localhost
```

Open the simulator dev URL. If Metro listens only on `[::1]:8081`, use the local proxy pattern already used in this repo session.

Capture:

```bash
mkdir -p artifacts/chat-today-focus
xcrun simctl io booted screenshot artifacts/chat-today-focus/01-focus-card-default.png
```

Verify visually:

- First screen shows one clear primary action.
- Status row is compact.
- Input bar remains warm Reva color, not black.
- Voice mode still toggles to `按住 说话`.
- No overlapping text.

**Step 4: Final commit if safe**

If no unrelated staged changes exist:

```bash
git status --short
git add artifacts/chat-today-focus/01-focus-card-default.png
git commit -m "test(mobile): verify chat today focus UI"
```

Usually do not commit screenshots unless the project keeps visual artifacts in git. If unsure, leave the artifact untracked and report its path.
