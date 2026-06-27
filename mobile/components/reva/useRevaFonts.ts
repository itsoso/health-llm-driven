/**
 * 复元 Reva — font loader. Registers the design's signature families so the
 * revaTheme type tokens render correctly: Manrope (Latin UI/headlines) and
 * IBM Plex Mono (data/lab values/tabular numerals).
 *
 * Loaded at the app root so data-heavy cards do not flash fallback fonts. CJK
 * keeps the system font (PingFang on iOS) — the full Noto Sans SC TTF is ~10MB
 * and not worth bundling; the design flagged the same.
 */
import { useFonts } from 'expo-font';

export function useRevaFonts(): boolean {
  const [loaded] = useFonts({
    Manrope: require('../../assets/fonts/Manrope-Variable.ttf'),
    IBMPlexMono: require('../../assets/fonts/IBMPlexMono-Regular.ttf'),
    'IBMPlexMono-Medium': require('../../assets/fonts/IBMPlexMono-Medium.ttf'),
  });
  return loaded;
}
