/* eslint-disable import/first */
import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

const mockLogin = jest.fn();
const mockLoginByPhoneCode = jest.fn();
const mockRequestPhoneCode = jest.fn();

jest.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    login: mockLogin,
    loginByPhoneCode: mockLoginByPhoneCode,
  }),
}));

jest.mock('../../services/auth', () => ({
  requestPhoneCode: (...args: unknown[]) => mockRequestPhoneCode(...args),
  loadCredentials: jest.fn().mockResolvedValue(null),
  saveCredentials: jest.fn().mockResolvedValue(undefined),
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
  }),
}));

import LoginScreen from '../login';

describe('LoginScreen phone-first auth', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockRequestPhoneCode.mockResolvedValue({
      phone: '+8613800138000',
      expires_in_seconds: 300,
      dev_code: '123456',
      message: '验证码已发送',
    });
  });

  it('uses phone code as the primary login and registration path', async () => {
    const { getByLabelText, getByText } = render(<LoginScreen />);

    fireEvent.changeText(getByLabelText('手机号输入框'), '13800138000');
    fireEvent.press(getByText('获取验证码'));

    await waitFor(() => expect(mockRequestPhoneCode).toHaveBeenCalledWith('13800138000', 'login'));
    expect(getByText('开发验证码已自动填入')).toBeTruthy();

    fireEvent.press(getByText('登录 / 注册'));

    await waitFor(() => expect(mockLoginByPhoneCode).toHaveBeenCalledWith('13800138000', '123456'));
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('keeps account password login as a secondary fallback', async () => {
    const { getByLabelText, getByText } = render(<LoginScreen />);

    fireEvent.press(getByText('账号密码登录'));
    fireEvent.changeText(getByLabelText('用户名输入框'), 'alice');
    fireEvent.changeText(getByLabelText('密码输入框'), 'hunter2');
    fireEvent.press(getByText('登录'));

    await waitFor(() => expect(mockLogin).toHaveBeenCalledWith('alice', 'hunter2'));
  });
});
