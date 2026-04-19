import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { CardShell } from './CardShell';
import { colors } from '@/constants/theme';
import type { CardSpec } from './types';

interface DietData {
  calories?: number;
  protein?: number;
  carbs?: number;
  fat?: number;
  fiber?: number;
  meals_count?: number;
  meals_by_type?: Record<string, number>; // meal_type -> total_cal
}

const MEAL_LABEL: Record<string, { label: string; icon: string; color: string }> = {
  breakfast: { label: '早餐', icon: '☀️',  color: '#FF9F0A' },
  lunch:     { label: '午餐', icon: '🍚', color: '#FF6723' },
  dinner:    { label: '晚餐', icon: '🌙', color: '#BF5AF2' },
  snack:     { label: '加餐', icon: '🍎', color: '#5AC8FA' },
};

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function DietCardView({
  calories, protein, carbs, fat, fiber, meals_count, meals_by_type,
}: DietData) {
  const macros = [
    { label: '蛋白', value: protein, color: '#FF375F', unit: 'g' },
    { label: '碳水', value: carbs,   color: '#FF9F0A', unit: 'g' },
    { label: '脂肪', value: fat,     color: '#BF5AF2', unit: 'g' },
    { label: '纤维', value: fiber,   color: '#30D158', unit: 'g' },
  ].filter((m) => m.value != null && m.value > 0);

  const hasMeals = meals_by_type && Object.keys(meals_by_type).length > 0;

  return (
    <CardShell icon="restaurant" iconColor="#FF6723" title="今日饮食" bg="#FFF7F0">
      <View style={styles.calRow}>
        <Text style={txt.cal}>
          {calories != null ? `${Math.round(calories)}` : '--'}
          <Text style={txt.calUnit}> kcal</Text>
        </Text>
        {meals_count != null && meals_count > 0 && (
          <Text style={txt.mealsCount}>{meals_count} 餐</Text>
        )}
      </View>

      {macros.length > 0 && (
        <View style={styles.macrosRow}>
          {macros.map((m) => (
            <View key={m.label} style={styles.macro}>
              <View style={[styles.macroDot, { backgroundColor: m.color }]} />
              <Text style={txt.macroLabel}>{m.label}</Text>
              <Text style={[txt.macroVal, { color: m.color }]}>
                {m.value!.toFixed(0)}{m.unit}
              </Text>
            </View>
          ))}
        </View>
      )}

      {hasMeals && (
        <View style={styles.mealsRow}>
          {(['breakfast', 'lunch', 'dinner', 'snack'] as const).map((t) => {
            const cal = meals_by_type?.[t];
            if (cal == null || cal === 0) return null;
            const meta = MEAL_LABEL[t];
            return (
              <View key={t} style={styles.meal}>
                <Text style={txt.mealIcon}>{meta.icon}</Text>
                <Text style={txt.mealLabel}>{meta.label}</Text>
                <Text style={[txt.mealCal, { color: meta.color }]}>{Math.round(cal)}</Text>
              </View>
            );
          })}
        </View>
      )}

      {!hasMeals && (!calories || calories === 0) && (
        <Text style={txt.emptyHint}>今日还没有饮食记录 · 说「我刚吃了…」就能记上</Text>
      )}
    </CardShell>
  );
}

export const DietCardSpec: CardSpec<DietData> = {
  type: 'diet',
  label: '今日饮食',
  match({ query_lower, toolsUsed }) {
    // 记录意图别抢
    if (/刚吃|刚喝|吃了|喝了|记录.*饮食|记录.*吃/.test(query_lower)) return null;
    if (toolsUsed.has('record_diet')) return null;
    if (/饮食|吃了什么|今日吃|今天吃|热量|卡路里|蛋白|碳水|脂肪|营养|calories/.test(query_lower)) return 18;
    return null;
  },
  async build({ api }) {
    try {
      const res = await api.get(`/diet/records/me/date/${today()}`);
      const d = res.data;
      if (!d) return null;
      const byType: Record<string, number> = {};
      for (const m of (d.meals || [])) {
        const k = m.meal_type || 'snack';
        byType[k] = (byType[k] || 0) + (m.calories || 0);
      }
      const out: DietData = {
        calories: d.total_calories,
        protein: d.total_protein,
        carbs: d.total_carbs,
        fat: d.total_fat,
        fiber: d.total_fiber,
        meals_count: d.meals_count,
        meals_by_type: byType,
      };
      return out;
    } catch {
      return null;
    }
  },
  render: (d) => <DietCardView {...d} />,
};

const styles = StyleSheet.create({
  calRow: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' },
  macrosRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 6 },
  macro: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  macroDot: { width: 6, height: 6, borderRadius: 3 },
  mealsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 8 },
  meal: { flexDirection: 'row', alignItems: 'center', gap: 2 },
});

const txt = {
  cal: { fontSize: 22, fontWeight: '800', color: colors.labelPrimary, fontVariant: ['tabular-nums'] as const } as TextStyle,
  calUnit: { fontSize: 12, fontWeight: '400', color: colors.labelTertiary } as TextStyle,
  mealsCount: { fontSize: 11, color: colors.labelTertiary } as TextStyle,
  macroLabel: { fontSize: 10, color: colors.labelSecondary } as TextStyle,
  macroVal: { fontSize: 11, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
  mealIcon: { fontSize: 11 } as TextStyle,
  mealLabel: { fontSize: 10, color: colors.labelSecondary } as TextStyle,
  mealCal: { fontSize: 11, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
  emptyHint: { fontSize: 11, color: colors.labelTertiary, marginTop: 4 } as TextStyle,
};
