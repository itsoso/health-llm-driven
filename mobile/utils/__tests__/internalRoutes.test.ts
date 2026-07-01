import { isSafeInternalRoute } from '../internalRoutes';

describe('isSafeInternalRoute', () => {
  it('accepts app-local routes', () => {
    expect(isSafeInternalRoute('/(tabs)/chat?prompt=hrv')).toBe(true);
    expect(isSafeInternalRoute('/indicator-history?type=weight')).toBe(true);
  });

  it('rejects external, scheme-relative, and control-character routes', () => {
    expect(isSafeInternalRoute('https://example.test/path')).toBe(false);
    expect(isSafeInternalRoute('//example.test/path')).toBe(false);
    expect(isSafeInternalRoute('/(tabs)/chat\ninject')).toBe(false);
  });
});
