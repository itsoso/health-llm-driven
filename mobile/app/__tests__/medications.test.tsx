/* eslint-disable import/first */
import React from 'react';
import { fireEvent, waitFor } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockPush = jest.fn();
const mockListMedications = jest.fn();
const mockAddMedication = jest.fn();
const mockLogMedication = jest.fn();
let mockParams: Record<string, string | undefined> = {};

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: mockBack, push: mockPush }),
  useLocalSearchParams: () => mockParams,
}));

jest.mock('../../services/medications', () => ({
  listMedications: (...args: any[]) => mockListMedications(...args),
  addMedication: (...args: any[]) => mockAddMedication(...args),
  logMedication: (...args: any[]) => mockLogMedication(...args),
  deactivateMedication: jest.fn(),
  restoreMedication: jest.fn(),
}));

import MedicationsScreen from '../medications';
import { renderWithProviders } from '../../test-utils';

describe('MedicationsScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockParams = {};
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
    mockAddMedication.mockResolvedValue({ id: 9, name: '替普瑞酮胶囊（施维舒）', is_active: true });
    mockLogMedication.mockResolvedValue({ id: 99, medication_id: 9, status: 'taken' });
  });

  it('navigates to edit screen when a medication row is pressed', async () => {
    const screen = renderWithProviders(<MedicationsScreen />);

    await waitFor(() => {
      expect(screen.getByText('二甲双胍')).toBeTruthy();
    });

    fireEvent.press(screen.getByLabelText('编辑 二甲双胍'));

    expect(mockPush).toHaveBeenCalledWith('/medication-edit?id=1');
  });

  it('turns Xiaoba medication draft route params into an explicit confirmable write', async () => {
    mockParams = {
      draft: 'medication',
      name: '替普瑞酮胶囊（施维舒）',
      dose: '20mg',
    };
    mockListMedications.mockResolvedValue([]);

    const screen = renderWithProviders(<MedicationsScreen />);

    await waitFor(() => {
      expect(screen.getByText('小巴识别到用药草稿')).toBeTruthy();
    });
    expect(screen.getByText('替普瑞酮胶囊（施维舒）')).toBeTruthy();
    expect(screen.getByText('20mg')).toBeTruthy();

    fireEvent.press(screen.getByText('确认记录用药'));

    await waitFor(() => {
      expect(mockAddMedication).toHaveBeenCalledWith(expect.objectContaining({
        name: '替普瑞酮胶囊（施维舒）',
        dosage: '20mg',
      }));
      expect(mockLogMedication).toHaveBeenCalledWith(expect.objectContaining({
        medication_id: 9,
        status: 'taken',
        actual_dosage: '20mg',
      }));
    });
  });
});
