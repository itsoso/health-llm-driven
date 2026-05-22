/* eslint-disable @typescript-eslint/no-require-imports, import/first */
import React from 'react';
import { render } from '@testing-library/react-native';

const mockPush = jest.fn();
const mockInvalidateQueries = jest.fn();

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
      return { data: { actions: [] }, isLoading: false, isRefetching: false };
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
  });

  it('does not show the low-value Agent data visibility panel on the home feed', () => {
    const { queryByText } = render(<TodayScreen />);

    expect(queryByText('Agent 数据视野')).toBeNull();
  });
});
