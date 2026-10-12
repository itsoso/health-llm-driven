jest.mock('../egressPolicy', () => ({ enforceAppEgressAllowed: jest.fn().mockResolvedValue(undefined) }));

describe('actual Axios session dispatch', () => {
  beforeEach(() => { jest.resetModules(); jest.unmock('axios'); });

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
});
