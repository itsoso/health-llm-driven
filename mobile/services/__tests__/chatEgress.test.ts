/* eslint-disable import/first */
const mockGetToken = jest.fn<Promise<string | null>, []>();

jest.mock('../auth', () => ({ getToken: () => mockGetToken() }));
jest.mock('../api', () => ({ BASE_URL: 'https://example.invalid' }));

import { getConversationsPage, streamChat } from '../chat';
import { setAppEgressMode } from '../egressPolicy';

describe('chat direct fetch egress guard', () => {
  beforeEach(() => {
    mockGetToken.mockReset().mockResolvedValue(null);
    setAppEgressMode(null);
  });

  afterEach(() => {
    setAppEgressMode(null);
    jest.restoreAllMocks();
  });

  it('blocks requests when neither an active session nor persisted credential exists', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch');

    await expect(getConversationsPage()).rejects.toThrow('cloud_session_required');

    expect(mockGetToken).toHaveBeenCalledTimes(1);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('recovers the first history request from a persisted cloud credential', async () => {
    mockGetToken.mockResolvedValue('persisted-token');
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0 }),
    } as Response);

    await expect(getConversationsPage()).resolves.toEqual({ items: [], total: 0 });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy.mock.calls[0][1]).toMatchObject({
      cache: 'no-store',
      headers: { Authorization: 'Bearer persisted-token' },
    });
  });

  it('blocks streaming before reading credentials or opening a request', async () => {
    const open = jest.fn();
    const originalXHR = global.XMLHttpRequest;
    global.XMLHttpRequest = jest.fn(() => ({ open })) as unknown as typeof XMLHttpRequest;

    try {
      await expect(streamChat('私人饮食').next()).rejects.toThrow('cloud_session_required');
      expect(mockGetToken).not.toHaveBeenCalled();
      expect(open).not.toHaveBeenCalled();
    } finally {
      global.XMLHttpRequest = originalXHR;
    }
  });
});
