// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Navigation from '../Navigation';

const route = vi.hoisted(() => ({ pathname: '/admin', search: '' }));
vi.mock('next/navigation', () => ({
  usePathname: () => route.pathname,
  useSearchParams: () => new URLSearchParams(route.search),
}));
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
  beforeEach(() => { route.pathname = '/admin'; route.search = ''; });

  it('offers LifeNav directly in the top bar and closes the mobile menu on selection', () => {
    render(<Navigation />);
    expect(screen.getAllByRole('link', { name: '人生导航' })).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: '打开主菜单' }));
    const links = screen.getAllByRole('link', { name: '人生导航' });
    expect(links).toHaveLength(3);
    links.forEach(link => expect(link).toHaveAttribute('href', '/agenda?navigation=week'));
    links[2].addEventListener('click', event => event.preventDefault());
    fireEvent.click(links[2]);
    expect(screen.getAllByRole('link', { name: '人生导航' })).toHaveLength(2);
  });

  it.each(['', 'navigation=week', 'navigation=other', 'navigation=week&view=today'])(
    'highlights only the matching agenda view for %s and updates after navigation', (search) => {
      route.pathname = '/agenda';
      route.search = search;
      const view = render(<Navigation />);
      const isLifeNav = new URLSearchParams(search).get('navigation') === 'week';
      screen.getAllByRole('link', { name: '人生导航' }).forEach(link => {
        expect(link.classList.contains('bg-purple-600/90')).toBe(isLifeNav);
      });
      screen.getAllByRole('link', { name: '今日议程' }).forEach(link => {
        expect(link.classList.contains('bg-purple-600/90')).toBe(!isLifeNav);
      });
      route.search = isLifeNav ? '' : 'navigation=week';
      view.rerender(<Navigation />);
      screen.getAllByRole('link', { name: '人生导航' }).forEach(link => {
        expect(link.classList.contains('bg-purple-600/90')).toBe(!isLifeNav);
      });
    },
  );

  it('opens Garmin data through the existing dashboard route', () => {
    render(<Navigation />);
    fireEvent.click(screen.getByRole('button', { name: '每日记录' }));
    expect(screen.getByRole('link', { name: 'Garmin数据' })).toHaveAttribute('href', '/dashboard');
  });

  it('links every visible health overview entry to the existing dashboard route', () => {
    render(<Navigation />);

    const overviewLinks = screen.getAllByRole('link', { name: '健康概览' });
    expect(overviewLinks.length).toBeGreaterThan(0);
    overviewLinks.forEach((link) => expect(link).toHaveAttribute('href', '/dashboard'));
  });
});
