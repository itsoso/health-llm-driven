/**
 * HealthPilot Design System Tokens
 */

// ── Colors ──────────────────────────────────────────────

export const colors = {
  // Brand
  brand: '#0A8F8F',
  brandLight: '#E6F5F5',
  brandDark: '#076B6B',

  // Semantic Health
  green: '#30D158',
  amber: '#FF9F0A',
  red: '#FF453A',
  purple: '#BF5AF2',
  pink: '#FF375F',
  orange: '#FF6723',
  blue: '#64D2FF',
  teal: '#5AC8FA',

  // Neutrals
  labelPrimary: '#1C1C1E',
  labelSecondary: '#636366',
  labelTertiary: '#AEAEB2',
  labelQuaternary: '#C7C7CC',
  separator: 'rgba(60, 60, 67, 0.12)',

  // Backgrounds
  bgPrimary: '#F2F2F7',
  bgCard: '#FFFFFF',
  bgElevated: '#FFFFFF',
  fill: '#E5E5EA',

  // Tinted Backgrounds
  tintGreen: '#E8FAF0',
  tintAmber: '#FFF5E6',
  tintRed: '#FFE8E6',
  tintPurple: '#F5E6FF',
  tintPink: '#FFE6EE',
  tintOrange: '#FFF0E6',
  tintBlue: '#E6F5FF',
  tintTeal: '#E6F8FF',
} as const;

export const darkColors = {
  brand: '#0EB5B5',
  brandLight: '#1A3333',
  brandDark: '#0EB5B5',

  green: '#30D158',
  amber: '#FF9F0A',
  red: '#FF453A',
  purple: '#BF5AF2',
  pink: '#FF375F',
  orange: '#FF6723',
  blue: '#64D2FF',
  teal: '#5AC8FA',

  labelPrimary: '#F5F5F7',
  labelSecondary: '#A1A1A6',
  labelTertiary: '#636366',
  labelQuaternary: '#48484A',
  separator: 'rgba(255, 255, 255, 0.12)',

  bgPrimary: '#000000',
  bgCard: '#1C1C1E',
  bgElevated: '#2C2C2E',
  fill: '#3A3A3C',

  tintGreen: '#0D2B1A',
  tintAmber: '#2B1F0D',
  tintRed: '#2B0D0D',
  tintPurple: '#1F0D2B',
  tintPink: '#2B0D1A',
  tintOrange: '#2B1A0D',
  tintBlue: '#0D1A2B',
  tintTeal: '#0D1F2B',
} as const;

// ── Typography ──────────────────────────────────────────

export const typography = {
  heroScore: { fontSize: 48, fontWeight: '700' as const, lineHeight: 56 },
  titleLarge: { fontSize: 34, fontWeight: '700' as const, lineHeight: 41 },
  titleMedium: { fontSize: 22, fontWeight: '700' as const, lineHeight: 28 },
  titleSmall: { fontSize: 17, fontWeight: '600' as const, lineHeight: 22 },
  bodyLarge: { fontSize: 17, fontWeight: '400' as const, lineHeight: 25 },
  bodyMedium: { fontSize: 15, fontWeight: '400' as const, lineHeight: 22 },
  bodySmall: { fontSize: 13, fontWeight: '400' as const, lineHeight: 18 },
  caption: { fontSize: 11, fontWeight: '500' as const, lineHeight: 13 },
  metric: { fontSize: 28, fontWeight: '700' as const, lineHeight: 34, fontVariant: ['tabular-nums'] as const },
  metricSmall: { fontSize: 20, fontWeight: '700' as const, lineHeight: 24, fontVariant: ['tabular-nums'] as const },
} as const;

// ── Dynamic Type 上限 ───────────────────────────────────
// 统一 maxFontSizeMultiplier (此前散落 1.18 / 1.3 / 1.4 / 无, 见 docs/mobile-ui-audit.md).
// default: 正文/标签放宽到 1.3 (照顾大字体用户);
// metric: 数字密集卡片 (步数/卡路里等) 收 1.18, 防止 tabular 数字撑破布局;
// compact: 极紧凑的 chip/badge 收 1.15.
export const FONT_SIZE_CAPS = {
  default: 1.3,
  metric: 1.18,
  compact: 1.15,
} as const;

// ── Spacing ─────────────────────────────────────────────

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
} as const;

// ── Radii ───────────────────────────────────────────────

export const radii = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  full: 999,
} as const;

// ── Shadows ─────────────────────────────────────────────

export const shadows = {
  subtle: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 3,
    elevation: 1,
  },
  medium: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 2,
  },
  heavy: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.12,
    shadowRadius: 16,
    elevation: 4,
  },
} as const;

// ── Health Metric Colors ────────────────────────────────

export const metricColors = {
  sleep: { main: colors.purple, tint: colors.tintPurple, icon: 'moon' },
  heartRate: { main: colors.pink, tint: colors.tintPink, icon: 'heart' },
  hrv: { main: colors.teal, tint: colors.tintTeal, icon: 'pulse' },
  battery: { main: colors.green, tint: colors.tintGreen, icon: 'battery-charging' },
  steps: { main: colors.orange, tint: colors.tintOrange, icon: 'footsteps' },
  active: { main: colors.pink, tint: colors.tintPink, icon: 'flame' },
  calories: { main: colors.red, tint: colors.tintRed, icon: 'flash' },
  water: { main: colors.blue, tint: colors.tintBlue, icon: 'water' },
  supplements: { main: '#AF52DE', tint: '#F5E6FF', icon: 'medical' },
  stress: { main: colors.amber, tint: colors.tintAmber, icon: 'cloudy' },
} as const;

// ── Score Color Helper ──────────────────────────────────

export function scoreColor(score: number): string {
  if (score >= 80) return colors.green;
  if (score >= 60) return colors.amber;
  return colors.red;
}

export function scoreGrade(score: number): string {
  if (score >= 90) return '优秀';
  if (score >= 80) return '良好';
  if (score >= 60) return '一般';
  if (score >= 40) return '较差';
  return '需关注';
}
