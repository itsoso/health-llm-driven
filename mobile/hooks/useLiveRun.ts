/**
 * Live Run GPS watcher + session state.
 *
 * 职责:
 * - expo-location.watchPositionAsync 1Hz 高精度定位
 * - 维护 30s 滑窗, 算瞬时配速 (单点 GPS 配速噪声大)
 * - GPS 信号丢失 >10s 自动暂停计时 (隧道/桥下)
 * - 跑步中本地评估 R1/R2/R3 规则, 触发离线语音
 * - 暴露给 UI: distance / duration / currentPace / avgPace / status / events
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import * as Location from 'expo-location';
import type { LiveRunGpsSample, LiveRunEvent } from '../services/liveRun/api';
import { evaluateRules, resetRuleEngine } from '../services/liveRun/ruleEngine';
import { triggerRule, clearQueue as clearVoiceQueue } from '../services/liveRun/voicePrompter';
import {
  startBackgroundTracking,
  stopBackgroundTracking,
  subscribeLocation,
  type LocationSubscription,
} from '../services/liveRun/backgroundLocation';

const WINDOW_MS = 30_000;
const GPS_LOSS_THRESHOLD_MS = 10_000;
const SAMPLE_INTERVAL_MS = 30_000;
const MIN_ACCURACY_M = 30;

export type RunStatus = 'idle' | 'requesting_permission' | 'running' | 'paused' | 'ended';

interface TrackPoint {
  ts: number;
  lat: number;
  lon: number;
  accuracy: number | null;
  speed: number | null;
}

interface RunState {
  status: RunStatus;
  distanceM: number;
  durationS: number;
  currentPace: number | null;
  avgPace: number | null;
  error: string | null;
  events: LiveRunEvent[];
}

function distanceMeters(a: TrackPoint, b: TrackPoint): number {
  const R = 6371e3;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLon = toRad(b.lon - a.lon);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

export function useLiveRun(targetPaceSeconds: number = 360) {
  const [state, setState] = useState<RunState>({
    status: 'idle',
    distanceM: 0,
    durationS: 0,
    currentPace: null,
    avgPace: null,
    error: null,
    events: [],
  });

  const gpsSamplesRef = useRef<LiveRunGpsSample[]>([]);
  const eventsRef = useRef<LiveRunEvent[]>([]);
  const trackRef = useRef<TrackPoint[]>([]);
  const lastSampleTsRef = useRef<number>(0);
  const startedAtRef = useRef<number>(0);
  const pausedTotalMsRef = useRef<number>(0);
  const pauseStartRef = useRef<number | null>(null);
  const subRef = useRef<LocationSubscription | null>(null);
  const tickerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const targetPaceRef = useRef<number>(targetPaceSeconds);

  useEffect(() => {
    targetPaceRef.current = targetPaceSeconds;
  }, [targetPaceSeconds]);

  const stop = useCallback(() => {
    subRef.current?.remove();
    subRef.current = null;
    stopBackgroundTracking().catch(() => { /* best effort */ });
    if (tickerRef.current) {
      clearInterval(tickerRef.current);
      tickerRef.current = null;
    }
    clearVoiceQueue();
  }, []);

  useEffect(() => () => stop(), [stop]);

  const onPoint = useCallback((loc: Location.LocationObject) => {
    const accuracy = loc.coords.accuracy;
    if (accuracy != null && accuracy > MIN_ACCURACY_M) {
      return;
    }
    const now = Date.now();
    const p: TrackPoint = {
      ts: now,
      lat: loc.coords.latitude,
      lon: loc.coords.longitude,
      accuracy,
      speed: loc.coords.speed,
    };

    if (pauseStartRef.current != null) {
      pausedTotalMsRef.current += now - pauseStartRef.current;
      pauseStartRef.current = null;
    }

    const prev = trackRef.current[trackRef.current.length - 1];
    if (prev) {
      const d = distanceMeters(prev, p);
      const dt = (now - prev.ts) / 1000;
      if (!(d > 100 && dt < 3)) {
        setState((s) => ({ ...s, distanceM: s.distanceM + d }));
      }
    }
    trackRef.current.push(p);

    while (trackRef.current.length > 0 && now - trackRef.current[0].ts > WINDOW_MS * 2) {
      trackRef.current.shift();
    }

    if (now - lastSampleTsRef.current >= SAMPLE_INTERVAL_MS) {
      gpsSamplesRef.current.push({
        ts: new Date(now).toISOString(),
        lat: p.lat,
        lon: p.lon,
      });
      lastSampleTsRef.current = now;
    }
  }, []);

  const start = useCallback(async () => {
    setState((s) => ({ ...s, status: 'requesting_permission', error: null }));

    startedAtRef.current = Date.now();
    pausedTotalMsRef.current = 0;
    pauseStartRef.current = null;
    trackRef.current = [];
    gpsSamplesRef.current = [];
    eventsRef.current = [];
    lastSampleTsRef.current = 0;
    resetRuleEngine();

    try {
      const ok = await startBackgroundTracking();
      if (!ok) {
        setState((s) => ({ ...s, status: 'idle', error: '定位权限未授权' }));
        return false;
      }
      subRef.current = subscribeLocation(onPoint);
    } catch (e: any) {
      setState((s) => ({ ...s, status: 'idle', error: e?.message || 'GPS 启动失败' }));
      return false;
    }

    tickerRef.current = setInterval(() => {
      const now = Date.now();
      const elapsedMs = now - startedAtRef.current - pausedTotalMsRef.current;
      const durationS = Math.max(0, Math.floor(elapsedMs / 1000));

      const track = trackRef.current;
      const windowStart = now - WINDOW_MS;
      const windowPoints = track.filter((x) => x.ts >= windowStart);
      let currentPace: number | null = null;
      if (windowPoints.length >= 2) {
        let d = 0;
        for (let i = 1; i < windowPoints.length; i++) {
          d += distanceMeters(windowPoints[i - 1], windowPoints[i]);
        }
        const windowMs = windowPoints[windowPoints.length - 1].ts - windowPoints[0].ts;
        if (d > 5 && windowMs > 5000) {
          currentPace = Math.round((windowMs / 1000) / (d / 1000));
        }
      }

      let nextStatus: RunStatus = 'running';
      if (track.length > 0 && now - track[track.length - 1].ts > GPS_LOSS_THRESHOLD_MS) {
        nextStatus = 'paused';
        if (pauseStartRef.current == null) {
          pauseStartRef.current = track[track.length - 1].ts + GPS_LOSS_THRESHOLD_MS;
        }
      }

      const ruleResults = evaluateRules({
        currentPace,
        targetPace: targetPaceRef.current,
        elapsedS: durationS,
        currentHr: null,
        z4PlusMinutes: 0,
      });

      const triggeredEvents: LiveRunEvent[] = [];
      for (const result of ruleResults) {
        if (result.type !== 'triggered') continue;
        const evt = result.event;
        const fired = triggerRule(evt.ruleId, evt.message, evt.metricSnapshot);
        if (!fired) continue;
        const newEvent: LiveRunEvent = {
          ts: new Date(evt.ts).toISOString(),
          rule_id: evt.ruleId,
          message: evt.message,
          metric_snapshot: evt.metricSnapshot,
        };
        triggeredEvents.push(newEvent);
        eventsRef.current.push(newEvent);
      }

      setState((s) => {
        const avgPace =
          s.distanceM > 50 && durationS > 10
            ? Math.round(durationS / (s.distanceM / 1000))
            : null;
        const events =
          triggeredEvents.length > 0 ? [...s.events, ...triggeredEvents] : s.events;
        return { ...s, status: nextStatus, durationS, currentPace, avgPace, events };
      });
    }, 1000);

    setState((s) => ({ ...s, status: 'running' }));
    return true;
  }, [onPoint]);

  const end = useCallback(() => {
    stop();
    setState((s) => ({ ...s, status: 'ended' }));
    return {
      gpsSamples: gpsSamplesRef.current,
      events: eventsRef.current,
    };
  }, [stop]);

  return {
    state,
    start,
    end,
    gpsSamples: gpsSamplesRef.current,
    events: state.events,
  };
}

export function formatPace(secondsPerKm: number | null): string {
  if (secondsPerKm == null || !isFinite(secondsPerKm) || secondsPerKm <= 0) return '--:--';
  const m = Math.floor(secondsPerKm / 60);
  const s = Math.floor(secondsPerKm % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function formatDuration(s: number): string {
  if (!isFinite(s) || s < 0) return '00:00';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}

export function formatDistanceKm(m: number): string {
  return (m / 1000).toFixed(2);
}
