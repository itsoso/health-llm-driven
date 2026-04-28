import api from './api';

export type DirectiveKind =
  | 'medication_change' | 'target_override' | 'lifestyle'
  | 'watch_metric' | 'skip_recommendation';

export type DirectiveSeverity = 'advisory' | 'strong' | 'mandatory';

export type DirectiveSource =
  | 'user_self' | 'external_telegram' | 'medical_exam_parsed' | 'manual' | string;

export interface UserDirective {
  id: number;
  kind: DirectiveKind;
  instruction: string;
  metric_key?: string | null;
  target_value?: string | null;
  medication_name?: string | null;
  severity: DirectiveSeverity;
  source: DirectiveSource;
  effective_from?: string | null;
  expires_at?: string | null;
  created_at?: string | null;
}

export interface DirectiveCreateInput {
  kind: DirectiveKind;
  instruction: string;
  metric_key?: string;
  target_value?: string;
  medication_name?: string;
  severity?: DirectiveSeverity;
  expires_days?: number;
}

export async function listMyDirectives(): Promise<UserDirective[]> {
  const { data } = await api.get<UserDirective[]>('/user-directives/me');
  return data;
}

export async function createDirective(input: DirectiveCreateInput): Promise<{ id: number }> {
  const { data } = await api.post<{ id: number; kind: string }>('/user-directives', input);
  return { id: data.id };
}

export async function parseFreeText(text: string, source: string = 'manual'): Promise<{ count: number; created: number[] }> {
  const { data } = await api.post<{ count: number; created: number[] }>(
    '/user-directives/parse',
    { text, source },
  );
  return data;
}

export async function revokeDirective(id: number, reason?: string): Promise<void> {
  await api.delete(`/user-directives/${id}`, { params: reason ? { reason } : undefined });
}

// ─── 展示工具 ───

export const KIND_LABEL: Record<DirectiveKind, string> = {
  medication_change: '用药调整',
  target_override:   '指标目标',
  lifestyle:         '生活方式',
  watch_metric:      '重点监测',
  skip_recommendation: '忽略建议',
};

export const SEVERITY_LABEL: Record<DirectiveSeverity, string> = {
  advisory:  '建议',
  strong:    '强',
  mandatory: '硬性',
};

export const SEVERITY_COLOR: Record<DirectiveSeverity, string> = {
  advisory:  '#636366',
  strong:    '#FF9F0A',
  mandatory: '#FF453A',
};

export const SOURCE_LABEL: Record<string, string> = {
  user_self:           '自己设',
  external_telegram:   'Telegram (外部)',
  medical_exam_parsed: '化验单解析',
  manual:              '手动输入',
};

export function sourceLabel(source: string): string {
  return SOURCE_LABEL[source] || source;
}
