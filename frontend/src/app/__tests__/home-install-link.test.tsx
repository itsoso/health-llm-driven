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

    const installLink = screen.getByRole('link', { name: /扫码安装小巴 iOS/i });
    expect(installLink).toHaveAttribute(
      'href',
      'https://health.executor.life/mobile-install/ios/20260705-124315-f4ac7f14/install.html',
    );
  });
});
