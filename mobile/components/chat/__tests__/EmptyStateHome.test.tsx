import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

import EmptyStateHome, {
  formatMemoryOpenerText,
  greetingForHour,
} from '../EmptyStateHome';

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

  it('renders the opening bubble: fused greeting + opener text + memory footnote inside', () => {
    const onOpenMemory = jest.fn();
    const onOpenerQuickReply = jest.fn();
    const opener = {
      text: '今天就是「提前晚餐」的检验日，做到了吗？',
      source: 'action_card_due',
      quick_replies: ['做到了'],
    } as any;

    const { getByText, getByLabelText } = render(
      <EmptyStateHome
        memoryOpener={[{ id: 1, type: 'allergy', type_label: '过敏', content: '对花粉过敏' }]}
        opener={opener}
        onOpenMemory={onOpenMemory}
        onOpenerQuickReply={onOpenerQuickReply}
      />,
    );

    // greeting is folded INTO the bubble as the first sentence + opener text follows.
    expect(getByText(/早上好|中午好|下午好|晚上好|夜深了/)).toBeTruthy();
    expect(getByText(/今天就是「提前晚餐」的检验日，做到了吗？/)).toBeTruthy();
    // memory footnote lives inside the bubble (sanitized text).
    expect(getByText('对花粉过敏')).toBeTruthy();

    // 校准 button reaches the memory calibration handler.
    fireEvent.press(getByLabelText('查看和校准 AI 记忆'));
    expect(onOpenMemory).toHaveBeenCalled();
  });

  it('renders quick replies below the bubble including a 换个话题 chip, all routed to onQuickReply', () => {
    const onOpenerQuickReply = jest.fn();
    const opener = {
      text: '今天就是「夜间血氧复盘」的检验日，做到了吗？',
      source: 'action_card_due',
      quick_replies: ['做到了 ✅', '没做 ❌'],
    } as any;

    const { getByLabelText } = render(
      <EmptyStateHome
        memoryOpener={[]}
        opener={opener}
        onOpenMemory={jest.fn()}
        onOpenerQuickReply={onOpenerQuickReply}
      />,
    );

    // opener-provided quick replies call onQuickReply with the RAW reply text.
    fireEvent.press(getByLabelText('一键回复: 做到了 ✅'));
    expect(onOpenerQuickReply).toHaveBeenCalledWith('做到了 ✅');
    fireEvent.press(getByLabelText('一键回复: 没做 ❌'));
    expect(onOpenerQuickReply).toHaveBeenCalledWith('没做 ❌');

    // appended 换个话题 chip routes through the SAME handler.
    fireEvent.press(getByLabelText('换个话题'));
    expect(onOpenerQuickReply).toHaveBeenCalledWith('换个话题');
  });

  it('omits the memory footnote when there is no memory', () => {
    const opener = {
      text: '今天就是「提前晚餐」的检验日，做到了吗？',
      source: 'action_card_due',
      quick_replies: ['做到了'],
    } as any;

    const { queryByLabelText, getByText } = render(
      <EmptyStateHome
        memoryOpener={[]}
        opener={opener}
        onOpenMemory={jest.fn()}
        onOpenerQuickReply={jest.fn()}
      />,
    );

    expect(getByText(/今天就是「提前晚餐」的检验日，做到了吗？/)).toBeTruthy();
    // No footnote / 校准 affordance when memory is absent.
    expect(queryByLabelText('查看和校准 AI 记忆')).toBeNull();
  });

  it('falls back to a memory-only bubble when opener is null but memory exists', () => {
    const onOpenMemory = jest.fn();
    const { getByText, getByLabelText } = render(
      <EmptyStateHome
        memoryOpener={[{ id: 1, type: 'medical', type_label: '医疗', content: '对花粉过敏' }]}
        opener={null}
        onOpenMemory={onOpenMemory}
        onOpenerQuickReply={jest.fn()}
      />,
    );

    expect(getByText('今天想从哪里开始？')).toBeTruthy();
    expect(getByText('对花粉过敏')).toBeTruthy();
    fireEvent.press(getByLabelText('查看和校准 AI 记忆'));
    expect(onOpenMemory).toHaveBeenCalled();
  });

  it('hides the memory bubble when cleanup leaves no sensible content (standalone greeting only)', () => {
    const { queryByLabelText, getByText } = render(
      <EmptyStateHome
        memoryOpener={[{ id: 1, type: 'medical', type_label: '医嘱', content: '{"x":"短"}' }]}
        opener={null}
        onOpenMemory={jest.fn()}
        onOpenerQuickReply={jest.fn()}
      />,
    );

    // No memory footnote/校准; only the standalone greeting block remains.
    expect(queryByLabelText('查看和校准 AI 记忆')).toBeNull();
    expect(getByText('今天想从哪里开始？')).toBeTruthy();
  });
});
