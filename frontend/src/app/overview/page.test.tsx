import { describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ redirect: vi.fn() }));
vi.mock('next/navigation', () => ({ redirect: mocks.redirect }));

import OverviewPage from './page';

describe('OverviewPage', () => {
  it('keeps old overview URLs working through the canonical dashboard route', () => {
    OverviewPage();

    expect(mocks.redirect).toHaveBeenCalledWith('/dashboard');
  });
});
