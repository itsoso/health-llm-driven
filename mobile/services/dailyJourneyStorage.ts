import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { uuid } from 'expo-modules-core';

const PREFIX = 'daily_journey_v1';
const INDEX = `${PREFIX}.index`;
const INSTALL = `${PREFIX}.installation`;
const CLEANUP = `${PREFIX}.cleanup`;
const MAX_CHUNKS = 128;
const OPTIONS = { keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY };
type Index = { bank: 0 | 1; count: number };
function parseIndex(raw: string): Index {
  const value = JSON.parse(raw);
  if (![0, 1].includes(value?.bank) || !Number.isInteger(value?.count) || value.count < 1 || value.count > MAX_CHUNKS) throw new Error('行程安全存储索引无效');
  return value;
}
function chunksOf(value: string): string[] {
  const chunks: string[] = []; let text = ''; let bytes = 0;
  for (const char of value) {
    const code = char.codePointAt(0)!;
    const size = code <= 0x7f ? 1 : code <= 0x7ff ? 2 : code <= 0xffff ? 3 : 4;
    if (bytes + size > 1800) { chunks.push(text); text = ''; bytes = 0; }
    text += char; bytes += size;
  }
  if (text) chunks.push(text);
  if (!chunks.length || chunks.length > MAX_CHUNKS) throw new Error('行程本机安全存储已满');
  return chunks;
}
const chunkKey = (bank: number, index: number) => `${PREFIX}.chunk.${bank}.${index}`;
const countKey = (bank: number) => `${PREFIX}.bank.${bank}.count`;
function parseCount(raw: string | null): number {
  if (raw === null) return 0;
  const count = Number(raw);
  if (!Number.isInteger(count) || count < 0 || count > MAX_CHUNKS) throw new Error('行程安全存储分块索引无效');
  return count;
}

/** Caller serializes mutations. Commit pointer changes only after all encrypted chunks persist. */
export const journeyStorage = {
  async read<T>(): Promise<T | null> {
    if (await SecureStore.getItemAsync(CLEANUP, OPTIONS)) { await journeyStorage.clear(); return null; }
    const raw = await SecureStore.getItemAsync(INDEX, OPTIONS);
    if (!raw) return null;
    const index = parseIndex(raw); const chunks: string[] = [];
    for (let i = 0; i < index.count; i += 1) {
      const chunk = await SecureStore.getItemAsync(chunkKey(index.bank, i), OPTIONS);
      if (chunk === null) throw new Error('行程安全存储不完整');
      chunks.push(chunk);
    }
    return JSON.parse(chunks.join('')) as T;
  },
  async write(value: unknown): Promise<void> {
    if (await SecureStore.getItemAsync(CLEANUP, OPTIONS)) await journeyStorage.clear();
    const chunks = chunksOf(JSON.stringify(value));
    const old = await SecureStore.getItemAsync(INDEX, OPTIONS);
    const previous = old ? parseIndex(old) : null;
    const bank = previous?.bank === 0 ? 1 : 0;
    const staleCount = parseCount(await SecureStore.getItemAsync(countKey(bank), OPTIONS));
    // Record the largest possibly-written extent before writing, so interrupted writes remain cleanable.
    await SecureStore.setItemAsync(countKey(bank), String(Math.max(staleCount, chunks.length)), OPTIONS);
    for (let i = 0; i < chunks.length; i += 1) await SecureStore.setItemAsync(chunkKey(bank, i), chunks[i], OPTIONS);
    await SecureStore.setItemAsync(INDEX, JSON.stringify({ bank, count: chunks.length }), OPTIONS);
    // Normal sampling touches only occupied chunks rather than issuing hundreds of empty Keychain deletes.
    if (previous) {
      const count = Math.max(previous.count, parseCount(await SecureStore.getItemAsync(countKey(previous.bank), OPTIONS)));
      for (let i = 0; i < count; i += 1) await SecureStore.deleteItemAsync(chunkKey(previous.bank, i), OPTIONS);
      await SecureStore.deleteItemAsync(countKey(previous.bank), OPTIONS);
    }
    for (let i = chunks.length; i < staleCount; i += 1) await SecureStore.deleteItemAsync(chunkKey(bank, i), OPTIONS);
    await SecureStore.setItemAsync(countKey(bank), String(chunks.length), OPTIONS);
  },
  async clear(): Promise<void> {
    // A process death after pointer deletion must not strand private chunks forever.
    await SecureStore.setItemAsync(CLEANUP, 'pending', OPTIONS);
    await SecureStore.deleteItemAsync(INDEX, OPTIONS);
    for (let start = 0; start < MAX_CHUNKS; start += 8) {
      await Promise.all(Array.from({ length: 8 }, (_, i) => start + i).flatMap(i => [0, 1].map(bank => SecureStore.deleteItemAsync(chunkKey(bank, i), OPTIONS))));
    }
    await SecureStore.deleteItemAsync(countKey(0), OPTIONS);
    await SecureStore.deleteItemAsync(countKey(1), OPTIONS);
    await SecureStore.deleteItemAsync(CLEANUP, OPTIONS);
  },
  async installation(): Promise<string> {
    if (await SecureStore.getItemAsync(CLEANUP, OPTIONS)) await journeyStorage.clear();
    const existing = await AsyncStorage.getItem(INSTALL);
    if (existing) return existing;
    // iOS Keychain can survive reinstall; the sandbox marker cannot. Never hydrate old tracks.
    await journeyStorage.clear();
    const id = uuid.v4();
    await AsyncStorage.setItem(INSTALL, id);
    return id;
  },
};
