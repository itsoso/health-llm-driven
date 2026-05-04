/**
 * AttributionChips — AI 回答底部的"用了你的什么数据"chip 行.
 *
 * P4 (2026-05-04): orchestrator system prompt 强制 LLM 在用了用户差异化数据时
 * 标注 marker. 这个组件把 marker 提取出来呈现给用户, 让"AI 在用我的基因/化验/
 * 用药/历史/趋势" 不再是后台事实, 而是每次回答都看得见的差异化护城河.
 *
 * 设计:
 * - 只在 markers ≥ 1 时渲染, 0 个不显示
 * - 每个 source 一个图标 + 颜色 (基因/化验/用药/历史/趋势)
 * - 4 个以上折叠 "+N"
 * - 不可点 (v1) — v2 加点击跳到对应数据源页 (基因报告 / 化验单)
 */
import React, { useMemo } from 'react';
import { StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import {
  extractAttributions,
  type AttributionItem,
  type AttributionSource,
} from '../../services/attributionExtract';
import { spacing, radii } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

interface Props {
  text: string;
}

const MAX_VISIBLE = 4;

function sourceMeta(source: AttributionSource, c: ColorPalette) {
  switch (source) {
    case 'genetic':
      return { icon: 'git-branch-outline' as const, color: c.purple, bg: c.tintPurple, label: '基因' };
    case 'lab':
      return { icon: 'flask-outline' as const, color: c.brand, bg: c.brandLight, label: '化验' };
    case 'medication':
      return { icon: 'medical-outline' as const, color: c.red, bg: c.tintRed, label: '在服' };
    case 'history':
      return { icon: 'time-outline' as const, color: '#0A84FF', bg: c.tintBlue, label: '历史' };
    case 'trend':
      return { icon: 'trending-up-outline' as const, color: c.amber, bg: c.tintAmber, label: '趋势' };
  }
}

export default function AttributionChips({ text }: Props) {
  const { c } = useTheme();
  const items = useMemo(() => extractAttributions(text), [text]);
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);

  if (items.length === 0) return null;

  const visible = items.slice(0, MAX_VISIBLE);
  const hiddenCount = items.length - visible.length;

  return (
    <View style={styles.wrap} accessibilityLabel="AI 用到了你的数据">
      <Text style={txt.prefix}>📌 用了你的：</Text>
      <View style={styles.chipsRow}>
        {visible.map((item, idx) => (
          <Chip key={`${item.source}-${item.label}-${idx}`} item={item} c={c} />
        ))}
        {hiddenCount > 0 ? (
          <View style={[styles.chip, { backgroundColor: c.bgPrimary }]}>
            <Text style={txt.chipMore}>+{hiddenCount}</Text>
          </View>
        ) : null}
      </View>
    </View>
  );
}

function Chip({ item, c }: { item: AttributionItem; c: ColorPalette }) {
  const meta = sourceMeta(item.source, c);
  return (
    <View
      style={[chipStyles.chip, { backgroundColor: meta.bg }]}
      accessibilityLabel={`${meta.label}: ${item.label}`}
    >
      <Ionicons name={meta.icon} size={11} color={meta.color} />
      <Text style={[chipStyles.label, { color: meta.color }]} numberOfLines={1}>
        {item.label}
      </Text>
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    wrap: {
      marginTop: spacing.sm,
      paddingTop: spacing.xs,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: c.fill,
      flexDirection: 'row',
      flexWrap: 'wrap',
      alignItems: 'center',
      gap: spacing.xs,
    },
    chipsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 4 },
    chip: {
      paddingHorizontal: spacing.sm,
      paddingVertical: 3,
      borderRadius: radii.full,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    prefix: { fontSize: 11, color: c.labelTertiary } as TextStyle,
    chipMore: { fontSize: 11, color: c.labelSecondary } as TextStyle,
  };
}

const chipStyles = StyleSheet.create({
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: radii.full,
    maxWidth: 140,
  },
  label: { fontSize: 11, fontWeight: '500' } as TextStyle,
});
