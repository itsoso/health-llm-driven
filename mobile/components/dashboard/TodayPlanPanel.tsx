import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { spacing, radii } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';
import {
  pickTopPlanActions,
  recordDailyPlanActionEvent,
  type DailyOperatingPlan,
  type DailyPlanAction,
  type DailyPlanActionEventType,
} from '../../services/dailyPlan';
import EvidenceChip from '../shared/EvidenceChip';
import { EvidenceRefsRow } from '../knowledge';

const DOMAIN_ICON: Record<string, keyof typeof Ionicons.glyphMap> = {
  measurement: 'analytics-outline',
  nutrition: 'restaurant-outline',
  movement: 'walk-outline',
  sleep: 'moon-outline',
  intervention: 'flag-outline',
  doctor: 'medical-outline',
};

const METRIC_LABEL: Record<string, string> = {
  sleep_score: '睡眠分',
  sleep: '睡眠',
  hrv: 'HRV',
  spo2: '血氧',
  body_fat: '体脂',
  bmi: 'BMI',
  weight: '体重',
  waist: '腰围',
  blood_pressure: '血压',
  vo2max: '最大摄氧量',
  protein: '蛋白质',
  glucose: '血糖',
  lipid: '血脂',
};

const WHEN_LABEL: Record<string, string> = {
  morning: '早晨',
  meals: '饮食时段',
  evening: '晚间',
  today: '今天',
};

function compactActionMeta(action: DailyPlanAction): string {
  const cycleMetric = action.verification?.cycle_target_metric_label || action.verification?.cycle_target_metric;
  if (cycleMetric) return `周期指标 ${cycleMetric}`;
  const metric = action.verification?.metric;
  if (metric) return `影响 ${METRIC_LABEL[metric] ?? metric}`;
  const when = action.when ?? 'today';
  return WHEN_LABEL[when] ?? when;
}

function cycleMetricLine(action: DailyPlanAction): string | null {
  const metric = action.verification?.cycle_target_metric_label || action.verification?.cycle_target_metric;
  return metric ? `90 天周期 · ${metric}` : null;
}

type PlanActionProgress = {
  completed_count?: number;
  handled_count?: number;
  remaining_count?: number;
  completed_action_keys?: string[];
  terminal_action_keys?: string[];
};

const COMPLETED_EVENT_STATES = new Set<DailyPlanActionEventType>(['completed', 'verified']);
const TERMINAL_EVENT_STATES = new Set<DailyPlanActionEventType>(['completed', 'skipped', 'verified']);

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function readActionProgress(state: Record<string, unknown>): PlanActionProgress | null {
  const raw = state.action_progress;
  if (!raw || typeof raw !== 'object') return null;
  const progress = raw as Record<string, unknown>;
  return {
    completed_count: numberValue(progress.completed_count) ?? undefined,
    handled_count: numberValue(progress.handled_count) ?? undefined,
    remaining_count: numberValue(progress.remaining_count) ?? undefined,
    completed_action_keys: stringArray(progress.completed_action_keys),
    terminal_action_keys: stringArray(progress.terminal_action_keys),
  };
}

function buildProgressLabel({
  progress,
  actions,
  eventByAction,
}: {
  progress: PlanActionProgress | null;
  actions: DailyPlanAction[];
  eventByAction: Record<string, DailyPlanActionEventType | 'sending' | 'error'>;
}): string | null {
  if (!progress && actions.length === 0) return null;
  const remoteCompleted = new Set(progress?.completed_action_keys ?? []);
  const remoteTerminal = new Set(progress?.terminal_action_keys ?? []);
  const completed = new Set(remoteCompleted);
  const terminal = new Set(remoteTerminal);

  for (const [actionKey, state] of Object.entries(eventByAction)) {
    if (state === 'sending' || state === 'error') continue;
    if (COMPLETED_EVENT_STATES.has(state)) completed.add(actionKey);
    if (TERMINAL_EVENT_STATES.has(state)) terminal.add(actionKey);
  }

  const visibleLocalTerminal = actions.filter((action) => {
    const key = action.action_key ? String(action.action_key) : '';
    return key && terminal.has(key) && !remoteTerminal.has(key);
  }).length;
  const baseRemaining = progress?.remaining_count ?? actions.length;
  const remaining = Math.max(0, baseRemaining - visibleLocalTerminal);
  const completedCount = Math.max(progress?.completed_count ?? 0, completed.size);
  const handledCount = Math.max(progress?.handled_count ?? 0, terminal.size);
  const otherHandled = Math.max(0, handledCount - completedCount);
  return otherHandled > 0
    ? `今日闭环 ${completedCount} 完成 · ${otherHandled} 已处理 · ${remaining} 待做`
    : `今日闭环 ${completedCount} 完成 · ${remaining} 待做`;
}

export default function TodayPlanPanel({
  plan,
  loading,
  compact = false,
  title = '今日操作计划',
  excludeActionKey,
  onPressAction,
  onActionEvent,
}: {
  plan?: DailyOperatingPlan | null;
  loading?: boolean;
  compact?: boolean;
  title?: string;
  excludeActionKey?: string | null;
  onPressAction?: (action: DailyPlanAction) => void;
  onActionEvent?: () => void;
}) {
  const { c } = useTheme();
  const [eventByAction, setEventByAction] = React.useState<Record<string, DailyPlanActionEventType | 'sending' | 'error'>>({});
  const visiblePlanActions = excludeActionKey
    ? (plan?.actions ?? []).filter(action => (action.action_key || action.title) !== excludeActionKey)
    : (plan?.actions ?? []);
  const actions = pickTopPlanActions(visiblePlanActions, compact ? 2 : 3);
  const visibleActionCount = visiblePlanActions.length;
  const state = plan?.state_summary ?? {};
  const progressLabel = buildProgressLabel({
    progress: readActionProgress(state),
    actions: visiblePlanActions,
    eventByAction,
  });
  const waist = state.waist_cm as number | undefined;
  const bp = state.blood_pressure as string | undefined;
  const acute = (state.acute && typeof state.acute === 'object')
    ? state.acute as Record<string, unknown>
    : null;
  const isRecoveryMode = Boolean(acute?.should_rest_from_training);
  const illnessNames = Array.isArray(acute?.illness_names)
    ? acute.illness_names.map(String).filter(Boolean).slice(0, 3)
    : [];
  const recoveryGuardrail = typeof acute?.training_guardrail === 'string' && acute.training_guardrail.trim()
    ? acute.training_guardrail.trim()
    : '今天不要求完成训练目标，优先恢复、补水和睡眠。';
  const submitEvent = React.useCallback(async (action: DailyPlanAction, eventType: DailyPlanActionEventType) => {
    const actionKey = action.action_key;
    if (!actionKey || eventByAction[actionKey] === 'sending') return;
    setEventByAction(prev => ({ ...prev, [actionKey]: 'sending' }));
    try {
      const result = await recordDailyPlanActionEvent(actionKey, { event_type: eventType, payload: {} });
      setEventByAction(prev => ({ ...prev, [actionKey]: result.action_state as DailyPlanActionEventType }));
      onActionEvent?.();
    } catch {
      setEventByAction(prev => ({ ...prev, [actionKey]: 'error' }));
    }
  }, [eventByAction, onActionEvent]);

  if (compact) {
    const compactSubtitle = loading
      ? '正在生成余下计划'
      : visibleActionCount > 0
        ? `除当前重点外，还有 ${visibleActionCount} 件事`
        : '当前重点处理完后再生成下一步';

    return (
      <View style={[styles.compactContainer, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
        <View style={styles.compactHeader}>
          <View style={[styles.compactIcon, { backgroundColor: c.tintTeal }]}>
            <Ionicons name="list-outline" size={16} color={c.teal} />
          </View>
          <View style={styles.headerText}>
            <Text style={[styles.compactTitle, { color: c.labelPrimary }]}>{title}</Text>
            <Text style={[styles.subtitle, { color: c.labelTertiary }]}>{compactSubtitle}</Text>
          </View>
          {isRecoveryMode ? (
            <View style={[styles.compactPill, { backgroundColor: c.tintAmber }]}>
              <Text style={[styles.compactPillText, { color: c.amber }]}>恢复优先</Text>
            </View>
          ) : null}
        </View>

        {actions.length === 0 ? (
          <Text style={[styles.compactEmptyText, { color: c.labelTertiary }]}>
            先完成当前重点，小巴会继续排队后续干预。
          </Text>
        ) : (
          <View style={styles.compactActionList}>
            {actions.map((action, index) => (
              <TouchableOpacity
                key={`${action.domain}-${action.title}-${index}`}
                style={[styles.compactActionRow, { borderColor: c.separator }]}
                onPress={() => onPressAction?.(action)}
                activeOpacity={0.75}
                accessibilityRole="button"
                accessibilityLabel={`打开余下计划 ${action.title}`}
              >
                <View style={[styles.compactActionIcon, { backgroundColor: c.fill }]}>
                  <Ionicons
                    name={DOMAIN_ICON[action.domain] ?? 'checkmark-circle-outline'}
                    size={14}
                    color={c.brand}
                  />
                </View>
                <View style={styles.compactActionMain}>
                  <Text style={[styles.compactActionTitle, { color: c.labelPrimary }]} numberOfLines={1}>
                    {action.title}
                  </Text>
                  <Text style={[styles.compactActionMeta, { color: c.labelTertiary }]} numberOfLines={1}>
                    {compactActionMeta(action)}
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} />
              </TouchableOpacity>
            ))}
          </View>
        )}
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.header}>
        <View style={[styles.headerIcon, { backgroundColor: c.tintTeal }]}>
          <Ionicons name="compass-outline" size={17} color={c.teal} />
        </View>
        <View style={styles.headerText}>
          <Text style={[styles.title, { color: c.labelPrimary }]}>{title}</Text>
          <Text style={[styles.subtitle, { color: c.labelTertiary }]}>
            {loading ? '正在生成' : `代谢健康 · ${plan?.plan_date ?? '今天'}`}
          </Text>
          {progressLabel ? (
            <Text style={[styles.progressText, { color: c.labelSecondary }]} numberOfLines={1}>
              {progressLabel}
            </Text>
          ) : null}
        </View>
        {(waist || bp) ? (
          <Text style={[styles.metricHint, { color: c.labelSecondary }]} numberOfLines={1}>
            {waist ? `腰围 ${waist}cm` : ''}{waist && bp ? ' · ' : ''}{bp ? `BP ${bp}` : ''}
          </Text>
        ) : null}
      </View>

      {isRecoveryMode ? (
        <View style={[styles.recoveryBanner, { backgroundColor: c.tintAmber, borderColor: c.amber }]}>
          <View style={[styles.recoveryIcon, { backgroundColor: c.bgCard }]}>
            <Ionicons name="shield-checkmark-outline" size={16} color={c.amber} />
          </View>
          <View style={styles.recoveryMain}>
            <View style={styles.recoveryTitleRow}>
              <Text style={[styles.recoveryTitle, { color: c.labelPrimary }]}>恢复模式</Text>
              {illnessNames.length > 0 ? (
                <View style={[styles.illnessPill, { backgroundColor: c.bgCard }]}>
                  <Text style={[styles.illnessText, { color: c.labelSecondary }]} numberOfLines={1}>
                    {illnessNames.join(' / ')}
                  </Text>
                </View>
              ) : null}
            </View>
            <Text style={[styles.recoveryText, { color: c.labelSecondary }]}>
              {recoveryGuardrail}
            </Text>
          </View>
        </View>
      ) : null}

      {actions.length === 0 ? (
        <View style={[styles.empty, { borderColor: c.separator }]}>
          <Text style={[styles.emptyText, { color: c.labelTertiary }]}>
            暂无今日计划, 下拉刷新后会基于 Twin 生成。
          </Text>
        </View>
      ) : (
        <View style={styles.actionList}>
          {actions.map((action, index) => {
            const cycleLine = cycleMetricLine(action);
            return (
              <View
                key={`${action.domain}-${action.title}-${index}`}
                style={[styles.actionItem, { borderColor: c.separator }]}
              >
                <TouchableOpacity
                  style={styles.actionRow}
                  onPress={() => onPressAction?.(action)}
                  activeOpacity={0.75}
                  accessibilityRole="button"
                  accessibilityLabel={action.title}
                >
                <View style={[styles.actionIcon, { backgroundColor: c.fill }]}>
                  <Ionicons
                    name={DOMAIN_ICON[action.domain] ?? 'checkmark-circle-outline'}
                    size={15}
                    color={c.brand}
                  />
                </View>
                <View style={styles.actionMain}>
                  <View style={styles.actionTitleRow}>
                    <Text style={[styles.actionTitle, { color: c.labelPrimary }]} numberOfLines={1}>
                      {action.title}
                    </Text>
                    <EvidenceChip level={action.evidence_level} />
                  </View>
                  {action.why ? (
                    <Text style={[styles.actionWhy, { color: c.labelSecondary }]} numberOfLines={2}>
                      {action.why}
                    </Text>
                  ) : null}
                  {action.verification?.metric ? (
                    <Text style={[styles.verificationText, { color: c.labelTertiary }]}>
                      验证 {action.verification.metric}
                      {action.verification.window_days ? ` · ${action.verification.window_days}天` : ''}
                    </Text>
                  ) : null}
                  {cycleLine ? (
                    <Text style={[styles.cycleText, { color: c.green }]} numberOfLines={1}>
                      {cycleLine}
                    </Text>
                  ) : null}
                  <EvidenceRefsRow refs={action.evidence_refs} />
                </View>
                <Text style={[styles.when, { color: c.labelTertiary }]}>{action.when ?? 'today'}</Text>
              </TouchableOpacity>

              <View style={styles.feedbackRow}>
                {([
                  ['accepted', '接受'],
                  ['adjusted', '调整'],
                  ['completed', '完成'],
                  ['skipped', '跳过'],
                ] as const).map(([status, label]) => {
                  const current = action.action_key ? eventByAction[action.action_key] : undefined;
                  const selected = current === status;
                  const disabled = !action.action_key || current === 'sending';
                  return (
                    <TouchableOpacity
                      key={status}
                      style={[
                        styles.feedbackChip,
                        { backgroundColor: selected ? c.tintTeal : c.fill },
                        selected && { borderColor: c.teal },
                      ]}
                      onPress={() => submitEvent(action, status)}
                      disabled={disabled}
                      activeOpacity={0.75}
                      accessibilityRole="button"
                      accessibilityLabel={`${action.title} ${label}`}
                    >
                      <Text style={[styles.feedbackText, { color: selected ? c.teal : c.labelSecondary }]}>
                        {current === 'sending' && status === 'completed' ? '记录中' : label}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
                {action.action_key && eventByAction[action.action_key] === 'error' ? (
                  <Text style={[styles.feedbackError, { color: c.red }]}>记录失败</Text>
                ) : null}
                </View>
              </View>
            );
          })}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    padding: spacing.md,
    gap: spacing.md,
  },
  compactContainer: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    padding: spacing.md,
    gap: spacing.sm,
  },
  header: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  compactHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  headerIcon: {
    width: 34,
    height: 34,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  compactIcon: {
    width: 30,
    height: 30,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerText: { flex: 1, gap: 2 },
  title: { fontSize: 16, fontWeight: '700' },
  compactTitle: { fontSize: 15, fontWeight: '800' },
  subtitle: { fontSize: 12, fontWeight: '500' },
  progressText: { fontSize: 12, fontWeight: '800' },
  metricHint: { maxWidth: 118, fontSize: 12, fontWeight: '600' },
  compactPill: {
    borderRadius: radii.full,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  compactPillText: { fontSize: 11, fontWeight: '800' },
  compactEmptyText: { fontSize: 12, lineHeight: 17 },
  compactActionList: { gap: spacing.xs },
  compactActionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingTop: spacing.sm,
    gap: spacing.sm,
  },
  compactActionIcon: {
    width: 26,
    height: 26,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  compactActionMain: { flex: 1, gap: 2 },
  compactActionTitle: { fontSize: 13, fontWeight: '800' },
  compactActionMeta: { fontSize: 11, fontWeight: '700' },
  recoveryBanner: {
    flexDirection: 'row',
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    padding: spacing.sm,
    gap: spacing.sm,
  },
  recoveryIcon: {
    width: 28,
    height: 28,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  recoveryMain: { flex: 1, gap: 4 },
  recoveryTitleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  recoveryTitle: { fontSize: 14, fontWeight: '800' },
  illnessPill: {
    maxWidth: 160,
    borderRadius: radii.full,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  illnessText: { fontSize: 11, fontWeight: '700' },
  recoveryText: { fontSize: 12, lineHeight: 17 },
  empty: {
    borderWidth: StyleSheet.hairlineWidth,
    borderStyle: 'dashed',
    borderRadius: radii.md,
    padding: spacing.md,
  },
  emptyText: { fontSize: 13, lineHeight: 18, textAlign: 'center' },
  actionList: { gap: spacing.sm },
  actionItem: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    padding: spacing.sm,
    gap: spacing.xs,
  },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  actionIcon: {
    width: 28,
    height: 28,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionMain: { flex: 1, gap: 2 },
  actionTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  actionTitle: { fontSize: 14, fontWeight: '700' },
  actionWhy: { fontSize: 12, lineHeight: 16 },
  verificationText: { fontSize: 11, fontWeight: '700' },
  cycleText: { fontSize: 11, fontWeight: '800' },
  when: { fontSize: 11, fontWeight: '600' },
  feedbackRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingLeft: 36,
  },
  feedbackChip: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'transparent',
    borderRadius: radii.full,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  feedbackText: { fontSize: 11, fontWeight: '700' },
  feedbackError: { fontSize: 11, fontWeight: '700' },
});
