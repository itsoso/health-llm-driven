// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { agentApi } from './ai';

describe('agentApi.streamMessage', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('declares GenUI capabilities so web chat can receive chart cards', async () => {
    localStorage.setItem('auth_token', 'tok_test');
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
      'X-Reva-Client-Caps': 'genui-v1, genui-components-v1',
    });
  });

  it('keeps the metric_table cap dark until eval passes (no genui-table-v1 token)', async () => {
    localStorage.setItem('auth_token', 'tok_test');
    const stream = new ReadableStream({ start(controller) { controller.close(); } });
    const fetchMock = vi.fn().mockResolvedValue(new Response(stream, { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const iterator = agentApi.streamMessage('近三天关键指标做个表');
    await iterator.next();

    const caps = (fetchMock.mock.calls[0][1]?.headers as Record<string, string>)['X-Reva-Client-Caps'];
    expect(caps).not.toContain('genui-table-v1');
  });
});
