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

describe('ConversationSheet canonical server order', () => {
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

  it('preserves backend order instead of applying Mobile-only briefing pinning', () => {
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

    expect(labels).toEqual([
      '对话: 记录饮食',
      '对话: 每日健康简报 · 04-16',
      '对话: 每日健康简报 · 04-25',
      '对话: 每日健康简报 · 04-21',
      '对话: 每周健康周报 · w17',
      '对话: 每日健康简报 ',
    ]);
  });

  it('does not locally re-sort entries when updated_at is missing', () => {
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
    expect(rows[0].props.accessibilityLabel).toBe('对话: 每日健康简报 · 04-20');
    expect(rows[1].props.accessibilityLabel).toBe('对话: 每日健康简报 · 04-25');
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

describe('ConversationSheet 搜索', () => {
  it('未提供 onSearchChange → 不渲染搜索框 (旧行为逐字节不变)', () => {
    const { queryByLabelText } = render(
      <ConversationSheet {...baseProps} conversations={[] as any} />
    );
    expect(queryByLabelText('搜索对话')).toBeNull();
  });

  it('提供 onSearchChange → 渲染搜索框, 输入回调受控值', () => {
    const onSearchChange = jest.fn();
    const { getByLabelText } = render(
      <ConversationSheet
        {...baseProps}
        conversations={[] as any}
        searchValue=""
        onSearchChange={onSearchChange}
      />
    );
    fireEvent.changeText(getByLabelText('搜索对话'), '胃痛');
    expect(onSearchChange).toHaveBeenCalledWith('胃痛');
  });

  it('清除按钮在有值时出现, 点击回调空串', () => {
    const onSearchChange = jest.fn();
    const { getByLabelText } = render(
      <ConversationSheet
        {...baseProps}
        conversations={[] as any}
        searchValue="喷嚏"
        onSearchChange={onSearchChange}
      />
    );
    fireEvent.press(getByLabelText('清除搜索'));
    expect(onSearchChange).toHaveBeenCalledWith('');
  });

  it('搜索无结果 → "未找到匹配的对话"; 无搜索空列表 → "还没有历史对话"', () => {
    const withSearch = render(
      <ConversationSheet
        {...baseProps}
        conversations={[] as any}
        searchValue="不存在的词"
        onSearchChange={jest.fn()}
      />
    );
    expect(withSearch.getByText('未找到匹配的对话')).toBeTruthy();

    const noSearch = render(
      <ConversationSheet {...baseProps} conversations={[] as any} />
    );
    expect(noSearch.getByText('还没有历史对话')).toBeTruthy();
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
