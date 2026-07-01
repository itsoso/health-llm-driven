import React from 'react';
import { Pressable, StyleSheet, Text, TextInput, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import type { CardRenderOptions, CardSpec } from './types';
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

interface DietDraftCardViewProps extends DietDraftData {
  onDraftChange?: (data: DietDraftData) => void;
}

type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snack';

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

function editNumber(value: unknown): string {
  const parsed = numberValue(value);
  return parsed == null ? '' : String(Math.round(parsed * 10) / 10);
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

function sanitizeNumberText(value: string): number | undefined {
  const parsed = Number(value.trim());
  return Number.isFinite(parsed) && parsed >= 0 ? Math.round(parsed * 10) / 10 : undefined;
}

function mealTypeValue(value: unknown): MealType {
  const raw = text(value);
  return raw && raw in MEAL_LABELS ? raw as MealType : 'snack';
}

export function DietDraftCardView(data: DietDraftCardViewProps) {
  const [editing, setEditing] = React.useState(false);
  const [draftMealType, setDraftMealType] = React.useState<MealType>(() => mealTypeValue(data.meal_type));
  const [draftFood, setDraftFood] = React.useState(() => foodText(data.food_items) || '');
  const [draftCalories, setDraftCalories] = React.useState(() => editNumber(data.calories));
  const [draftProtein, setDraftProtein] = React.useState(() => editNumber(data.protein));
  const [draftCarbs, setDraftCarbs] = React.useState(() => editNumber(data.carbs));
  const [draftFat, setDraftFat] = React.useState(() => editNumber(data.fat));
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
      <View style={styles.inlineHeader}>
        <Text maxFontSizeMultiplier={1.15} style={styles.inlineHint}>
          确认前可修正餐次、食物和营养估算
        </Text>
        <Pressable
          onPress={() => setEditing((prev) => !prev)}
          accessibilityRole="button"
          accessibilityLabel={editing ? '收起修正' : '修正饮食草稿'}
          style={({ pressed }) => [styles.editButton, pressed && styles.editButtonPressed]}
        >
          <Ionicons name={editing ? 'chevron-up' : 'create-outline'} size={12} color={DIET_ACCENT} />
          <Text style={styles.editButtonText}>{editing ? '收起' : '修正'}</Text>
        </Pressable>
      </View>

      <Text maxFontSizeMultiplier={1.25} style={styles.food} numberOfLines={3}>
        {foodItems}
      </Text>

      {editing ? (
        <View style={styles.editor}>
          <View style={styles.mealTypeRow}>
            {(Object.keys(MEAL_LABELS) as MealType[]).map((key) => (
              <Pressable
                key={key}
                onPress={() => setDraftMealType(key)}
                accessibilityRole="button"
                accessibilityLabel={`餐次 ${MEAL_LABELS[key]}`}
                style={[
                  styles.mealChip,
                  draftMealType === key && styles.mealChipActive,
                ]}
              >
                <Text style={[
                  styles.mealChipText,
                  draftMealType === key && styles.mealChipTextActive,
                ]}>
                  {MEAL_LABELS[key]}
                </Text>
              </Pressable>
            ))}
          </View>
          <TextInput
            accessibilityLabel="食物描述"
            value={draftFood}
            onChangeText={setDraftFood}
            placeholder="食物描述"
            placeholderTextColor={C.ink4}
            multiline
            style={styles.foodInput}
          />
          <View style={styles.editMacroGrid}>
            <DraftNumberInput label="热量" unit="kcal" value={draftCalories} onChangeText={setDraftCalories} />
            <DraftNumberInput label="蛋白" unit="g" value={draftProtein} onChangeText={setDraftProtein} />
            <DraftNumberInput label="碳水" unit="g" value={draftCarbs} onChangeText={setDraftCarbs} />
            <DraftNumberInput label="脂肪" unit="g" value={draftFat} onChangeText={setDraftFat} />
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="应用饮食草稿修正"
            style={({ pressed }) => [styles.applyButton, pressed && { opacity: 0.86 }]}
            onPress={() => {
              const next: DietDraftData = {
                ...data,
                meal_type: draftMealType,
                food_items: draftFood.trim() || data.food_items,
              };
              const calories = sanitizeNumberText(draftCalories);
              const protein = sanitizeNumberText(draftProtein);
              const carbs = sanitizeNumberText(draftCarbs);
              const fat = sanitizeNumberText(draftFat);
              if (calories != null) next.calories = calories;
              if (protein != null) next.protein = protein;
              if (carbs != null) next.carbs = carbs;
              if (fat != null) next.fat = fat;
              data.onDraftChange?.(next);
              setEditing(false);
            }}
          >
            <Text style={styles.applyButtonText}>应用修正</Text>
          </Pressable>
        </View>
      ) : null}

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
  render: (data, options?: CardRenderOptions) => (
    <DietDraftCardView {...data} onDraftChange={options?.onCardDataChange} />
  ),
};

function DraftNumberInput({
  label,
  unit,
  value,
  onChangeText,
}: {
  label: string;
  unit: string;
  value: string;
  onChangeText: (value: string) => void;
}) {
  return (
    <View style={styles.editMacroCell}>
      <Text style={styles.editMacroLabel}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        value={value}
        onChangeText={onChangeText}
        keyboardType="decimal-pad"
        placeholder="0"
        placeholderTextColor={C.ink4}
        style={styles.editMacroInput}
      />
      <Text style={styles.editMacroUnit}>{unit}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  inlineHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8,
  },
  inlineHint: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11.5,
    lineHeight: 16,
    color: C.ink3,
    fontWeight: '700',
  } as TextStyle,
  editButton: {
    minHeight: 28,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    borderRadius: revaRadii.pill,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    paddingHorizontal: 9,
  },
  editButtonPressed: {
    opacity: 0.78,
  },
  editButtonText: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: DIET_ACCENT,
    fontWeight: '800',
  } as TextStyle,
  food: {
    fontFamily: revaFonts.sans,
    fontSize: 15,
    lineHeight: 21,
    fontWeight: '800',
    color: C.ink1,
  } as TextStyle,
  editor: {
    gap: 9,
    marginTop: 10,
    marginBottom: 2,
    borderRadius: revaRadii.md,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    padding: 10,
  },
  mealTypeRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
  },
  mealChip: {
    minHeight: 30,
    justifyContent: 'center',
    borderRadius: revaRadii.pill,
    backgroundColor: C.paper2,
    paddingHorizontal: 11,
  },
  mealChipActive: {
    backgroundColor: DIET_ACCENT,
  },
  mealChipText: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: C.ink2,
    fontWeight: '800',
  } as TextStyle,
  mealChipTextActive: {
    color: '#fff',
  } as TextStyle,
  foodInput: {
    minHeight: 44,
    borderRadius: revaRadii.sm,
    backgroundColor: C.paper2,
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontFamily: revaFonts.sans,
    fontSize: 13,
    color: C.ink1,
  } as TextStyle,
  editMacroGrid: {
    flexDirection: 'row',
    gap: 7,
  },
  editMacroCell: {
    flex: 1,
    alignItems: 'center',
    gap: 3,
  },
  editMacroLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    fontWeight: '700',
  } as TextStyle,
  editMacroInput: {
    width: '100%',
    minHeight: 34,
    borderRadius: revaRadii.sm,
    backgroundColor: C.paper2,
    paddingHorizontal: 6,
    paddingVertical: 5,
    fontFamily: revaFonts.mono,
    fontSize: 13,
    color: C.ink1,
    textAlign: 'center',
  } as TextStyle,
  editMacroUnit: {
    fontFamily: revaFonts.mono,
    fontSize: 9.5,
    color: C.ink3,
  } as TextStyle,
  applyButton: {
    minHeight: 34,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: revaRadii.sm,
    backgroundColor: DIET_ACCENT,
  },
  applyButtonText: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    color: '#fff',
    fontWeight: '900',
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
