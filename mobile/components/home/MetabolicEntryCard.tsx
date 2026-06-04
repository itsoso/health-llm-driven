/**
 * MetabolicEntryCard —— 首页「代谢健康」显眼入口 (Personal Health OS 代谢闭环).
 *
 * 之前代谢画像/90天干预只埋在「我」设置 hub 里, discoverability 差。这里把它提到
 * 首页:有进行中的干预周期就显示「第 N / 90 天」, 否则引导「看风险 · 开始干预」。
 * 点击进 /metabolic-profile(画像front door, 内含进入 90 天干预的 CTA)。
 *
 * 三态都诚实: 加载中 / 进行中(显示天数) / 未开始。失败静默退化为"未开始"引导。
 */
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { spacing, radii } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';
import { useActiveCycle } from '../../hooks/useHealthOs';

function daysBetween(a?: string | null, b?: string | null): number | null {
  if (!a || !b) return null;
  const da = new Date(a).getTime();
  const db = new Date(b).getTime();
  if (Number.isNaN(da) || Number.isNaN(db)) return null;
  return Math.round((db - da) / 86400000);
}

export default function MetabolicEntryCard() {
  const { c } = useTheme();
  const router = useRouter();
  const { data: cycle, isLoading } = useActiveCycle();

  let icon: keyof typeof Ionicons.glyphMap = 'pulse-outline';
  let iconColor = c.brand;
  let tint = c.brandLight;
  let title = '代谢健康';
  let sub = '看代谢风险 · 开始 90 天干预';
  let a11y = '代谢健康，查看代谢风险并开始 90 天干预';

  if (isLoading) {
    sub = '加载中…';
  } else if (cycle && cycle.status === 'active') {
    const total = daysBetween(cycle.start_date, cycle.planned_end_date) ?? 90;
    const elapsed = daysBetween(cycle.start_date, new Date().toISOString()) ?? 0;
    const day = Math.max(1, Math.min(total, elapsed + 1));
    const met = cycle.outcomes.filter((o) => o.status === 'met').length;
    icon = 'fitness';
    iconColor = c.green;
    tint = c.tintGreen;
    title = '代谢干预进行中';
    sub = `第 ${day} / ${total} 天` + (met > 0 ? ` · ${met} 项已达标` : '');
    a11y = `代谢干预进行中，第 ${day} 天，共 ${total} 天`;
  }

  return (
    <Pressable
      testID="home-metabolic-entry-card"
      onPress={() => router.push('/metabolic-profile' as any)}
      style={({ pressed }) => [
        styles.row,
        { backgroundColor: c.bgCard, borderColor: c.separator, opacity: pressed ? 0.78 : 1 },
      ]}
      accessibilityRole="button"
      accessibilityLabel={a11y}
    >
      <View style={[styles.iconWrap, { backgroundColor: tint }]}>
        <Ionicons name={icon} size={16} color={iconColor} />
      </View>
      <View style={styles.textWrap}>
        <Text maxFontSizeMultiplier={1.4} style={[styles.title, { color: c.labelPrimary }]} numberOfLines={1}>
          {title}
        </Text>
        <Text maxFontSizeMultiplier={1.4} style={[styles.sub, { color: c.labelTertiary }]} numberOfLines={1}>
          {sub}
        </Text>
      </View>
      <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderRadius: radii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    marginBottom: spacing.md,
  },
  iconWrap: { width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center' },
  textWrap: { flex: 1, gap: 2, minWidth: 0 },
  title: { fontSize: 13, fontWeight: '800' },
  sub: { fontSize: 11, fontWeight: '500' },
});
