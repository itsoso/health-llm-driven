import { useColorScheme } from 'react-native';
import { colors, darkColors } from '@/constants/theme';

export type ThemeColors = typeof colors;

export function useThemeColors(): ThemeColors {
  const scheme = useColorScheme();
  return scheme === 'dark' ? (darkColors as unknown as ThemeColors) : colors;
}

export function useIsDarkMode(): boolean {
  return useColorScheme() === 'dark';
}
