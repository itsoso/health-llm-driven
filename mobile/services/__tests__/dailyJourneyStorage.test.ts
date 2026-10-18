import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { journeyStorage } from '../dailyJourneyStorage';
jest.mock('expo-secure-store', () => ({ getItemAsync: jest.fn(), setItemAsync: jest.fn(), deleteItemAsync: jest.fn(), AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY: 4 }));
jest.mock('@react-native-async-storage/async-storage', () => ({ __esModule: true, default: { getItem: jest.fn(), setItem: jest.fn() } }));
jest.mock('expo-modules-core', () => ({ uuid: { v4: () => 'install-1' } }));
let values: Map<string, string>;
beforeEach(() => {
  values = new Map(); jest.clearAllMocks();
  (SecureStore.getItemAsync as jest.Mock).mockImplementation(async k => values.get(k) ?? null);
  (SecureStore.setItemAsync as jest.Mock).mockImplementation(async (k, v) => { values.set(k, v); });
  (SecureStore.deleteItemAsync as jest.Mock).mockImplementation(async k => { values.delete(k); });
  (AsyncStorage.getItem as jest.Mock).mockResolvedValue('install-1');
});
it('encrypts bounded UTF-8 chunks with lock-screen accessible device-only protection', async () => {
  const value = { token: 'token', label: '中文'.repeat(1500) };
  await journeyStorage.write(value);
  expect(await journeyStorage.read()).toEqual(value);
  for (const [, serialized, options] of (SecureStore.setItemAsync as jest.Mock).mock.calls) {
    expect(Buffer.byteLength(serialized, 'utf8')).toBeLessThan(2048);
    expect(options.keychainAccessible).toBe(SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY);
  }
  expect(AsyncStorage.setItem).not.toHaveBeenCalled();
});
it('retains committed generation if a new chunk cannot persist', async () => {
  await journeyStorage.write({ value: 'old' });
  (SecureStore.setItemAsync as jest.Mock).mockRejectedValueOnce(new Error('storage full'));
  await expect(journeyStorage.write({ value: 'new' })).rejects.toThrow();
  expect(await journeyStorage.read()).toEqual({ value: 'old' });
});
it('rejects missing chunk instead of treating a partial queue as successful', async () => {
  await journeyStorage.write({ value: 'record' });
  for (const k of values.keys()) if (k.includes('.chunk.')) values.delete(k);
  await expect(journeyStorage.read()).rejects.toThrow();
});
it('purges retained keychain records after reinstall loses its non-keychain marker', async () => {
  await journeyStorage.write({ value: 'old' });
  (AsyncStorage.getItem as jest.Mock).mockResolvedValue(null);
  expect(await journeyStorage.installation()).toBe('install-1');
  expect(await journeyStorage.read()).toBeNull();
});
it('recovers interrupted deletion even after the commit index was removed', async () => {
  await journeyStorage.write({ token: 'private', points: [31, 121] });
  (SecureStore.deleteItemAsync as jest.Mock).mockImplementationOnce(async key => { values.delete(key); })
    .mockRejectedValueOnce(new Error('keychain unavailable'));
  await expect(journeyStorage.clear()).rejects.toThrow();
  expect(await journeyStorage.read()).toBeNull();
  expect([...values.keys()].filter(key => key.includes('daily_journey'))).toEqual([]);
});
