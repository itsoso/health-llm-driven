/**
 * DietSummaryCard — 「今日饮食汇总」结构化卡 (汇总类卡 v1, Reva 设计语言)。
 *
 * 后端经 ```reva-ui fence 内联下发(与 metric_table 同一通道):
 *   {"type":"diet_daily_summary","v":1,"data":{...}}
 * → ChatBubble extractRevaUiBlocks(utils/revaUiBlocks.ts 有 diet 分支)→ renderCard
 * → 本卡渲染 (仅后端下发, match/build 恒 null)。**v 是整数 1**,parser 校验 v===1。
 *
 * 视觉:2 行头(📋 + 标题 + 北京时间副行) → 餐次×宏量表(右列 mono tabular 右对齐)
 * → 全天合计(粗 + 顶发丝) → 关键观察(三步临床语义色) → 饮水进度(info 蓝条)。
 * 全部走 revaTheme token,数字 tabular-nums,防御性解析,字段缺失降级不崩。
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import type { TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaShadows,
  revaSemantic,
  revaSpacing,
  type RevaStatus,
} from '../../../constants/revaTheme';
import { MEAL_ICONS } from './mealCardVisuals';
import type { CardSpec } from './types';

type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snack';

const MEAL_LABELS: Record<MealType, string> = {
  breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐',
};

// 表列顺序 = 契约字段 → 表头。热量为 kcal, 其余为 g(见 unitLegend)。
const MACRO_KEYS = ['calories', 'protein', 'carbs', 'fat'] as const;
const MACRO_HEADERS = ['热量', '蛋白', '碳水', '脂肪'] as const;

const OBS_STATUS: Record<string, RevaStatus> = { normal: 'normal', caution: 'caution', risk: 'risk' };
const OBS_ICON: Record<RevaStatus, keyof typeof Ionicons.glyphMap> = {
  normal: 'checkmark-circle', caution: 'warning', risk: 'alert-circle', info: 'information-circle',
};

interface Meal {
  icon: keyof typeof Ionicons.glyphMap;
  name: string;
  detail?: string;
  values: (string | null)[]; // 4 列宏量, null → 缺值渲染 '—'
}

interface Observation {
  status: RevaStatus;
  label: string;
  detail?: string;
}

// ── 防御性解析 ────────────────────────────────────────────────────────────
function text(v: unknown): string | undefined {
  if (typeof v === 'string') { const t = v.trim(); return t || undefined; }
  if (typeof v === 'number' && Number.isFinite(v)) return String(v);
  return undefined;
}
function num(v: unknown): number | undefined {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string' && v.trim()) { const n = Number(v.trim()); return Number.isFinite(n) ? n : undefined; }
  return undefined;
}
/** 展示数字:整数原样, 否则最多 1 位小数(founder ≤2 位规范内)。缺值 → null。 */
function fmtNum(v: unknown): string | null {
  const n = num(v);
  if (n == null) return null;
  return Number.isInteger(n) ? String(n) : String(Math.round(n * 10) / 10);
}
function macroCells(source: unknown): (string | null)[] {
  const r = (source && typeof source === 'object') ? (source as Record<string, unknown>) : {};
  return MACRO_KEYS.map((k) => fmtNum(r[k]));
}
/** ISO record_date → 「M月D日」;非 ISO 原样;空 → undefined。 */
function formatDate(raw: unknown): string | undefined {
  const s = text(raw);
  if (!s) return undefined;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  return m ? `${Number(m[2])}月${Number(m[3])}日` : s;
}
function parseMeals(raw: unknown): Meal[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item): Meal | null => {
      if (!item || typeof item !== 'object') return null;
      const r = item as Record<string, unknown>;
      const mealType = text(r.meal_type) as MealType | undefined;
      const name = text(r.name) || (mealType ? MEAL_LABELS[mealType] : undefined) || '餐次';
      const icon = (mealType && MEAL_ICONS[mealType]) || 'restaurant';
      return { icon, name, detail: text(r.detail), values: macroCells(r) };
    })
    .filter((m): m is Meal => m != null);
}
function parseObservations(raw: unknown): Observation[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item): Observation | null => {
      if (!item || typeof item !== 'object') return null;
      const r = item as Record<string, unknown>;
      const label = text(r.label);
      if (!label) return null;
      const status = OBS_STATUS[text(r.severity) || ''] || 'normal';
      return { status, label, detail: text(r.detail) };
    })
    .filter((o): o is Observation => o != null);
}

export function DietSummaryCardView({ data }: { data?: unknown }) {
  const d = (data && typeof data === 'object') ? (data as Record<string, any>) : {};
  const dateLabel = formatDate(d.record_date);
  const meals = parseMeals(d.meals);
  const totals = macroCells(d.totals);
  const hasTotals = totals.some((v) => v != null);
  const observations = parseObservations(d.observations);

  const waterCurrent = num(d.water?.current_ml);
  const waterTarget = num(d.water?.target_ml);
  const showWater = waterCurrent != null && waterTarget != null && waterTarget > 0;
  const waterPct = showWater ? Math.max(0, Math.min(100, (waterCurrent! / waterTarget!) * 100)) : 0;
  const waterRemaining = showWater ? Math.max(0, Math.round(waterTarget! - waterCurrent!)) : 0;

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Ionicons name="clipboard-outline" size={16} color={C.green500} />
        <View style={styles.headerText}>
          <Text maxFontSizeMultiplier={1.3} style={styles.title}>今日饮食汇总</Text>
          {dateLabel ? (
            <Text maxFontSizeMultiplier={1.2} style={styles.subtitle}>北京时间 · {dateLabel}</Text>
          ) : null}
        </View>
      </View>

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

      {observations.length > 0 ? (
        <View style={styles.obsSection}>
          <Text maxFontSizeMultiplier={1.1} style={styles.sectionLabel}>关键观察</Text>
          {observations.map((obs, i) => (
            <View key={i} style={styles.obsRow}>
              <Ionicons name={OBS_ICON[obs.status]} size={14} color={revaSemantic[obs.status].fg} style={styles.obsIcon} />
              <Text maxFontSizeMultiplier={1.2} style={styles.obsBody}>
                <Text style={[styles.obsLabel, { color: revaSemantic[obs.status].fg }]}>{obs.label}</Text>
                {obs.detail ? <Text style={styles.obsDetail}>{`  ${obs.detail}`}</Text> : null}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      {showWater ? (
        <View style={styles.waterSection}>
          <View style={styles.waterHead}>
            <Text maxFontSizeMultiplier={1.1} style={styles.sectionLabel}>饮水进度</Text>
            <Text maxFontSizeMultiplier={1.1} style={styles.waterValue}>{waterCurrent}/{waterTarget}ml</Text>
          </View>
          <View style={styles.waterTrack}>
            <View style={[styles.waterFill, { width: `${waterPct}%` }]} />
          </View>
          {waterRemaining > 0 ? (
            <Text maxFontSizeMultiplier={1.1} style={styles.waterHint}>还差约 {waterRemaining}ml</Text>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

export const DietSummaryCardSpec: CardSpec = {
  type: 'diet_daily_summary',
  label: '今日饮食汇总',
  match() {
    return null; // 仅接受后端下发 (done.cards / meta.cards), 不本地关键词触发
  },
  build() {
    return null;
  },
  render: (data) => <DietSummaryCardView data={data} />,
};

const styles = StyleSheet.create({
  card: {
    borderRadius: revaRadii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.surface,
    paddingHorizontal: revaSpacing.s4,
    paddingVertical: revaSpacing.s3 + 2,
    marginVertical: revaSpacing.s2,
    minWidth: 240,
    ...revaShadows.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: revaSpacing.s2,
    marginBottom: revaSpacing.s3,
  },
  headerText: { flexShrink: 1, gap: 2 },
  title: {
    fontFamily: revaFonts.sans,
    fontSize: 14,
    fontWeight: '800',
    color: C.ink1,
    lineHeight: 19,
  } as TextStyle,
  subtitle: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.ink3,
    lineHeight: 15,
  } as TextStyle,

  table: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
  },
  headRow: { paddingTop: revaSpacing.s2, paddingBottom: 5 },
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

  obsSection: { marginTop: revaSpacing.s3, gap: 6 },
  sectionLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.3,
    color: C.ink3,
  } as TextStyle,
  obsRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 6 },
  obsIcon: { marginTop: 1 },
  obsBody: { flex: 1, lineHeight: 17 } as TextStyle,
  obsLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '700',
  } as TextStyle,
  obsDetail: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: C.ink2,
  } as TextStyle,

  waterSection: {
    marginTop: revaSpacing.s3,
    gap: 5,
    paddingHorizontal: 10,
    paddingVertical: 9,
    borderRadius: revaRadii.md,
    backgroundColor: revaSemantic.info.bg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaSemantic.info.line,
  },
  waterHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  waterValue: {
    fontFamily: revaFonts.mono,
    fontSize: 13,
    fontWeight: '700',
    color: revaSemantic.info.fg,
    lineHeight: 16,
    fontVariant: ['tabular-nums'],
  } as TextStyle,
  waterTrack: {
    height: 6,
    borderRadius: 3,
    backgroundColor: revaSemantic.info.line,
    overflow: 'hidden',
  },
  waterFill: {
    height: '100%',
    borderRadius: 3,
    backgroundColor: revaSemantic.info.fg,
  },
  waterHint: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 14,
  } as TextStyle,
});
