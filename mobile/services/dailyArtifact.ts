import type { AgendaSource } from './agenda';

export type DailyArtifactTone = 'normal' | 'caution' | 'risk' | 'info';

export interface DailyArtifactEvidence {
  id: string;
  label: string;
  value: string;
  tone: DailyArtifactTone;
}

export interface DailyArtifactTopAction {
  title: string;
  subtitle: string | null;
  scheduledFor: string | null;
  source: 'timeline' | 'daily_plan' | 'empty';
  canComplete: boolean;
  completeRef?: AgendaSource | null;
  deepLink?: string | null;
}

export interface DailyArtifact {
  stateLabel: string;
  readiness: {
    score: number | null;
    staleScore?: number | null;
    label: string;
    asOf?: string | null;
  };
  topAction: DailyArtifactTopAction | null;
  evidence: DailyArtifactEvidence[];
  freshness: {
    label: string;
    tone: DailyArtifactTone;
    lastSyncAt: number | null;
  };
  safetyBoundary: {
    level: 'normal' | 'risk';
    label: string;
  };
  actions: {
    canComplete: boolean;
    canSkip: boolean;
    skipRequiresReason: boolean;
    canAskReva: boolean;
  };
  tracking: {
    artifactId: string;
    weekIndex: number;
    topActionSource: DailyArtifactTopAction['source'];
  };
}

interface TimelineNowItem {
  id?: string | null;
  title?: string | null;
  subtitle?: string | null;
  scheduled_for?: string | null;
  can_complete?: boolean | null;
  complete_ref?: AgendaSource | null;
  deep_link?: string | null;
}

interface DailyPlanFallbackAction {
  title?: string | null;
  reason?: string | null;
  why?: string | null;
  domain?: string | null;
}

interface SafetyAlertLike {
  severity?: string | null;
  title?: string | null;
}

export interface DailyArtifactInput {
  nowMs?: number;
  readinessScore?: number | null;
  readinessStale?: boolean;
  readinessDate?: string | null;
  nowItem?: TimelineNowItem | null;
  fallbackAction?: DailyPlanFallbackAction | null;
  sleepHours?: number | null;
  hrv?: number | null;
  spo2?: number | null;
  healthKitLastSyncAt?: number | null;
  safetyAlerts?: SafetyAlertLike[];
}

function readinessLabel(score: number | null, stale?: boolean): string {
  if (stale && score != null) return '昨晚未同步';
  if (score == null) return '待同步';
  if (score >= 80) return '可上强度';
  if (score >= 60) return '适度活动';
  return '注意恢复';
}

function shortSubtitle(value?: string | null): string | null {
  if (!value) return null;
  return value.split(/[，,。.;；]/)[0]?.trim() || value;
}

function freshnessLabel(lastSyncAt: number | null | undefined, nowMs: number): DailyArtifact['freshness'] {
  if (!lastSyncAt) {
    return { label: 'HealthKit 未自动同步', tone: 'caution', lastSyncAt: null };
  }
  const diff = Math.max(0, nowMs - lastSyncAt);
  const minutes = Math.round(diff / 60000);
  if (minutes < 60) {
    return { label: `${Math.max(1, minutes)} 分钟前同步`, tone: 'normal', lastSyncAt };
  }
  const hours = Math.round(minutes / 60);
  return {
    label: `${hours} 小时前同步`,
    tone: hours > 4 ? 'caution' : 'normal',
    lastSyncAt,
  };
}

function isRiskSeverity(severity?: string | null): boolean {
  return ['critical', 'high', 'risk'].includes(String(severity || '').toLowerCase());
}

function buildTopAction(input: DailyArtifactInput): DailyArtifactTopAction {
  if (input.nowItem?.title) {
    return {
      title: input.nowItem.title,
      subtitle: shortSubtitle(input.nowItem.subtitle),
      scheduledFor: input.nowItem.scheduled_for ?? null,
      source: 'timeline',
      canComplete: Boolean(input.nowItem.can_complete && input.nowItem.complete_ref),
      completeRef: input.nowItem.complete_ref ?? null,
      deepLink: input.nowItem.deep_link ?? null,
    };
  }
  if (input.fallbackAction?.title) {
    return {
      title: input.fallbackAction.title,
      subtitle: shortSubtitle(input.fallbackAction.reason ?? input.fallbackAction.why),
      scheduledFor: null,
      source: 'daily_plan',
      canComplete: false,
      completeRef: null,
      deepLink: null,
    };
  }
  return {
    title: '补齐今天记录',
    subtitle: null,
    scheduledFor: null,
    source: 'empty',
    canComplete: false,
    completeRef: null,
    deepLink: null,
  };
}

function isoDate(nowMs: number): string {
  return new Date(nowMs).toISOString().slice(0, 10);
}

function isoWeekIndex(nowMs: number): number {
  const d = new Date(nowMs);
  const utc = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const day = utc.getUTCDay() || 7;
  utc.setUTCDate(utc.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(utc.getUTCFullYear(), 0, 1));
  return Math.ceil((((utc.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
}

function buildArtifactId(nowMs: number, topAction: DailyArtifactTopAction, input: DailyArtifactInput): string {
  const sourceId = topAction.source === 'timeline'
    ? input.nowItem?.id || topAction.title
    : topAction.title;
  return `${isoDate(nowMs)}:${topAction.source}:${String(sourceId).trim() || 'empty'}`;
}

function buildEvidence(input: DailyArtifactInput): DailyArtifactEvidence[] {
  const riskAlerts = (input.safetyAlerts ?? []).filter((alert) => isRiskSeverity(alert.severity));
  const evidence: DailyArtifactEvidence[] = [];
  const firstRisk = riskAlerts[0];
  if (firstRisk?.title) {
    evidence.push({ id: 'safety', label: '安全提醒', value: firstRisk.title, tone: 'risk' });
  }
  if (input.sleepHours != null) {
    evidence.push({ id: 'sleep', label: '睡眠', value: `${input.sleepHours.toFixed(1)} h`, tone: input.sleepHours >= 6.5 ? 'normal' : 'caution' });
  }
  if (input.hrv != null) {
    evidence.push({ id: 'hrv', label: 'HRV', value: `${Math.round(input.hrv)} ms`, tone: 'info' });
  }
  if (input.spo2 != null) {
    evidence.push({ id: 'spo2', label: '血氧', value: `${Math.round(input.spo2)}%`, tone: input.spo2 >= 95 ? 'normal' : 'caution' });
  }
  return evidence.slice(0, 3);
}

export function buildDailyArtifact(input: DailyArtifactInput): DailyArtifact {
  const nowMs = input.nowMs ?? Date.now();
  const riskCount = (input.safetyAlerts ?? []).filter((alert) => isRiskSeverity(alert.severity)).length;
  const readinessIsStale = Boolean(input.readinessStale && input.readinessScore != null);
  const topAction = buildTopAction(input);

  return {
    stateLabel: '今日状态',
    readiness: {
      score: readinessIsStale ? null : input.readinessScore ?? null,
      staleScore: readinessIsStale ? input.readinessScore ?? null : undefined,
      label: readinessLabel(input.readinessScore ?? null, readinessIsStale),
      asOf: input.readinessDate ?? null,
    },
    topAction,
    evidence: buildEvidence(input),
    freshness: freshnessLabel(input.healthKitLastSyncAt, nowMs),
    safetyBoundary: riskCount > 0
      ? { level: 'risk', label: `有 ${riskCount} 条风险提醒` }
      : { level: 'normal', label: '安全边界正常' },
    actions: {
      canComplete: topAction.canComplete,
      canSkip: true,
      skipRequiresReason: true,
      canAskReva: true,
    },
    tracking: {
      artifactId: buildArtifactId(nowMs, topAction, input),
      weekIndex: isoWeekIndex(nowMs),
      topActionSource: topAction.source,
    },
  };
}
