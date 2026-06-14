// @vitest-environment jsdom
/**
 * ai-assistant 页 URL 状态回归:
 *   - mount 时 URL 带 ?c=<id> → 自动加载对应对话 (agentApi.getConversation(id)).
 *   - 无 ?c → 不加载, 进新对话空态.
 */
import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';

const searchParamsGet = vi.fn();
const routerReplace = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: routerReplace, push: vi.fn() }),
  useSearchParams: () => ({ get: searchParamsGet }),
}));

const getConversation = vi.fn();
const getConversations = vi.fn();
vi.mock('@/services/api/ai', () => ({
  agentApi: {
    getConversation: (...a: unknown[]) => getConversation(...a),
    getConversations: (...a: unknown[]) => getConversations(...a),
    streamMessage: vi.fn(),
    deleteConversation: vi.fn(),
    updateConversationTitle: vi.fn(),
  },
  sharedApi: { createTextShare: vi.fn() },
}));

const apiGet = vi.fn();
vi.mock('@/services/api/client', () => ({
  api: { get: (...a: unknown[]) => apiGet(...a), put: vi.fn(), post: vi.fn() },
}));

import AIAssistantPage from '../page';

beforeEach(() => {
  vi.clearAllMocks();
  apiGet.mockResolvedValue({ data: {} });
  getConversations.mockResolvedValue({ data: { items: [], total: 0 } });
  getConversation.mockResolvedValue({ data: { messages: [] } });
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
});
