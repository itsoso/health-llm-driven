/* eslint-disable import/first */
import React from 'react';
import { Alert } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';

const mockExportData = jest.fn();
const mockRestoreData = jest.fn();
const mockDeleteLocalData = jest.fn();
const mockShare = jest.fn();
const mockClipboard = jest.fn();

jest.mock('@expo/vector-icons', () => ({ Ionicons: () => null }));
jest.mock('expo-sharing', () => ({
  isAvailableAsync: jest.fn().mockResolvedValue(true),
  shareAsync: (...args: unknown[]) => mockShare(...args),
}));
jest.mock('expo-clipboard', () => ({
  setStringAsync: (...args: unknown[]) => mockClipboard(...args),
}));
jest.mock('expo-document-picker', () => ({
  getDocumentAsync: jest.fn().mockResolvedValue({
    canceled: false,
    assets: [{ uri: 'file:///private/restore.json', name: 'restore.json' }],
  }),
}));
jest.mock('../../../services/localDataLifecycle', () => ({
  LocalDataLifecycle: jest.fn().mockImplementation(() => ({
    exportData: (...args: unknown[]) => mockExportData(...args),
    restoreData: (...args: unknown[]) => mockRestoreData(...args),
  })),
}));
jest.mock('../../../hooks/useAppSession', () => ({
  useAppSession: () => ({
    session: { mode: 'strict_local', localIdentityId: 'local-owner' },
    deleteLocalData: mockDeleteLocalData,
  }),
}));

import LocalDataScreen from '../LocalDataScreen';

describe('LocalDataScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockExportData.mockResolvedValue({
      fileUri: 'file:///private/export.json',
      recoveryKey: 'a'.repeat(43) + '=',
    });
    mockRestoreData.mockResolvedValue(undefined);
    mockDeleteLocalData.mockResolvedValue(undefined);
  });

  it('presents backup file and key separately and copies only after an explicit tap', async () => {
    const screen = render(<LocalDataScreen onBack={jest.fn()} />);

    fireEvent.press(screen.getByText('创建加密备份'));
    await waitFor(() => expect(screen.getByText('a'.repeat(43) + '=')).toBeTruthy());
    expect(mockClipboard).not.toHaveBeenCalled();

    fireEvent.press(screen.getByText('分享恢复文件'));
    await waitFor(() => expect(mockShare).toHaveBeenCalledWith(
      'file:///private/export.json',
      expect.objectContaining({ mimeType: 'application/json' }),
    ));
    expect(mockClipboard).not.toHaveBeenCalled();

    fireEvent.press(screen.getByText('复制恢复密钥'));
    await waitFor(() => expect(mockClipboard).toHaveBeenCalledWith('a'.repeat(43) + '='));
  });

  it('restores a selected file only after the user enters its separate key', async () => {
    const screen = render(<LocalDataScreen onBack={jest.fn()} />);

    fireEvent.press(screen.getByText('选择恢复文件'));
    await waitFor(() => expect(screen.getByText('restore.json')).toBeTruthy());
    fireEvent.changeText(screen.getByPlaceholderText('粘贴 44 位恢复密钥'), 'b'.repeat(43) + '=');
    fireEvent.press(screen.getByText('恢复到空保险库'));

    await waitFor(() => expect(mockRestoreData).toHaveBeenCalledWith(
      'file:///private/restore.json',
      'b'.repeat(43) + '=',
    ));
  });

  it('requires a destructive confirmation before crypto-shredding the vault', async () => {
    const alert = jest.spyOn(Alert, 'alert').mockImplementation(
      (_title, _message, buttons) => {
        const destructive = buttons?.find((button) => button.style === 'destructive');
        destructive?.onPress?.();
      },
    );
    const screen = render(<LocalDataScreen onBack={jest.fn()} />);

    await act(async () => {
      fireEvent.press(screen.getByText('删除本机全部数据'));
    });

    expect(alert).toHaveBeenCalled();
    expect(mockDeleteLocalData).toHaveBeenCalledTimes(1);
  });

  it('does not claim data was retained after crypto-shred when only preference cleanup fails', async () => {
    jest.spyOn(Alert, 'alert').mockImplementation((_title, _message, buttons) => {
      buttons?.find((button) => button.style === 'destructive')?.onPress?.();
    });
    mockDeleteLocalData.mockRejectedValue(
      new Error('local_data_deleted_preference_cleanup_failed'),
    );
    const screen = render(<LocalDataScreen onBack={jest.fn()} />);

    fireEvent.press(screen.getByText('删除本机全部数据'));

    await waitFor(() => expect(screen.getByText(
      '本地数据已删除，但运行模式配置未能重置。请重启 App 后再试。',
    )).toBeTruthy());
  });
});
