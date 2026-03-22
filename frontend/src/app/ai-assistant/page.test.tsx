import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import AIAssistantPage from './page';

const {
  mockPush,
  mockShowToast,
  mockChatGetConversations,
  mockOpenClawGetConversations,
} = vi.hoisted(() => ({
  mockPush: vi.fn(),
  mockShowToast: vi.fn(),
  mockChatGetConversations: vi.fn().mockResolvedValue({ data: [] }),
  mockOpenClawGetConversations: vi.fn().mockResolvedValue({ data: [] }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      email: 'user@example.com',
    },
  }),
}));

vi.mock('@/contexts/ToastContext', () => ({
  useToast: () => ({
    showToast: mockShowToast,
  }),
}));

vi.mock('@/services/api', () => ({
  api: {
    post: vi.fn(),
  },
  chatApi: {
    getConversations: mockChatGetConversations,
    getConversation: vi.fn(),
    deleteConversation: vi.fn(),
    sendMessage: vi.fn(),
    streamMessage: vi.fn(),
    transcribe: vi.fn(),
    voiceCommand: vi.fn(),
  },
  openclawApi: {
    getConversations: mockOpenClawGetConversations,
    getConversation: vi.fn(),
    deleteConversation: vi.fn(),
    streamMessage: vi.fn(),
  },
  sharedApi: {
    createShare: vi.fn(),
  },
}));

describe('AIAssistantPage', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('auth_token', 'token');
    mockPush.mockClear();
    mockShowToast.mockClear();
    mockChatGetConversations.mockClear();
    mockOpenClawGetConversations.mockClear();
  });

  it('renders the redesigned health workspace empty state', async () => {
    render(<AIAssistantPage />);

    await waitFor(() => {
      expect(mockChatGetConversations).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText('健康工作台')).toBeInTheDocument();
    expect(screen.getByText('恢复状态')).toBeInTheDocument();
    expect(screen.getAllByText('支持图片、文件、语音').length).toBeGreaterThan(0);
  });
});
