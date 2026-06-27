import api from '../api';
import { connectionStatusSummary, fetchDataConnections } from '../dataConnections';

jest.mock('../api', () => ({
  get: jest.fn(),
}));

describe('dataConnections service', () => {
  beforeEach(() => jest.clearAllMocks());

  it('normalizes current-user connection lists from wrapper payloads', async () => {
    (api.get as jest.Mock).mockResolvedValue({
      data: {
        connections: [
          { id: 1, provider: 'healthkit', status: 'connected', sync_enabled: true },
        ],
      },
    });

    const rows = await fetchDataConnections();

    expect(api.get).toHaveBeenCalledWith('/data-connections/me');
    expect(rows).toEqual([
      { id: 1, provider: 'healthkit', status: 'connected', sync_enabled: true },
    ]);
  });

  it('fails closed to an empty list so settings never crashes', async () => {
    (api.get as jest.Mock).mockRejectedValue(new Error('not wired yet'));

    await expect(fetchDataConnections()).resolves.toEqual([]);
  });

  it('summarizes connected, pending, empty, and disabled states', () => {
    expect(connectionStatusSummary(null)).toBe('未连接');
    expect(connectionStatusSummary([
      { status: 'connected', sync_enabled: true },
      { status: 'stale', sync_enabled: true },
    ])).toBe('1/2 已连接');
    expect(connectionStatusSummary([
      { status: 'stale', sync_enabled: true },
      { status: 'error', sync_enabled: true },
    ])).toBe('2/2 待同步');
    expect(connectionStatusSummary([{ status: 'connected', sync_enabled: false }])).toBe('已关闭');
  });
});
