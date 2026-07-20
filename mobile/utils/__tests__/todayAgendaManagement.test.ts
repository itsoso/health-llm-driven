import type { AgendaItem } from '../../services/agenda';
import {
  agendaItemKey,
  cleanAgendaTitle,
  groupTodayAgendaItems,
  resolveAgendaBackAction,
} from '../todayAgendaManagement';

function item(overrides: Partial<AgendaItem>): AgendaItem {
  return {
    type: 'hydration',
    title: '喝水 200ml',
    status: 'pending',
    priority: 50,
    time_window: 'anytime',
    source: { object_type: 'health_protocol', object_id: 1 },
    ...overrides,
  };
}

describe('todayAgendaManagement', () => {
  it('groups today items into now, later and handled in priority order', () => {
    const morningMedication = item({
      type: 'medication',
      title: '晨间用药',
      priority: 90,
      time_window: 'morning',
      source: { object_type: 'health_protocol', object_id: 2 },
    });
    const anytimeHydration = item({ priority: 60 });
    const eveningWalk = item({
      type: 'training',
      title: '晚饭后步行',
      priority: 80,
      time_window: 'evening',
      source: { object_type: 'daily_plan_action', object_id: 'walk' },
    });
    const completed = item({
      title: '已完成补水',
      status: 'completed',
      priority: 100,
      source: { object_type: 'health_protocol', object_id: 3 },
    });

    const groups = groupTodayAgendaItems(
      [anytimeHydration, completed, eveningWalk, morningMedication],
      { now: new Date('2026-07-20T09:00:00-04:00') },
    );

    expect(groups.now.map(entry => entry.title)).toEqual(['晨间用药', '喝水 200ml']);
    expect(groups.later.map(entry => entry.title)).toEqual(['晚饭后步行']);
    expect(groups.handled.map(entry => entry.title)).toEqual(['已完成补水']);
  });

  it('moves a session-snoozed action to later without marking it complete', () => {
    const hydration = item({ source: { object_type: 'health_protocol', object_id: 9 } });
    const key = agendaItemKey(hydration);

    const groups = groupTodayAgendaItems([hydration], {
      now: new Date('2026-07-20T12:00:00-04:00'),
      snoozedKeys: new Set([key]),
    });

    expect(groups.now).toEqual([]);
    expect(groups.later).toEqual([hydration]);
    expect(groups.handled).toEqual([]);
  });

  it('removes internal metric and producer labels from user-facing titles', () => {
    expect(cleanAgendaTitle('[spo2_avg] 血氧饱和度偏低')).toBe('血氧饱和度偏低');
    expect(cleanAgendaTitle('anomaly_detector  睡眠评分极低')).toBe('睡眠评分极低');
    expect(cleanAgendaTitle('safety_guardian')).toBe('今日健康行动');
  });

  it('uses native back when possible and chat as the deep-link fallback', () => {
    expect(resolveAgendaBackAction(true)).toEqual({ type: 'back' });
    expect(resolveAgendaBackAction(false)).toEqual({ type: 'navigate', route: '/(tabs)/chat' });
  });
});
