import type { DailyOperatingPlan, DailyPlanAction } from '../../services/dailyPlan';
import type { TodayDynamicView } from '../../services/todayDynamicView';
import type { TodayTimelineItem, TodayTimelineResponse } from '../../services/todayTimeline';

export type TodayFocusSource = 'dynamic_today' | 'daily_plan' | 'timeline';

export interface TodayFocusPrimary {
  key: string;
  source: TodayFocusSource;
  title: string;
  reason?: string | null;
  deepLink?: string | null;
  evidence: string[];
  verification: string[];
}

export interface TodayFocusModel {
  primary: TodayFocusPrimary | null;
  emptyTitle: string;
  status: {
    actionable: number;
    completed: number;
    overdue: number;
  };
}

export function normalizeTodayFocusKey(value: string | null | undefined): string {
  return (value ?? '')
    .trim()
    .replace(/[：]/g, ':')
    .replace(/\s+/g, '');
}

export function buildTodayFocusModel(args: {
  dynamicView?: TodayDynamicView | null;
  dailyPlan?: DailyOperatingPlan | null;
  timeline?: TodayTimelineResponse | null;
}): TodayFocusModel {
  const primary =
    readDynamicPrimary(args.dynamicView) ??
    readDailyPlanPrimary(args.dailyPlan) ??
    readTimelinePrimary(args.timeline);
  const actionable = nonNegativeCount(args.timeline?.counts?.actionable);
  const promotedInTimeline = primary && isPrimaryRepresentedInTimeline(primary, args.timeline) ? 1 : 0;

  return {
    primary,
    emptyTitle: '今日暂无重点行动',
    status: {
      actionable: Math.max(0, actionable - promotedInTimeline),
      completed: nonNegativeCount(args.timeline?.past?.completed_count),
      overdue: nonNegativeCount(args.timeline?.counts?.overdue),
    },
  };
}

function readDynamicPrimary(view?: TodayDynamicView | null): TodayFocusPrimary | null {
  const cards = view?.sections?.flatMap(section => section.cards) ?? [];
  for (const card of cards) {
    const atom = readText(card.render?.atom);
    const data = asRecord(card.data);
    const nextAction = asRecord(data.next_action);
    const title = readText(nextAction.title) || readText(data.title);
    if (!title) continue;
    if (atom && atom !== 'daily_artifact') continue;

    return {
      key: card.id || normalizeTodayFocusKey(title),
      source: 'dynamic_today',
      title,
      reason: readText(data.why_now) || readText(data.summary),
      deepLink: readText(nextAction.deep_link),
      evidence: readStringList(data.evidence),
      verification: readStringList(data.verification),
    };
  }
  return null;
}

function readDailyPlanPrimary(plan?: DailyOperatingPlan | null): TodayFocusPrimary | null {
  const action = (plan?.actions ?? []).find(item => readText(item?.title));
  if (!action) return null;
  return fromPlanAction(action);
}

function fromPlanAction(action: DailyPlanAction): TodayFocusPrimary {
  const title = readText(action.title) || '今日行动';
  return {
    key: action.action_key || normalizeTodayFocusKey(title),
    source: 'daily_plan',
    title,
    reason: action.why ?? null,
    deepLink: null,
    evidence: readStringList(action.evidence_refs),
    verification: [
      readText(action.verification?.cycle_target_metric_label),
      readText(action.verification?.metric),
    ].filter((item): item is string => Boolean(item)),
  };
}

function readTimelinePrimary(timeline?: TodayTimelineResponse | null): TodayFocusPrimary | null {
  const items = (timeline?.items ?? []).filter(isRenderableTimelineItem);
  const nowId = readText(timeline?.now);
  const item = (nowId ? items.find(row => row.id === nowId) : null) ?? items[0];
  if (!item) return null;
  return fromTimelineItem(item);
}

function fromTimelineItem(item: TodayTimelineItem): TodayFocusPrimary {
  const title = readText(item.title) || '今日行动';
  const proofLine = item.proof
    ? [readText(item.proof.label), readText(item.proof.delta)].filter(Boolean).join(' ')
    : '';
  return {
    key: item.id || normalizeTodayFocusKey(`${item.kind}:${item.scheduled_for ?? ''}:${title}`),
    source: 'timeline',
    title,
    reason: readText(item.subtitle) || timelineStatusReason(item.status),
    deepLink: readText(item.deep_link),
    evidence: proofLine ? [proofLine] : [],
    verification: item.can_complete ? ['完成后记录结果'] : [],
  };
}

function isRenderableTimelineItem(item: TodayTimelineItem | null | undefined): item is TodayTimelineItem {
  if (!item || !readText(item.title)) return false;
  const status = readText(item.status).toLowerCase();
  return status !== 'completed' && status !== 'skipped';
}

function isPrimaryRepresentedInTimeline(
  primary: TodayFocusPrimary,
  timeline?: TodayTimelineResponse | null,
): boolean {
  const primaryTitleKey = normalizeTodayFocusKey(primary.title);
  return (timeline?.items ?? [])
    .filter(isRenderableTimelineItem)
    .some(item => (
      item.id === primary.key ||
      normalizeTodayFocusKey(item.title) === primaryTitleKey ||
      Boolean(primary.deepLink && item.deep_link === primary.deepLink)
    ));
}

function timelineStatusReason(status: string | null | undefined): string | null {
  if (status === 'overdue') return '这项已经过时段，建议先处理或跳过。';
  if (status === 'due') return '现在是处理这项的合适时段。';
  return null;
}

function readText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function readStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (typeof item === 'string') return item.trim();
      if (!item || typeof item !== 'object') return '';
      const ref = item as { claim_id?: unknown; doc_id?: unknown; id?: unknown };
      return readText(ref.claim_id) || readText(ref.doc_id) || readText(ref.id);
    })
    .filter((item): item is string => item.length > 0);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function nonNegativeCount(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value)
    ? Math.max(0, Math.round(value))
    : 0;
}
