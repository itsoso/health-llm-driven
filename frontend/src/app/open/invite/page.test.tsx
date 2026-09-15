// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import RegistrationInviteLanding from './RegistrationInviteLanding';

const token = 'abcdefghijklmnopqrstuvwxyz_123456';

describe('RegistrationInviteLanding', () => {
  afterEach(() => {
    window.history.replaceState(null, '', '/');
  });

  it('consumes the fragment credential without sending it to the Web origin or App Store', async () => {
    window.history.replaceState(null, '', `/open/invite#token=${token}`);
    render(<RegistrationInviteLanding />);

    expect(await screen.findByRole('link', { name: '在小巴健康中打开' })).toHaveAttribute(
      'href',
      `health://invite?token=${token}`,
    );
    expect(window.location.pathname).toBe('/open/invite');
    expect(window.location.search).toBe('');
    expect(window.location.hash).toBe('');
    expect(screen.getByRole('link', { name: '前往 App Store 安装' })).toHaveAttribute(
      'href',
      'https://apps.apple.com/app/id6763569720',
    );
    expect(screen.getByRole('link', { name: '前往 App Store 安装' }).getAttribute('href')).not.toContain(token);
  });

  it.each([
    '/open/invite',
    '/open/invite#token=short',
    `/open/invite?token=${token}`,
    `/open/invite#token=${token}&phone=13800138000`,
    `/open/invite#token=${token}&token=${token}`,
  ])('fails closed and clears invalid or over-scoped credential input: %s', async (url) => {
    window.history.replaceState(null, '', url);
    render(<RegistrationInviteLanding />);

    expect(await screen.findByRole('alert')).toHaveTextContent('注册链接无效或不完整');
    expect(screen.queryByRole('link', { name: '在小巴健康中打开' })).not.toBeInTheDocument();
    await waitFor(() => expect(window.location.href).not.toContain(token));
    expect(window.location.search).toBe('');
    expect(window.location.hash).toBe('');
  });
});
