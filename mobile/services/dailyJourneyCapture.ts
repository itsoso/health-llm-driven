import * as Location from 'expo-location';
import * as TaskManager from 'expo-task-manager';
import { uuid } from 'expo-modules-core';
import { getAuthSessionSnapshot, subscribeAuthSessionChange } from './api';
import { dailyJourneyAPI, dailyJourneyError, DailyJourneyPoint, DailyJourneySession } from './dailyJourney';
import { journeyStorage } from './dailyJourneyStorage';
import { hasDailyJourneyNativeCapability } from '../config/releaseCapabilities';

export const DAILY_JOURNEY_LOCATION_TASK = 'REVA_DAILY_JOURNEY_V1';
export const DAILY_JOURNEY_QUEUE_LIMIT = 512;
type Status = 'idle' | 'starting' | 'active' | 'paused' | 'ended' | 'interrupted';
export interface DailyJourneyCaptureSnapshot {
  status: Status; session: DailyJourneySession | null; pendingCount: number;
  offline: boolean; error: string | null;
}
interface Persisted {
  schema: 1; installation: string; token: string; requestId: string; timezone: string;
  retentionDays: 1 | 7; intentExpiresAt: number; session: DailyJourneySession | null;
  status: Status; pendingAction: 'pause' | 'end' | 'delete' | null;
  points: DailyJourneyPoint[]; error: string | null; acceptAfter: number;
}
let record: Persisted | null = null;
let epoch = 0;
let startingEpoch: number | null = null;
let localOperations: Promise<unknown> = Promise.resolve();
let nativeOperations: Promise<unknown> = Promise.resolve();
let upload: Promise<void> | null = null;
let snapshot: DailyJourneyCaptureSnapshot = { status: 'idle', session: null, pendingCount: 0, offline: false, error: null };
const listeners = new Set<() => void>();
class CaptureError extends Error {}
const authError = () => new CaptureError('登录状态已改变，采集已停止');
function local<T>(fn: () => Promise<T>): Promise<T> {
  const next = localOperations.then(fn, fn);
  localOperations = next.then(() => undefined, () => undefined);
  return next;
}
function native<T>(fn: () => Promise<T>): Promise<T> {
  const next = nativeOperations.then(fn, fn);
  nativeOperations = next.then(() => undefined, () => undefined);
  return next;
}
function publish(patch: Partial<DailyJourneyCaptureSnapshot> = {}) {
  snapshot = { ...snapshot, status: record?.status ?? 'idle', session: record?.session ?? null,
    pendingCount: record?.points.length ?? 0, error: record?.error ?? null, ...patch };
  listeners.forEach(listener => listener());
}
function checkEpoch(value: number) { if (epoch !== value) throw authError(); }
async function ownerToken(expected?: string): Promise<string> {
  const before = getAuthSessionSnapshot();
  // Lazy loading avoids the auth -> api -> capture lifecycle initialization cycle.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { readPersistedApiAuthToken } = require('./auth') as typeof import('./auth');
  const persisted = await readPersistedApiAuthToken();
  const after = getAuthSessionSnapshot();
  if (before.generation !== after.generation || !persisted || (after.initialized && after.token !== persisted)
    || (expected && expected !== persisted)) throw authError();
  return persisted;
}
async function backgroundAuthAccess(enabled: boolean, token: string, guard = epoch) {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { setBackgroundAuthAccess } = require('./auth') as typeof import('./auth');
  await setBackgroundAuthAccess(enabled, token, { isCurrent: () => guard === epoch });
}
async function owned(value: number, token: string) { checkEpoch(value); await ownerToken(token); checkEpoch(value); }
async function persist(value: Persisted, guard = epoch) {
  checkEpoch(guard);
  try { await journeyStorage.write(value); }
  catch { throw new CaptureError('本机行程无法安全保存，采集已中断'); }
  checkEpoch(guard); record = value; publish();
}
async function stopNative(guard = epoch) {
  await native(async () => {
    if (guard !== epoch) return;
    const started = await Location.hasStartedLocationUpdatesAsync(DAILY_JOURNEY_LOCATION_TASK);
    if (guard === epoch && started) await Location.stopLocationUpdatesAsync(DAILY_JOURNEY_LOCATION_TASK);
  });
}
function stopWithoutWaitingForStorage(guard: number): Promise<CaptureError | null> {
  return stopNative(guard).then(() => null, () => new CaptureError('系统定位停止未确认，请检查系统定位设置'));
}
async function permissions(request: boolean) {
  if (!hasDailyJourneyNativeCapability()) throw new CaptureError('请安装支持每日行程的新版 iOS 安装包');
  const foreground = await (request ? Location.requestForegroundPermissionsAsync() : Location.getForegroundPermissionsAsync());
  if (!foreground.granted) throw new CaptureError('未允许前台定位，行程未开始采集');
  const background = await (request ? Location.requestBackgroundPermissionsAsync() : Location.getBackgroundPermissionsAsync());
  if (!background.granted) throw new CaptureError('请允许始终定位后再开启当天行程');
}
function safeError(error: unknown) { return error instanceof CaptureError ? error.message : dailyJourneyError(error); }
function validSession(session: DailyJourneySession, client: string) {
  const start = Date.parse(session.started_at); const deadline = Date.parse(session.deadline_at); const expiry = Date.parse(session.expires_at);
  if (session.client_id !== client || !session.id || !Number.isInteger(session.version) || !Number.isInteger(session.segment)
    || !Number.isFinite(start) || !Number.isFinite(deadline) || deadline <= start || deadline - start > 86400000
    || !Number.isFinite(expiry) || expiry < deadline || !['active', 'paused', 'ended'].includes(session.status)) throw new CaptureError('行程状态校验失败，采集已停止');
}
async function startNative(guard: number) {
  if (!record?.session) throw new CaptureError('请重新开启当天行程');
  const current = record;
  await owned(guard, current.token);
  await native(async () => {
    await owned(guard, current.token);
    await Location.startLocationUpdatesAsync(DAILY_JOURNEY_LOCATION_TASK, {
      accuracy: Location.Accuracy.Balanced, distanceInterval: 50, timeInterval: 60000,
      deferredUpdatesDistance: 100, deferredUpdatesInterval: 60000,
      pausesUpdatesAutomatically: true, activityType: Location.ActivityType.Other,
      showsBackgroundLocationIndicator: true,
    });
  });
  try {
    await owned(guard, current.token);
    await local(() => persist({ ...current, status: 'active', error: null }, guard));
    publish({ offline: false });
  } catch (error) { await stopNative(); throw error; }
}

async function interrupt(message: string) {
  const guard = ++epoch;
  const stopping = stopWithoutWaitingForStorage(guard);
  if (record) record = { ...record, status: 'interrupted', error: message, pendingAction: record.pendingAction ?? 'pause' };
  publish({ status: 'interrupted', error: message });
  try { await local(async () => { if (record) await persist(record, guard); }); }
  finally { const error = await stopping; if (error) { publish({ error: error.message }); throw error; } }
}

async function transition(action: 'pause' | 'end' | 'delete') {
  const guard = ++epoch;
  const current = record;
  if (!current) return;
  if (!current.session) throw new CaptureError('开始请求的结果未确认，请重试开启或在历史列表删除行程');
  const stopping = stopWithoutWaitingForStorage(guard);
  // Synchronous invalidation prevents callbacks/late responses from reviving collection.
  record = { ...current, status: action === 'pause' ? 'paused' : 'ended', pendingAction: action, points: action === 'delete' ? [] : current.points, error: null };
  publish({ offline: true });
  try { await local(async () => { if (record) await persist(record, guard); }); }
  catch { publish({ status: 'interrupted', error: '本机停止状态保存失败，采集已停止，请重新打开应用' }); throw new CaptureError('本机停止状态保存失败'); }
  finally { const error = await stopping; if (error) { publish({ error: error.message }); throw error; } }
  await flushPending();
  // An older in-flight upload must not delay the user's local stop.
  if (!record?.pendingAction && !upload) await dailyJourneyCapture.flush();
  if (action === 'delete' && record?.pendingAction === 'delete') throw new CaptureError('本机已停止采集，云端删除尚未确认，请联网后重试');
}

async function flushPending() {
  const current = record; const guard = epoch;
  if (!current?.session || !current.pendingAction) return;
  try {
    await owned(guard, current.token);
    if (current.pendingAction === 'delete') {
      await dailyJourneyAPI.remove(current.session.id, current.token);
      await owned(guard, current.token);
      await backgroundAuthAccess(false, current.token);
      await owned(guard, current.token);
      await local(async () => { checkEpoch(guard); await journeyStorage.clear(); checkEpoch(guard); record = null; publish({ offline: false }); });
      return;
    }
    const session = await dailyJourneyAPI.state(current.session.id, {
      action: current.pendingAction, expected_version: current.session.version, client_id: current.installation,
    }, current.token);
    await owned(guard, current.token); validSession(session, current.installation);
    await local(() => persist({ ...current, session, pendingAction: null, error: null }, guard));
    publish({ offline: false });
  } catch (error) {
    if (guard !== epoch) return;
    const status = (error as { response?: { status?: number } })?.response?.status;
    if (status === 404 || status === 410) {
      await expireLocalSession(current, guard);
      if (!snapshot.error) publish({ error: dailyJourneyError(error) });
    } else if (status === 409) {
      // Reconcile a confirmed remote state; never blindly replay a conflicting write.
      try {
        const session = await dailyJourneyAPI.get(current.session.id, current.token);
        await owned(guard, current.token); validSession(session, current.installation);
        const confirmed = session.status === 'ended' || (current.pendingAction === 'pause' && session.status === 'paused');
        await local(() => persist({ ...current, session, status: session.status === 'ended' ? 'ended' : current.status,
          pendingAction: confirmed ? null : current.pendingAction, error: confirmed ? null : '行程状态已改变，请再次同步' }, guard));
        publish({ offline: !confirmed });
      } catch (readError) { if (guard === epoch) publish({ offline: true, error: safeError(readError) }); }
    } else publish({ offline: true, error: safeError(error) });
  }
}

async function flushPoints() {
  if (record?.pendingAction) { await flushPending(); if (record?.pendingAction) return; }
  const current = record; const guard = epoch;
  if (!current?.session || current.status === 'starting' || !current.points.length) return;
  if (Date.now() >= Date.parse(current.session.expires_at)) { await expireLocalSession(current, guard); return; }
  try {
    await owned(guard, current.token);
    const batch = current.points.slice(0, 100);
    const result = await dailyJourneyAPI.points(current.session.id, { client_id: current.installation, segment: current.session.segment, points: batch }, current.token);
    await owned(guard, current.token); validSession(result.session, current.installation);
    if (result.session.segment !== current.session.segment) {
      await interrupt('行程已在其他操作中改变，请刷新后继续'); return;
    }
    const ids = new Set(batch.map(point => point.id));
    await local(async () => {
      checkEpoch(guard);
      if (!record) throw authError();
      await persist({ ...record, status: record.status === 'active' ? result.session.status : record.status,
        session: result.session, points: record.points.filter(point => !ids.has(point.id)), error: null }, guard);
    });
    if (result.session.status !== 'active') await stopNative();
    publish({ offline: false });
  } catch (error) {
    if (guard !== epoch) return;
    const status = (error as { response?: { status?: number } })?.response?.status;
    if (status === 404 || status === 410) { await expireLocalSession(current, guard); if (!snapshot.error) publish({ error: dailyJourneyError(error) }); }
    else if (error instanceof CaptureError || (status && status >= 400 && status < 500)) await interrupt(safeError(error));
    else publish({ offline: true, error: safeError(error) });
  }
}

async function restoreRecord(guard: number): Promise<Persisted | null> {
  return local(async () => {
    checkEpoch(guard);
    // Repeated foreground/page initialization must not replace an evolving in-memory queue.
    if (record) return record;
    const installation = await journeyStorage.installation();
    const loaded = await journeyStorage.read<Persisted>();
    checkEpoch(guard);
    if (!loaded) return null;
    if (loaded.schema !== 1 || loaded.installation !== installation || !Array.isArray(loaded.points)
      || loaded.points.length > DAILY_JOURNEY_QUEUE_LIMIT || !loaded.token || !Number.isFinite(loaded.acceptAfter)) throw new CaptureError('行程本机记录无效');
    await owned(guard, loaded.token);
    if (loaded.session) validSession(loaded.session, installation);
    record = loaded; publish();
    return loaded;
  });
}

async function expireLocalSession(current: Persisted, guard: number) {
  let error: string | null = null;
  try { await owned(guard, current.token); await backgroundAuthAccess(false, current.token, guard); }
  catch (cause) { error = safeError(cause); }
  if (guard !== epoch) return;
  await dailyJourneyCapture.clearForAuthChange();
  if (error) publish({ error });
}

export const dailyJourneyCapture = {
  getSnapshot: () => snapshot,
  subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
  async initialize(): Promise<void> {
    const guard = epoch;
    try {
      const saved = await restoreRecord(guard);
      checkEpoch(guard);
      if (!saved) {
        if (startingEpoch === guard) return;
        record = null; publish(); await stopNative(guard); checkEpoch(guard);
        // No journey remains: recover a credential opt-in interrupted before intent persistence.
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        const { recoverBackgroundAuthAccess } = require('./auth') as typeof import('./auth');
        await recoverBackgroundAuthAccess({ isCurrent: () => epoch === guard && startingEpoch !== guard && !record });
        return;
      }
      await owned(guard, saved.token);
      if (Date.now() >= (saved.session ? Date.parse(saved.session.expires_at) : saved.intentExpiresAt)) {
        await expireLocalSession(saved, guard); return;
      }
      // A durable delete obligation has priority over day rollover.
      if (saved.pendingAction === 'delete') { await stopNative(guard); checkEpoch(guard); await dailyJourneyCapture.flush(); return; }
      if (saved.session && Date.now() >= Date.parse(saved.session.deadline_at)) { await transition('end'); return; }
      if (saved.status === 'active') {
        await permissions(false); await owned(guard, saved.token);
        const started = await Location.hasStartedLocationUpdatesAsync(DAILY_JOURNEY_LOCATION_TASK);
        checkEpoch(guard);
        if (!started) { await interrupt('系统定位已停止，请主动继续当天行程'); return; }
      } else await stopNative(guard);
      checkEpoch(guard);
      await dailyJourneyCapture.flush();
    } catch (error) {
      if (guard !== epoch) return;
      if (error instanceof CaptureError && error.message === authError().message) {
        await dailyJourneyCapture.clearForAuthChange(); return;
      }
      await interrupt(safeError(error));
    }
  },
  async start(options: { retentionDays: 1 | 7; consent: true }): Promise<void> {
    if (options.consent !== true || ![1, 7].includes(options.retentionDays)) throw new CaptureError('请先确认定位用途和保留期限');
    if (!hasDailyJourneyNativeCapability()) throw new CaptureError('请安装支持每日行程的新版 iOS 安装包');
    if (record?.session && record.status !== 'ended') throw new CaptureError('请先结束或继续当前行程');
    if (record?.session && (record.points.length || record.pendingAction)) throw new CaptureError('请先同步或删除上一次行程，再开启新的行程');
    const guard = ++epoch;
    startingEpoch = guard;
    let began = false;
    let backgroundToken: string | null = null;
    publish({ status: 'starting', error: null });
    try {
      await restoreRecord(guard); checkEpoch(guard);
      if (record?.session && (record.status !== 'ended' || record.points.length || record.pendingAction)) throw new CaptureError('请先继续、同步或删除上一次行程');
      const token = await ownerToken(); checkEpoch(guard);
      // An uncertain start keeps its idempotency key and consent parameters together.
      // Never silently submit the original retention after the user selects a different one.
      if (record && !record.session && record.token === token && record.intentExpiresAt > Date.now()
        && record.retentionDays !== options.retentionDays) {
        throw new CaptureError(`上次保留 ${record.retentionDays} 天的开始请求尚未确认，不能直接改为 ${options.retentionDays} 天。请选择原来的 ${record.retentionDays} 天重试确认；确认后可在历史列表删除，再按新期限开启。`);
      }
      await permissions(true); await owned(guard, token);
      await backgroundAuthAccess(true, token); await owned(guard, token);
      backgroundToken = token;
      const installation = await local(() => journeyStorage.installation());
      await owned(guard, token);
      const current: Persisted = record && !record.session && record.token === token && record.intentExpiresAt > Date.now()
        ? record : { schema: 1, installation, token, requestId: uuid.v4(), timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          retentionDays: options.retentionDays, intentExpiresAt: Math.min(new Date(Date.now()).setHours(24, 0, 0, 0), Date.now() + 86400000), session: null, status: 'starting', pendingAction: null, points: [], error: null, acceptAfter: Date.now() };
      began = true;
      await local(() => persist({ ...current, pendingAction: null, status: 'starting', error: null }, guard));
      const session = await dailyJourneyAPI.start({ request_id: current.requestId, client_id: installation, timezone: current.timezone, retention_days: current.retentionDays, consent: true }, token);
      await owned(guard, token); validSession(session, installation);
      if (session.status !== 'active' || Date.now() >= Date.parse(session.deadline_at)) {
        await local(() => persist({ ...current, session, status: session.status === 'paused' ? 'paused' : 'ended', pendingAction: null }, guard));
        throw new CaptureError('这次行程已暂停或结束，请查看当前状态');
      }
      await local(() => persist({ ...current, session, status: 'starting', pendingAction: null, acceptAfter: Date.parse(session.started_at) }, guard));
      await startNative(guard);
    } catch (error) {
      let message = safeError(error);
      if (guard === epoch && backgroundToken && !record) {
        try { await backgroundAuthAccess(false, backgroundToken, guard); }
        catch { message = '定位未开始，登录凭据保护恢复未完成，请重新打开应用'; }
      }
      if (guard === epoch && began && record?.status !== 'ended') await interrupt(message);
      else if (guard === epoch) publish({ error: message });
      throw new CaptureError(message);
    } finally { if (startingEpoch === guard) startingEpoch = null; }
  },
  pause: () => transition('pause'),
  end: () => transition('end'),
  async resume(): Promise<void> {
    const operationEpoch = epoch;
    await permissions(true);
    checkEpoch(operationEpoch);
    if (!record?.session || record.status === 'ended' || Date.now() >= Date.parse(record.session.deadline_at)) throw new CaptureError('当天行程已结束，请主动开启新的行程');
    if (record.status === 'active') return;
    if (record.session.status === 'active' && !record.pendingAction) {
      record = { ...record, pendingAction: 'pause' };
      await local(() => persist(record!));
    }
    await dailyJourneyCapture.flush();
    checkEpoch(operationEpoch);
    if (!record?.session || record.pendingAction || record.points.length) throw new CaptureError('请联网同步之前的轨迹和暂停状态后继续');
    const current = record; const guard = ++epoch;
    try {
      await owned(guard, current.token);
      await backgroundAuthAccess(true, current.token); await owned(guard, current.token);
      const session = await dailyJourneyAPI.state(current.session!.id, { action: 'resume', expected_version: current.session!.version, client_id: current.installation }, current.token);
      await owned(guard, current.token); validSession(session, current.installation);
      if (session.status !== 'active' || Date.now() >= Date.parse(session.deadline_at)) throw new CaptureError('当天行程已结束');
      await local(() => persist({ ...current, session, status: 'starting', points: [], error: null, acceptAfter: Date.now() }, guard));
      await startNative(guard);
    } catch (error) { if (guard === epoch) await interrupt(safeError(error)); throw new CaptureError(safeError(error)); }
  },
  async remove(id: string): Promise<void> {
    const guard = epoch;
    if (!record) await restoreRecord(guard);
    checkEpoch(guard);
    if (record?.session?.id === id) { await transition('delete'); return; }
    const token = await ownerToken();
    await dailyJourneyAPI.remove(id, token);
  },
  async flush(): Promise<void> {
    if (upload) return upload;
    upload = (async () => {
      // At most six batches per invocation; never spin/retry after an uncertain failure.
      for (let i = 0; i < Math.ceil(DAILY_JOURNEY_QUEUE_LIMIT / 100); i += 1) {
        const count = record?.points.length ?? 0;
        await flushPoints();
        if (!record?.points.length || record.points.length >= count || record.pendingAction) break;
      }
      if (record?.status === 'ended' && !record.pendingAction && !record.points.length) {
        const guard = epoch; const token = record.token;
        try {
          await owned(guard, token);
          await backgroundAuthAccess(false, token); await owned(guard, token);
          // A completed session no longer needs a background-accessible token copy.
          await local(async () => { checkEpoch(guard); await journeyStorage.clear(); checkEpoch(guard); });
        } catch (error) { if (guard === epoch) publish({ error: safeError(error) }); }
      }
    })().finally(() => { upload = null; });
    return upload;
  },
  clearForAuthChange(): Promise<void> {
    const guard = ++epoch; record = null; publish({ offline: false });
    const stopping = stopWithoutWaitingForStorage(guard);
    return local(async () => { try { await journeyStorage.clear(); } finally { const error = await stopping; if (error) { publish({ error: error.message }); throw error; } } });
  },
};

/** Native task callback: no raw coordinates are logged, geocoded, or sent to an LLM. */
export async function processDailyJourneyLocations(locations: Location.LocationObject[]): Promise<void> {
  if (!record) {
    const initialEpoch = epoch;
    try { await restoreRecord(initialEpoch); }
    catch (error) { if (initialEpoch === epoch) { await dailyJourneyCapture.clearForAuthChange(); publish({ status: 'interrupted', error: safeError(error) }); } return; }
  }
  const current = record; const guard = epoch;
  if (!current?.session || current.status !== 'active' || current.pendingAction) return;
  try {
    await owned(guard, current.token);
    if (Date.now() >= Date.parse(current.session.expires_at)) { await expireLocalSession(current, guard); return; }
    await permissions(false); await owned(guard, current.token);
    const deadline = Date.parse(current.session.deadline_at); const start = Math.max(Date.parse(current.session.started_at), current.acceptAfter);
    const points = locations.filter(location => {
      const c = location.coords;
      return Number.isFinite(location.timestamp) && location.timestamp >= start && location.timestamp < deadline && location.timestamp <= Date.now() + 120000
        && Number.isFinite(c.latitude) && Math.abs(c.latitude) <= 90 && Number.isFinite(c.longitude) && Math.abs(c.longitude) <= 180
        && c.accuracy !== null && Number.isFinite(c.accuracy) && c.accuracy >= 0 && c.accuracy <= 10000;
    }).map(location => ({ id: uuid.v4(), recorded_at: new Date(location.timestamp).toISOString(), latitude: location.coords.latitude,
      longitude: location.coords.longitude, accuracy_m: location.coords.accuracy!, speed_mps: location.coords.speed !== null && Number.isFinite(location.coords.speed) && location.coords.speed >= 0 && location.coords.speed <= 200 ? location.coords.speed : null }));
    await local(async () => {
      checkEpoch(guard);
      if (!record || record.status !== 'active') return;
      if (record.points.length + points.length > DAILY_JOURNEY_QUEUE_LIMIT) throw new CaptureError('离线行程已满，采集已中断，请联网后继续');
      await persist({ ...record, points: [...record.points, ...points] }, guard);
    });
    if (Date.now() >= deadline) { await transition('end'); return; }
    await dailyJourneyCapture.flush();
  } catch (error) { if (guard === epoch) await interrupt(safeError(error)); }
}

if (!TaskManager.isTaskDefined(DAILY_JOURNEY_LOCATION_TASK)) {
  TaskManager.defineTask<{ locations: Location.LocationObject[] }>(DAILY_JOURNEY_LOCATION_TASK, async ({ data, error }) => {
    if (error) { if (!record) await dailyJourneyCapture.initialize(); await interrupt('系统定位中断，请检查定位权限后继续'); return; }
    if (data?.locations) await processDailyJourneyLocations(data.locations);
  });
}
subscribeAuthSessionChange(() => {
  const token = getAuthSessionSnapshot().token;
  if (record && token === record.token) return;
  if (!record && token) {
    const guard = ++epoch;
    // The first authenticated foreground hydration is not an account switch.
    // Match the durable owner before deciding whether to clear a headless session.
    void local(async () => {
      if (guard !== epoch) return;
      const installation = await journeyStorage.installation();
      const saved = await journeyStorage.read<Persisted>();
      if (guard !== epoch) return;
      if (saved?.token === token && saved.installation === installation) return;
      await journeyStorage.clear();
      await stopNative(guard);
    }).catch(() => publish({ status: 'interrupted', error: '登录后的行程安全检查未完成，请重新打开应用' }));
    return;
  }
  void dailyJourneyCapture.clearForAuthChange().catch(() => publish({ status: 'interrupted', error: '退出后的本机清理未完成，请重新打开应用' }));
});
