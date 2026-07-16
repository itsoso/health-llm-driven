/**
 * HealthPilot Design System Tokens
 */
// 复元 Reva 字型:typography 是 AppText 原语(+15 消费者)的底座,此前无 fontFamily →
// 永远系统 SF,越"用 AppText 统一"越回退。这里补齐设计字族(文本 Manrope、数字 mono),
// 一处修好全部消费者。字族名与 useRevaFonts 注册的一致('Manrope'/'IBMPlexMono')。
import { revaFonts } from './revaTheme';

// ── Colors ──────────────────────────────────────────────

// 复元 Reva 设计语言 — 亮色调色板 (paper/ink/green). token 名沿用旧体系, 值换 Reva,
// 这样所有走 useTheme().c 的屏自动继承 Reva 观感, 无需逐屏改引用.
export const colors = {
  // Brand — Reva green
  brand: '#1F8A5B',
  brandLight: '#E3F0E9',
  brandDark: '#176F49',

  // Semantic Health — 收敛到 Reva 三档语义 + 柔化的辅助色 (数据可视化用)
  green: '#1F8A5B',
  amber: '#C98A1E',
  red: '#D5503A',
  purple: '#7C5CBF',
  pink: '#C2487A',
  orange: '#C97A2E',
  blue: '#2A6FDB',
  teal: '#2F9E8F',

  // Neutrals — Reva ink 系
  labelPrimary: '#16201B',
  labelSecondary: '#5B6B63',
  labelTertiary: '#8A968F',
  labelQuaternary: '#B7C0BA',
  separator: 'rgba(22, 32, 27, 0.10)',

  // Backgrounds — Reva paper / surface
  bgPrimary: '#F7F6F2',
  bgCard: '#FFFFFF',
  bgElevated: '#FFFFFF',
  fill: '#EBEAE3',

  // Tinted Backgrounds — Reva 柔色底
  tintGreen: '#E3F0E9',
  tintAmber: '#F6ECD9',
  tintRed: '#F7E4E0',
  tintPurple: '#EDE7F6',
  tintPink: '#F7E4EC',
  tintOrange: '#F6E9DA',
  tintBlue: '#E4ECF8',
  tintTeal: '#E0EFEC',
} as const;

// Reva 暗色 — 深绿黑 (focus-bg #0F1C17) 家族, 绿色提亮到 green-bright 保证对比
export const darkColors = {
  brand: '#3AD29F',
  brandLight: '#15271E',
  brandDark: '#3AD29F',

  green: '#3AD29F',
  amber: '#E0A84A',
  red: '#E8897A',
  purple: '#A892D6',
  pink: '#D87FA4',
  orange: '#D89A5A',
  blue: '#6EA0E8',
  teal: '#5BB8AC',

  labelPrimary: '#EAF1ED',
  labelSecondary: '#9BA8A1',
  labelTertiary: '#6B776F',
  labelQuaternary: '#49544D',
  separator: 'rgba(234, 241, 237, 0.12)',

  bgPrimary: '#0E1712',
  bgCard: '#18221C',
  bgElevated: '#212E26',
  fill: '#2A352E',

  tintGreen: '#12281D',
  tintAmber: '#2A2110',
  tintRed: '#2A1512',
  tintPurple: '#1E1A2A',
  tintPink: '#2A1620',
  tintOrange: '#2A1F10',
  tintBlue: '#101D2E',
  tintTeal: '#0F2420',
} as const;

// ── Semantic Status Colors ──────────────────────────────
// 消除散落各组件的 70+ 重复 hex (#34C759 / #FF9F0A / #FF453A / tailwind slate/emerald 系...).
// 5 档语义, 每档 { fg, bg, solid }:
//   fg    — 文字/图标前景 (在 bg 上可读)
//   bg    — 浅色底 (chip / tint 卡片背景)
//   solid — 实心填充 (进度条 / 实心 badge / 图标块)
// light/dark 1:1 同键, 走 useTheme().s 自动切换. 业务档 (证据等级/命中率/风险) 映射到这 5 个 tone, 不再各造一套.
export type SemanticTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral';
type SemanticEntry = { fg: string; bg: string; solid: string };

// Reva 三档语义 normal(绿)/caution(琥珀)/risk(红) + info(蓝)/neutral(灰绿)
export const semanticColors: Record<SemanticTone, SemanticEntry> = {
  success: { fg: '#176F49', bg: '#E3F0E9', solid: '#1F8A5B' },
  warning: { fg: '#8A5A12', bg: '#F6ECD9', solid: '#C98A1E' },
  danger:  { fg: '#9E3A2C', bg: '#F7E4E0', solid: '#D5503A' },
  info:    { fg: '#1E4FA0', bg: '#E4ECF8', solid: '#2A6FDB' },
  neutral: { fg: '#5B6B63', bg: '#EFEEE8', solid: '#8A968F' },
} as const;

export const darkSemanticColors: Record<SemanticTone, SemanticEntry> = {
  success: { fg: '#3AD29F', bg: '#12281D', solid: '#1F8A5B' },
  warning: { fg: '#E0A84A', bg: '#2A2110', solid: '#C98A1E' },
  danger:  { fg: '#E8897A', bg: '#2A1512', solid: '#D5503A' },
  info:    { fg: '#6EA0E8', bg: '#101D2E', solid: '#2A6FDB' },
  neutral: { fg: '#9BA8A1', bg: '#18221C', solid: '#8A968F' },
} as const;

export type SemanticPalette = typeof semanticColors;

// ── Typography ──────────────────────────────────────────

export const typography = {
  heroScore: { fontFamily: revaFonts.mono, fontSize: 48, fontWeight: '700' as const, lineHeight: 56 },
  titleLarge: { fontFamily: revaFonts.sans, fontSize: 34, fontWeight: '700' as const, lineHeight: 41 },
  titleMedium: { fontFamily: revaFonts.sans, fontSize: 22, fontWeight: '700' as const, lineHeight: 28 },
  titleSmall: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '600' as const, lineHeight: 22 },
  bodyLarge: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '400' as const, lineHeight: 25 },
  bodyMedium: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '400' as const, lineHeight: 22 },
  bodySmall: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '400' as const, lineHeight: 18 },
  caption: { fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '500' as const, lineHeight: 13 },
  // 数字走 mono(tabular)—— app 的"临床仪表"招牌。IBMPlexMono 打包了 Regular/Medium;
  // 700 会假粗,形态仍是等宽 tabular(重字重精度留待后续切补打 Mono SemiBold)。
  metric: { fontFamily: revaFonts.mono, fontSize: 28, fontWeight: '700' as const, lineHeight: 34, fontVariant: ['tabular-nums'] as const },
  metricSmall: { fontFamily: revaFonts.mono, fontSize: 20, fontWeight: '700' as const, lineHeight: 24, fontVariant: ['tabular-nums'] as const },
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
  sleep: { main: colors.blue, tint: colors.tintBlue, icon: 'moon' },
  heartRate: { main: colors.pink, tint: colors.tintPink, icon: 'heart' },
  hrv: { main: colors.green, tint: colors.tintGreen, icon: 'pulse' },
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
