/* eslint-disable import/first */
import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

const applyUpdate = jest.fn();
const dismiss = jest.fn();

jest.mock('../../../hooks/useAppUpdate', () => ({
  useAppUpdate: jest.fn(),
}));

import { useAppUpdate } from '../../../hooks/useAppUpdate';
import AppUpdateBanner from '../AppUpdateBanner';

describe('AppUpdateBanner', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (useAppUpdate as jest.Mock).mockReturnValue({
      status: 'idle',
      isForced: false,
      applyUpdate,
      dismiss,
    });
  });

  it('stays hidden until an update is ready', () => {
    const { queryByTestId } = render(<AppUpdateBanner />);
    expect(queryByTestId('app-update-banner')).toBeNull();
  });

  it('offers explicit apply and dismiss actions for a ready update', () => {
    (useAppUpdate as jest.Mock).mockReturnValue({ status: 'ready', isForced: false, applyUpdate, dismiss });
    const { getByText, getByTestId } = render(<AppUpdateBanner />);

    expect(getByTestId('app-update-banner')).toBeTruthy();
    fireEvent.press(getByText('立即更新'));
    fireEvent.press(getByText('稍后'));

    expect(applyUpdate).toHaveBeenCalledTimes(1);
    expect(dismiss).toHaveBeenCalledTimes(1);
  });

  it('does not offer a dismiss action for a forced update', () => {
    (useAppUpdate as jest.Mock).mockReturnValue({ status: 'ready', isForced: true, applyUpdate, dismiss });
    const { getByText, queryByText } = render(<AppUpdateBanner />);

    expect(getByText('请完成应用更新')).toBeTruthy();
    expect(queryByText('稍后')).toBeNull();
  });
});
