import { estimateTtsFallbackMs, shouldFinishAudioPlayback } from '../audioPlayback';

describe('audioPlayback helpers', () => {
  it('treats expo-audio didJustFinish as finished', () => {
    expect(shouldFinishAudioPlayback({ didJustFinish: true })).toBe(true);
  });

  it('treats ended playbackState as finished', () => {
    expect(shouldFinishAudioPlayback({ playbackState: 'ended' })).toBe(true);
  });

  it('treats currentTime near duration as finished', () => {
    expect(shouldFinishAudioPlayback({ currentTime: 9.96, duration: 10 })).toBe(true);
  });

  it('does not finish while audio is still playing', () => {
    expect(shouldFinishAudioPlayback({ currentTime: 3, duration: 10, playing: true })).toBe(false);
  });

  it('uses seconds from audio duration for fallback timeout when available', () => {
    expect(estimateTtsFallbackMs('很短一句话', 12)).toBe(17000);
  });
});
