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
  streamMessage.mockImplementation(async function* () {
    yield { event: 'done', data: { conversation_id: 88 } };
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

  it('searches history by title or message content from the page rail', async () => {
    searchParamsGet.mockReturnValue(null);
    render(<AIAssistantPage />);

    fireEvent.change(await screen.findByLabelText('搜索对话'), { target: { value: '睡眠' } });

    await waitFor(() => {
      expect(getConversations).toHaveBeenLastCalledWith(20, 0, '睡眠');
    });
  });

  it('renders structured opener quick replies by label', async () => {
    searchParamsGet.mockReturnValue(null);
    apiGet.mockImplementation((path: string) => {
      if (path === '/agent/conversation-starters') {
        return Promise.resolve({
          data: {
            opener: {
              text: '我们从记录一件小事开始吧',
              source: 'cold_start',
              quick_replies: [
                { label: '拍一张今天的饭', action: 'photo_meal' },
                { label: '记一下体重', action: 'record_weight' },
              ],
            },
            suggestions: [],
            onboarding: true,
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(<AIAssistantPage />);

    expect(await screen.findByText('拍一张今天的饭')).toBeInTheDocument();
    expect(screen.getByText('记一下体重')).toBeInTheDocument();
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

  it('keeps web composer input available and queues a second prompt while streaming', async () => {
    searchParamsGet.mockReturnValue(null);
    let finishFirst: (() => void) | undefined;
    streamMessage.mockImplementation(async function* (text: string) {
      if (text === '第一条') {
        yield { event: 'start', data: { conversation_id: 88 } };
        await new Promise<void>((resolve) => { finishFirst = resolve; });
        yield { event: 'done', data: { conversation_id: 88 } };
        return;
      }
      yield { event: 'done', data: { conversation_id: 88 } };
    });

    render(<AIAssistantPage />);

    fireEvent.change(screen.getByPlaceholderText(/发消息/), { target: { value: '第一条' } });
    fireEvent.click(screen.getByTitle('发送'));

    await waitFor(() => expect(streamMessage).toHaveBeenCalledTimes(1));
    const textarea = screen.getByPlaceholderText(/发消息|回答中/);
    expect(textarea).not.toBeDisabled();

    fireEvent.change(textarea, { target: { value: '第二条' } });
    fireEvent.click(screen.getByTitle('发送'));

    expect(screen.getByText('第二条')).toBeInTheDocument();
    expect(screen.getByText('小巴处理中，已加入队列。')).toBeInTheDocument();
    expect(streamMessage).toHaveBeenCalledTimes(1);

    finishFirst?.();
    await waitFor(() => expect(streamMessage).toHaveBeenCalledTimes(2));
  });
});
