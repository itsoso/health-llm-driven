import { act, renderHook, waitFor } from '@testing-library/react-native';
import Voice from '@react-native-voice/voice';
import { synthesize as cloudSynthesize } from '../../services/cloudTts';
import { splitTextForCloudTts } from '../../utils/ttsText';
import { useVoiceConversation } from '../useVoiceConversation';

const mockSpeechSpeak = jest.fn();
const mockSpeechStop = jest.fn();
const mockVoiceDestroy = jest.fn().mockResolvedValue(undefined);
const mockVoiceRemoveAllListeners = jest.fn();
const mockPlayerPlay = jest.fn();
const mockPlayerPause = jest.fn();
const mockPlayerRemove = jest.fn();
const mockPlaybackCallbacks: ((status: any) => void)[] = [];
let mockAutoFinishPlayback = true;

jest.mock('@react-native-voice/voice', () => ({
  __esModule: true,
  default: {
    destroy: (...args: any[]) => mockVoiceDestroy(...args),
    removeAllListeners: (...args: any[]) => mockVoiceRemoveAllListeners(...args),
    stop: jest.fn().mockResolvedValue(undefined),
    cancel: jest.fn().mockResolvedValue(undefined),
    start: jest.fn().mockResolvedValue(undefined),
  },
}));

jest.mock('expo-speech', () => ({
  speak: (...args: any[]) => mockSpeechSpeak(...args),
  stop: (...args: any[]) => mockSpeechStop(...args),
  getAvailableVoicesAsync: jest.fn().mockResolvedValue([]),
}));

jest.mock('expo-audio', () => ({
  setAudioModeAsync: jest.fn().mockResolvedValue(undefined),
  createAudioPlayer: jest.fn(() => ({
    addListener: jest.fn((_event: string, cb: (status: any) => void) => {
      mockPlaybackCallbacks.push(cb);
      if (mockAutoFinishPlayback) {
        setTimeout(() => cb({ didJustFinish: true }), 0);
      }
      return { remove: jest.fn() };
    }),
    play: (...args: any[]) => mockPlayerPlay(...args),
    pause: (...args: any[]) => mockPlayerPause(...args),
    remove: (...args: any[]) => mockPlayerRemove(...args),
  })),
}));

jest.mock('../../services/voiceStyle', () => ({
  loadVoiceStyle: jest.fn().mockResolvedValue('cloud_cloned_private_female'),
  getVoiceStyle: jest.fn(() => ({
    provider: 'cloud',
    cloudVoiceKey: 'cloned_private_female',
  })),
  resolveIosSpeechOptions: jest.fn().mockResolvedValue({
    language: 'zh-CN',
    rate: 1.0,
    pitch: 1.0,
  }),
}));

jest.mock('../../services/cloudTts', () => ({
  synthesize: jest.fn().mockResolvedValue({ localUri: 'file://tts.mp3', bytes: 1000 }),
  cleanupTmpTts: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('../../services/chat', () => ({
  streamChat: jest.fn(),
  getConversationMessages: jest.fn().mockResolvedValue({ messages: [], total_messages: 0 }),
}));

const mockCloudSynthesize = cloudSynthesize as jest.MockedFunction<typeof cloudSynthesize>;
const mockedVoice = Voice as any;

describe('useVoiceConversation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockPlaybackCallbacks.length = 0;
    mockAutoFinishPlayback = true;
  });

  it('keeps long direct voice-chat scripts on private cloud voice by chunking them safely', async () => {
    const longText = Array.from({ length: 35 }, (_, i) => (
      `第${i + 1}段：结合你的体检、基因、运动和睡眠数据，今天建议优先执行一个明确动作。`
    )).join(' ');
    const expectedChunks = splitTextForCloudTts(longText);

    expect(expectedChunks.length).toBeGreaterThan(1);

    const { result, unmount } = renderHook(() => useVoiceConversation());

    await act(async () => {
      await result.current.speakDirect(longText);
    });

    await waitFor(() => {
      expect(mockCloudSynthesize).toHaveBeenCalled();
    });
    expect(mockCloudSynthesize.mock.calls.every(([arg]) => arg.text.length <= 480)).toBe(true);
    expect(mockCloudSynthesize.mock.calls[0][0].text).toBe(expectedChunks[0]);
    expect(mockSpeechSpeak).not.toHaveBeenCalled();

    unmount();
  });

  it('does not clear process-wide speech listeners when the voice screen closes', async () => {
    const { result, unmount } = renderHook(() => useVoiceConversation());

    await act(async () => {
      await result.current.startListening();
    });
    act(() => {
      mockedVoice.onSpeechPartialResults({ value: ['正在记录这句话'] });
    });
    expect(result.current.transcript).toBe('正在记录这句话');

    await act(async () => {
      unmount();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mockVoiceRemoveAllListeners).not.toHaveBeenCalled();
  });

  it('stops queued playback and never reopens the microphone after unmount', async () => {
    mockAutoFinishPlayback = false;
    const longText = Array.from({ length: 35 }, (_, i) => (
      `第${i + 1}段：离开语音页面后，不应继续播放，也不应重新启动麦克风。`
    )).join(' ');
    expect(splitTextForCloudTts(longText).length).toBeGreaterThan(1);

    const { result, unmount } = renderHook(() => useVoiceConversation());

    act(() => {
      void result.current.speakDirect(longText, { thenListen: true });
    });
    await waitFor(() => {
      expect(mockPlayerPlay).toHaveBeenCalledTimes(1);
    });

    act(() => {
      unmount();
    });
    await new Promise((resolve) => setTimeout(resolve, 350));

    expect(mockPlayerPlay).toHaveBeenCalledTimes(1);
    expect(mockedVoice.start).not.toHaveBeenCalled();
  });
});
