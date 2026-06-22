import api from './api';
import type { RokidIntegrationStatus } from '../modules/rokid-bridge';

/**
 * Meal monitoring (餐食监控) client — periodic photo sampling → batch analysis →
 * DRAFT → user confirm → post-meal OBSERVATIONAL summary.
 *
 * 这不是真·实时视频(无 Rokid 视频 API / BLE 带宽 / R4)。流程是:
 *   start (consent) → 顺序采样若干帧 → finish 批量分析出草稿(不写 DietRecord)
 *   → 用户确认 → confirm 才落库 DietRecord;或 abort 丢弃并清原始帧。
 *
 * 后端契约: /api/v1/ambient/meal-sessions (JWT 由 services/api.ts 自动附带, 用户隔离).
 * NOTE: 这些类型现为手写 —— 后端部署后应跑 `npm run generate-types` 用
 *       components['schemas'][...] 替换(镜像 frontend),消除手写漂移风险。
 */

export type MealSessionStatus =
  | 'active'
  | 'needs_confirmation'
  | 'confirmed'
  | 'aborted'
  | string;

export type MealSessionSource = 'rokid_glasses' | 'phone';

export interface MealSession {
  id: number;
  status: MealSessionStatus;
  frame_count: number;
  started_at?: string;
  raw_media_delete_at?: string;
  source?: string | null;
  device_type?: string | null;
  [key: string]: unknown;
}

export interface MealFood {
  name: string;
  quantity?: string | null;
  calories?: number | null;
  protein?: number | null;
  carbs?: number | null;
  fat?: number | null;
  fiber?: number | null;
  [key: string]: unknown;
}

export interface MealTotals {
  calories?: number | null;
  protein?: number | null;
  carbs?: number | null;
  fat?: number | null;
  fiber?: number | null;
}

export interface MealGuidanceAlert {
  title?: string;
  message?: string;
  severity?: string;
  [key: string]: unknown;
}

export interface MealDraftDietRecord {
  food_items?: unknown;
  [key: string]: unknown;
}

export interface MealSessionSummary {
  session_id: number;
  status: 'needs_confirmation' | string;
  target: 'diet_draft' | string;
  frame_count: number;
  foods: MealFood[];
  totals: MealTotals;
  observational_summary: string;
  guidance_alerts: MealGuidanceAlert[];
  disclaimer: string;
  draft_diet_record: MealDraftDietRecord | null;
}

export interface StartMealSessionResponse extends MealSession {}

export interface AppendMealFrameResponse {
  frame_event_id: number;
  session_id: number;
  frame_count: number;
  status: MealSessionStatus;
}

export interface FinishMealSessionResponse {
  session: MealSession;
  summary: MealSessionSummary;
}

export interface ConfirmMealSessionResponse {
  session: MealSession;
  diet_record_id: number | null;
}

export interface AbortMealSessionResponse {
  session: MealSession;
}

/** Client-side throttle ceiling — backend rejects the 31st frame with 429. */
export const MEAL_SESSION_MAX_FRAMES = 30;

/**
 * Meal photo capture should prefer Rokid when the native bridge is usable.
 *
 * CustomView running/evidence is diagnostic only here: the iOS bridge can still
 * attempt camera capture on an authenticated BLE-linked session, and JS keeps a
 * timeout fallback to the phone camera if the SDK does not return an image.
 */
export function canAttemptRokidMealPhoto(status?: Partial<RokidIntegrationStatus> | null): boolean {
  if (!status || status.platform !== 'ios') {
    return false;
  }
  if (status.bridgeAvailable === false || status.sdkLinked !== true) {
    return false;
  }
  if (status.authorizationState && status.authorizationState !== 'authenticated') {
    return false;
  }
  return status.iosBleConnected !== false;
}

export async function startMealSession(input: {
  consent: boolean;
  source?: MealSessionSource;
  deviceType?: string;
  meta?: Record<string, unknown>;
}): Promise<StartMealSessionResponse> {
  // 不假装成功:consent 必须为 true 才发请求;调用方应在同意门控住,这里再兜一道。
  const response = await api.post<StartMealSessionResponse>('/ambient/meal-sessions', {
    consent: input.consent,
    source: input.source,
    device_type: input.deviceType,
    meta: input.meta,
  });
  return response.data;
}

export async function appendMealFrame(
  sessionId: number,
  frame: {
    imageBase64?: string;
    imageUri?: string;
    capturedAt?: string;
    recognitionResult?: Record<string, unknown>;
    meta?: Record<string, unknown>;
  },
): Promise<AppendMealFrameResponse> {
  const response = await api.post<AppendMealFrameResponse>(
    `/ambient/meal-sessions/${sessionId}/frames`,
    {
      image_base64: frame.imageBase64,
      image_uri: frame.imageUri,
      captured_at: frame.capturedAt,
      recognition_result: frame.recognitionResult,
      meta: frame.meta,
    },
  );
  return response.data;
}

export async function finishMealSession(sessionId: number): Promise<FinishMealSessionResponse> {
  const response = await api.post<FinishMealSessionResponse>(
    `/ambient/meal-sessions/${sessionId}/finish`,
    {},
  );
  return response.data;
}

export async function confirmMealSession(
  sessionId: number,
  input?: { mealType?: string },
): Promise<ConfirmMealSessionResponse> {
  const response = await api.post<ConfirmMealSessionResponse>(
    `/ambient/meal-sessions/${sessionId}/confirm`,
    {
      confirm: true,
      meal_type: input?.mealType,
    },
  );
  return response.data;
}

export async function abortMealSession(sessionId: number): Promise<AbortMealSessionResponse> {
  const response = await api.post<AbortMealSessionResponse>(
    `/ambient/meal-sessions/${sessionId}/abort`,
    {},
  );
  return response.data;
}

export async function getMealSession(sessionId: number): Promise<MealSession> {
  const response = await api.get<MealSession>(`/ambient/meal-sessions/${sessionId}`);
  return response.data;
}

/**
 * Read an HTTP status off an unknown error (axios shape). Used to detect 429
 * (rate limit / frame cap) and 409 (wrong session status) without retry storms.
 */
export function mealSessionErrorStatus(error: unknown): number | undefined {
  if (error && typeof error === 'object') {
    const response = (error as { response?: { status?: unknown } }).response;
    if (response && typeof response.status === 'number') {
      return response.status;
    }
  }
  return undefined;
}

export function mealSessionErrorDetail(error: unknown): string | undefined {
  if (error && typeof error === 'object') {
    const response = (error as { response?: { data?: { detail?: unknown } } }).response;
    const detail = response?.data?.detail;
    if (typeof detail === 'string' && detail.length > 0) {
      return detail;
    }
    const message = (error as { message?: unknown }).message;
    if (typeof message === 'string' && message.length > 0) {
      return message;
    }
  }
  return undefined;
}
