// @ts-nocheck — vitest 是 devDependency，next build 时不可用
import { vi } from 'vitest';
import '@testing-library/jest-dom/vitest';

Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
  configurable: true,
  value: vi.fn(),
});
