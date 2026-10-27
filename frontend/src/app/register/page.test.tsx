import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { push, verifyPhoneCode, post } = vi.hoisted(() => ({ push: vi.fn(), verifyPhoneCode: vi.fn(), post: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));
vi.mock('next/link', () => ({ default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a> }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ isAuthenticated: false, verifyPhoneCode }) }));
vi.mock('@/services/api/client', () => ({ api: { post } }));
import RegisterPage from './page';

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe('public phone registration', () => {
  it('registers through a verified phone without an invitation or a health questionnaire', async () => {
    post.mockResolvedValue({ data: { phone: '+8613800138000' } });
    verifyPhoneCode.mockResolvedValue({ success: true });
    render(<RegisterPage />);
    expect(screen.queryByLabelText(/邀请码/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('手机号'), { target: { value: '138 0013 8000' } });
    fireEvent.click(screen.getByRole('button', { name: '获取验证码' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/auth/phone/code', { phone: '+8613800138000', purpose: 'login' }));
    fireEvent.change(await screen.findByLabelText('短信验证码'), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: '验证并登录 / 注册' }));
    await waitFor(() => expect(verifyPhoneCode).toHaveBeenCalledWith('+8613800138000', '123456'));
    await waitFor(() => expect(push).toHaveBeenCalledWith('/'));
    expect(screen.queryByText('健康问卷')).not.toBeInTheDocument();
  });

  it('keeps the verified code bound to the number it was sent to', async () => {
    post.mockResolvedValue({ data: {} });
    render(<RegisterPage />);
    fireEvent.change(screen.getByLabelText('手机号'), { target: { value: '13800138000' } });
    fireEvent.click(screen.getByRole('button', { name: '获取验证码' }));
    await screen.findByLabelText('短信验证码');
    expect(screen.getByLabelText('手机号')).toBeDisabled();
    expect(screen.getByRole('button', { name: /秒后重新获取/ })).toBeDisabled();
  });

  it('shows the structured server rejection without advancing', async () => {
    post.mockRejectedValue({ response: { data: { detail: { code: 'REGISTRATION_CLOSED', message: '新用户注册暂时关闭' } } } });
    render(<RegisterPage />);
    fireEvent.change(screen.getByLabelText('手机号'), { target: { value: '13800138000' } });
    fireEvent.click(screen.getByRole('button', { name: '获取验证码' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('新用户注册暂时关闭');
    expect(verifyPhoneCode).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });

  it('does not navigate when session verification fails', async () => {
    post.mockResolvedValue({ data: {} });
    verifyPhoneCode.mockResolvedValue({ success: false, error: '登录服务返回了无法识别的验证结果' });
    render(<RegisterPage />);
    fireEvent.change(screen.getByLabelText('手机号'), { target: { value: '13800138000' } });
    fireEvent.click(screen.getByRole('button', { name: '获取验证码' }));
    fireEvent.change(await screen.findByLabelText('短信验证码'), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: '验证并登录 / 注册' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('无法识别');
    expect(push).not.toHaveBeenCalled();
  });
});
