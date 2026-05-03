/**
 * SpecialistChipRow — Home 入口 (信任循环可见化)
 *
 * 顶行: TrustHeroChip — 永远显示, 即使无数据 (引导用户认识到 AI 在押注)
 *   - 有评分: "AI 押 12 中 8 (30天)"   → 进 best specialist 详情
 *   - 仅待评分: "AI 押注中 12 张 ⏳"  → 进 best 或 fallback
 *   - 全空: "AI 还没开始押注 — 多用 App, 让它学会你"  → 不可点
 *
 * 第二行 (条件): per-specialist chip 横滚, 仅 is_significant (≥3 样本) 才出.
 *
 * Task 7 → Task 11 (2026-05-04): 把 hero chip 加上, 配合 outcome_grader 的
 * APNs hit push, 形成完整信任反馈环.
 */
import React, { useMemo } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
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

  const allRows = data?.by_specialist ?? [];
  const significant = allRows.filter((r) => r.is_significant);
  const totalGraded = allRows.reduce((s, r) => s + r.total_graded, 0);
  const totalHits = allRows.reduce((s, r) => s + r.hits, 0);
  const pending = data?.pending_grading ?? 0;
  const best = data?.best_specialist;

  // hero target: 优先去 best specialist, 其次首个 significant, 都没就不可点
  const heroTarget: string | null = best ?? significant[0]?.specialist ?? null;
  const heroPressable = Boolean(heroTarget);

  const heroText = (() => {
    if (totalGraded > 0) {
      return `AI 押 ${totalGraded} 中 ${totalHits} · 近 30 天`;
    }
    if (pending > 0) {
      return `AI 押注中 ${pending} 张 ⏳`;
    }
    return 'AI 还没开始押注 — 多用 App 让它学会你';
  })();

  const HeroWrapper: any = heroPressable ? Pressable : View;
  const heroProps = heroPressable
    ? {
        onPress: () => router.push(`/specialist/${heroTarget}` as any),
        accessibilityRole: 'button' as const,
        accessibilityLabel: `查看 ${heroTarget} 详情, 30 天 ${totalHits}/${totalGraded} 命中`,
      }
    : {};

  return (
    <View style={styles.wrap}>
      <HeroWrapper
        style={({ pressed }: { pressed?: boolean }) => [
          styles.hero,
          pressed && heroPressable && styles.heroPressed,
        ]}
        {...heroProps}
      >
        <Ionicons
          name={totalGraded > 0 ? 'trending-up' : 'hourglass-outline'}
          size={14}
          color={totalGraded > 0 ? c.brand : c.labelTertiary}
        />
        <Text style={styles.heroText} numberOfLines={1}>
          {heroText}
        </Text>
        {heroPressable && (
          <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} />
        )}
      </HeroWrapper>

      {significant.length > 0 && (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.scroll}
        >
          {significant.map((row) => (
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
      )}
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    wrap: { marginBottom: spacing.md, gap: spacing.xs },
    hero: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      marginHorizontal: spacing.md,
      paddingHorizontal: 12,
      paddingVertical: 8,
      borderRadius: radii.md,
      backgroundColor: c.brandLight,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
    },
    heroPressed: { opacity: 0.6 },
    heroText: {
      flex: 1,
      fontSize: typography.bodySmall.fontSize,
      color: c.labelPrimary,
      fontWeight: '600' as const,
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
