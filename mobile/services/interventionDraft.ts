import type { ActionCardCreateInput } from './actionCards';

export type InterventionMetricKey = 'sleep_score' | 'hrv' | 'rhr' | 'weight' | 'bp' | 'spo2_odi' | 'custom';

export interface BuildInterventionDraftInput {
  title: string;
  advice: string;
  sourceType?: string;
  sourceId?: string | null;
  metricHint?: InterventionMetricKey;
  verificationDays?: number;
}

export interface InterventionDraft {
  title: string;
  content: string;
  card_type: 'plan';
  source_type?: string;
  source_id?: string | null;
  priority: number;
  metric_key?: InterventionMetricKey;
  baseline_value?: string;
  target_value?: string;
  verification_days: number;
  checklist: { item: string; done: boolean }[];
}

export type InterventionDraftPayload = ActionCardCreateInput & {
  metric_key?: InterventionMetricKey;
  baseline_value?: string;
  target_value?: string;
  verification_days?: number;
  checklist?: { item: string; done: boolean }[];
};

export function buildInterventionDraft(input: BuildInterventionDraftInput): InterventionDraft {
  const title = input.title.trim() || '健康行动';
  const advice = input.advice.trim();
  const verificationDays = input.verificationDays ?? inferVerificationDays(advice);

  return {
    title,
    content: buildContent(title, advice, verificationDays),
    card_type: 'plan',
    source_type: input.sourceType,
    source_id: input.sourceId,
    priority: input.sourceType === 'sleep_spo2' ? 2 : 1,
    metric_key: input.metricHint ?? inferMetric(advice),
    verification_days: verificationDays,
    checklist: buildChecklist(advice),
  };
}

export function normalizeInterventionDraft(draft: InterventionDraft): InterventionDraftPayload {
  return {
    title: draft.title.trim(),
    content: draft.content.trim(),
    card_type: 'plan',
    source_type: draft.source_type,
    source_id: draft.source_id,
    priority: draft.priority,
    metric_key: draft.metric_key,
    baseline_value: normalizeOptional(draft.baseline_value),
    target_value: normalizeOptional(draft.target_value),
    verification_days: draft.verification_days,
    checklist: draft.checklist,
    accepted: true,
  };
}

function buildContent(title: string, advice: string, verificationDays: number): string {
  return [
    `## ${title}`,
    '',
    advice || '执行这项健康行动。',
    '',
    `复盘窗口：${verificationDays} 天后检查相关指标和主观感受。`,
  ].join('\n');
}

function buildChecklist(advice: string): { item: string; done: boolean }[] {
  const clean = advice.replace(/^[-*]\s*/, '').trim();
  if (!clean) return [{ item: '完成一次行动记录', done: false }];
  return [{ item: clean.length > 40 ? `${clean.slice(0, 40)}...` : clean, done: false }];
}

function inferVerificationDays(advice: string): number {
  const match = advice.match(/(\d+)\s*天/);
  if (match) return Math.max(1, Math.min(30, Number(match[1])));
  if (/今晚|明天|睡眠|血氧|ODI/i.test(advice)) return 1;
  return 7;
}

function inferMetric(advice: string): InterventionMetricKey {
  if (/血氧|ODI|低氧/i.test(advice)) return 'spo2_odi';
  if (/HRV|恢复/i.test(advice)) return 'hrv';
  if (/心率|静息/i.test(advice)) return 'rhr';
  if (/体重|减重/i.test(advice)) return 'weight';
  if (/血压/i.test(advice)) return 'bp';
  if (/睡眠|晚餐|侧睡/i.test(advice)) return 'sleep_score';
  return 'custom';
}

function normalizeOptional(value?: string): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}
