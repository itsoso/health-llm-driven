import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { spacing, radii } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';
import {
  pickTopPlanActions,
  submitDailyPlanActionFeedback,
  type DailyOperatingPlan,
  type DailyPlanAction,
  type DailyPlanActionFeedbackStatus,
} from '../../services/dailyPlan';

const DOMAIN_ICON: Record<string, keyof typeof Ionicons.glyphMap> = {
  measurement: 'analytics-outline',
  nutrition: 'restaurant-outline',
  movement: 'walk-outline',
  sleep: 'moon-outline',
  intervention: 'flag-outline',
  doctor: 'medical-outline',
};

export default function TodayPlanPanel({
  plan,
  loading,
  onPressAction,
}: {
  plan?: DailyOperatingPlan | null;
  loading?: boolean;
  onPressAction?: (action: DailyPlanAction) => void;
}) {
  const { c } = useTheme();
  const [feedbackByAction, setFeedbackByAction] = React.useState<Record<string, DailyPlanActionFeedbackStatus | 'sending' | 'error'>>({});
  const actions = pickTopPlanActions(plan?.actions ?? [], 3);
  const state = plan?.state_summary ?? {};
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
  const submitFeedback = React.useCallback(async (action: DailyPlanAction, status: DailyPlanActionFeedbackStatus) => {
    const actionKey = action.action_key;
    if (!actionKey || feedbackByAction[actionKey] === 'sending') return;
    setFeedbackByAction(prev => ({ ...prev, [actionKey]: 'sending' }));
    try {
      await submitDailyPlanActionFeedback(actionKey, status);
      setFeedbackByAction(prev => ({ ...prev, [actionKey]: status }));
    } catch {
      setFeedbackByAction(prev => ({ ...prev, [actionKey]: 'error' }));
    }
  }, [feedbackByAction]);

  return (
    <View style={[styles.container, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.header}>
        <View style={[styles.headerIcon, { backgroundColor: c.tintTeal }]}>
          <Ionicons name="compass-outline" size={17} color={c.teal} />
        </View>
        <View style={styles.headerText}>
          <Text style={[styles.title, { color: c.labelPrimary }]}>今日操作计划</Text>
          <Text style={[styles.subtitle, { color: c.labelTertiary }]}>
            {loading ? '正在生成' : `代谢健康 · ${plan?.plan_date ?? '今天'}`}
          </Text>
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
          {actions.map((action, index) => (
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
                  <Text style={[styles.actionTitle, { color: c.labelPrimary }]} numberOfLines={1}>
                    {action.title}
                  </Text>
                  {action.why ? (
                    <Text style={[styles.actionWhy, { color: c.labelSecondary }]} numberOfLines={2}>
                      {action.why}
                    </Text>
                  ) : null}
                </View>
                <Text style={[styles.when, { color: c.labelTertiary }]}>{action.when ?? 'today'}</Text>
              </TouchableOpacity>

              <View style={styles.feedbackRow}>
                {([
                  ['done', '做到了'],
                  ['skipped', '跳过'],
                  ['adjusted', '调整'],
                ] as const).map(([status, label]) => {
                  const current = action.action_key ? feedbackByAction[action.action_key] : undefined;
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
                      onPress={() => submitFeedback(action, status)}
                      disabled={disabled}
                      activeOpacity={0.75}
                      accessibilityRole="button"
                      accessibilityLabel={`${action.title} ${label}`}
                    >
                      <Text style={[styles.feedbackText, { color: selected ? c.teal : c.labelSecondary }]}>
                        {current === 'sending' && status === 'done' ? '记录中' : label}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
                {action.action_key && feedbackByAction[action.action_key] === 'error' ? (
                  <Text style={[styles.feedbackError, { color: c.red }]}>记录失败</Text>
                ) : null}
              </View>
            </View>
          ))}
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
  header: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  headerIcon: {
    width: 34,
    height: 34,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerText: { flex: 1, gap: 2 },
  title: { fontSize: 16, fontWeight: '700' },
  subtitle: { fontSize: 12, fontWeight: '500' },
  metricHint: { maxWidth: 118, fontSize: 12, fontWeight: '600' },
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
  actionTitle: { fontSize: 14, fontWeight: '700' },
  actionWhy: { fontSize: 12, lineHeight: 16 },
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
