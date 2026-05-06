/**
 * SpecialistChipRow.buildHero — 纯函数, 抽到这里避免 jest 单测被 axios fetch 污染.
 */
import { Ionicons } from '@expo/vector-icons';
import type { ColorPalette } from '../../hooks/useTheme';

export type HeroState = 'graded' | 'pending' | 'empty';

export interface HeroSummary {
  state: HeroState;
  iconName: keyof typeof Ionicons.glyphMap;
  iconTint: string;
  iconBg: string;
  primary: string;
  secondary: string;
  navTarget: string;
  a11yLabel: string;
}

export function buildHero(
  c: ColorPalette,
  totalGraded: number,
  totalHits: number,
  pending: number,
  best: string | null,
  firstSignificant: string | null,
): HeroSummary {
  const target = best ?? firstSignificant ?? null;
  const navTarget = target ? `/specialist/${target}` : '/(tabs)/alerts';

  if (totalGraded > 0) {
    return {
      state: 'graded',
      iconName: 'trending-up',
      iconTint: c.brand,
      iconBg: c.brandLight,
      primary: `AI 近 30 天准了 ${totalHits}/${totalGraded}`,
      secondary: '点开看它最擅长哪些判断',
      navTarget,
      a11yLabel: `AI 信任循环, 30 天做出 ${totalGraded} 条判断, 事后数据证明准 ${totalHits} 条`,
    };
  }
  if (pending > 0) {
    return {
      state: 'pending',
      iconName: 'hourglass-outline',
      iconTint: c.amber,
      iconBg: c.tintAmber,
      primary: `AI 正在观察 ${pending} 条判断`,
      secondary: '数据够了会自动告诉你它准不准',
      navTarget: '/(tabs)/alerts',
      a11yLabel: `AI 有 ${pending} 条判断等数据验证`,
    };
  }
  return {
    state: 'empty',
    iconName: 'sparkles-outline',
    iconTint: c.labelTertiary,
    iconBg: c.bgPrimary,
    primary: 'AI 还在学你的节奏',
    secondary: '多用几天, 判断会越来越准',
    navTarget: '/(tabs)/alerts',
    a11yLabel: 'AI 尚未做出判断, 点开看行动卡片',
  };
}
