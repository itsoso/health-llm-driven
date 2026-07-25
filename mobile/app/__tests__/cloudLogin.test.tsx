/* eslint-disable import/first */
import React from 'react';
import { render } from '@testing-library/react-native';

jest.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    login: jest.fn(),
    loginByPhoneCode: jest.fn(),
  }),
}));

jest.mock('../../services/auth', () => ({
  loadCredentials: jest.fn().mockResolvedValue(null),
  requestPhoneCode: jest.fn(),
  saveCredentials: jest.fn(),
}));

jest.mock('../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgPrimary: '#fff', bgCard: '#fff', brandLight: '#eee', brand: '#15976c',
      labelPrimary: '#111', labelSecondary: '#555', labelTertiary: '#888',
      separator: '#ddd',
    },
  }),
}));

import LoginScreen from '../login';

describe('cloud account onboarding', () => {
  it('offers account authentication without a local-mode entry', () => {
    const screen = render(<LoginScreen />);

    expect(screen.getByText('账号密码登录')).toBeTruthy();
    expect(screen.queryByText('无需注册，立即本地使用')).toBeNull();
  });
});
