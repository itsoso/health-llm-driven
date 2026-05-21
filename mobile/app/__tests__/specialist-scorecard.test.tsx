/* eslint-disable import/first */
import React from 'react';
import { render } from '@testing-library/react-native';

const mockBack = jest.fn();
let mockParams: { name?: string } = { name: 'recovery_coach' };
let mockScorecard: any;

jest.mock('expo-router', () => ({
  Stack: { Screen: 'StackScreen' },
  useRouter: () => ({ back: mockBack }),
  useLocalSearchParams: () => mockParams,
}));

jest.mock('../../hooks/useSpecialistScorecard', () => ({
  useSpecialistScorecard: (...args: any[]) => mockScorecard(...args),
}));

jest.mock('../../services/clientEvents', () => ({
  emitClientEvent: jest.fn(),
}));

import SpecialistScorecardScreen from '../specialist/[name]';

describe('SpecialistScorecardScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockParams = { name: 'recovery_coach' };
    mockScorecard = jest.fn().mockReturnValue({
      data: null,
      isLoading: false,
      isError: false,
      error: null,
      isRefetching: false,
      refetch: jest.fn(),
    });
  });

  it('shows an explicit error state when scorecard loading fails', () => {
    mockScorecard = jest.fn().mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
      error: new Error('网络问题'),
      isRefetching: false,
      refetch: jest.fn(),
    });

    const { getByText } = render(<SpecialistScorecardScreen />);

    expect(getByText('加载失败: 网络问题')).toBeTruthy();
  });

  it('does not query scorecard when route name is missing', () => {
    mockParams = {};

    const { getByText } = render(<SpecialistScorecardScreen />);

    expect(mockScorecard).not.toHaveBeenCalled();
    expect(getByText('specialist 未知')).toBeTruthy();
  });
});
