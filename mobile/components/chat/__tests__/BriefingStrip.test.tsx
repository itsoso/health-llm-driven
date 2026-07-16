import React from 'react';
import { StyleSheet } from 'react-native';
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

  it('falls back to the today half-sheet nav only when no onPress is provided (back-compat)', () => {
    const { getByLabelText } = render(
      <BriefingStrip timeline={undefined} onDismiss={jest.fn()} />,
    );
    fireEvent.press(getByLabelText('今日简报：查看今日待办与身体信号'));
    expect(mockNavigate).toHaveBeenCalledWith('/today-sheet');
  });

  it('agent-native: onPress toggles inline expand instead of navigating to a page', () => {
    const onPress = jest.fn();
    const { getByLabelText } = render(
      <BriefingStrip timeline={undefined} onPress={onPress} expanded={false} />,
    );
    fireEvent.press(getByLabelText('今日简报：查看今日待办与身体信号'));
    expect(onPress).toHaveBeenCalledTimes(1);
    expect(mockNavigate).not.toHaveBeenCalled(); // 不跳独立页
  });

  it('reflects expanded state on the accessibility node', () => {
    const { getByLabelText } = render(
      <BriefingStrip timeline={undefined} onPress={jest.fn()} expanded />,
    );
    const node = getByLabelText('今日简报：查看今日待办与身体信号');
    expect(node.props.accessibilityState?.expanded).toBe(true);
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

  it('uses a compact editorial strip instead of a floating card', () => {
    const { getByTestId } = render(
      <BriefingStrip timeline={undefined} onDismiss={jest.fn()} />,
    );

    const style = StyleSheet.flatten(getByTestId('briefing-strip').props.style);
    expect(style.borderRadius).toBeLessThanOrEqual(10);
    expect(style.paddingVertical).toBeLessThanOrEqual(7);
    expect(style.shadowOpacity ?? 0).toBe(0);
  });
});
