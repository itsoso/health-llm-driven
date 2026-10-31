/* eslint-disable import/first */
import React from 'react';
import { Alert } from 'react-native';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

jest.mock('../../../services/records', () => ({
  __esModule: true,
  updateCheckin: jest.fn(),
  createNasalWashRequest: jest.fn(() => ({ event_id: 'event-test', count: 1, record_date: '2026-10-31' })),
  recordNasalWash: jest.fn(),
}));

import { updateCheckin, recordNasalWash } from '../../../services/records';
import RhinitisCard from '../RhinitisCard';

const mockRecordNasalWash = recordNasalWash as jest.Mock;
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
    mockRecordNasalWash.mockResolvedValueOnce({});
    const onUpdate = jest.fn();
    const { getByText } = render(
      <RhinitisCard checkin={{ nasal_wash_count: 2 }} onUpdate={onUpdate} />,
    );

    fireEvent.press(getByText('洗鼻'));

    await waitFor(() => {
      expect(mockRecordNasalWash).toHaveBeenCalledWith({ event_id: 'event-test', count: 1, record_date: '2026-10-31' });
      expect(mockUpdateCheckin).not.toHaveBeenCalled();
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

it('reuses the same wash request after an uncertain failure', async () => {
  mockRecordNasalWash.mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce({});
  const onUpdate = jest.fn();
  const { getByText } = render(<RhinitisCard checkin={{ nasal_wash_count: 9 }} onUpdate={onUpdate} />);
  fireEvent.press(getByText('洗鼻'));
  await waitFor(() => expect(Alert.alert).toHaveBeenCalled());
  fireEvent.press(getByText('洗鼻'));
  await waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1));
  expect(mockRecordNasalWash.mock.calls[1][0]).toBe(mockRecordNasalWash.mock.calls[0][0]);
});
