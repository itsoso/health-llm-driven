import api from './api';

export interface ConnectorPolicy {
  id?: number;
  connection_id?: number;
  scopes?: string[];
  rate_limit?: string;
  token_status?: string;
  degraded_behavior?: string;
  data_minimization?: string;
  revoke_deletes_derived?: boolean;
  audit_required?: boolean;
}

export interface ConsentGrant {
  id: number;
  connection_id: number;
  grantee_type: string;
  grantee_id?: string | null;
  scopes: string[];
  purpose: string;
  status: string;
  granted_at?: string | null;
  revoked_at?: string | null;
  expires_at?: string | null;
}

export type ConnectionHealthStatus = 'healthy' | 'degraded' | 'revoked' | 'unknown';
export type ConnectionHealthSeverity = 'ok' | 'warning' | 'blocked';
export type ConnectionHealthAction = 'none' | 'retry_later' | 'reconnect';

export interface ConnectionHealth {
  status: ConnectionHealthStatus;
  severity: ConnectionHealthSeverity;
  message_code: string;
  can_attempt_sync: boolean;
  can_use_cached_data: boolean;
  needs_reconnect: boolean;
  user_action: ConnectionHealthAction;
  connection_status?: string;
  token_status?: string;
  degraded_behavior?: string;
  last_success_at?: string | null;
  last_attempt_at?: string | null;
  sync_error?: string | null;
}

export interface DataConnection {
  id: number;
  provider: string;
  provider_type: string;
  display_name: string;
  connection_status: string;
  scopes: string[];
  token_status: string;
  last_success_at?: string | null;
  last_attempt_at?: string | null;
  sync_error?: string | null;
  source_ref?: string | null;
  metadata?: Record<string, unknown>;
  active_consents: ConsentGrant[];
  policy: ConnectorPolicy | null;
  connection_health?: ConnectionHealth;
}

export interface DataConnectionsResponse {
  connections: DataConnection[];
}

export const HEALTHKIT_CONSENT_SCOPES = [
  'healthkit.daily.read',
  'healthkit.ecg.read',
  'healthkit.blood_pressure.read',
  'healthkit.spo2.read',
  'healthkit.body.read',
];

const HEALTHKIT_PROVIDER = 'healthkit';

export async function fetchDataConnections(): Promise<DataConnectionsResponse> {
  const { data } = await api.get<DataConnectionsResponse>('/data-connections/me');
  return data;
}

function hasAllScopes(actual: string[] = [], required: string[] = HEALTHKIT_CONSENT_SCOPES): boolean {
  const actualSet = new Set(actual);
  return required.every((scope) => actualSet.has(scope));
}

export function hasActiveHealthKitConsent(data?: DataConnectionsResponse | null): boolean {
  const connections = data?.connections ?? [];
  return connections.some((connection) => (
    connection.provider === HEALTHKIT_PROVIDER
    && connection.connection_status === 'active'
    && connection.token_status !== 'revoked'
    && hasAllScopes(connection.scopes)
    && connection.active_consents.some((grant) => (
      grant.status === 'active'
      && grant.grantee_type === 'self'
      && hasAllScopes(grant.scopes)
      && (!grant.expires_at || new Date(grant.expires_at).getTime() > Date.now())
    ))
  ));
}

export async function hasActiveHealthKitServerConsent(): Promise<boolean> {
  return hasActiveHealthKitConsent(await fetchDataConnections());
}

export async function ensureHealthKitServerConsent(): Promise<DataConnection> {
  const existing = await fetchDataConnections();
  const active = existing.connections.find((connection) => (
    connection.provider === HEALTHKIT_PROVIDER
    && connection.connection_status === 'active'
    && connection.token_status !== 'revoked'
    && hasAllScopes(connection.scopes)
  ));
  if (active && hasActiveHealthKitConsent({ connections: [active] })) {
    return active;
  }

  const { data: connection } = await api.post<DataConnection>('/data-connections/me', {
    provider: HEALTHKIT_PROVIDER,
    provider_type: HEALTHKIT_PROVIDER,
    display_name: 'Apple Health',
    scopes: HEALTHKIT_CONSENT_SCOPES,
    token_status: 'not_required',
    source_ref: 'ios-healthkit',
    metadata: {
      origin: 'ios_healthkit_authorization',
      client: 'mobile',
    },
  });

  if (!hasActiveHealthKitConsent({ connections: [connection] })) {
    await api.post(`/data-connections/${connection.id}/consents`, {
      grantee_type: 'self',
      grantee_id: null,
      scopes: HEALTHKIT_CONSENT_SCOPES,
      purpose: 'sync HealthKit data into Reva',
    });
  }
  return connection;
}

export async function revokeDataConnection(connectionId: number): Promise<DataConnection> {
  const { data } = await api.post<DataConnection>(`/data-connections/${connectionId}/revoke`);
  return data;
}

function fallbackConnectionHealth(connection: DataConnection): ConnectionHealth {
  const connectionStatus = connection.connection_status ?? 'unknown';
  const tokenStatus = connection.token_status ?? 'none';
  if (connectionStatus === 'revoked' || tokenStatus === 'revoked') {
    return {
      status: 'revoked',
      severity: 'blocked',
      message_code: 'connection_revoked',
      can_attempt_sync: false,
      can_use_cached_data: false,
      needs_reconnect: true,
      user_action: 'reconnect',
      connection_status: connectionStatus,
      token_status: tokenStatus,
      degraded_behavior: connection.policy?.degraded_behavior,
      sync_error: connection.sync_error,
    };
  }
  if (connectionStatus === 'active' && tokenStatus !== 'expired') {
    return {
      status: 'healthy',
      severity: 'ok',
      message_code: 'connection_healthy',
      can_attempt_sync: true,
      can_use_cached_data: true,
      needs_reconnect: false,
      user_action: 'none',
      connection_status: connectionStatus,
      token_status: tokenStatus,
      degraded_behavior: connection.policy?.degraded_behavior,
      sync_error: connection.sync_error,
    };
  }
  const needsReconnect = tokenStatus === 'expired';
  return {
    status: connectionStatus === 'degraded' || needsReconnect ? 'degraded' : 'unknown',
    severity: 'warning',
    message_code: needsReconnect ? 'reconnect_required' : 'temporarily_degraded',
    can_attempt_sync: !needsReconnect,
    can_use_cached_data: connection.policy?.degraded_behavior !== 'fail_closed',
    needs_reconnect: needsReconnect,
    user_action: needsReconnect ? 'reconnect' : 'retry_later',
    connection_status: connectionStatus,
    token_status: tokenStatus,
    degraded_behavior: connection.policy?.degraded_behavior,
    sync_error: connection.sync_error,
  };
}

export function getConnectionHealth(connection: DataConnection): ConnectionHealth {
  return connection.connection_health ?? fallbackConnectionHealth(connection);
}

export function connectionHealthDisplay(connection: DataConnection) {
  const health = getConnectionHealth(connection);
  const cacheLabel = health.can_use_cached_data ? '缓存可只读使用' : '缓存不可用';
  if (health.message_code === 'connection_healthy') {
    return {
      health,
      label: '可用',
      description: '连接正常，数据可用于运行时判断',
      actionLabel: '无需操作',
      cacheLabel,
    };
  }
  if (health.message_code === 'reconnect_required') {
    return {
      health,
      label: '需重连',
      description: '授权已失效，需要重新授权；已授权缓存仍可只读使用',
      actionLabel: '重新授权',
      cacheLabel,
    };
  }
  if (health.message_code === 'connection_revoked') {
    return {
      health,
      label: '已撤权',
      description: '连接已撤权，系统不会继续使用该连接的数据',
      actionLabel: '重新连接',
      cacheLabel,
    };
  }
  if (health.message_code === 'temporarily_degraded') {
    return {
      health,
      label: '暂不可用',
      description: '连接暂时不可用，系统会等待后重试',
      actionLabel: '稍后重试',
      cacheLabel,
    };
  }
  return {
    health,
    label: '需检查',
    description: '连接状态不明确，请检查数据源配置',
    actionLabel: '检查',
    cacheLabel,
  };
}

export function connectionStatusSummary(data?: DataConnectionsResponse | null): string {
  const connections = data?.connections ?? [];
  if (connections.length === 0) return '未连接';
  const active = connections.filter((connection) => getConnectionHealth(connection).status === 'healthy').length;
  const needsAttention = connections.filter((connection) => (
    getConnectionHealth(connection).status !== 'healthy'
  )).length;
  if (needsAttention > 0) return `${active} 个可用 · ${needsAttention} 个需处理`;
  return `${active} 个可用`;
}
