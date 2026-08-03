import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';

import {
  PENDING_REGISTRATION_KEY,
  clearPendingRegistration,
  createPendingRegistration,
  loadPendingRegistration,
} from '../registrationInviteStorage';

function deferred<T = void>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

async function flushMicrotasks(): Promise<void> {
  for (let turn = 0; turn < 20; turn += 1) await Promise.resolve();
}

describe('registrationInviteStorage', () => {
  let secureItems: Record<string, string>;

  beforeEach(() => {
    jest.clearAllMocks();
    secureItems = {};
    (SecureStore.setItemAsync as jest.Mock).mockImplementation(async (key, value) => {
      secureItems[key] = value;
    });
    (SecureStore.getItemAsync as jest.Mock).mockImplementation(
      async (key) => secureItems[key] ?? null,
    );
    (SecureStore.deleteItemAsync as jest.Mock).mockImplementation(async (key) => {
      delete secureItems[key];
    });
  });

  it('stores a versioned allowlisted payload and reuses its stable idempotency key', async () => {
    const pending = await createPendingRegistration({
      verifiedPhoneTicket: 'A'.repeat(32),
      expiresInSeconds: 300,
      phoneMasked: '138****8000',
      nowMs: 1_000,
      generateIdempotencyKey: () => 'registration-1234567890abcdef',
    });

    expect(pending).toEqual({
      version: 1,
      verifiedPhoneTicket: 'A'.repeat(32),
      expiresAt: 301_000,
      idempotencyKey: 'registration-1234567890abcdef',
      phoneMasked: '138****8000',
    });
    expect(await loadPendingRegistration(2_000)).toEqual(pending);
    await expect(createPendingRegistration({
      verifiedPhoneTicket: 'A'.repeat(32),
      expiresInSeconds: 300,
      nowMs: 2_000,
      generateIdempotencyKey: () => {
        throw new Error('must reuse the first key');
      },
    })).resolves.toEqual(pending);
    expect(AsyncStorage.setItem).not.toHaveBeenCalled();
    expect(AsyncStorage.getItem).not.toHaveBeenCalled();
  });

  it('deletes expired and malformed payloads instead of returning credentials', async () => {
    secureItems[PENDING_REGISTRATION_KEY] = JSON.stringify({
      version: 1,
      verifiedPhoneTicket: 'A'.repeat(32),
      expiresAt: 999,
      idempotencyKey: 'registration-1234567890abcdef',
    });
    await expect(loadPendingRegistration(1_000)).resolves.toBeNull();
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith(PENDING_REGISTRATION_KEY);

    secureItems[PENDING_REGISTRATION_KEY] = JSON.stringify({
      version: 1,
      verifiedPhoneTicket: 'A'.repeat(32),
      expiresAt: 5_000,
      idempotencyKey: 'registration-1234567890abcdef',
      unexpectedSecret: 'must-not-be-accepted',
    });
    await expect(loadPendingRegistration(1_000)).resolves.toBeNull();
    expect(secureItems[PENDING_REGISTRATION_KEY]).toBeUndefined();
  });

  it('rejects oversized raw payloads before JSON parsing', async () => {
    secureItems[PENDING_REGISTRATION_KEY] = `{"padding":"${'x'.repeat(5_000)}"}`;
    const parseSpy = jest.spyOn(JSON, 'parse');

    await expect(loadPendingRegistration()).resolves.toBeNull();

    expect(parseSpy).not.toHaveBeenCalled();
    expect(secureItems[PENDING_REGISTRATION_KEY]).toBeUndefined();
    parseSpy.mockRestore();
  });

  it('fails explicitly when SecureStore cannot durably persist the pending ticket', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(null);

    await expect(createPendingRegistration({
      verifiedPhoneTicket: 'A'.repeat(32),
      expiresInSeconds: 300,
      generateIdempotencyKey: () => 'registration-1234567890abcdef',
    })).rejects.toThrow('待注册状态无法安全保存');
  });

  it('cleans only its own candidate after readback failure', async () => {
    let reads = 0;
    (SecureStore.getItemAsync as jest.Mock).mockImplementation(async (key) => {
      reads += 1;
      if (reads === 1) return null;
      if (reads === 2) throw new Error('transient readback failure');
      return secureItems[key] ?? null;
    });

    await expect(createPendingRegistration({
      verifiedPhoneTicket: 'C'.repeat(32),
      expiresInSeconds: 300,
      generateIdempotencyKey: () => 'registration-candidate-1234',
    })).rejects.toThrow('待注册状态无法安全保存');

    expect(secureItems[PENDING_REGISTRATION_KEY]).toBeUndefined();
  });

  it('does not delete a newer pending payload after an older readback fails', async () => {
    const newer = JSON.stringify({
      version: 1,
      verifiedPhoneTicket: 'N'.repeat(32),
      expiresAt: Date.now() + 300_000,
      idempotencyKey: 'registration-newer-12345678',
    });
    let reads = 0;
    (SecureStore.getItemAsync as jest.Mock).mockImplementation(async (key) => {
      reads += 1;
      if (reads === 1) return null;
      if (reads === 2) {
        secureItems[key] = newer;
        throw new Error('old readback interrupted');
      }
      return secureItems[key] ?? null;
    });

    await expect(createPendingRegistration({
      verifiedPhoneTicket: 'O'.repeat(32),
      expiresInSeconds: 300,
      generateIdempotencyKey: () => 'registration-older-12345678',
    })).rejects.toThrow('待注册状态无法安全保存');

    expect(secureItems[PENDING_REGISTRATION_KEY]).toBe(newer);
  });

  it('uses secure random bytes when randomUUID is unavailable on the native runtime', async () => {
    const cryptoDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
    Object.defineProperty(globalThis, 'crypto', {
      configurable: true,
      value: {
        getRandomValues: (bytes: Uint8Array) => {
          bytes.fill(0xab);
          return bytes;
        },
      },
    });
    try {
      const pending = await createPendingRegistration({
        verifiedPhoneTicket: 'B'.repeat(32),
        expiresInSeconds: 300,
      });
      expect(pending.idempotencyKey).toBe(`registration-${'ab'.repeat(16)}`);
    } finally {
      if (cryptoDescriptor) {
        Object.defineProperty(globalThis, 'crypto', cryptoDescriptor);
      } else {
        delete (globalThis as { crypto?: Crypto }).crypto;
      }
    }
  });

  it('fails loudly when the native runtime exposes no secure random source', async () => {
    const cryptoDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
    Object.defineProperty(globalThis, 'crypto', {
      configurable: true,
      value: undefined,
    });
    try {
      await expect(createPendingRegistration({
        verifiedPhoneTicket: 'D'.repeat(32),
        expiresInSeconds: 300,
      })).rejects.toThrow('设备无法生成安全的注册请求标识');
    } finally {
      if (cryptoDescriptor) {
        Object.defineProperty(globalThis, 'crypto', cryptoDescriptor);
      } else {
        delete (globalThis as { crypto?: Crypto }).crypto;
      }
    }
  });

  it('fails explicitly when SecureStore cannot read pending state', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockRejectedValue(new Error('locked'));

    await expect(loadPendingRegistration()).rejects.toThrow('待注册状态无法安全读取');
  });

  it('fails explicitly when corrupt cleanup or an explicit clear cannot delete securely', async () => {
    secureItems[PENDING_REGISTRATION_KEY] = '{bad json';
    (SecureStore.deleteItemAsync as jest.Mock).mockRejectedValue(new Error('locked'));

    await expect(loadPendingRegistration()).rejects.toThrow('待注册状态无法安全清除');
    await expect(clearPendingRegistration()).rejects.toThrow('待注册状态无法安全清除');
  });

  it('queues a new create behind malformed-load compare-and-delete cleanup', async () => {
    secureItems[PENDING_REGISTRATION_KEY] = JSON.stringify({ version: 1, invalid: true });
    const deleteStarted = deferred();
    const releaseDelete = deferred();
    (SecureStore.deleteItemAsync as jest.Mock).mockImplementationOnce(async (key) => {
      deleteStarted.resolve();
      await releaseDelete.promise;
      delete secureItems[key];
    });

    const oldLoad = loadPendingRegistration();
    await deleteStarted.promise;
    const newer = createPendingRegistration({
      verifiedPhoneTicket: 'N'.repeat(32),
      expiresInSeconds: 300,
      generateIdempotencyKey: () => 'registration-newer-queue-1',
    });
    await flushMicrotasks();
    expect(Object.values(secureItems).some((raw) => raw.includes('N'.repeat(32)))).toBe(false);
    releaseDelete.resolve();

    await expect(oldLoad).resolves.toBeNull();
    const pending = await newer;
    expect(await loadPendingRegistration()).toEqual(pending);
  });

  it('queues a new create behind expired-load cleanup', async () => {
    secureItems[PENDING_REGISTRATION_KEY] = JSON.stringify({
      version: 1,
      verifiedPhoneTicket: 'E'.repeat(32),
      expiresAt: 100,
      idempotencyKey: 'registration-expired-queue',
    });
    const deleteStarted = deferred();
    const releaseDelete = deferred();
    (SecureStore.deleteItemAsync as jest.Mock).mockImplementationOnce(async (key) => {
      deleteStarted.resolve();
      await releaseDelete.promise;
      delete secureItems[key];
    });

    const expiredLoad = loadPendingRegistration(101);
    await deleteStarted.promise;
    const newer = createPendingRegistration({
      verifiedPhoneTicket: 'F'.repeat(32),
      expiresInSeconds: 300,
      nowMs: 101,
      generateIdempotencyKey: () => 'registration-fresh-queue-1',
    });
    await flushMicrotasks();
    expect(Object.values(secureItems).some((raw) => raw.includes('F'.repeat(32)))).toBe(false);
    releaseDelete.resolve();

    await expect(expiredLoad).resolves.toBeNull();
    const pending = await newer;
    expect(await loadPendingRegistration(102)).toEqual(pending);
  });

  it('queues a new create behind failed-readback candidate cleanup', async () => {
    let reads = 0;
    const deleteStarted = deferred();
    const releaseDelete = deferred();
    (SecureStore.getItemAsync as jest.Mock).mockImplementation(async (key) => {
      reads += 1;
      if (reads === 1) return null;
      if (reads === 2) throw new Error('readback failed');
      return secureItems[key] ?? null;
    });
    (SecureStore.deleteItemAsync as jest.Mock).mockImplementationOnce(async (key) => {
      deleteStarted.resolve();
      await releaseDelete.promise;
      delete secureItems[key];
    });

    const failedCreate = createPendingRegistration({
      verifiedPhoneTicket: 'O'.repeat(32),
      expiresInSeconds: 300,
      generateIdempotencyKey: () => 'registration-older-queue-1',
    });
    await deleteStarted.promise;
    const newer = createPendingRegistration({
      verifiedPhoneTicket: 'P'.repeat(32),
      expiresInSeconds: 300,
      generateIdempotencyKey: () => 'registration-newer-queue-2',
    });
    await flushMicrotasks();
    expect(Object.values(secureItems).some((raw) => raw.includes('P'.repeat(32)))).toBe(false);
    releaseDelete.resolve();

    await expect(failedCreate).rejects.toThrow('待注册状态无法安全保存');
    const pending = await newer;
    expect(await loadPendingRegistration()).toEqual(pending);
  });

  it('orders clear before a subsequently requested create', async () => {
    secureItems[PENDING_REGISTRATION_KEY] = JSON.stringify({ version: 1 });
    const deleteStarted = deferred();
    const releaseDelete = deferred();
    (SecureStore.deleteItemAsync as jest.Mock).mockImplementationOnce(async (key) => {
      deleteStarted.resolve();
      await releaseDelete.promise;
      delete secureItems[key];
    });

    const clearing = clearPendingRegistration();
    await deleteStarted.promise;
    const newer = createPendingRegistration({
      verifiedPhoneTicket: 'Q'.repeat(32),
      expiresInSeconds: 300,
      generateIdempotencyKey: () => 'registration-after-clear-1',
    });
    await flushMicrotasks();
    expect(Object.values(secureItems).some((raw) => raw.includes('Q'.repeat(32)))).toBe(false);
    releaseDelete.resolve();

    await clearing;
    const pending = await newer;
    expect(await loadPendingRegistration()).toEqual(pending);
  });
});
