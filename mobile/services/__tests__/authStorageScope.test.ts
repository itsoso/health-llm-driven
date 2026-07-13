const mockGetToken = jest.fn();

jest.mock('../auth', () => ({
  getToken: (...args: any[]) => mockGetToken(...args),
}));

import { authStorageScopeFromToken, getAuthStorageScope } from '../authStorageScope';

describe('authStorageScope', () => {
  beforeEach(() => jest.clearAllMocks());

  it('derives a non-sensitive account scope from the signed token subject', () => {
    expect(authStorageScopeFromToken('x.eyJzdWIiOiI0MiJ9.y')).toBe('user-42');
  });

  it.each([
    '',
    'not-a-jwt',
    'x.e30.y',
    'x.eyJzdWIiOiIuLi8xIn0.y',
  ])('rejects an unusable token scope: %s', (token) => {
    expect(authStorageScopeFromToken(token)).toBeNull();
  });

  it('fails closed when no authenticated account can be identified', async () => {
    mockGetToken.mockResolvedValueOnce(null);
    await expect(getAuthStorageScope()).rejects.toThrow('auth_storage_scope_unavailable');
  });

  it('loads the current account scope from secure authentication state', async () => {
    mockGetToken.mockResolvedValueOnce('x.eyJzdWIiOiI3In0.y');
    await expect(getAuthStorageScope()).resolves.toBe('user-7');
  });
});
