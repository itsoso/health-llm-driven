import Voice from '@react-native-voice/voice';
import {
  bindVoiceEventHandlers,
  releaseVoiceEventHandlers,
  resetVoiceEventRouterForTests,
} from '../voiceEventRouter';

jest.mock('@react-native-voice/voice', () => ({
  __esModule: true,
  default: {},
}));

const mockedVoice = Voice as any;

describe('voiceEventRouter', () => {
  beforeEach(() => {
    resetVoiceEventRouterForTests();
  });

  it('routes singleton native events only to the newest active voice session', () => {
    const oldResults = jest.fn();
    const nextResults = jest.fn();
    const oldLease = bindVoiceEventHandlers({ onSpeechResults: oldResults });

    mockedVoice.onSpeechResults({ value: ['old'] });
    expect(oldResults).toHaveBeenCalledTimes(1);

    const nextLease = bindVoiceEventHandlers({ onSpeechResults: nextResults });
    mockedVoice.onSpeechResults({ value: ['new'] });
    expect(oldResults).toHaveBeenCalledTimes(1);
    expect(nextResults).toHaveBeenCalledWith({ value: ['new'] });

    releaseVoiceEventHandlers(oldLease);
    mockedVoice.onSpeechResults({ value: ['still-new'] });
    expect(nextResults).toHaveBeenLastCalledWith({ value: ['still-new'] });

    releaseVoiceEventHandlers(nextLease);
    mockedVoice.onSpeechResults({ value: ['ignored'] });
    expect(nextResults).toHaveBeenCalledTimes(2);
  });
});
