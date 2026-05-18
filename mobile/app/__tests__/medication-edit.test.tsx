/* eslint-disable import/first */
import React from 'react';
import { fireEvent, waitFor } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockGetMedication = jest.fn();
const mockUpdateMedication = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: mockBack }),
  useLocalSearchParams: () => ({ id: '1' }),
}));

jest.mock('../../services/medications', () => ({
  getMedication: (...args: any[]) => mockGetMedication(...args),
  updateMedication: (...args: any[]) => mockUpdateMedication(...args),
}));

import MedicationEditScreen from '../medication-edit';
import { renderWithProviders } from '../../test-utils';

describe('MedicationEditScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetMedication.mockResolvedValue({
      id: 1,
      name: '二甲双胍',
      dosage: '500mg',
      frequency: '每日 2 次',
      purpose: '控糖',
      notes: null,
      is_active: true,
    });
    mockUpdateMedication.mockResolvedValue({ id: 1, name: '二甲双胍缓释' });
  });

  it('loads medication details and saves updates', async () => {
    const screen = renderWithProviders(<MedicationEditScreen />);

    await waitFor(() => {
      expect(mockGetMedication).toHaveBeenCalledWith(1);
    });

    await waitFor(() => {
      expect(screen.getByLabelText('药品名称')).toBeTruthy();
    });

    fireEvent.changeText(screen.getByLabelText('药品名称'), '二甲双胍缓释');
    fireEvent.press(screen.getByLabelText('保存药品'));

    await waitFor(() => {
      expect(mockUpdateMedication).toHaveBeenCalledWith(1, expect.objectContaining({ name: '二甲双胍缓释' }));
    });
    expect(mockBack).toHaveBeenCalled();
  });

  it('shows an error state and retries when loading fails', async () => {
    mockGetMedication
      .mockRejectedValueOnce(new Error('network error'))
      .mockResolvedValueOnce({
        id: 1,
        name: '二甲双胍',
        dosage: '500mg',
        frequency: '每日 2 次',
        purpose: '控糖',
        notes: null,
        is_active: true,
      });

    const screen = renderWithProviders(<MedicationEditScreen />);

    await waitFor(() => {
      expect(mockGetMedication).toHaveBeenCalledWith(1);
    });

    await waitFor(() => {
      expect(screen.getByText('加载失败')).toBeTruthy();
    });

    fireEvent.press(screen.getByLabelText('重试加载'));

    await waitFor(() => {
      expect(mockGetMedication).toHaveBeenCalledTimes(2);
    });

    await waitFor(() => {
      expect(screen.getByLabelText('药品名称')).toBeTruthy();
    });
  });
});
