import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

jest.mock('expo-document-picker', () => ({
  getDocumentAsync: jest.fn(),
}));
jest.mock('expo-image-picker', () => ({
  requestCameraPermissionsAsync: jest.fn(),
  requestMediaLibraryPermissionsAsync: jest.fn(),
  launchCameraAsync: jest.fn(),
  launchImageLibraryAsync: jest.fn(),
}));
jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  notificationAsync: jest.fn(),
  ImpactFeedbackStyle: { Light: 'light' },
  NotificationFeedbackType: { Success: 'success' },
}));
jest.mock('../../../services/medicalExams', () => ({
  previewMedicalExamAsset: jest.fn(),
  confirmMedicalExamPreview: jest.fn(),
}));

import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import {
  previewMedicalExamAsset,
  confirmMedicalExamPreview,
} from '../../../services/medicalExams';
import MedicalExamImportFlow from '../MedicalExamImportFlow';

const preview = {
  source: 'pdf' as const,
  fileName: '体检.pdf',
  exam_date: '2026-07-29',
  exam_type: 'biochemistry',
  hospital_name: '测试医院',
  conclusions: [],
  items: [{ item_name: 'ALT', value: 25, unit: 'U/L', is_abnormal: 'normal' }],
};

describe('MedicalExamImportFlow', () => {
  beforeEach(() => jest.clearAllMocks());

  it('previews before it persists and confirms only after user action', async () => {
    (DocumentPicker.getDocumentAsync as jest.Mock).mockResolvedValue({
      canceled: false,
      assets: [{ uri: 'file:///tmp/report.pdf', name: '体检.pdf', mimeType: 'application/pdf' }],
    });
    (previewMedicalExamAsset as jest.Mock).mockResolvedValue(preview);
    (confirmMedicalExamPreview as jest.Mock).mockResolvedValue({ examId: 88 });
    const onImported = jest.fn();

    const screen = render(
      <MedicalExamImportFlow visible onClose={jest.fn()} onImported={onImported} />,
    );
    fireEvent.press(screen.getByText('选择报告文件'));

    await waitFor(() => expect(screen.getByText('核对报告')).toBeTruthy());
    expect(confirmMedicalExamPreview).not.toHaveBeenCalled();

    fireEvent.press(screen.getByText('确认保存'));
    await waitFor(() => expect(confirmMedicalExamPreview).toHaveBeenCalledTimes(1));
    expect(onImported).toHaveBeenCalledWith({ examId: 88 });
  });

  it('keeps the selected file and offers inline retry after parsing fails', async () => {
    (DocumentPicker.getDocumentAsync as jest.Mock).mockResolvedValue({
      canceled: false,
      assets: [{ uri: 'file:///tmp/report.pdf', name: '体检.pdf', mimeType: 'application/pdf' }],
    });
    (previewMedicalExamAsset as jest.Mock).mockRejectedValue(new Error('解析服务暂不可用'));

    const screen = render(
      <MedicalExamImportFlow visible onClose={jest.fn()} onImported={jest.fn()} />,
    );
    fireEvent.press(screen.getByText('选择报告文件'));

    await waitFor(() => expect(screen.getByText('解析服务暂不可用')).toBeTruthy());
    expect(screen.getByText('体检.pdf')).toBeTruthy();
    expect(screen.getByText('重新解析')).toBeTruthy();
    expect(screen.getByText('更换报告')).toBeTruthy();
  });

  it('shows camera picker failures inline instead of dropping the flow', async () => {
    (ImagePicker.requestCameraPermissionsAsync as jest.Mock).mockResolvedValue({
      granted: true,
    });
    (ImagePicker.launchCameraAsync as jest.Mock).mockRejectedValue(
      new Error('相机暂不可用'),
    );

    const screen = render(
      <MedicalExamImportFlow visible onClose={jest.fn()} onImported={jest.fn()} />,
    );
    fireEvent.press(screen.getByText('拍摄报告'));

    await waitFor(() => expect(screen.getByText('相机暂不可用')).toBeTruthy());
    expect(screen.getByText('选择报告文件')).toBeTruthy();
  });
});
