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
const apiPost = vi.fn();
vi.mock('@/services/api/client', () => ({
  api: {
    get: (...a: unknown[]) => apiGet(...a),
    put: vi.fn(),
    post: (...a: unknown[]) => apiPost(...a),
  },
}));

const executeMedicalExamImportSkillForFile = vi.fn();
vi.mock('@/services/chatMedicalExamImportSkill', () => ({
  executeMedicalExamImportSkillForFile: (...a: unknown[]) => executeMedicalExamImportSkillForFile(...a),
}));

import AIAssistantPage from '../page';

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(window, 'confirm', {
    configurable: true,
    value: vi.fn(() => true),
  });
  Object.defineProperty(window, 'alert', {
    configurable: true,
    value: vi.fn(),
  });
  apiGet.mockResolvedValue({ data: {} });
  apiPost.mockResolvedValue({ data: {} });
  getConversations.mockResolvedValue({ data: { items: [], total: 0 } });
  getConversation.mockResolvedValue({ data: { messages: [] } });
  streamMessage.mockImplementation(async function* () {
    yield { event: 'done', data: { conversation_id: 88 } };
  });
});

const MEDICATION_POLICY = {
  requires_manual_confirm: true,
  required_receipt: true,
  capability_id: 'medication_draft.v1',
  autonomy_tier: 'manual_confirm',
  policy_reason: 'manual_confirm_write',
};

function medicationCard(intentId = 42) {
  return {
    type: 'medication_draft',
    data: {
      items: [
        { medication_name: '伊托必利', actual_dosage: '1粒' },
        { medication_name: '替普瑞酮', actual_dosage: '1粒', observed_strength: '50mg' },
      ],
      taken_at: '2026-07-21 21:15',
      boundary: '确认后只记录本次事实。',
    },
    actions: [
      {
        ...MEDICATION_POLICY,
        id: `medication-batch-confirm:${intentId}`,
        label: '确认记录',
        action: 'write_intent.confirm',
        endpoint: `/write-intents/${intentId}/confirm`,
        payload: { write_intent_id: intentId },
        style: 'primary',
        confirmation: { title: '确认记录两项用药？', detail: '将一次写入两条事实。' },
      },
      {
        ...MEDICATION_POLICY,
        id: `medication-batch-dismiss:${intentId}`,
        label: '取消',
        action: 'write_intent.dismiss',
        endpoint: `/write-intents/${intentId}/dismiss`,
        payload: { write_intent_id: intentId },
        style: 'secondary',
      },
    ],
  };
}

function medicationConversation(meta?: Record<string, unknown>) {
  return {
    data: {
      messages: [{
        id: 501,
        role: 'assistant',
        content: '请确认记录本次服药。',
        created_at: '2026-07-21T21:15:00-04:00',
        meta: {
          completion_status: 'complete',
          client_turn_finalized: true,
          cards: [medicationCard()],
          ...meta,
        },
      }],
    },
  };
}

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

  it('locks medication sibling actions atomically and renders every response receipt and safety alert', async () => {
    searchParamsGet.mockReturnValue('42');
    getConversation.mockResolvedValue(medicationConversation());
    let resolveConfirm: ((value: unknown) => void) | undefined;
    apiPost.mockImplementationOnce(() => new Promise((resolve) => { resolveConfirm = resolve; }));

    render(<AIAssistantPage />);

    const confirmButton = await screen.findByRole('button', { name: '确认记录' });
    const dismissButton = screen.getByRole('button', { name: '取消' });
    fireEvent.click(confirmButton);

    expect(confirmButton).toBeDisabled();
    expect(dismissButton).toBeDisabled();
    fireEvent.click(dismissButton);
    expect(apiPost).toHaveBeenCalledTimes(1);
    expect(apiPost).toHaveBeenCalledWith('/write-intents/42/confirm');

    resolveConfirm?.({
      data: {
        id: 42,
        status: 'executed',
        executed_ref: 'medication_logs:101,102',
        write_receipts: [
          {
            operation_id: 'receipt-1', status: 'verified', resource_type: 'medication_log',
            resource_id: '101', completed_at: '2026-07-21T21:15:01-04:00', verified: true,
          },
          {
            operation_id: 'receipt-2', status: 'verified', resource_type: 'medication_log',
            resource_id: '102', completed_at: '2026-07-21T21:15:02-04:00', verified: true,
          },
        ],
        safety_alerts: [
          {
            rule_id: 'ddi.1', category: 'ddi', severity: { value: 3, label: 'high', label_zh: '高风险' },
            title: '安全提示一', message: '第一条不能被截断。', action: '联系医生或药师。',
          },
          {
            rule_id: 'ddi.2', category: 'ddi', severity: { value: 4, label: 'critical', label_zh: '严重' },
            title: '安全提示二', message: '第二条关键提示也必须显示。', action: '如有不适及时就医。',
          },
        ],
      },
    });

    expect(await screen.findByText('用药 · 已记录')).toBeInTheDocument();
    expect(screen.getByText(/回执 #101/)).toBeInTheDocument();
    expect(screen.getByText(/回执 #102/)).toBeInTheDocument();
    expect(screen.getByText('安全提示一')).toBeInTheDocument();
    expect(screen.getByText('安全提示二')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '确认记录' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '取消' })).not.toBeInTheDocument();
  });

  it('visually locks every repeated projection of the same medication intent group', async () => {
    searchParamsGet.mockReturnValue('42');
    const conversation = medicationConversation();
    conversation.data.messages.push({
      ...conversation.data.messages[0],
      id: 502,
      content: '同一服务端计划的恢复投影。',
    });
    getConversation.mockResolvedValue(conversation);
    apiPost.mockImplementationOnce(() => new Promise(() => {}));

    render(<AIAssistantPage />);

    const confirmButtons = await screen.findAllByRole('button', { name: '确认记录' });
    expect(confirmButtons).toHaveLength(2);
    fireEvent.click(confirmButtons[0]);

    screen.getAllByRole('button', { name: '确认记录' }).forEach(button => {
      expect(button).toBeDisabled();
    });
    screen.getAllByRole('button', { name: '取消' }).forEach(button => {
      expect(button).toBeDisabled();
    });
    expect(apiPost).toHaveBeenCalledTimes(1);
  });

  it('reconciles a 409 expiry from authoritative conversation meta', async () => {
    searchParamsGet.mockReturnValue('42');
    getConversation
      .mockResolvedValueOnce(medicationConversation())
      .mockResolvedValueOnce(medicationConversation({
        medication_batch_decision: { intent_id: 42, status: 'expired' },
        write_receipts: [],
        safety_alerts: [],
      }));
    apiPost.mockRejectedValueOnce({
      response: { status: 409, data: { detail: '确认计划已过期，请重新提交记录' } },
    });

    render(<AIAssistantPage />);
    fireEvent.click(await screen.findByRole('button', { name: '确认记录' }));

    await waitFor(() => expect(getConversation).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('用药 · 确认已过期')).toBeInTheDocument();
    expect(screen.getByText(/没有写入/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '确认记录' })).not.toBeInTheDocument();
  });

  it('dismisses a medication batch without fabricating a success receipt', async () => {
    searchParamsGet.mockReturnValue('42');
    getConversation.mockResolvedValue(medicationConversation());
    apiPost.mockResolvedValueOnce({ data: { id: 42, status: 'dismissed' } });

    render(<AIAssistantPage />);
    fireEvent.click(await screen.findByRole('button', { name: '取消' }));

    expect(await screen.findByText('用药 · 已取消')).toBeInTheDocument();
    expect(screen.getByText('这组记录已取消，没有写入。')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: '逐项写入回执' })).not.toBeInTheDocument();
    expect(apiPost).toHaveBeenCalledWith('/write-intents/42/dismiss');
  });

  it('projects a text-confirm terminal decision onto the earlier medication card immediately', async () => {
    searchParamsGet.mockReturnValue('42');
    getConversation.mockResolvedValue(medicationConversation());
    streamMessage.mockImplementationOnce(async function* () {
      yield { event: 'start', data: { conversation_id: 42 } };
      yield { event: 'token', data: { content: '已记录本次服药。' } };
      yield {
        event: 'done',
        data: {
          conversation_id: 42,
          message_id: 503,
          completion_status: 'complete',
          cards: [],
          medication_batch_decision: {
            intent_id: 42,
            status: 'executed',
            write_receipts: [
              {
                operation_id: 'write_intent:medication_intake_batch:42:101',
                status: 'verified', resource_type: 'medication_log', resource_id: '101',
                completed_at: '2026-07-21T21:15:01-04:00', verified: true,
              },
              {
                operation_id: 'write_intent:medication_intake_batch:42:102',
                status: 'verified', resource_type: 'medication_log', resource_id: '102',
                completed_at: '2026-07-21T21:15:02-04:00', verified: true,
              },
            ],
            safety_alerts: [{
              rule_id: 'ddi.text-confirm', category: 'ddi', severity: { value: 3, label: 'high' },
              title: '文本确认安全提示', message: '完整保留批次提示。',
            }],
          },
        },
      };
    });

    render(<AIAssistantPage />);
    await screen.findByRole('button', { name: '确认记录' });
    fireEvent.change(screen.getByPlaceholderText(/发消息/), { target: { value: '确认' } });
    fireEvent.click(screen.getByTitle('发送'));

    expect(await screen.findByText('用药 · 已记录')).toBeInTheDocument();
    expect(screen.getByText(/回执 #101/)).toBeInTheDocument();
    expect(screen.getByText(/回执 #102/)).toBeInTheDocument();
    expect(screen.getByText('文本确认安全提示')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '确认记录' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '取消' })).not.toBeInTheDocument();
  });

  it.each([
    ['dismissed', '用药 · 已取消'],
    ['expired', '用药 · 确认已过期'],
  ] as const)('projects a text %s terminal without any write receipt', async (status, title) => {
    searchParamsGet.mockReturnValue('42');
    getConversation.mockResolvedValue(medicationConversation());
    streamMessage.mockImplementationOnce(async function* () {
      yield { event: 'start', data: { conversation_id: 42 } };
      yield {
        event: 'done',
        data: {
          conversation_id: 42,
          message_id: 504,
          completion_status: status === 'dismissed' ? 'complete' : 'error',
          cards: [],
          medication_batch_decision: {
            intent_id: 42,
            status,
            write_receipts: [],
            safety_alerts: [],
          },
        },
      };
    });

    render(<AIAssistantPage />);
    await screen.findByRole('button', { name: '确认记录' });
    fireEvent.change(screen.getByPlaceholderText(/发消息/), { target: { value: '确认' } });
    fireEvent.click(screen.getByTitle('发送'));

    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '确认记录' })).not.toBeInTheDocument();
    expect(screen.queryByRole('list', { name: '逐项写入回执' })).not.toBeInTheDocument();
  });
});
