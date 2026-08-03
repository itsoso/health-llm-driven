/* eslint-disable import/first */
jest.mock('../auth', () => ({
  getToken: jest.fn().mockResolvedValue('test-token'),
}));

jest.mock('../api', () => ({
  BASE_URL: 'https://example.test/api/v1',
}));

import { streamChat } from '../chat';
import { buildClientCapsHeader } from '../clientCaps';
import { setAppEgressMode } from '../egressPolicy';

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
    setAppEgressMode('cloud_account');
  });

  afterEach(() => {
    (global as any).XMLHttpRequest = OriginalXHR;
    jest.useRealTimers();
    jest.clearAllMocks();
    setAppEgressMode(null);
  });

  it('yields conversation id from agent_start before done for resume', async () => {
    const iter = streamChat('hello');
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    xhr.responseText =
      'data: {"event":"agent_start","data":{"message":"小巴正在分析...","conversation_id":42}}\n\n';
    xhr.onprogress?.();

    await expect(first).resolves.toEqual({
      value: { type: 'start', conversationId: 42, thought: '正在理解你的问题' },
      done: false,
    });
    await iter.return?.(undefined as any);
  });

  it('sends the client turn id and yields only durable request persistence as acceptance', async () => {
    const iter = streamChat(
      '记录午餐',
      undefined,
      undefined,
      undefined,
      undefined,
      'voice',
      'turn-mobile-42',
    );
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    expect(JSON.parse(xhr.send.mock.calls[0][0])).toMatchObject({
      message: '记录午餐',
      channel: 'voice',
      client_turn_id: 'turn-mobile-42',
    });

    xhr.responseText =
      'data: {"event":"request_persisted","data":{"conversation_id":42,"user_message_id":98,"client_turn_id":"turn-mobile-42"}}\n\n';
    xhr.onprogress?.();

    await expect(first).resolves.toEqual({
      value: {
        type: 'persisted',
        conversationId: 42,
        userMessageId: 98,
        clientTurnId: 'turn-mobile-42',
      },
      done: false,
    });
    await iter.return?.(undefined as any);
  });

  it('rejects a busy JSON response instead of parsing it as SSE', async () => {
    const first = streamChat(
      '晚餐只吃了 1/2 修改记录',
      undefined,
      undefined,
      undefined,
      undefined,
      'typed',
      'turn-busy-1',
    ).next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    xhr.status = 409;
    xhr.responseText = JSON.stringify({ detail: '上一条消息仍在处理，请稍后重试' });
    xhr.onload?.();

    await expect(first).rejects.toMatchObject({
      name: 'ChatStreamHttpError',
      status: 409,
      detail: '上一条消息仍在处理，请稍后重试',
    });
  });

  it('drops non-allowlisted HTTP error detail before it reaches the UI', async () => {
    const first = streamChat('测试错误脱敏').next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    xhr.status = 500;
    xhr.responseText = JSON.stringify({
      detail: 'internal prompt with token=secret and private health data',
    });
    xhr.onload?.();

    await expect(first).rejects.toMatchObject({
      name: 'ChatStreamHttpError',
      status: 500,
      message: '请求失败 (status: 500)',
      detail: undefined,
    });
  });

  it('does not parse progress bytes from a non-2xx response', async () => {
    const first = streamChat('测试错误流隔离').next();
    let settled = false;
    void first.finally(() => {
      settled = true;
    }).catch(() => undefined);

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    xhr.status = 500;
    xhr.responseText =
      'data: {"event":"token","data":{"content":"private server detail"}}\n\n';
    xhr.onprogress?.();
    await Promise.resolve();

    expect(settled).toBe(false);

    xhr.responseText = JSON.stringify({ detail: 'private server detail' });
    xhr.onload?.();
    await expect(first).rejects.toMatchObject({
      name: 'ChatStreamHttpError',
      status: 500,
      message: '请求失败 (status: 500)',
    });
  });

  it('sends device current time context with every stream request', async () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2026-07-16T15:40:00.000Z'));

    const iter = streamChat('我明天几点起床比较合理？');
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    const body = JSON.parse(xhr.send.mock.calls[0][0]);
    expect(body.client_time_context).toMatchObject({
      client_now_iso: '2026-07-16T15:40:00.000Z',
    });
    expect(typeof body.client_time_context.timezone).toBe('string');
    expect(typeof body.client_time_context.timezone_offset_minutes).toBe('number');

    xhr.responseText =
      'data: {"event":"done","data":{"conversation_id":1,"message_id":2}}\n\n';
    xhr.onprogress?.();
    await first;
    await iter.return?.(undefined as any);
  });

  it('maps agent progress events to safe thinking summaries', async () => {
    const iter = streamChat('分析我最近 7 天睡眠');
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    xhr.responseText =
      'data: {"event":"agent_start","data":{"message":"小巴正在分析...","conversation_id":42}}\n\n';
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

  it('preserves deterministic write receipts from tool results', async () => {
    const iter = streamChat('记录午餐');
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    xhr.responseText =
      'data: {"event":"tool_result","data":{"tool":"health_record","success":true,"write_attempted":true,"write_completed":true,"record_type":"diet","record_data":{"food_items":"牛肉面"},"receipt":{"operation_id":"health_record:diet_record:701","status":"verified","resource_type":"diet_record","resource_id":"701","completed_at":"2026-07-09T12:00:00.000Z","verified":true}}}\n\n';
    xhr.onprogress?.();

    await expect(first).resolves.toEqual({
      value: {
        type: 'tool',
        content: '',
        toolName: 'health_record',
        toolSuccess: true,
        writeAttempted: true,
        writeCompleted: true,
        receipt: {
          operationId: 'health_record:diet_record:701',
          status: 'verified',
          resourceType: 'diet_record',
          resourceId: '701',
          completedAt: '2026-07-09T12:00:00.000Z',
          verified: true,
        },
        recordType: 'diet',
        recordData: { food_items: '牛肉面' },
        thought: '已取得记录信息',
      },
      done: false,
    });
    await iter.return?.(undefined as any);
  });

  it('keeps a recoverable tool failure out of the assistant body before a verified retry', async () => {
    const iter = streamChat('删除旧午餐，保留刚才这一餐');
    const failedAttempt = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    xhr.responseText =
      'data: {"event":"tool_result","data":{"tool":"health_manage","success":false,"write_attempted":true,"write_completed":false,"preview":"参数不完整"}}\n\n';
    xhr.onprogress?.();

    await expect(failedAttempt).resolves.toEqual({
      value: {
        type: 'tool',
        content: '',
        toolName: 'health_manage',
        toolSuccess: false,
        writeAttempted: true,
        writeCompleted: false,
        recordType: undefined,
        recordData: undefined,
        thought: '健康记录暂时不可用',
      },
      done: false,
    });

    const successfulRetry = iter.next();
    xhr.responseText +=
      'data: {"event":"tool_result","data":{"tool":"health_manage","success":true,"write_attempted":true,"write_completed":true,"receipt":{"operation_id":"health_manage:diet_record:829","status":"verified","resource_type":"diet_record","resource_id":"829","completed_at":"2026-07-16T04:17:31.825611+00:00","verified":true}}}\n\n';
    xhr.onprogress?.();

    await expect(successfulRetry).resolves.toEqual({
      value: expect.objectContaining({
        type: 'tool',
        content: '',
        toolName: 'health_manage',
        toolSuccess: true,
        writeCompleted: true,
        receipt: expect.objectContaining({
          operationId: 'health_manage:diet_record:829',
          verified: true,
        }),
      }),
      done: false,
    });
    await iter.return?.(undefined as any);
  });

  it('parses an uncertain write as a reconciliation state instead of a generic outage', async () => {
    const iter = streamChat('昨天喝水很多 补充记录 1200 毫升');
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    xhr.responseText =
      'data: {"event":"tool_result","data":{"tool":"health_record","success":false,"write_attempted":true,"write_completed":false,"write_outcome":"uncertain","dispatch_started":true,"resubmit_safe":false,"error_code":"missing_receipt"}}\n\n';
    xhr.onprogress?.();

    await expect(first).resolves.toEqual({
      value: expect.objectContaining({
        type: 'tool',
        toolName: 'health_record',
        toolSuccess: false,
        writeOutcome: 'uncertain',
        dispatchStarted: true,
        resubmitSafe: false,
        errorCode: 'missing_receipt',
        thought: '记录状态需要核对',
      }),
      done: false,
    });
    await iter.return?.(undefined as any);
  });

  it('parses only an active retry-source recovery action as terminal retryable', async () => {
    const iter = streamChat('记录喝水 1200 毫升');
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    xhr.responseText =
      'data: {"event":"done","data":{"conversation_id":42,"message_id":99,"completion_status":"error","turn_outcome":{"category":"action_not_executed","reason_code":"write_without_tool","retryable":true},"recovery_action":{"type":"retry_source_turn","status":"active"}}}\n\n';
    xhr.onprogress?.();

    await expect(first).resolves.toEqual({
      value: expect.objectContaining({
        type: 'done',
        terminalRetryable: true,
        retryMode: 'retry_source',
        terminalErrorCode: 'write_without_tool',
      }),
      done: false,
    });
    await iter.return?.(undefined as any);
  });

  it('distinguishes health-manage queries from writes at tool-call time', async () => {
    const queryIter = streamChat('查询饮食');
    const queryEvent = queryIter.next();
    await Promise.resolve();
    const queryXhr = MockXMLHttpRequest.instances[0];
    queryXhr.responseText =
      'data: {"event":"tool_call","data":{"tool":"health_manage","args":"{\\"operation\\":\\"list\\"}"}}\n\n';
    queryXhr.onprogress?.();
    await expect(queryEvent).resolves.toEqual({
      value: expect.objectContaining({
        type: 'tool',
        toolName: 'health_manage',
        writeAttempted: false,
      }),
      done: false,
    });
    await queryIter.return?.(undefined as any);

    const writeIter = streamChat('删除饮食');
    const writeEvent = writeIter.next();
    await Promise.resolve();
    const writeXhr = MockXMLHttpRequest.instances[1];
    writeXhr.responseText =
      'data: {"event":"tool_call","data":{"tool":"health_manage","args":"{\\"operation\\":\\"delete\\"}"}}\n\n';
    writeXhr.onprogress?.();
    await expect(writeEvent).resolves.toEqual({
      value: expect.objectContaining({
        type: 'tool',
        toolName: 'health_manage',
        writeAttempted: true,
      }),
      done: false,
    });
    await writeIter.return?.(undefined as any);
  });

  it('declares GenUI support so the backend can return deterministic charts', async () => {
    const iter = streamChat('帮我绘制最近半年的HRV曲线');
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];

    // caps 头 = buildClientCapsHeader 单一真源(此前硬编码基础 caps → 结构化卡 cap 从不到后端,
    // 卡在生产死。这条锁死:点亮的 metric_table / diet / sleep caps 必须真的发出去,禁止再硬编码)。
    const capsCall = (xhr.setRequestHeader as jest.Mock).mock.calls.find(
      (c: any[]) => c[0] === 'X-Reva-Client-Caps',
    );
    expect(capsCall).toBeTruthy();
    expect(capsCall![1]).toBe(buildClientCapsHeader());
    for (const token of [
      'genui-v1', 'genui-components-v1', 'genui-record-quality-v1',
      'genui-table-v1', 'genui-diet-summary-v1', 'genui-sleep-summary-v1',
      'genui-medication-list-v1',
    ]) {
      expect(capsCall![1]).toContain(token);
    }

    xhr.responseText =
      'data: {"event":"done","data":{"conversation_id":42,"message_id":99}}\n\n';
    xhr.onprogress?.();
    await first;
    await iter.return?.(undefined as any);
  });

  it('preserves an explicit request_persisted false on done', async () => {
    const iter = streamChat('保留草稿');
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    xhr.responseText =
      'data: {"event":"done","data":{"conversation_id":42,"message_id":99,"request_persisted":false}}\n\n';
    xhr.onprogress?.();

    await expect(first).resolves.toEqual({
      value: expect.objectContaining({
        type: 'done',
        conversationId: 42,
        messageId: 99,
        requestPersisted: false,
      }),
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

  it('uses the health evidence card as the Mobile projection of the done manifest', async () => {
    const iter = streamChat('我腰疼怎么办');
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    const manifest = {
      version: 'health-evidence.v1',
      risk_level: 'medium',
      missing_discriminators: [{
        question: '近期是否有严重外伤？',
        choices: ['有', '没有', '不确定'],
      }],
    };
    xhr.responseText = `data: ${JSON.stringify({
      event: 'done',
      data: {
        conversation_id: 42,
        message_id: 100,
        health_evidence_manifest: manifest,
        cards: [{ type: 'health_evidence', data: manifest, actions: [] }],
      },
    })}\n\n`;
    xhr.onprogress?.();

    await expect(first).resolves.toEqual({
      value: expect.objectContaining({
        type: 'done',
        cards: [{
          type: 'health_evidence',
          data: manifest,
          actions: [],
        }],
      }),
      done: false,
    });
    await iter.return?.(undefined as any);
  });

  it('preserves verified write receipts from done for durable message rendering', async () => {
    const iter = streamChat('记录午餐');
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    xhr.responseText =
      'data: {"event":"done","data":{"conversation_id":42,"message_id":99,"write_receipts":[{"operation_id":"health_record:diet_record:701","status":"verified","resource_type":"diet_record","resource_id":"701","completed_at":"2026-07-09T12:00:00.000Z","verified":true}]}}\n\n';
    xhr.onprogress?.();

    await expect(first).resolves.toEqual({
      value: expect.objectContaining({
        type: 'done',
        writeReceipts: [{
          operationId: 'health_record:diet_record:701',
          status: 'verified',
          resourceType: 'diet_record',
          resourceId: '701',
          completedAt: '2026-07-09T12:00:00.000Z',
          verified: true,
        }],
      }),
      done: false,
    });
    await iter.return?.(undefined as any);
  });

  it('preserves exact namespaced medication terminal evidence from done', async () => {
    const iter = streamChat('确认');
    const first = iter.next();

    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];
    xhr.responseText =
      'data: {"event":"done","data":{"conversation_id":42,"message_id":99,"medication_batch_decision":{"intent_id":42,"status":"executed","write_receipts":[{"operation_id":"write_intent:medication_intake_batch:42:101","status":"verified","resource_type":"medication_log","resource_id":"101","completed_at":"2026-07-21T21:15:01-04:00","verified":true}],"safety_alerts":[{"rule_id":"ddi.medication","category":"ddi","severity":{"value":3,"label":"high","label_zh":"警告"},"title":"用药提示","message":"用药消息"}]},"write_receipts":[{"operation_id":"health_record:diet_record:701","status":"verified","resource_type":"diet_record","resource_id":"701","completed_at":"2026-07-21T21:15:00-04:00","verified":true}]}}\n\n';
    xhr.onprogress?.();

    await expect(first).resolves.toEqual({
      value: expect.objectContaining({
        type: 'done',
        medicationBatchDecision: {
          intentId: 42,
          decisionStatus: 'executed',
          writeReceipts: [{
            operationId: 'write_intent:medication_intake_batch:42:101',
            status: 'verified',
            resourceType: 'medication_log',
            resourceId: '101',
            completedAt: '2026-07-21T21:15:01-04:00',
            verified: true,
          }],
          safetyAlerts: [expect.objectContaining({ rule_id: 'ddi.medication' })],
        },
      }),
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

  it('maps status stage events to slim status-line labels (P0-1 新契约: accepted/tool/synthesis)', async () => {
    const iter = streamChat('看看我今天走了多少步');
    const first = iter.next();
    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];

    // accepted (流一打开) → 正在理解…
    xhr.responseText =
      'data: {"event":"status","data":{"stage":"accepted"}}\n\n';
    xhr.onprogress?.();
    await expect(first).resolves.toEqual({
      value: { type: 'status', statusLabel: '正在理解…', statusStage: 'accepted' },
      done: false,
    });

    // tool with label (后端确定性映射的中文动词短语) → 原样透传 label
    const second = iter.next();
    xhr.responseText +=
      'data: {"event":"status","data":{"stage":"tool","round":1,"label":"查看步数数据…"}}\n\n';
    xhr.onprogress?.();
    await expect(second).resolves.toEqual({
      value: { type: 'status', statusLabel: '查看步数数据…', statusStage: 'tool' },
      done: false,
    });

    // tool without label → 兜底 "正在处理…"
    const third = iter.next();
    xhr.responseText += 'data: {"event":"status","data":{"stage":"tool","round":2}}\n\n';
    xhr.onprogress?.();
    await expect(third).resolves.toEqual({
      value: { type: 'status', statusLabel: '正在处理…', statusStage: 'tool' },
      done: false,
    });

    // synthesis → 正在整理回答…
    const fourth = iter.next();
    xhr.responseText += 'data: {"event":"status","data":{"stage":"synthesis"}}\n\n';
    xhr.onprogress?.();
    await expect(fourth).resolves.toEqual({
      value: { type: 'status', statusLabel: '正在整理回答…', statusStage: 'synthesis' },
      done: false,
    });

    await iter.return?.(undefined as any);
  });

  it('parses the flat status family the backend actually emits ({"type":"status",...}, web/mac 同源)', async () => {
    const iter = streamChat('看看我今天走了多少步');
    const first = iter.next();
    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];

    // 后端 agent_executor 发的是扁平 shape (无 event 包装) —— 两个家族语义等价, 都必须能解析。
    xhr.responseText = 'data: {"type":"status","stage":"accepted"}\n\n';
    xhr.onprogress?.();
    await expect(first).resolves.toEqual({
      value: { type: 'status', statusLabel: '正在理解…', statusStage: 'accepted' },
      done: false,
    });

    const second = iter.next();
    xhr.responseText +=
      'data: {"type":"status","stage":"tool","round":1,"label":"查看健康数据…"}\n\n';
    xhr.onprogress?.();
    await expect(second).resolves.toEqual({
      value: { type: 'status', statusLabel: '查看健康数据…', statusStage: 'tool' },
      done: false,
    });

    const third = iter.next();
    xhr.responseText += 'data: {"type":"status","stage":"synthesis"}\n\n';
    xhr.onprogress?.();
    await expect(third).resolves.toEqual({
      value: { type: 'status', statusLabel: '正在整理回答…', statusStage: 'synthesis' },
      done: false,
    });

    await iter.return?.(undefined as any);
  });

  it('keeps backward-compat status stages (vision/thinking) as status-line labels', async () => {
    const iter = streamChat('看看这张体检照片');
    const first = iter.next();
    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];

    // vision → 识别图片中…
    xhr.responseText =
      'data: {"event":"status","data":{"stage":"vision"}}\n\n';
    xhr.onprogress?.();
    await expect(first).resolves.toEqual({
      value: { type: 'status', statusLabel: '识别图片中…', statusStage: 'vision' },
      done: false,
    });

    // thinking → 正在思考…
    const second = iter.next();
    xhr.responseText += 'data: {"event":"status","data":{"stage":"thinking","round":2}}\n\n';
    xhr.onprogress?.();
    await expect(second).resolves.toEqual({
      value: { type: 'status', statusLabel: '正在思考…', statusStage: 'thinking' },
      done: false,
    });

    await iter.return?.(undefined as any);
  });

  it('prefers the deterministic label over a legacy detail field for the tool stage', async () => {
    const iter = streamChat('查一下睡眠');
    const first = iter.next();
    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];

    // label 优先于 detail (兼容旧后端只发 detail 的场景 → 也能出状态行)
    xhr.responseText =
      'data: {"event":"status","data":{"stage":"tool","detail":"查睡眠数据"}}\n\n';
    xhr.onprogress?.();
    await expect(first).resolves.toEqual({
      value: { type: 'status', statusLabel: '查睡眠数据', statusStage: 'tool' },
      done: false,
    });

    await iter.return?.(undefined as any);
  });

  it('ignores unknown status stages (保持 fall-through 忽略行为)', async () => {
    const iter = streamChat('随便问问');
    const first = iter.next();
    await Promise.resolve();
    const xhr = MockXMLHttpRequest.instances[0];

    // 未知 stage 应被丢弃 (无 event 产出), 后续 token 正常
    xhr.responseText =
      'data: {"event":"status","data":{"stage":"quantum-flux"}}\n\n' +
      'data: {"event":"token","data":{"content":"你好"}}\n\n';
    xhr.onprogress?.();

    await expect(first).resolves.toEqual({
      value: { type: 'token', content: '你好' },
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
