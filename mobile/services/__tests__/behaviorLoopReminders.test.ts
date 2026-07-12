jest.mock('react-native', () => ({ Platform: { OS: 'ios' } }));

jest.mock('expo-notifications', () => ({
  __esModule: true,
  SchedulableTriggerInputTypes: { DAILY: 'daily', DATE: 'date' },
  getPermissionsAsync: jest.fn(),
  getAllScheduledNotificationsAsync: jest.fn(),
  scheduleNotificationAsync: jest.fn(),
  cancelScheduledNotificationAsync: jest.fn(),
}));

import * as Notifications from 'expo-notifications';
import {
  buildTopActionNotification,
  buildInterventionCycleNotifications,
  behaviorLoopActionToEventType,
  isRecheckDue,
  scheduleBehaviorLoopReminders,
  cancelBehaviorLoopReminders,
  BEHAVIOR_LOOP_KIND,
  INTERVENTION_CYCLE_KIND,
  INTERVENTION_RECHECK_KIND,
} from '../behaviorLoopReminders';
import type { DailyOperatingPlan, DailyPlanAction } from '../dailyPlan';
import type { InterventionCycle } from '../healthOs';

const mockNotif = Notifications as unknown as {
  getPermissionsAsync: jest.Mock;
  getAllScheduledNotificationsAsync: jest.Mock;
  scheduleNotificationAsync: jest.Mock;
  cancelScheduledNotificationAsync: jest.Mock;
};

beforeEach(() => {
  jest.clearAllMocks();
  mockNotif.getAllScheduledNotificationsAsync.mockResolvedValue([]);
  mockNotif.scheduleNotificationAsync.mockResolvedValue('id');
  mockNotif.cancelScheduledNotificationAsync.mockResolvedValue(undefined);
});

const action = (over: Partial<DailyPlanAction> = {}): DailyPlanAction => ({
  domain: 'movement',
  title: '走 8000 步',
  action_key: 'move_walk_8000',
  ...over,
});

const plan = (actions: DailyPlanAction[]): DailyOperatingPlan => ({
  plan_date: '2026-06-14',
  primary_goal: '降 LDL',
  status: 'active',
  state_summary: {},
  actions,
});

const cycle = (over: Partial<InterventionCycle> = {}): InterventionCycle => ({
  id: 7,
  cycle_type: 'metabolic',
  status: 'active',
  start_date: '2026-04-01',
  planned_end_date: '2026-06-30',
  baseline_snapshot_id: null,
  latest_snapshot_id: null,
  target_metrics: [{ code: 'ldl', target: 2.6, direction: 'down' }],
  stop_conditions: null,
  outcomes: [],
  ...over,
});

describe('buildTopActionNotification', () => {
  it('有 top action (含 action_key) → 一条带 BEHAVIOR_LOOP category + DAILY trigger 的通知', () => {
    const spec = buildTopActionNotification(plan([action(), action({ title: '第二件事', action_key: 'b' })]));
    expect(spec).not.toBeNull();
    expect(spec!.content.categoryIdentifier).toBe('BEHAVIOR_LOOP');
    expect(spec!.content.body).toBe('走 8000 步'); // 取第一条 top action, 不另算
    expect(spec!.content.data).toMatchObject({
      kind: BEHAVIOR_LOOP_KIND,
      action_key: 'move_walk_8000',
    });
    expect(spec!.trigger).toMatchObject({ type: 'daily' });
  });

  it('空 plan → null (不发)', () => {
    expect(buildTopActionNotification(plan([]))).toBeNull();
    expect(buildTopActionNotification(null)).toBeNull();
  });

  it('top action 无 action_key → null (完成/跳过无处可记)', () => {
    expect(buildTopActionNotification(plan([action({ action_key: null })]))).toBeNull();
  });

  it('top action 无 title → null', () => {
    expect(buildTopActionNotification(plan([action({ title: '' })]))).toBeNull();
  });
});

describe('behaviorLoopActionToEventType', () => {
  it('完成 → completed; 跳过 → skipped; 稍后 → null', () => {
    expect(behaviorLoopActionToEventType('LOOP_DONE')).toBe('completed');
    expect(behaviorLoopActionToEventType('LOOP_SKIP')).toBe('skipped');
    expect(behaviorLoopActionToEventType('LOOP_LATER')).toBeNull();
  });
});

describe('isRecheckDue', () => {
  const now = new Date('2026-07-01T00:00:00Z');
  it('planned_end_date 已过 → 到期', () => {
    expect(isRecheckDue(cycle({ planned_end_date: '2026-06-30' }), now)).toBe(true);
  });
  it('planned_end_date 未到 → 未到期', () => {
    expect(isRecheckDue(cycle({ planned_end_date: '2026-08-01' }), now)).toBe(false);
  });
  it('非 active → 未到期', () => {
    expect(isRecheckDue(cycle({ status: 'completed', planned_end_date: '2026-06-30' }), now)).toBe(false);
  });
});

describe('buildInterventionCycleNotifications', () => {
  it('active 周期 (未到期) → 1 条周期轻提醒', () => {
    const specs = buildInterventionCycleNotifications(
      cycle({ planned_end_date: '2026-08-01' }),
      new Date('2026-06-14T00:00:00Z'),
    );
    expect(specs).toHaveLength(1);
    expect(specs[0].content.data).toMatchObject({ kind: INTERVENTION_CYCLE_KIND, cycle_id: 7 });
    expect(specs[0].content.data).toMatchObject({ deep_link: '/intervention-cycle' });
    expect(String(specs[0].content.body)).toContain('LDL');
  });

  it('复查到期 → 周期提醒 + 复查提醒 (2 条)', () => {
    const specs = buildInterventionCycleNotifications(
      cycle({ planned_end_date: '2026-06-30' }),
      new Date('2026-07-01T00:00:00Z'),
    );
    expect(specs).toHaveLength(2);
    const kinds = specs.map((s) => (s.content.data as any).kind);
    expect(kinds).toEqual([INTERVENTION_CYCLE_KIND, INTERVENTION_RECHECK_KIND]);
    const recheck = specs[1];
    expect(recheck.trigger).toBeNull(); // 立即投递
    expect((recheck.content.data as any).deep_link).toBe('/intervention-cycle');
  });

  it('复查到期但仍在 09:00 前 → 复查提醒延迟到当天 09:00', () => {
    const specs = buildInterventionCycleNotifications(
      cycle({ planned_end_date: '2026-06-30' }),
      new Date('2026-07-01T08:30:00'),
    );
    const recheck = specs[1];
    expect(recheck.trigger).toEqual({
      type: 'date',
      date: new Date('2026-07-01T09:00:00'),
    });
  });

  it('无周期 / 非 active → 空', () => {
    expect(buildInterventionCycleNotifications(null, new Date())).toEqual([]);
    expect(buildInterventionCycleNotifications(cycle({ status: 'completed' }), new Date())).toEqual([]);
  });
});

describe('scheduleBehaviorLoopReminders', () => {
  it('有权限: 先 cancel 本类旧通知 (不动他类), 再排 top action + 周期', async () => {
    mockNotif.getPermissionsAsync.mockResolvedValue({ status: 'granted' });
    mockNotif.getAllScheduledNotificationsAsync.mockResolvedValue([
      { identifier: 'loop_old', content: { data: { kind: BEHAVIOR_LOOP_KIND } } },
      { identifier: 'cycle_old', content: { data: { kind: INTERVENTION_CYCLE_KIND } } },
      { identifier: 'med', content: { data: { kind: 'medication_reminder' } } },
      { identifier: 'openloop', content: { data: { kind: 'open_loop' } } },
    ]);

    const n = await scheduleBehaviorLoopReminders({
      plan: plan([action()]),
      cycle: cycle({ planned_end_date: '2026-08-01' }),
      now: new Date('2026-06-14T00:00:00Z'),
    });

    expect(n).toBe(2); // top action + 周期轻提醒
    // 只 cancel 本类 2 条, 不动 medication / open_loop
    const cancelled = mockNotif.cancelScheduledNotificationAsync.mock.calls.map((c) => c[0]);
    expect(cancelled.sort()).toEqual(['cycle_old', 'loop_old']);
    expect(mockNotif.scheduleNotificationAsync).toHaveBeenCalledTimes(2);
  });

  it('空态 (无 plan top action + 无周期): 仍 cancel 残留, 但不排新的 → 0', async () => {
    mockNotif.getPermissionsAsync.mockResolvedValue({ status: 'granted' });
    const n = await scheduleBehaviorLoopReminders({ plan: plan([]), cycle: null });
    expect(n).toBe(0);
    expect(mockNotif.scheduleNotificationAsync).not.toHaveBeenCalled();
  });

  it('无权限: 不排新的 → 0', async () => {
    mockNotif.getPermissionsAsync.mockResolvedValue({ status: 'denied' });
    const n = await scheduleBehaviorLoopReminders({
      plan: plan([action()]),
      cycle: cycle(),
    });
    expect(n).toBe(0);
    expect(mockNotif.scheduleNotificationAsync).not.toHaveBeenCalled();
  });
});

describe('cancelBehaviorLoopReminders', () => {
  it('只 cancel 本模块的 3 类 kind', async () => {
    mockNotif.getAllScheduledNotificationsAsync.mockResolvedValue([
      { identifier: 'a', content: { data: { kind: BEHAVIOR_LOOP_KIND } } },
      { identifier: 'b', content: { data: { kind: INTERVENTION_RECHECK_KIND } } },
      { identifier: 'c', content: { data: { kind: 'medication_reminder' } } },
      { identifier: 'd', content: { data: {} } },
    ]);
    await cancelBehaviorLoopReminders();
    const cancelled = mockNotif.cancelScheduledNotificationAsync.mock.calls.map((c) => c[0]);
    expect(cancelled.sort()).toEqual(['a', 'b']);
  });
});
