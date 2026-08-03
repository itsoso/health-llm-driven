import * as SecureStore from 'expo-secure-store';

export const PENDING_REGISTRATION_KEY = 'pending_invited_registration_v1';
const MAX_PENDING_REGISTRATION_BYTES = 4_096;

const TICKET_PATTERN = /^[A-Za-z0-9_-]{22,128}$/;
const IDEMPOTENCY_PATTERN = /^[A-Za-z0-9._:-]{16,128}$/;
const ALLOWED_FIELDS = new Set([
  'version',
  'verifiedPhoneTicket',
  'expiresAt',
  'idempotencyKey',
  'phoneMasked',
]);

function exceedsUtf8ByteLimit(value: string, limit: number): boolean {
  let bytes = 0;
  for (const character of value) {
    const codePoint = character.codePointAt(0) ?? 0;
    bytes += codePoint <= 0x7f
      ? 1
      : codePoint <= 0x7ff
        ? 2
        : codePoint <= 0xffff
          ? 3
          : 4;
    if (bytes > limit) return true;
  }
  return false;
}

export interface PendingRegistration {
  version: 1;
  verifiedPhoneTicket: string;
  expiresAt: number;
  idempotencyKey: string;
  phoneMasked?: string;
}

interface CreatePendingRegistrationInput {
  verifiedPhoneTicket: string;
  expiresInSeconds: number;
  phoneMasked?: string;
  nowMs?: number;
  generateIdempotencyKey?: () => string;
}

let pendingStorageMutation: Promise<unknown> = Promise.resolve();

function serializePendingStorageMutation<T>(operation: () => Promise<T>): Promise<T> {
  const next = pendingStorageMutation.then(operation, operation);
  pendingStorageMutation = next.then(() => undefined, () => undefined);
  return next;
}

function defaultIdempotencyKey(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return `registration-${globalThis.crypto.randomUUID()}`;
  }
  if (typeof globalThis.crypto?.getRandomValues === 'function') {
    const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
    return `registration-${hex}`;
  }
  throw new Error('设备无法生成安全的注册请求标识，请重启后重试');
}

function isPendingRegistration(value: unknown): value is PendingRegistration {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  if (Object.keys(record).some((key) => !ALLOWED_FIELDS.has(key))) return false;
  if (record.version !== 1) return false;
  if (
    typeof record.verifiedPhoneTicket !== 'string'
    || !TICKET_PATTERN.test(record.verifiedPhoneTicket)
  ) return false;
  if (
    typeof record.idempotencyKey !== 'string'
    || !IDEMPOTENCY_PATTERN.test(record.idempotencyKey)
  ) return false;
  if (
    typeof record.expiresAt !== 'number'
    || !Number.isSafeInteger(record.expiresAt)
    || record.expiresAt <= 0
  ) return false;
  if (
    record.phoneMasked !== undefined
    && (
      typeof record.phoneMasked !== 'string'
      || record.phoneMasked.length < 1
      || record.phoneMasked.length > 64
      || /[\r\n\0]/.test(record.phoneMasked)
    )
  ) return false;
  return true;
}

async function clearPendingRegistrationRaw(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(PENDING_REGISTRATION_KEY);
  } catch {
    throw new Error('待注册状态无法安全清除，请解锁设备后重试');
  }
}

export async function clearPendingRegistration(): Promise<void> {
  return serializePendingStorageMutation(clearPendingRegistrationRaw);
}

async function deletePendingRegistrationIfMatches(
  candidate: string,
  failLoud = false,
): Promise<void> {
  try {
    const current = await SecureStore.getItemAsync(PENDING_REGISTRATION_KEY);
    if (current === candidate) {
      await SecureStore.deleteItemAsync(PENDING_REGISTRATION_KEY);
    }
  } catch {
    if (failLoud) {
      throw new Error('待注册状态无法安全清除，请解锁设备后重试');
    }
    // The caller still fails loudly. Never broaden a failed candidate cleanup
    // into an unconditional delete that could erase a newer registration.
  }
}

async function discardInvalidPendingRegistration(candidate: string): Promise<null> {
  await deletePendingRegistrationIfMatches(candidate, true);
  return null;
}

async function loadPendingRegistrationRaw(
  nowMs = Date.now(),
): Promise<PendingRegistration | null> {
  let raw: string | null;
  try {
    raw = await SecureStore.getItemAsync(PENDING_REGISTRATION_KEY);
  } catch {
    throw new Error('待注册状态无法安全读取，请解锁设备后重试');
  }
  if (raw === null) return null;
  if (exceedsUtf8ByteLimit(raw, MAX_PENDING_REGISTRATION_BYTES)) {
    return discardInvalidPendingRegistration(raw);
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return discardInvalidPendingRegistration(raw);
  }
  if (!isPendingRegistration(parsed) || parsed.expiresAt <= nowMs) {
    return discardInvalidPendingRegistration(raw);
  }
  return parsed;
}

export async function loadPendingRegistration(
  nowMs = Date.now(),
): Promise<PendingRegistration | null> {
  return serializePendingStorageMutation(
    () => loadPendingRegistrationRaw(nowMs),
  );
}

export async function createPendingRegistration({
  verifiedPhoneTicket,
  expiresInSeconds,
  phoneMasked,
  nowMs = Date.now(),
  generateIdempotencyKey = defaultIdempotencyKey,
}: CreatePendingRegistrationInput): Promise<PendingRegistration> {
  if (!TICKET_PATTERN.test(verifiedPhoneTicket)) {
    throw new Error('登录服务返回了无效的手机号验证凭据');
  }
  if (
    !Number.isSafeInteger(expiresInSeconds)
    || expiresInSeconds < 1
    || expiresInSeconds > 86_400
  ) {
    throw new Error('登录服务返回了无效的手机号验证有效期');
  }

  return serializePendingStorageMutation(async () => {
    const existing = await loadPendingRegistrationRaw(nowMs);
    if (existing?.verifiedPhoneTicket === verifiedPhoneTicket) return existing;

    const pending: PendingRegistration = {
      version: 1,
      verifiedPhoneTicket,
      expiresAt: nowMs + expiresInSeconds * 1_000,
      idempotencyKey: generateIdempotencyKey(),
      ...(phoneMasked ? { phoneMasked } : {}),
    };
    if (!isPendingRegistration(pending)) {
      throw new Error('无法创建安全的待注册状态');
    }

    const serialized = JSON.stringify(pending);
    try {
      await SecureStore.setItemAsync(PENDING_REGISTRATION_KEY, serialized);
      const stored = await SecureStore.getItemAsync(PENDING_REGISTRATION_KEY);
      if (stored !== serialized) throw new Error('verification failed');
    } catch {
      await deletePendingRegistrationIfMatches(serialized);
      throw new Error('待注册状态无法安全保存，请解锁设备后重试');
    }
    return pending;
  });
}
