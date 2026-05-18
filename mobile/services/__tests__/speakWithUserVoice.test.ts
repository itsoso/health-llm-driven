import { speakWithUserVoice } from '../speakWithUserVoice';
import { synthesize as cloudSynthesize } from '../cloudTts';
import { splitTextForCloudTts } from '../../utils/ttsText';

const mockSpeechSpeak = jest.fn();
const mockSpeechStop = jest.fn();
const mockPlayerPlay = jest.fn();
const mockPlayerPause = jest.fn();
const mockPlayerRemove = jest.fn();

jest.mock('expo-speech', () => ({
  speak: (...args: any[]) => mockSpeechSpeak(...args),
  stop: (...args: any[]) => mockSpeechStop(...args),
  getAvailableVoicesAsync: jest.fn().mockResolvedValue([]),
}));

jest.mock('expo-audio', () => ({
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

jest.mock('../voiceStyle', () => {
  return {
    loadVoiceStyle: jest.fn().mockResolvedValue('cloud_cloned_private_female'),
    getVoiceStyle: jest.fn(() => ({
      key: 'cloud_cloned_private_female',
      provider: 'cloud',
      label: '私享女声',
      description: '专属声音复刻',
      cloudVoiceKey: 'cloned_private_female',
    })),
    resolveIosSpeechOptions: jest.fn().mockResolvedValue({
      language: 'zh-CN',
      rate: 1.0,
      pitch: 1.0,
    }),
  };
});

jest.mock('../cloudTts', () => ({
  synthesize: jest.fn().mockResolvedValue({ localUri: 'file://tts.mp3', bytes: 1000 }),
}));

const mockCloudSynthesize = cloudSynthesize as jest.MockedFunction<typeof cloudSynthesize>;

describe('speakWithUserVoice', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('submits long private coach replies to cloud TTS as backend-safe chunks', async () => {
    const longText = Array.from({ length: 35 }, (_, i) => (
      `第${i + 1}段：结合你的体检、基因、运动和睡眠数据，今天建议优先执行一个明确动作。`
    )).join(' ');

    const expectedChunks = splitTextForCloudTts(longText);
    expect(expectedChunks.length).toBeGreaterThan(1);

    const handle = await speakWithUserVoice(longText);
    await new Promise(resolve => setTimeout(resolve, 100));

    expect(handle.cancel).toEqual(expect.any(Function));
    expect(mockCloudSynthesize).toHaveBeenCalled();
    expect(mockCloudSynthesize.mock.calls.every(([arg]) => arg.text.length <= 480)).toBe(true);
    expect(mockCloudSynthesize.mock.calls[0][0].text).toBe(expectedChunks[0]);
    expect(mockSpeechSpeak).not.toHaveBeenCalled();
  });
});
