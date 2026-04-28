import React from 'react';
import { render } from '@testing-library/react-native';

jest.mock('../../hooks/useNetworkStatus', () => ({
  useNetworkStatus: jest.fn().mockReturnValue({ isOnline: true }),
}));

import { useNetworkStatus } from '../../hooks/useNetworkStatus';
import NetworkBanner from '../NetworkBanner';

describe('NetworkBanner', () => {
  it('renders nothing when online', () => {
    (useNetworkStatus as jest.Mock).mockReturnValue({ isOnline: true });
    const { queryByTestId } = render(<NetworkBanner />);
    expect(queryByTestId('network-banner')).toBeNull();
  });

  it('shows offline banner when offline', () => {
    (useNetworkStatus as jest.Mock).mockReturnValue({ isOnline: false });
    const { getByTestId, getByText } = render(<NetworkBanner />);
    expect(getByTestId('network-banner')).toBeTruthy();
    expect(getByText('离线模式 — 显示缓存数据')).toBeTruthy();
  });
});
