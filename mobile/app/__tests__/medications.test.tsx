/* eslint-disable import/first */
import React from 'react';
import { fireEvent, waitFor } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockPush = jest.fn();
const mockListMedications = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: mockBack, push: mockPush }),
}));

jest.mock('../../services/medications', () => ({
  listMedications: (...args: any[]) => mockListMedications(...args),
  deactivateMedication: jest.fn(),
  restoreMedication: jest.fn(),
}));

import MedicationsScreen from '../medications';
import { renderWithProviders } from '../../test-utils';

describe('MedicationsScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockListMedications.mockResolvedValue([
      {
        id: 1,
        name: '二甲双胍',
        dosage: '500mg',
        frequency: '每日 2 次',
        purpose: '控糖',
        is_active: true,
      },
    ]);
  });

  it('navigates to edit screen when a medication row is pressed', async () => {
    const screen = renderWithProviders(<MedicationsScreen />);

    await waitFor(() => {
      expect(screen.getByText('二甲双胍')).toBeTruthy();
    });

    fireEvent.press(screen.getByLabelText('编辑 二甲双胍'));

    expect(mockPush).toHaveBeenCalledWith('/medication-edit?id=1');
  });
});
