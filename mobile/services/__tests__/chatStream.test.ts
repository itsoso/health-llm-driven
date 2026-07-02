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
      value: { type: 'start', conversationId: 42, thought: '正在理解你的问题' },
      done: false,
    });
    await iter.return?.(undefined as any);
  });

  it('maps agent progress events to safe thinking summaries', async () => {
    const iter = streamChat('分析我最近 7 天睡眠');
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    xhr.responseText =
      'data: {"event":"agent_start","data":{"message":"Agent 正在分析...","conversation_id":42}}\n\n';
    xhr.onprogress?.();

    await expect(first).resolves.toEqual({
      value: { type: 'start', conversationId: 42, thought: '正在理解你的问题' },
      done: false,
    });

    const second = iter.next();
    xhr.responseText +=
      'data: {"event":"tool_call","data":{"tool":"health_query","round":1,"args":"{\\"dimension\\":\\"sleep\\"}"}}\n\n';
    xhr.onprogress?.();

    await expect(second).resolves.toEqual({
      value: {
        type: 'tool',
        content: '',
        toolName: 'health_query',
        thought: '读取健康数据',
      },
      done: false,
    });

    const third = iter.next();
    xhr.responseText +=
      'data: {"event":"tool_result","data":{"tool":"health_query","success":true,"preview":"ok"}}\n\n';
    xhr.onprogress?.();

    await expect(third).resolves.toEqual({
      value: {
        type: 'tool',
        content: '',
        toolName: 'health_query',
        toolSuccess: true,
        recordType: undefined,
        recordData: undefined,
        thought: '已取得健康数据',
      },
      done: false,
    });
    await iter.return?.(undefined as any);
  });

  it('declares GenUI support so the backend can return deterministic charts', async () => {
    const iter = streamChat('帮我绘制最近半年的HRV曲线');
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];

    expect(xhr.setRequestHeader).toHaveBeenCalledWith('X-Reva-Client-Caps', expect.stringContaining('genui-v1'));
    expect(xhr.setRequestHeader).toHaveBeenCalledWith('X-Reva-Client-Caps', expect.stringContaining('genui-components-v1'));

    xhr.responseText =
      'data: {"event":"done","data":{"conversation_id":42,"message_id":99}}\n\n';
    xhr.onprogress?.();
    await first;
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

  it('preserves llm usage profile from done event', async () => {
    const iter = streamChat('昨天我吃得如何');
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    xhr.responseText =
      'data: {"event":"done","data":{"conversation_id":42,"message_id":99,"llm_rounds_ms":[4100],"perf":{"total_ms":5200,"pre_llm_ms":44,"llm_ttft_ms":900,"rounds":[{"llm_gen_ms":4100,"tool_exec_ms":12,"tools":["health_query"]}]},"llm_usage":{"calls":1,"prompt_tokens":1200,"completion_tokens":360,"total_tokens":1560,"cost_usd":0.0004,"items":[{"model":"qwen3.7-plus","prompt_tokens":1200,"completion_tokens":360}]}}}\n\n';
    xhr.onprogress?.();

    await expect(first).resolves.toMatchObject({
      value: {
        type: 'done',
        conversationId: 42,
        messageId: 99,
        llmRoundsMs: [4100],
        perf: {
          total_ms: 5200,
          pre_llm_ms: 44,
          llm_ttft_ms: 900,
          rounds: [
            { llm_gen_ms: 4100, tool_exec_ms: 12, tools: ['health_query'] },
          ],
        },
        llmUsage: {
          calls: 1,
          prompt_tokens: 1200,
          completion_tokens: 360,
          total_tokens: 1560,
          items: [
            {
              model: 'qwen3.7-plus',
              prompt_tokens: 1200,
              completion_tokens: 360,
            },
          ],
        },
      },
      done: false,
    });
    await iter.return?.(undefined as any);
  });

  it('yields card events before done for interleaved dynamic UI', async () => {
    const iter = streamChat('吃了两个鸡蛋一杯牛奶');
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    xhr.responseText =
      'data: {"event":"card","data":{"anchor":"after-token-1","descriptor":{"type":"diet","data":{"items":["鸡蛋","牛奶"]},"actions":[{"id":"confirm-diet","label":"确认记录","action":"write_intent.confirm","endpoint":"/write-intents/12/confirm","payload":{"write_intent_id":12},"requires_manual_confirm":true}]}}}\n\n';
    xhr.onprogress?.();

    await expect(first).resolves.toEqual({
      value: {
        type: 'card',
        anchor: 'after-token-1',
        card: {
          type: 'diet',
          data: { items: ['鸡蛋', '牛奶'] },
          actions: [
            {
              id: 'confirm-diet',
              label: '确认记录',
              action: 'write_intent.confirm',
              endpoint: '/write-intents/12/confirm',
              payload: { write_intent_id: 12 },
              requires_manual_confirm: true,
            },
          ],
        },
      },
      done: false,
    });
    await iter.return?.(undefined as any);
  });

  it('parses a final done event even without a trailing newline', async () => {
    const iter = streamChat('slow commercial model');
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    xhr.responseText =
      'data: {"event":"done","data":{"conversation_id":77,"message_id":88,"completion_status":"complete"}}';
    xhr.onload?.();

    await expect(first).resolves.toEqual({
      value: {
        type: 'done',
        conversationId: 77,
        messageId: 88,
        elapsedMs: undefined,
        llmMs: undefined,
        llmRounds: undefined,
        model: undefined,
        sourcesUsed: undefined,
        completionStatus: 'complete',
        cards: undefined,
      },
      done: false,
    });
    await iter.return?.(undefined as any);
  });

  it('allows longer commercial gateway replies before timing out', async () => {
    const iter = streamChat('use commercial model');
    const first = iter.next();
    await Promise.resolve();

    const xhr = MockXMLHttpRequest.instances[0];
    expect(xhr.timeout).toBe(300000);

    xhr.responseText =
      'data: {"event":"done","data":{"conversation_id":1,"message_id":2}}\n\n';
    xhr.onprogress?.();
    await first;
    await iter.return?.(undefined as any);
  });
});
