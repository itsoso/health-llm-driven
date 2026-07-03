import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { EvidenceRefsRow } from './EvidenceRefsRow';
import type { EvidenceRef } from './EvidenceRefsRow';
import { MacroBar, MACRO_HUES } from './mealCardVisuals';
import { revaColors as C, revaFonts } from '../../../constants/revaTheme';
import type { CardSpec } from './types';

// 饮食类目 accent (橙) + 卡底 tint = 「是饮食卡」装饰色, 保留字面量 (= legacy orange/tintOrange).
const DIET_ACCENT = '#C97A2E';
const DIET_TINT = '#F6E9DA';

// 餐次装饰性 hue (早琥珀/午橙/晚紫/加餐青), 区分类目, 非临床好坏, 保留字面量.
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

const MEAL_LABELS: Record<string, { label: string; icon: keyof typeof Ionicons.glyphMap; color: string }> = {
  breakfast: { label: '早餐', icon: 'cafe', color: MACRO_AMBER },
  lunch:     { label: '午餐', icon: 'restaurant', color: DIET_ACCENT },
  dinner:    { label: '晚餐', icon: 'moon', color: MACRO_PURPLE },
  snack:     { label: '加餐', icon: 'nutrition', color: MACRO_TEAL },
};

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function DietCardView({
  calories, protein, carbs, fat, fiber, meals_count, meals_by_type, evidence_refs,
}: DietData) {
  // 2×2 营养网格: 只渲染非空 macro。
  const macros = [
    { label: '蛋白质', value: protein, color: MACRO_HUES.protein, unit: 'g' },
    { label: '碳水', value: carbs,   color: MACRO_HUES.carbs, unit: 'g' },
    { label: '脂肪', value: fat,     color: MACRO_HUES.fat, unit: 'g' },
    { label: '膳食纤维', value: fiber, color: MACRO_HUES.fiber, unit: 'g' },
  ].filter((m) => m.value != null && m.value > 0);

  const hasMeals = meals_by_type && Object.keys(meals_by_type).length > 0;
  const isEmpty = !hasMeals && (!calories || calories === 0);

  return (
    <CardShell icon="restaurant" iconColor={DIET_ACCENT} title="今日饮食" bg={DIET_TINT}>
      {/* 卡路里 hero：大号等宽数字 + 单位 + 餐数。 */}
      <View style={styles.heroRow}>
        <Text maxFontSizeMultiplier={1.18} style={styles.cal}>
          {calories != null ? `${Math.round(calories)}` : '--'}
          <Text style={styles.calUnit}> kcal</Text>
        </Text>
        {meals_count != null && meals_count > 0 && (
          <Text maxFontSizeMultiplier={1.18} style={styles.mealsCount}>
            {Math.round(meals_count)} 餐
          </Text>
        )}
      </View>

      {/* 分段营养条：按热量占比拆分。总热量 ≤ 0 或无 macro → 自动隐藏。 */}
      <MacroBar protein={protein} carbs={carbs} fat={fat} fiber={fiber} style={styles.macroBar} />

      {/* 2×2 营养网格：彩色圆点 + 标签 + 克数。 */}
      {macros.length > 0 && (
        <View style={styles.macroGrid}>
          {macros.map((m) => (
            <View key={m.label} style={styles.macroCell}>
              <View style={[styles.macroDot, { backgroundColor: m.color }]} />
              <Text maxFontSizeMultiplier={1.1} style={styles.macroLabel} numberOfLines={1}>
                {m.label}
              </Text>
              <Text maxFontSizeMultiplier={1.1} style={[styles.macroVal, { color: m.color }]}>
                {Math.round(m.value!)}{m.unit}
              </Text>
            </View>
          ))}
        </View>
      )}

      {/* 餐次分布：早/午/晚/加餐 各自热量。 */}
      {hasMeals && (
        <View style={styles.mealsRow}>
          {(['breakfast', 'lunch', 'dinner', 'snack'] as const).map((t) => {
            const cal = meals_by_type?.[t];
            if (cal == null || cal === 0) return null;
            const meta = MEAL_LABELS[t];
            return (
              <View key={t} style={styles.meal}>
                <Ionicons name={meta.icon} size={12} color={meta.color} />
                <Text maxFontSizeMultiplier={1.15} style={styles.mealLabel}>
                  {meta.label}
                </Text>
                <Text maxFontSizeMultiplier={1.15} style={[styles.mealCal, { color: meta.color }]}>
                  {Math.round(cal)}
                </Text>
              </View>
            );
          })}
        </View>
      )}

      {isEmpty && (
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
  heroRow: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' },
  cal: { fontFamily: revaFonts.mono, fontSize: 28, fontWeight: '800', color: C.ink1, fontVariant: ['tabular-nums'] as const } as TextStyle,
  calUnit: { fontFamily: revaFonts.mono, fontSize: 13, fontWeight: '400', color: C.ink3 } as TextStyle,
  mealsCount: { fontFamily: revaFonts.mono, fontSize: 12, color: C.ink3, fontVariant: ['tabular-nums'] as const } as TextStyle,
  macroBar: { marginTop: 10 },
  macroGrid: { flexDirection: 'row', flexWrap: 'wrap', marginTop: 10 },
  macroCell: { width: '50%', flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 5 },
  macroDot: { width: 8, height: 8, borderRadius: 4 },
  macroLabel: { flex: 1, fontFamily: revaFonts.sans, fontSize: 12, color: C.ink2, fontWeight: '700' } as TextStyle,
  macroVal: { fontFamily: revaFonts.mono, fontSize: 13, fontWeight: '900', fontVariant: ['tabular-nums'] as const } as TextStyle,
  mealsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 10 },
  meal: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  mealLabel: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink2, fontWeight: '600' } as TextStyle,
  mealCal: { fontFamily: revaFonts.mono, fontSize: 12, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
  emptyHint: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3, marginTop: 8 } as TextStyle,
});
