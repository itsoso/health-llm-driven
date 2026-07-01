import type { DailyArtifact, DailyArtifactTopAction } from '../services/dailyArtifact';
import {
  buildChatContextRoute,
  serializeAgentContext,
  type AgentContextPayload,
} from './agentContext';
import { formatHealthActionTitle } from './actionCopy';

export type DailyArtifactMovementTarget = 'strength' | 'mobility' | 'recovery';
export type DailyArtifactNavigationRoute = string | ReturnType<typeof buildChatContextRoute>;

const RECOVERY_WORDS = ['恢复', '休息', '睡眠', '暂停高强度', '轻活动', '低强度', '主动恢复', '减量'];
const MOBILITY_WORDS = ['拉伸', '柔韧', '放松', '活动度'];
const CARDIO_ONLY_WORDS = ['跑步', '健走', '步行', '快走', '慢跑', '骑行'];
const STRENGTH_WORDS = ['训练', '运动', '力量', '锻炼', '俯卧撑', '深蹲', '核心'];
const NUTRITION_WORDS = ['饮食', '餐', '蛋白', '热量', '碳水', '脂肪', '补水', '喝水'];
const MEDICATION_WORDS = ['用药', '服药', '药', '补剂', '维生素'];
const EXAM_WORDS = ['体检', '化验', '复查', '检查', '指标'];

export function buildDailyArtifactAskRoute(artifact: DailyArtifact) {
  const title = formatHealthActionTitle(artifact.top_action?.title || artifact.state.summary || '今天这条行动');
  return buildChatContextRoute({
    prompt: `请解释这条今日行动: ${title}。告诉我为什么现在做、现在怎么做、如何验证; 如果我现在不适合执行,请给出替代方案。`,
    context: createDailyArtifactChatContext(artifact, 'ask_reva'),
    badge: artifact.state.label || '今日最重要行动',
  });
}

export function buildDailyArtifactBasisRoute(artifact: DailyArtifact) {
  return {
    pathname: '/daily-artifact/[date]' as const,
    params: {
      date: artifact.artifact_date || 'today',
      actionId: artifact.top_action?.id ?? undefined,
      artifact: serializeAgentContext(createDailyArtifactChatContext(artifact, 'explain_basis')),
    },
  };
}

export function buildDailyArtifactBasisChatRoute(artifact: DailyArtifact | AgentContextPayload) {
  const context = isDailyArtifact(artifact)
    ? createDailyArtifactChatContext(artifact, 'explain_basis')
    : artifact;
  const action = context.top_action as Record<string, unknown> | null | undefined;
  const state = context.state as Record<string, unknown> | null | undefined;
  const rawTitle = typeof action?.title === 'string'
    ? action.title
    : typeof state?.summary === 'string'
      ? state.summary
      : '今天这条行动';
  const title = formatHealthActionTitle(rawTitle);
  return buildChatContextRoute({
    prompt: `请详细解读这条今日行动的决策依据: ${title}。按「为什么选它、依据来自哪里、有哪些不确定性、怎么验证、什么情况下不该做」说明,并继续和我讨论替代方案。`,
    context,
    badge: '决策依据',
  });
}

export function parseDailyArtifactDetailPayload(value: unknown): AgentContextPayload | null {
  const raw = Array.isArray(value) ? value[0] : value;
  if (typeof raw !== 'string' || !raw.trim()) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    return parsed as AgentContextPayload;
  } catch {
    return null;
  }
}

export function buildDailyArtifactExecuteRoute(
  artifact: DailyArtifact | null | undefined,
  action: DailyArtifactTopAction,
  options: { nowDeepLink?: string | null } = {},
): DailyArtifactNavigationRoute {
  const explicit = firstUsableRoute(
    explicitRouteFromAction(action),
    options.nowDeepLink,
  );
  if (explicit) return explicit;

  const movementTarget = inferDailyArtifactMovementTarget(action);
  if (movementTarget === 'recovery') return '/movement-plan';
  if (movementTarget === 'strength' || movementTarget === 'mobility') {
    return appendCompleteRef(`/guided-task?domain=${movementTarget}`, sourceFromAction(action));
  }

  const text = actionText(action);
  if (NUTRITION_WORDS.some((word) => text.includes(word))) return '/diet-plan';
  if (MEDICATION_WORDS.some((word) => text.includes(word))) return '/medications';
  if (EXAM_WORDS.some((word) => text.includes(word))) return '/medical-exams';

  return buildChatContextRoute({
    prompt: `请把这条今日行动拆成现在可执行的步骤: ${formatHealthActionTitle(action.title)}。如果它还不适合执行,请先问我必要的补充信息。`,
    context: createDailyArtifactChatContext(artifact, 'execute', action),
    badge: '执行今日行动',
  });
}

export function inferDailyArtifactMovementTarget(
  action: DailyArtifactTopAction,
): DailyArtifactMovementTarget | null {
  const text = actionText(action);
  if (!text) return null;
  const primaryText = primaryActionText(action);
  if (RECOVERY_WORDS.some((word) => primaryText.includes(word))) return 'recovery';
  if (MOBILITY_WORDS.some((word) => text.includes(word))) return 'mobility';

  const cardioOnly = CARDIO_ONLY_WORDS.some((word) => text.includes(word));
  const strengthLike = STRENGTH_WORDS.some((word) => text.includes(word));
  if (cardioOnly && !strengthLike) return null;
  return strengthLike ? 'strength' : null;
}

export function createDailyArtifactChatContext(
  artifact: DailyArtifact | null | undefined,
  intent: 'ask_reva' | 'execute' | 'explain_basis',
  actionOverride?: DailyArtifactTopAction | null,
): AgentContextPayload {
  const action = actionOverride ?? artifact?.top_action ?? null;
  return {
    from: 'daily_artifact/home',
    intent,
    artifact_date: artifact?.artifact_date ?? null,
    state: artifact
      ? {
          label: artifact.state.label,
          tone: artifact.state.tone,
          summary: artifact.state.summary,
        }
      : null,
    top_action: action
      ? {
          id: action.id,
          title: formatHealthActionTitle(action.title),
          status: action.status ?? null,
          priority_tier: action.priority_tier ?? null,
          confidence: action.confidence ?? null,
          why_now: action.why_now ?? null,
          do_now: action.do_now ?? null,
          target_state_variable: action.target_state_variable ?? null,
          verification_signal: action.verification_signal ?? null,
          source: action.source ?? null,
        }
      : null,
    evidence: (artifact?.evidence ?? []).slice(0, 4).map((item) => ({
      kind: item.kind,
      label: item.label,
      summary: item.summary,
      source: item.source ?? null,
      domain: item.domain ?? null,
      confidence: item.confidence ?? null,
    })),
    safety_boundary: artifact?.safety_boundary ?? null,
  };
}

function explicitRouteFromAction(action: DailyArtifactTopAction): string | null {
  const actions = action.actions as Record<string, any> | null | undefined;
  const runtime = action.runtime_context as Record<string, any> | null | undefined;
  return firstString(
    actions?.execute?.target,
    actions?.execute?.route,
    actions?.open?.target,
    actions?.open?.route,
    actions?.primary?.target,
    actions?.primary?.route,
    runtime?.target,
    runtime?.route,
    runtime?.deep_link,
    runtime?.client_route,
    runtime?.client_action?.route,
  );
}

function firstUsableRoute(...values: (string | null | undefined)[]): string | null {
  for (const value of values) {
    const route = normalizeAppRoute(value);
    if (route) return route;
  }
  return null;
}

function normalizeAppRoute(value: string | null | undefined): string | null {
  if (!value) return null;
  const route = value.trim();
  if (!route || /^https?:\/\//i.test(route)) return null;
  const normalized = route.startsWith('/') ? route : `/${route}`;
  if (/^\/voice-chat\b/i.test(normalized)) return null;
  if (normalized === '/timeline') return null;
  return normalized;
}

function firstString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value;
  }
  return null;
}

function appendCompleteRef(base: string, source: DailyArtifactTopAction['source'] | null): string {
  if (!source?.object_type || source.object_id == null) return base;
  const params = new URLSearchParams({
    completeType: source.object_type,
    completeId: String(source.object_id),
  });
  if (source.slot) params.set('slot', source.slot);
  return `${base}&${params.toString()}`;
}

function sourceFromAction(action: DailyArtifactTopAction): DailyArtifactTopAction['source'] | null {
  return action.actions?.complete?.source ?? action.source ?? null;
}

function actionText(action: DailyArtifactTopAction): string {
  return [
    action.title,
    action.type,
    action.why_now,
    action.do_now,
    action.target_state_variable,
    action.verification_signal,
  ].filter(Boolean).join(' ');
}

function primaryActionText(action: DailyArtifactTopAction): string {
  return [
    action.title,
    action.type,
    action.do_now,
  ].filter(Boolean).join(' ');
}

function isDailyArtifact(value: DailyArtifact | AgentContextPayload): value is DailyArtifact {
  return typeof (value as DailyArtifact).artifact_date === 'string'
    && typeof (value as DailyArtifact).state?.summary === 'string'
    && 'empty_state' in value;
}
