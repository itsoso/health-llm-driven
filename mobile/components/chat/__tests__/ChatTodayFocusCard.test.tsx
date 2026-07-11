import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

jest.mock('@expo/vector-icons', () => ({ Ionicons: 'Ionicons' }));

import ChatTodayFocusCard from '../ChatTodayFocusCard';
import type { TodayFocusModel } from '../todayFocus';

const focusModel = (): TodayFocusModel => ({
  emptyTitle: '今日暂无重点行动',
  primary: {
    key: 'movement.recovery',
    source: 'daily_plan',
    title: '恢复/休息：暂停高强度',
    reason: '昨晚恢复不足，今天优先降低训练负荷。',
    deepLink: '/fitness-plan',
    evidence: ['睡眠恢复偏弱', 'HRV 低于近期基线'],
    verification: ['今晚睡眠', '主观疲劳'],
  },
  status: {
    actionable: 3,
    completed: 1,
    overdue: 0,
  },
});

describe('ChatTodayFocusCard', () => {
  it('renders one compact primary action with real status counts', () => {
    const { getByText, getByTestId } = render(
      <ChatTodayFocusCard model={focusModel()} />,
    );

    expect(getByText('现在最重要')).toBeTruthy();
    expect(getByText('恢复/休息：暂停高强度')).toBeTruthy();
    expect(getByText('昨晚恢复不足，今天优先降低训练负荷。')).toBeTruthy();
    expect(getByText('接下来 3')).toBeTruthy();
    expect(getByText('已完成 1')).toBeTruthy();

    const rootStyle = StyleSheet.flatten(getByTestId('chat-today-focus-card').props.style);
    expect(rootStyle.marginHorizontal).toBeGreaterThanOrEqual(12);
    expect(rootStyle.paddingVertical).toBeLessThanOrEqual(14);
  });

  it('routes execute and ask actions to the parent with the selected primary action', () => {
    const onExecute = jest.fn();
    const onAsk = jest.fn();
    const model = focusModel();
    const { getByLabelText } = render(
      <ChatTodayFocusCard model={model} onExecute={onExecute} onAsk={onAsk} />,
    );

    fireEvent.press(getByLabelText('执行今日重点：恢复/休息：暂停高强度'));
    expect(onExecute).toHaveBeenCalledWith(model.primary);

    fireEvent.press(getByLabelText('问小巴：恢复/休息：暂停高强度'));
    expect(onAsk).toHaveBeenCalledWith(model.primary);
  });

  it('expands evidence and verification only after tapping why', () => {
    const { getByLabelText, getByText, queryByText } = render(
      <ChatTodayFocusCard model={focusModel()} />,
    );

    expect(queryByText('依据')).toBeNull();
    fireEvent.press(getByLabelText('查看今日重点依据'));
    expect(getByText('依据')).toBeTruthy();
    expect(getByText('睡眠恢复偏弱')).toBeTruthy();
    expect(getByText('验证')).toBeTruthy();
    expect(getByText('今晚睡眠')).toBeTruthy();
  });

  it('shows an honest empty state when no primary action exists', () => {
    const onOpenToday = jest.fn();
    const { getByText, getByLabelText, queryByLabelText } = render(
      <ChatTodayFocusCard
        model={{
          emptyTitle: '今日暂无重点行动',
          primary: null,
          status: { actionable: 0, completed: 0, overdue: 0 },
        }}
        onOpenToday={onOpenToday}
      />,
    );

    expect(getByText('今日暂无重点行动')).toBeTruthy();
    expect(queryByLabelText(/执行今日重点/)).toBeNull();
    fireEvent.press(getByLabelText('打开今日详情'));
    expect(onOpenToday).toHaveBeenCalledTimes(1);
  });

  it('renders a stable single-line compact variant during an active conversation', () => {
    const { getByText, getByLabelText, queryByText, queryByLabelText } = render(
      <ChatTodayFocusCard model={focusModel()} variant="compact" />,
    );

    expect(getByLabelText('今日重点，已收起')).toBeTruthy();
    expect(getByText('恢复/休息：暂停高强度')).toBeTruthy();
    expect(getByText('接下来 3 · 已完成 1')).toBeTruthy();
    expect(queryByText('昨晚恢复不足，今天优先降低训练负荷。')).toBeNull();
    expect(queryByLabelText(/执行今日重点/)).toBeNull();
    expect(queryByLabelText(/问小巴/)).toBeNull();
  });

  it('shows one Agent turn status line and a retry command for recoverable failures', () => {
    const onRetry = jest.fn();
    const { getByText, getByLabelText } = render(
      <ChatTodayFocusCard
        model={focusModel()}
        variant="compact"
        turnStatus={{ label: '网络中断，已保留内容', tone: 'error', retryable: true }}
        onRetry={onRetry}
      />,
    );

    expect(getByText('网络中断，已保留内容')).toBeTruthy();
    fireEvent.press(getByLabelText('重试上一轮'));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
