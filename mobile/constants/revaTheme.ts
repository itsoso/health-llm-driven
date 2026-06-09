/**
 * 复元 Reva — Design tokens (React Native port)
 *
 * Faithful port of `docs/design/reva/colors_and_type.css` (Claude Design handoff).
 * Source of truth = that CSS; keep this file in sync when the design system updates.
 *
 * Feeling: "clinical calm with a pulse of vitality" — warm paper, one hero green,
 * numbers in mono, three-step clinical semantics.
 *
 * ⚠️ Fonts: the design specifies Manrope (Latin) + Noto Sans SC (CJK) +
 * IBM Plex Mono (data/numbers). These must be bundled via expo-font and the
 * family names registered before the type tokens render correctly. Until then RN
 * falls back to system fonts. (Same substitution the design flagged for Google Fonts.)
 */

// ── Color ────────────────────────────────────────────────────────────────
export const revaColors = {
  // Core palette (warm clinical)
  paper: '#F7F6F2', // app background — warm off-white, not stark
  paper2: '#F1EFE8', // recessed / grouped background
  surface: '#FFFFFF', // cards, sheets
  surface2: '#FBFAF7', // subtle raised tint

  ink1: '#16201B', // primary text — deep forest near-black
  ink2: '#5C6660', // secondary text
  ink3: '#8A938D', // muted / captions / placeholders
  ink4: '#B7BDB7', // disabled / faint

  line: '#E7E5DE', // hairline borders
  lineStrong: '#D7D5CC', // stronger dividers, input borders

  // Primary: Vital Green (health, recovery)
  green50: '#E8F2EC',
  green100: '#CDE6D8',
  green300: '#6FBE94',
  green500: '#1F8A5B', // PRIMARY
  green600: '#176F49', // press / hover-dark
  green700: '#115738',
  greenOn: '#FFFFFF', // text on primary
  greenBright: '#3AD29F', // accent on dark surfaces

  // Secondary: Clinical Blue (info, links, trends)
  blue50: '#E7EEFB',
  blue100: '#CBDCF6',
  blue500: '#2A6FDB',
  blue600: '#1F58B6',

  // Focus surface (deep green-black) — hero data moments
  focusBg: '#0F1C17',
  focusBg2: '#16271F',
  focusLine: '#23463A',
  focusInk1: '#EAF3EE',
  focusInk2: '#9DB3A8',
} as const;

/** Three-step clinical semantics: normal / caution / risk (+ info). */
export const revaSemantic = {
  normal: { fg: '#1F8A5B', bg: '#E8F2EC', line: '#CDE6D8' }, // in-range / improving
  caution: { fg: '#C98A1E', bg: '#FBF1DD', line: '#F0DCB0' }, // borderline / watch (注意)
  risk: { fg: '#D5503A', bg: '#FBE8E4', line: '#F3CDC4' }, // out-of-range / high (异常/偏高)
  info: { fg: '#2A6FDB', bg: '#E7EEFB', line: '#CBDCF6' },
} as const;

export type RevaStatus = keyof typeof revaSemantic;

// ── Font families (bundle via expo-font; see header note) ──────────────────
export const revaFonts = {
  sans: 'Manrope', // Latin UI / headlines
  cjk: 'NotoSansSC', // Chinese
  mono: 'IBMPlexMono', // data, lab values, tabular numerals
} as const;

// ── Radii ──────────────────────────────────────────────────────────────────
export const revaRadii = {
  xs: 6,
  sm: 10,
  md: 14,
  lg: 18, // default card radius
  xl: 24, // sheets, hero cards
  pill: 999,
} as const;

// ── Spacing (4px base) ──────────────────────────────────────────────────────
export const revaSpacing = {
  s1: 4, s2: 8, s3: 12, s4: 16, s5: 20,
  s6: 24, s7: 32, s8: 40, s9: 48, s10: 64,
} as const;

// ── Shadows (soft, low, green-tinted) → RN style objects ────────────────────
// shadowColor uses the ink tone (#142019 ≈ rgba(20,32,27)) the CSS shadows use.
export const revaShadows = {
  sm: {
    shadowColor: '#142019', shadowOpacity: 0.06, shadowRadius: 2,
    shadowOffset: { width: 0, height: 1 }, elevation: 1,
  },
  md: {
    shadowColor: '#142019', shadowOpacity: 0.08, shadowRadius: 16,
    shadowOffset: { width: 0, height: 4 }, elevation: 4,
  },
  lg: {
    shadowColor: '#142019', shadowOpacity: 0.12, shadowRadius: 36,
    shadowOffset: { width: 0, height: 14 }, elevation: 10,
  },
  focus: {
    shadowColor: '#08140F', shadowOpacity: 0.45, shadowRadius: 48,
    shadowOffset: { width: 0, height: 18 }, elevation: 18,
  },
} as const;

// ── Motion ──────────────────────────────────────────────────────────────────
// RN: pair durations with Easing.bezier(...) at the call site.
export const revaMotion = {
  durFast: 140,
  dur: 240,
  durSlow: 420,
  easeOut: [0.22, 0.61, 0.36, 1] as const, // cubic-bezier
  easeInOut: [0.45, 0, 0.25, 1] as const,
} as const;

// ── Type scale (semantic) → RN TextStyle objects ────────────────────────────
// lineHeight is absolute px (fontSize × css line-height); letterSpacing in px
// (css em × fontSize). Mono families carry tabular figures for measurements.
export const revaType = {
  display: { // big metric numbers — readiness score, lab value
    fontFamily: revaFonts.mono, fontWeight: '500' as const,
    fontSize: 56, lineHeight: 56, letterSpacing: -1.12, color: revaColors.ink1,
  },
  metric: { // medium metric number
    fontFamily: revaFonts.mono, fontWeight: '500' as const,
    fontSize: 30, lineHeight: 32, letterSpacing: -0.3,
  },
  h1: { fontFamily: revaFonts.sans, fontWeight: '800' as const, fontSize: 28, lineHeight: 34, letterSpacing: -0.56, color: revaColors.ink1 },
  h2: { fontFamily: revaFonts.sans, fontWeight: '700' as const, fontSize: 22, lineHeight: 28, letterSpacing: -0.22, color: revaColors.ink1 },
  h3: { fontFamily: revaFonts.sans, fontWeight: '700' as const, fontSize: 18, lineHeight: 23, color: revaColors.ink1 },
  title: { fontFamily: revaFonts.sans, fontWeight: '600' as const, fontSize: 16, lineHeight: 22, color: revaColors.ink1 },
  body: { fontFamily: revaFonts.sans, fontWeight: '400' as const, fontSize: 15, lineHeight: 23, color: revaColors.ink1 },
  body2: { fontFamily: revaFonts.sans, fontWeight: '400' as const, fontSize: 14, lineHeight: 21, color: revaColors.ink2 },
  caption: { fontFamily: revaFonts.sans, fontWeight: '500' as const, fontSize: 12, lineHeight: 17, color: revaColors.ink3 },
  overline: { fontFamily: revaFonts.sans, fontWeight: '600' as const, fontSize: 11, lineHeight: 14, letterSpacing: 0.88, color: revaColors.ink3 }, // uppercase at call site
  dataLabel: { fontFamily: revaFonts.mono, fontWeight: '500' as const, fontSize: 12, letterSpacing: 0.24, color: revaColors.ink3 },
  unit: { fontFamily: revaFonts.mono, fontWeight: '400' as const, fontSize: 14, color: revaColors.ink3 },
} as const;

export const revaTheme = {
  colors: revaColors,
  semantic: revaSemantic,
  fonts: revaFonts,
  radii: revaRadii,
  spacing: revaSpacing,
  shadows: revaShadows,
  motion: revaMotion,
  type: revaType,
} as const;

export default revaTheme;
