import React from 'react';
import { FlatList } from 'react-native';
import { render, fireEvent, waitFor } from '@testing-library/react-native';

import ConversationSheet from '../ConversationSheet';

const baseProps = {
  visible: true,
  onClose: jest.fn(),
  setConversations: jest.fn(),
  currentConversationId: undefined,
  onSelectConversation: jest.fn(),
  onDeleteConversation: jest.fn(),
};

describe('ConversationSheet pinning', () => {
  it('renames a conversation title inline', async () => {
    const onRenameConversation = jest.fn().mockResolvedValue(undefined);
    const conversations = [
      { id: 415, title: '分析我最近的代谢健康', created_at: '2026-04-25T01:00:00Z', updated_at: '2026-04-25T15:00:00Z' },
    ];

    const { getByLabelText } = render(
      <ConversationSheet
        {...baseProps}
        conversations={conversations as any}
        onRenameConversation={onRenameConversation}
      />
    );

    fireEvent.press(getByLabelText('重命名对话'));
    fireEvent.changeText(getByLabelText('对话标题'), '最近代谢复盘');
    fireEvent.press(getByLabelText('保存标题'));

    await waitFor(() => {
      expect(onRenameConversation).toHaveBeenCalledWith(415, '最近代谢复盘');
    });
  });

  it('pins per-day briefings to top sorted by updated_at desc', () => {
    const conversations = [
      // 一条普通的、updated_at 最新的对话
      { id: 391, title: '记录饮食', created_at: '2026-04-25T18:02:00Z', updated_at: '2026-04-25T18:04:00Z' },
      // 简报对话: 03-31 老格式 + 多条按日期切片的新格式
      { id: 408, title: '每日健康简报 · 04-16', created_at: '2026-04-15T17:01:00Z', updated_at: '2026-04-15T17:32:00Z' },
      { id: 415, title: '每日健康简报 · 04-25', created_at: '2026-04-25T01:01:00Z', updated_at: '2026-04-25T15:01:00Z' },
      { id: 412, title: '每日健康简报 · 04-21', created_at: '2026-04-21T01:01:00Z', updated_at: '2026-04-21T15:04:00Z' },
      // 一条周报
      { id: 200, title: '每周健康周报 · w17', created_at: '2026-04-20T09:00:00Z', updated_at: '2026-04-20T09:00:00Z' },
      // 一条尾部空白的旧简报 (验证 trim)
      { id: 134, title: '每日健康简报 ', created_at: '2026-03-31T08:00:00Z', updated_at: '2026-03-31T08:00:00Z' },
    ];

    const { getAllByRole } = render(
      <ConversationSheet {...baseProps} conversations={conversations as any} />
    );

    // 第一个 button 是 row, 删除按钮是嵌套 button. 用 accessibilityLabel 区分.
    const rows = getAllByRole('button').filter((node: any) =>
      typeof node.props.accessibilityLabel === 'string' &&
      node.props.accessibilityLabel.startsWith('对话:')
    );
    const labels = rows.map((r: any) => r.props.accessibilityLabel);

    // 简报应在最前 4 条 (4-25, 4-21, 4-16, 03-31 按 updated_at desc)
    expect(labels[0]).toBe('对话: 每日健康简报 · 04-25');
    expect(labels[1]).toBe('对话: 每日健康简报 · 04-21');
    expect(labels[2]).toBe('对话: 每日健康简报 · 04-16');
    expect(labels[3]).toBe('对话: 每日健康简报 ');
    // 周报紧随其后
    expect(labels[4]).toBe('对话: 每周健康周报 · w17');
    // 普通对话在末尾
    expect(labels[5]).toBe('对话: 记录饮食');
  });

  it('falls back to created_at if updated_at missing', () => {
    const conversations = [
      { id: 1, title: '每日健康简报 · 04-20', created_at: '2026-04-20T01:00:00Z' },
      { id: 2, title: '每日健康简报 · 04-25', created_at: '2026-04-25T01:00:00Z' },
    ];

    const { getAllByRole } = render(
      <ConversationSheet {...baseProps} conversations={conversations as any} />
    );

    const rows = getAllByRole('button').filter((n: any) =>
      typeof n.props.accessibilityLabel === 'string' &&
      n.props.accessibilityLabel.startsWith('对话:')
    );
    expect(rows[0].props.accessibilityLabel).toBe('对话: 每日健康简报 · 04-25');
    expect(rows[1].props.accessibilityLabel).toBe('对话: 每日健康简报 · 04-20');
  });

  it('invokes onSelectConversation with the row id', () => {
    const onSelect = jest.fn();
    const conversations = [
      { id: 415, title: '每日健康简报 · 04-25', created_at: '2026-04-25T01:00:00Z', updated_at: '2026-04-25T15:00:00Z' },
    ];

    const { getByLabelText } = render(
      <ConversationSheet {...baseProps} onSelectConversation={onSelect} conversations={conversations as any} />
    );
    fireEvent.press(getByLabelText('对话: 每日健康简报 · 04-25'));
    expect(onSelect).toHaveBeenCalledWith(415);
  });

  it('shows updated_at as the displayed date (not original created_at)', () => {
    const conversations = [
      // 简报老格式: created_at 03-31, 但 updated_at 是今天
      { id: 135, title: '每日健康简报', created_at: '2026-03-31T02:59:00Z', updated_at: '2026-04-25T15:01:00Z' },
    ];

    const { getByText } = render(
      <ConversationSheet {...baseProps} conversations={conversations as any} />
    );
    expect(getByText('2026-04-25')).toBeTruthy();
  });
});

// 生成一页普通对话 (非置顶, 保持相对顺序稳定)
function makeConvs(ids: number[]) {
  return ids.map(id => ({
    id,
    title: `对话 ${id}`,
    created_at: '2026-04-25T01:00:00Z',
    updated_at: '2026-04-25T01:00:00Z',
  }));
}

const firePageEnd = (renderResult: any) => {
  const list = renderResult.UNSAFE_getByType(FlatList);
  list.props.onEndReached({ distanceFromEnd: 0 });
};

describe('ConversationSheet 无限下拉分页', () => {
  it('onEndReached 在 hasMore 且未加载时触发 onLoadMore', () => {
    const onLoadMore = jest.fn();
    const rr = render(
      <ConversationSheet
        {...baseProps}
        conversations={makeConvs([1, 2, 3]) as any}
        hasMore
        loadingMore={false}
        loadMoreError={false}
        onLoadMore={onLoadMore}
        total={57}
      />
    );
    firePageEnd(rr);
    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });

  it('end-guard: 已全部加载 (hasMore=false) 时 onEndReached 不越界', () => {
    const onLoadMore = jest.fn();
    const rr = render(
      <ConversationSheet
        {...baseProps}
        conversations={makeConvs([1, 2, 3]) as any}
        hasMore={false}
        loadingMore={false}
        onLoadMore={onLoadMore}
        total={3}
      />
    );
    firePageEnd(rr);
    expect(onLoadMore).not.toHaveBeenCalled();
  });

  it('end-guard: 正在加载中 (loadingMore) 时 onEndReached 不重复触发', () => {
    const onLoadMore = jest.fn();
    const rr = render(
      <ConversationSheet
        {...baseProps}
        conversations={makeConvs([1, 2, 3]) as any}
        hasMore
        loadingMore
        onLoadMore={onLoadMore}
        total={57}
      />
    );
    firePageEnd(rr);
    expect(onLoadMore).not.toHaveBeenCalled();
  });

  it('end-guard: 处于加载失败态时 onEndReached 不自动重试 (等用户点重试)', () => {
    const onLoadMore = jest.fn();
    const rr = render(
      <ConversationSheet
        {...baseProps}
        conversations={makeConvs([1, 2, 3]) as any}
        hasMore
        loadingMore={false}
        loadMoreError
        onLoadMore={onLoadMore}
        total={57}
      />
    );
    firePageEnd(rr);
    expect(onLoadMore).not.toHaveBeenCalled();
  });

  it('append: 追加下一页后所有行都渲染, 顺序不打乱', () => {
    const rr = render(
      <ConversationSheet
        {...baseProps}
        conversations={makeConvs([1, 2, 3]) as any}
        hasMore
        total={6}
      />
    );
    // 追加第二页
    rr.rerender(
      <ConversationSheet
        {...baseProps}
        conversations={makeConvs([1, 2, 3, 4, 5, 6]) as any}
        hasMore={false}
        total={6}
      />
    );
    const rows = rr
      .getAllByRole('button')
      .filter((n: any) => typeof n.props.accessibilityLabel === 'string' && n.props.accessibilityLabel.startsWith('对话:'));
    const labels = rows.map((r: any) => r.props.accessibilityLabel);
    expect(labels).toEqual([
      '对话: 对话 1', '对话: 对话 2', '对话: 对话 3',
      '对话: 对话 4', '对话: 对话 5', '对话: 对话 6',
    ]);
  });

  it('footer: 全部加载完且总数超过一页时显示 "没有更多了"', () => {
    const rr = render(
      <ConversationSheet
        {...baseProps}
        conversations={makeConvs([1, 2, 3]) as any}
        hasMore={false}
        total={25}
      />
    );
    expect(rr.getByText('没有更多了')).toBeTruthy();
  });

  it('footer: 总数不足一页 (total<=20) 时不显示 "没有更多了"', () => {
    const rr = render(
      <ConversationSheet
        {...baseProps}
        conversations={makeConvs([1, 2, 3]) as any}
        hasMore={false}
        total={3}
      />
    );
    expect(rr.queryByText('没有更多了')).toBeNull();
  });

  it('footer: 加载失败显示 "加载失败，点击重试" 且点击调用 onLoadMore', () => {
    const onLoadMore = jest.fn();
    const rr = render(
      <ConversationSheet
        {...baseProps}
        conversations={makeConvs([1, 2, 3]) as any}
        hasMore
        loadMoreError
        onLoadMore={onLoadMore}
        total={57}
      />
    );
    fireEvent.press(rr.getByLabelText('加载失败，点击重试'));
    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });
});
