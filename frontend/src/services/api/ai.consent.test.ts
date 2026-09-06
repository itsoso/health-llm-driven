import { afterEach, expect, it, vi } from 'vitest';
import { agentApi } from './ai';

afterEach(() => vi.unstubAllGlobals());

it('does not dispatch a chat payload without a verified consent session', async () => {
  const transmitted: string[] = [];
  vi.stubGlobal('fetch', async (url: string) => {
    transmitted.push(url);
    return new Response(new ReadableStream({ start(controller) { controller.close(); } }));
  });
  await expect(agentApi.streamMessage('synthetic draft').next()).rejects.toThrow();
  expect(transmitted).not.toContain('/api/agent/stream');
});
