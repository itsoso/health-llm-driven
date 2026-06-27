import {
  connectionStatusSummary,
  fetchDataConnections,
  revokeDataConnection,
} from '../dataConnections';
import api from '../api';

jest.mock('../api', () => ({
  get: jest.fn(),
  post: jest.fn(),
}));

describe('dataConnections service', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('fetches governed data connections', async () => {
    (api.get as jest.Mock).mockResolvedValueOnce({
      data: {
        connections: [
          {
            id: 1,
            provider: 'garmin',
            provider_type: 'wearable',
            display_name: 'Garmin',
            connection_status: 'active',
            scopes: ['sleep', 'hrv'],
            token_status: 'valid',
            active_consents: [],
            policy: { degraded_behavior: 'read_only' },
          },
        ],
      },
    });

    const result = await fetchDataConnections();

    expect(api.get).toHaveBeenCalledWith('/data-connections/me');
    expect(result.connections[0].provider).toBe('garmin');
  });

  it('fails closed to an empty response so settings never crashes', async () => {
    (api.get as jest.Mock).mockRejectedValueOnce(new Error('not wired yet'));

    await expect(fetchDataConnections()).resolves.toEqual({ connections: [] });
  });

  it('summarizes governed connection status for settings', () => {
    expect(connectionStatusSummary({ connections: [] })).toBe('未连接');
    expect(connectionStatusSummary({
      connections: [
        {
          id: 1,
          provider: 'garmin',
          provider_type: 'wearable',
          display_name: 'Garmin',
          connection_status: 'active',
          scopes: ['sleep'],
          token_status: 'valid',
          active_consents: [],
          policy: null,
        },
        {
          id: 2,
          provider: 'fhir_bundle',
          provider_type: 'fhir_bundle',
          display_name: 'FHIR Bundle',
          connection_status: 'degraded',
          scopes: ['labs.read'],
          token_status: 'expired',
          active_consents: [],
          policy: null,
        },
      ],
    })).toBe('1 个可用 · 1 个需处理');
  });

  it('summarizes legacy connection arrays from older settings payloads', () => {
    expect(connectionStatusSummary([
      { id: 1, provider: 'healthkit', status: 'connected', sync_enabled: true },
      { id: 2, provider: 'garmin', status: 'stale', sync_enabled: true },
    ])).toBe('1/2 已连接');
    expect(connectionStatusSummary([
      { id: 1, provider: 'healthkit', status: 'stale', sync_enabled: true },
      { id: 2, provider: 'garmin', status: 'error', sync_enabled: true },
    ])).toBe('2/2 待同步');
    expect(connectionStatusSummary([{ id: 1, provider: 'healthkit', status: 'connected', sync_enabled: false }])).toBe('已关闭');
  });

  it('revokes connection through governed endpoint', async () => {
    (api.post as jest.Mock).mockResolvedValueOnce({ data: { id: 1, provider: 'garmin', connection_status: 'revoked' } });

    const result = await revokeDataConnection(1);

    expect(api.post).toHaveBeenCalledWith('/data-connections/1/revoke');
    expect(result.connection_status).toBe('revoked');
  });
});
