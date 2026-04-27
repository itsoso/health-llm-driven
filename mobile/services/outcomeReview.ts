import type { ActionCard } from './actionCards';

export type OutcomeReviewStatus = 'met' | 'not_met' | 'inconclusive' | 'pending';

export interface OutcomeReviewInput {
  item_id?: number;
  item_code?: string;
  title?: string;
  actual_value?: string | number | null;
  suggested_status?: string;
  target?: string;
  note?: string;
  latest_assessment?: {
    score?: number;
    summary?: string;
    evidence?: string[];
  } | null;
}

export interface OutcomeReviewDraft {
  status: OutcomeReviewStatus;
  actualValue: string;
  summary: string;
  evidence: string[];
}

export function buildOutcomeReviewDraft(input: OutcomeReviewInput): OutcomeReviewDraft {
  const status = normalizeStatus(input.suggested_status);
  const actualValue = input.actual_value == null ? '' : String(input.actual_value);
  const title = input.title || input.item_code || '健康干预';
  const summary = input.latest_assessment?.summary
    || `${title}${input.target ? `，目标 ${input.target}` : ''}${actualValue ? `，实际 ${actualValue}` : ''}`;
  const evidence = [
    input.note,
    ...(input.latest_assessment?.evidence || []),
  ].filter(Boolean) as string[];

  return { status, actualValue, summary, evidence };
}

export function buildActionCardOutcomeDraft(card: ActionCard): OutcomeReviewDraft {
  const assessment = card.latest_assessment;
  const status = statusFromScore(assessment?.score);
  const evidence = [
    card.metric_key ? `指标 ${card.metric_key}` : null,
    card.baseline_value ? `基线 ${card.baseline_value}` : null,
    card.target_value ? `目标 ${card.target_value}` : null,
    ...(assessment?.evidence || []),
  ].filter(Boolean) as string[];

  return {
    status,
    actualValue: '',
    summary: assessment?.summary || `${card.title}${card.target_value ? `，目标 ${card.target_value}` : ''}`,
    evidence,
  };
}

function normalizeStatus(status?: string): OutcomeReviewStatus {
  if (status === 'met' || status === 'not_met' || status === 'inconclusive' || status === 'pending') {
    return status;
  }
  return 'pending';
}

function statusFromScore(score?: number): OutcomeReviewStatus {
  if (score == null) return 'pending';
  if (score >= 7) return 'met';
  if (score <= 4) return 'not_met';
  return 'inconclusive';
}
