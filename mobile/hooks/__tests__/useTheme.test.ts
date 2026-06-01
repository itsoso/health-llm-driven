import { renderHook } from '@testing-library/react-native';
import {
  colors,
  darkColors,
  semanticColors,
  darkSemanticColors,
} from '../../constants/theme';

let mockScheme: 'light' | 'dark' = 'light';
jest.mock('react-native/Libraries/Utilities/useColorScheme', () => ({
  __esModule: true,
  default: () => mockScheme,
}));

import { useThemeColors, useIsDarkMode, useTheme } from '../useTheme';

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

describe('useTheme().s (semantic palette)', () => {
  it('returns light semantic palette by default', () => {
    mockScheme = 'light';
    const { result } = renderHook(() => useTheme());
    expect(result.current.s.success.bg).toBe(semanticColors.success.bg);
    expect(result.current.s.danger.fg).toBe(semanticColors.danger.fg);
  });

  it('returns dark semantic palette in dark mode', () => {
    mockScheme = 'dark';
    const { result } = renderHook(() => useTheme());
    expect(result.current.s.success.bg).toBe(darkSemanticColors.success.bg);
    expect(result.current.s.danger.fg).toBe(darkSemanticColors.danger.fg);
  });
});
