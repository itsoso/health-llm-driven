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

  it('opens the isolated demo on-ramp before entering 小巴', () => {
    const { getByLabelText } = render(<RevaTryEntryCard />);

    fireEvent.press(getByLabelText('试试小巴'));

    expect(mockPush).toHaveBeenCalledWith('/reva-onboarding?mode=demo');
  });

  it('presents the home entry with the 小巴 product persona', () => {
    const { getByText, queryByText } = render(<RevaTryEntryCard />);

    expect(getByText('小巴')).toBeTruthy();
    expect(getByText('就绪度 · 数据 · 小巴对话,一套主动健康体验')).toBeTruthy();
    expect(queryByText('复元')).toBeNull();
    expect(queryByText('就绪度 · 数据 · 复元对话,一套主动健康体验')).toBeNull();
  });
});
