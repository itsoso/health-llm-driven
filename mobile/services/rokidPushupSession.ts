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
// 眼镜端识别 APK 托管在 health 公开免登录目录,
// app 在 bundled 缺失时从这里下载 → installAppFileUri 装到眼镜。可用 env 覆盖。
export const ROKID_PUSHUP_APK_DOWNLOAD_URL =
  process.env.EXPO_PUBLIC_ROKID_PUSHUP_APK_URL
  || 'https://health.executor.life/rokid-pushup-glasses.apk';

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

// 赛后复盘(观察性,R4 安全):session 质量 + MovementCoach 训练负荷上下文 + 教学链接。
// 字段与后端 RokidPushupSessionReviewResponse 对齐;后端部署后可 npm run generate-types 替换为生成类型。
export type RokidPushupSessionReview = {
  session_id: number;
  session_quality: { reps: number; avg_quality_score: number | null; event_count: number };
  training_context: {
    acwr?: number | null;
    training_status?: string | null;
    readiness_zone?: string | null;
    today_intensity?: string | null;
  } | null;
  observations: string[];
  teaching_links: { key: string; title: string; url?: string | null }[];
  guidance_alerts: unknown[];
  guidance_sanitized?: boolean;
  guidance_violations?: string[];
  disclaimer: string;
};

export async function getRokidPushupSessionReview(
  sessionId: number,
): Promise<RokidPushupSessionReview> {
  const response = await api.get(`/devices/rokid/pushup-sessions/${sessionId}/review`);
  return response.data as RokidPushupSessionReview;
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

export function rokidPushupSessionStateMessage(event: RokidPushupEvent): string | null {
  if (event.event_type !== 'session_state') {
    return null;
  }
  const payload = event.payload ?? {};
  const state = typeof payload.state === 'string' ? payload.state : 'session_state';
  const message = typeof payload.message === 'string' && payload.message.trim()
    ? payload.message.trim()
    : state;
  const detail = typeof payload.detail === 'string' && payload.detail.trim()
    ? payload.detail.trim()
    : null;
  return detail
    ? `眼镜端状态: ${message} · ${detail}`
    : `眼镜端状态: ${message}`;
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
