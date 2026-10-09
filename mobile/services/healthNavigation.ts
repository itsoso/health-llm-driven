import api from './api';

export type NavigationExecutionStatus = 'pending' | 'completed' | 'skipped' | 'deferred' | 'withdrawn' | 'unknown';
export interface HealthNavigationAction {
  action_ref: string;
  action_revision: string;
  share_title: string;
  share_completion_criterion: string;
  execution_status: NavigationExecutionStatus;
  safety_state: 'allowed' | 'restricted' | 'unknown';
  requires_health_review: boolean;
  scheduling_mode: 'flexible' | 'view_only';
  detail_ref: string;
}
export interface HealthWeekNavigation {
  schema_version: 'health_week_navigation.v1';
  local_date: string;
  timezone: string;
  timezone_source: string;
  availability: 'ready' | 'partial' | 'not_generated' | 'unavailable';
  projection_revision: string;
  projection_sequence: number;
  generated_at: string | null;
  source_as_of: string | null;
  expires_at: string | null;
  restrictions: Array<Record<string, unknown>>;
  review_window: { start_date: string; end_date: string; days: 7; includes_today: boolean; kind: string };
  actions: HealthNavigationAction[];
  review: {
    recorded_days: number; window_days: number; coverage_status: string;
    completed_occurrences: number; skipped_occurrences: number;
    deferred_occurrences: number; unknown_occurrences: number; claim_boundary: string;
  };
}
export interface HealthNavigationActionDetail extends Pick<HealthNavigationAction, 'action_ref' | 'action_revision' | 'execution_status' | 'safety_state' | 'requires_health_review' | 'scheduling_mode'> {
  title: string;
  completion_criterion: string;
  plan_date: string;
  action_key: string;
  expires_at?: string | null;
  can_confirm: boolean;
}
export interface NavigationEventInput {
  event_type: 'completed' | 'skipped' | 'deferred';
  expected_revision: string;
  operation_id: string;
}
export interface NavigationGrant { scope: 'navigation:generic'; window_policy: 'current_trailing7'; connected: boolean; created_at: string; grant_id: string; recipient_id: string; expires_at: string; revoked_at?: string | null; status?: string }

export function validHealthActionRef(ref: unknown): ref is string {
  return typeof ref === 'string' && (
    /^[A-Za-z0-9_-]{8,128}$/.test(ref)
    || /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\.[a-f0-9]{64}$/.test(ref)
  );
}
function actionPath(ref: string): string {
  if (!validHealthActionRef(ref)) throw new Error('invalid_action_reference');
  return `/health-navigation/actions/${encodeURIComponent(ref)}`;
}
export async function fetchHealthWeekNavigation(): Promise<HealthWeekNavigation> {
  const { data } = await api.get<HealthWeekNavigation>('/health-navigation/summary');
  return data;
}
export async function refreshHealthWeekNavigation(): Promise<unknown> {
  const { data } = await api.post('/health-navigation/refresh');
  return data;
}
export async function fetchHealthNavigationAction(ref: string): Promise<HealthNavigationActionDetail> {
  const { data } = await api.get<HealthNavigationActionDetail>(actionPath(ref));
  return data;
}
export async function recordHealthNavigationEvent(ref: string, input: NavigationEventInput): Promise<unknown> {
  const { data } = await api.post(`${actionPath(ref)}/events`, input);
  return data;
}
export async function fetchHealthNavigationGrants(): Promise<NavigationGrant[]> {
  const { data } = await api.get<NavigationGrant[]>('/health-navigation/grants');
  return data;
}
export async function revokeHealthNavigationGrant(id: string): Promise<void> {
  await api.delete(`/health-navigation/grants/${encodeURIComponent(id)}`);
}
export const navigationStatusLabel: Record<NavigationExecutionStatus, string> = {
  pending: '待记录', completed: '已完成', skipped: '已跳过', deferred: '已延期', withdrawn: '已撤回', unknown: '状态未知',
};
export function navigationErrorMessage(error: unknown): string {
  const status = (error as { response?: { status?: number } })?.response?.status;
  if (status === 503) return '健康周导航暂未开放或暂时不可用，请稍后重试。';
  if (status === 401) return '请重新登录后查看。';
  if (status === 404 || status === 410) return '此行动引用已失效或不可访问。';
  if (status === 409) return '行动已发生变化，请重新核对最新内容。';
  if (status === 403) return '当前权限或安全条件不允许此操作。';
  return '暂时无法获取权威状态，请重试。';
}
