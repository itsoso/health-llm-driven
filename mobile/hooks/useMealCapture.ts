import { useCallback, useEffect, useRef, useState } from 'react';

import {
  MEAL_SESSION_MAX_FRAMES,
  abortMealSession,
  appendMealFrame,
  confirmMealSession,
  finishMealSession,
  mealSessionErrorDetail,
  mealSessionErrorStatus,
  startMealSession,
  type MealSessionSource,
  type MealSessionSummary,
} from '../services/mealMonitoring';

/**
 * useMealCapture — 餐食监控采样状态机 (周期照片采样 → 草稿 → 确认/放弃)。
 *
 * 关键不变量(见 meal-monitor.tsx):
 *  - consent 必须 true 才会 start;startSession 自带兜底门控。
 *  - 顺序采样(非重叠定时器):每帧 await captureFrame() → POST /frames → 短间隔 → 重复。
 *    眼镜 BLE 单张照片最长 25s,await 本身就在节流;再加 ~min-interval 兜底。
 *  - 停止条件:用户结束 / frame_count 命中 30(后端 429 之前客户端先停)/ 任意 429。
 *  - 卸载/离屏时 active 会 abort(原始帧立即清除)。
 */

export type MealCapturePhase =
  | 'idle'
  | 'starting'
  | 'monitoring'
  | 'finishing'
  | 'draft'
  | 'confirming'
  | 'confirmed'
  | 'aborting'
  | 'error';

export interface MealCaptureFrame {
  imageBase64?: string;
  imageUri?: string;
  capturedAt: string;
}

export interface MealCaptureResult {
  /** A frame to upload, or null when capture failed / was cancelled (loop stops, no fake success). */
  frame: MealCaptureFrame | null;
  /** Optional human reason for a null result, surfaced as the stop message. */
  reason?: string;
}

export interface UseMealCaptureOptions {
  source?: MealSessionSource;
  /** Min spacing between frame captures (ms). The await on captureFrame already paces; this is a floor. */
  minIntervalMs?: number;
  /** Capture exactly one frame. Should await glasses photo, fall back to phone ImagePicker. */
  captureFrame: () => Promise<MealCaptureResult>;
}

export interface MealCaptureState {
  phase: MealCapturePhase;
  sessionId: number | null;
  frameCount: number;
  lastFrameAt: string | null;
  message: string | null;
  summary: MealSessionSummary | null;
  dietRecordId: number | null;
  reachedFrameCap: boolean;
  isBusy: boolean;
}

const DEFAULT_MIN_INTERVAL_MS = 4500;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function useMealCapture(options: UseMealCaptureOptions) {
  const { source, captureFrame } = options;
  const minIntervalMs = options.minIntervalMs ?? DEFAULT_MIN_INTERVAL_MS;

  const [state, setState] = useState<MealCaptureState>({
    phase: 'idle',
    sessionId: null,
    frameCount: 0,
    lastFrameAt: null,
    message: null,
    summary: null,
    dietRecordId: null,
    reachedFrameCap: false,
    isBusy: false,
  });

  // Refs drive the async loop so it reads live values without stale closures.
  const monitoringRef = useRef(false);
  const sessionIdRef = useRef<number | null>(null);
  const loopRunningRef = useRef(false);
  const captureFrameRef = useRef(captureFrame);
  captureFrameRef.current = captureFrame;

  const patch = useCallback((next: Partial<MealCaptureState>) => {
    setState((prev) => ({ ...prev, ...next }));
  }, []);

  const runCaptureLoop = useCallback(async () => {
    if (loopRunningRef.current) {
      return;
    }
    loopRunningRef.current = true;
    try {
      let localFrameCount = 0;
      while (monitoringRef.current && sessionIdRef.current != null) {
        if (localFrameCount >= MEAL_SESSION_MAX_FRAMES) {
          monitoringRef.current = false;
          patch({ phase: 'monitoring', reachedFrameCap: true, message: '已采够样本，请结束并分析' });
          break;
        }
        let result: MealCaptureResult;
        try {
          result = await captureFrameRef.current();
        } catch (error) {
          monitoringRef.current = false;
          patch({
            phase: 'error',
            message: `采样失败: ${mealSessionErrorDetail(error) ?? 'capture_failed'}`,
          });
          break;
        }
        if (!monitoringRef.current || sessionIdRef.current == null) {
          break;
        }
        if (!result.frame) {
          // No fake success: a cancelled/failed capture stops the loop with the real reason.
          monitoringRef.current = false;
          patch({ phase: 'error', message: result.reason ?? '本帧未采集到照片，已停止' });
          break;
        }
        try {
          const appended = await appendMealFrame(sessionIdRef.current, {
            imageBase64: result.frame.imageBase64,
            imageUri: result.frame.imageUri,
            capturedAt: result.frame.capturedAt,
          });
          localFrameCount = appended.frame_count;
          patch({
            frameCount: appended.frame_count,
            lastFrameAt: result.frame.capturedAt,
            message: null,
          });
        } catch (error) {
          const status = mealSessionErrorStatus(error);
          monitoringRef.current = false;
          if (status === 429) {
            // Frame cap / rate limit hit on the server — stop, do NOT retry.
            patch({
              phase: 'monitoring',
              reachedFrameCap: true,
              message: mealSessionErrorDetail(error) ?? '已采够样本，请结束并分析',
            });
          } else {
            patch({
              phase: 'error',
              message: `上传帧失败: ${mealSessionErrorDetail(error) ?? 'append_failed'}`,
            });
          }
          break;
        }
        if (!monitoringRef.current) {
          break;
        }
        await delay(minIntervalMs);
      }
    } finally {
      loopRunningRef.current = false;
    }
  }, [minIntervalMs, patch]);

  const startSession = useCallback(
    async (consent: boolean) => {
      // Consent gate: never start without explicit accept.
      if (!consent) {
        patch({ phase: 'error', message: '需要先同意视觉分析说明才能开始' });
        return;
      }
      if (monitoringRef.current || loopRunningRef.current) {
        return;
      }
      patch({
        phase: 'starting',
        message: null,
        summary: null,
        dietRecordId: null,
        reachedFrameCap: false,
        frameCount: 0,
        lastFrameAt: null,
        isBusy: true,
      });
      try {
        const session = await startMealSession({ consent: true, source });
        sessionIdRef.current = session.id;
        monitoringRef.current = true;
        patch({
          phase: 'monitoring',
          sessionId: session.id,
          frameCount: session.frame_count ?? 0,
          isBusy: false,
        });
        void runCaptureLoop();
      } catch (error) {
        sessionIdRef.current = null;
        monitoringRef.current = false;
        const status = mealSessionErrorStatus(error);
        patch({
          phase: 'error',
          isBusy: false,
          message:
            status === 429
              ? mealSessionErrorDetail(error) ?? '今天的餐食监控次数已达上限'
              : `开始失败: ${mealSessionErrorDetail(error) ?? 'start_failed'}`,
        });
      }
    },
    [patch, runCaptureLoop, source],
  );

  const finish = useCallback(async () => {
    const sessionId = sessionIdRef.current;
    if (sessionId == null) {
      return;
    }
    monitoringRef.current = false;
    patch({ phase: 'finishing', isBusy: true, message: null });
    try {
      const result = await finishMealSession(sessionId);
      patch({
        phase: 'draft',
        isBusy: false,
        summary: result.summary,
        frameCount: result.summary.frame_count ?? state.frameCount,
        message: null,
      });
    } catch (error) {
      patch({
        phase: 'error',
        isBusy: false,
        message: `分析失败: ${mealSessionErrorDetail(error) ?? 'finish_failed'}`,
      });
    }
  }, [patch, state.frameCount]);

  const confirm = useCallback(
    async (mealType?: string) => {
      const sessionId = sessionIdRef.current;
      if (sessionId == null) {
        return;
      }
      patch({ phase: 'confirming', isBusy: true, message: null });
      try {
        const result = await confirmMealSession(sessionId, { mealType });
        monitoringRef.current = false;
        sessionIdRef.current = null;
        patch({
          phase: 'confirmed',
          isBusy: false,
          dietRecordId: result.diet_record_id,
          message: '已记录这餐',
        });
      } catch (error) {
        patch({
          phase: 'error',
          isBusy: false,
          message: `确认失败: ${mealSessionErrorDetail(error) ?? 'confirm_failed'}`,
        });
      }
    },
    [patch],
  );

  const abort = useCallback(async () => {
    const sessionId = sessionIdRef.current;
    monitoringRef.current = false;
    if (sessionId == null) {
      patch({ phase: 'idle', isBusy: false });
      return;
    }
    sessionIdRef.current = null;
    patch({ phase: 'aborting', isBusy: true });
    try {
      await abortMealSession(sessionId);
      patch({ phase: 'idle', isBusy: false, message: '已放弃并清除原始照片', summary: null, sessionId: null });
    } catch (error) {
      patch({
        phase: 'error',
        isBusy: false,
        message: `放弃失败: ${mealSessionErrorDetail(error) ?? 'abort_failed'}`,
      });
    }
  }, [patch]);

  /**
   * Fire-and-forget abort for unmount/navigate-away while active — purges raw
   * frames immediately. Mirrors rokid-health unmount cleanup. Safe to call when
   * the session is already terminal (no session id → noop).
   */
  const abortOnUnmount = useCallback(() => {
    const sessionId = sessionIdRef.current;
    monitoringRef.current = false;
    sessionIdRef.current = null;
    if (sessionId != null) {
      void abortMealSession(sessionId).catch(() => undefined);
    }
  }, []);

  useEffect(() => () => abortOnUnmount(), [abortOnUnmount]);

  return {
    state,
    startSession,
    finish,
    confirm,
    abort,
    abortOnUnmount,
  };
}
