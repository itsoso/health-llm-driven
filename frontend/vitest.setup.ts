// @ts-nocheck — vitest 是 devDependency，next build 时不可用
import { vi } from 'vitest';
import '@testing-library/jest-dom/vitest';

Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
  configurable: true,
  value: vi.fn(),
});

// jsdom 在某些 vitest+next 组合下不会自动提供 localStorage 的 .clear()
// 补一个完整 in-memory 实现, 避免测试因环境差异而崩.
if (typeof window !== 'undefined') {
  const ensureStorage = (key) => {
    if (!window[key] || typeof window[key].clear !== 'function') {
      const store = new Map();
      Object.defineProperty(window, key, {
        configurable: true,
        value: {
          getItem: (k) => (store.has(k) ? store.get(k) : null),
          setItem: (k, v) => { store.set(k, String(v)); },
          removeItem: (k) => { store.delete(k); },
          clear: () => store.clear(),
          key: (i) => Array.from(store.keys())[i] ?? null,
          get length() { return store.size; },
        },
      });
    }
  };
  ensureStorage('localStorage');
  ensureStorage('sessionStorage');
}
