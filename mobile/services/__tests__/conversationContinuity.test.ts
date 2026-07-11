const storage: Record<string, string> = {};
let mockScope = 'user-7';
let mockFailLegacyCleanup = false;
const assertSecureStoreKey = (key: string) => {
  if (!/^[a-zA-Z0-9._-]+$/.test(key)) throw new Error('invalid secure-store key');
};

jest.mock('@react-native-async-storage/async-storage', () => ({
  __esModule: true,
  default: {
    getItem: jest.fn(async (key: string) => storage[key] ?? null),
    setItem: jest.fn(async (key: string, value: string) => { storage[key] = value; }),
    removeItem: jest.fn(async (key: string) => {
      if (mockFailLegacyCleanup && key === 'chat:conversation_continuity:v1') {
        throw new Error('legacy cleanup unavailable');
      }
      delete storage[key];
    }),
  },
}));

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(async (key: string) => {
    assertSecureStoreKey(key);
    return storage[key] ?? null;
  }),
  setItemAsync: jest.fn(async (key: string, value: string) => {
    assertSecureStoreKey(key);
    storage[key] = value;
  }),
  deleteItemAsync: jest.fn(async (key: string) => {
    assertSecureStoreKey(key);
    delete storage[key];
  }),
}));

jest.mock('../authStorageScope', () => ({
  getAuthStorageScope: jest.fn(async () => mockScope),
}));

import {
  acknowledgePendingWriteReceipt,
  conversationContinuityStorageKey,
  loadPendingWriteReceipt,
  mergeConversationContinuity,
  rememberVerifiedWriteReceipt,
} from '../conversationContinuity';

const receipt = {
  operationId: 'health_record:diet:81',
  status: 'verified' as const,
  resourceType: 'diet_record',
  resourceId: '81',
  completedAt: '2026-07-09T12:00:00.000Z',
  verified: true as const,
};

describe('conversationContinuity', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockScope = 'user-7';
    mockFailLegacyCleanup = false;
    Object.keys(storage).forEach(key => delete storage[key]);
  });

  it('uses a SecureStore-compatible account-scoped key', () => {
    expect(conversationContinuityStorageKey('user-7')).toMatch(/^[a-zA-Z0-9._-]+$/);
  });

  it('persists only a compact verified resource receipt', async () => {
    await rememberVerifiedWriteReceipt(receipt, 1000);

    const storageKey = conversationContinuityStorageKey(mockScope);
    expect(JSON.parse(storage[storageKey])).toEqual({
      version: 1,
      receipt,
      storedAt: 1000,
    });
    await expect(loadPendingWriteReceipt(2000)).resolves.toEqual(receipt);
  });

  it('persists and restores continuity when legacy AsyncStorage cleanup is unavailable', async () => {
    mockFailLegacyCleanup = true;

    await expect(rememberVerifiedWriteReceipt(receipt, 1000)).resolves.toBeUndefined();
    await expect(loadPendingWriteReceipt(2000)).resolves.toEqual(receipt);
  });

  it('merges caller context with a structured latest write receipt', () => {
    const merged = mergeConversationContinuity('{"from":"diet/today"}', receipt);

    expect(JSON.parse(merged || '{}')).toEqual({
      from: 'diet/today',
      continuity: {
        latest_verified_write: {
          operation_id: 'health_record:diet:81',
          resource_type: 'diet_record',
          resource_id: '81',
          completed_at: '2026-07-09T12:00:00.000Z',
          verified: true,
        },
      },
    });
  });

  it('acknowledges only the exact receipt accepted by the server', async () => {
    await rememberVerifiedWriteReceipt(receipt, 1000);

    await acknowledgePendingWriteReceipt('some-newer-operation');
    await expect(loadPendingWriteReceipt(2000)).resolves.toEqual(receipt);

    await acknowledgePendingWriteReceipt(receipt.operationId);
    await expect(loadPendingWriteReceipt(2000)).resolves.toBeUndefined();
  });

  it('prunes stale or malformed continuity snapshots', async () => {
    await rememberVerifiedWriteReceipt(receipt, 1000);
    await expect(loadPendingWriteReceipt(1000 + 24 * 60 * 60 * 1000 + 1)).resolves.toBeUndefined();
    const storageKey = conversationContinuityStorageKey(mockScope);
    expect(storage[storageKey]).toBeUndefined();

    storage[storageKey] = '{bad-json';
    await expect(loadPendingWriteReceipt(2000)).resolves.toBeUndefined();
    expect(storage[storageKey]).toBeUndefined();
  });

  it('does not expose one account receipt to another account', async () => {
    await rememberVerifiedWriteReceipt(receipt, 1000);
    mockScope = 'user-8';

    await expect(loadPendingWriteReceipt(2000)).resolves.toBeUndefined();
    expect(storage[conversationContinuityStorageKey('user-7')]).toBeDefined();
  });
});
