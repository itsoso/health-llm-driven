import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { CardShell } from './CardShell';
import { EvidenceRefsRow } from './EvidenceRefsRow';
import type { EvidenceRef } from './EvidenceRefsRow';
import { revaColors as C, revaFonts } from '../../../constants/revaTheme';
import type { CardSpec } from './types';

// 饮食类目 accent (橙) + 卡底 tint = 「是饮食卡」装饰色, 保留字面量 (= legacy orange/tintOrange).
const DIET_ACCENT = '#C97A2E';
const DIET_TINT = '#F6E9DA';

// 营养素 / 餐次的装饰性 hue (蛋白粉 / 碳水琥珀 / 脂肪紫 / 纤维绿; 早琥珀/午橙/晚紫/加餐青),
// 区分类目, 非临床好坏, 保留字面量.
const MACRO_PINK = '#C2487A';
const MACRO_AMBER = '#C98A1E';
const MACRO_PURPLE = '#7C5CBF';
const MACRO_TEAL = '#2F9E8F';

interface DietData {
  calories?: number;
  protein?: number;
  carbs?: number;
  fat?: number;
  fiber?: number;
  meals_count?: number;
  meals_by_type?: Record<string, number>;
  evidence_refs?: EvidenceRef[];
}

const MEAL_LABELS: Record<string, { label: string; icon: string; color: string }> = {
  breakfast: { label: '早餐', icon: '☀️', color: MACRO_AMBER },
  lunch:     { label: '午餐', icon: '🍚', color: DIET_ACCENT },
  dinner:    { label: '晚餐', icon: '🌙', color: MACRO_PURPLE },
  snack:     { label: '加餐', icon: '🍎', color: MACRO_TEAL },
};

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function DietCardView({
  calories, protein, carbs, fat, fiber, meals_count, meals_by_type, evidence_refs,
}: DietData) {
  const macros = [
    { label: '蛋白', value: protein, color: MACRO_PINK, unit: 'g' },
    { label: '碳水', value: carbs,   color: MACRO_AMBER, unit: 'g' },
    { label: '脂肪', value: fat,     color: MACRO_PURPLE, unit: 'g' },
    { label: '纤维', value: fiber,   color: C.green500, unit: 'g' },
  ].filter((m) => m.value != null && m.value > 0);

  const hasMeals = meals_by_type && Object.keys(meals_by_type).length > 0;

  return (
    <CardShell icon="restaurant" iconColor={DIET_ACCENT} title="今日饮食" bg={DIET_TINT}>
      <View style={styles.calRow}>
        <Text maxFontSizeMultiplier={1.3} style={styles.cal}>
          {calories != null ? `${Math.round(calories)}` : '--'}
          <Text style={styles.calUnit}> kcal</Text>
        </Text>
        {meals_count != null && meals_count > 0 && (
          <Text maxFontSizeMultiplier={1.3} style={styles.mealsCount}>
            {meals_count} 餐
          </Text>
        )}
      </View>

      {macros.length > 0 && (
        <View style={styles.macrosRow}>
          {macros.map((m) => (
            <View key={m.label} style={styles.macro}>
              <View style={[styles.macroDot, { backgroundColor: m.color }]} />
              <Text maxFontSizeMultiplier={1.3} style={styles.macroLabel}>
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
            const meta = MEAL_LABELS[t];
            return (
              <View key={t} style={styles.meal}>
                <Text maxFontSizeMultiplier={1.3} style={styles.mealIcon}>{meta.icon}</Text>
                <Text maxFontSizeMultiplier={1.3} style={styles.mealLabel}>
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
        <Text maxFontSizeMultiplier={1.3} style={styles.emptyHint}>
          今日还没有饮食记录 · 说「我刚吃了…」就能记上
        </Text>
      )}

      <EvidenceRefsRow refs={evidence_refs} />
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
  cal: { fontFamily: revaFonts.mono, fontSize: 22, fontWeight: '800', color: C.ink1, fontVariant: ['tabular-nums'] as const } as TextStyle,
  calUnit: { fontFamily: revaFonts.mono, fontSize: 12, fontWeight: '400', color: C.ink3 } as TextStyle,
  mealsCount: { fontFamily: revaFonts.mono, fontSize: 11, color: C.ink3 } as TextStyle,
  macroLabel: { fontFamily: revaFonts.sans, fontSize: 10, color: C.ink2 } as TextStyle,
  macroVal: { fontFamily: revaFonts.mono, fontSize: 11, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
  mealIcon: { fontSize: 11 } as TextStyle,
  mealLabel: { fontFamily: revaFonts.sans, fontSize: 10, color: C.ink2 } as TextStyle,
  mealCal: { fontFamily: revaFonts.mono, fontSize: 11, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
  emptyHint: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3, marginTop: 4 } as TextStyle,
});
