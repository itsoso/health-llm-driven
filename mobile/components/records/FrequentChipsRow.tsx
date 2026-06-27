/**
 * FrequentChipsRow —— 通用「常用·一键记录」横向 chips (2026-06-01).
 *
 * 抽象自 diet 的 FrequentFoodsRow:给一排标题 + 横向滚动 chip,点一下触发 onPick.
 * 用于补剂(最常打卡)和饮水(最常用量+类型)的快捷记录。无数据时不渲染。
 */

import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaFonts,
} from '../../constants/revaTheme';

export interface FrequentChip {
  key: string;
  title: string;
  meta?: string;
}

interface Props {
  label: string;
  icon?: keyof typeof Ionicons.glyphMap;
  chips: FrequentChip[];
  onPick: (index: number) => void;
}

export default function FrequentChipsRow({ label, icon = 'repeat-outline', chips, onPick }: Props) {
  if (!chips || chips.length === 0) return null;

  return (
    <View style={styles.wrapper} testID="frequent-chips-row">
      <View style={styles.titleRow}>
        <Ionicons name={icon} size={14} color={C.ink2} />
        <Text maxFontSizeMultiplier={1.4} style={styles.title}>
          {label}
        </Text>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.scroll}>
        {chips.map((chip, i) => (
          <Pressable
            key={chip.key}
            onPress={() => onPick(i)}
            style={({ pressed }) => [
              styles.chip,
              { opacity: pressed ? 0.7 : 1 },
            ]}
            accessibilityRole="button"
            accessibilityLabel={`${chip.title}${chip.meta ? '，' + chip.meta : ''}`}
          >
            <Text maxFontSizeMultiplier={1.3} style={styles.chipTitle} numberOfLines={1}>
              {chip.title}
            </Text>
            {chip.meta ? (
              <Text maxFontSizeMultiplier={1.3} style={styles.chipMeta} numberOfLines={1}>
                {chip.meta}
              </Text>
            ) : null}
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

// Reva 设计语言:暖白 surface chip / ink 文字 / r-lg 18。chip 标题/量值走 mono 等宽 signature。
const styles = StyleSheet.create({
  wrapper: { marginBottom: revaSpacing.s2, gap: 8 },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 2 },
  title: { fontFamily: revaFonts.sans, fontSize: 12, fontWeight: '700', color: C.ink2 },
  scroll: { flexDirection: 'row', gap: revaSpacing.s2, paddingHorizontal: 2, paddingBottom: 2 },
  chip: {
    minWidth: 80,
    maxWidth: 180,
    borderRadius: revaRadii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.surface,
    paddingHorizontal: revaSpacing.s3,
    paddingVertical: 9,
    gap: 3,
  },
  chipTitle: { fontFamily: revaFonts.mono, fontSize: 13, fontWeight: '700', color: C.ink1 },
  chipMeta: { fontFamily: revaFonts.mono, fontSize: 10, fontWeight: '500', color: C.ink3 },
});
