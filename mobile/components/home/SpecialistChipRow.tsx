/**
 * SpecialistChipRow — Home 入口
 *
 * Task 7: 从 /specialists/hit-rate 取近 30 天 significant specialists (≥3 样本),
 * 渲染为横滚 chip, 点击进 /specialist/[name] 详情页.
 *
 * Task 8 会加 tooltip 把 chip 升级成 TrustHintChip.
 */
import React, { useMemo } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { useSpecialistHitRate } from '../../hooks/useSpecialistScorecard';
import { specialistLabel } from '../../services/personalOutcome';
import { spacing, radii, typography } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

export default function SpecialistChipRow() {
  const router = useRouter();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const { data } = useSpecialistHitRate(30);

  const chips = (data?.by_specialist ?? []).filter((r) => r.is_significant);
  if (chips.length === 0) return null; // 样本不足不显示

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>近 30 天信任循环</Text>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scroll}
      >
        {chips.map((row) => (
          <Pressable
            key={row.specialist}
            onPress={() => router.push(`/specialist/${row.specialist}` as any)}
            style={({ pressed }) => [styles.chip, pressed && styles.chipPressed]}
            accessibilityRole="button"
            accessibilityLabel={`${specialistLabel(row.specialist)}, 命中 ${row.hits} 条共 ${row.total_graded} 条`}
          >
            <Text style={styles.chipText}>
              {specialistLabel(row.specialist)} · {row.hits}/{row.total_graded}
            </Text>
            <Text style={styles.chipArrow}>→</Text>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    wrap: { marginBottom: spacing.md },
    title: {
      fontSize: typography.bodySmall.fontSize,
      color: c.labelSecondary,
      marginBottom: spacing.xs,
      paddingHorizontal: spacing.md,
    },
    scroll: { paddingHorizontal: spacing.md, gap: 8 },
    chip: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingHorizontal: 12,
      paddingVertical: 6,
      borderRadius: 16,
      backgroundColor: c.bgCard,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
      gap: 4,
    },
    chipPressed: { opacity: 0.6 },
    chipText: {
      fontSize: typography.bodySmall.fontSize,
      color: c.labelPrimary,
      fontWeight: '500' as const,
    },
    chipArrow: {
      fontSize: typography.bodySmall.fontSize,
      color: c.brand,
    },
  });
}
