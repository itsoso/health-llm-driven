import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { radii, spacing } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';
import type { HealthGuardrailSummary } from '../../services/healthGuardrailSummary';

interface Props {
  summary?: HealthGuardrailSummary | null;
  isError?: boolean;
  onPress: (route: string) => void;
}

export default function HealthGuardrailCard({ summary, isError = false, onPress }: Props) {
  const { c, isDark } = useTheme();

  if (!summary && !isError) return null;

  const hasAttention = (summary?.attentionCount ?? 0) > 0 || isError;
  const accent = hasAttention ? c.amber : c.teal;
  const tint = hasAttention ? c.tintAmber : c.tintTeal;
  const title = isError ? '健康守门加载失败' : summary?.title ?? '健康守门';
  const subtitle = isError ? '稍后刷新，避免基于不完整状态做判断。' : summary?.subtitle ?? '';
  const route = summary?.primaryRoute ?? '/data-integrity';

  return (
    <Pressable
      testID="home-health-guardrail-card"
      onPress={() => onPress(route)}
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
          <Ionicons name="shield-checkmark-outline" size={18} color={accent} />
        </View>
        <View style={styles.titleBlock}>
          <Text style={[styles.eyebrow, { color: accent }]} maxFontSizeMultiplier={1.12}>
            健康守门
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

      {summary ? (
        <View style={styles.itemGrid}>
          {summary.items.map((item) => (
            <View
              key={item.key}
              style={[
                styles.item,
                {
                  backgroundColor: item.attention ? tint : c.bgPrimary,
                  borderColor: item.attention ? accent : c.separator,
                },
              ]}
            >
              <Text style={[styles.itemLabel, { color: c.labelSecondary }]} maxFontSizeMultiplier={1.08}>
                {item.label}
              </Text>
              <Text
                style={[styles.itemValue, { color: item.attention ? accent : c.labelPrimary }]}
                maxFontSizeMultiplier={1.08}
                numberOfLines={1}
              >
                {item.value}
              </Text>
            </View>
          ))}
        </View>
      ) : null}
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
  itemGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  item: {
    borderRadius: radii.md,
    borderWidth: StyleSheet.hairlineWidth,
    flexBasis: '48%',
    flexGrow: 1,
    minWidth: 132,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  itemLabel: {
    fontSize: 11,
    fontWeight: '700',
  },
  itemValue: {
    fontSize: 13,
    fontWeight: '800',
    marginTop: 2,
  },
});
