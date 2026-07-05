// @vitest-environment jsdom
/**
 * ai-assistant 页 URL 状态回归:
 *   - mount 时 URL 带 ?c=<id> → 自动加载对应对话 (agentApi.getConversation(id)).
 *   - 无 ?c → 不加载, 进新对话空态.
 */
import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const searchParamsGet = vi.fn();
const routerReplace = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: routerReplace, push: vi.fn() }),
  useSearchParams: () => ({ get: searchParamsGet }),
}));

const getConversation = vi.fn();
const getConversations = vi.fn();
const streamMessage = vi.fn();
vi.mock('@/services/api/ai', () => ({
  agentApi: {
    getConversation: (...a: unknown[]) => getConversation(...a),
    getConversations: (...a: unknown[]) => getConversations(...a),
    streamMessage: (...a: unknown[]) => streamMessage(...a),
    deleteConversation: vi.fn(),
    updateConversationTitle: vi.fn(),
  },
  sharedApi: { createTextShare: vi.fn() },
}));

const apiGet = vi.fn();
vi.mock('@/services/api/client', () => ({
  api: { get: (...a: unknown[]) => apiGet(...a), put: vi.fn(), post: vi.fn() },
}));

const executeMedicalExamImportSkillForFile = vi.fn();
vi.mock('@/services/chatMedicalExamImportSkill', () => ({
  executeMedicalExamImportSkillForFile: (...a: unknown[]) => executeMedicalExamImportSkillForFile(...a),
}));

import AIAssistantPage from '../page';

beforeEach(() => {
  vi.clearAllMocks();
  apiGet.mockResolvedValue({ data: {} });
  getConversations.mockResolvedValue({ data: { items: [], total: 0 } });
  getConversation.mockResolvedValue({ data: { messages: [] } });
  // 默认: 空的 async 迭代, 让 sendMessage 的 for-await 循环干净结束。
  streamMessage.mockImplementation(async function* () {
    /* no events */
  });
});

describe('ai-assistant URL state', () => {
  it('loads conversation from ?c=<id> on mount', async () => {
    searchParamsGet.mockReturnValue('42');
    render(<AIAssistantPage />);
    await waitFor(() => expect(getConversation).toHaveBeenCalledWith(42));
  });

  it('does not load any conversation when ?c is absent', async () => {
    searchParamsGet.mockReturnValue(null);
    render(<AIAssistantPage />);
    await waitFor(() => expect(getConversations).toHaveBeenCalled());
    expect(getConversation).not.toHaveBeenCalled();
  });

  it('ignores non-numeric ?c value', async () => {
    searchParamsGet.mockReturnValue('abc');
    render(<AIAssistantPage />);
    await waitFor(() => expect(getConversations).toHaveBeenCalled());
    expect(getConversation).not.toHaveBeenCalled();
  });

  it('prefills the composer from ?prompt= for a cross-page 提问 entry (fresh conversation)', async () => {
    const question = '结合我的疾病风险基因位点（共 3 个），给我个性化建议。';
    searchParamsGet.mockImplementation((key: string) =>
      key === 'prompt' ? encodeURIComponent(question) : null,
    );
    render(<AIAssistantPage />);
    // input 预填成解码后的问题, 且不自动发送 (streamMessage 未被调用)。
    expect(await screen.findByDisplayValue(question)).toBeInTheDocument();
    expect(streamMessage).not.toHaveBeenCalled();
    // 跨页提问 = 全新对话: 不恢复任何旧对话 (无 getConversation 调用),
    // 停在 empty-state 空态 (「今天想了解什么？」 标题可见)。
    expect(getConversation).not.toHaveBeenCalled();
    expect(screen.getByText('今天想了解什么？')).toBeInTheDocument();
    // 消费后清掉 ?prompt=, 刷新不重复注入。
    await waitFor(() => expect(routerReplace).toHaveBeenCalledWith('/ai-assistant', { scroll: false }));
  });

  it('does not prefill from ?prompt= when ?c= conversation restore wins', async () => {
    searchParamsGet.mockImplementation((key: string) => {
      if (key === 'c') return '42';
      if (key === 'prompt') return encodeURIComponent('不应出现的预填');
      return null;
    });
    render(<AIAssistantPage />);
    await waitFor(() => expect(getConversation).toHaveBeenCalledWith(42));
    expect(screen.queryByDisplayValue('不应出现的预填')).toBeNull();
  });

  it('sends opener text quick replies with the opener context so verification has a target', async () => {
    searchParamsGet.mockReturnValue(null);
    apiGet.mockImplementation((url: string) => {
      if (typeof url === 'string' && url.includes('/agent/conversation-starters')) {
        return Promise.resolve({
          data: {
            opener: {
              text: '今天就是「AI 预测：7 天体重保持 ≤ 71.3kg」的检验日，做到了吗？',
              source: 'action_card_due',
              source_id: 88,
              quick_replies: [{ text: '做到了 ✅' }, { text: '没做 ❌' }, { text: '调整下计划' }],
              deep_link: '/action-cards/88',
              priority: 100,
            },
            suggestions: null,
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(<AIAssistantPage />);

    const chip = await screen.findByRole('button', { name: '做到了 ✅' });
    fireEvent.click(chip);

    await waitFor(() => expect(streamMessage).toHaveBeenCalled());
    const call = streamMessage.mock.calls[0];
    // sendMessage(text, extraContext) → streamMessage(text, convId, u, u, u, u, extraContext)
    const messageText = call[0] as string;
    const extraContext = call[6] as string;
    expect(messageText).toContain('AI 预测：7 天体重保持 ≤ 71.3kg');
    expect(messageText).toContain('做到了 ✅');
    expect(JSON.parse(extraContext)).toMatchObject({
      entry: 'conversation_opener_quick_reply',
      user_reply: '做到了 ✅',
      source: 'action_card_due',
      source_id: 88,
      action_card_id: 88,
    });
  });

  it('imports a medical exam file from the composer and renders a result card', async () => {
    searchParamsGet.mockReturnValue(null);
    executeMedicalExamImportSkillForFile.mockResolvedValueOnce({
      skillId: 'medical_exam_import',
      card: {
        type: 'medical_exam_import_result',
        data: {
          exam_id: 42,
          source: 'pdf',
          items_count: 28,
          abnormal_count: 3,
          review_required: true,
          safety_note: 'OCR/AI 解析结果需要复核后再用于判断。',
        },
      },
      prompt: '请基于我刚导入的体检报告，解释异常/关键指标。',
      context: {},
    });
    render(<AIAssistantPage />);

    const file = new File(['pdf'], 'report.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('选择体检报告文件'), {
      target: { files: [file] },
    });

    await waitFor(() => expect(executeMedicalExamImportSkillForFile).toHaveBeenCalledWith(file));
    expect(await screen.findByText('体检报告已导入')).toBeInTheDocument();
    expect(screen.getByDisplayValue('请基于我刚导入的体检报告，解释异常/关键指标。')).toBeInTheDocument();
  });
});
