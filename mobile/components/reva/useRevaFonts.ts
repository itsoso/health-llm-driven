/**
 * 复元 Reva — font loader. Registers the design's signature families so the
 * revaTheme type tokens render correctly: Manrope (Latin UI/headlines) and
 * IBM Plex Mono (data/lab values/tabular numerals).
 *
 * Loaded once from the app root so Reva cards can appear on any route or chat
 * surface without a local font gate. CJK keeps the system font (PingFang on iOS)
 * — the full Noto Sans SC TTF is ~10MB and not worth bundling.
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
