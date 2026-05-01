/**
 * useTheme — 主题钩子
 *
 * 统一从这里拿调色板, 不要直接 `import { colors } from theme` (那样不响应 dark mode 切换).
 * 系统切换 light/dark 时自动重渲, 所有 c.* 引用就跟着切.
 *
 * 用法:
 *   const { c, isDark } = useTheme();
 *   <View style={{ backgroundColor: c.bgCard }} />
 *
 * createStyles(c) 模式 (推荐):
 *   const { c } = useTheme();
 *   const styles = useMemo(() => createStyles(c), [c]);
 *   function createStyles(c: ColorPalette) {
 *     return StyleSheet.create({ card: { backgroundColor: c.bgCard, ... } });
 *   }
 */
import { useMemo } from 'react';
import { useColorScheme } from 'react-native';
import { colors, darkColors } from '../constants/theme';

export type ColorPalette = typeof colors;
export type ThemeScheme = 'light' | 'dark';

// 旧别名 — 保留向后兼容, 新代码用 useTheme.
export type ThemeColors = ColorPalette;

export function useThemeColors(): ColorPalette {
  return useTheme().c;
}

export function useIsDarkMode(): boolean {
  return useTheme().isDark;
}

export function useTheme(): { scheme: ThemeScheme; isDark: boolean; c: ColorPalette } {
  const scheme = useColorScheme();
  const isDark = scheme === 'dark';
  return useMemo(
    () => ({
      scheme: (isDark ? 'dark' : 'light') as ThemeScheme,
      isDark,
      c: isDark ? (darkColors as unknown as ColorPalette) : colors,
    }),
    [isDark],
  );
}
