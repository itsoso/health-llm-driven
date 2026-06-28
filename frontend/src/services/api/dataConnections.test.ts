import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./client', () => ({
  api: {
    get: vi.fn(),
  },
}));

import { api } from './client';
import {
  connectionHealthDisplay,
  connectionStatusSummary,
  fetchDataConnections,
} from './dataConnections';

const mockGet = api.get as unknown as ReturnType<typeof vi.fn>;

describe('web data connections API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches governed data connections from the canonical endpoint', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
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
            policy: { degraded_behavior: 'read_only' },
          },
        ],
      },
    });

    const result = await fetchDataConnections();

    expect(mockGet).toHaveBeenCalledWith('/data-connections/me');
    expect(result.connections[0].provider).toBe('healthkit');
  });

  it('summarizes degraded backend connection health for settings and nav surfaces', () => {
    const data = {
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
    };

    expect(connectionStatusSummary(data)).toBe('0 个可用 · 1 个需处理');
  });

  it('maps connection health to web display copy without exposing raw tokens', () => {
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
});
