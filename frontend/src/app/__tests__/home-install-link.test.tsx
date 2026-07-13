import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: null }),
}));

vi.mock('@/services/api/client', () => ({
  api: { get: vi.fn() },
}));

describe('Home mobile install link', () => {
  it('links to the current QR install page from the web homepage', async () => {
    const Home = (await import('@/app/page')).default;

    render(<Home />);

    const installLink = screen.getByRole('link', { name: /扫码安装 iPhone 版/i });
    expect(installLink).toHaveAttribute('href', '/mobile-install/ios/latest/install.html');
  });
});
