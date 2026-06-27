/* eslint-disable import/first */
import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

const mockBack = jest.fn();

jest.mock('expo-router', () => ({
  Stack: { Screen: () => null },
  useRouter: () => ({ back: mockBack }),
}));

jest.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 3, username: 'PreviewUser' },
    isAuthenticated: true,
  }),
}));

jest.mock('../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgPrimary: '#F7F6F2',
      bgCard: '#FFFFFF',
      bgElevated: '#FFFFFF',
      fill: '#EBEAE3',
      labelPrimary: '#16201B',
      labelSecondary: '#5B6B63',
      labelTertiary: '#8A968F',
      labelQuaternary: '#B7C0BA',
      separator: 'rgba(22,32,27,0.1)',
      brand: '#1F8A5B',
      brandLight: '#E3F0E9',
    },
    s: jest.requireActual('../../constants/theme').semanticColors,
  }),
}));

import SystemMapScreen from '../system-map';

describe('SystemMapScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders the code-derived system snapshot for the current user', () => {
    const { getByText, getByTestId } = render(<SystemMapScreen />);

    expect(getByText('系统地图')).toBeTruthy();
    expect(getByText('user_id=3')).toBeTruthy();
    expect(getByText('代码派生快照')).toBeTruthy();
    expect(getByTestId('system-map-count-api_routers').props.children).toBe(159);
    expect(getByTestId('system-map-count-mobile_routes').props.children).toBe(92);
    expect(getByText('SafetyGuardianSpecialist')).toBeTruthy();
    expect(getByText('genetic')).toBeTruthy();
  });

  it('goes back through the header control', () => {
    const { getByLabelText } = render(<SystemMapScreen />);

    fireEvent.press(getByLabelText('返回'));

    expect(mockBack).toHaveBeenCalled();
  });
});
