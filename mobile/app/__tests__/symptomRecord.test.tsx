import React from 'react';
import { Alert } from 'react-native';
import { fireEvent, render, waitFor } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockReplace = jest.fn();
jest.mock('expo-router', () => ({
  router: { back: () => mockBack(), replace: (...a: any[]) => mockReplace(...a) },
}));

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  notificationAsync: jest.fn(),
  ImpactFeedbackStyle: { Light: 'light', Medium: 'medium' },
  NotificationFeedbackType: { Success: 'success' },
}));

const mockCreate = jest.fn().mockResolvedValue({});
jest.mock('../../services/symptoms', () => ({
  createSymptom: (...a: any[]) => mockCreate(...a),
  BODY_PARTS: [
    { value: 'eye', label: '眼睛', emoji: '👁' },
    { value: 'knee', label: '膝盖', emoji: '🦵' },
  ],
}));

jest.mock('../../services/clientEvents', () => ({ emitClientEvent: jest.fn() }));
jest.mock('../../components/agent/AgentFeedbackLink', () => () => null);
jest.mock('../../utils/agentContext', () => ({ createSymptomAgentContext: () => ({}) }));

jest.mock('../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgPrimary: '#000', bgCard: '#1C1C1E', brand: '#0A8F8F', brandLight: '#123',
      labelPrimary: '#fff', labelSecondary: '#aaa', labelTertiary: '#777',
      labelQuaternary: '#48484A', separator: '#333',
    },
  }),
}));

import SymptomRecordScreen from '../symptom-record';

describe('SymptomRecordScreen save/voice placement', () => {
  beforeEach(() => jest.clearAllMocks());

  it('puts 保存 in the bottom CTA and a mic button in the header', () => {
    const { getByText, getByLabelText } = render(<SymptomRecordScreen />);
    expect(getByText('保存')).toBeTruthy();        // 底部大按钮
    expect(getByLabelText('语音记录')).toBeTruthy(); // 右上角图标
  });

  it('saves the symptom from the bottom CTA once a part + description exist', async () => {
    const { getByText, getByPlaceholderText } = render(<SymptomRecordScreen />);
    fireEvent.press(getByText('眼睛'));
    fireEvent.changeText(getByPlaceholderText(/眼睛痒/), '眼睛痒');
    fireEvent.press(getByText('保存'));
    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({ body_part: 'eye', description: '眼睛痒', source: 'manual' }),
    );
  });

  it('does not save when nothing is filled (CTA disabled)', () => {
    const { getByText } = render(<SymptomRecordScreen />);
    fireEvent.press(getByText('保存'));
    expect(mockCreate).not.toHaveBeenCalled();
  });

  it('confirms before voice switch when data is already entered (avoid data loss)', () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    const { getByText, getByLabelText } = render(<SymptomRecordScreen />);
    fireEvent.press(getByText('眼睛'));
    fireEvent.press(getByLabelText('语音记录'));
    expect(alertSpy).toHaveBeenCalled();      // 弹确认, 不直接跳走
    expect(mockReplace).not.toHaveBeenCalled();
    alertSpy.mockRestore();
  });

  it('goes straight to voice when nothing entered', () => {
    const { getByLabelText } = render(<SymptomRecordScreen />);
    fireEvent.press(getByLabelText('语音记录'));
    expect(mockReplace).toHaveBeenCalledWith('/voice-chat?intent=journal');
  });
});
