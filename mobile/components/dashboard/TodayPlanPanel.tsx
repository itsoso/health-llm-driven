import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { spacing, radii } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';
import { pickTopPlanActions, type DailyOperatingPlan, type DailyPlanAction } from '../../services/dailyPlan';

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
  const actions = pickTopPlanActions(plan?.actions ?? [], 3);
  const state = plan?.state_summary ?? {};
  const waist = state.waist_cm as number | undefined;
  const bp = state.blood_pressure as string | undefined;

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

      {actions.length === 0 ? (
        <View style={[styles.empty, { borderColor: c.separator }]}>
          <Text style={[styles.emptyText, { color: c.labelTertiary }]}>
            暂无今日计划, 下拉刷新后会基于 Twin 生成。
          </Text>
        </View>
      ) : (
        <View style={styles.actionList}>
          {actions.map((action, index) => (
            <TouchableOpacity
              key={`${action.domain}-${action.title}-${index}`}
              style={[styles.actionRow, { borderColor: c.separator }]}
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
  empty: {
    borderWidth: StyleSheet.hairlineWidth,
    borderStyle: 'dashed',
    borderRadius: radii.md,
    padding: spacing.md,
  },
  emptyText: { fontSize: 13, lineHeight: 18, textAlign: 'center' },
  actionList: { gap: spacing.sm },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    padding: spacing.sm,
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
});
