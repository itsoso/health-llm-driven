describe('services/api auth failure handling', () => {
  let requestFulfilled: ((config: any) => Promise<any>) | undefined;
  let responseRejected: ((error: any) => Promise<never>) | undefined;
  let unauthorized: jest.Mock;

  beforeEach(() => {
    jest.resetModules();
    requestFulfilled = undefined;
    responseRejected = undefined;
    unauthorized = jest.fn();

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
      enforceAppEgressAllowed: jest.fn().mockResolvedValue(undefined),
    }));
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

  it('notifies auth when the current native session receives a 401 response', async () => {
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
