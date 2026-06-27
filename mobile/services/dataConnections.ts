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

export async function fetchDataConnections(): Promise<DataConnectionsResponse> {
  const { data } = await api.get<DataConnectionsResponse>('/data-connections/me');
  return data;
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
