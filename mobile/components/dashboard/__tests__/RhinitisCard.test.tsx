import React from 'react';
import { Alert } from 'react-native';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

jest.mock('../../../services/records', () => ({
  __esModule: true,
  updateCheckin: jest.fn(),
}));

import { updateCheckin } from '../../../services/records';
import RhinitisCard from '../RhinitisCard';

const mockUpdateCheckin = updateCheckin as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
  jest.spyOn(Alert, 'alert').mockImplementation(() => {});
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe('RhinitisCard', () => {
  it('does not present app-authored prescription names or doses', () => {
    const { queryByText } = render(<RhinitisCard checkin={{}} />);

    expect(queryByText('莫米松')).toBeNull();
    expect(queryByText('异丙托')).toBeNull();
    expect(queryByText('每侧2喷')).toBeNull();
  });

  it('opens the user medication manager without creating or logging medicine', () => {
    const onManageMedications = jest.fn();
    const { getByText } = render(
      <RhinitisCard checkin={{}} onManageMedications={onManageMedications} />,
    );

    fireEvent.press(getByText('用药管理'));

    expect(onManageMedications).toHaveBeenCalledTimes(1);
  });

  it('updates the nasal wash count and refreshes after success', async () => {
    mockUpdateCheckin.mockResolvedValueOnce({});
    const onUpdate = jest.fn();
    const { getByText } = render(
      <RhinitisCard checkin={{ nasal_wash_count: 2 }} onUpdate={onUpdate} />,
    );

    fireEvent.press(getByText('洗鼻'));

    await waitFor(() => {
      expect(mockUpdateCheckin).toHaveBeenCalledWith('nasal_wash_count', 3);
      expect(onUpdate).toHaveBeenCalledTimes(1);
    });
  });

  it('shows a retryable error and does not refresh when a check-in fails', async () => {
    mockUpdateCheckin.mockRejectedValueOnce(new Error('network'));
    const onUpdate = jest.fn();
    const { getByText } = render(
      <RhinitisCard checkin={{ sneeze_count: 1 }} onUpdate={onUpdate} />,
    );

    fireEvent.press(getByText('喷嚏'));

    await waitFor(() => {
      expect(Alert.alert).toHaveBeenCalledWith('记录失败', '请检查网络后重试。');
    });
    expect(onUpdate).not.toHaveBeenCalled();
  });
});
