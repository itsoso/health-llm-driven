jest.mock('../api', () => ({
  __esModule: true,
  default: { post: jest.fn(), get: jest.fn() },
}));

import api from '../api';
import {
  abortMealSession,
  appendMealFrame,
  canAttemptRokidMealPhoto,
  confirmMealSession,
  finishMealSession,
  getMealSession,
  mealSessionErrorDetail,
  mealSessionErrorStatus,
  startMealSession,
} from '../mealMonitoring';

const mockedApi = api as jest.Mocked<typeof api>;

describe('services/mealMonitoring', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedApi.post.mockResolvedValue({ data: {} } as never);
    mockedApi.get.mockResolvedValue({ data: {} } as never);
  });

  it('starts a session with mandatory consent and source', async () => {
    await startMealSession({ consent: true, source: 'rokid_glasses' });
    expect(mockedApi.post).toHaveBeenCalledWith('/ambient/meal-sessions', {
      consent: true,
      source: 'rokid_glasses',
      device_type: undefined,
      meta: undefined,
    });
  });

  it('appends exactly one frame with snake_cased payload', async () => {
    await appendMealFrame(9, { imageBase64: 'AAAA', capturedAt: '2026-06-22T00:00:00Z' });
    expect(mockedApi.post).toHaveBeenCalledWith('/ambient/meal-sessions/9/frames', {
      image_base64: 'AAAA',
      image_uri: undefined,
      captured_at: '2026-06-22T00:00:00Z',
      recognition_result: undefined,
      meta: undefined,
    });
  });

  it('posts finish / confirm / abort / get to the right paths', async () => {
    await finishMealSession(9);
    await confirmMealSession(9, { mealType: 'dinner' });
    await abortMealSession(9);
    await getMealSession(9);

    expect(mockedApi.post).toHaveBeenCalledWith('/ambient/meal-sessions/9/finish', {});
    expect(mockedApi.post).toHaveBeenCalledWith('/ambient/meal-sessions/9/confirm', {
      confirm: true,
      meal_type: 'dinner',
    });
    expect(mockedApi.post).toHaveBeenCalledWith('/ambient/meal-sessions/9/abort', {});
    expect(mockedApi.get).toHaveBeenCalledWith('/ambient/meal-sessions/9');
  });

  it('reads HTTP status and detail off axios-shaped errors', () => {
    const err = { response: { status: 429, data: { detail: '今天的次数已达上限' } } };
    expect(mealSessionErrorStatus(err)).toBe(429);
    expect(mealSessionErrorDetail(err)).toBe('今天的次数已达上限');
    expect(mealSessionErrorStatus(new Error('boom'))).toBeUndefined();
    expect(mealSessionErrorDetail(new Error('boom'))).toBe('boom');
  });

  it('treats CustomView running as diagnostic, not a hard blocker for Rokid meal photos', () => {
    expect(canAttemptRokidMealPhoto({
      platform: 'ios',
      bridgeAvailable: true,
      sdkLinked: true,
      authorizationState: 'authenticated',
      iosBleConnected: true,
      customViewRunning: false,
    })).toBe(true);
  });

  it('blocks Rokid meal photos only on hard native preconditions', () => {
    expect(canAttemptRokidMealPhoto({ platform: 'android', sdkLinked: true, iosBleConnected: true })).toBe(false);
    expect(canAttemptRokidMealPhoto({ platform: 'ios', sdkLinked: false, iosBleConnected: true })).toBe(false);
    expect(canAttemptRokidMealPhoto({ platform: 'ios', sdkLinked: true, iosBleConnected: false })).toBe(false);
    expect(canAttemptRokidMealPhoto({
      platform: 'ios',
      sdkLinked: true,
      authorizationState: 'not_authenticated',
      iosBleConnected: true,
    })).toBe(false);
  });
});
