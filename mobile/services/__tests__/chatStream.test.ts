/* eslint-disable import/first */
jest.mock('../auth', () => ({
  getToken: jest.fn().mockResolvedValue('test-token'),
}));

jest.mock('../api', () => ({
  BASE_URL: 'https://example.test/api/v1',
}));

import { streamChat } from '../chat';

class MockXMLHttpRequest {
  static instances: MockXMLHttpRequest[] = [];

  responseText = '';
  responseType = '';
  timeout = 0;
  onprogress: (() => void) | null = null;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  status = 200;

  open = jest.fn();
  setRequestHeader = jest.fn();
  send = jest.fn();
  abort = jest.fn();

  constructor() {
    MockXMLHttpRequest.instances.push(this);
  }
}

describe('streamChat', () => {
  const OriginalXHR = global.XMLHttpRequest;

  beforeEach(() => {
    MockXMLHttpRequest.instances = [];
    (global as any).XMLHttpRequest = MockXMLHttpRequest as any;
  });

  afterEach(() => {
    (global as any).XMLHttpRequest = OriginalXHR;
    jest.clearAllMocks();
  });

  it('yields conversation id from agent_start before done for resume', async () => {
    const iter = streamChat('hello');
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    xhr.responseText =
      'data: {"event":"agent_start","data":{"message":"Agent 正在分析...","conversation_id":42}}\n\n';
    xhr.onprogress?.();

    await expect(first).resolves.toEqual({
      value: { type: 'start', conversationId: 42 },
      done: false,
    });
    await iter.return?.(undefined as any);
  });

  it('preserves cards from done event for mobile card rendering', async () => {
    const iter = streamChat('MTHFR 怎么办');
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    xhr.responseText =
      'data: {"event":"done","data":{"conversation_id":42,"message_id":99,"cards":[{"type":"system_knowledge_evidence","data":{"entity":{"title":"MTHFR"},"claims":[]}}]}}\n\n';
    xhr.onprogress?.();

    await expect(first).resolves.toEqual({
      value: {
        type: 'done',
        conversationId: 42,
        messageId: 99,
        elapsedMs: undefined,
        llmMs: undefined,
        llmRounds: undefined,
        model: undefined,
        sourcesUsed: undefined,
        cards: [
          {
            type: 'system_knowledge_evidence',
            data: { entity: { title: 'MTHFR' }, claims: [] },
          },
        ],
      },
      done: false,
    });
    await iter.return?.(undefined as any);
  });
});
