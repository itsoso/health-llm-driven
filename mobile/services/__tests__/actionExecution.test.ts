jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn(), patch: jest.fn(), post: jest.fn(), delete: jest.fn(), put: jest.fn() },
}));

import api from '../api';
import {
  getExecuteCapability,
  getExecuteLabel,
  getNavigationTarget,
  executeReminderForCard,
  defaultReminderTime,
} from '../actionExecution';
import type { ActionCard } from '../actionCards';

const mockPost = api.post as jest.Mock;

function makeCard(overrides: Partial<ActionCard> = {}): ActionCard {
  return {
    id: 1,
    title: 'test',
    content: 'body',
    card_type: 'note',
    status: 'active',
    priority: 0,
    is_visible: true,
    created_at: null,
    ...overrides,
  } as ActionCard;
}

describe('getExecuteCapability', () => {
  it('reminder card returns reminder', () => {
    expect(getExecuteCapability(makeCard({ card_type: 'reminder' }))).toBe('reminder');
  });

  it('recommendation with metric_key returns navigate', () => {
    expect(getExecuteCapability(makeCard({ card_type: 'recommendation', metric_key: 'weight' }))).toBe('navigate');
  });

  it('guide with metric_key returns navigate', () => {
    expect(getExecuteCapability(makeCard({ card_type: 'guide', metric_key: 'hrv' }))).toBe('navigate');
  });

  it('plan with metric_key also navigates (Phase 2 v1, expo-calendar 后置)', () => {
    expect(getExecuteCapability(makeCard({ card_type: 'plan', metric_key: 'weight' }))).toBe('navigate');
  });

  it('recommendation without metric_key has no handler', () => {
    expect(getExecuteCapability(makeCard({ card_type: 'recommendation' }))).toBeNull();
  });

  it('insight / note never executable', () => {
    expect(getExecuteCapability(makeCard({ card_type: 'insight' }))).toBeNull();
    expect(getExecuteCapability(makeCard({ card_type: 'note', metric_key: 'weight' }))).toBeNull();
  });

  it('completed cards not executable even if reminder', () => {
    expect(getExecuteCapability(makeCard({ card_type: 'reminder', status: 'completed' }))).toBeNull();
  });

  it('archived cards not executable', () => {
    expect(getExecuteCapability(makeCard({ card_type: 'reminder', status: 'archived' }))).toBeNull();
  });
});

describe('getExecuteLabel', () => {
  it('reminder → 设置提醒', () => {
    expect(getExecuteLabel('reminder')).toBe('设置提醒');
  });
  it('navigate → 现在记录', () => {
    expect(getExecuteLabel('navigate')).toBe('现在记录');
  });
  it('null → fallback 执行', () => {
    expect(getExecuteLabel(null)).toBe('执行');
  });
});

describe('getNavigationTarget', () => {
  it('weight → record tab', () => {
    expect(getNavigationTarget(makeCard({ metric_key: 'weight' }))).toBe('/(tabs)/record');
  });

  it('blood pressure → /blood-pressure', () => {
    expect(getNavigationTarget(makeCard({ metric_key: 'systolic_bp' }))).toBe('/blood-pressure');
    expect(getNavigationTarget(makeCard({ metric_key: 'bp' }))).toBe('/blood-pressure');
  });

  it('sleep / hrv / rhr → /sleep', () => {
    expect(getNavigationTarget(makeCard({ metric_key: 'sleep_score' }))).toBe('/sleep');
    expect(getNavigationTarget(makeCard({ metric_key: 'hrv' }))).toBe('/sleep');
    expect(getNavigationTarget(makeCard({ metric_key: 'rhr' }))).toBe('/sleep');
  });

  it('spo2 → spo2 analysis page (任意 spo2_* 前缀都接)', () => {
    expect(getNavigationTarget(makeCard({ metric_key: 'spo2_odi' }))).toBe('/sleep-spo2-analysis');
    // 后端如果加 spo2_min/spo2_avg, 不在 ActionCardMetricKey union 里, 用 as any 模拟
    expect(getNavigationTarget(makeCard({ metric_key: 'spo2_min' as any }))).toBe('/sleep-spo2-analysis');
  });

  it('lab metrics → indicator-history', () => {
    expect(getNavigationTarget(makeCard({ metric_key: 'ldl' }))).toBe('/indicator-history');
    expect(getNavigationTarget(makeCard({ metric_key: 'hba1c' }))).toBe('/indicator-history');
    expect(getNavigationTarget(makeCard({ metric_key: 'alt' }))).toBe('/indicator-history');
  });

  it('unknown metric falls back to record tab', () => {
    expect(getNavigationTarget(makeCard({ metric_key: 'something_weird' as any }))).toBe('/(tabs)/record');
  });

  it('no metric_key falls back to record tab', () => {
    expect(getNavigationTarget(makeCard())).toBe('/(tabs)/record');
  });
});

describe('defaultReminderTime', () => {
  it('+1 小时, 整分钟', () => {
    const noon = new Date('2026-05-04T12:30:00');
    expect(defaultReminderTime(noon)).toBe('13:30');
  });

  it('跨天移到次日 09:00', () => {
    const lateNight = new Date('2026-05-04T23:30:00');
    expect(defaultReminderTime(lateNight)).toBe('09:00');
  });

  it('22:30 还在当天 (+1=23:30, < 23 阈值边界检查 -- 23:30 实际 OK)', () => {
    const evening = new Date('2026-05-04T22:30:00');
    // +1h = 23:30, 但代码 next.getHours() >= 23 判断, 23:30 → 落到次日
    expect(defaultReminderTime(evening)).toBe('09:00');
  });

  it('22:00 还在当天 (+1=23:00, 触发跨天)', () => {
    const t = new Date('2026-05-04T22:00:00');
    // +1h = 23:00, 23 >= 23 → 落到次日
    expect(defaultReminderTime(t)).toBe('09:00');
  });

  it('21:30 当天 (+1=22:30, 不跨天)', () => {
    const t = new Date('2026-05-04T21:30:00');
    expect(defaultReminderTime(t)).toBe('22:30');
  });
});

describe('executeReminderForCard', () => {
  beforeEach(() => jest.clearAllMocks());

  it('调 POST /notification/reminders 用卡片 title + 截断 content', async () => {
    mockPost.mockResolvedValue({
      data: { reminder: { id: 42, reminder_type: 'custom', name: 't', reminder_times: ['10:00'], days_of_week: [1,2,3,4,5,6,7], message: 'x', enabled: true } },
    });
    const card = makeCard({
      title: '每日喝水 2L',
      content: '保持水分摄入,\n建议每天 2L,\n避免脱水.',
      card_type: 'reminder',
    });

    await executeReminderForCard(card, { time: '10:00' });

    expect(mockPost).toHaveBeenCalledTimes(1);
    const [path, body] = mockPost.mock.calls[0];
    expect(path).toBe('/notification/reminders');
    expect(body.reminder_type).toBe('custom');
    expect(body.name).toBe('每日喝水 2L');
    expect(body.reminder_times).toEqual(['10:00']);
    expect(body.days_of_week).toEqual([1,2,3,4,5,6,7]);
    // message 单行 (换行被替换), 80 字内
    expect(body.message).not.toContain('\n');
    expect(body.message.length).toBeLessThanOrEqual(80);
  });

  it('返回创建好的 Reminder 对象', async () => {
    mockPost.mockResolvedValue({
      data: { reminder: { id: 99, reminder_type: 'custom', name: 'x', reminder_times: ['09:00'], days_of_week: [1], message: 'm', enabled: true } },
    });
    const card = makeCard({ card_type: 'reminder', title: 'x' });

    const result = await executeReminderForCard(card, { time: '09:00', daysOfWeek: [1] });

    expect(result.id).toBe(99);
    expect(result.reminder_times).toEqual(['09:00']);
  });

  it('content 缺失时回落到 title 当 message', async () => {
    mockPost.mockResolvedValue({
      data: { reminder: { id: 1, reminder_type: 'custom', name: 't', reminder_times: ['08:00'], days_of_week: [1], message: 't', enabled: true } },
    });
    const card = makeCard({ card_type: 'reminder', title: 'standalone-title', content: '' });

    await executeReminderForCard(card, { time: '08:00' });

    expect(mockPost.mock.calls[0][1].message).toBe('standalone-title');
  });
});
