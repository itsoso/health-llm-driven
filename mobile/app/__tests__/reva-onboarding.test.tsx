import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

const mockReplace = jest.fn();
let mockParams: Record<string, string> = { mode: 'demo' };

jest.mock('expo-router', () => ({
  __esModule: true,
  useRouter: () => ({ replace: mockReplace }),
  useLocalSearchParams: () => mockParams,
}));

jest.mock('../../components/reva/useRevaFonts', () => ({
  useRevaFonts: () => true,
}));

import RevaOnboardingScreen from '../reva-onboarding';

describe('RevaOnboardingScreen demo mode', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockParams = { mode: 'demo' };
  });

  it('shows a no-write demo on-ramp with safety, evidence, and a Daily Artifact action', () => {
    const { getByText } = render(<RevaOnboardingScreen />);

    expect(getByText('示例模式 · 不写入你的 Twin')).toBeTruthy();
    expect(getByText('安全脑拦截')).toBeTruthy();
    expect(getByText('证据卡')).toBeTruthy();
    expect(getByText('今日最重要行动')).toBeTruthy();
  });

  it('enters the 阿衡 hub without writing demo data', () => {
    const { getByText } = render(<RevaOnboardingScreen />);

    fireEvent.press(getByText('进入阿衡'));

    expect(mockReplace).toHaveBeenCalledWith('/reva');
  });
});
