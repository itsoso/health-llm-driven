describe('services/api auth failure handling', () => {
  let requestFulfilled: ((config: any) => Promise<any>) | undefined;
  let responseRejected: ((error: any) => Promise<never>) | undefined;
  let unauthorized: jest.Mock;
  let enforceAppEgressAllowed: jest.Mock;

  beforeEach(() => {
    jest.resetModules();
    requestFulfilled = undefined;
    responseRejected = undefined;
    unauthorized = jest.fn();
    enforceAppEgressAllowed = jest.fn().mockResolvedValue(undefined);

    jest.doMock('axios', () => ({
      __esModule: true,
      default: {
        create: jest.fn(() => ({
          interceptors: {
            request: {
              use: jest.fn((fulfilled) => {
                requestFulfilled = fulfilled;
              }),
            },
            response: {
              use: jest.fn((_ok, rejected) => {
                responseRejected = rejected;
              }),
            },
          },
        })),
      },
    }));
    jest.doMock('../egressPolicy', () => ({
      enforceAppEgressAllowed,
    }));
  });

  it('rejects AI upload before transport when disclosure is declined even with explicit-cloud flag', async () => {
    const { setRuntimeAuthToken } = require('../api');
    const { requireAIConsent } = require('../aiConsent');
    setRuntimeAuthToken('session-a');
    requireAIConsent.mockRejectedValueOnce(new Error('ai_consent_required'));
    const headers = { get: () => '1', delete: jest.fn() };
    await expect(requestFulfilled?.({ headers, method: 'post', url: '/diet/recognize' })).rejects.toThrow('ai_consent_required');
  });

  it('invalidates cached consent on the server policy-required response', async () => {
    const { setRuntimeAuthToken } = require('../api');
    const state = require('../aiConsentState');
    setRuntimeAuthToken('session-a');
    state.acceptAIConsentRevision(state.aiConsentRevision());
    const error = { response: { status: 403, data: { detail: { code: 'ai_consent_required' } } } };
    await expect(responseRejected?.(error)).rejects.toBe(error);
    expect(state.hasAIConsent()).toBe(false);
  });

  it.each([
    '/medical-exams/import/image', '/medical-exams/import/pdf',
    '/prescriptions/recognize', '/ambient/audio-inputs', '/ambient/visual-inputs',
    '/diet/estimate-nutrition?food_description=private',
  ])('blocks sensitive AI upload before transport: %s', async (url) => {
    const { setRuntimeAuthToken } = require('../api');
    const { requireAIConsent } = require('../aiConsent');
    setRuntimeAuthToken('session-a');
    requireAIConsent.mockRejectedValueOnce(new Error('ai_consent_required'));
    await expect(requestFulfilled?.({ headers: { get: jest.fn(), delete: jest.fn() }, method: 'post', url })).rejects.toThrow('ai_consent_required');
  });

  it.each(['/water/records', '/diet/records', '/ambient/meal-sessions/42/abort', '/auth/me/deletion-request'])('allows non-AI record management after declining: %s', async (url) => {
    const { setRuntimeAuthToken } = require('../api');
    const { requireAIConsent } = require('../aiConsent');
    setRuntimeAuthToken('session-a');
    await expect(requestFulfilled?.({ headers: { get: jest.fn(), delete: jest.fn() }, method: 'post', url })).resolves.toMatchObject({ url });
    expect(requireAIConsent).not.toHaveBeenCalled();
  });

  it('rejects a consent write bound to a session that changed while awaiting dispatch', async () => {
    const { setRuntimeAuthToken } = require('../api');
    const state = require('../aiConsentState');
    setRuntimeAuthToken('session-a');
    const oldRevision = state.aiConsentRevision();
    setRuntimeAuthToken('session-b');
    const headers = { get: jest.fn(), delete: jest.fn() };
    await expect(requestFulfilled?.({ headers, method: 'put', url: '/auth/ai-consent', __revaConsentRevision: oldRevision })).rejects.toThrow('auth_session_changed');
  });

  it.each([
    '/auth/login/json',
    '/auth/phone/code',
    '/auth/phone/login?source=app',
  ])('allows the exact login bootstrap endpoint before a cloud session: %s', async (url) => {
    require('../api');
    const headers = {
      get: jest.fn(() => undefined),
      delete: jest.fn(),
    } as any;

    await requestFulfilled?.({ headers, method: 'post', url });

    expect(enforceAppEgressAllowed).toHaveBeenCalledWith({
      explicitCloudAI: false,
      cloudSessionBootstrap: true,
      cloudCredentialPresent: false,
    });
  });

  it.each([
    { method: 'get', url: '/auth/login/json' },
    { method: 'post', url: '/auth/me' },
    { method: 'post', url: '/agent/chat' },
  ])('keeps non-bootstrap traffic behind the cloud session: $method $url', async (request) => {
    require('../api');
    const headers = {
      get: jest.fn(() => undefined),
      delete: jest.fn(),
    } as any;

    await requestFulfilled?.({ headers, ...request });

    expect(enforceAppEgressAllowed).toHaveBeenCalledWith({
      explicitCloudAI: false,
      cloudSessionBootstrap: false,
      cloudCredentialPresent: false,
    });
  });

  it('uses a persisted token to bootstrap authenticated session recovery', async () => {
    const SecureStore = require('expo-secure-store');
    SecureStore.getItemAsync.mockResolvedValueOnce('tok_saved');
    require('../api');
    const headers = {
      get: jest.fn(() => undefined),
      delete: jest.fn(),
    } as any;

    await requestFulfilled?.({ headers, method: 'get', url: '/auth/me' });

    expect(enforceAppEgressAllowed).toHaveBeenCalledWith({
      explicitCloudAI: false,
      cloudSessionBootstrap: false,
      cloudCredentialPresent: true,
    });
    expect(headers.Authorization).toBe('Bearer tok_saved');
  });

  it('uses the runtime token when SecureStore is temporarily unavailable after login', async () => {
    const SecureStore = require('expo-secure-store');
    SecureStore.getItemAsync.mockRejectedValueOnce(new Error('keychain locked'));
    const { setRuntimeAuthToken } = require('../api');
    const headers = {
      get: jest.fn(() => undefined),
      delete: jest.fn(),
    } as any;

    setRuntimeAuthToken('tok_runtime');
    await requestFulfilled?.({ headers });

    expect(headers.Authorization).toBe('Bearer tok_runtime');
    expect(SecureStore.getItemAsync).not.toHaveBeenCalled();
  });

  it('never sends the web cookie session sentinel as a native bearer token', async () => {
    const SecureStore = require('expo-secure-store');
    SecureStore.getItemAsync.mockResolvedValueOnce('__web_cookie_session__');
    const { setRuntimeAuthToken } = require('../api');
    const headers = {
      get: jest.fn(() => undefined),
      delete: jest.fn(),
    } as any;

    setRuntimeAuthToken('__web_cookie_session__');
    await requestFulfilled?.({ headers });

    expect(headers.Authorization).toBeUndefined();
  });

  it('asks auth to revalidate when a business request receives a current-session 401', async () => {
    const SecureStore = require('expo-secure-store');
    const shared = require('../../modules/shared-keychain');
    const { setOnUnauthorized, setRuntimeAuthToken } = require('../api');
    setOnUnauthorized(unauthorized);
    setRuntimeAuthToken('tok_current');

    await expect(
      responseRejected?.({
        response: { status: 401 },
        config: { url: '/action-cards', __revaAuthToken: 'tok_current' },
      }),
    ).rejects.toMatchObject({ response: { status: 401 } });

    expect(SecureStore.deleteItemAsync).not.toHaveBeenCalled();
    expect(shared.deleteTokenFromSharedKeychain).not.toHaveBeenCalled();
    expect(unauthorized).toHaveBeenCalledTimes(1);
  });

  it('leaves /auth/me 401 handling to the session validator to avoid recursive logout', async () => {
    const { setOnUnauthorized, setRuntimeAuthToken } = require('../api');
    setOnUnauthorized(unauthorized);
    setRuntimeAuthToken('tok_current');

    await expect(
      responseRejected?.({
        response: { status: 401 },
        config: { url: '/auth/me', __revaAuthToken: 'tok_current' },
      }),
    ).rejects.toMatchObject({ response: { status: 401 } });

    expect(unauthorized).not.toHaveBeenCalled();
  });

  it('does not invalidate an existing session when a new login attempt is rejected', async () => {
    const { setOnUnauthorized, setRuntimeAuthToken } = require('../api');
    setOnUnauthorized(unauthorized);
    setRuntimeAuthToken('tok_current');

    await expect(
      responseRejected?.({
        response: { status: 401 },
        config: { url: '/auth/login/json', __revaAuthToken: 'tok_current' },
      }),
    ).rejects.toMatchObject({ response: { status: 401 } });

    expect(unauthorized).not.toHaveBeenCalled();
  });

  it('ignores a delayed 401 from a request that used an older token', async () => {
    const { setOnUnauthorized, setRuntimeAuthToken } = require('../api');
    setOnUnauthorized(unauthorized);
    setRuntimeAuthToken('tok_new');

    await expect(
      responseRejected?.({
        response: { status: 401 },
        config: { url: '/auth/me', __revaAuthToken: 'tok_old' },
      }),
    ).rejects.toMatchObject({ response: { status: 401 } });

    expect(unauthorized).not.toHaveBeenCalled();
  });

  it('records the token used by a request so its eventual 401 can be scoped', async () => {
    const { setRuntimeAuthToken } = require('../api');
    const headers = {
      get: jest.fn(() => undefined),
      delete: jest.fn(),
    } as any;
    const config = { headers } as any;

    setRuntimeAuthToken('tok_request');
    await requestFulfilled?.(config);

    expect(config.__revaAuthToken).toBe('tok_request');
  });
});
jest.mock('../aiConsent', () => ({ requireAIConsent: jest.fn().mockResolvedValue(undefined) }));
