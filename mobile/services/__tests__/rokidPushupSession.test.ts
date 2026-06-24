jest.mock('../api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

import api from '../api';
import {
  applyRokidPushupEventToCoach,
  createRokidPushupSession,
  finishRokidPushupSession,
  listRokidPushupEvents,
  rokidPushupSessionStateMessage,
  rokidPushupEventToPoseSample,
} from '../rokidPushupSession';
import { createPushupCoachState } from '../pushupCoach';

const mockedApi = api as jest.Mocked<typeof api>;

describe('services/rokidPushupSession', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('creates a backend session for glasses-side real pose ingest', async () => {
    mockedApi.post.mockResolvedValueOnce({
      data: {
        id: 7,
        ingest_token: 'one-time-token',
        open_url: 'reva://rokid/pushup?session_id=7',
      },
    } as never);

    await expect(createRokidPushupSession({
      targetReps: 20,
      sourceDevice: 'rokid_glasses_ultra',
      meta: { packageName: 'life.executor.health.rokid.pushup' },
    })).resolves.toMatchObject({
      id: 7,
      ingest_token: 'one-time-token',
    });

    expect(mockedApi.post).toHaveBeenCalledWith('/devices/rokid/pushup-sessions', {
      target_reps: 20,
      source_device: 'rokid_glasses_ultra',
      meta: { packageName: 'life.executor.health.rokid.pushup' },
    });
  });

  it('polls incremental pose events and can finish a session', async () => {
    mockedApi.get.mockResolvedValueOnce({ data: { events: [{ id: 11, event_type: 'pose' }] } } as never);
    mockedApi.post.mockResolvedValueOnce({ data: { session: { id: 7, status: 'finished' } } } as never);

    await expect(listRokidPushupEvents(7, { afterId: 10, limit: 50 })).resolves.toEqual([
      { id: 11, event_type: 'pose' },
    ]);
    await expect(finishRokidPushupSession(7)).resolves.toMatchObject({
      session: { id: 7, status: 'finished' },
    });

    expect(mockedApi.get).toHaveBeenCalledWith('/devices/rokid/pushup-sessions/7/events', {
      params: { after_id: 10, limit: 50 },
    });
    expect(mockedApi.post).toHaveBeenCalledWith('/devices/rokid/pushup-sessions/7/finish');
  });

  it('converts backend pose events into pushup coach samples', () => {
    const sample = rokidPushupEventToPoseSample({
      id: 11,
      session_id: 7,
      user_id: 1,
      event_type: 'pose',
      reps: 0,
      phase: 'down',
      elbow_angle_deg: 84,
      shoulder_hip_ankle_angle_deg: 174,
      visibility: 0.94,
      quality_score: 91,
      payload: { model: 'glasses_pose_v1' },
      occurred_at: '2026-06-18T12:00:00.000Z',
      created_at: '2026-06-18T12:00:00.100Z',
    });

    expect(sample).toEqual({
      timestampMs: Date.parse('2026-06-18T12:00:00.000Z'),
      elbowAngleDeg: 84,
      shoulderHipAnkleAngleDeg: 174,
      visibility: 0.94,
    });
  });

  it('applies real Rokid pose and rep events to the pushup coach state', () => {
    let state = createPushupCoachState({ targetReps: 20 });
    state = applyRokidPushupEventToCoach(state, {
      id: 1,
      session_id: 7,
      user_id: 1,
      event_type: 'pose',
      reps: 0,
      phase: 'up',
      elbow_angle_deg: 170,
      shoulder_hip_ankle_angle_deg: 176,
      visibility: 0.94,
      quality_score: null,
      payload: null,
      occurred_at: '2026-06-18T12:00:00.000Z',
      created_at: '2026-06-18T12:00:00.000Z',
    });
    state = applyRokidPushupEventToCoach(state, {
      id: 2,
      session_id: 7,
      user_id: 1,
      event_type: 'pose',
      reps: 0,
      phase: 'down',
      elbow_angle_deg: 84,
      shoulder_hip_ankle_angle_deg: 174,
      visibility: 0.94,
      quality_score: null,
      payload: null,
      occurred_at: '2026-06-18T12:00:00.700Z',
      created_at: '2026-06-18T12:00:00.700Z',
    });
    state = applyRokidPushupEventToCoach(state, {
      id: 3,
      session_id: 7,
      user_id: 1,
      event_type: 'pose',
      reps: 1,
      phase: 'up',
      elbow_angle_deg: 166,
      shoulder_hip_ankle_angle_deg: 175,
      visibility: 0.94,
      quality_score: 92,
      payload: null,
      occurred_at: '2026-06-18T12:00:01.500Z',
      created_at: '2026-06-18T12:00:01.500Z',
    });

    expect(state.reps).toBe(1);

    state = applyRokidPushupEventToCoach(state, {
      id: 4,
      session_id: 7,
      user_id: 1,
      event_type: 'rep',
      reps: 5,
      phase: 'up',
      elbow_angle_deg: null,
      shoulder_hip_ankle_angle_deg: null,
      visibility: 0.97,
      quality_score: 88,
      payload: { suggestion: '保持节奏' },
      occurred_at: '2026-06-18T12:00:05.000Z',
      created_at: '2026-06-18T12:00:05.000Z',
    });

    expect(state.reps).toBe(5);
    expect(state.qualityScore).toBe(88);
    expect(state.feedback).toContain('眼镜端已确认');
    expect(state.suggestion).toBe('保持节奏');
  });

  it('formats glasses session_state events for the mobile coach timeline', () => {
    expect(rokidPushupSessionStateMessage({
      id: 5,
      session_id: 7,
      user_id: 1,
      event_type: 'session_state',
      reps: null,
      phase: null,
      elbow_angle_deg: null,
      shoulder_hip_ankle_angle_deg: null,
      visibility: null,
      quality_score: null,
      payload: {
        state: 'session_ready',
        message: 'Reva session #7',
        detail: 'target_reps=20',
      },
      occurred_at: '2026-06-18T12:00:00.000Z',
      created_at: '2026-06-18T12:00:00.000Z',
    })).toBe('眼镜端状态: Reva session #7 · target_reps=20');
  });
});
