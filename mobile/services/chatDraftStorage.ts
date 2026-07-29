import AsyncStorage from '@react-native-async-storage/async-storage';
import * as FileSystem from 'expo-file-system/legacy';
import * as SecureStore from 'expo-secure-store';
import { getAuthStorageScope } from './authStorageScope';

const LEGACY_CHAT_DRAFT_STORAGE_KEY = 'chat:composer_draft:v1';
const CHAT_DRAFT_STORAGE_KEY_PREFIX = 'chat:composer_draft:v2';
// SecureStore keys only allow alphanumeric characters plus '.', '-' and '_'.
const CHAT_DRAFT_TEXT_KEY_PREFIX = 'chat.composer_draft_text.v1';
const CHAT_DRAFT_VERSION = 3;
const CHAT_DRAFT_DIRECTORY_ROOT = `${FileSystem.documentDirectory ?? ''}chat-drafts/`;
const MAX_DRAFT_IMAGES = 9;
const CHAT_DRAFT_TTL_MS = 24 * 60 * 60 * 1000;
const ABANDONED_FILE_TTL_MS = 7 * 24 * 60 * 60 * 1000;
let draftMutationTail: Promise<void> = Promise.resolve();

export interface DraftableImage {
  uri: string;
  base64: string;
  type: string;
  draftCreatedAt?: number;
}

type DraftImageReference = Pick<DraftableImage, 'uri'>
  & Partial<Omit<DraftableImage, 'uri'>>;

export interface ChatDraft {
  text: string;
  images: DraftableImage[];
  intent?: 'diet_photo_record';
  captureSessionId?: string;
}

export type ChatDraftMetadata = Pick<ChatDraft, 'intent' | 'captureSessionId'>;

interface StoredDraftImage {
  uri: string;
  type: string;
  createdAt: number;
}

interface StoredChatDraft {
  version: 2 | 3;
  updatedAt: number;
  images: StoredDraftImage[];
  intent?: 'diet_photo_record';
  captureSessionId?: string;
}

interface DraftStorageContext {
  metadataKey: string;
  textKey: string;
  directory: string;
}

function serializeDraftMutation<T>(operation: () => Promise<T>): Promise<T> {
  const result = draftMutationTail.then(operation, operation);
  draftMutationTail = result.then(() => undefined, () => undefined);
  return result;
}

export function chatDraftStorageKey(scope: string): string {
  return `${CHAT_DRAFT_STORAGE_KEY_PREFIX}:${scope}`;
}

export function chatDraftTextStorageKey(scope: string): string {
  return `${CHAT_DRAFT_TEXT_KEY_PREFIX}.${scope}`;
}

export function chatDraftDirectory(scope: string): string {
  return `${CHAT_DRAFT_DIRECTORY_ROOT}${scope}/`;
}

async function currentStorageContext(): Promise<DraftStorageContext> {
  const scope = await getAuthStorageScope();
  return {
    metadataKey: chatDraftStorageKey(scope),
    textKey: chatDraftTextStorageKey(scope),
    directory: chatDraftDirectory(scope),
  };
}

function isPrivateDraftUri(uri: string, directory: string): boolean {
  return !!directory && uri.startsWith(directory);
}

function normalizeImageType(raw: string): string {
  const normalized = String(raw || 'jpeg').toLowerCase().replace(/[^a-z0-9]/g, '');
  if (normalized === 'jpg') return 'jpeg';
  return normalized || 'jpeg';
}

async function ensureDraftDirectory(directory: string): Promise<void> {
  if (!FileSystem.documentDirectory) throw new Error('chat_draft_directory_unavailable');
  await FileSystem.makeDirectoryAsync(directory, { intermediates: true });
}

function toStoredSnapshot(
  images: DraftableImage[],
  updatedAt: number,
  directory: string,
  metadata: ChatDraftMetadata = {},
): StoredChatDraft {
  return {
    version: CHAT_DRAFT_VERSION,
    updatedAt,
    ...(metadata.intent === 'diet_photo_record' ? { intent: metadata.intent } : {}),
    ...(metadata.intent === 'diet_photo_record' && metadata.captureSessionId
      ? { captureSessionId: metadata.captureSessionId }
      : {}),
    images: images
      .filter(image => isPrivateDraftUri(image.uri, directory))
      .slice(0, MAX_DRAFT_IMAGES)
      .map(image => ({
        uri: image.uri,
        type: normalizeImageType(image.type),
        createdAt: image.draftCreatedAt ?? updatedAt,
      })),
  };
}

async function storeSnapshot(
  context: DraftStorageContext,
  text: string,
  snapshot: StoredChatDraft,
): Promise<void> {
  const protectedText = String(text || '').slice(0, 2000);
  if (!protectedText && snapshot.images.length === 0) {
    await Promise.all([
      AsyncStorage.removeItem(context.metadataKey),
      SecureStore.deleteItemAsync(context.textKey),
    ]);
    return;
  }
  await Promise.all([
    AsyncStorage.setItem(context.metadataKey, JSON.stringify(snapshot)),
    protectedText
      ? SecureStore.setItemAsync(context.textKey, protectedText)
      : SecureStore.deleteItemAsync(context.textKey),
  ]);
}

export async function materializeDraftImages(
  images: DraftableImage[],
  now = Date.now(),
): Promise<DraftableImage[]> {
  if (!images.length) return [];
  const context = await currentStorageContext();
  await ensureDraftDirectory(context.directory);
  const materialized: DraftableImage[] = [];
  const createdUris: string[] = [];
  try {
    for (const [index, image] of images.slice(0, MAX_DRAFT_IMAGES).entries()) {
      if (isPrivateDraftUri(image.uri, context.directory)) {
        materialized.push({
          ...image,
          type: normalizeImageType(image.type),
          draftCreatedAt: image.draftCreatedAt ?? now,
        });
        continue;
      }
      const type = normalizeImageType(image.type);
      const suffix = Math.random().toString(36).slice(2, 10);
      const uri = `${context.directory}${now}-${index}-${suffix}.${type}`;
      if (image.base64) {
        await FileSystem.writeAsStringAsync(uri, image.base64, {
          encoding: FileSystem.EncodingType.Base64,
        });
      } else {
        await FileSystem.copyAsync({ from: image.uri, to: uri });
      }
      createdUris.push(uri);
      materialized.push({ ...image, uri, type, draftCreatedAt: now });
    }
    return materialized;
  } catch (error) {
    await Promise.allSettled(createdUris.map(uri => (
      FileSystem.deleteAsync(uri, { idempotent: true })
    )));
    throw error;
  }
}

export async function persistChatDraft(
  text: string,
  images: DraftableImage[],
  updatedAt = Date.now(),
  metadata: ChatDraftMetadata = {},
): Promise<void> {
  await serializeDraftMutation(async () => {
    const context = await currentStorageContext();
    await storeSnapshot(
      context,
      text,
      toStoredSnapshot(images, updatedAt, context.directory, metadata),
    );
  });
}

export async function loadChatDraft(): Promise<ChatDraft> {
  const context = await currentStorageContext();
  await Promise.allSettled([
    AsyncStorage.removeItem(LEGACY_CHAT_DRAFT_STORAGE_KEY),
  ]);
  const [raw, protectedText] = await Promise.all([
    AsyncStorage.getItem(context.metadataKey),
    SecureStore.getItemAsync(context.textKey),
  ]);
  const text = String(protectedText || '').slice(0, 2000);
  if (!raw) return { text, images: [] };
  let snapshot: StoredChatDraft;
  try {
    snapshot = JSON.parse(raw) as StoredChatDraft;
  } catch {
    await AsyncStorage.removeItem(context.metadataKey);
    return { text, images: [] };
  }
  if (![2, CHAT_DRAFT_VERSION].includes(snapshot?.version) || !Array.isArray(snapshot.images)) {
    await AsyncStorage.removeItem(context.metadataKey);
    return { text, images: [] };
  }
  const updatedAt = Number(snapshot.updatedAt);
  const isLegacySnapshot = snapshot.version === 2;
  if (
    !isLegacySnapshot
    && (
      !Number.isFinite(updatedAt)
      || updatedAt <= 0
      || Date.now() - updatedAt > CHAT_DRAFT_TTL_MS
    )
  ) {
    const cleared = await serializeDraftMutation(async () => {
      const latestRaw = await AsyncStorage.getItem(context.metadataKey);
      if (latestRaw !== raw) return false;
      await Promise.allSettled(snapshot.images.map(image => {
        if (!image || typeof image.uri !== 'string' || !isPrivateDraftUri(image.uri, context.directory)) {
          return Promise.resolve();
        }
        return FileSystem.deleteAsync(image.uri, { idempotent: true });
      }));
      await Promise.all([
        AsyncStorage.removeItem(context.metadataKey),
        SecureStore.deleteItemAsync(context.textKey),
      ]);
      return true;
    });
    if (!cleared) return loadChatDraft();
    return { text: '', images: [] };
  }
  const restored: DraftableImage[] = [];
  for (const image of snapshot.images.slice(0, MAX_DRAFT_IMAGES)) {
    if (
      !image
      || typeof image.uri !== 'string'
      || !isPrivateDraftUri(image.uri, context.directory)
    ) continue;
    const info = await FileSystem.getInfoAsync(image.uri);
    if (!info.exists) continue;
    restored.push({
      uri: image.uri,
      base64: '',
      type: normalizeImageType(image.type),
      draftCreatedAt: Number(image.createdAt) || snapshot.updatedAt || Date.now(),
    });
  }
  if (isLegacySnapshot || restored.length !== snapshot.images.length) {
    await storeSnapshot(
      context,
      text,
      toStoredSnapshot(
        restored,
        isLegacySnapshot ? Date.now() : (snapshot.updatedAt || Date.now()),
        context.directory,
        {
        intent: snapshot.intent,
        captureSessionId: snapshot.captureSessionId,
        },
      ),
    );
  }
  const captureSessionId = typeof snapshot.captureSessionId === 'string'
    ? snapshot.captureSessionId.trim()
    : '';
  const hasMealIntent = (
    snapshot.intent === 'diet_photo_record'
    && captureSessionId.length > 0
    && restored.length > 0
  );
  return {
    text,
    images: restored,
    ...(hasMealIntent ? {
      intent: 'diet_photo_record' as const,
      captureSessionId,
    } : {}),
  };
}

export async function hydrateDraftImagesForSend(images: DraftableImage[]): Promise<DraftableImage[]> {
  const context = await currentStorageContext();
  return Promise.all(images.map(async image => {
    if (image.base64) return image;
    if (!isPrivateDraftUri(image.uri, context.directory)) {
      throw new Error('chat_draft_image_not_private');
    }
    const base64 = await FileSystem.readAsStringAsync(image.uri, {
      encoding: FileSystem.EncodingType.Base64,
    });
    if (!base64) throw new Error('chat_draft_image_empty');
    return { ...image, base64 };
  }));
}

export async function deleteDraftImage(image: DraftImageReference): Promise<void> {
  const context = await currentStorageContext();
  if (!isPrivateDraftUri(image.uri, context.directory)) return;
  await FileSystem.deleteAsync(image.uri, { idempotent: true });
}

export async function clearPersistedChatDraft(images: DraftImageReference[] = []): Promise<void> {
  await serializeDraftMutation(async () => {
    const context = await currentStorageContext();
    await Promise.all(images.map(image => (
      isPrivateDraftUri(image.uri, context.directory)
        ? FileSystem.deleteAsync(image.uri, { idempotent: true })
        : Promise.resolve()
    )));
    await Promise.all([
      AsyncStorage.removeItem(context.metadataKey),
      SecureStore.deleteItemAsync(context.textKey),
    ]);
  });
}

export async function cleanupAbandonedChatDraftFiles(
  activeUris: string[] = [],
  now = Date.now(),
): Promise<void> {
  if (!FileSystem.documentDirectory) return;
  const context = await currentStorageContext();
  await ensureDraftDirectory(context.directory);
  const active = new Set(activeUris);
  const entries = await FileSystem.readDirectoryAsync(context.directory);
  await Promise.all(entries.map(async name => {
    const uri = `${context.directory}${name}`;
    if (active.has(uri)) return;
    const timestamp = Number(name.split('-', 1)[0]);
    const info = await FileSystem.getInfoAsync(uri);
    if (!info.exists) return;
    const modifiedAt = 'modificationTime' in info && typeof info.modificationTime === 'number'
      ? info.modificationTime * 1000
      : timestamp;
    if (Number.isFinite(modifiedAt) && now - modifiedAt > ABANDONED_FILE_TTL_MS) {
      await FileSystem.deleteAsync(uri, { idempotent: true });
    }
  }));
}
