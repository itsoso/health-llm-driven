/* eslint-disable import/first */
jest.mock('../auth', () => ({
  getToken: jest.fn().mockResolvedValue('test-token'),
}));

jest.mock('../api', () => ({
  BASE_URL: 'https://example.test/api/v1',
}));

import {
  getConversationMessages,
  getConversations,
  getConversationsPage,
} from '../chat';

describe('getConversationsPage', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    jest.clearAllMocks();
  });

  it('passes offset/limit/title_like through as query params', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0, limit: 20, offset: 40 }),
    });
    global.fetch = fetchMock as any;

    await getConversationsPage({ offset: 40, limit: 20, titleLike: '简报' });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const url: string = fetchMock.mock.calls[0][0];
    expect(url).toContain('/agent/conversations?');
    expect(url).toContain('limit=20');
    expect(url).toContain('offset=40');
    expect(url).toContain('title_like=');
    // 中文 title 被 URL 编码
    expect(decodeURIComponent(url)).toContain('title_like=简报');
  });

  it('passes search (title∪content) through as query param', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0, limit: 20, offset: 0 }),
    });
    global.fetch = fetchMock as any;

    await getConversationsPage({ search: '胃痛' });

    const url: string = fetchMock.mock.calls[0][0];
    expect(url).toContain('search=');
    expect(decodeURIComponent(url)).toContain('search=胃痛');
    expect(url).not.toContain('title_like');
  });

  it('search takes precedence over title_like when both given', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0, limit: 20, offset: 0 }),
    });
    global.fetch = fetchMock as any;

    await getConversationsPage({ search: '喷嚏', titleLike: '简报' });

    const url: string = fetchMock.mock.calls[0][0];
    expect(decodeURIComponent(url)).toContain('search=喷嚏');
    // search 生效时不再发 title_like(后端 search 已覆盖标题)
    expect(url).not.toContain('title_like');
  });

  it('omits search when empty string', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0, limit: 20, offset: 0 }),
    });
    global.fetch = fetchMock as any;

    await getConversationsPage({ search: '' });

    const url: string = fetchMock.mock.calls[0][0];
    expect(url).not.toContain('search=');
  });

  it('defaults offset=0 limit=20 and omits title_like when absent', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0, limit: 20, offset: 0 }),
    });
    global.fetch = fetchMock as any;

    await getConversationsPage();

    const url: string = fetchMock.mock.calls[0][0];
    expect(url).toContain('limit=20');
    expect(url).toContain('offset=0');
    expect(url).not.toContain('title_like');
  });

  it('returns items + total from the paginated envelope', async () => {
    const items = [
      { id: 1, title: 'a', created_at: '2026-04-25T01:00:00Z' },
      { id: 2, title: 'b', created_at: '2026-04-24T01:00:00Z' },
    ];
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items, total: 57, limit: 20, offset: 0 }),
    }) as any;

    const page = await getConversationsPage({ offset: 0, limit: 20 });
    expect(page.items).toEqual(items);
    expect(page.total).toBe(57);
  });

  it('falls back total to items.length when backend omits total', async () => {
    const items = [{ id: 1, title: 'a', created_at: '2026-04-25T01:00:00Z' }];
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items }),
    }) as any;

    const page = await getConversationsPage();
    expect(page.total).toBe(1);
  });

  it('throws (fail-loud) on non-ok response — caller keeps loaded list', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
    }) as any;

    await expect(getConversationsPage({ offset: 20 })).rejects.toThrow(/500/);
  });
});

describe('getConversations (compat wrapper)', () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
    jest.clearAllMocks();
  });

  it('returns first-page items', async () => {
    const items = [{ id: 9, title: 'x', created_at: '2026-04-25T01:00:00Z' }];
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items, total: 1 }),
    }) as any;

    const out = await getConversations();
    expect(out).toEqual(items);
  });

  it('swallows errors and returns [] (legacy callers do not handle throw)', async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 502, json: async () => ({}) }) as any;
    const out = await getConversations('每日健康简报');
    expect(out).toEqual([]);
  });
});

describe('getConversationMessages', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    jest.clearAllMocks();
  });

  it('passes cursor pagination and returns the server page metadata', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        messages: [{ id: 18, role: 'assistant', content: 'ok' }],
        total_messages: 91,
        has_more: true,
        oldest_message_id: 18,
      }),
    });
    global.fetch = fetchMock as any;

    const page = await getConversationMessages(7, {
      limit: 80,
      beforeMessageId: 99,
    });

    expect(fetchMock.mock.calls[0][0]).toBe(
      'https://example.test/api/v1/agent/conversations/7?limit=80&before_message_id=99',
    );
    expect(page.has_more).toBe(true);
    expect(page.oldest_message_id).toBe(18);
  });

  it('throws on a non-ok response so loaded history is not replaced by empty data', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({}),
    }) as any;

    await expect(getConversationMessages(7, { limit: 80 })).rejects.toThrow(/503/);
  });
});
