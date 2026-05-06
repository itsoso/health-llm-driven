/**
 * SpecialistChipRow — Home 入口 (信任循环可见化)
 *
 * 顶卡: TrustHeroCard — 永远显示且永远可点.
 *   有评分:   "[icon] AI 近 30 天准了 8/12  ›"              → best specialist 详情
 *   仅待评分: "[icon] AI 正在观察 4 条判断  ›   等自动验证" → /alerts (查看 pending)
 *   全空:     "[icon] AI 准备就绪  ›   多用 App 学习你"  → /alerts
 *
 * 第二行 (条件): per-specialist chip 横滚, 仅 is_significant (≥3 样本) 才出.
 *
 * 上一版 bug 修复: HeroWrapper=View 时函数式 style 不生效, 整个 chrome 没渲染.
 * 改成永远 Pressable + 静态 style.
 */
import React, { useMemo } from 'react';
import { StyleSheet, Text, ScrollView, Pressable, View, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useSpecialistHitRate } from '../../hooks/useSpecialistScorecard';
import { specialistLabel } from '../../services/personalOutcome';
import { spacing, radii, typography } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import { buildHero } from './specialistChipHero';
import { emitClientEvent } from '../../services/clientEvents';

export default function SpecialistChipRow() {
  const router = useRouter();
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const { data } = useSpecialistHitRate(30);

  const allRows = data?.by_specialist ?? [];
  const significant = allRows.filter((r) => r.is_significant);
  const totalGraded = allRows.reduce((s, r) => s + r.total_graded, 0);
  const totalHits = allRows.reduce((s, r) => s + r.hits, 0);
  const pending = data?.pending_grading ?? 0;
  const best = data?.best_specialist ?? null;
  const firstSig = significant[0]?.specialist ?? null;

  const hero = useMemo(
    () => buildHero(c, totalGraded, totalHits, pending, best, firstSig),
    [c, totalGraded, totalHits, pending, best, firstSig],
  );

  return (
    <View style={styles.wrap}>
      <Pressable
        style={({ pressed }) => [styles.hero, pressed && styles.heroPressed]}
        onPress={() => {
          // Phase 0.4: 埋点 — TrustHero chip 点击
          emitClientEvent('home_chip_clicked', {
            chip: 'trust_hero',
            target: hero.navTarget,
          });
          router.push(hero.navTarget as any);
        }}
        accessibilityRole="button"
        accessibilityLabel={hero.a11yLabel}
      >
        <View style={[styles.heroIconWrap, { backgroundColor: hero.iconBg }]}>
          <Ionicons name={hero.iconName} size={16} color={hero.iconTint} />
        </View>
        <View style={styles.heroTextWrap}>
          <Text style={styles.heroPrimary} numberOfLines={1}>{hero.primary}</Text>
          <Text style={styles.heroSecondary} numberOfLines={1}>{hero.secondary}</Text>
        </View>
        <Ionicons name="chevron-forward" size={16} color={c.labelTertiary} />
      </Pressable>

      {significant.length > 0 && (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.scroll}
        >
          {significant.map((row) => (
            <Pressable
              key={row.specialist}
              onPress={() => {
                // Phase 0.4: 埋点 — specialist chip 点击
                emitClientEvent('home_chip_clicked', {
                  chip: 'specialist',
                  target: row.specialist,
                });
                router.push(`/specialist/${row.specialist}` as any);
              }}
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

function createStyles(c: ColorPalette, isDark: boolean) {
  return StyleSheet.create({
    wrap: { marginBottom: spacing.md, gap: spacing.sm },
    hero: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 12,
      marginHorizontal: spacing.lg,
      paddingHorizontal: 14,
      paddingVertical: 12,
      borderRadius: radii.lg,
      backgroundColor: c.bgCard,
      // dark 用 hairline 边框替代 shadow (与 DashboardCard / HealthCard 一致)
      ...(isDark
        ? { borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator }
        : {
            shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
            shadowOpacity: 0.06, shadowRadius: 3, elevation: 1,
          }),
    },
    heroPressed: { opacity: 0.7 },
    heroIconWrap: {
      width: 32, height: 32, borderRadius: 10,
      alignItems: 'center', justifyContent: 'center',
    },
    heroTextWrap: { flex: 1, gap: 2 },
    heroPrimary: {
      fontSize: 15, fontWeight: '700' as const, color: c.labelPrimary,
    } as TextStyle,
    heroSecondary: {
      fontSize: 11, color: c.labelTertiary,
    } as TextStyle,
    scroll: { paddingHorizontal: spacing.lg, gap: 8 },
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
    } as TextStyle,
    chipArrow: {
      fontSize: typography.bodySmall.fontSize,
      color: c.brand,
    } as TextStyle,
  });
}

// helpers exported for test (从 ./specialistChipHero re-export 供老 import 路径)
export { buildHero } from './specialistChipHero';
