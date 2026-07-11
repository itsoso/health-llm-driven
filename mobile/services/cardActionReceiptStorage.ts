import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

import type { ChatCardActionDescriptor } from '../components/chat/cards/types';
import { getAuthStorageScope } from './authStorageScope';
import { normalizeWriteReceipt, type WriteReceipt } from './writeReceipt';

const STORAGE_KEY_PREFIX = 'chat:card_action_receipt:v2';
const INDEX_KEY_PREFIX = 'chat:card_action_receipt_index:v2';
const STORAGE_VERSION = 2;
const RECEIPT_TTL_MS = 90 * 24 * 60 * 60 * 1000;
const MAX_ENTRIES = 100;

interface StoredReceiptEnvelope {
  version: 2;
  identity: string;
  receipt: WriteReceipt;
  storedAt: number;
}

interface StoredReceiptIndex {
  version: 2;
  entries: Record<string, StoredReceiptIndexEntry>;
}

interface StoredReceiptIndexEntry {
  storedAt: number;
  completionOnly: boolean;
}

export interface CardActionCompletion {
  verified: true;
  receipt?: WriteReceipt;
}

let mutationQueue: Promise<void> = Promise.resolve();

export function cardActionReceiptStorageKey(scope: string, identity: string): string {
  return `${STORAGE_KEY_PREFIX}:${scope}:${digest(identity)}`;
}

function cardActionReceiptIndexKey(scope: string): string {
  return `${INDEX_KEY_PREFIX}:${scope}`;
}

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === 'object') {
    const source = value as Record<string, unknown>;
    return Object.keys(source).sort().reduce<Record<string, unknown>>((out, key) => {
      out[key] = stableValue(source[key]);
      return out;
    }, {});
  }
  return value;
}

function digest(value: string): string {
  let first = 0xdeadbeef ^ value.length;
  let second = 0x41c6ce57 ^ value.length;
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    first = Math.imul(first ^ code, 2654435761);
    second = Math.imul(second ^ code, 1597334677);
  }
  first = Math.imul(first ^ (first >>> 16), 2246822507)
    ^ Math.imul(second ^ (second >>> 13), 3266489909);
  second = Math.imul(second ^ (second >>> 16), 2246822507)
    ^ Math.imul(first ^ (first >>> 13), 3266489909);
  return `${(second >>> 0).toString(16).padStart(8, '0')}${(first >>> 0).toString(16).padStart(8, '0')}-${value.length}`;
}

export function buildCardActionReceiptIdentity(
  action: ChatCardActionDescriptor,
  cardType: string,
  sourceInstance?: string | number,
): string {
  const canonical = JSON.stringify(stableValue({
    cardType,
    sourceInstance: sourceInstance ?? null,
    id: action.id ?? null,
    action: action.action,
    endpoint: action.endpoint ?? null,
    payload: action.payload ?? null,
  }));
  return `${String(cardType || 'card').replace(/[^a-zA-Z0-9_.-]/g, '_').slice(0, 32)}:${digest(canonical)}`;
}

function parseEnvelope(raw: string | null, expectedIdentity: string): StoredReceiptEnvelope | undefined {
  if (!raw) return undefined;
  try {
    const parsed = JSON.parse(raw) as Partial<StoredReceiptEnvelope>;
    const receipt = normalizeWriteReceipt(parsed.receipt);
    if (
      parsed.version !== STORAGE_VERSION
      || parsed.identity !== expectedIdentity
      || typeof parsed.storedAt !== 'number'
      || !receipt
    ) {
      return undefined;
    }
    return {
      version: STORAGE_VERSION,
      identity: expectedIdentity,
      receipt,
      storedAt: parsed.storedAt,
    };
  } catch {
    return undefined;
  }
}

function parseIndex(raw: string | null): StoredReceiptIndex {
  if (!raw) return { version: STORAGE_VERSION, entries: {} };
  try {
    const parsed = JSON.parse(raw) as Partial<StoredReceiptIndex>;
    if (parsed.version !== STORAGE_VERSION || !parsed.entries || typeof parsed.entries !== 'object') {
      return { version: STORAGE_VERSION, entries: {} };
    }
    const entries: Record<string, StoredReceiptIndexEntry> = {};
    for (const [key, rawEntry] of Object.entries(parsed.entries)) {
      const legacyTimestamp = typeof rawEntry === 'number' ? rawEntry : undefined;
      const candidate = rawEntry as Partial<StoredReceiptIndexEntry>;
      const storedAt = legacyTimestamp ?? candidate?.storedAt;
      if (typeof storedAt !== 'number' || !Number.isFinite(storedAt)) continue;
      entries[key] = {
        storedAt,
        completionOnly: legacyTimestamp === undefined && candidate.completionOnly === true,
      };
    }
    return { version: STORAGE_VERSION, entries };
  } catch {
    return { version: STORAGE_VERSION, entries: {} };
  }
}

function enqueueMutation(operation: () => Promise<void>): Promise<void> {
  const pending = mutationQueue.then(operation, operation);
  mutationQueue = pending.catch(() => undefined);
  return pending;
}

async function removeIndexedReceipt(scope: string, storageKey: string): Promise<void> {
  await enqueueMutation(async () => {
    try {
      await SecureStore.deleteItemAsync(storageKey);
    } catch {
      // Index cleanup must still proceed when Keychain is temporarily unavailable.
    }
    const indexKey = cardActionReceiptIndexKey(scope);
    const index = parseIndex(await AsyncStorage.getItem(indexKey));
    if (!(storageKey in index.entries)) return;
    delete index.entries[storageKey];
    await AsyncStorage.setItem(indexKey, JSON.stringify(index));
  });
}

export async function saveCardActionReceipt(
  identity: string,
  rawReceipt: WriteReceipt,
  storedAt = Date.now(),
): Promise<void> {
  const receipt = normalizeWriteReceipt(rawReceipt);
  if (!identity || !receipt) throw new Error('write_receipt_unverified');
  const scope = await getAuthStorageScope();
  const storageKey = cardActionReceiptStorageKey(scope, identity);
  const indexKey = cardActionReceiptIndexKey(scope);
  await enqueueMutation(async () => {
    let secureSaved = true;
    try {
      await SecureStore.setItemAsync(storageKey, JSON.stringify({
        version: STORAGE_VERSION,
        identity,
        receipt,
        storedAt,
      } satisfies StoredReceiptEnvelope));
    } catch {
      secureSaved = false;
    }

    let discardedKeys: string[] = [];
    try {
      const index = parseIndex(await AsyncStorage.getItem(indexKey));
      const nextEntries = {
        ...index.entries,
        [storageKey]: { storedAt, completionOnly: !secureSaved },
      };
      const ranked = Object.entries(nextEntries)
        .filter(([, entry]) => (
          entry.storedAt <= storedAt + 60_000
          && storedAt - entry.storedAt <= RECEIPT_TTL_MS
        ))
        .sort(([, left], [, right]) => right.storedAt - left.storedAt);
      const retained = ranked.slice(0, MAX_ENTRIES);
      const retainedKeys = new Set(retained.map(([key]) => key));
      discardedKeys = Object.keys(nextEntries).filter(key => !retainedKeys.has(key));

      await AsyncStorage.setItem(indexKey, JSON.stringify({
        version: STORAGE_VERSION,
        entries: Object.fromEntries(retained),
      } satisfies StoredReceiptIndex));
    } catch {
      throw new Error('card_action_receipt_index_persistence_failed');
    }
    await Promise.allSettled(discardedKeys.map(key => SecureStore.deleteItemAsync(key)));
  });
}

export async function loadCardActionCompletion(
  identity: string,
  now = Date.now(),
): Promise<CardActionCompletion | undefined> {
  if (!identity) return undefined;
  const scope = await getAuthStorageScope();
  const storageKey = cardActionReceiptStorageKey(scope, identity);
  let secureRaw: string | null = null;
  let secureReadFailed = false;
  try {
    secureRaw = await SecureStore.getItemAsync(storageKey);
  } catch {
    secureReadFailed = true;
    // A non-sensitive AsyncStorage tombstone remains a valid duplicate guard.
  }
  const envelope = parseEnvelope(secureRaw, identity);
  if (envelope) {
    if (envelope.storedAt <= now + 60_000 && now - envelope.storedAt <= RECEIPT_TTL_MS) {
      return { verified: true, receipt: envelope.receipt };
    }
    await removeIndexedReceipt(scope, storageKey);
    return undefined;
  }
  const index = parseIndex(await AsyncStorage.getItem(cardActionReceiptIndexKey(scope)));
  const fallback = index.entries[storageKey];
  if (
    fallback
    && (fallback.completionOnly === true || secureReadFailed)
    && fallback.storedAt <= now + 60_000
    && now - fallback.storedAt <= RECEIPT_TTL_MS
  ) {
    return { verified: true, receipt: undefined };
  }
  if (secureRaw || fallback) await removeIndexedReceipt(scope, storageKey);
  return undefined;
}

export async function loadCardActionReceipt(
  identity: string,
  now = Date.now(),
): Promise<WriteReceipt | undefined> {
  return (await loadCardActionCompletion(identity, now))?.receipt;
}
