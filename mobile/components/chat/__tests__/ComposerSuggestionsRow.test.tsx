import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import ComposerSuggestionsRow from '../ComposerSuggestionsRow';

it('removes the retired photo entry and duplicates before choosing visible prompts', () => {
  const onPress = jest.fn();
  const suggestion = (text: string, key: string) => ({ text, key, priority: 10, icon: 'sparkles-outline' as const });
  const view = render(<ComposerSuggestionsRow suggestions={[
    suggestion('拍照记一餐', 'legacy-photo'),
    suggestion(' 聊聊今天的状态 ', 'state'),
    suggestion('聊聊今天的状态', 'duplicate'),
    suggestion('聊聊今天的饮食', 'diet'),
    suggestion('第三个话题', 'third'),
  ]} onSuggestionPress={onPress} />);
  expect(view.queryByLabelText('拍照记一餐')).toBeNull();
  expect(view.queryByText('拍照记一餐')).toBeNull();
  expect(view.getAllByText('聊聊今天的状态')).toHaveLength(1);
  expect(view.queryByText('第三个话题')).toBeNull();
  fireEvent.press(view.getByLabelText('向小气候提问: 聊聊今天的饮食'));
  expect(onPress).toHaveBeenCalledWith(expect.objectContaining({ key: 'diet' }), 1);
});

it('renders no empty suggestion strip', () => {
  const view = render(<ComposerSuggestionsRow suggestions={[]} onSuggestionPress={jest.fn()} />);
  expect(view.toJSON()).toBeNull();
});

it('trims only display text and preserves the original suggestion callback payload', () => {
  const original = { text: ' 聊聊今天的状态 ', key: 'state', priority: 10, icon: 'sparkles-outline' as const };
  const onPress = jest.fn();
  const view = render(<ComposerSuggestionsRow suggestions={[original]} onSuggestionPress={onPress} />);
  fireEvent.press(view.getByLabelText('向小气候提问: 聊聊今天的状态'));
  expect(onPress.mock.calls[0][0]).toBe(original);
  expect(onPress).toHaveBeenCalledWith(original, 0);
});
