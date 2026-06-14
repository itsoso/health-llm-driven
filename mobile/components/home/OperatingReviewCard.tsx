import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { spacing, radii } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';
import type { OperatingReviewSummary } from '../../services/operatingReviewSummary';

interface Props {
  summary?: OperatingReviewSummary | null;
  isError?: boolean;
  onPress: () => void;
}

export default function OperatingReviewCard({ summary, isError = false, onPress }: Props) {
  const { c } = useTheme();
  const title = isError ? '执行复盘加载失败' : summary?.title ?? '执行复盘检查中';
  const subtitle = isError ? '稍后再看最近行动和指标变化。' : summary?.subtitle ?? '正在读取最近行动完成情况。';
  const highlight = summary?.highlight;
  const highlightColor = highlight?.positive ? c.green : c.orange;

  return (
    <TouchableOpacity
      testID="home-operating-review-card"
      accessibilityRole="button"
      accessibilityLabel={`${title}: ${subtitle}`}
      onPress={onPress}
      activeOpacity={0.86}
      style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}
    >
      <View style={styles.header}>
        <View style={[styles.iconWrap, { backgroundColor: c.tintBlue }]}>
          <Ionicons name="checkbox-outline" size={19} color={c.blue} />
        </View>
        <View style={styles.titleBlock}>
          <Text style={[styles.eyebrow, { color: c.blue }]}>执行复盘</Text>
          <Text style={[styles.title, { color: c.labelPrimary }]} numberOfLines={2}>
            {title}
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={18} color={c.labelTertiary} />
      </View>

      <Text style={[styles.subtitle, { color: c.labelSecondary }]} numberOfLines={2}>
        {subtitle}
      </Text>

      {highlight ? (
        <View style={[styles.highlight, { backgroundColor: highlight.positive ? c.tintGreen : c.tintOrange }]}>
          <Text style={[styles.highlightLabel, { color: c.labelSecondary }]}>{highlight.label}</Text>
          <Text style={[styles.highlightValue, { color: highlightColor }]} numberOfLines={1}>
            {highlight.value}
          </Text>
          <Text style={[styles.highlightDetail, { color: c.labelTertiary }]} numberOfLines={1}>
            {highlight.detail}
          </Text>
        </View>
      ) : null}

      <View style={styles.itemRow}>
        {(summary?.items ?? fallbackItems).map((item) => (
          <View key={item.key} style={[styles.item, { backgroundColor: item.accent ? c.brandLight : c.fill }]}>
            <Text style={[styles.itemValue, { color: item.accent ? c.brand : c.labelPrimary }]} numberOfLines={1}>
              {item.value}
            </Text>
            <Text style={[styles.itemLabel, { color: c.labelTertiary }]} numberOfLines={1}>
              {item.label}
            </Text>
          </View>
        ))}
      </View>
    </TouchableOpacity>
  );
}

const fallbackItems: OperatingReviewSummary['items'] = [
  { key: 'completion_rate', label: '完成率', value: '—', accent: false },
  { key: 'completed', label: '已完成', value: '—', accent: false },
  { key: 'total', label: '总行动', value: '—', accent: false },
  { key: 'learnable', label: '可学习', value: '—', accent: false },
];

const styles = StyleSheet.create({
  card: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  header: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  iconWrap: {
    width: 36,
    height: 36,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  titleBlock: { flex: 1, minWidth: 0 },
  eyebrow: { fontSize: 11, fontWeight: '800', marginBottom: 2 },
  title: { fontSize: 16, fontWeight: '800', lineHeight: 21 },
  subtitle: { fontSize: 13, lineHeight: 18 },
  highlight: {
    borderRadius: radii.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
    gap: 2,
  },
  highlightLabel: { fontSize: 11, fontWeight: '700' },
  highlightValue: { fontSize: 15, fontWeight: '900' },
  highlightDetail: { fontSize: 11 },
  itemRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  item: {
    flex: 1,
    minWidth: '22%',
    borderRadius: radii.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: 6,
    alignItems: 'center',
    gap: 2,
  },
  itemValue: { fontSize: 14, fontWeight: '900' },
  itemLabel: { fontSize: 10, fontWeight: '700' },
});
