import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

import RevaTimelineStrip from '../RevaTimelineStrip';

let mockTimeline: any = null;
const mockPush = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
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
    jest.clearAllMocks();
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

  it('opens the full agenda queue from the Today header action', () => {
    const { getByText } = render(<RevaTimelineStrip />);

    fireEvent.press(getByText('待办 5 · 已完成 1'));

    expect(mockPush).toHaveBeenCalledWith('/agenda');
  });

  it('opens photo meal timeline actions in camera capture instead of the generic diet page', () => {
    mockTimeline.items = [
      item('photo-meal', '拍照记餐', {
        subtitle: '打开相机拍一下今天午餐',
        deep_link: '/diet',
      }),
    ];

    const { getByText } = render(<RevaTimelineStrip />);

    fireEvent.press(getByText('拍照记餐'));

    expect(mockPush).toHaveBeenCalledWith('/diet?capture=photo&return_to=chat');
  });

  it('keeps calendar work blocks out of the Today next-actions strip', () => {
    mockTimeline.items = [
      item('work', '年终总结会议', { kind: 'work', driver: 'plan_driven' }),
      item('water', '补水 300ml'),
    ];

    const { getByText, queryByText } = render(<RevaTimelineStrip />);

    expect(queryByText('年终总结会议')).toBeNull();
    expect(getByText('补水 300ml')).toBeTruthy();
    expect(getByText('待办 1 · 已完成 1')).toBeTruthy();
  });

  // ── defect ⑤:带精确时点且已过 >2h 的项标「已过时段」(弱提示,不重排、不标红) ──
  describe('overdue tag', () => {
    beforeEach(() => {
      jest.useFakeTimers();
      jest.setSystemTime(new Date('2026-06-29T15:06:00'));
    });
    afterEach(() => {
      jest.useRealTimers();
    });

    it('tags an item scheduled >2h in the past as 已过时段', () => {
      mockTimeline.items = [
        item('early', '晨间体重', { scheduled_for: '08:00' }), // 15:06 时已过 >2h
        item('soon', '午后补水', { scheduled_for: '14:30' }), // 仅过 36 分钟,不标
      ];

      const { getByText, queryAllByText } = render(<RevaTimelineStrip />);

      expect(getByText('晨间体重')).toBeTruthy();
      expect(getByText('午后补水')).toBeTruthy();
      // 只有 08:00 那条被标,14:30 那条不标
      expect(queryAllByText('已过时段')).toHaveLength(1);
    });

    it('does not tag items without a precise scheduled_for time', () => {
      mockTimeline.items = [
        item('windowed', '午间用药', { scheduled_for: null }),
      ];

      const { queryByText } = render(<RevaTimelineStrip />);

      expect(queryByText('已过时段')).toBeNull();
    });
  });
});
