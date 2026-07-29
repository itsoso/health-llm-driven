/* eslint-disable import/first */
const mockGetToken = jest.fn().mockResolvedValue('token');

jest.mock('../auth', () => ({ getToken: () => mockGetToken() }));
jest.mock('../api', () => ({ BASE_URL: 'https://example.invalid' }));

import { getConversationsPage, streamChat } from '../chat';
import { setAppEgressMode } from '../egressPolicy';

describe('chat direct fetch egress guard', () => {
  beforeEach(() => {
    mockGetToken.mockClear();
    setAppEgressMode(null);
  });

  afterEach(() => {
    setAppEgressMode(null);
    jest.restoreAllMocks();
  });

  it('blocks requests before a cloud session exists', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch');

    await expect(getConversationsPage()).rejects.toThrow('cloud_session_required');

    expect(mockGetToken).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
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
