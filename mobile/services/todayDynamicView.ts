import type { ChatCardActionDescriptor } from '../components/chat/cards/types';
import type { DailyArtifact } from './dailyArtifact';
import api from './api';
import { isSafeInternalRoute } from '../utils/internalRoutes';

export type TodayDynamicTrigger = 'open' | 'resume' | 'pull_refresh' | 'action_completed';
export type TodayDynamicSurface = 'mobile.today';

export interface TodayDynamicCard {
  id?: string;
  type: string;
  data: Record<string, unknown> | DailyArtifact;
  actions?: ChatCardActionDescriptor[];
  render?: Record<string, unknown>;
}

export interface TodayDynamicSection {
  slot: string;
  priority: number;
  title?: string | null;
  cards: TodayDynamicCard[];
}

export interface TodayDynamicView {
  view_id: string;
  surface: TodayDynamicSurface;
  trigger: TodayDynamicTrigger;
  generated_by: string;
  generated_at?: string | null;
  expires_at?: string | null;
  context_hash: string;
  safety_boundary?: string | null;
  sections: TodayDynamicSection[];
}

export interface GetTodayDynamicViewOptions {
  trigger?: TodayDynamicTrigger;
  clientContext?: Record<string, unknown>;
}

const ALLOWED_DYNAMIC_ACTIONS = new Set([
  'agenda.complete',
  'daily_plan_action.complete',
  'write_intent.confirm',
  'write_intent.dismiss',
  'route.open',
  'ui.inline.expand',
]);
const WRITE_DYNAMIC_ACTIONS = new Set([
  'agenda.complete',
  'daily_plan_action.complete',
  'write_intent.confirm',
  'write_intent.dismiss',
]);

export async function getTodayDynamicView(
  options: GetTodayDynamicViewOptions = {},
): Promise<TodayDynamicView> {
  const trigger = options.trigger ?? 'open';
  const { data } = await api.post('/dynamic-views/today', {
    trigger,
    surface: 'mobile.today',
    client_context: options.clientContext ?? {},
  });
  return normalizeTodayDynamicView(data);
}

export function normalizeTodayDynamicView(raw: Partial<TodayDynamicView> | null | undefined): TodayDynamicView {
  return {
    view_id: typeof raw?.view_id === 'string' && raw.view_id ? raw.view_id : 'today:empty',
    surface: raw?.surface === 'mobile.today' ? raw.surface : 'mobile.today',
    trigger: normalizeTrigger(raw?.trigger),
    generated_by: typeof raw?.generated_by === 'string' && raw.generated_by
      ? raw.generated_by
      : 'aheng_today_view_v1',
    generated_at: raw?.generated_at ?? null,
    expires_at: raw?.expires_at ?? null,
    context_hash: typeof raw?.context_hash === 'string' ? raw.context_hash : '',
    safety_boundary: raw?.safety_boundary ?? null,
    sections: normalizeSections(raw?.sections),
  };
}

export function hasRenderableTodayDynamicView(view: TodayDynamicView | null | undefined): view is TodayDynamicView {
  return Boolean(view?.sections?.some((section) => section.cards.length > 0));
}

function normalizeTrigger(value: unknown): TodayDynamicTrigger {
  return value === 'resume' || value === 'pull_refresh' || value === 'action_completed'
    ? value
    : 'open';
}

function normalizeSections(value: unknown): TodayDynamicSection[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((raw): TodayDynamicSection | null => {
      if (!raw || typeof raw !== 'object') return null;
      const section = raw as Record<string, unknown>;
      const slot = typeof section.slot === 'string' ? section.slot.trim() : '';
      if (!slot) return null;
      const cards = normalizeCards(section.cards);
      if (cards.length === 0) return null;
      const priority = typeof section.priority === 'number' && Number.isFinite(section.priority)
        ? section.priority
        : 0;
      return {
        slot,
        priority,
        title: typeof section.title === 'string' ? section.title : null,
        cards,
      };
    })
    .filter((section): section is TodayDynamicSection => section != null)
    .sort((a, b) => b.priority - a.priority);
}

function normalizeCards(value: unknown): TodayDynamicCard[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((raw): TodayDynamicCard | null => {
      if (!raw || typeof raw !== 'object') return null;
      const card = raw as Record<string, unknown>;
      const type = typeof card.type === 'string' ? card.type.trim() : '';
      if (!type) return null;
      return {
        id: typeof card.id === 'string' && card.id.trim() ? card.id.trim() : undefined,
        type,
        data: card.data && typeof card.data === 'object' ? card.data as Record<string, unknown> : {},
        actions: normalizeActions(card.actions),
        render: card.render && typeof card.render === 'object'
          ? card.render as Record<string, unknown>
          : undefined,
      };
    })
    .filter((card): card is TodayDynamicCard => card != null);
}

function normalizeActions(value: unknown): ChatCardActionDescriptor[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const actions = value
    .filter((raw): raw is ChatCardActionDescriptor => (
      raw != null &&
      typeof raw === 'object' &&
      typeof (raw as ChatCardActionDescriptor).label === 'string' &&
      (raw as ChatCardActionDescriptor).label.trim().length > 0 &&
      typeof (raw as ChatCardActionDescriptor).action === 'string' &&
      ALLOWED_DYNAMIC_ACTIONS.has((raw as ChatCardActionDescriptor).action) &&
      isSafeAction(raw as ChatCardActionDescriptor)
    ))
    .map((action) => ({
      ...action,
      label: action.label.trim(),
    }));
  return actions.length > 0 ? actions : undefined;
}

function isSafeAction(action: ChatCardActionDescriptor): boolean {
  if (action.action === 'route.open') {
    return isSafeInternalRoute(action.payload?.route);
  }
  if (action.action === 'ui.inline.expand') {
    return Boolean(
      typeof action.payload?.target === 'string' &&
      action.payload?.patch &&
      typeof action.payload.patch === 'object' &&
      !Array.isArray(action.payload.patch),
    );
  }
  if (action.action === 'daily_plan_action.complete') {
    const actionId = action.payload?.action_id;
    return Boolean(
      action.requires_manual_confirm === true &&
      hasRegisteredWritePolicy(action) &&
      typeof actionId === 'string' &&
      actionId.length > 0 &&
      action.payload?.event_type === 'completed' &&
      action.endpoint === `/daily-plan/actions/${encodeURIComponent(actionId)}/events`,
    );
  }
  return action.requires_manual_confirm === true && hasRegisteredWritePolicy(action);
}

function hasRegisteredWritePolicy(action: ChatCardActionDescriptor): boolean {
  if (!WRITE_DYNAMIC_ACTIONS.has(action.action)) return true;
  return Boolean(
    typeof action.capability_id === 'string' &&
    /^[a-z][a-z0-9_]*\.v\d+$/.test(action.capability_id) &&
    action.required_receipt === true &&
    action.autonomy_tier === 'manual_confirm' &&
    action.policy_reason === 'manual_confirm_write',
  );
}
