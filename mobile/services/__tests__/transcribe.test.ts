const mockReadAsStringAsync = jest.fn().mockResolvedValue('audio-base64');
const mockPost = jest.fn();

jest.mock('expo-file-system/legacy', () => ({
  readAsStringAsync: (...args: any[]) => mockReadAsStringAsync(...args),
  EncodingType: { Base64: 'base64' },
}));

jest.mock('../api', () => ({
  __esModule: true,
  default: { post: (...args: any[]) => mockPost(...args) },
}));

import { transcribeAudio, transcribeAudioDetailed } from '../transcribe';
import { requireAIConsent } from '../aiConsent';

describe('transcribeAudioDetailed', () => {
  it('does not read or upload voice data when consent is absent', async () => {
    (requireAIConsent as jest.Mock).mockRejectedValueOnce(new Error('ai_consent_required'));
    await expect(transcribeAudioDetailed('file:///draft.m4a')).rejects.toThrow('ai_consent_required');
    expect(mockReadAsStringAsync).not.toHaveBeenCalled();
    expect(mockPost).not.toHaveBeenCalled();
  });
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('returns cloud ASR metadata for voice draft quality and latency tracking', async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        text: '今天 HRV 下降',
        provider: 'openai_whisper',
        model: 'whisper-1',
        duration_ms: 1234,
        confidence: 'medium',
      },
    });

    const result = await transcribeAudioDetailed('file:///tmp/voice.m4a');

    expect(mockPost).toHaveBeenCalledWith('/chat/transcribe', {
      audio_base64: 'audio-base64',
      audio_format: 'm4a',
    });
    expect(result).toEqual({
      text: '今天 HRV 下降',
      provider: 'openai_whisper',
      model: 'whisper-1',
      durationMs: 1234,
      confidence: 'medium',
      empty: false,
    });
  });

  it('keeps the legacy transcribeAudio API returning text only', async () => {
    mockPost.mockResolvedValueOnce({ data: { text: '识别出的文字' } });

    await expect(transcribeAudio('file:///tmp/voice.m4a')).resolves.toBe('识别出的文字');
  });
});
jest.mock('../aiConsent', () => ({ requireAIConsent: jest.fn().mockResolvedValue(undefined) }));
