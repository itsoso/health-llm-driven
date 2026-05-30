/**
 * FrequentFoodsRow —— 餐食「常吃」一键复用 (2026-05-30, P1-b).
 *
 * 横向 chips, 每个是用户最近常吃的食物 (后端 /diet/records/me/frequent 按频次聚合).
 * 点一下直接 createDietRecord(用历史营养素中位数) → 1-tap 记录, 砍掉最高频的重复录入摩擦.
 * 无数据时不渲染 (不占位、不打扰).
 */

import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { spacing, radii } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';
import type { FrequentFood } from '../../services/diet';

const MEAL_LABEL: Record<string, string> = {
  breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐',
};

interface Props {
  foods: FrequentFood[];
  onPick: (food: FrequentFood) => void;
}

export default function FrequentFoodsRow({ foods, onPick }: Props) {
  const { c } = useTheme();

  if (!foods || foods.length === 0) return null;

  return (
    <View style={styles.wrapper} testID="frequent-foods-row">
      <View style={styles.titleRow}>
        <Ionicons name="repeat-outline" size={14} color={c.labelSecondary} />
        <Text
          maxFontSizeMultiplier={1.4}
          style={[styles.title, { color: c.labelSecondary }]}
        >
          常吃 · 点一下直接记录
        </Text>
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scroll}
      >
        {foods.map((f, i) => {
          const cal = f.calories != null ? `${Math.round(f.calories)}kcal` : '按历史估算';
          return (
            <Pressable
              key={`${f.food_items}-${i}`}
              onPress={() => onPick(f)}
              style={({ pressed }) => [
                styles.chip,
                { backgroundColor: c.bgCard, borderColor: c.separator, opacity: pressed ? 0.7 : 1 },
              ]}
              accessibilityRole="button"
              accessibilityLabel={`记录${MEAL_LABEL[f.meal_type] || ''}：${f.food_items}，${cal}`}
            >
              <Text
                maxFontSizeMultiplier={1.3}
                style={[styles.chipFood, { color: c.labelPrimary }]}
                numberOfLines={1}
              >
                {f.food_items}
              </Text>
              <Text
                maxFontSizeMultiplier={1.3}
                style={[styles.chipMeta, { color: c.labelTertiary }]}
                numberOfLines={1}
              >
                {MEAL_LABEL[f.meal_type] || ''} · {cal}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { marginBottom: spacing.md, gap: 8 },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 2 },
  title: { fontSize: 12, fontWeight: '700' },
  scroll: { flexDirection: 'row', gap: spacing.sm, paddingHorizontal: 2, paddingBottom: 2 },
  chip: {
    minWidth: 96,
    maxWidth: 180,
    borderRadius: radii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: spacing.md,
    paddingVertical: 9,
    gap: 3,
  },
  chipFood: { fontSize: 13, fontWeight: '700' },
  chipMeta: { fontSize: 10, fontWeight: '500' },
});
