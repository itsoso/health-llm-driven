jest.mock('../egressPolicy', () => ({ enforceAppEgressAllowed: jest.fn().mockResolvedValue(undefined) }));

describe('actual Axios session dispatch', () => {
  beforeEach(async () => {
    jest.resetModules(); jest.unmock('axios');
    await require('@react-native-async-storage/async-storage').clear();
    require('expo-secure-store').getItemAsync.mockReset().mockResolvedValue(null);
  });

  it.each(['get', 'post', 'request', 'call'])('captures the owner before Axios queues %s', async method => {
    const { default: api, setRuntimeAuthToken } = require('../api');
    setRuntimeAuthToken('synthetic-a');
    const adapter = jest.fn().mockResolvedValue({ status: 200, statusText: 'OK', headers: {}, data: {} });
    const config = { adapter };
    const pending = method === 'get' ? api.get('/diet/records', config)
      : method === 'post' ? api.post('/diet/records', {}, config)
      : method === 'request' ? api.request({ ...config, url: '/diet/records' })
      : api({ ...config, url: '/diet/records' });
    setRuntimeAuthToken('synthetic-b');
    await expect(pending).rejects.toThrow('auth_session_changed');
    expect(adapter).not.toHaveBeenCalled();
  });

  it('does not invalidate a new session on an old same-token 401', async () => {
    const { default: api, setRuntimeAuthToken, setOnUnauthorized } = require('../api');
    const unauthorized = jest.fn();
    setOnUnauthorized(unauthorized);
    setRuntimeAuthToken('synthetic-a');
    let reject!: (error: unknown) => void;
    let dispatched!: () => void;
    const started = new Promise<void>(resolve => { dispatched = resolve; });
    let sent: any;
    const pending = api.get('/diet/records', { adapter: (config: any) => {
      sent = config;
      dispatched();
      return new Promise((_, fail) => { reject = fail; });
    } });
    await started;
    setRuntimeAuthToken(null);
    setRuntimeAuthToken('synthetic-a');
    reject({ config: sent, response: { status: 401 } });
    await expect(pending).rejects.toMatchObject({ response: { status: 401 } });
    expect(unauthorized).not.toHaveBeenCalled();
  });

  it('drops a caller-supplied old Authorization header after logout', async () => {
    const { default: api, setRuntimeAuthToken } = require('../api');
    setRuntimeAuthToken(null);
    const adapter = jest.fn(async (config: any) => ({ config, status: 200, statusText: 'OK', headers: {}, data: {} }));
    await api.get('/auth/me', { headers: { Authorization: 'Bearer synthetic-old' }, adapter });
    expect(adapter.mock.calls[0][0].headers.get('Authorization')).toBeUndefined();
  });

  it.each(['present', 'unreadable', 'absent'])('respects the persistent logout barrier on cold startup: %s', async barrier => {
    const storage = require('@react-native-async-storage/async-storage');
    const store = require('expo-secure-store');
    store.getItemAsync.mockResolvedValue('synthetic-residue');
    if (barrier === 'present') await storage.setItem('auth:logout_tombstone:v1', '1');
    if (barrier === 'unreadable') storage.getItem.mockRejectedValueOnce(new Error('synthetic-storage-failure'));
    const { default: api } = require('../api');
    const adapter = jest.fn(async (config: any) => ({ config, status: 200, statusText: 'OK', headers: {}, data: {} }));
    const pending = api.get('/diet/records', { adapter });
    if (barrier === 'unreadable') {
      await expect(pending).rejects.toThrow('auth_storage_unavailable');
      expect(adapter).not.toHaveBeenCalled();
    } else {
      await pending;
      expect(adapter.mock.calls[0][0].headers.get('Authorization')).toBe(
        barrier === 'present' ? undefined : 'Bearer synthetic-residue');
    }
  });

  it('allows explicit new login without an old credential when the barrier is unreadable', async () => {
    const storage = require('@react-native-async-storage/async-storage');
    storage.getItem.mockRejectedValueOnce(new Error('synthetic-storage-failure'));
    require('expo-secure-store').getItemAsync.mockResolvedValue('synthetic-old');
    const { default: api } = require('../api');
    const adapter = jest.fn(async (config: any) => ({ config, status: 200, statusText: 'OK', headers: {}, data: {} }));
    await api.post('/auth/login/json', {}, { adapter });
    expect(adapter.mock.calls[0][0].headers.get('Authorization')).toBeUndefined();
  });

  it('rejects a persisted journey batch bound to a different credential before dispatch', async () => {
    const { default: api, setRuntimeAuthToken } = require('../api');
    setRuntimeAuthToken('synthetic-new-owner');
    const adapter = jest.fn();
    await expect(api.post('/daily-journeys/sessions/synthetic/points', {}, {
      adapter, __revaExpectedAuthToken: 'synthetic-old-owner',
    })).rejects.toThrow('auth_session_changed');
    expect(adapter).not.toHaveBeenCalled();
  });

  it('exposes a copy of the current dispatch identity and advances it even on same-token relogin', () => {
    const { getAuthSessionSnapshot, setRuntimeAuthToken } = require('../api');
    setRuntimeAuthToken('synthetic-owner');
    const before = getAuthSessionSnapshot();
    expect(before).toMatchObject({ token: 'synthetic-owner', initialized: true });
    setRuntimeAuthToken(null);
    setRuntimeAuthToken('synthetic-owner');
    expect(getAuthSessionSnapshot().generation).toBeGreaterThan(before.generation);
    before.token = 'caller-mutated';
    expect(getAuthSessionSnapshot().token).toBe('synthetic-owner');
  });
});
