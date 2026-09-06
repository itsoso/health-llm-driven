// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { agentApi } from './ai';

// These tests exercise stream transport; real permission behavior is covered separately.
vi.mock('@/services/aiConsent', async importOriginal => ({
  ...await importOriginal<typeof import('@/services/aiConsent')>(),
  requireAiConsent: vi.fn().mockResolvedValue(undefined),
}));

describe('agentApi.streamMessage', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('declares GenUI capabilities so web chat can receive chart cards', async () => {
    const stream = new ReadableStream({
      start(controller) {
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(stream, { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const iterator = agentApi.streamMessage('最近一周睡眠时长曲线 以及评估睡眠');
    await iterator.next();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][1]?.headers).toMatchObject({
      'X-Reva-Client-Caps': 'genui-v1, genui-components-v1, genui-table-v1',
    });
  });

  it('declares the metric_table capability after the eval gate passed', async () => {
    const stream = new ReadableStream({ start(controller) { controller.close(); } });
    const fetchMock = vi.fn().mockResolvedValue(new Response(stream, { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const iterator = agentApi.streamMessage('近三天关键指标做个表');
    await iterator.next();

    const caps = (fetchMock.mock.calls[0][1]?.headers as Record<string, string>)['X-Reva-Client-Caps'];
    expect(caps).toContain('genui-table-v1');
  });

  it('sends device current time context with every stream request', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-16T15:40:00.000Z'));
    const stream = new ReadableStream({ start(controller) { controller.close(); } });
    const fetchMock = vi.fn().mockResolvedValue(new Response(stream, { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const iterator = agentApi.streamMessage('我明天几点起床比较合理？');
    await iterator.next();

    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body.client_time_context).toMatchObject({
      client_now_iso: '2026-07-16T15:40:00.000Z',
    });
    expect(typeof body.client_time_context.timezone).toBe('string');
    expect(typeof body.client_time_context.timezone_offset_minutes).toBe('number');
    // Web 恒打字通道 → 后端 symptom/rhinitis 免确认(漏传 channel=None 会 fail-closed 重复追问)。
    expect(body.channel).toBe('typed');
  });
});
