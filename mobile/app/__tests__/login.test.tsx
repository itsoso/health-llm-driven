/* eslint-disable import/first */
import React from 'react';
import { Alert } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';

const mockLogin = jest.fn();
const mockVerifyPhoneCode = jest.fn();
const mockCompleteInvitedRegistration = jest.fn();
const mockRequestPhoneCode = jest.fn();
const mockReplace = jest.fn();

let mockPendingRegistration: { expiresAt: number; phoneMasked?: string } | null = null;

jest.mock('expo-router', () => ({
  useRouter: () => ({ replace: mockReplace }),
}));

jest.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    login: mockLogin,
    verifyPhoneCode: mockVerifyPhoneCode,
    completeInvitedRegistration: mockCompleteInvitedRegistration,
    pendingRegistration: mockPendingRegistration,
  }),
}));

jest.mock('../../services/auth', () => ({
  requestPhoneCode: (...args: unknown[]) => mockRequestPhoneCode(...args),
  loadCredentials: jest.fn().mockResolvedValue(null),
  saveCredentials: jest.fn().mockResolvedValue(undefined),
  registrationAuthErrorCode: (error: unknown) => (
    (error as { code?: string; response?: { data?: { detail?: { code?: string } } } } | null)
      ?.code
    ?? (error as { response?: { data?: { detail?: { code?: string } } } } | null)
      ?.response?.data?.detail?.code
    ?? null
  ),
}));

jest.mock('../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgPrimary: '#F8F7F2',
      bgCard: '#FFFFFF',
      fill: '#F1F0EA',
      labelPrimary: '#10231D',
      labelSecondary: '#66736D',
      labelTertiary: '#A1AAA5',
      separator: '#E5E2D8',
      brand: '#15946B',
      brandLight: '#E4F4EC',
    },
    s: {
      danger: { fg: '#9B2C2C', bg: '#FFF0F0', solid: '#D92D20' },
    },
  }),
}));

import LoginScreen from '../login';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

function beginOtp(view: ReturnType<typeof render>, phone = '+86 138 0013 8000') {
  fireEvent.changeText(view.getByLabelText('手机号输入框'), phone);
  fireEvent.press(view.getByText('获取验证码'));
}

async function reachInvite(view: ReturnType<typeof render>) {
  beginOtp(view);
  await waitFor(() => expect(view.getByLabelText('验证码输入框')).toBeTruthy());
  fireEvent.changeText(view.getByLabelText('验证码输入框'), '123456');
  mockVerifyPhoneCode.mockImplementationOnce(async () => {
    mockPendingRegistration = { expiresAt: Date.now() + 300_000, phoneMasked: '+86 138****8000' };
    return 'invitation_required';
  });
  fireEvent.press(view.getByText('验证并登录'));
  await waitFor(() => expect(view.getByText('输入邀请码')).toBeTruthy());
}

describe('LoginScreen invitation-gated phone auth', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockPendingRegistration = null;
    mockRequestPhoneCode.mockResolvedValue({
      phone: '+8613800138000',
      expires_in_seconds: 300,
      dev_code: null,
      message: '验证码已发送',
    });
    mockVerifyPhoneCode.mockResolvedValue('authenticated');
    mockCompleteInvitedRegistration.mockResolvedValue(undefined);
    jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
    jest.useRealTimers();
  });

  it('uses invitation-only copy and defaults the phone field to +86', () => {
    const view = render(<LoginScreen />);

    expect(view.getByText('登录小巴')).toBeTruthy();
    expect(view.getByText('首次使用需获得管理员邀请')).toBeTruthy();
    expect(view.queryByText('登录 / 注册')).toBeNull();
    expect(view.getByLabelText('手机号输入框').props.value).toBe('+86 ');
    expect(view.getByLabelText('获取验证码').props.accessibilityState.disabled).toBe(true);
    fireEvent.changeText(view.getByLabelText('手机号输入框'), '+86 138 0013 8000');
    expect(view.getByLabelText('获取验证码').props.accessibilityState.disabled).toBe(false);
  });

  it('acknowledges a deep-link invitation on the phone step without displaying its token or phone', () => {
    const secret = 'abcdefghijklmnopqrstuvwxyz_123456';
    const view = render(<LoginScreen invitationLinkToken={secret} />);

    expect(view.getByText('已获得邀请')).toBeTruthy();
    expect(view.queryByText(secret)).toBeNull();
    expect(view.queryByText('13800138000')).toBeNull();
  });

  it('verifies an existing phone once and lets the authenticated root navigate normally', async () => {
    const view = render(<LoginScreen />);
    beginOtp(view);
    await waitFor(() => expect(mockRequestPhoneCode).toHaveBeenCalledWith('+8613800138000', 'login'));

    fireEvent.changeText(view.getByLabelText('验证码输入框'), '123456');
    fireEvent.press(view.getByText('验证并登录'));

    await waitFor(() => expect(mockVerifyPhoneCode).toHaveBeenCalledWith('+8613800138000', '123456'));
    expect(mockCompleteInvitedRegistration).not.toHaveBeenCalled();
    expect(mockReplace).not.toHaveBeenCalledWith('/reva-onboarding');
  });

  it('discards a deep-link credential locally after an existing phone authenticates', async () => {
    const clearLink = jest.fn();
    const view = render(
      <LoginScreen
        invitationLinkToken="abcdefghijklmnopqrstuvwxyz_123456"
        onInvitationLinkCleared={clearLink}
      />,
    );
    beginOtp(view);
    await waitFor(() => expect(view.getByLabelText('验证码输入框')).toBeTruthy());
    fireEvent.changeText(view.getByLabelText('验证码输入框'), '123456');
    fireEvent.press(view.getByText('验证并登录'));

    await waitFor(() => expect(clearLink).toHaveBeenCalledTimes(1));
    expect(mockCompleteInvitedRegistration).not.toHaveBeenCalled();
  });

  it('moves an unknown phone from OTP to invite without requesting a second OTP', async () => {
    const view = render(<LoginScreen />);
    await reachInvite(view);

    expect(view.getByText('小巴目前采用邀请制，请输入管理员发送的邀请码。')).toBeTruthy();
    expect(view.getByText('+86 138****8000')).toBeTruthy();
    expect(mockRequestPhoneCode).toHaveBeenCalledTimes(1);
  });

  it('keeps the manual invite path behind phone ownership verification', async () => {
    const view = render(<LoginScreen />);

    fireEvent.press(view.getByText('我有邀请码'));
    expect(Alert.alert).toHaveBeenCalledWith('先验证手机号', '邀请码需与手机号匹配，请先获取并验证短信验证码。');
    await reachInvite(view);
    fireEvent.changeText(view.getByLabelText('邀请码输入框'), 'abcd2e7k');
    fireEvent.press(view.getByText('完成注册'));

    await waitFor(() => expect(mockCompleteInvitedRegistration).toHaveBeenCalledWith({ manualCode: 'ABCD2E7K' }));
    expect(view.getByText('邀请验证成功，欢迎加入小巴')).toBeTruthy();
    fireEvent.press(view.getByText('开始设置我的健康档案'));
    expect(mockReplace).toHaveBeenCalledWith('/reva-onboarding');
  });

  it('lets the authenticated root preserve the welcome step before onboarding navigation', () => {
    const startOnboarding = jest.fn();
    const view = render(
      <LoginScreen
        registrationCompleted
        onStartHealthProfile={startOnboarding}
      />,
    );

    expect(view.getByText('邀请验证成功，欢迎加入小巴')).toBeTruthy();
    fireEvent.press(view.getByText('开始设置我的健康档案'));
    expect(startOnboarding).toHaveBeenCalledTimes(1);
  });

  it('uses a preloaded deep-link token only after OTP and never displays it', async () => {
    const secret = 'abcdefghijklmnopqrstuvwxyz_123456';
    const logSpy = jest.spyOn(console, 'log').mockImplementation(() => {});
    const view = render(<LoginScreen invitationLinkToken={secret} />);

    expect(view.queryByText(secret)).toBeNull();
    await reachInvite(view);
    expect(view.getByText('已读取安全邀请链接')).toBeTruthy();
    await waitFor(() => expect(
      view.getByLabelText('完成注册').props.accessibilityState.disabled,
    ).toBe(false));
    fireEvent.press(view.getByText('完成注册'));

    await waitFor(() => expect(mockCompleteInvitedRegistration).toHaveBeenCalledWith({ linkToken: secret }));
    expect(logSpy).not.toHaveBeenCalled();
  });

  it('lets a newer runtime link replace manual entry and clears the typed code', async () => {
    const firstToken = 'abcdefghijklmnopqrstuvwxyz_123456';
    const secondToken = 'zyxwvutsrqponmlkjihgfedc_654321';
    const view = render(<LoginScreen invitationLinkToken={firstToken} />);
    await reachInvite(view);
    await waitFor(() => expect(
      view.getByLabelText('改用 8 位邀请码').props.accessibilityState.disabled,
    ).toBe(false));
    fireEvent.press(view.getByText('改用 8 位邀请码'));
    fireEvent.changeText(view.getByLabelText('邀请码输入框'), 'ABCD2E7K');

    view.rerender(<LoginScreen invitationLinkToken={secondToken} />);

    await waitFor(() => expect(view.getByText('已读取安全邀请链接')).toBeTruthy());
    expect(view.queryByLabelText('邀请码输入框')).toBeNull();
    fireEvent.press(view.getByText('完成注册'));
    await waitFor(() => expect(mockCompleteInvitedRegistration)
      .toHaveBeenCalledWith({ linkToken: secondToken }));
  });

  it('restores an unexpired pending registration directly to invite entry after restart', () => {
    mockPendingRegistration = { expiresAt: Date.now() + 60_000, phoneMasked: '+86 139****1234' };
    const view = render(<LoginScreen />);

    expect(view.getByText('输入邀请码')).toBeTruthy();
    expect(view.getByText('+86 139****1234')).toBeTruthy();
    expect(view.queryByLabelText('验证码输入框')).toBeNull();
  });

  it.each([
    ['INVITATION_PHONE_MISMATCH', '该邀请码不是发送给当前手机号的，请确认手机号或联系管理员。'],
    ['INVITATION_EXPIRED', '邀请码已过期，请联系管理员重新发送。'],
    ['INVITATION_REVOKED', '邀请码已被撤销，请联系管理员。'],
    ['INVITATION_ALREADY_USED', '邀请码已使用；如已注册，请返回使用手机号登录。'],
    ['INVITATION_INVALID', '邀请码无效，请检查后重试或联系管理员。'],
  ])('maps %s to an actionable message without exposing server detail', async (code, message) => {
    mockCompleteInvitedRegistration.mockRejectedValueOnce({
      response: { data: { detail: { code, message: 'SERVER_SECRET_DETAIL' } } },
    });
    const view = render(<LoginScreen />);
    await reachInvite(view);
    fireEvent.changeText(view.getByLabelText('邀请码输入框'), 'ABCD2E7K');
    fireEvent.press(view.getByText('完成注册'));

    await waitFor(() => expect(view.getByText(message)).toBeTruthy());
    expect(view.queryByText('SERVER_SECRET_DETAIL')).toBeNull();
  });

  it('returns to phone verification when the verified ticket expires', async () => {
    mockCompleteInvitedRegistration.mockRejectedValueOnce({
      name: 'RegistrationFlowError',
      code: 'VERIFIED_PHONE_TICKET_EXPIRED',
    });
    const view = render(<LoginScreen />);
    await reachInvite(view);
    fireEvent.changeText(view.getByLabelText('邀请码输入框'), 'ABCD2E7K');
    fireEvent.press(view.getByText('完成注册'));

    await waitFor(() => expect(view.getByText('验证码已过期，请重新验证。')).toBeTruthy());
    expect(view.getByLabelText('验证码输入框')).toBeTruthy();
    expect(view.getByText(/\+86138\*\*\*\*8000/)).toBeTruthy();
    expect(view.getByLabelText('验证码输入框').props.value).toBe('');
  });

  it('clears the old OTP as soon as resend starts and disables mutable controls while loading', async () => {
    jest.useFakeTimers();
    const view = render(<LoginScreen />);
    beginOtp(view);
    await act(async () => {});
    fireEvent.changeText(view.getByLabelText('验证码输入框'), '123456');
    act(() => jest.advanceTimersByTime(60_000));
    const resend = deferred<{
      phone: string;
      expires_in_seconds: number;
      dev_code: null;
      message: string;
    }>();
    mockRequestPhoneCode.mockReturnValueOnce(resend.promise);

    fireEvent.press(view.getByText('重新发送'));

    expect(view.getByLabelText('验证码输入框').props.value).toBe('');
    expect(view.getByLabelText('修改手机号').props.accessibilityState.disabled).toBe(true);
    expect(view.getByLabelText('重新发送验证码').props.accessibilityState.disabled).toBe(true);
    await act(async () => resend.resolve({
      phone: '+8613800138000',
      expires_in_seconds: 300,
      dev_code: null,
      message: '验证码已发送',
    }));
  });

  it('disables login-mode and invite shortcuts while requesting an OTP', async () => {
    const request = deferred<{
      phone: string;
      expires_in_seconds: number;
      dev_code: null;
      message: string;
    }>();
    mockRequestPhoneCode.mockReturnValueOnce(request.promise);
    const view = render(<LoginScreen />);
    fireEvent.changeText(view.getByLabelText('手机号输入框'), '+86 138 0013 8000');
    fireEvent.press(view.getByText('获取验证码'));

    expect(view.getByLabelText('我有邀请码').props.accessibilityState.disabled).toBe(true);
    expect(view.getByLabelText('账号密码登录').props.accessibilityState.disabled).toBe(true);
    await act(async () => request.resolve({
      phone: '+8613800138000',
      expires_in_seconds: 300,
      dev_code: null,
      message: '验证码已发送',
    }));
  });

  it('disables manual-credential switching while link registration is submitting', async () => {
    const completion = deferred<void>();
    mockCompleteInvitedRegistration.mockReturnValueOnce(completion.promise);
    const view = render(
      <LoginScreen invitationLinkToken="abcdefghijklmnopqrstuvwxyz_123456" />,
    );
    await reachInvite(view);
    await waitFor(() => expect(
      view.getByLabelText('改用 8 位邀请码').props.accessibilityState.disabled,
    ).toBe(false));
    fireEvent.press(view.getByText('完成注册'));

    expect(view.getByLabelText('改用 8 位邀请码').props.accessibilityState.disabled).toBe(true);
    await act(async () => completion.resolve());
  });

  it('disables switching login methods while account login is submitting', async () => {
    const login = deferred<void>();
    mockLogin.mockReturnValueOnce(login.promise);
    const view = render(<LoginScreen />);
    fireEvent.press(view.getByText('账号密码登录'));
    fireEvent.changeText(view.getByLabelText('用户名输入框'), 'alice');
    fireEvent.changeText(view.getByLabelText('密码输入框'), 'hunter2');
    fireEvent.press(view.getByText('登录'));

    expect(view.getByLabelText('手机号登录').props.accessibilityState.disabled).toBe(true);
    await act(async () => login.resolve());
  });

  it('offers countdown resend and change-phone controls on the OTP step', async () => {
    jest.useFakeTimers();
    const view = render(<LoginScreen />);
    beginOtp(view);
    await act(async () => {});

    expect(view.getByText(/重新发送 \(\d+s\)/)).toBeTruthy();
    fireEvent.press(view.getByText('修改手机号'));
    expect(view.queryByLabelText('验证码输入框')).toBeNull();
  });

  it('keeps account password login as a secondary fallback', async () => {
    const view = render(<LoginScreen />);

    fireEvent.press(view.getByText('账号密码登录'));
    fireEvent.changeText(view.getByLabelText('用户名输入框'), 'alice');
    fireEvent.changeText(view.getByLabelText('密码输入框'), 'hunter2');
    fireEvent.press(view.getByText('登录'));

    await waitFor(() => expect(mockLogin).toHaveBeenCalledWith('alice', 'hunter2'));
  });

  it('shows an inline error when account password login fails', async () => {
    mockLogin.mockRejectedValueOnce({ response: { status: 401 } });
    const view = render(<LoginScreen />);

    fireEvent.press(view.getByText('账号密码登录'));
    fireEvent.changeText(view.getByLabelText('用户名输入框'), 'alice');
    fireEvent.changeText(view.getByLabelText('密码输入框'), 'wrong-password');
    fireEvent.press(view.getByText('登录'));

    expect(await view.findByRole('alert')).toHaveTextContent('登录失败，请检查账号信息。');
  });
});
