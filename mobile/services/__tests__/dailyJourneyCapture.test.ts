import * as Location from 'expo-location';
import { uuid } from 'expo-modules-core';
import { getAuthSessionSnapshot, subscribeAuthSessionChange } from '../api';
import { readPersistedApiAuthToken, setBackgroundAuthAccess, recoverBackgroundAuthAccess } from '../auth';
import { hasDailyJourneyNativeCapability } from '../../config/releaseCapabilities';
import { dailyJourneyAPI } from '../dailyJourney';
import { journeyStorage } from '../dailyJourneyStorage';
import { dailyJourneyCapture, processDailyJourneyLocations } from '../dailyJourneyCapture';
jest.mock('../api', () => ({ getAuthSessionSnapshot: jest.fn(), subscribeAuthSessionChange: jest.fn() }));
jest.mock('../auth', () => ({ readPersistedApiAuthToken: jest.fn(), setBackgroundAuthAccess: jest.fn(), recoverBackgroundAuthAccess: jest.fn() }));
jest.mock('../dailyJourney', () => ({ dailyJourneyAPI: { start: jest.fn(), state: jest.fn(), get: jest.fn(), points: jest.fn(), remove: jest.fn() }, dailyJourneyError: () => '同步失败' }));
jest.mock('../dailyJourneyStorage', () => ({ journeyStorage: { installation: jest.fn(), read: jest.fn(), write: jest.fn(), clear: jest.fn() } }));
jest.mock('../../config/releaseCapabilities', () => ({ hasDailyJourneyNativeCapability: jest.fn() }));
jest.mock('expo-modules-core', () => ({ uuid: { v4: jest.fn() } }));
jest.mock('expo-task-manager', () => ({ defineTask: jest.fn(), isTaskDefined: () => false }));
jest.mock('expo-location', () => ({ requestForegroundPermissionsAsync: jest.fn(), requestBackgroundPermissionsAsync: jest.fn(), getForegroundPermissionsAsync: jest.fn(), getBackgroundPermissionsAsync: jest.fn(), startLocationUpdatesAsync: jest.fn(), stopLocationUpdatesAsync: jest.fn(), hasStartedLocationUpdatesAsync: jest.fn(), Accuracy: { Balanced: 3 }, ActivityType: { Other: 1 } }));
const now = new Date('2026-10-18T04:00:00Z').getTime();
const authListener = (subscribeAuthSessionChange as jest.Mock).mock.calls[0][0] as () => void;
const session = { id: 'session', client_id: 'install', local_date: '2026-10-18', timezone: 'Asia/Shanghai', status: 'active', version: 1, segment: 1, started_at: new Date(now).toISOString(), deadline_at: '2026-10-18T16:00:00Z', expires_at: '2026-10-25T16:00:00Z', retention_days: 7, point_count: 0, ended_at: null };
const position = (time = now + 1000) => ({ timestamp: time, coords: { latitude: 31, longitude: 121, accuracy: 12, speed: 0 } });
let stored: any; let token = 'owner-A'; let generation = 0;
beforeEach(async () => {
  jest.clearAllMocks(); stored = null; token = 'owner-A'; generation = 0;
  jest.spyOn(Date, 'now').mockReturnValue(now + 2000);
  (uuid.v4 as jest.Mock).mockReturnValue('uuid');
  (getAuthSessionSnapshot as jest.Mock).mockImplementation(() => ({ token, generation, initialized: true }));
  (readPersistedApiAuthToken as jest.Mock).mockImplementation(async () => token);
  (setBackgroundAuthAccess as jest.Mock).mockResolvedValue(undefined);
  (journeyStorage.installation as jest.Mock).mockResolvedValue('install');
  (journeyStorage.read as jest.Mock).mockImplementation(async () => stored);
  (journeyStorage.write as jest.Mock).mockImplementation(async value => { stored = JSON.parse(JSON.stringify(value)); });
  (journeyStorage.clear as jest.Mock).mockImplementation(async () => { stored = null; });
  (hasDailyJourneyNativeCapability as jest.Mock).mockReturnValue(true);
  for (const fn of [Location.requestForegroundPermissionsAsync, Location.requestBackgroundPermissionsAsync, Location.getForegroundPermissionsAsync, Location.getBackgroundPermissionsAsync]) (fn as jest.Mock).mockResolvedValue({ granted: true });
  (Location.hasStartedLocationUpdatesAsync as jest.Mock).mockResolvedValue(true);
  (Location.startLocationUpdatesAsync as jest.Mock).mockResolvedValue(undefined);
  (Location.stopLocationUpdatesAsync as jest.Mock).mockResolvedValue(undefined);
  (dailyJourneyAPI.start as jest.Mock).mockResolvedValue(session);
  (dailyJourneyAPI.get as jest.Mock).mockResolvedValue(session);
  (dailyJourneyAPI.state as jest.Mock).mockImplementation(async (_id, body) => ({ ...session, status: body.action === 'resume' ? 'active' : body.action === 'end' ? 'ended' : 'paused', version: 2, segment: body.action === 'resume' ? 2 : 1 }));
  (dailyJourneyAPI.points as jest.Mock).mockResolvedValue({ accepted: 1, duplicate: 0, session });
  await dailyJourneyCapture.clearForAuthChange(); jest.clearAllMocks();
});
afterEach(() => jest.restoreAllMocks());
const start = () => dailyJourneyCapture.start({ retentionDays: 7, consent: true });
it('requires explicit consent and native capability before asking permission', async () => {
  await expect(dailyJourneyCapture.start({ retentionDays: 7, consent: false as any })).rejects.toThrow();
  (hasDailyJourneyNativeCapability as jest.Mock).mockReturnValue(false);
  await expect(start()).rejects.toThrow();
  expect(Location.requestForegroundPermissionsAsync).not.toHaveBeenCalled();
  expect(dailyJourneyAPI.start).not.toHaveBeenCalled();
});
it('background denial never creates a session or starts native collection', async () => {
  (Location.requestBackgroundPermissionsAsync as jest.Mock).mockResolvedValue({ granted: false });
  await expect(start()).rejects.toThrow();
  expect(dailyJourneyAPI.start).not.toHaveBeenCalled();
  expect(Location.startLocationUpdatesAsync).not.toHaveBeenCalled();
  expect(dailyJourneyCapture.getSnapshot().status).not.toBe('active');
});
it('registration failure stops locally and reports interruption', async () => {
  (Location.startLocationUpdatesAsync as jest.Mock).mockRejectedValue(new Error('native private details'));
  await expect(start()).rejects.toThrow();
  expect(dailyJourneyCapture.getSnapshot().status).toBe('interrupted');
  expect(dailyJourneyCapture.getSnapshot().error).not.toContain('native private');
  expect(stored.pendingAction).toBe('pause');
});
it('persists points before upload, keeps offline queue, and passes exact owner token', async () => {
  await start();
  (dailyJourneyAPI.points as jest.Mock).mockRejectedValue(new Error('offline'));
  await processDailyJourneyLocations([position()] as any);
  expect(stored.points).toHaveLength(1);
  expect(dailyJourneyCapture.getSnapshot()).toMatchObject({ pendingCount: 1, offline: true });
  expect(dailyJourneyAPI.points).toHaveBeenCalledWith('session', expect.objectContaining({ segment: 1 }), 'owner-A');
});
it('pause persists stopped state before network and blocks delayed GPS', async () => {
  await start();
  (dailyJourneyAPI.state as jest.Mock).mockImplementation(async () => { expect(stored.status).toBe('paused'); throw new Error('offline'); });
  await dailyJourneyCapture.pause();
  await processDailyJourneyLocations([position()] as any);
  expect(stored.points).toEqual([]);
  expect(dailyJourneyAPI.points).not.toHaveBeenCalled();
  expect(dailyJourneyCapture.getSnapshot()).toMatchObject({ status: 'paused', offline: true });
});
it('an account switch while start awaits cannot install a task or rebind ownership', async () => {
  let resolve!: (s: any) => void;
  (dailyJourneyAPI.start as jest.Mock).mockImplementation(() => new Promise(r => { resolve = r; }));
  const pending = start();
  for (let i = 0; i < 30 && !resolve; i += 1) await Promise.resolve();
  token = 'owner-B'; generation += 1;
  await dailyJourneyCapture.clearForAuthChange(); resolve(session);
  await expect(pending).rejects.toThrow();
  expect(Location.startLocationUpdatesAsync).not.toHaveBeenCalled();
  expect(stored).toBeNull();
});
it('midnight stops callbacks and never creates another daily session', async () => {
  await start();
  jest.spyOn(Date, 'now').mockReturnValue(new Date(session.deadline_at).getTime() + 1);
  await processDailyJourneyLocations([position(new Date(session.deadline_at).getTime() + 1)] as any);
  expect(dailyJourneyCapture.getSnapshot().status).toBe('ended');
  expect(dailyJourneyAPI.points).not.toHaveBeenCalled();
  expect(dailyJourneyAPI.start).toHaveBeenCalledTimes(1);
});
it('old callback cannot apply an upload response after a local pause', async () => {
  await start(); let resolve!: (s: any) => void;
  (dailyJourneyAPI.points as jest.Mock).mockImplementation(() => new Promise(r => { resolve = r; }));
  const pending = processDailyJourneyLocations([position()] as any);
  for (let i = 0; i < 40 && !resolve; i += 1) await Promise.resolve();
  await dailyJourneyCapture.pause(); resolve({ accepted: 1, session }); await pending;
  expect(dailyJourneyCapture.getSnapshot().status).toBe('paused');
  expect(stored.status).toBe('paused');
});
it('resume cannot continue another session after permissions await and account cleanup', async () => {
  await start(); await dailyJourneyCapture.pause();
  let resolve!: (value: any) => void;
  (Location.requestBackgroundPermissionsAsync as jest.Mock).mockImplementationOnce(() => new Promise(r => { resolve = r; }));
  const pending = dailyJourneyCapture.resume();
  for (let i = 0; i < 10 && !resolve; i += 1) await Promise.resolve();
  await dailyJourneyCapture.clearForAuthChange(); token = 'owner-B'; generation += 1;
  await start(); const before = (dailyJourneyAPI.state as jest.Mock).mock.calls.length;
  resolve({ granted: true });
  await expect(pending).rejects.toThrow();
  expect(dailyJourneyAPI.state).toHaveBeenCalledTimes(before);
});
it('failed start retries the same idempotency key and clears stale pending pause', async () => {
  (dailyJourneyAPI.start as jest.Mock).mockRejectedValueOnce(new Error('timeout'));
  await expect(start()).rejects.toThrow();
  await start();
  const bodies = (dailyJourneyAPI.start as jest.Mock).mock.calls.map(call => call[0]);
  expect(bodies[0].request_id).toBe(bodies[1].request_id);
  expect(stored.pendingAction).toBeNull();
  await processDailyJourneyLocations([position()] as any);
  expect(dailyJourneyAPI.points).toHaveBeenCalledTimes(1);
});
it.each([[7, 1], [1, 7]] as const)('rejects retention change %s to %s while start is unconfirmed, then restores the exact original request', async (original, changed) => {
  (dailyJourneyAPI.start as jest.Mock).mockRejectedValueOnce(new Error('timeout'));
  await expect(dailyJourneyCapture.start({ retentionDays: original, consent: true })).rejects.toThrow();
  const pending = JSON.parse(JSON.stringify(stored));
  const permissionCalls = (Location.requestForegroundPermissionsAsync as jest.Mock).mock.calls.length;
  const credentialCalls = (setBackgroundAuthAccess as jest.Mock).mock.calls.length;
  await expect(dailyJourneyCapture.start({ retentionDays: changed, consent: true })).rejects.toThrow(`保留 ${original} 天`);
  expect(dailyJourneyAPI.start).toHaveBeenCalledTimes(1);
  expect(stored).toEqual(pending);
  expect(Location.requestForegroundPermissionsAsync).toHaveBeenCalledTimes(permissionCalls);
  expect(setBackgroundAuthAccess).toHaveBeenCalledTimes(credentialCalls);
  expect(dailyJourneyCapture.getSnapshot().error).toContain(`请选择原来的 ${original} 天`);
  (dailyJourneyAPI.start as jest.Mock).mockResolvedValue({ ...session, retention_days: original });
  await dailyJourneyCapture.start({ retentionDays: original, consent: true });
  const requests = (dailyJourneyAPI.start as jest.Mock).mock.calls.map(call => call[0]);
  expect(requests).toHaveLength(2);
  expect(requests[1]).toEqual(requests[0]);
  expect(stored.session.retention_days).toBe(original);
  expect(dailyJourneyCapture.getSnapshot()).toMatchObject({ status: 'active', error: null });
  await dailyJourneyCapture.remove('session');
  expect(stored).toBeNull();
  (uuid.v4 as jest.Mock).mockReturnValue('new-request');
  (dailyJourneyAPI.start as jest.Mock).mockResolvedValue({ ...session, id: 'new-session', retention_days: changed });
  await dailyJourneyCapture.start({ retentionDays: changed, consent: true });
  expect(dailyJourneyAPI.start).toHaveBeenLastCalledWith(expect.objectContaining({ request_id: 'new-request', retention_days: changed }), 'owner-A');
  expect(stored.session.retention_days).toBe(changed);
});
it('cold hydration also rejects a changed retention without replacing the saved request', async () => {
  (dailyJourneyAPI.start as jest.Mock).mockRejectedValueOnce(new Error('timeout'));
  await expect(start()).rejects.toThrow();
  const pending = stored;
  await dailyJourneyCapture.clearForAuthChange(); stored = pending;
  await expect(dailyJourneyCapture.start({ retentionDays: 1, consent: true })).rejects.toThrow('保留 7 天');
  expect(dailyJourneyAPI.start).toHaveBeenCalledTimes(1);
  expect(stored.requestId).toBe(pending.requestId);
  expect(stored.retentionDays).toBe(7);
});
it('rechecks background permission on every native callback', async () => {
  await start();
  (Location.getBackgroundPermissionsAsync as jest.Mock).mockResolvedValue({ granted: false });
  await processDailyJourneyLocations([position()] as any);
  expect(dailyJourneyCapture.getSnapshot().status).toBe('interrupted');
  expect(dailyJourneyAPI.points).not.toHaveBeenCalled();
  expect(Location.stopLocationUpdatesAsync).toHaveBeenCalled();
});
it('stops visibly on bounded queue overflow', async () => {
  await start();
  (dailyJourneyAPI.points as jest.Mock).mockRejectedValue(new Error('offline'));
  await processDailyJourneyLocations(Array.from({ length: 513 }, () => position()) as any);
  expect(dailyJourneyCapture.getSnapshot()).toMatchObject({ status: 'interrupted', error: expect.stringContaining('已满') });
  expect(dailyJourneyAPI.points).not.toHaveBeenCalled();
});
it('does not upload a sample that cannot be stored securely', async () => {
  await start();
  (journeyStorage.write as jest.Mock).mockRejectedValueOnce(new Error('keychain full'));
  await processDailyJourneyLocations([position()] as any);
  expect(dailyJourneyCapture.getSnapshot().status).toBe('interrupted');
  expect(dailyJourneyAPI.points).not.toHaveBeenCalled();
});
it('purges expired queue on initialize and stops native task', async () => {
  await start(); jest.spyOn(Date, 'now').mockReturnValue(Date.parse(session.expires_at) + 1);
  await dailyJourneyCapture.initialize();
  expect(stored).toBeNull();
  expect(dailyJourneyCapture.getSnapshot().status).toBe('idle');
});
it('headless hydration purges owner A queue when durable auth belongs to B', async () => {
  await start();
  (getAuthSessionSnapshot as jest.Mock).mockReturnValue({ token: null, generation: 0, initialized: false });
  (readPersistedApiAuthToken as jest.Mock).mockResolvedValue('owner-B');
  await dailyJourneyCapture.initialize();
  expect(stored).toBeNull();
  expect(dailyJourneyAPI.points).not.toHaveBeenCalled();
});
it('resume discards native samples buffered before the new recording segment', async () => {
  await start(); await dailyJourneyCapture.pause(); await dailyJourneyCapture.resume();
  await processDailyJourneyLocations([position(now + 1000)] as any);
  expect(dailyJourneyAPI.points).not.toHaveBeenCalled();
});
it('retains queued observations on offline end and uploads them when ended state is confirmed', async () => {
  await start(); (dailyJourneyAPI.points as jest.Mock).mockRejectedValueOnce(new Error('offline'));
  await processDailyJourneyLocations([position()] as any);
  (dailyJourneyAPI.state as jest.Mock).mockRejectedValueOnce(new Error('offline'));
  await dailyJourneyCapture.end();
  expect(stored.points).toHaveLength(1);
  (dailyJourneyAPI.points as jest.Mock).mockResolvedValue({ accepted: 1, duplicate: 0, session: { ...session, status: 'ended', version: 2 } });
  await dailyJourneyCapture.flush();
  expect(dailyJourneyCapture.getSnapshot()).toMatchObject({ status: 'ended', pendingCount: 0, offline: false });
});
it('does not resume while the old recording segment has pending points', async () => {
  await start(); (dailyJourneyAPI.points as jest.Mock).mockRejectedValue(new Error('offline'));
  await processDailyJourneyLocations([position()] as any);
  await dailyJourneyCapture.pause();
  await expect(dailyJourneyCapture.resume()).rejects.toThrow();
  expect((dailyJourneyAPI.state as jest.Mock).mock.calls.some(call => call[1].action === 'resume')).toBe(false);
  expect(stored.points).toHaveLength(1);
});
it('cannot replace an ended offline queue by starting a new session', async () => {
  await start(); (dailyJourneyAPI.points as jest.Mock).mockRejectedValue(new Error('offline'));
  await processDailyJourneyLocations([position()] as any);
  await dailyJourneyCapture.end();
  await expect(start()).rejects.toThrow();
  expect(dailyJourneyAPI.start).toHaveBeenCalledTimes(1);
  expect(stored.points).toHaveLength(1);
});
it('queue overflow keeps the previous encrypted points for later synchronization', async () => {
  await start(); (dailyJourneyAPI.points as jest.Mock).mockRejectedValue(new Error('offline'));
  await processDailyJourneyLocations(Array.from({ length: 512 }, () => position()) as any);
  await processDailyJourneyLocations([position()] as any);
  expect(dailyJourneyCapture.getSnapshot()).toMatchObject({ status: 'interrupted', pendingCount: 512 });
  expect(stored.points).toHaveLength(512);
});
it('state conflict reads back an already ended session without replaying a write', async () => {
  await start();
  (dailyJourneyAPI.state as jest.Mock).mockRejectedValue({ response: { status: 409 } });
  (dailyJourneyAPI.get as jest.Mock).mockResolvedValue({ ...session, status: 'ended', version: 4 });
  await dailyJourneyCapture.end();
  expect(stored).toBeNull();
  expect(dailyJourneyCapture.getSnapshot()).toMatchObject({ status: 'ended', offline: false });
  expect(dailyJourneyAPI.state).toHaveBeenCalledTimes(1);
});
it('offline delete survives midnight initialization instead of becoming an end', async () => {
  await start();
  (dailyJourneyAPI.remove as jest.Mock).mockRejectedValueOnce(new Error('offline'));
  await expect(dailyJourneyCapture.remove('session')).rejects.toThrow('尚未确认');
  expect(stored.pendingAction).toBe('delete');
  jest.spyOn(Date, 'now').mockReturnValue(new Date(session.deadline_at).getTime() + 1);
  (dailyJourneyAPI.remove as jest.Mock).mockResolvedValue(undefined);
  await dailyJourneyCapture.initialize();
  expect(dailyJourneyAPI.remove).toHaveBeenCalledTimes(2);
  expect(dailyJourneyAPI.state).not.toHaveBeenCalled();
  expect(stored).toBeNull();
});
it('keeps pre-midnight samples in a delayed batch while rejecting samples after cutoff', async () => {
  await start();
  const midnight = Date.parse(session.deadline_at);
  jest.spyOn(Date, 'now').mockReturnValue(midnight + 2000);
  (dailyJourneyAPI.points as jest.Mock).mockResolvedValue({ accepted: 1, duplicate: 0, session: { ...session, status: 'ended', version: 2 } });
  await processDailyJourneyLocations([position(midnight - 1000), position(midnight + 1000)] as any);
  expect(dailyJourneyAPI.points).toHaveBeenCalledWith('session', expect.objectContaining({ points: [expect.objectContaining({ recorded_at: new Date(midnight - 1000).toISOString() })] }), 'owner-A');
  expect(dailyJourneyCapture.getSnapshot().status).toBe('ended');
});
it('headless cold delivery retains pre-midnight samples before applying the daily cutoff', async () => {
  await start(); const persisted = stored;
  await dailyJourneyCapture.clearForAuthChange(); stored = persisted;
  const midnight = Date.parse(session.deadline_at);
  jest.spyOn(Date, 'now').mockReturnValue(midnight + 2000);
  (dailyJourneyAPI.points as jest.Mock).mockResolvedValue({ accepted: 1, duplicate: 0, session: { ...session, status: 'ended', version: 2 } });
  await processDailyJourneyLocations([position(midnight - 1000)] as any);
  expect(dailyJourneyAPI.points).toHaveBeenCalledTimes(1);
  expect(dailyJourneyCapture.getSnapshot().status).toBe('ended');
});
it('starting before page initialization cannot replace a durable unfinished session', async () => {
  await start(); const persisted = stored;
  await dailyJourneyCapture.clearForAuthChange(); stored = persisted;
  await expect(start()).rejects.toThrow();
  expect(dailyJourneyAPI.start).toHaveBeenCalledTimes(1);
  expect(stored.session.id).toBe('session');
});
it('delete before page initialization still clears the matching local queue', async () => {
  await start(); const persisted = stored;
  await dailyJourneyCapture.clearForAuthChange(); stored = persisted;
  (dailyJourneyAPI.remove as jest.Mock).mockResolvedValue(undefined);
  await dailyJourneyCapture.remove('session');
  expect(stored).toBeNull();
  expect(dailyJourneyCapture.getSnapshot().status).toBe('idle');
});
it('normal same-owner login hydration preserves the existing background session', async () => {
  await start(); const persisted = stored;
  await dailyJourneyCapture.clearForAuthChange(); stored = persisted;
  authListener(); await dailyJourneyCapture.initialize();
  expect(stored.session.id).toBe('session');
  expect(dailyJourneyCapture.getSnapshot().status).toBe('active');
});
it('a different owner login hydration removes the old durable session', async () => {
  await start(); const persisted = stored;
  await dailyJourneyCapture.clearForAuthChange(); stored = persisted;
  token = 'owner-B'; generation += 1;
  authListener(); await dailyJourneyCapture.initialize();
  expect(stored).toBeNull();
  expect(dailyJourneyCapture.getSnapshot().status).toBe('idle');
});
it('a definitive remote 404 clears queued points and restores foreground-only credentials', async () => {
  await start();
  (dailyJourneyAPI.points as jest.Mock).mockRejectedValue({ response: { status: 404 } });
  await processDailyJourneyLocations([position()] as any);
  expect(stored).toBeNull();
  expect(setBackgroundAuthAccess).toHaveBeenLastCalledWith(false, 'owner-A', expect.objectContaining({ isCurrent: expect.any(Function) }));
  expect(dailyJourneyCapture.getSnapshot().status).toBe('idle');
});
it('a terminal 410 from state synchronization also restores credentials and clears the queue', async () => {
  await start();
  (dailyJourneyAPI.state as jest.Mock).mockRejectedValue({ response: { status: 410 } });
  await dailyJourneyCapture.end();
  expect(stored).toBeNull();
  expect(setBackgroundAuthAccess).toHaveBeenLastCalledWith(false, 'owner-A', expect.any(Object));
});
it('ending an uncertain start never reports a confirmed cloud end', async () => {
  (dailyJourneyAPI.start as jest.Mock).mockRejectedValue(new Error('timeout'));
  await expect(start()).rejects.toThrow();
  await expect(dailyJourneyCapture.end()).rejects.toThrow('未确认');
});
it('native stop begins even while secure persistence is stalled', async () => {
  await start(); let resolve!: () => void;
  (journeyStorage.write as jest.Mock).mockImplementationOnce(() => new Promise<void>(r => { resolve = r; }));
  const pending = dailyJourneyCapture.pause();
  for (let i = 0; i < 30; i += 1) await Promise.resolve();
  expect(Location.stopLocationUpdatesAsync).toHaveBeenCalled();
  resolve(); await pending;
});
it('empty startup recovers interrupted credential expansion, but not during an explicit start', async () => {
  await dailyJourneyCapture.initialize();
  expect(recoverBackgroundAuthAccess).toHaveBeenCalledTimes(1);
  let resolve!: () => void;
  (setBackgroundAuthAccess as jest.Mock).mockImplementationOnce(() => new Promise<void>(r => { resolve = r; }));
  const pending = start();
  for (let i = 0; i < 50 && !resolve; i += 1) await Promise.resolve();
  await dailyJourneyCapture.initialize();
  expect(recoverBackgroundAuthAccess).toHaveBeenCalledTimes(1);
  resolve(); await pending;
  expect(dailyJourneyCapture.getSnapshot().status).toBe('active');
});
