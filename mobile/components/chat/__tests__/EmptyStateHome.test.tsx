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

  it('renders the opening bubble with a quiet memory source affordance', () => {
    const onOpenMemory = jest.fn();
    const onOpenerQuickReply = jest.fn();
    const opener = {
      text: '今天就是「提前晚餐」的检验日，做到了吗？',
      source: 'action_card_due',
      quick_replies: [{ text: '做到了' }],
    } as any;

    const { getByText, getByLabelText, queryByText } = render(
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
    // The opener keeps provenance without embedding another body paragraph.
    expect(queryByText('对花粉过敏')).toBeNull();
    expect(getByText('依据 1 条过敏')).toBeTruthy();

    // 校准 button reaches the memory calibration handler.
    fireEvent.press(getByLabelText('查看和校准 AI 记忆'));
    expect(onOpenMemory).toHaveBeenCalled();
  });

  it('renders 小巴 as a branded assistant avatar in the opening bubble', () => {
    const opener = {
      text: '今天就是「提前晚餐」的检验日，做到了吗？',
      source: 'action_card_due',
      quick_replies: [{ text: '做到了' }],
    } as any;

    const { getByLabelText } = render(
      <EmptyStateHome
        memoryOpener={[]}
        opener={opener}
        onOpenMemory={jest.fn()}
        onOpenerQuickReply={jest.fn()}
      />,
    );

    expect(getByLabelText('小巴形象')).toBeTruthy();
  });

  it('renders quick replies below the bubble including a 换个话题 chip, all routed to onQuickReply', () => {
    const onOpenerQuickReply = jest.fn();
    const opener = {
      text: '今天就是「夜间血氧复盘」的检验日，做到了吗？',
      source: 'action_card_due',
      quick_replies: [{ text: '做到了 ✅' }, { text: '没做 ❌' }],
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

  it('deduplicates semantically equivalent opener replies after label normalization', () => {
    const opener = {
      text: '今晚按计划完成了吗？',
      source: 'action_card_due',
      quick_replies: [
        { text: '做到了' },
        { text: '已经完成' },
        { text: '调整计划' },
      ],
    } as any;

    const { getAllByText, getByLabelText, queryByLabelText } = render(
      <EmptyStateHome
        memoryOpener={[]}
        opener={opener}
        onOpenMemory={jest.fn()}
        onOpenerQuickReply={jest.fn()}
      />,
    );

    expect(getAllByText('完成了')).toHaveLength(1);
    expect(getByLabelText('一键回复: 做到了')).toBeTruthy();
    expect(queryByLabelText('一键回复: 已经完成')).toBeNull();
    expect(getByLabelText('换个话题')).toBeTruthy();
  });

  it('caps opener actions at three and does not append 换个话题 when the group is full', () => {
    const opener = {
      text: '现在想从哪一步开始？',
      source: 'action_card_due',
      quick_replies: [
        { text: '做到了' },
        { text: '没做' },
        { text: '调整计划' },
        { text: '稍后再说' },
      ],
    } as any;

    const { getByLabelText, queryByLabelText } = render(
      <EmptyStateHome
        memoryOpener={[]}
        opener={opener}
        onOpenMemory={jest.fn()}
        onOpenerQuickReply={jest.fn()}
      />,
    );

    expect(getByLabelText('一键回复: 做到了')).toBeTruthy();
    expect(getByLabelText('一键回复: 没做')).toBeTruthy();
    expect(getByLabelText('一键回复: 调整计划')).toBeTruthy();
    expect(queryByLabelText('一键回复: 稍后再说')).toBeNull();
    expect(queryByLabelText('换个话题')).toBeNull();
  });

  it('removes opener reply actions from the tree when the keyboard owns the viewport', () => {
    const opener = {
      text: '今晚按计划完成了吗？',
      source: 'action_card_due',
      quick_replies: [{ text: '做到了' }, { text: '调整计划' }],
    } as any;

    const { queryByLabelText } = render(
      <EmptyStateHome
        memoryOpener={[]}
        opener={opener}
        onOpenMemory={jest.fn()}
        onOpenerQuickReply={jest.fn()}
        showReplyActions={false}
      />,
    );

    expect(queryByLabelText('一键回复: 做到了')).toBeNull();
    expect(queryByLabelText('一键回复: 调整计划')).toBeNull();
    expect(queryByLabelText('换个话题')).toBeNull();
  });

  it('omits the memory footnote when there is no memory', () => {
    const opener = {
      text: '今天就是「提前晚餐」的检验日，做到了吗？',
      source: 'action_card_due',
      quick_replies: [{ text: '做到了' }],
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
    expect(getByText('记忆 · 医疗')).toBeTruthy();
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

  // ── 冷启动包 (P0-3) ─────────────────────────────────────────────────────
  it('routes an action quick reply to onQuickAction (not onOpenerQuickReply)', () => {
    const onOpenerQuickReply = jest.fn();
    const onQuickAction = jest.fn();
    const opener = {
      text: '欢迎！先从这三件事之一开始。',
      source: 'memory_fact',
      quick_replies: [
        { text: '拍照记一餐', action: 'photo_meal' },
        { text: '做到了' },
      ],
    } as any;

    const { getByLabelText } = render(
      <EmptyStateHome
        memoryOpener={[]}
        opener={opener}
        onOpenMemory={jest.fn()}
        onOpenerQuickReply={onOpenerQuickReply}
        onboarding
        onQuickAction={onQuickAction}
      />,
    );

    // action reply → 本地导航 handler, 不发文本。
    fireEvent.press(getByLabelText('一键回复: 拍照记一餐'));
    expect(onQuickAction).toHaveBeenCalledWith('photo_meal');
    expect(onOpenerQuickReply).not.toHaveBeenCalledWith('拍照记一餐');

    // 同一 opener 里无 action 的 reply 仍走既有发送路径。
    fireEvent.press(getByLabelText('一键回复: 做到了'));
    expect(onOpenerQuickReply).toHaveBeenCalledWith('做到了');
  });

  it('renders the Quick Start card in the third state (onboarding, no opener, no memory)', () => {
    const onQuickAction = jest.fn();
    const { getByLabelText, queryByText } = render(
      <EmptyStateHome
        memoryOpener={[]}
        opener={null}
        onOpenMemory={jest.fn()}
        onOpenerQuickReply={jest.fn()}
        onboarding
        onQuickAction={onQuickAction}
      />,
    );

    // 三个首次价值动作都在, 点击各走对应 action。
    fireEvent.press(getByLabelText('拍照记一餐'));
    expect(onQuickAction).toHaveBeenCalledWith('photo_meal');
    fireEvent.press(getByLabelText('记录体重'));
    expect(onQuickAction).toHaveBeenCalledWith('record_weight');
    fireEvent.press(getByLabelText('连接设备'));
    expect(onQuickAction).toHaveBeenCalledWith('connect_device');
    // 冷启动第三态用卡替代 greeting-only, 不再只剩一句问候。
    expect(queryByText('今天想从哪里开始？')).toBeNull();
  });

  it('keeps greeting-only third state when not onboarding (no Quick Start card)', () => {
    const { queryByLabelText, getByText } = render(
      <EmptyStateHome
        memoryOpener={[]}
        opener={null}
        onOpenMemory={jest.fn()}
        onOpenerQuickReply={jest.fn()}
        onboarding={false}
      />,
    );

    // 非冷启动 → 保持只有问候块, 不出 Quick Start 卡。
    expect(getByText('今天想从哪里开始？')).toBeTruthy();
    expect(queryByLabelText('记录体重')).toBeNull();
    expect(queryByLabelText('连接设备')).toBeNull();
  });
});
