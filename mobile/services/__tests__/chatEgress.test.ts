/* eslint-disable import/first */
const mockGetToken = jest.fn().mockResolvedValue('token');

jest.mock('../auth', () => ({ getToken: () => mockGetToken() }));
jest.mock('../api', () => ({ BASE_URL: 'https://example.invalid' }));

import { getConversationsPage, streamChat } from '../chat';
import { setAppEgressAuditSink, setAppEgressMode } from '../egressPolicy';

describe('chat direct fetch egress guard', () => {
  beforeEach(() => {
    mockGetToken.mockClear();
  });

  afterEach(() => {
    setAppEgressMode(null);
    setAppEgressAuditSink(null);
    jest.restoreAllMocks();
  });

  it('blocks strict local mode before reading credentials or calling fetch', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch');
    setAppEgressMode('strict_local');

    await expect(getConversationsPage()).rejects.toThrow('strict_local_egress_blocked');

    expect(mockGetToken).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('blocks the streaming XHR path before reading credentials or opening a request', async () => {
    const open = jest.fn();
    const originalXHR = global.XMLHttpRequest;
    global.XMLHttpRequest = jest.fn(() => ({ open })) as unknown as typeof XMLHttpRequest;
    setAppEgressMode('strict_local');

    try {
      await expect(streamChat('私人饮食').next()).rejects.toThrow('strict_local_egress_blocked');
      expect(mockGetToken).not.toHaveBeenCalled();
      expect(open).not.toHaveBeenCalled();
    } finally {
      global.XMLHttpRequest = originalXHR;
    }
  });
});
