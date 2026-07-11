import { loadAgentHomeBootstrap } from '../agentHomeBootstrap';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('loadAgentHomeBootstrap', () => {
  it('publishes one snapshot only after every initial source settles', async () => {
    const history = deferred<void>();
    const starters = deferred<any>();
    const memory = deferred<any[]>();
    const llm = deferred<any>();
    let settled = false;

    const resultPromise = loadAgentHomeBootstrap({
      loadLatestConversation: () => history.promise,
      fetchStarters: () => starters.promise,
      fetchMemory: () => memory.promise,
      fetchLlmPreference: () => llm.promise,
    }).then(result => {
      settled = true;
      return result;
    });

    starters.resolve({
      opener: { text: '今天先确认午餐记录。' },
      suggestions: [{ text: '查询全天饮食', key: 'diet', priority: 10 }],
      onboarding: false,
    });
    memory.resolve([{ id: 1, content: '关注晚餐时间' }]);
    llm.resolve({ model_id: 'qwen3.7-plus', options: [] });
    await Promise.resolve();
    expect(settled).toBe(false);

    history.resolve();
    await expect(resultPromise).resolves.toMatchObject({
      opener: { text: '今天先确认午餐记录。' },
      suggestions: [{ text: '查询全天饮食', key: 'diet', priority: 10 }],
      memory: [{ id: 1, content: '关注晚餐时间' }],
      llmPreference: { model_id: 'qwen3.7-plus', options: [] },
      errors: [],
    });
  });

  it('settles with explicit fallbacks when individual sources fail', async () => {
    const result = await loadAgentHomeBootstrap({
      loadLatestConversation: async () => { throw new Error('history unavailable'); },
      fetchStarters: async () => { throw new Error('starter unavailable'); },
      fetchMemory: async () => [],
      fetchLlmPreference: async () => { throw new Error('model unavailable'); },
    });

    expect(result).toEqual({
      opener: null,
      suggestions: null,
      onboarding: false,
      memory: [],
      llmPreference: { model_id: null, options: [] },
      errors: ['history', 'starters', 'llm_preference'],
    });
  });
});
