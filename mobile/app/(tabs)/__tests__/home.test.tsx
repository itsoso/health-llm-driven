/* eslint-disable @typescript-eslint/no-require-imports, import/first */
import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

const mockPush = jest.fn();
const mockInvalidateQueries = jest.fn();
const mockRecordDailyPlanActionEvent = jest.fn();
let mockDailyPlanActions: unknown[] = [];

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('@tanstack/react-query', () => ({
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    const key = Array.isArray(queryKey) ? queryKey.join(':') : String(queryKey);
    if (key.includes('safety')) {
      return { data: { alerts: [] }, isLoading: false, isRefetching: false };
    }
    if (key.includes('action-cards')) {
      return { data: [], isLoading: false, isRefetching: false };
    }
    if (key.includes('twin')) {
      return { data: {}, isLoading: false, isRefetching: false };
    }
    if (key.includes('daily-plan')) {
      return { data: { actions: mockDailyPlanActions }, isLoading: false, isRefetching: false };
    }
    if (key.includes('trajectory')) {
      return { data: null, isLoading: false, isRefetching: false };
    }
    return { data: null, isLoading: false, isRefetching: false };
  },
  useQueryClient: () => ({
    invalidateQueries: mockInvalidateQueries,
  }),
}));

jest.mock('../../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgPrimary: '#fff',
      bgCard: '#fff',
      fill: '#f5f5f5',
      labelPrimary: '#111',
      labelSecondary: '#555',
      labelTertiary: '#999',
      separator: '#eee',
      brand: '#0A8F8F',
      brandLight: '#E6F7F7',
      purple: '#7C3AED',
      pink: '#EC4899',
      blue: '#2563EB',
      teal: '#0F766E',
      orange: '#EA580C',
      green: '#16A34A',
      red: '#DC2626',
      amber: '#D97706',
      tintBlue: '#DBEAFE',
      tintGreen: '#DCFCE7',
      tintPurple: '#EDE9FE',
      tintPink: '#FCE7F3',
      tintOrange: '#FFEDD5',
      tintTeal: '#CCFBF1',
      tintRed: '#FEE2E2',
      tintAmber: '#FEF3C7',
    },
    isDark: false,
  }),
}));

jest.mock('../../../services/safety', () => ({
  getSafetyReport: jest.fn(),
}));

jest.mock('../../../services/actionCards', () => ({
  getActiveCards: jest.fn(),
  pickWeeklySuggestionCards: jest.fn(() => []),
}));

jest.mock('../../../services/dailyPlan', () => ({
  getDailyOperatingPlan: jest.fn(),
  recordDailyPlanActionEvent: (...args: unknown[]) => mockRecordDailyPlanActionEvent(...args),
}));

jest.mock('../../../services/trajectory', () => ({
  getHealthTrajectory: jest.fn(),
}));

jest.mock('../../../services/api', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

jest.mock('../../../utils/agentContext', () => ({
  pushChatWithContext: jest.fn(),
}));

jest.mock('../../../components/dashboard/TodayPlanPanel', () => 'TodayPlanPanel');
jest.mock('../../../components/dashboard/TrajectorySnapshotPanel', () => 'TrajectorySnapshotPanel');
jest.mock('../../../components/dashboard/EnvironmentCard', () => 'EnvironmentCard');
jest.mock('../../../components/dashboard/DataFreshnessPanel', () => {
  const { Text } = require('react-native');
  const MockDataFreshnessPanel = () => <Text>Agent 数据视野</Text>;
  MockDataFreshnessPanel.displayName = 'MockDataFreshnessPanel';
  return MockDataFreshnessPanel;
});

jest.mock('../../../components/shared/EvidenceChip', () => 'EvidenceChip');
jest.mock('../../../components/knowledge', () => ({
  EvidenceRefsRow: () => null,
}));

import TodayScreen from '../index';

describe('TodayScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockDailyPlanActions = [];
  });

  it('does not show the low-value Agent data visibility panel on the home feed', () => {
    const { queryByText } = render(<TodayScreen />);

    expect(queryByText('Agent 数据视野')).toBeNull();
  });

  it('frames the home screen around today focus and uses compact quick entries', () => {
    const { getByText, queryByText } = render(<TodayScreen />);

    expect(queryByText('今天先做 0 件事')).toBeNull();
    expect(getByText('保持记录节奏')).toBeTruthy();
    expect(getByText('高频入口')).toBeTruthy();
  });

  it('shows the active plan count when today has actions', () => {
    mockDailyPlanActions = [
      { id: '1', title: '晨间记录' },
      { id: '2', title: '步行 20 分钟' },
    ];

    const { getByText } = render(<TodayScreen />);

    expect(getByText('今天先做 2 件事')).toBeTruthy();
  });

  it('surfaces the next best action and lets the user start it directly', () => {
    mockDailyPlanActions = [
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
        why: '同一时间测量噪声更低。',
      },
    ];

    const { getByText } = render(<TodayScreen />);

    expect(getByText('现在先做')).toBeTruthy();
    expect(getByText('晨起记录体重和腰围')).toBeTruthy();

    fireEvent.press(getByText('开始'));

    expect(mockPush).toHaveBeenCalledWith('/body-measurements?focus=morning');
  });

  it('lets the user complete the next best action from the top card', async () => {
    mockRecordDailyPlanActionEvent.mockResolvedValueOnce({
      action_state: 'completed',
      payload: {},
    });
    mockDailyPlanActions = [
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
      },
    ];

    const { getByText } = render(<TodayScreen />);

    fireEvent.press(getByText('完成'));

    await waitFor(() => {
      expect(mockRecordDailyPlanActionEvent).toHaveBeenCalledWith(
        'measurement.weight_waist_morning',
        { event_type: 'completed', payload: { source: 'next_best_action' } },
      );
    });
  });

  it('shows an inline failure when completing the next action fails', async () => {
    mockRecordDailyPlanActionEvent.mockRejectedValueOnce(new Error('network'));
    mockDailyPlanActions = [
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
      },
    ];

    const { getByText } = render(<TodayScreen />);

    fireEvent.press(getByText('完成'));

    await waitFor(() => {
      expect(getByText('记录失败，请重试')).toBeTruthy();
    });
  });

  it('resets completion state when the next action changes', async () => {
    mockRecordDailyPlanActionEvent.mockResolvedValueOnce({
      action_state: 'completed',
      payload: {},
    });
    mockDailyPlanActions = [
      {
        action_key: 'measurement.weight_waist_morning',
        domain: 'measurement',
        title: '晨起记录体重和腰围',
      },
    ];

    const { getByText, queryByText, rerender } = render(<TodayScreen />);

    fireEvent.press(getByText('完成'));

    await waitFor(() => {
      expect(getByText('已完成')).toBeTruthy();
    });

    mockDailyPlanActions = [
      {
        action_key: 'nutrition.log_lunch',
        domain: 'nutrition',
        title: '记录午餐',
      },
    ];
    rerender(<TodayScreen />);

    expect(queryByText('已完成')).toBeNull();
    expect(getByText('完成')).toBeTruthy();
  });
});
