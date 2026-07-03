// @vitest-environment jsdom
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('next/link', () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    login: vi.fn(),
    isAuthenticated: false,
  }),
}));

import LoginPage from './page';

describe('LoginPage', () => {
  it('makes phone login available through the primary identifier field', async () => {
    render(<LoginPage />);

    expect(await screen.findByLabelText('手机号 / 邮箱 / 用户名')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('请输入手机号、邮箱或用户名')).toBeInTheDocument();
  });
});
