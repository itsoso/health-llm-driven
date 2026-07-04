import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

import EmptyStateHome, {
  formatMemoryOpenerText,
  greetingForHour,
  type EmptyStateSuggestion,
} from '../EmptyStateHome';

jest.mock('../OpenerCard', () => {
  const React = require('react');
  const { Pressable, Text } = require('react-native');
  const MockOpenerCard = ({ opener, onQuickReply }: any) => (
    <Pressable accessibilityLabel="opener-card" onPress={() => onQuickReply(opener.quick_replies[0])}>
      <Text>{opener.text}</Text>
    </Pressable>
  );
  MockOpenerCard.displayName = 'MockOpenerCard';
  return MockOpenerCard;
});

const suggestions: EmptyStateSuggestion[] = [
  { icon: 'moon-outline', text: '分析我的睡眠质量', key: 'sleep', priority: 10 },
  { icon: 'fitness-outline', text: '给我运动建议', key: 'exercise', priority: 8 },
];

describe('EmptyStateHome', () => {
  it('maps local hour to lightweight greeting text', () => {
    expect(greetingForHour(4)).toBe('夜深了');
    expect(greetingForHour(8)).toBe('早上好');
    expect(greetingForHour(12)).toBe('中午好');
    expect(greetingForHour(15)).toBe('下午好');
    expect(greetingForHour(21)).toBe('晚上好');
  });

  it('sanitizes leaked JSON fragments before rendering memory opener copy', () => {
    expect(formatMemoryOpenerText([
      { id: 1, type: 'medical', type_label: '医嘱', content: '"建议":"鼻炎发作时优先生理盐水冲洗。", "注意事项": "避免连续使用喷剂。"' },
    ])).toBe('鼻炎发作时优先生理盐水冲洗。 避免连续使用喷剂。');
  });

  it('renders memory, opener and starter suggestions with explicit handlers', () => {
    const onOpenMemory = jest.fn();
    const onOpenerQuickReply = jest.fn();
    const onSuggestionPress = jest.fn();
    const opener = {
      text: '今天就是「提前晚餐」的检验日，做到了吗？',
      source: 'action_card_due',
      quick_replies: ['做到了'],
    } as any;

    const { getByText, getByLabelText } = render(
      <EmptyStateHome
        memoryOpener={[{ id: 1, type: 'allergy', type_label: '过敏', content: '对花粉过敏' }]}
        opener={opener}
        suggestions={suggestions}
        onOpenMemory={onOpenMemory}
        onOpenerQuickReply={onOpenerQuickReply}
        onSuggestionPress={onSuggestionPress}
      />,
    );

    expect(getByText('今天想从哪里开始？')).toBeTruthy();
    expect(getByText('对花粉过敏')).toBeTruthy();
    expect(getByText('今天就是「提前晚餐」的检验日，做到了吗？')).toBeTruthy();

    fireEvent.press(getByLabelText('查看和校准 AI 记忆'));
    expect(onOpenMemory).toHaveBeenCalled();

    fireEvent.press(getByText('分析我的睡眠质量'));
    expect(onSuggestionPress).toHaveBeenCalledWith(suggestions[0], 0);

    fireEvent.press(getByLabelText('opener-card'));
    expect(onOpenerQuickReply).toHaveBeenCalledWith('做到了');
  });

  it('hides the memory card when cleanup leaves no sensible content', () => {
    const { queryByText } = render(
      <EmptyStateHome
        memoryOpener={[{ id: 1, type: 'medical', type_label: '医嘱', content: '{"x":"短"}' }]}
        opener={null}
        suggestions={suggestions}
        onOpenMemory={jest.fn()}
        onOpenerQuickReply={jest.fn()}
        onSuggestionPress={jest.fn()}
      />,
    );

    expect(queryByText('记忆线索')).toBeNull();
  });
});
