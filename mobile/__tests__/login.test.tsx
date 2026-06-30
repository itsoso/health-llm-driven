/* eslint-disable import/first */
import React from 'react';
import { render } from '@testing-library/react-native';

const mockLogin = jest.fn();

jest.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ login: mockLogin }),
}));

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
  }),
}));

jest.mock('../services/auth', () => ({
  loadCredentials: jest.fn().mockResolvedValue(null),
  saveCredentials: jest.fn().mockResolvedValue(undefined),
}));

import LoginScreen from '../app/login';

describe('LoginScreen', () => {
  it('uses 阿衡 as the login brand name', () => {
    const { getByText, queryByText } = render(<LoginScreen />);

    expect(getByText('阿衡')).toBeTruthy();
    expect(queryByText('HealthPilot')).toBeNull();
  });
});
