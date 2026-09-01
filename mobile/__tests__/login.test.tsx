/* eslint-disable import/first */
import React from 'react';
import { render } from '@testing-library/react-native';

const mockLogin = jest.fn();
const mockVerifyPhoneCode = jest.fn();
const mockCompleteInvitedRegistration = jest.fn();

jest.mock('../hooks/useAuth', () => ({
  useAuth: () => ({
    login: mockLogin,
    verifyPhoneCode: mockVerifyPhoneCode,
    completeInvitedRegistration: mockCompleteInvitedRegistration,
    pendingRegistration: null,
  }),
}));

jest.mock('expo-router', () => ({ useRouter: () => ({ replace: jest.fn() }) }));

jest.mock('../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgPrimary: '#fff',
      bgCard: '#f8f8f8',
      brand: '#0A8F8F',
      brandLight: '#E6F5F3',
      labelPrimary: '#111',
      labelSecondary: '#666',
      labelTertiary: '#999',
      separator: '#ddd',
    },
    s: {
      danger: { fg: '#900', bg: '#fee', solid: '#c00' },
    },
  }),
}));

jest.mock('../services/auth', () => ({
  loadCredentials: jest.fn().mockResolvedValue(null),
  saveCredentials: jest.fn().mockResolvedValue(undefined),
}));

import LoginScreen from '../app/login';

describe('LoginScreen', () => {
  it('uses 小巴健康 and invitation-only registration language', () => {
    const { getByText, queryByText } = render(<LoginScreen />);

    expect(getByText('小巴健康')).toBeTruthy();
    expect(getByText('登录小巴')).toBeTruthy();
    expect(getByText('首次使用需获得管理员邀请')).toBeTruthy();
    expect(queryByText('登录 / 注册')).toBeNull();
    expect(queryByText('HealthPilot')).toBeNull();
  });
});
