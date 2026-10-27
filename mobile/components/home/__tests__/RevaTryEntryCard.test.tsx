import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

const mockPush = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('expo-haptics', () => ({
  selectionAsync: jest.fn().mockResolvedValue(undefined),
}));

import RevaTryEntryCard from '../RevaTryEntryCard';

describe('RevaTryEntryCard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('opens the isolated demo on-ramp before entering 小气候', () => {
    const { getByLabelText } = render(<RevaTryEntryCard />);

    fireEvent.press(getByLabelText('试试小气候'));

    expect(mockPush).toHaveBeenCalledWith('/reva-onboarding?mode=demo');
  });

  it('presents the home entry with the 小气候 product persona', () => {
    const { getByText, queryByText } = render(<RevaTryEntryCard />);

    expect(getByText('小气候')).toBeTruthy();
    expect(getByText('就绪度 · 数据 · 小气候对话,一套主动健康体验')).toBeTruthy();
    expect(queryByText('复元')).toBeNull();
    expect(queryByText('就绪度 · 数据 · 复元对话,一套主动健康体验')).toBeNull();
  });
});
