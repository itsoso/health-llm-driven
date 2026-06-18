import api from './api';
import {
  updatePushupCoach,
  type PushupCoachState,
  type PushupPoseSample,
} from './pushupCoach';

export const ROKID_PUSHUP_APP_PACKAGE = 'life.executor.health.rokid.pushup';
export const ROKID_PUSHUP_APP_ACTIVITY = '.MainActivity';
export const ROKID_PUSHUP_APK_RESOURCE_NAME = 'rokid-pushup-glasses';
export const ROKID_PUSHUP_APK_RESOURCE_EXTENSION = 'apk';

export type RokidPushupSession = {
  id: number;
  user_id: number;
  status: string;
  target_reps: number;
  source_device: string;
  ingest_token?: string;
  ingest_url?: string;
  events_url?: string;
  open_url?: string;
  created_at: string;
};

export type RokidPushupEvent = {
  id: number;
  session_id: number;
  user_id: number;
  event_type: 'pose' | 'rep' | 'session_state' | string;
  reps?: number | null;
  phase?: 'unknown' | 'up' | 'down' | 'transition' | string | null;
  elbow_angle_deg?: number | null;
  shoulder_hip_ankle_angle_deg?: number | null;
  visibility?: number | null;
  quality_score?: number | null;
  payload?: Record<string, unknown> | null;
  occurred_at: string;
  created_at: string;
};

export type CreateRokidPushupSessionInput = {
  targetReps?: number;
  sourceDevice?: string;
  meta?: Record<string, unknown>;
};

export async function createRokidPushupSession(input?: CreateRokidPushupSessionInput) {
  const response = await api.post('/devices/rokid/pushup-sessions', {
    target_reps: input?.targetReps ?? 20,
    source_device: input?.sourceDevice ?? 'rokid_glasses',
    meta: input?.meta,
  });
  return response.data as RokidPushupSession;
}

export async function listRokidPushupEvents(
  sessionId: number,
  options?: { afterId?: number; limit?: number },
) {
  const response = await api.get(`/devices/rokid/pushup-sessions/${sessionId}/events`, {
    params: {
      after_id: options?.afterId ?? 0,
      limit: options?.limit ?? 200,
    },
  });
  return (response.data?.events ?? []) as RokidPushupEvent[];
}

export async function finishRokidPushupSession(sessionId: number) {
  const response = await api.post(`/devices/rokid/pushup-sessions/${sessionId}/finish`);
  return response.data as { session: RokidPushupSession };
}

export function rokidPushupEventToPoseSample(event: RokidPushupEvent): PushupPoseSample | null {
  if (event.event_type !== 'pose') {
    return null;
  }
  const timestampMs = Date.parse(event.occurred_at);
  return {
    timestampMs: Number.isFinite(timestampMs) ? timestampMs : Date.now(),
    elbowAngleDeg: event.elbow_angle_deg ?? undefined,
    shoulderHipAnkleAngleDeg: event.shoulder_hip_ankle_angle_deg ?? undefined,
    visibility: event.visibility ?? undefined,
  };
}

export function applyRokidPushupEventToCoach(
  state: PushupCoachState,
  event: RokidPushupEvent,
): PushupCoachState {
  const sample = rokidPushupEventToPoseSample(event);
  if (sample) {
    return updatePushupCoach(state, sample);
  }

  if (event.event_type === 'rep' && event.reps != null && event.reps >= state.reps) {
    const suggestion = typeof event.payload?.suggestion === 'string'
      ? event.payload.suggestion
      : '继续保持稳定节奏, 先保证动作完整。';
    return {
      ...state,
      reps: event.reps,
      phase: event.phase === 'up' || event.phase === 'down' || event.phase === 'transition'
        ? event.phase
        : state.phase,
      qualityScore: event.quality_score ?? state.qualityScore,
      feedback: `第 ${event.reps} 个完成, 眼镜端已确认。`,
      suggestion,
      lastSampleAtMs: Number.isFinite(Date.parse(event.occurred_at))
        ? Date.parse(event.occurred_at)
        : state.lastSampleAtMs,
    };
  }

  return state;
}
