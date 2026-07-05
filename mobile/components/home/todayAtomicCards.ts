import type { DailyArtifact } from '../../services/dailyArtifact';
import type { SafetyAlert } from '../../services/safety';
import { formatHealthActionTitle } from '../../utils/actionCopy';
import { stateVariableLabel } from '../../services/trajectoryDisplay';

export type TodayAtomicCardKind = 'daily_artifact' | 'safety_alert';

export interface TodayAtomicAction {
  id: string;
  label: string;
  route?: string;
}

export interface TodayAtomicRenderState {
  show: boolean;
  reason: string;
}

export interface TodayAtomicCardContract<TPayload = unknown> {
  id: string;
  kind: TodayAtomicCardKind;
  slot: 'primary_action' | 'safety';
  priority: number;
  render: TodayAtomicRenderState;
  primaryAction: TodayAtomicAction | null;
  secondaryActions: TodayAtomicAction[];
  verificationSignals: string[];
  safetyBoundary: string | null;
  dedupeKeys: string[];
  riskLevel?: string | null;
  payload: TPayload | null;
}

export function buildDailyArtifactAtomicContract(
  artifact: DailyArtifact | null | undefined,
): TodayAtomicCardContract<DailyArtifact> {
  const action = artifact?.top_action ?? null;
  const hasAction = Boolean(artifact && action && !artifact.empty_state);
  return {
    id: `daily-artifact:${artifact?.artifact_date ?? 'unknown'}:${action?.id ?? 'empty'}`,
    kind: 'daily_artifact',
    slot: 'primary_action',
    priority: 100,
    render: {
      show: hasAction,
      reason: hasAction ? 'has_top_action' : 'missing_top_action',
    },
    primaryAction: hasAction ? { id: 'execute', label: '去执行' } : null,
    secondaryActions: hasAction
      ? [
          { id: 'explain_basis', label: '查看决策依据' },
          { id: 'ask_reva', label: '问小巴' },
          { id: 'skip', label: '跳过' },
        ]
      : [],
    verificationSignals: hasAction && artifact ? artifactVerificationSignals(artifact) : [],
    safetyBoundary: artifact?.safety_boundary ?? null,
    dedupeKeys: action?.title ? [formatHealthActionTitle(action.title)] : [],
    payload: artifact ?? null,
  };
}

export function buildSafetyAlertAtomicContract(
  alerts: SafetyAlert[] | null | undefined,
): TodayAtomicCardContract<SafetyAlert> {
  const candidates = (alerts ?? []).filter(alert => isHighPrioritySafety(alert));
  const picked = candidates.find(alert => severityKey(alert.severity) === 'critical')
    ?? candidates.find(alert => severityKey(alert.severity) === 'high')
    ?? null;
  const severity = picked ? severityKey(picked.severity) : null;
  return {
    id: `safety-alert:${picked?.rule_id ?? 'none'}`,
    kind: 'safety_alert',
    slot: 'safety',
    priority: severity === 'critical' ? 95 : 90,
    render: {
      show: Boolean(picked),
      reason: picked ? 'has_high_priority_alert' : 'no_high_priority_alert',
    },
    primaryAction: picked
      ? { id: 'open_alerts', label: '查看安全提醒', route: '/(tabs)/alerts' }
      : null,
    secondaryActions: picked ? [{ id: 'ask_reva', label: '问小巴' }] : [],
    verificationSignals: [],
    safetyBoundary: picked ? '确定性安全规则优先于行动排序；需要时请联系医生或急救服务。' : null,
    dedupeKeys: picked?.title ? [picked.title] : [],
    riskLevel: severity,
    payload: picked,
  };
}

export function selectTodayAtomicContracts({
  artifact,
  safetyAlerts,
}: {
  artifact?: DailyArtifact | null;
  safetyAlerts?: SafetyAlert[] | null;
}): TodayAtomicCardContract[] {
  return [
    buildDailyArtifactAtomicContract(artifact),
    buildSafetyAlertAtomicContract(safetyAlerts),
  ]
    .filter(contract => contract.render.show)
    .sort((a, b) => b.priority - a.priority);
}

function isHighPrioritySafety(alert: SafetyAlert): boolean {
  return ['critical', 'high'].includes(severityKey(alert.severity));
}

function severityKey(value: unknown): string {
  return typeof value === 'string' ? value : (value as { label?: string } | null)?.label ?? 'info';
}

function artifactVerificationSignals(artifact: DailyArtifact): string[] {
  const action = artifact.top_action;
  if (!action) return [];
  return uniqueValues([
    metricLabel(action.verification_signal ?? null),
    metricLabel(action.target_state_variable ?? null),
    ...(artifact.evidence ?? []).flatMap(item => (item.metrics ?? []).map(metricLabel)),
  ]);
}

function uniqueValues(values: (string | null)[]): string[] {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value))));
}

// 单一真相源:services/trajectoryDisplay.ts 的 stateVariableLabel(缺映射原样返回)。
function metricLabel(value: string | null | undefined): string | null {
  return stateVariableLabel(value ?? null);
}
