import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

import AppLockScreen from '../AppLockScreen';

jest.mock('../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgPrimary: '#fff',
      brand: '#0A8F8F',
      labelPrimary: '#111',
    },
  }),
}));

describe('AppLockScreen', () => {
  it('uses 小巴健康 as the locked app brand name', () => {
    const onUnlock = jest.fn();
    const { getByText, queryByText } = render(<AppLockScreen onUnlock={onUnlock} />);

    expect(getByText('小巴健康')).toBeTruthy();
    expect(queryByText('HealthPilot')).toBeNull();

    fireEvent.press(getByText('解锁'));
    expect(onUnlock).toHaveBeenCalledTimes(1);
  });
});
