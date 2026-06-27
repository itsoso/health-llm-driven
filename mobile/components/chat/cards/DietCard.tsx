import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { CardShell } from './CardShell';
import { EvidenceRefsRow } from './EvidenceRefsRow';
import type { EvidenceRef, KnowledgeContraindication } from './EvidenceRefsRow';
import { useTheme, type ColorPalette } from '../../../hooks/useTheme';
import type { CardSpec } from './types';

interface DietData {
  calories?: number;
  protein?: number;
  carbs?: number;
  fat?: number;
  fiber?: number;
  meals_count?: number;
  meals_by_type?: Record<string, number>;
  evidence_refs?: EvidenceRef[];
  claim_boundary?: string | null;
  contraindications?: KnowledgeContraindication[] | null;
}

function _mealLabel(c: ColorPalette): Record<string, { label: string; icon: string; color: string }> {
  return {
    breakfast: { label: '早餐', icon: '☀️',  color: c.amber },
    lunch:     { label: '午餐', icon: '🍚', color: c.orange },
    dinner:    { label: '晚餐', icon: '🌙', color: c.purple },
    snack:     { label: '加餐', icon: '🍎', color: c.teal },
  };
}

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function DietCardView({
  calories, protein, carbs, fat, fiber, meals_count, meals_by_type, evidence_refs,
  claim_boundary, contraindications,
}: DietData) {
  const { c } = useTheme();
  const mealLabels = _mealLabel(c);
  const macros = [
    { label: '蛋白', value: protein, color: c.pink, unit: 'g' },
    { label: '碳水', value: carbs,   color: c.amber, unit: 'g' },
    { label: '脂肪', value: fat,     color: c.purple, unit: 'g' },
    { label: '纤维', value: fiber,   color: c.green, unit: 'g' },
  ].filter((m) => m.value != null && m.value > 0);

  const hasMeals = meals_by_type && Object.keys(meals_by_type).length > 0;

  return (
    <CardShell icon="restaurant" iconColor={c.orange} title="今日饮食" bg={c.tintOrange}>
      <View style={styles.calRow}>
        <Text maxFontSizeMultiplier={1.3} style={[styles.cal, { color: c.labelPrimary }]}>
          {calories != null ? `${Math.round(calories)}` : '--'}
          <Text style={[styles.calUnit, { color: c.labelTertiary }]}> kcal</Text>
        </Text>
        {meals_count != null && meals_count > 0 && (
          <Text maxFontSizeMultiplier={1.3} style={[styles.mealsCount, { color: c.labelTertiary }]}>
            {meals_count} 餐
          </Text>
        )}
      </View>

      {macros.length > 0 && (
        <View style={styles.macrosRow}>
          {macros.map((m) => (
            <View key={m.label} style={styles.macro}>
              <View style={[styles.macroDot, { backgroundColor: m.color }]} />
              <Text maxFontSizeMultiplier={1.3} style={[styles.macroLabel, { color: c.labelSecondary }]}>
                {m.label}
              </Text>
              <Text maxFontSizeMultiplier={1.3} style={[styles.macroVal, { color: m.color }]}>
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
            const meta = mealLabels[t];
            return (
              <View key={t} style={styles.meal}>
                <Text maxFontSizeMultiplier={1.3} style={styles.mealIcon}>{meta.icon}</Text>
                <Text maxFontSizeMultiplier={1.3} style={[styles.mealLabel, { color: c.labelSecondary }]}>
                  {meta.label}
                </Text>
                <Text maxFontSizeMultiplier={1.3} style={[styles.mealCal, { color: meta.color }]}>
                  {Math.round(cal)}
                </Text>
              </View>
            );
          })}
        </View>
      )}

      {!hasMeals && (!calories || calories === 0) && (
        <Text maxFontSizeMultiplier={1.3} style={[styles.emptyHint, { color: c.labelTertiary }]}>
          今日还没有饮食记录 · 说「我刚吃了…」就能记上
        </Text>
      )}

      <EvidenceRefsRow
        refs={evidence_refs}
        claimBoundary={claim_boundary}
        contraindications={contraindications}
      />
    </CardShell>
  );
}

export const DietCardSpec: CardSpec<DietData> = {
  type: 'diet',
  label: '今日饮食',
  match({ query_lower, toolsUsed }) {
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
  cal: { fontSize: 22, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
  calUnit: { fontSize: 12, fontWeight: '400' } as TextStyle,
  mealsCount: { fontSize: 11 } as TextStyle,
  macroLabel: { fontSize: 10 } as TextStyle,
  macroVal: { fontSize: 11, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
  mealIcon: { fontSize: 11 } as TextStyle,
  mealLabel: { fontSize: 10 } as TextStyle,
  mealCal: { fontSize: 11, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
  emptyHint: { fontSize: 11, marginTop: 4 } as TextStyle,
});
