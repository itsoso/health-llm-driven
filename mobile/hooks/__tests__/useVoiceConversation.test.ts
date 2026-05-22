import { act, renderHook, waitFor } from '@testing-library/react-native';
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
      setTimeout(() => cb({ didJustFinish: true }), 0);
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

describe('useVoiceConversation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
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
});
