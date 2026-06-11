// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ConversationHistoryRail from '../ConversationHistoryRail';

describe('ConversationHistoryRail', () => {
  it('renames a conversation title inline', async () => {
    const onRename = vi.fn().mockResolvedValue(undefined);

    render(
      <ConversationHistoryRail
        conversations={[
          {
            id: 7,
            title: '分析我最近的代谢健康',
            created_at: '2026-05-18T08:00:00Z',
            updated_at: '2026-05-18T09:00:00Z',
            last_message: '分析我最近的代谢健康',
          },
        ]}
        activeConvId={7}
        loading={false}
        onLoad={vi.fn()}
        onDelete={vi.fn()}
        onNew={vi.fn()}
        onRename={onRename}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '重命名对话' }));
    fireEvent.change(screen.getByLabelText('对话标题'), {
      target: { value: '最近代谢复盘' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存标题' }));

    await waitFor(() => {
      expect(onRename).toHaveBeenCalledWith(7, '最近代谢复盘');
    });
  });

  it('shows prev/next pager and disables prev on first page', () => {
    const onNextPage = vi.fn();
    render(
      <ConversationHistoryRail
        conversations={[
          { id: 1, title: '对话A', created_at: '', updated_at: '' },
        ]}
        loading={false}
        onLoad={vi.fn()}
        onDelete={vi.fn()}
        onNew={vi.fn()}
        onRename={vi.fn()}
        page={1}
        totalPages={3}
        onPrevPage={vi.fn()}
        onNextPage={onNextPage}
      />,
    );

    expect(screen.getByText('第 1 / 3 页')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '下一页' }));
    expect(onNextPage).toHaveBeenCalled();
  });

  it('hides pager when only one page', () => {
    render(
      <ConversationHistoryRail
        conversations={[{ id: 1, title: '对话A', created_at: '', updated_at: '' }]}
        loading={false}
        onLoad={vi.fn()}
        onDelete={vi.fn()}
        onNew={vi.fn()}
        onRename={vi.fn()}
        page={1}
        totalPages={1}
      />,
    );
    expect(screen.queryByText(/页$/)).not.toBeInTheDocument();
  });
});
