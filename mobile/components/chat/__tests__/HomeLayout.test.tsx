import React from 'react';
import { act, fireEvent, render } from '@testing-library/react-native';
import { AppState, StyleSheet } from 'react-native';
import EmptyStateHome from '../EmptyStateHome';

const base = {
  memoryOpener: [], opener: null,
  onOpenMemory: jest.fn(), onOpenerQuickReply: jest.fn(), onQuickAction: jest.fn(),
};

it('gives the home greeting a heading and does not truncate long opening content', () => {
  const text = '这是一条需要完整阅读的开场说明。'.repeat(12);
  const view = render(<EmptyStateHome {...base} opener={{ text, quick_replies: [], source: 'memory_fact', priority: 5 }} />);
  expect(view.getByRole('header')).toBeTruthy();
  expect(view.getByText(text).props.numberOfLines).toBeUndefined();
});

it('keeps an accessible touch target for each opener reply', () => {
  const view = render(<EmptyStateHome {...base} opener={{ text: '从这里继续',
    quick_replies: [{ text: '做到了' }, { text: '调整计划' }], source: 'memory_fact', priority: 5 }} />);
  for (const label of ['一键回复: 做到了', '一键回复: 调整计划', '换个话题']) {
    expect(StyleSheet.flatten(view.getByLabelText(label).props.style).minHeight).toBeGreaterThanOrEqual(44);
  }
  fireEvent.press(view.getByLabelText('一键回复: 做到了'));
  expect(base.onOpenerQuickReply).toHaveBeenCalledWith('做到了');
});

it('removes retired photo shortcuts from old opener payloads while preserving other actions', () => {
  const action = jest.fn();
  const view = render(<EmptyStateHome {...base} onQuickAction={action} opener={{ text: '从这里开始',
    quick_replies: [{ text: '拍照记一餐', action: 'photo_meal' }, { text: '拍照记录一餐' },
      { text: '记录体重', action: 'record_weight' }], source: 'memory_fact', priority: 5 }} />);
  expect(view.queryByText(/拍照/)).toBeNull();
  fireEvent.press(view.getByLabelText('一键回复: 记录体重'));
  expect(action).toHaveBeenCalledWith('record_weight');
});

it('keeps onboarding actions out of the tree while the keyboard owns the viewport', () => {
  const view = render(<EmptyStateHome {...base} onboarding showReplyActions={false} />);
  expect(view.queryByLabelText('记录体重')).toBeNull();
  expect(view.queryByLabelText('连接设备')).toBeNull();
});

it('keeps fresh conversations independent of old personal context', () => {
  const view = render(<EmptyStateHome {...base} freshStart
    memoryOpener={[{ id: 1, type: 'medical', type_label: '医疗', content: '合成旧记忆' }]}
    opener={{ text: '合成旧开场', quick_replies: [], source: 'memory_fact', priority: 5 }} />);
  expect(view.queryByText(/合成旧/)).toBeNull();
  expect(view.queryByLabelText('拍照记一餐')).toBeNull();
  expect(view.getByLabelText('记录体重')).toBeTruthy();
});

it('refreshes neutral greeting on time and foreground changes without sending a message', () => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date(2026, 10, 5, 10, 59, 30));
  const remove = jest.fn();
  let foreground: (state: 'active') => void = () => {};
  const spy = jest.spyOn(AppState, 'addEventListener').mockImplementation((_event, callback) => {
    foreground = callback;
    return { remove };
  });
  const send = jest.fn();
  const view = render(<EmptyStateHome {...base} freshStart onOpenerQuickReply={send} />);
  try {
    expect(view.getByText('早上好')).toBeTruthy();
    act(() => jest.advanceTimersByTime(60_000));
    expect(view.getByText('中午好')).toBeTruthy();
    act(() => {
      jest.setSystemTime(new Date(2026, 10, 5, 19));
      foreground('active');
    });
    expect(view.getByText('晚上好')).toBeTruthy();
    expect(send).not.toHaveBeenCalled();
  } finally {
    view.unmount();
    expect(remove).toHaveBeenCalledTimes(1);
    expect(jest.getTimerCount()).toBe(0);
    spy.mockRestore();
    jest.useRealTimers();
  }
});
