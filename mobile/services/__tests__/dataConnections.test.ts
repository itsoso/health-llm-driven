import {
  connectionHealthDisplay,
  connectionStatusSummary,
  ensureHealthKitServerConsent,
  fetchDataConnections,
  hasActiveHealthKitConsent,
  HEALTHKIT_CONSENT_SCOPES,
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

  it('summarizes connection status for settings', () => {
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

  it('prefers backend connection health when summarizing settings status', () => {
    expect(connectionStatusSummary({
      connections: [
        {
          id: 1,
          provider: 'healthkit',
          provider_type: 'healthkit',
          display_name: 'Apple Health',
          connection_status: 'active',
          scopes: ['heart_rate.read'],
          token_status: 'valid',
          active_consents: [],
          policy: null,
          connection_health: {
            status: 'degraded',
            severity: 'warning',
            message_code: 'reconnect_required',
            can_attempt_sync: false,
            can_use_cached_data: true,
            needs_reconnect: true,
            user_action: 'reconnect',
          },
        },
      ],
    })).toBe('0 个可用 · 1 个需处理');
  });

  it('maps connection health into user-facing mobile copy', () => {
    const display = connectionHealthDisplay({
      id: 1,
      provider: 'healthkit',
      provider_type: 'healthkit',
      display_name: 'Apple Health',
      connection_status: 'degraded',
      scopes: ['heart_rate.read'],
      token_status: 'expired',
      active_consents: [],
      policy: null,
      connection_health: {
        status: 'degraded',
        severity: 'warning',
        message_code: 'reconnect_required',
        can_attempt_sync: false,
        can_use_cached_data: true,
        needs_reconnect: true,
        user_action: 'reconnect',
      },
    });

    expect(display.label).toBe('需重连');
    expect(display.actionLabel).toBe('重新授权');
    expect(display.cacheLabel).toBe('缓存可只读使用');
    expect(display.description).toContain('授权已失效');
  });

  it('revokes connection through governed endpoint', async () => {
    (api.post as jest.Mock).mockResolvedValueOnce({ data: { id: 1, connection_status: 'revoked' } });

    const result = await revokeDataConnection(1);

    expect(api.post).toHaveBeenCalledWith('/data-connections/1/revoke');
    expect(result.connection_status).toBe('revoked');
  });

  it('recognizes active HealthKit self consent with all required scopes', () => {
    expect(hasActiveHealthKitConsent({
      connections: [{
        id: 7,
        provider: 'healthkit',
        provider_type: 'healthkit',
        display_name: 'Apple Health',
        connection_status: 'active',
        scopes: HEALTHKIT_CONSENT_SCOPES,
        token_status: 'not_required',
        active_consents: [{
          id: 9,
          connection_id: 7,
          grantee_type: 'self',
          grantee_id: null,
          scopes: HEALTHKIT_CONSENT_SCOPES,
          purpose: 'sync HealthKit data into Reva',
          status: 'active',
        }],
        policy: null,
      }],
    })).toBe(true);
  });

  it('does not treat revoked HealthKit consent as active', () => {
    expect(hasActiveHealthKitConsent({
      connections: [{
        id: 7,
        provider: 'healthkit',
        provider_type: 'healthkit',
        display_name: 'Apple Health',
        connection_status: 'revoked',
        scopes: HEALTHKIT_CONSENT_SCOPES,
        token_status: 'revoked',
        active_consents: [],
        policy: null,
      }],
    })).toBe(false);
  });

  it('creates Apple Health connection and self consent when user explicitly enables sync', async () => {
    (api.get as jest.Mock).mockResolvedValueOnce({ data: { connections: [] } });
    (api.post as jest.Mock)
      .mockResolvedValueOnce({
        data: {
          id: 7,
          provider: 'healthkit',
          provider_type: 'healthkit',
          display_name: 'Apple Health',
          connection_status: 'active',
          scopes: HEALTHKIT_CONSENT_SCOPES,
          token_status: 'not_required',
          active_consents: [],
          policy: null,
        },
      })
      .mockResolvedValueOnce({ data: { id: 9, status: 'active' } });

    const connection = await ensureHealthKitServerConsent();

    expect(connection.id).toBe(7);
    expect(api.post).toHaveBeenNthCalledWith(1, '/data-connections/me', expect.objectContaining({
      provider: 'healthkit',
      provider_type: 'healthkit',
      scopes: HEALTHKIT_CONSENT_SCOPES,
      token_status: 'not_required',
    }));
    expect(api.post).toHaveBeenNthCalledWith(2, '/data-connections/7/consents', expect.objectContaining({
      grantee_type: 'self',
      scopes: HEALTHKIT_CONSENT_SCOPES,
    }));
  });
});
