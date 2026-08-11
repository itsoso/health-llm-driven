/* eslint-disable import/first */
import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

jest.mock('@expo/vector-icons', () => ({ Ionicons: 'Ionicons' }));

import ChatTodayFocusCard from '../ChatTodayFocusCard';
import type { TodayFocusModel } from '../todayFocus';
import { revaColors as C, revaSemantic } from '../../../constants/revaTheme';

const focusModel = (withStrip = true): TodayFocusModel => ({
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
  contextStrip: withStrip ? {
    key: 'movement.recovery',
    label: '现在',
    title: '降低今天的训练强度',
    tone: 'normal',
    deepLink: '/fitness-plan',
  } : null,
});

describe('ChatTodayFocusCard', () => {
  it('renders nothing when there is no qualified context or Agent state', () => {
    const { queryByTestId, queryByText } = render(
      <ChatTodayFocusCard model={focusModel(false)} />,
    );

    expect(queryByTestId('chat-today-focus-card')).toBeNull();
    expect(queryByText('今日重点')).toBeNull();
  });

  it('renders a compact direct context strip without counts or an eyebrow', () => {
    const { getByText, getByTestId, queryByText, queryByTestId } = render(
      <ChatTodayFocusCard model={focusModel()} />,
    );

    expect(getByText('现在')).toBeTruthy();
    expect(getByText('降低今天的训练强度')).toBeTruthy();
    expect(queryByText('今日重点')).toBeNull();
    expect(queryByText(/接下来/)).toBeNull();
    expect(queryByText(/已完成/)).toBeNull();
    expect(queryByTestId('chat-today-focus-icon')).toBeNull();

    const style = StyleSheet.flatten(getByTestId('chat-today-focus-card').props.style);
    expect(style.borderRadius).toBeLessThanOrEqual(10);
    expect(style.minHeight).toBe(40);
    expect(style.shadowOpacity ?? 0).toBe(0);
    expect(getByText('降低今天的训练强度').props.numberOfLines).toBe(2);
  });

  it('renders caution context as a neutral rail with semantic color only on the accent', () => {
    const model = focusModel();
    model.contextStrip = {
      key: 'lab-review',
      label: '待处理',
      title: '复查血脂四项',
      tone: 'caution',
    };
    const { getByTestId, getByText } = render(
      <ChatTodayFocusCard model={model} />,
    );

    const stripStyle = StyleSheet.flatten(getByTestId('chat-today-focus-card').props.style);
    const accentStyle = StyleSheet.flatten(getByTestId('chat-today-focus-accent').props.style);
    expect(stripStyle.backgroundColor).toBe(C.surface2);
    expect(stripStyle.minHeight).toBe(40);
    expect(accentStyle.backgroundColor).toBe(revaSemantic.caution.fg);
    expect(StyleSheet.flatten(getByText('待处理').props.style)).toEqual(
      expect.objectContaining({ fontSize: 14, lineHeight: 19 }),
    );
    expect(StyleSheet.flatten(getByText('复查血脂四项').props.style)).toEqual(
      expect.objectContaining({ fontSize: 15, lineHeight: 20 }),
    );
  });

  it('opens Today and lets the parent dismiss an action without a launcher state', () => {
    const onOpenToday = jest.fn();
    const onDismiss = jest.fn();
    const { getByLabelText, queryByText } = render(
      <ChatTodayFocusCard
        model={focusModel()}
        onOpenToday={onOpenToday}
        onDismiss={onDismiss}
      />,
    );

    const openButton = getByLabelText('打开今日计划');
    expect(StyleSheet.flatten(openButton.props.style).minHeight).toBe(40);
    expect(openButton.props.hitSlop).toBe(4);
    fireEvent.press(openButton);
    expect(onOpenToday).toHaveBeenCalledTimes(1);
    const dismissButton = getByLabelText('关闭当前提示');
    expect(dismissButton.props.hitSlop).toBe(4);
    expect(StyleSheet.flatten(dismissButton.props.style)).toEqual(
      expect.objectContaining({ width: 40, height: 40 }),
    );
    fireEvent.press(dismissButton);
    expect(onDismiss).toHaveBeenCalledTimes(1);
    expect(queryByText('已隐藏，点此展开')).toBeNull();
  });

  it('shows one transient Agent status instead of the timeline context', () => {
    const { getByText, getByTestId, queryByText } = render(
      <ChatTodayFocusCard
        model={focusModel()}
        turnStatus={{ label: '正在整理你的饮食记录…', tone: 'active' }}
      />,
    );

    expect(getByText('正在整理你的饮食记录…')).toBeTruthy();
    expect(queryByText('降低今天的训练强度')).toBeNull();
    expect(queryByText('今日重点')).toBeNull();
    expect(getByTestId('chat-today-focus-card').props.accessibilityLiveRegion).toBe('polite');
  });

  it('keeps a high-severity context visible above an active Agent turn', () => {
    const model = focusModel();
    model.contextStrip = {
      key: 'safety-1',
      label: '需要关注',
      title: '恢复状态明显下降',
      tone: 'risk',
    };
    const { getByText, getByTestId, queryByText } = render(
      <ChatTodayFocusCard
        model={model}
        turnStatus={{ label: '正在整理你的饮食记录…', tone: 'active' }}
      />,
    );

    expect(getByText('恢复状态明显下降')).toBeTruthy();
    expect(queryByText('正在整理你的饮食记录…')).toBeNull();
    expect(getByTestId('chat-today-focus-icon')).toBeTruthy();
  });

  it('keeps a recoverable Agent failure visible with a retry command', () => {
    const onRetry = jest.fn();
    const { getByText, getByLabelText } = render(
      <ChatTodayFocusCard
        model={focusModel(false)}
        turnStatus={{ label: '网络中断，内容已保留', tone: 'error', retryable: true }}
        onRetry={onRetry}
      />,
    );

    expect(getByText('网络中断，内容已保留')).toBeTruthy();
    fireEvent.press(getByLabelText('重试上一轮'));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
