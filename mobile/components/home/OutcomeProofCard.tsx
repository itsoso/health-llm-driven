import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { radii, spacing } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';
import type { OutcomeProofSummary } from '../../services/outcomeProofSummary';

interface Props {
  summary: OutcomeProofSummary;
  isError?: boolean;
  onPress: () => void;
}

export default function OutcomeProofCard({ summary, isError = false, onPress }: Props) {
  const { c, isDark } = useTheme();
  const title = isError ? '个人证据加载失败' : summary.title;
  const subtitle = isError ? '稍后刷新，避免用过期结果判断干预。' : summary.subtitle;
  const hasWin = !isError && summary.items.some((item) => item.key === 'improved' && item.value !== '0');
  const accent = hasWin ? c.green : c.brand;
  const tint = hasWin ? c.tintGreen : c.brandLight;

  return (
    <Pressable
      testID="home-outcome-proof-card"
      onPress={onPress}
      style={({ pressed }) => [
        styles.card,
        {
          backgroundColor: c.bgCard,
          borderColor: c.separator,
          opacity: pressed ? 0.78 : 1,
        },
        isDark
          ? null
          : {
              shadowColor: '#000',
              shadowOffset: { width: 0, height: 2 },
              shadowOpacity: 0.05,
              shadowRadius: 6,
              elevation: 2,
            },
      ]}
      accessibilityRole="button"
      accessibilityLabel={`${title}: ${subtitle}`}
    >
      <View style={styles.headerRow}>
        <View style={[styles.iconWrap, { backgroundColor: tint }]}>
          <Ionicons name="analytics-outline" size={18} color={accent} />
        </View>
        <View style={styles.titleBlock}>
          <Text style={[styles.eyebrow, { color: accent }]} maxFontSizeMultiplier={1.12}>
            个人证据
          </Text>
          <Text style={[styles.title, { color: c.labelPrimary }]} maxFontSizeMultiplier={1.12} numberOfLines={2}>
            {title}
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={15} color={c.labelTertiary} />
      </View>

      <Text style={[styles.subtitle, { color: c.labelSecondary }]} maxFontSizeMultiplier={1.12} numberOfLines={2}>
        {subtitle}
      </Text>

      {summary.highlight ? (
        <View style={[styles.highlight, { backgroundColor: tint }]}>
          <Text style={[styles.highlightTitle, { color: c.labelPrimary }]} maxFontSizeMultiplier={1.08} numberOfLines={1}>
            {summary.highlight.title}
          </Text>
          <Text style={[styles.highlightDetail, { color: accent }]} maxFontSizeMultiplier={1.08} numberOfLines={1}>
            {summary.highlight.detail}
          </Text>
        </View>
      ) : null}

      <View style={styles.itemGrid}>
        {summary.items.map((item) => (
          <View
            key={item.key}
            style={[
              styles.item,
              {
                backgroundColor: item.accent ? tint : c.bgPrimary,
                borderColor: item.accent ? accent : c.separator,
              },
            ]}
          >
            <Text style={[styles.itemValue, { color: item.accent ? accent : c.labelPrimary }]} maxFontSizeMultiplier={1.08}>
              {item.value}
            </Text>
            <Text style={[styles.itemLabel, { color: c.labelSecondary }]} maxFontSizeMultiplier={1.08} numberOfLines={1}>
              {item.label}
            </Text>
          </View>
        ))}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radii.xl,
    borderWidth: StyleSheet.hairlineWidth,
    gap: spacing.sm,
    marginBottom: spacing.md,
    padding: spacing.md,
  },
  headerRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: spacing.sm,
  },
  iconWrap: {
    alignItems: 'center',
    borderRadius: radii.lg,
    height: 34,
    justifyContent: 'center',
    width: 34,
  },
  titleBlock: {
    flex: 1,
    minWidth: 0,
  },
  eyebrow: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0,
  },
  title: {
    fontSize: 16,
    fontWeight: '800',
    lineHeight: 21,
  },
  subtitle: {
    fontSize: 13,
    lineHeight: 18,
  },
  highlight: {
    borderRadius: radii.md,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  highlightTitle: {
    fontSize: 12,
    fontWeight: '800',
  },
  highlightDetail: {
    fontSize: 12,
    fontWeight: '800',
    marginTop: 2,
  },
  itemGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  item: {
    alignItems: 'center',
    borderRadius: radii.md,
    borderWidth: StyleSheet.hairlineWidth,
    flexBasis: '22%',
    flexGrow: 1,
    minWidth: 68,
    paddingVertical: spacing.xs,
  },
  itemValue: {
    fontSize: 15,
    fontWeight: '900',
  },
  itemLabel: {
    fontSize: 10,
    fontWeight: '700',
    marginTop: 2,
  },
});
