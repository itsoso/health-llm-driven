import type { ImagePickerAsset } from 'expo-image-picker';
import type { Action } from 'expo-image-manipulator';
import * as FileSystem from 'expo-file-system/legacy';

export const IMAGE_UPLOAD_MAX_EDGE = 1568;
export const IMAGE_UPLOAD_COMPRESS = 0.7;
const PICKER_FALLBACK_QUALITY = 0.8;

let Manipulator: typeof import('expo-image-manipulator') | null = null;
try {
  Manipulator = require('expo-image-manipulator');
} catch {
  Manipulator = null;
  // eslint-disable-next-line no-console
  console.warn('[imageUpload] image-manipulator unavailable; using picker encoding');
}

export interface PreparedUploadImage {
  uri: string;
  base64: string;
  type: string;
  temporaryUri?: string;
}

async function deleteTemporaryUri(uri: string | undefined): Promise<void> {
  if (!uri) return;
  try {
    await FileSystem.deleteAsync(uri, { idempotent: true });
  } catch (error) {
    // eslint-disable-next-line no-console
    console.warn('[imageUpload] failed to delete temporary encoded image', error);
  }
}

export async function cleanupPreparedUploadImages(
  images: ReadonlyArray<PreparedUploadImage | null>,
): Promise<void> {
  await Promise.all(images.map(image => deleteTemporaryUri(image?.temporaryUri)));
}

export function imagePickerEncodingOptions(): { base64: boolean; quality?: number } {
  return Manipulator
    ? { base64: false }
    : { base64: true, quality: PICKER_FALLBACK_QUALITY };
}

function normalizeImageType(asset: ImagePickerAsset): string {
  const fromMime = asset.mimeType?.split('/')[1];
  const fromName = asset.fileName?.split('.').pop();
  const fromUri = asset.uri?.split(/[?#]/)[0]?.split('.').pop();
  const raw = (fromMime || fromName || fromUri || 'jpeg').toLowerCase();
  return raw === 'jpg' ? 'jpeg' : raw;
}

export async function prepareImageForUpload(
  asset: ImagePickerAsset,
): Promise<PreparedUploadImage | null> {
  const inlineBase64 = typeof asset.base64 === 'string' ? asset.base64 : '';
  if (!asset.uri) {
    return inlineBase64
      ? { uri: '', base64: inlineBase64, type: normalizeImageType(asset) }
      : null;
  }

  const M = Manipulator;
  if (!M) {
    return inlineBase64
      ? { uri: asset.uri, base64: inlineBase64, type: normalizeImageType(asset) }
      : null;
  }

  const width = asset.width ?? 0;
  const height = asset.height ?? 0;
  const longestEdge = Math.max(width, height);
  const actions: Action[] = [];
  if (longestEdge > IMAGE_UPLOAD_MAX_EDGE) {
    actions.push(width >= height
      ? { resize: { width: IMAGE_UPLOAD_MAX_EDGE } }
      : { resize: { height: IMAGE_UPLOAD_MAX_EDGE } });
  }
  const result = await M.manipulateAsync(asset.uri, actions, {
    compress: IMAGE_UPLOAD_COMPRESS,
    format: M.SaveFormat.JPEG,
    base64: true,
  });
  const temporaryUri = result.uri && result.uri !== asset.uri ? result.uri : undefined;
  if (!result.base64) {
    await deleteTemporaryUri(temporaryUri);
    return null;
  }
  return {
    uri: result.uri || asset.uri,
    base64: result.base64,
    type: 'jpeg',
    ...(temporaryUri ? { temporaryUri } : {}),
  };
}

export async function prepareImageForUploadSafe(
  asset: ImagePickerAsset,
): Promise<PreparedUploadImage | null> {
  try {
    return await prepareImageForUpload(asset);
  } catch {
    return null;
  }
}

export function base64DecodedByteLength(value: string): number {
  const compact = value
    .replace(/^data:[^;]+;base64,/i, '')
    .replace(/\s+/g, '');
  if (!compact) return 0;
  const padding = compact.endsWith('==') ? 2 : compact.endsWith('=') ? 1 : 0;
  return Math.max(0, Math.floor(compact.length * 3 / 4) - padding);
}
