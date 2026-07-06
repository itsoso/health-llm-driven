/**
 * useVoiceRecording — 按住说话的三条承重路径。
 *
 * 1. 主路径: 端上识别(Voice zh-CN), 备胎录音器不启动, 松手拿最终结果交卷;
 * 2. 备胎: Voice.start 抛错 → 自动降级 expo-audio 录音 + 云端转写;
 * 3. 兜底: stop 后最终结果迟迟不来 → 1.2s 超时拿最新 partial 交卷, 不让用户干等。
 *
 * 背景(2026-07-06): 云端 Whisper 代理 429 时整条语音链路挂死, founder 实锤
 * 「语音识别失败」。端上主路径把云端从关键路径上摘掉, 这些测试守护该结构不回退。
 */
import { act, renderHook, waitFor } from '@testing-library/react-native';
import { Alert } from 'react-native';
import Voice from '@react-native-voice/voice';
import { useVoiceRecording } from '../useVoiceRecording';
import { transcribeAudio } from '../../services/transcribe';

const mockVoiceStart = jest.fn();
const mockVoiceStop = jest.fn().mockResolvedValue(undefined);
const mockVoiceCancel = jest.fn().mockResolvedValue(undefined);

jest.mock('@react-native-voice/voice', () => ({
  __esModule: true,
  // 普通可变对象: hook 直接对 default 赋 onSpeechXxx 回调, 测试经它触发事件。
  default: {
    start: (...args: any[]) => mockVoiceStart(...args),
    stop: (...args: any[]) => mockVoiceStop(...args),
    cancel: (...args: any[]) => mockVoiceCancel(...args),
  },
}));

const mockPrepare = jest.fn().mockResolvedValue(undefined);
const mockRecord = jest.fn();
const mockRecorderStop = jest.fn().mockResolvedValue(undefined);

jest.mock('expo-audio', () => ({
  RecordingPresets: { HIGH_QUALITY: {} },
  setAudioModeAsync: jest.fn().mockResolvedValue(undefined),
  requestRecordingPermissionsAsync: jest.fn().mockResolvedValue({ granted: true }),
  useAudioRecorder: () => ({
    prepareToRecordAsync: (...args: any[]) => mockPrepare(...args),
    record: (...args: any[]) => mockRecord(...args),
    stop: (...args: any[]) => mockRecorderStop(...args),
    uri: 'file://fallback.m4a',
  }),
}));

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn().mockResolvedValue(undefined),
  notificationAsync: jest.fn().mockResolvedValue(undefined),
  ImpactFeedbackStyle: { Medium: 'medium' },
  NotificationFeedbackType: { Success: 'success', Warning: 'warning' },
}));

jest.mock('../../services/transcribe', () => ({
  transcribeAudio: jest.fn().mockResolvedValue('云端转写结果'),
}));

const voiceHandlers = Voice as unknown as {
  onSpeechPartialResults?: (e: any) => void;
  onSpeechResults?: (e: any) => void;
  onSpeechEnd?: (e?: any) => void;
  onSpeechError?: (e?: any) => void;
};

describe('useVoiceRecording', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockVoiceStart.mockResolvedValue(undefined);
    jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  });

  it('主路径: 端上识别, 不碰备胎录音器, partial 实时可见, 松手拿最终结果', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useVoiceRecording({ onTranscript }));

    await act(async () => {
      await result.current.startRecording();
    });

    expect(mockVoiceStart).toHaveBeenCalledWith('zh-CN');
    expect(mockPrepare).not.toHaveBeenCalled();
    expect(result.current.isRecording).toBe(true);

    act(() => {
      voiceHandlers.onSpeechPartialResults?.({ value: ['喝了一杯'] });
    });
    expect(result.current.partialText).toBe('喝了一杯');

    let stopPromise: Promise<void>;
    act(() => {
      stopPromise = result.current.stopAndTranscribe();
      // Voice.stop 后 iOS 送最终结果
      voiceHandlers.onSpeechResults?.({ value: ['喝了一杯水'] });
    });
    await act(async () => { await stopPromise!; });

    expect(onTranscript).toHaveBeenCalledWith('喝了一杯水');
    expect(transcribeAudio).not.toHaveBeenCalled();
    expect(result.current.partialText).toBe('');
  });

  it('备胎: Voice.start 抛错 → 降级录音 + 云端转写', async () => {
    mockVoiceStart.mockRejectedValue(new Error('dictation disabled'));
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useVoiceRecording({ onTranscript }));

    await act(async () => {
      await result.current.startRecording();
    });

    expect(mockPrepare).toHaveBeenCalled();
    expect(mockRecord).toHaveBeenCalled();
    expect(result.current.isRecording).toBe(true);

    await act(async () => {
      await result.current.stopAndTranscribe();
    });

    expect(transcribeAudio).toHaveBeenCalledWith('file://fallback.m4a');
    expect(onTranscript).toHaveBeenCalledWith('云端转写结果');
  });

  it('兜底: 最终结果不来 → 1.2s 超时拿最新 partial 交卷', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useVoiceRecording({ onTranscript }));

    await act(async () => {
      await result.current.startRecording();
    });
    act(() => {
      voiceHandlers.onSpeechPartialResults?.({ value: ['今天走了八千步'] });
    });

    await act(async () => {
      const p = result.current.stopAndTranscribe();
      // 不触发 onSpeechResults —— 只等真实 1.2s 兜底
      await p;
    });

    expect(onTranscript).toHaveBeenCalledWith('今天走了八千步');
    expect(transcribeAudio).not.toHaveBeenCalled();
  }, 10000);

  it('取消: 上滑取消后不产出任何转写', async () => {
    const onTranscript = jest.fn();
    const { result } = renderHook(() => useVoiceRecording({ onTranscript }));

    await act(async () => {
      await result.current.startRecording();
    });
    await act(async () => {
      await result.current.cancelRecording();
    });

    expect(mockVoiceCancel).toHaveBeenCalled();
    expect(onTranscript).not.toHaveBeenCalled();
    await waitFor(() => expect(result.current.isRecording).toBe(false));
  });
});
