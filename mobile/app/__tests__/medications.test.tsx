/* eslint-disable import/first */
import React from 'react';
import { Alert } from 'react-native';
import { fireEvent, waitFor } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockPush = jest.fn();
const mockListMedications = jest.fn();
const mockAddMedication = jest.fn();
const mockLogMedication = jest.fn();
const mockDeactivateMedication = jest.fn();
beforeEach(() => { jest.clearAllMocks(); });
let mockParams: Record<string, string | undefined> = {};

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: mockBack, push: mockPush }),
  useLocalSearchParams: () => mockParams,
}));

jest.mock('../../services/medications', () => ({
  listMedications: (...args: any[]) => mockListMedications(...args),
  addMedication: (...args: any[]) => mockAddMedication(...args),
  logMedication: (...args: any[]) => mockLogMedication(...args),
  deactivateMedication: (...args: any[]) => mockDeactivateMedication(...args),
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
      expect(screen.getByText('小气候识别到用药草稿')).toBeTruthy();
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


it('offers a permanent reminder entry without inferring a dose slot', async () => {
  mockParams = {}; mockListMedications.mockResolvedValue([{ id: 7, name: '药品甲', is_active: true }]);
  const screen = renderWithProviders(<MedicationsScreen />);
  await waitFor(() => expect(screen.getByLabelText('查看 药品甲 的提醒')).toBeTruthy());
  fireEvent.press(screen.getByLabelText('查看 药品甲 的提醒'));
  expect(mockPush).toHaveBeenCalledWith('/medication-reminder?id=7');
});

it('does not turn reminder instructions into a confirmable intake draft', async () => {
  mockParams = { draft: 'medication', name: '提醒 先查询核实药品、计划时间和记录状态 不要记录服药' };
  const screen = renderWithProviders(<MedicationsScreen />);
  await waitFor(() => expect(screen.getByText('这条内容需要核对')).toBeTruthy());
  expect(screen.queryByLabelText('确认记录用药')).toBeNull();
  expect(mockAddMedication).not.toHaveBeenCalled();
  expect(mockLogMedication).not.toHaveBeenCalled();
});

it('labels reminder actions and keeps stop actions behind a menu', async () => {
  mockParams = {};
  mockListMedications.mockResolvedValue([{ id: 7, name: '药品甲', dosage: '50mg', frequency: 'daily', is_active: true }]);
  const screen = renderWithProviders(<MedicationsScreen />);
  await waitFor(() => expect(screen.getByText('每日')).toBeTruthy());
  expect(screen.getByText('提醒与打卡')).toBeTruthy();
  expect(screen.getByLabelText('更多 药品甲 的操作')).toBeTruthy();
});

it('shows a load failure instead of a misleading empty list', async () => {
  mockParams = {};
  mockListMedications.mockRejectedValue(new Error('offline'));
  const screen = renderWithProviders(<MedicationsScreen />);
  await waitFor(() => expect(screen.getByText('暂时无法加载用药清单')).toBeTruthy());
  expect(screen.queryByText('还没有在用药品')).toBeNull();
});


it('keeps instruction-like saved entries editable without offering a reminder', async () => {
  mockParams = {};
  const name = '记录 不要建议我自行停药、换药或改剂量';
  mockListMedications.mockResolvedValue([{ id: 8, name, is_active: true }]);
  const screen = renderWithProviders(<MedicationsScreen />);
  await waitFor(() => expect(screen.getByText('名称待核对')).toBeTruthy());
  expect(screen.queryByLabelText(`查看 ${name} 的提醒`)).toBeNull();
  fireEvent.press(screen.getByLabelText(`编辑 ${name}`));
  expect(mockPush).toHaveBeenCalledWith('/medication-edit?id=8');
  expect(mockDeactivateMedication).not.toHaveBeenCalled();
});

it('does not stop medication when opening the actions menu', async () => {
  mockParams = {};
  mockListMedications.mockResolvedValue([{ id: 8, name: '药品甲', is_active: true }]);
  const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  const screen = renderWithProviders(<MedicationsScreen />);
  await waitFor(() => expect(screen.getByLabelText('更多 药品甲 的操作')).toBeTruthy());
  fireEvent.press(screen.getByLabelText('更多 药品甲 的操作'));
  expect(alert).toHaveBeenCalled();
  expect(mockDeactivateMedication).not.toHaveBeenCalled();
  alert.mockRestore();
});
