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

  it('keeps the editor open and shows medication safety alerts after save', async () => {
    mockGetMedication.mockResolvedValueOnce({
      id: 1,
      name: '卡马西平',
      dosage: '100mg',
      frequency: '每日 1 次',
      purpose: '神经痛',
      notes: null,
      is_active: true,
    });
    mockUpdateMedication.mockResolvedValueOnce({
      id: 1,
      name: '卡马西平',
      safety_alerts: [{
        rule_id: 'pgx.cpic.hla-b_卡马西平',
        category: 'pgx',
        severity: { label: 'critical', label_zh: '紧急', value: 4 },
        title: 'HLA-B × 卡马西平',
        message: '携带 HLA-B 风险等位基因时，卡马西平相关严重皮肤不良反应风险升高。',
        action: '请先与医生或药师确认，不要自行调整用药。',
      }],
    });

    const screen = renderWithProviders(<MedicationEditScreen />);

    await waitFor(() => {
      expect(screen.getByLabelText('药品名称')).toBeTruthy();
    });

    fireEvent.press(screen.getByLabelText('保存药品'));

    await waitFor(() => {
      expect(screen.getByText('HLA-B × 卡马西平')).toBeTruthy();
    });
    expect(screen.getByText('请先与医生或药师确认，不要自行调整用药。')).toBeTruthy();
    expect(mockBack).not.toHaveBeenCalled();
  });

  it('shows medication safety alerts returned by detail loading', async () => {
    mockGetMedication.mockResolvedValueOnce({
      id: 1,
      name: '卡马西平',
      dosage: '100mg',
      frequency: '每日 1 次',
      purpose: '神经痛',
      notes: null,
      is_active: true,
      safety_alerts: [{
        rule_id: 'pgx.cpic.hla-b_卡马西平',
        category: 'pgx',
        severity: { label: 'critical', label_zh: '紧急', value: 4 },
        title: 'HLA-B × 卡马西平',
        message: '携带 HLA-B 风险等位基因时，卡马西平相关严重皮肤不良反应风险升高。',
        action: '请先与医生或药师确认，不要自行调整用药。',
      }],
    });

    const screen = renderWithProviders(<MedicationEditScreen />);

    await waitFor(() => {
      expect(screen.getByText('HLA-B × 卡马西平')).toBeTruthy();
    });
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
