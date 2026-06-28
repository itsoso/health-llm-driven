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

export function connectionStatusSummary(data?: DataConnectionsResponse | null): string {
  const connections = data?.connections ?? [];
  if (connections.length === 0) return '未连接';
  const active = connections.filter((connection) => connection.connection_status === 'active').length;
  const needsAttention = connections.filter((connection) => (
    connection.connection_status !== 'active' || ['expired', 'revoked'].includes(connection.token_status)
  )).length;
  if (needsAttention > 0) return `${active} 个可用 · ${needsAttention} 个需处理`;
  return `${active} 个可用`;
}
