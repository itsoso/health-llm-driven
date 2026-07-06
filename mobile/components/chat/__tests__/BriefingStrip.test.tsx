import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';

const mockNavigate = jest.fn();
jest.mock('expo-router', () => ({
  router: { navigate: (...args: any[]) => mockNavigate(...args) },
}));
jest.mock('@expo/vector-icons', () => ({ Ionicons: 'Ionicons' }));

import BriefingStrip, { buildBriefingSummary } from '../BriefingStrip';

describe('BriefingStrip', () => {
  beforeEach(() => jest.clearAllMocks());

  it('shows the dismiss button when onDismiss is provided and calls it on press (not navigate)', () => {
    const onDismiss = jest.fn();
    const { getByLabelText } = render(
      <BriefingStrip timeline={undefined} onDismiss={onDismiss} />,
    );
    fireEvent.press(getByLabelText('关闭今日简报'));
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('hides the dismiss button when onDismiss is absent', () => {
    const { queryByLabelText } = render(<BriefingStrip timeline={undefined} />);
    expect(queryByLabelText('关闭今日简报')).toBeNull();
  });

  it('strip body opens the today half-sheet (formSheet over chat, not a full nav away)', () => {
    const { getByLabelText } = render(
      <BriefingStrip timeline={undefined} onDismiss={jest.fn()} />,
    );
    fireEvent.press(getByLabelText('今日简报：查看今日待办与身体信号'));
    expect(mockNavigate).toHaveBeenCalledWith('/today-sheet');
  });

  it('buildBriefingSummary uses only real counts and neutral fallbacks', () => {
    expect(buildBriefingSummary(undefined)).toBe('查看今日待办与身体信号');
    expect(
      buildBriefingSummary({ counts: { actionable: 3 }, past: { completed_count: 2 } } as any),
    ).toBe('3 项待办 · 2 项已完成');
    expect(
      buildBriefingSummary({ counts: { actionable: 0 }, past: { completed_count: 0 } } as any),
    ).toBe('今天暂无待办 · 查看身体信号');
  });
});
