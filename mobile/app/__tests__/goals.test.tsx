/* eslint-disable import/first, @typescript-eslint/no-require-imports */
import React from 'react';
import { render, waitFor } from '@testing-library/react-native';

const mockBack = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: mockBack }),
}));

jest.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: jest.fn() }),
}));

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  ImpactFeedbackStyle: { Medium: 'medium', Light: 'light' },
}));

jest.mock('../../hooks/useGoals', () => ({
  useGoals: () => ({
    data: [
      {
        id: 1,
        title: '每周 4 次 Zone2 有氧',
        description: '改善代谢健康',
        goal_type: 'exercise',
        goal_period: 'weekly',
        target_value: 4,
        target_unit: '次',
        current_value: 1,
        status: 'active',
        start_date: '2026-05-18',
        end_date: null,
        implementation_steps: '今天完成 30 分钟低强度有氧',
        priority: 1,
        notes: null,
      },
    ],
    isLoading: false,
    refetch: jest.fn(),
    isRefetching: false,
  }),
  useUpdateGoalProgress: () => ({ mutate: jest.fn() }),
}));

jest.mock('../../services/goals', () => ({
  generateGoalsFromAnalysis: jest.fn(),
}));

jest.mock('../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgPrimary: '#fff',
      bgCard: '#fff',
      fill: '#f5f5f5',
      labelPrimary: '#111',
      labelSecondary: '#555',
      labelTertiary: '#999',
      labelQuaternary: '#bbb',
      separator: '#eee',
      brand: '#0A8F8F',
      brandLight: '#E6F7F7',
      green: '#16A34A',
      blue: '#2563EB',
      purple: '#7C3AED',
    },
  }),
}));

jest.mock('../../components/goals/GoalCard', () => {
  const React = require('react');
  const { Text, View } = require('react-native');
  const MockGoalCard = ({ goal }: any) => (
    <View>
      <Text>{goal.title}</Text>
    </View>
  );
  MockGoalCard.displayName = 'MockGoalCard';
  return MockGoalCard;
});

jest.mock('../../components/goals/ProgressUpdateSheet', () => {
  const React = require('react');
  const { View } = require('react-native');
  const MockProgressUpdateSheet = () => <View />;
  MockProgressUpdateSheet.displayName = 'MockProgressUpdateSheet';
  return MockProgressUpdateSheet;
});

jest.mock('../../components/agent/AgentFeedbackLink', () => {
  const React = require('react');
  const { Text } = require('react-native');
  const MockAgentFeedbackLink = ({ label }: any) => <Text>{label}</Text>;
  MockAgentFeedbackLink.displayName = 'MockAgentFeedbackLink';
  return MockAgentFeedbackLink;
});

jest.mock('../../utils/agentContext', () => ({
  createGoalsAgentContext: jest.fn(() => ({})),
}));

import GoalsScreen from '../goals';

describe('GoalsScreen', () => {
  it('frames active goals as weekly commitments and today actions', async () => {
    const { getAllByText, getByText } = render(<GoalsScreen />);

    await waitFor(() => expect(getByText('本周承诺')).toBeTruthy());
    expect(getByText('今日动作')).toBeTruthy();
    expect(getAllByText('每周 4 次 Zone2 有氧').length).toBeGreaterThan(0);
    expect(getByText('今天完成 30 分钟低强度有氧')).toBeTruthy();
  });
});
