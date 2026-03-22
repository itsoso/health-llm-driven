import { vi } from 'vitest';
import '@testing-library/jest-dom/vitest';

Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
  configurable: true,
  value: vi.fn(),
});
