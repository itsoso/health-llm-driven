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

export type DataConnectionStatus =
  | 'active'
  | 'connected'
  | 'authorized'
  | 'syncing'
  | 'stale'
  | 'error'
  | 'degraded'
  | 'disconnected'
  | 'revoked'
  | string;

export interface DataConnection {
  id: number;
  provider: string;
  provider_type?: string;
  display_name?: string;
  connection_status?: DataConnectionStatus;
  status?: DataConnectionStatus | null;
  source?: string | null;
  name?: string | null;
  scopes?: string[];
  token_status?: string;
  sync_enabled?: boolean | null;
  last_success_at?: string | null;
  last_attempt_at?: string | null;
  last_sync_at?: string | null;
  updated_at?: string | null;
  sync_error?: string | null;
  source_ref?: string | null;
  metadata?: Record<string, unknown>;
  active_consents?: ConsentGrant[];
  policy?: ConnectorPolicy | null;
}

export interface DataConnectionsResponse {
  connections: DataConnection[];
}

function normalizeConnections(data: unknown): DataConnection[] {
  if (Array.isArray(data)) {
    return data.filter((item): item is DataConnection => item != null && typeof item === 'object');
  }
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    if (Array.isArray(obj.connections)) return normalizeConnections(obj.connections);
    if (Array.isArray(obj.items)) return normalizeConnections(obj.items);
    if (Array.isArray(obj.data)) return normalizeConnections(obj.data);
  }
  return [];
}

export async function fetchDataConnections(): Promise<DataConnectionsResponse> {
  try {
    const { data } = await api.get<DataConnectionsResponse>('/data-connections/me');
    return { connections: normalizeConnections(data) };
  } catch {
    return { connections: [] };
  }
}

export async function revokeDataConnection(connectionId: number): Promise<DataConnection> {
  const { data } = await api.post<DataConnection>(`/data-connections/${connectionId}/revoke`);
  return data;
}

function isGovernedShape(connection: DataConnection): boolean {
  return Boolean(connection.connection_status || connection.token_status || connection.provider_type);
}

function activeStatus(connection: DataConnection): string {
  return String(connection.connection_status || connection.status || '').toLowerCase();
}

export function connectionStatusSummary(data?: DataConnectionsResponse | DataConnection[] | null): string {
  const connections = Array.isArray(data) ? data : data?.connections ?? [];
  if (connections.length === 0) return '未连接';

  const enabled = connections.filter((connection) => connection.sync_enabled !== false);
  if (enabled.length === 0) return '已关闭';

  const hasGovernedShape = enabled.some(isGovernedShape);
  if (hasGovernedShape) {
    const active = enabled.filter((connection) => {
      const status = activeStatus(connection);
      return ['active', 'connected', 'authorized', 'syncing'].includes(status)
        && !['expired', 'revoked'].includes(String(connection.token_status || '').toLowerCase());
    }).length;
    const needsAttention = enabled.length - active;
    if (needsAttention > 0) return `${active} 个可用 · ${needsAttention} 个需处理`;
    return `${active} 个可用`;
  }

  const active = enabled.filter((connection) => (
    ['connected', 'authorized', 'syncing'].includes(activeStatus(connection))
  )).length;
  if (active > 0) return `${active}/${connections.length} 已连接`;
  return `${enabled.length}/${connections.length} 待同步`;
}
