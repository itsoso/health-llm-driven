describe('services/api auth failure handling', () => {
  let responseRejected: ((error: any) => Promise<never>) | undefined;
  let unauthorized: jest.Mock;

  beforeEach(() => {
    jest.resetModules();
    responseRejected = undefined;
    unauthorized = jest.fn();

    jest.doMock('axios', () => ({
      __esModule: true,
      default: {
        create: jest.fn(() => ({
          interceptors: {
            request: { use: jest.fn() },
            response: {
              use: jest.fn((_ok, rejected) => {
                responseRejected = rejected;
              }),
            },
          },
        })),
      },
    }));
  });

  it('does not erase the persisted token for an incidental 401 response', async () => {
    const SecureStore = require('expo-secure-store');
    const shared = require('../../modules/shared-keychain');
    const { setOnUnauthorized } = require('../api');
    setOnUnauthorized(unauthorized);

    await expect(
      responseRejected?.({
        response: { status: 401 },
        config: { url: '/action-cards' },
      }),
    ).rejects.toMatchObject({ response: { status: 401 } });

    expect(SecureStore.deleteItemAsync).not.toHaveBeenCalled();
    expect(shared.deleteTokenFromSharedKeychain).not.toHaveBeenCalled();
    expect(unauthorized).toHaveBeenCalledTimes(1);
  });
});
