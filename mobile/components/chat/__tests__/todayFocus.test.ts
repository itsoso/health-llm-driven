import {
  buildTodayFocusModel,
  normalizeTodayFocusKey,
} from '../todayFocus';
import type { DailyOperatingPlan } from '../../../services/dailyPlan';
import type { TodayDynamicView } from '../../../services/todayDynamicView';
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

const atLocalTime = (hour: number, minute: number): Date => (
  new Date(2026, 6, 16, hour, minute, 0, 0)
);

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

  it('dedupes the promoted timeline action from remaining actionable count', () => {
    const model = buildTodayFocusModel({
      timeline: timeline('餐后步行 10 分钟'),
    });

    expect(model.primary?.title).toBe('餐后步行 10 分钟');
    expect(model.status.actionable).toBe(1);
  });

  it('dedupes a promoted dynamic action by normalized title when timeline has the same item', () => {
    const model = buildTodayFocusModel({
      dynamicView: dynamicView('餐后步行 10 分钟'),
      timeline: timeline('餐后步行 10 分钟'),
    });

    expect(model.primary?.source).toBe('dynamic_today');
    expect(model.status.actionable).toBe(1);
  });

  it('does not promote completed or skipped timeline items', () => {
    const completedTimeline = timeline('餐后步行 10 分钟');
    completedTimeline.items[0].status = 'completed';
    completedTimeline.items.push({
      ...completedTimeline.items[0],
      id: 'timeline-2',
      title: '晚间散步 10 分钟',
      status: 'skipped',
    });

    const model = buildTodayFocusModel({ timeline: completedTimeline });

    expect(model.primary).toBeNull();
    expect(model.status.actionable).toBe(2);
  });

  it('normalizes duplicate keys consistently', () => {
    expect(normalizeTodayFocusKey('  晨起启动：补水并看今日重点 ')).toBe('晨起启动:补水并看今日重点');
  });

  it('keeps an unscheduled pending item out of the conversation header', () => {
    const pendingTimeline = timeline('晨起记录体重和腰围');
    pendingTimeline.date = '2026-07-16';

    const model = buildTodayFocusModel({
      timeline: pendingTimeline,
      now: atLocalTime(15, 0),
    });

    expect(model.contextStrip).toBeNull();
  });

  it('shows a due item with direct now copy', () => {
    const dueTimeline = timeline('记录体重和腰围');
    dueTimeline.date = '2026-07-16';
    dueTimeline.items[0].status = 'due';

    const model = buildTodayFocusModel({
      timeline: dueTimeline,
      now: atLocalTime(8, 30),
    });

    expect(model.contextStrip).toEqual(expect.objectContaining({
      key: 'timeline-1',
      label: '现在',
      title: '记录体重和腰围',
      tone: 'normal',
    }));
  });

  it('uses action-oriented copy for overdue context instead of technical period wording', () => {
    const overdueTimeline = timeline('复查：血脂四项');
    overdueTimeline.date = '2026-07-16';
    overdueTimeline.items[0].status = 'overdue';

    const model = buildTodayFocusModel({
      timeline: overdueTimeline,
      now: atLocalTime(12, 30),
    });

    expect(model.contextStrip).toEqual(expect.objectContaining({
      label: '待处理',
      title: '复查：血脂四项',
      tone: 'caution',
    }));
  });

  it('prioritizes a high-severity state over a due action', () => {
    const safetyTimeline = timeline('记录体重和腰围');
    safetyTimeline.date = '2026-07-16';
    safetyTimeline.items[0].status = 'due';
    safetyTimeline.items.push({
      ...safetyTimeline.items[0],
      id: 'safety-1',
      title: '恢复状态明显下降',
      status: 'info',
      severity: 'high',
      priority: 2,
    });

    const model = buildTodayFocusModel({
      timeline: safetyTimeline,
      now: atLocalTime(8, 30),
    });

    expect(model.contextStrip).toEqual(expect.objectContaining({
      key: 'safety-1',
      label: '需要关注',
      title: '恢复状态明显下降',
      tone: 'risk',
    }));
  });

  it('shows only precisely scheduled actions within the next 90 minutes', () => {
    const nearTimeline = timeline('记录午餐');
    nearTimeline.date = '2026-07-16';
    nearTimeline.items[0].scheduled_for = '09:30';

    const nearModel = buildTodayFocusModel({
      timeline: nearTimeline,
      now: atLocalTime(8, 15),
    });
    const farModel = buildTodayFocusModel({
      timeline: nearTimeline,
      now: atLocalTime(7, 30),
    });

    expect(nearModel.contextStrip).toEqual(expect.objectContaining({
      label: '09:30',
      title: '记录午餐',
    }));
    expect(farModel.contextStrip).toBeNull();
  });
});
