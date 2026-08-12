import { describe, expect, it, vi } from 'vitest';

import ArchitectureRedirect from './page';


const redirect = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ redirect }));

describe('ArchitectureRedirect', () => {
  it('redirects the legacy path to the generated System Map', () => {
    ArchitectureRedirect();

    expect(redirect).toHaveBeenCalledWith('/admin/system-map');
  });
});
