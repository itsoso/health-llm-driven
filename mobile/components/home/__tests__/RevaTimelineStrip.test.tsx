import React from 'react';
import { render } from '@testing-library/react-native';

import RevaTimelineStrip from '../RevaTimelineStrip';

let mockTimeline: any = null;

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock('expo-haptics', () => ({
  selectionAsync: jest.fn(),
  impactAsync: jest.fn(),
  notificationAsync: jest.fn(),
  ImpactFeedbackStyle: { Light: 'light' },
  NotificationFeedbackType: { Success: 'success', Error: 'error' },
}));

jest.mock('../../../hooks/useTodayTimeline', () => ({
  useTodayTimeline: () => ({ data: mockTimeline, isLoading: false, isError: false }),
  useCompleteAgendaItem: () => ({ mutate: jest.fn() }),
  useSkipAgendaItem: () => ({ mutate: jest.fn() }),
}));

function item(id: string, title: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    kind: 'action',
    time_window: 'noon',
    scheduled_for: null,
    title,
    subtitle: '来自时间线',
    icon: 'pulse-outline',
    color: '#1F8A5B',
    status: 'pending',
    priority: 1,
    can_complete: false,
    complete_ref: null,
    deep_link: null,
    severity: null,
    proof: null,
    ...overrides,
  };
}

describe('RevaTimelineStrip', () => {
  beforeEach(() => {
    mockTimeline = {
      date: '2026-06-29',
      current_window: 'noon',
      now: 'walk',
      items: [
        item('walk', '午饭后步行 10 分钟'),
        item('water', '补水 300ml'),
        item('med', '确认午间用药'),
        item('stretch', '肩颈拉伸 5 分钟'),
        item('sleep', '睡前准备'),
        item('done', '已完成行动', { status: 'completed' }),
        item('outcome', '结果复盘', { kind: 'outcome' }),
      ],
      past: { completed_count: 1, events: [] },
      counts: { actionable: 5, overdue: 0, info: 0 },
    };
  });

  it('deduplicates actions already promoted by Aheng and keeps only the next three visible', () => {
    const { getByText, queryByText } = render(
      <RevaTimelineStrip excludeTitles={['午饭后步行 10 分钟']} />,
    );

    expect(queryByText('午饭后步行 10 分钟')).toBeNull();
    expect(queryByText('已完成行动')).toBeNull();
    expect(queryByText('结果复盘')).toBeNull();
    expect(getByText('补水 300ml')).toBeTruthy();
    expect(getByText('确认午间用药')).toBeTruthy();
    expect(getByText('肩颈拉伸 5 分钟')).toBeTruthy();
    expect(queryByText('睡前准备')).toBeNull();
    expect(getByText('待办 4 · 已完成 1')).toBeTruthy();
    expect(getByText('还有 1 项')).toBeTruthy();
  });
});
