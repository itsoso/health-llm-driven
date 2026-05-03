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
      primary: `${totalGraded} 押 · ${totalHits} 中`,
      secondary: '近 30 天 · 点开看详情',
      navTarget,
      a11yLabel: `AI 信任循环, 30 天押 ${totalGraded} 张命中 ${totalHits} 张`,
    };
  }
  if (pending > 0) {
    return {
      state: 'pending',
      iconName: 'hourglass-outline',
      iconTint: c.amber,
      iconBg: c.tintAmber,
      primary: `${pending} 张押注中`,
      secondary: '等数据到期自动评分',
      navTarget: '/(tabs)/alerts',
      a11yLabel: `AI 押注中 ${pending} 张, 等待自动评分`,
    };
  }
  return {
    state: 'empty',
    iconName: 'sparkles-outline',
    iconTint: c.labelTertiary,
    iconBg: c.bgPrimary,
    primary: 'AI 准备就绪',
    secondary: '多用 App 几天, 开始为你押注',
    navTarget: '/(tabs)/alerts',
    a11yLabel: 'AI 押注未开始, 点开看行动卡片',
  };
}
