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
});
