import { restoreMessagesFromHistory } from '../useChatEngine';

jest.mock('../../services/chat', () => ({
  streamChat: jest.fn(),
  getConversations: jest.fn(),
  getConversationMessages: jest.fn(),
  deleteConversation: jest.fn(),
}));

jest.mock('../../services/api', () => ({
  __esModule: true,
  default: {},
  BASE_URL: 'https://example.test/api/v1',
}));

jest.mock('../../services/clientEvents', () => ({
  emitClientEvent: jest.fn(),
}));

jest.mock('../../components/chat/cards', () => ({
  renderServerCards: (cards: any[]) => Array.isArray(cards) ? cards : [],
  dispatchCard: jest.fn(),
}));

describe('restoreMessagesFromHistory', () => {
  it('restores chat image URLs without duplicating the API prefix', () => {
    const restored = restoreMessagesFromHistory([
      {
        id: 11,
        role: 'user',
        content: '记录一下\n[附图: 1张]',
        created_at: '2026-07-01 13:54:00',
        image_url: '["/api/v1/upload/files/chat/knee-mri.jpeg"]',
      },
    ], 'https://example.test/api/v1', 'h');

    expect(restored[0]).toMatchObject({
      id: 'h-11',
      role: 'user',
      imageUris: ['https://example.test/api/v1/upload/files/chat/knee-mri.jpeg'],
    });
  });

  it('restores chat images from array and absolute URL history payloads', () => {
    const restored = restoreMessagesFromHistory([
      {
        id: 12,
        role: 'user',
        content: '两张图',
        created_at: '2026-07-01 13:55:00',
        image_url: [
          '/api/v1/upload/files/chat/a.jpeg',
          'https://cdn.example.test/chat/b.jpeg',
        ],
      },
    ], 'https://example.test/api/v1', 'h');

    expect(restored[0]?.imageUris).toEqual([
      'https://example.test/api/v1/upload/files/chat/a.jpeg',
      'https://cdn.example.test/chat/b.jpeg',
    ]);
  });

  it('restores persisted server cards after the assistant message', () => {
    const restored = restoreMessagesFromHistory([
      {
        id: 10,
        role: 'assistant',
        content: '已记录晚餐。',
        created_at: '2026-05-18 18:57:00',
        meta: {
          elapsed_ms: 13900,
          model: 'MiniMax-M2.5',
          sources_used: ['今天打卡记录'],
          cards: [
            {
              type: 'system_knowledge_evidence',
              data: {
                entity: { title: 'MTHFR' },
                claims: [{ title: 'MTHFR C677T 与叶酸转化边界' }],
              },
            },
          ],
        },
      },
    ], 'https://example.test', 'h');

    expect(restored).toHaveLength(2);
    expect(restored[0]).toMatchObject({
      id: 'h-10',
      role: 'assistant',
      content: '已记录晚餐。',
      elapsedMs: 13900,
      model: 'MiniMax-M2.5',
      sourcesUsed: ['今天打卡记录'],
    });
    expect(restored[1]).toMatchObject({
      id: 'h-10-card-0',
      role: 'assistant',
      content: '',
      cardType: 'system_knowledge_evidence',
      cardData: {
        entity: { title: 'MTHFR' },
        claims: [{ title: 'MTHFR C677T 与叶酸转化边界' }],
      },
    });
  });

  it('restores llm usage from assistant message meta', () => {
    const restored = restoreMessagesFromHistory([
      {
        id: 20,
        role: 'assistant',
        content: '已分析。',
        created_at: '2026-07-02 10:00:00',
        meta: {
          llm_usage: {
            calls: 2,
            prompt_tokens: 1800,
            completion_tokens: 420,
            total_tokens: 2220,
            items: [
              { model: 'qwen3.7-plus', prompt_tokens: 1000, completion_tokens: 300 },
              { model: 'qwen3.7-max', prompt_tokens: 800, completion_tokens: 120 },
            ],
          },
        },
      },
    ], 'https://example.test', 'h');

    expect(restored[0]).toMatchObject({
      id: 'h-20',
      role: 'assistant',
      llmUsage: {
        calls: 2,
        prompt_tokens: 1800,
        completion_tokens: 420,
        total_tokens: 2220,
      },
    });
  });
});
