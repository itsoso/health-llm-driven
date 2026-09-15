// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import Navigation from '../Navigation';

vi.mock('next/navigation', () => ({ usePathname: () => '/admin' }));
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: null,
    isAuthenticated: false,
    isLoading: true,
    logout: vi.fn(),
  }),
}));
vi.mock('@/components/NotificationCenter', () => ({ default: () => null }));

describe('Navigation', () => {
  it('links every visible health overview entry to the existing dashboard route', () => {
    render(<Navigation />);

    const overviewLinks = screen.getAllByRole('link', { name: '健康概览' });
    expect(overviewLinks.length).toBeGreaterThan(0);
    overviewLinks.forEach((link) => expect(link).toHaveAttribute('href', '/dashboard'));
  });
});
