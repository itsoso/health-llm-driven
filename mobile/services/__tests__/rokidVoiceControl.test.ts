jest.mock('../../modules/rokid-bridge', () => ({
  startRokidRecord: jest.fn(),
  stopRokidRecord: jest.fn(),
}));

jest.mock('../api', () => ({
  __esModule: true,
  default: {
    post: jest.fn(),
  },
}));

import { startRokidRecord, stopRokidRecord } from '../../modules/rokid-bridge';
import api from '../api';
import {
  executeRokidVoiceClientAction,
  startRokidVoiceCommandCapture,
  stopRokidVoiceCommandCapture,
  submitRokidVoiceCommand,
} from '../rokidVoiceControl';

const mockedApi = api as jest.Mocked<typeof api>;
const mockStartRokidRecord = startRokidRecord as jest.MockedFunction<typeof startRokidRecord>;
const mockStopRokidRecord = stopRokidRecord as jest.MockedFunction<typeof stopRokidRecord>;

describe('services/rokidVoiceControl', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('starts and stops a bounded Rokid voice command recording session', async () => {
    mockStartRokidRecord.mockResolvedValueOnce({ ok: true } as never);
    mockStopRokidRecord.mockResolvedValueOnce({ ok: true } as never);

    await startRokidVoiceCommandCapture();
    await stopRokidVoiceCommandCapture();

    expect(mockStartRokidRecord).toHaveBeenCalledWith({
      type: 'reva_voice_command',
      codec: 'pcm',
      mode: 'rokidOmni',
    });
    expect(mockStopRokidRecord).toHaveBeenCalledWith('reva_voice_command');
  });

  it('submits a Rokid transcript to the command router endpoint', async () => {
    mockedApi.post.mockResolvedValueOnce({
      data: { command: { intent: 'food_photo', client_action: 'capture_food_photo' } },
    } as never);

    await submitRokidVoiceCommand({
      transcript: '拍一下这餐',
      confidence: 0.92,
      context: 'rokid_health',
    });

    expect(mockedApi.post).toHaveBeenCalledWith('/ambient/rokid-voice-commands', {
      transcript: '拍一下这餐',
      confidence: 0.92,
      context: 'rokid_health',
      captured_at: undefined,
      privacy_class: 'health_l3',
      meta: undefined,
    });
  });

  it('executes only whitelisted client actions from the backend command response', async () => {
    const handlers = {
      captureFoodPhoto: jest.fn().mockResolvedValue(undefined),
      openPushupCoach: jest.fn().mockResolvedValue(undefined),
      openGuidedTask: jest.fn().mockResolvedValue(undefined),
    };

    await executeRokidVoiceClientAction(
      { command: { client_action: 'capture_food_photo', route: null, parameters: { visual_intent: 'food_scan' } } },
      handlers,
    );
    await executeRokidVoiceClientAction(
      { command: { client_action: 'open_pushup_coach', route: '/rokid-pushup-coach', parameters: { target_reps: 20 } } },
      handlers,
    );
    await executeRokidVoiceClientAction(
      { command: { client_action: 'open_guided_task', route: '/guided-task?domain=strength&source=rokid_voice' } },
      handlers,
    );
    await executeRokidVoiceClientAction(
      { command: { client_action: 'unsupported_action', route: '/admin' } },
      handlers,
    );

    expect(handlers.captureFoodPhoto).toHaveBeenCalledWith({ visualIntent: 'food_scan' });
    expect(handlers.openPushupCoach).toHaveBeenCalledWith({ targetReps: 20, route: '/rokid-pushup-coach' });
    expect(handlers.openGuidedTask).toHaveBeenCalledWith({ route: '/guided-task?domain=strength&source=rokid_voice' });
    expect(handlers.captureFoodPhoto).toHaveBeenCalledTimes(1);
    expect(handlers.openPushupCoach).toHaveBeenCalledTimes(1);
    expect(handlers.openGuidedTask).toHaveBeenCalledTimes(1);
  });
});
