import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { revaColors as C, revaRadii, revaFonts, revaSemantic } from '../../../constants/revaTheme';
import { MEAL_ICONS, MacroBar, IngredientChips } from './mealCardVisuals';
import type { CardSpec } from './types';

// RecordData: 保持既有键 type/detail 不变;新增的营养字段全为可选 (additive) —
// 仅当后端下发的记录卡带 food/macros 时才走餐食可视化, 本地 build() 从不填充它们.
interface RecordData {
  type: string;
  detail: string;
  food?: string | string[];
  calories?: number;
  protein?: number;
  carbs?: number;
  fat?: number;
  fiber?: number;
  meal_type?: string;
}

// 每类记录的 accent + tint = 「是哪类记录」的装饰色码 (饮水蓝/补剂紫/饮食橙/运动粉…),
// 非「好坏」临床语义, 故保留 Reva 亮色调色板字面量 (= legacy color/tint 值) → 无视觉回归.
const RECORD_ICONS: Record<string, { icon: string; color: string; bg: string }> = {
  water:           { icon: 'water',             color: '#2A6FDB', bg: '#E4ECF8' },
  supplement:      { icon: 'medical',           color: '#7C5CBF', bg: '#EDE7F6' },
  diet:            { icon: 'restaurant',        color: '#C97A2E', bg: '#F6E9DA' },
  exercise:        { icon: 'fitness',           color: '#C2487A', bg: '#F7E4EC' },
  weight:          { icon: 'scale',             color: C.green500, bg: C.green50 },
  blood_pressure:  { icon: 'heart',             color: '#D5503A', bg: '#F7E4E0' },
  rhinitis:        { icon: 'water',             color: '#2F9E8F', bg: '#E0EFEC' },
  checkin:         { icon: 'checkbox',          color: C.green500, bg: C.green50 },
  medication:      { icon: 'flask',             color: '#7C5CBF', bg: '#EDE7F6' },
  reminder:        { icon: 'notifications',     color: '#2F7D67', bg: '#DFF1EA' },
  default:         { icon: 'checkmark-circle',  color: C.green500, bg: C.green50 },
};

// 饮食类目 accent (橙) — 与 DietDraftCard / record.tsx legacy 一致.
const DIET_ACCENT = '#C97A2E';

const MEAL_LABELS: Record<string, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '加餐',
};

type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snack';

// 防御闸: 后端若漏把原始 JSON 当 detail (历史 bug: tool result 无 message 字段时
// fallback 倒出整段 {"record_date":...}), 这里兜底成 "已记录", 绝不把 JSON 渲染给用户.
function safeDetail(detail: string): string {
  const trimmed = (detail || '').trim();
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) return '已记录';
  return trimmed || '已记录';
}

function numberValue(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value.trim());
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

/** 拆 food 成独立食材条 (数组 or " + "/"、" 分隔的字符串), 供 chip 渲染。 */
function foodChips(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => (typeof item === 'string' ? item.trim() : ''))
      .filter(Boolean)
      .slice(0, 8);
  }
  if (typeof value !== 'string') return [];
  const joined = value.trim();
  if (!joined) return [];
  return joined
    .split(/\s*[+＋、,]\s*/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 8);
}

function mealTypeValue(value: unknown): MealType | undefined {
  const raw = typeof value === 'string' ? value.trim() : '';
  return raw && raw in MEAL_LABELS ? (raw as MealType) : undefined;
}

/** 是否为「带餐食营养」的饮食记录 — 有 food 或任一 macro/热量时才走餐食可视化。 */
function isDietRecord(d: RecordData): boolean {
  if (d.type !== 'diet') return false;
  const chips = foodChips(d.food);
  const hasMacro = [d.calories, d.protein, d.carbs, d.fat, d.fiber]
    .some((v) => numberValue(v) != null);
  return chips.length > 0 || hasMacro;
}

/** 饮食记录卡 — 复用 mealCardVisuals (MEAL_ICONS / MacroBar / IngredientChips)。 */
function DietRecordCardView(d: RecordData) {
  const mealType = mealTypeValue(d.meal_type);
  const mealLabel = mealType ? MEAL_LABELS[mealType] : '餐食';
  const chips = foodChips(d.food);
  const calories = numberValue(d.calories);
  const protein = numberValue(d.protein);
  const carbs = numberValue(d.carbs);
  const fat = numberValue(d.fat);
  const fiber = numberValue(d.fiber);
  return (
    <View style={[styles.card, styles.dietCard]}>
      <View style={styles.dietHeader}>
        <Ionicons
          name={(mealType ? MEAL_ICONS[mealType] : 'restaurant') as any}
          size={15}
          color={DIET_ACCENT}
        />
        <Text maxFontSizeMultiplier={1.2} style={txt.dietTitle} numberOfLines={1}>
          {mealLabel}已记录
        </Text>
        <View style={styles.dietBadge}>
          <Text maxFontSizeMultiplier={1.15} style={txt.dietBadge}>饮食</Text>
        </View>
      </View>

      {/* 热量 hero：大号等宽数字 + 单位 (Math.round, tabular)。无值 → 不渲染。 */}
      {calories != null ? (
        <Text maxFontSizeMultiplier={1.18} style={txt.dietHero}>
          {Math.round(calories)}
          <Text style={txt.dietHeroUnit}> kcal</Text>
        </Text>
      ) : null}

      {/* 分段营养条：总热量 ≤ 0 或无 macro → MacroBar 自身返回 null。 */}
      <MacroBar protein={protein} carbs={carbs} fat={fat} fiber={fiber} style={styles.dietMacroBar} />

      {/* 食材 chips */}
      <IngredientChips items={chips} style={styles.dietChips} />
    </View>
  );
}

export function RecordCardView(d: RecordData) {
  if (isDietRecord(d)) {
    return <DietRecordCardView {...d} />;
  }
  const cfg = RECORD_ICONS[d.type] || RECORD_ICONS.default;
  return (
    <View style={[styles.card, styles.simpleCard]}>
      <Ionicons name={cfg.icon as any} size={16} color={cfg.color} />
      <Text maxFontSizeMultiplier={1.3} style={txt.text}>
        {safeDetail(d.detail)}
      </Text>
      <Ionicons name="checkmark-circle" size={14} color={C.green500} />
    </View>
  );
}

export const RecordCardSpec: CardSpec<RecordData> = {
  type: 'record',
  label: '记录确认',
  match({ query_lower, toolsUsed }) {
    if (toolsUsed.has('health_record')) return 20;
    if (/记录|打卡|吃了|喝了|喝水|服药|补剂.*吃|刚吃|刚喝|体重是|血压是|洗鼻了|喷嚏|提醒|闹钟/.test(query_lower)) return 12;
    return null;
  },
  build({ query_lower }) {
    let type = 'default';
    if (/喝水|喝了.*水/.test(query_lower)) type = 'water';
    else if (/补剂|服药/.test(query_lower)) type = 'supplement';
    else if (/吃了|早餐|午餐|晚餐|加餐/.test(query_lower)) type = 'diet';
    else if (/体重/.test(query_lower)) type = 'weight';
    else if (/血压/.test(query_lower)) type = 'blood_pressure';
    else if (/喷嚏|洗鼻|鼻炎/.test(query_lower)) type = 'rhinitis';
    else if (/提醒|闹钟/.test(query_lower)) type = 'reminder';
    else if (/跑|运动|锻炼|训练/.test(query_lower)) type = 'exercise';
    return { type, detail: '已记录' };
  },
  render: (d) => <RecordCardView {...d} />,
};

const styles = StyleSheet.create({
  // 统一容器基线: surface 底 + 发丝边 + revaRadii + 软阴影 (与新卡一致).
  card: {
    borderRadius: revaRadii.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.surface,
    marginVertical: 4,
  },
  // 非饮食记录: 单行图标 + 文本 + 勾, padding 与旧版一致 (10).
  simpleCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    padding: 10,
  },
  dietCard: {
    padding: 12,
  },
  dietHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  dietBadge: {
    marginLeft: 'auto',
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: 8,
    backgroundColor: revaSemantic.normal.bg,
  },
  dietMacroBar: {
    marginTop: 10,
  },
  dietChips: {
    marginTop: 10,
  },
});

const txt = {
  text: { fontFamily: revaFonts.sans, fontSize: 13, flex: 1, color: C.ink1 } as TextStyle,
  dietTitle: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '700', color: C.ink1, flexShrink: 1 } as TextStyle,
  dietBadge: { fontFamily: revaFonts.sans, fontSize: 10, fontWeight: '700', color: revaSemantic.normal.fg } as TextStyle,
  dietHero: {
    fontFamily: revaFonts.mono,
    fontSize: 28,
    fontWeight: '800',
    color: C.ink1,
    fontVariant: ['tabular-nums'] as const,
    marginTop: 8,
  } as TextStyle,
  dietHeroUnit: { fontFamily: revaFonts.mono, fontSize: 13, fontWeight: '400', color: C.ink3 } as TextStyle,
};
