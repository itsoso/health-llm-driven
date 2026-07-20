import type { AgendaItem } from '../services/agenda';

export interface TodayAgendaGroups {
  now: AgendaItem[];
  later: AgendaItem[];
  handled: AgendaItem[];
}

export type AgendaBackAction =
  | { type: 'back' }
  | { type: 'navigate'; route: '/(tabs)/chat' };

const WINDOW_START_HOUR: Record<string, number> = {
  morning: 0,
  noon: 11,
  afternoon: 14,
  evening: 18,
  bedtime: 21,
  anytime: 0,
  today: 0,
};

const WINDOW_ORDER: Record<string, number> = {
  morning: 0,
  noon: 1,
  afternoon: 2,
  evening: 3,
  bedtime: 4,
  anytime: 5,
  today: 5,
};

const HANDLED_STATUSES = new Set(['completed', 'done', 'skipped']);
const INTERNAL_PREFIX = /^\s*(?:\[[a-z0-9_.-]+\]\s*)+/i;
const INTERNAL_PRODUCER = /\b(?:safety_guardian|anomaly_detector|weekly_advisor)\b/gi;

export function agendaItemKey(item: AgendaItem): string {
  const slot = item.source.slot ? `:${item.source.slot}` : '';
  return `${item.source.object_type}:${item.source.object_id}${slot}`;
}

export function cleanAgendaTitle(value: string | null | undefined): string {
  const cleaned = String(value ?? '')
    .replace(INTERNAL_PREFIX, '')
    .replace(INTERNAL_PRODUCER, '')
    .replace(/\s{2,}/g, ' ')
    .replace(/^\s*[·:：|/-]+\s*/, '')
    .trim();
  return cleaned || '今日健康行动';
}

export function groupTodayAgendaItems(
  items: AgendaItem[],
  options: { now?: Date; snoozedKeys?: ReadonlySet<string> } = {},
): TodayAgendaGroups {
  const now = options.now ?? new Date();
  const snoozedKeys = options.snoozedKeys ?? new Set<string>();
  const groups: TodayAgendaGroups = { now: [], later: [], handled: [] };

  for (const item of items) {
    if (HANDLED_STATUSES.has(item.status)) {
      groups.handled.push(item);
      continue;
    }
    if (snoozedKeys.has(agendaItemKey(item)) || isFutureWindow(item.time_window, now)) {
      groups.later.push(item);
      continue;
    }
    groups.now.push(item);
  }

  groups.now.sort(compareAgendaItems);
  groups.later.sort(compareAgendaItems);
  groups.handled.sort(compareAgendaItems);
  return groups;
}

export function resolveAgendaBackAction(canGoBack: boolean): AgendaBackAction {
  return canGoBack
    ? { type: 'back' }
    : { type: 'navigate', route: '/(tabs)/chat' };
}

function isFutureWindow(timeWindow: string | undefined, now: Date): boolean {
  const startHour = WINDOW_START_HOUR[timeWindow ?? 'anytime'];
  return typeof startHour === 'number' && startHour > now.getHours();
}

function compareAgendaItems(a: AgendaItem, b: AgendaItem): number {
  const priorityDelta = (b.priority ?? 0) - (a.priority ?? 0);
  if (priorityDelta !== 0) return priorityDelta;
  const timeDelta = (WINDOW_ORDER[a.time_window ?? 'anytime'] ?? 9)
    - (WINDOW_ORDER[b.time_window ?? 'anytime'] ?? 9);
  if (timeDelta !== 0) return timeDelta;
  return cleanAgendaTitle(a.title).localeCompare(cleanAgendaTitle(b.title), 'zh-CN');
}
