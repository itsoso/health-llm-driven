/**
 * 餐食卡共享可视化件 —— DietCard(今日汇总)与 DietDraftCard(单餐结果/草稿)共用。
 *
 * - MEAL_ICONS: 餐次 → Ionicons(早/午/晚/加餐)。
 * - MACRO_HUES: 营养素装饰 hue(脂肪=琥珀 / 碳水=蓝 / 蛋白=橙 / 纤维=绿)。这是「区分类目」
 *   的色码, 不是「指标好坏」三步临床语义, 故 amber/blue/green 走 token, 蛋白橙沿用 App
 *   饮食 accent 字面量(与 record.tsx / DietCard legacy 一致)。
 * - MacroBar: 一条按「热量占比」拆分的横条(蛋白×4 / 碳水×4 / 脂肪×9 / 纤维×2)。
 *   总热量 ≤ 0 或无 macro → 不渲染(护栏)。
 * - IngredientChips: 食材 pill chips(surface 底 + line 边 + full 圆角)。
 */
import React from 'react';
import { StyleSheet, Text, TextStyle, View, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { revaColors as C, revaFonts, revaRadii, revaSemantic } from '../../../constants/revaTheme';

type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snack';

export const MEAL_ICONS: Record<MealType, keyof typeof Ionicons.glyphMap> = {
  breakfast: 'cafe',
  lunch: 'restaurant',
  dinner: 'moon',
  snack: 'nutrition',
};

// 营养素装饰 hue。amber/blue/green 用 Reva token；蛋白橙沿用 App 饮食 accent 字面量。
export const MACRO_HUES = {
  protein: '#C97A2E', // 橙 (= DIET_ACCENT / CAT_HUES.orange, 全 App 一致)
  carbs: C.blue500, // 蓝
  fat: revaSemantic.caution.fg, // 琥珀
  fiber: C.green500, // 绿
} as const;

// 每克热量系数 (Atwater): 蛋白 4 / 碳水 4 / 脂肪 9 / 纤维 ≈2。用于把 macro 折成热量占比。
const KCAL_PER_G = { protein: 4, carbs: 4, fat: 9, fiber: 2 } as const;

interface MacroBarProps {
  protein?: number;
  carbs?: number;
  fat?: number;
  fiber?: number;
  style?: ViewStyle;
}

/** 分段营养条：按热量占比拆一条横条。总热量 ≤ 0 或无 macro → 返回 null。 */
export function MacroBar({ protein, carbs, fat, fiber, style }: MacroBarProps) {
  const segments = [
    { key: 'protein', kcal: (protein ?? 0) * KCAL_PER_G.protein, color: MACRO_HUES.protein },
    { key: 'carbs', kcal: (carbs ?? 0) * KCAL_PER_G.carbs, color: MACRO_HUES.carbs },
    { key: 'fat', kcal: (fat ?? 0) * KCAL_PER_G.fat, color: MACRO_HUES.fat },
    { key: 'fiber', kcal: (fiber ?? 0) * KCAL_PER_G.fiber, color: MACRO_HUES.fiber },
  ].filter((s) => Number.isFinite(s.kcal) && s.kcal > 0);

  const total = segments.reduce((sum, s) => sum + s.kcal, 0);
  if (total <= 0 || segments.length === 0) return null;

  return (
    <View style={[barStyles.track, style]}>
      {segments.map((s, index) => (
        <View
          key={s.key}
          style={{
            flexGrow: s.kcal / total,
            flexBasis: 0,
            backgroundColor: s.color,
            // 段间发丝白缝，视觉分隔（除最后一段）。
            marginRight: index < segments.length - 1 ? 1 : 0,
          }}
        />
      ))}
    </View>
  );
}

interface IngredientChipsProps {
  items: string[];
  fallback?: string;
  style?: ViewStyle;
}

/** 食材 pill chips。空数组 + 有 fallback → 渲染单个占位 chip；空数组无 fallback → null。 */
export function IngredientChips({ items, fallback, style }: IngredientChipsProps) {
  const chips = items.length > 0 ? items : fallback ? [fallback] : [];
  if (chips.length === 0) return null;
  return (
    <View style={[chipStyles.wrap, style]}>
      {chips.map((item, index) => (
        <View key={`${item}-${index}`} style={chipStyles.chip}>
          <Text maxFontSizeMultiplier={1.2} style={chipStyles.text} numberOfLines={1}>
            {item}
          </Text>
        </View>
      ))}
    </View>
  );
}

const barStyles = StyleSheet.create({
  track: {
    flexDirection: 'row',
    height: 8,
    borderRadius: revaRadii.pill,
    overflow: 'hidden',
    backgroundColor: C.paper2,
  },
});

const chipStyles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  chip: {
    borderRadius: revaRadii.pill,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    paddingHorizontal: 10,
    paddingVertical: 5,
    maxWidth: '100%',
  },
  text: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: C.ink1,
    fontWeight: '600',
  } as TextStyle,
});
