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
});
