import { renderHook } from '@testing-library/react-native';
import { colors, darkColors } from '@/constants/theme';

let mockScheme: 'light' | 'dark' = 'light';
jest.mock('react-native/Libraries/Utilities/useColorScheme', () => ({
  __esModule: true,
  default: () => mockScheme,
}));

import { useThemeColors, useIsDarkMode } from '../useTheme';

describe('useThemeColors', () => {
  it('returns light colors by default', () => {
    mockScheme = 'light';
    const { result } = renderHook(() => useThemeColors());
    expect(result.current.bgPrimary).toBe(colors.bgPrimary);
    expect(result.current.labelPrimary).toBe(colors.labelPrimary);
  });

  it('returns dark colors in dark mode', () => {
    mockScheme = 'dark';
    const { result } = renderHook(() => useThemeColors());
    expect(result.current.bgPrimary).toBe(darkColors.bgPrimary);
    expect(result.current.labelPrimary).toBe(darkColors.labelPrimary);
  });
});

describe('useIsDarkMode', () => {
  it('returns false for light mode', () => {
    mockScheme = 'light';
    const { result } = renderHook(() => useIsDarkMode());
    expect(result.current).toBe(false);
  });

  it('returns true for dark mode', () => {
    mockScheme = 'dark';
    const { result } = renderHook(() => useIsDarkMode());
    expect(result.current).toBe(true);
  });
});
