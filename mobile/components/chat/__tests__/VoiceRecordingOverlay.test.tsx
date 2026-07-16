import React from 'react';
import { render } from '@testing-library/react-native';
import { VoiceRecordingOverlay } from '../VoiceRecordingOverlay';

describe('VoiceRecordingOverlay', () => {
  it('shows the default send/cancel hint while recording', () => {
    const { getByText } = render(<VoiceRecordingOverlay visible />);
    expect(getByText('松开发送 · 上滑取消')).toBeTruthy();
  });

  it('switches to the cancel state when cancelArmed (上滑取消区激活)', () => {
    const { getByText, queryByText } = render(<VoiceRecordingOverlay visible cancelArmed />);
    expect(getByText('松开取消')).toBeTruthy();
    expect(queryByText('松开发送 · 上滑取消')).toBeNull();
  });

  it('renders up to 3 contextual suggestions and trims blanks', () => {
    const { getByText, queryByText } = render(
      <VoiceRecordingOverlay
        visible
        suggestions={['背部肌肉疼痛的原因有哪些？', '   ', '如何增强背部力量？', '第三条', '第四条应被截断']}
      />,
    );
    expect(getByText('背部肌肉疼痛的原因有哪些？')).toBeTruthy();
    expect(getByText('如何增强背部力量？')).toBeTruthy();
    expect(getByText('第三条')).toBeTruthy();
    expect(queryByText('第四条应被截断')).toBeNull(); // 去空后 slice(0,3)
  });

  it('renders the waveform', () => {
    const { getByLabelText } = render(<VoiceRecordingOverlay visible />);
    expect(getByLabelText('语音波形')).toBeTruthy();
  });

  it('degrades gracefully: real levels / empty suggestions / hidden do not throw', () => {
    expect(() => render(<VoiceRecordingOverlay visible levels={[0.2, 0.9, 0.5, 0.3]} />)).not.toThrow();
    expect(() => render(<VoiceRecordingOverlay visible suggestions={[]} />)).not.toThrow();
    expect(() => render(<VoiceRecordingOverlay visible={false} />)).not.toThrow();
  });
});
