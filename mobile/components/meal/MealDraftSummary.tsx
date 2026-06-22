import React, { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { radii, spacing } from '../../constants/theme';
import { useTheme, type ColorPalette } from '../../hooks/useTheme';
import type { MealSessionSummary } from '../../services/mealMonitoring';

/**
 * MealDraftSummary — 渲染 finish 返回的草稿(识别食物 + 总量 + 观察性总结 + 免责声明)。
 *
 * 关键约束(餐后观察、非实时指导):observational_summary 与 disclaimer 原样展示,
 * 绝不附加任何命令/处方式 UI 文案("你应该少吃…")。guidance_alerts 若有则照实渲染。
 */

function fmt(value?: number | null, unit?: string): string {
  if (value == null || !Number.isFinite(value)) {
    return '—';
  }
  return `${Math.round(value)}${unit ?? ''}`;
}

export function MealDraftSummary({ summary }: { summary: MealSessionSummary }) {
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  const totals = summary.totals ?? {};
  const totalCells: { label: string; value: string }[] = [
    { label: '热量', value: fmt(totals.calories, ' kcal') },
    { label: '蛋白', value: fmt(totals.protein, ' g') },
    { label: '碳水', value: fmt(totals.carbs, ' g') },
    { label: '脂肪', value: fmt(totals.fat, ' g') },
    { label: '纤维', value: fmt(totals.fiber, ' g') },
  ];

  return (
    <View style={styles.wrap}>
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>识别到的食物</Text>
        {summary.foods?.length ? (
          summary.foods.map((food, index) => (
            <View key={`${food.name}-${index}`} style={styles.foodRow}>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={styles.foodName} numberOfLines={2}>
                  {food.name}
                  {food.quantity ? <Text style={styles.foodQuantity}>{`  ${food.quantity}`}</Text> : null}
                </Text>
              </View>
              {food.calories != null ? (
                <Text style={styles.foodCalories}>{fmt(food.calories, ' kcal')}</Text>
              ) : null}
            </View>
          ))
        ) : (
          <Text style={styles.empty}>未识别出具体食物，可直接确认或放弃。</Text>
        )}

        <View style={styles.totalsRow}>
          {totalCells.map((cell) => (
            <View key={cell.label} style={styles.totalCell}>
              <Text style={styles.totalValue} numberOfLines={1}>{cell.value}</Text>
              <Text style={styles.totalLabel}>{cell.label}</Text>
            </View>
          ))}
        </View>
        <Text style={styles.frameMeta}>基于 {summary.frame_count} 帧采样</Text>
      </View>

      {summary.observational_summary ? (
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>餐后观察</Text>
          {/* 原样展示,不添加任何指导/命令式文案 */}
          <Text style={styles.observational}>{summary.observational_summary}</Text>
        </View>
      ) : null}

      {summary.guidance_alerts?.length ? (
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>提示</Text>
          {summary.guidance_alerts.map((alert, index) => (
            <View key={`${alert.title ?? 'alert'}-${index}`} style={[styles.alertRow, { backgroundColor: s.warning.bg }]}>
              <Ionicons name="alert-circle-outline" size={16} color={s.warning.fg} style={styles.alertIcon} />
              <View style={{ flex: 1, minWidth: 0 }}>
                {alert.title ? <Text style={[styles.alertTitle, { color: s.warning.fg }]}>{alert.title}</Text> : null}
                {alert.message ? <Text style={[styles.alertMessage, { color: s.warning.fg }]}>{alert.message}</Text> : null}
              </View>
            </View>
          ))}
        </View>
      ) : null}

      {summary.disclaimer ? (
        <Text style={styles.disclaimer}>{summary.disclaimer}</Text>
      ) : null}
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    wrap: { gap: spacing.md },
    card: {
      backgroundColor: c.bgCard,
      borderRadius: radii.lg,
      padding: spacing.lg,
      gap: spacing.sm,
    },
    sectionTitle: { fontSize: 15, fontWeight: '700', color: c.labelPrimary, marginBottom: spacing.xs },
    foodRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      paddingVertical: spacing.xs,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: c.separator,
    },
    foodName: { fontSize: 15, color: c.labelPrimary, lineHeight: 21 },
    foodQuantity: { fontSize: 13, color: c.labelTertiary },
    foodCalories: { fontSize: 14, fontWeight: '600', color: c.labelSecondary, fontVariant: ['tabular-nums'] },
    empty: { fontSize: 14, color: c.labelTertiary },
    totalsRow: { flexDirection: 'row', gap: spacing.xs, marginTop: spacing.sm },
    totalCell: {
      flex: 1,
      backgroundColor: c.fill,
      borderRadius: radii.md,
      paddingVertical: spacing.sm,
      alignItems: 'center',
      gap: 2,
    },
    totalValue: { fontSize: 13, fontWeight: '700', color: c.labelPrimary, fontVariant: ['tabular-nums'] },
    totalLabel: { fontSize: 11, color: c.labelTertiary },
    frameMeta: { fontSize: 12, color: c.labelTertiary, marginTop: spacing.xs },
    observational: { fontSize: 15, lineHeight: 23, color: c.labelPrimary },
    alertRow: { flexDirection: 'row', gap: spacing.sm, padding: spacing.md, borderRadius: radii.md },
    alertIcon: { marginTop: 1 },
    alertTitle: { fontSize: 14, fontWeight: '700' },
    alertMessage: { fontSize: 13, lineHeight: 19, marginTop: 2 },
    disclaimer: { fontSize: 12, lineHeight: 18, color: c.labelTertiary, paddingHorizontal: spacing.xs },
  });
}

export default MealDraftSummary;
