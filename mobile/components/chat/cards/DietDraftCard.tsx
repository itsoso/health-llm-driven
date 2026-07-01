import React from 'react';
import { StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import type { CardSpec } from './types';
import { revaColors as C, revaFonts, revaRadii, revaSemantic } from '../../../constants/revaTheme';

const DIET_ACCENT = '#C97A2E';
const DIET_TINT = '#F6E9DA';

const MEAL_LABELS: Record<string, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '加餐',
};

const SOURCE_LABELS: Record<string, string> = {
  chat: '对话',
  chat_photo: '对话/图片',
  photo: '图片',
  voice: '语音',
  text: '文字',
  meal_monitor: '餐食监控',
};

interface DietDraftData {
  meal_type?: unknown;
  food_items?: unknown;
  calories?: unknown;
  protein?: unknown;
  carbs?: unknown;
  fat?: unknown;
  fiber?: unknown;
  confidence?: unknown;
  source?: unknown;
  suggestions?: unknown;
  post_meal_walk?: unknown;
  boundary?: unknown;
}

function text(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed || undefined;
  }
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return undefined;
}

function foodText(value: unknown): string | undefined {
  if (Array.isArray(value)) {
    const items = value.map(text).filter((item): item is string => Boolean(item));
    return items.length ? items.slice(0, 6).join(' + ') : undefined;
  }
  return text(value);
}

function numberValue(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value.trim());
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

function listText(value: unknown): string[] {
  const raw = Array.isArray(value) ? value : value == null ? [] : [value];
  return raw.map(text).filter((item): item is string => Boolean(item)).slice(0, 3);
}

function macroRows(data: DietDraftData) {
  return [
    { label: '热量', value: numberValue(data.calories), suffix: 'kcal', color: '#FF6723' },
    { label: '蛋白', value: numberValue(data.protein), suffix: 'g', color: '#C2487A' },
    { label: '碳水', value: numberValue(data.carbs), suffix: 'g', color: '#C98A1E' },
    { label: '脂肪', value: numberValue(data.fat), suffix: 'g', color: '#7C5CBF' },
    { label: '纤维', value: numberValue(data.fiber), suffix: 'g', color: C.green500 },
  ].filter((row) => row.value != null && row.value >= 0);
}

function confidenceLabel(value: unknown): string | undefined {
  const confidence = numberValue(value);
  if (confidence == null) return undefined;
  const normalized = confidence <= 1 ? confidence * 100 : confidence;
  if (normalized <= 0) return undefined;
  return `置信度 ${Math.round(Math.min(100, normalized))}%`;
}

function sourceLabel(value: unknown): string | undefined {
  const source = text(value);
  if (!source) return undefined;
  return `来源: ${SOURCE_LABELS[source] || source}`;
}

function postMealWalkText(value: unknown): string | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const raw = value as Record<string, unknown>;
  if (raw.recommended !== true) return undefined;
  const minutes = numberValue(raw.minutes) ?? 10;
  return `餐后轻走 ${Math.round(minutes)} 分钟`;
}

export function DietDraftCardView(data: DietDraftData) {
  const foodItems = foodText(data.food_items) || '待确认餐食';
  const mealType = text(data.meal_type);
  const mealLabel = mealType ? (MEAL_LABELS[mealType] || mealType) : '餐食';
  const macros = macroRows(data);
  const meta = [confidenceLabel(data.confidence), sourceLabel(data.source)].filter(Boolean).join(' · ');
  const suggestions = listText(data.suggestions);
  const walkText = postMealWalkText(data.post_meal_walk);
  const boundary = text(data.boundary) || '营养为估算值,确认后写入今日饮食记录。';

  return (
    <CardShell
      icon="restaurant-outline"
      iconColor={DIET_ACCENT}
      title="待确认饮食记录"
      badge={mealLabel}
      badgeColor={DIET_ACCENT}
      bg={DIET_TINT}
    >
      <Text maxFontSizeMultiplier={1.25} style={styles.food} numberOfLines={3}>
        {foodItems}
      </Text>

      {macros.length > 0 ? (
        <View style={styles.macroGrid}>
          {macros.map((row) => (
            <View key={row.label} style={styles.macroPill}>
              <Text maxFontSizeMultiplier={1.1} style={styles.macroLabel}>
                {row.label}{' '}
                <Text style={[styles.macroValue, { color: row.color }]}>
                  {Math.round(row.value!)}{row.suffix}
                </Text>
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      {meta ? (
        <Text maxFontSizeMultiplier={1.15} style={styles.meta}>
          {meta}
        </Text>
      ) : null}

      {(walkText || suggestions.length > 0) ? (
        <View style={styles.nextBox}>
          {walkText ? (
            <View style={styles.nextRow}>
              <Ionicons name="footsteps-outline" size={13} color={C.green600} />
              <Text maxFontSizeMultiplier={1.15} style={styles.nextText}>{walkText}</Text>
            </View>
          ) : null}
          {suggestions.map((item) => (
            <View key={item} style={styles.nextRow}>
              <Ionicons name="arrow-forward-circle-outline" size={13} color={C.green600} />
              <Text maxFontSizeMultiplier={1.15} style={styles.nextText}>{item}</Text>
            </View>
          ))}
        </View>
      ) : null}

      <View style={styles.boundaryRow}>
        <Ionicons name="information-circle-outline" size={12} color={revaSemantic.caution.fg} />
        <Text maxFontSizeMultiplier={1.15} style={styles.boundary}>
          {boundary}
        </Text>
      </View>
    </CardShell>
  );
}

export const DietDraftCardSpec: CardSpec<DietDraftData> = {
  type: 'diet_draft',
  label: '饮食草稿',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data) => <DietDraftCardView {...data} />,
};

const styles = StyleSheet.create({
  food: {
    fontFamily: revaFonts.sans,
    fontSize: 15,
    lineHeight: 21,
    fontWeight: '800',
    color: C.ink1,
  } as TextStyle,
  macroGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
    marginTop: 9,
  },
  macroPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    borderRadius: revaRadii.pill,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  macroLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.ink3,
    fontWeight: '700',
  } as TextStyle,
  macroValue: {
    fontFamily: revaFonts.mono,
    fontSize: 11.5,
    fontWeight: '900',
    fontVariant: ['tabular-nums'] as const,
  } as TextStyle,
  meta: {
    marginTop: 8,
    fontFamily: revaFonts.sans,
    fontSize: 11.5,
    color: C.ink3,
    fontWeight: '700',
  } as TextStyle,
  nextBox: {
    gap: 6,
    marginTop: 9,
    borderRadius: revaRadii.sm,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    paddingHorizontal: 9,
    paddingVertical: 8,
  },
  nextRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
  },
  nextText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 12.2,
    lineHeight: 17,
    color: C.ink2,
    fontWeight: '700',
  } as TextStyle,
  boundaryRow: {
    marginTop: 8,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 5,
  },
  boundary: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 16,
    color: C.ink3,
  } as TextStyle,
});
