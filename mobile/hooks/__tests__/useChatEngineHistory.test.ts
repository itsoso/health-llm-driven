import {
  dedupeStableCardMessages,
  restoreMessagesFromHistory,
} from '../useChatEngine';

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

  it('restores health evidence from persisted meta.cards without a second manifest state', () => {
    const manifest = {
      version: 'health-evidence.v1',
      risk_level: 'medium',
      intent: {
        intent_id: 'health_advice.symptom.low_back_pain',
      },
      context_categories_used: ['symptom'],
      authority_evidence_refs: ['claim:low-back-triage'],
      missing_discriminators: [{
        id: 'low_back.major_trauma',
        question: '近期是否有严重外伤？',
        choices: ['有', '没有', '不确定'],
      }],
      private_packet: {
        medication_record_id: 42,
      },
    };
    const restored = restoreMessagesFromHistory([
      {
        id: 14,
        role: 'assistant',
        content: '先确认几个安全问题。',
        created_at: '2026-07-29 12:00:00',
        meta: {
          health_evidence_manifest: manifest,
          client_turn_id: 'turn-parent-7',
          cards: [{
            type: 'health_evidence',
            data: manifest,
            actions: [],
          }],
        },
      },
    ], 'https://example.test', 'h');

    expect(restored).toHaveLength(2);
    expect(restored[0]).toMatchObject({
      role: 'assistant',
      sourceMessageId: 14,
    });
    expect(restored[1]).toMatchObject({
      role: 'assistant',
      cardType: 'health_evidence',
      cardData: {
        version: 'health-evidence.v1',
        risk_level: 'medium',
        intent: {
          intent_id: 'health_advice.symptom.low_back_pain',
        },
        context_categories_used: ['symptom'],
        authority_evidence_refs: ['claim:low-back-triage'],
        missing_discriminators: [{
          id: 'low_back.major_trauma',
          question: '近期是否有严重外伤？',
          choices: ['有', '没有', '不确定'],
        }],
      },
      cardActions: [],
      sourceMessageId: 14,
      sourceTurnId: 'turn-parent-7',
    });
  });

  it('folds repeated projections of one meal card and keeps the latest media set', () => {
    const restored = restoreMessagesFromHistory([
      {
        id: 13,
        role: 'assistant',
        content: '晚餐已记录。',
        created_at: '2026-07-25 18:30:00',
        meta: {
          client_turn_id: 'turn-meal-1',
          cards: [
            {
              type: 'diet_draft',
              data: {
                card_id: 'diet-record:88',
                record_id: 88,
                photo_asset_ids: [901],
                photo_urls: ['/api/v1/upload/files/diet/1/a.jpeg'],
              },
            },
            {
              type: 'diet_draft',
              data: {
                card_id: 'diet-record:88',
                record_id: 88,
                photo_asset_ids: [901, 902],
                photo_urls: [
                  '/api/v1/upload/files/diet/1/a.jpeg',
                  '/api/v1/upload/files/diet/1/b.jpeg',
                ],
              },
            },
          ],
        },
      },
    ], 'https://example.test', 'h');

    expect(restored).toHaveLength(2);
    expect(restored[1]).toMatchObject({
      cardType: 'diet_draft',
      sourceTurnId: 'turn-meal-1',
      cardData: {
        card_id: 'diet-record:88',
        record_id: 88,
        photo_asset_ids: [901, 902],
        photo_urls: [
          '/api/v1/upload/files/diet/1/a.jpeg',
          '/api/v1/upload/files/diet/1/b.jpeg',
        ],
      },
    });
  });

  it('keeps one latest projection when the same stable card appears in different turns', () => {
    const restored = restoreMessagesFromHistory([
      {
        id: 21,
        role: 'assistant',
        content: '第一张已记录。',
        created_at: '2026-07-25 18:30:00',
        meta: {
          client_turn_id: 'turn-meal-1',
          cards: [{
            type: 'diet_draft',
            data: {
              card_id: 'diet-record:99',
              record_id: 99,
              photo_urls: ['/api/v1/upload/files/diet/1/a.jpeg'],
            },
          }],
        },
      },
      {
        id: 22,
        role: 'assistant',
        content: '第二张已补充。',
        created_at: '2026-07-25 18:31:00',
        meta: {
          client_turn_id: 'turn-meal-2',
          cards: [{
            type: 'diet_draft',
            data: {
              card_id: 'diet-record:99',
              record_id: 99,
              photo_urls: [
                '/api/v1/upload/files/diet/1/a.jpeg',
                '/api/v1/upload/files/diet/1/b.jpeg',
              ],
            },
          }],
        },
      },
    ], 'https://example.test', 'h');

    const mealCards = restored.filter(message => message.cardType === 'diet_draft');
    expect(mealCards).toHaveLength(1);
    expect(mealCards[0]).toMatchObject({
      sourceTurnId: 'turn-meal-2',
      cardData: {
        card_id: 'diet-record:99',
        photo_urls: [
          '/api/v1/upload/files/diet/1/a.jpeg',
          '/api/v1/upload/files/diet/1/b.jpeg',
        ],
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
          perf: {
            total_ms: 29200,
            pre_llm_ms: 44,
            llm_ttft_ms: 23600,
            rounds: [
              { llm_gen_ms: 4100, tool_exec_ms: 15, tools: ['health_manage'] },
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
      perf: {
        total_ms: 29200,
        pre_llm_ms: 44,
        llm_ttft_ms: 23600,
      },
    });
  });
});

describe('dedupeStableCardMessages', () => {
  it('keeps the newest stable projection when an older history page is prepended', () => {
    const merged = dedupeStableCardMessages([
      {
        id: 'old-card',
        role: 'assistant',
        content: '',
        cardType: 'diet_draft',
        cardData: {
          card_id: 'diet-record:99',
          photo_urls: ['/api/v1/upload/files/diet/1/a.jpeg'],
        },
      },
      {
        id: 'new-card',
        role: 'assistant',
        content: '',
        cardType: 'diet_draft',
        cardData: {
          card_id: 'diet-record:99',
          photo_urls: [
            '/api/v1/upload/files/diet/1/a.jpeg',
            '/api/v1/upload/files/diet/1/b.jpeg',
          ],
        },
      },
    ]);

    expect(merged.map(message => message.id)).toEqual(['new-card']);
    expect(merged[0].cardData.photo_urls).toHaveLength(2);
  });
});
