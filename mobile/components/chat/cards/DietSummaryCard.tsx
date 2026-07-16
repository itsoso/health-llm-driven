/**
 * DietSummaryCard — 「今日饮食汇总」结构化卡 (汇总类卡 v1, Reva 设计语言)。
 *
 * 后端经 ```reva-ui fence 内联下发(与 metric_table 同一通道):
 *   {"type":"diet_daily_summary","v":1,"data":{...}}
 * → ChatBubble extractRevaUiBlocks(utils/revaUiBlocks.ts 有 diet 分支)→ renderCard
 * → 本卡渲染 (仅后端下发, match/build 恒 null)。**v 是整数 1**,parser 校验 v===1。
 *
 * 结构:壳 + 2 行头、关键观察、饮水进度条都走 **StatusSummary scaffold**(汇总卡族共享,
 * 见 statusSummary.tsx);本卡只保留领域主体 —— 餐次×宏量表(右列 mono tabular 右对齐)+
 * 全天合计。视觉与抽 scaffold 前一字不差。
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import type { TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { revaColors as C, revaFonts } from '../../../constants/revaTheme';
import { MEAL_ICONS } from './mealCardVisuals';
import type { CardSpec } from './types';
import {
  StatusSummaryShell,
  StatusObservationList,
  StatusProgressBar,
  parseObservations,
  formatBeijingDate,
  fmtNum,
  pickText,
  pickNum,
} from './statusSummary';

type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snack';

const MEAL_LABELS: Record<MealType, string> = {
  breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐',
};

// 表列顺序 = 契约字段 → 表头。热量为 kcal, 其余为 g(见 unitLegend)。
const MACRO_KEYS = ['calories', 'protein', 'carbs', 'fat'] as const;
const MACRO_HEADERS = ['热量', '蛋白', '碳水', '脂肪'] as const;

interface Meal {
  icon: keyof typeof Ionicons.glyphMap;
  name: string;
  detail?: string;
  values: (string | null)[]; // 4 列宏量, null → 缺值渲染 '—'
}

// ── 领域解析(饮食专属;通用原语来自 statusSummary） ─────────────────────────
function macroCells(source: unknown): (string | null)[] {
  const r = (source && typeof source === 'object') ? (source as Record<string, unknown>) : {};
  return MACRO_KEYS.map((k) => fmtNum(r[k]));
}
function parseMeals(raw: unknown): Meal[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item): Meal | null => {
      if (!item || typeof item !== 'object') return null;
      const r = item as Record<string, unknown>;
      const mealType = pickText(r.meal_type) as MealType | undefined;
      const name = pickText(r.name) || (mealType ? MEAL_LABELS[mealType] : undefined) || '餐次';
      const icon = (mealType && MEAL_ICONS[mealType]) || 'restaurant';
      return { icon, name, detail: pickText(r.detail), values: macroCells(r) };
    })
    .filter((m): m is Meal => m != null);
}

export function DietSummaryCardView({ data }: { data?: unknown }) {
  const d = (data && typeof data === 'object') ? (data as Record<string, any>) : {};
  const dateLabel = formatBeijingDate(d.record_date);
  const meals = parseMeals(d.meals);
  const totals = macroCells(d.totals);
  const hasTotals = totals.some((v) => v != null);
  const observations = parseObservations(d.observations);

  const waterCurrent = pickNum(d.water?.current_ml);
  const waterTarget = pickNum(d.water?.target_ml);
  const showWater = waterCurrent != null && waterTarget != null && waterTarget > 0;
  const waterPct = showWater ? (waterCurrent! / waterTarget!) * 100 : 0;
  const waterRemaining = showWater ? Math.max(0, Math.round(waterTarget! - waterCurrent!)) : 0;

  return (
    <StatusSummaryShell
      icon="clipboard-outline"
      title="今日饮食汇总"
      subtitle={dateLabel ? `北京时间 · ${dateLabel}` : undefined}
    >
      {meals.length > 0 || hasTotals ? (
        <View style={styles.table}>
          <View style={[styles.row, styles.headRow]}>
            <View style={styles.mealCol} />
            {MACRO_HEADERS.map((h) => (
              <Text key={h} maxFontSizeMultiplier={1.1} style={[styles.headCell, styles.numCol]}>{h}</Text>
            ))}
          </View>

          {meals.map((meal, i) => (
            <View key={i} style={[styles.row, styles.mealRow, i < meals.length - 1 ? styles.rowDivider : null]}>
              <View style={[styles.mealCol, styles.mealLeft]}>
                <Ionicons name={meal.icon} size={14} color={C.ink2} style={styles.mealIcon} />
                <View style={styles.mealTextWrap}>
                  <Text maxFontSizeMultiplier={1.25} style={styles.mealName} numberOfLines={1}>{meal.name}</Text>
                  {meal.detail ? (
                    <Text maxFontSizeMultiplier={1.2} style={styles.mealDetail} numberOfLines={2}>{meal.detail}</Text>
                  ) : null}
                </View>
              </View>
              {meal.values.map((v, ci) => (
                <Text key={ci} maxFontSizeMultiplier={1.2} style={[styles.valueCell, styles.numCol]}>{v ?? '—'}</Text>
              ))}
            </View>
          ))}

          {hasTotals ? (
            <View style={[styles.row, styles.totalRow]}>
              <Text maxFontSizeMultiplier={1.25} style={[styles.totalLabel, styles.mealCol]}>全天合计</Text>
              {totals.map((v, ci) => (
                <Text key={ci} maxFontSizeMultiplier={1.2} style={[styles.totalCell, styles.numCol]}>{v ?? '—'}</Text>
              ))}
            </View>
          ) : null}

          <Text maxFontSizeMultiplier={1.1} style={styles.unitLegend}>热量 kcal · 蛋白 / 碳水 / 脂肪 g</Text>
        </View>
      ) : null}

      <StatusObservationList items={observations} />

      {showWater ? (
        <StatusProgressBar
          label="饮水进度"
          valueText={`${waterCurrent}/${waterTarget}ml`}
          pct={waterPct}
          hint={waterRemaining > 0 ? `还差约 ${waterRemaining}ml` : undefined}
          tone="info"
        />
      ) : null}
    </StatusSummaryShell>
  );
}

export const DietSummaryCardSpec: CardSpec = {
  type: 'diet_daily_summary',
  label: '今日饮食汇总',
  match() {
    return null; // 仅接受后端下发 (reva-ui fence), 不本地关键词触发
  },
  build() {
    return null;
  },
  render: (data) => <DietSummaryCardView data={data} />,
};

// 领域专属样式:餐次×宏量表(壳/头/观察/进度条样式在 statusSummary.tsx)。
const styles = StyleSheet.create({
  table: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
  },
  headRow: { paddingTop: 8, paddingBottom: 5 },
  mealRow: { paddingVertical: 8 },
  rowDivider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line },
  mealCol: { flex: 1.7 },
  numCol: { flex: 1, textAlign: 'right' },
  mealLeft: { flexDirection: 'row', alignItems: 'flex-start', gap: 6 },
  mealIcon: { marginTop: 1 },
  mealTextWrap: { flexShrink: 1, gap: 1 },
  mealName: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    fontWeight: '700',
    color: C.ink1,
    lineHeight: 17,
  } as TextStyle,
  mealDetail: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.ink3,
    lineHeight: 15,
  } as TextStyle,
  headCell: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '600',
    letterSpacing: 0.3,
    color: C.ink3,
  } as TextStyle,
  valueCell: {
    fontFamily: revaFonts.mono,
    fontSize: 13,
    fontWeight: '500',
    color: C.ink1,
    lineHeight: 17,
    fontVariant: ['tabular-nums'],
  } as TextStyle,
  totalRow: {
    paddingTop: 9,
    paddingBottom: 2,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.lineStrong,
  },
  totalLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    fontWeight: '800',
    color: C.ink1,
    lineHeight: 17,
  } as TextStyle,
  totalCell: {
    fontFamily: revaFonts.mono,
    fontSize: 13,
    fontWeight: '700',
    color: C.ink1,
    lineHeight: 17,
    fontVariant: ['tabular-nums'],
  } as TextStyle,
  unitLegend: {
    marginTop: 7,
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 14,
  } as TextStyle,
});
