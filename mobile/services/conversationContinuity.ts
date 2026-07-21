import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

import { normalizeWriteReceipt, type WriteReceipt } from './writeReceipt';
import { getAuthStorageScope } from './authStorageScope';

const LEGACY_CHAT_CONTINUITY_STORAGE_KEY = 'chat:conversation_continuity:v1';
const CHAT_CONTINUITY_STORAGE_KEY_PREFIX = 'chat:conversation_continuity:v2';
const CONTINUITY_VERSION = 1;
const CONTINUITY_TTL_MS = 24 * 60 * 60 * 1000;
const MAX_EXTRA_CONTEXT_LENGTH = 3900;

interface StoredConversationContinuity {
  version: 1;
  receipt: WriteReceipt;
  storedAt: number;
}

let mutationQueue: Promise<void> = Promise.resolve();

export function conversationContinuityStorageKey(scope: string): string {
  return `${CHAT_CONTINUITY_STORAGE_KEY_PREFIX}:${scope}`;
}

async function currentStorageKey(): Promise<string> {
  return conversationContinuityStorageKey(await getAuthStorageScope());
}

async function removeLegacyDeviceScopedReceipt(): Promise<void> {
  await Promise.allSettled([
    AsyncStorage.removeItem(LEGACY_CHAT_CONTINUITY_STORAGE_KEY),
    SecureStore.deleteItemAsync(LEGACY_CHAT_CONTINUITY_STORAGE_KEY),
  ]);
}

function enqueueMutation(operation: () => Promise<void>): Promise<void> {
  const pending = mutationQueue.then(operation, operation);
  mutationQueue = pending.catch(() => undefined);
  return pending;
}

function parseSnapshot(raw: string | null): StoredConversationContinuity | undefined {
  if (!raw) return undefined;
  try {
    const parsed = JSON.parse(raw) as Partial<StoredConversationContinuity>;
    const receipt = normalizeWriteReceipt(parsed?.receipt);
    if (
      parsed?.version !== CONTINUITY_VERSION
      || !receipt
      || receipt.status !== 'verified'
      || typeof parsed.storedAt !== 'number'
    ) {
      return undefined;
    }
    return {
      version: CONTINUITY_VERSION,
      receipt,
      storedAt: parsed.storedAt,
    };
  } catch {
    return undefined;
  }
}

export async function rememberVerifiedWriteReceipt(
  rawReceipt: WriteReceipt,
  storedAt = Date.now(),
): Promise<void> {
  const receipt = normalizeWriteReceipt(rawReceipt);
  if (!receipt) throw new Error('write_receipt_unverified');
  if (receipt.status !== 'verified') return;
  const storageKey = await currentStorageKey();
  await enqueueMutation(async () => {
    await removeLegacyDeviceScopedReceipt();
    await SecureStore.setItemAsync(storageKey, JSON.stringify({
      version: CONTINUITY_VERSION,
      receipt,
      storedAt,
    } satisfies StoredConversationContinuity));
  });
}

export async function loadPendingWriteReceipt(now = Date.now()): Promise<WriteReceipt | undefined> {
  const storageKey = await currentStorageKey();
  await removeLegacyDeviceScopedReceipt();
  const raw = await SecureStore.getItemAsync(storageKey);
  const snapshot = parseSnapshot(raw);
  if (!snapshot || now - snapshot.storedAt > CONTINUITY_TTL_MS || snapshot.storedAt > now + 60_000) {
    if (raw) {
      await enqueueMutation(async () => {
        const current = await SecureStore.getItemAsync(storageKey);
        if (current === raw) await SecureStore.deleteItemAsync(storageKey);
      });
    }
    return undefined;
  }
  return snapshot.receipt;
}

export async function acknowledgePendingWriteReceipt(operationId: string): Promise<void> {
  const expectedOperationId = String(operationId || '').trim();
  if (!expectedOperationId) return;
  const storageKey = await currentStorageKey();
  await enqueueMutation(async () => {
    const raw = await SecureStore.getItemAsync(storageKey);
    const snapshot = parseSnapshot(raw);
    if (snapshot?.receipt.operationId === expectedOperationId) {
      await SecureStore.deleteItemAsync(storageKey);
    }
  });
}

function parseCallerContext(extraContext?: string): Record<string, unknown> {
  const raw = String(extraContext || '').trim();
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    // Preserve legacy non-JSON caller context under an explicit field.
  }
  return { entry_context: raw };
}

export function mergeConversationContinuity(
  extraContext: string | undefined,
  receipt: WriteReceipt | undefined,
): string | undefined {
  if (!receipt) {
    const raw = String(extraContext || '').trim();
    return raw || undefined;
  }
  const normalized = normalizeWriteReceipt(receipt);
  if (!normalized || normalized.status !== 'verified') {
    const raw = String(extraContext || '').trim();
    return raw || undefined;
  }
  const callerContext = parseCallerContext(extraContext);
  const currentContinuity = callerContext.continuity;
  const continuity = currentContinuity && typeof currentContinuity === 'object' && !Array.isArray(currentContinuity)
    ? currentContinuity as Record<string, unknown>
    : {};
  const latestVerifiedWrite = {
    operation_id: normalized.operationId,
    resource_type: normalized.resourceType,
    resource_id: normalized.resourceId,
    completed_at: normalized.completedAt,
    verified: true,
  };
  const merged = JSON.stringify({
    ...callerContext,
    continuity: {
      ...continuity,
      latest_verified_write: latestVerifiedWrite,
    },
  });
  if (merged.length <= MAX_EXTRA_CONTEXT_LENGTH) return merged;
  return JSON.stringify({
    continuity: { latest_verified_write: latestVerifiedWrite },
  });
}
