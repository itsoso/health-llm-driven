export interface DietPhotoAssetLike {
  ordinal?: number | null;
  url?: string | null;
}

export interface DietRecordPhotoSource {
  image_url?: string | null;
  image_urls?: Array<string | null | undefined> | null;
  photo_assets?: DietPhotoAssetLike[] | null;
}

function normalizedUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const url = value.trim();
  return url ? url : null;
}

/**
 * Prefer the authoritative, ordered photo-asset relation. Legacy image fields
 * remain as a backward-compatible fallback for records created before assets.
 */
export function dietRecordPhotoUrls(record: DietRecordPhotoSource): string[] {
  const assets = Array.isArray(record.photo_assets)
    ? record.photo_assets
        .map((asset, index) => ({
          url: normalizedUrl(asset?.url),
          ordinal: typeof asset?.ordinal === 'number' ? asset.ordinal : index,
          index,
        }))
        .filter((asset): asset is { url: string; ordinal: number; index: number } => Boolean(asset.url))
        .sort((left, right) => left.ordinal - right.ordinal || left.index - right.index)
        .map((asset) => asset.url)
    : [];

  const candidates = assets.length > 0
    ? assets
    : [
        ...(Array.isArray(record.image_urls) ? record.image_urls : []),
        record.image_url,
      ].map(normalizedUrl).filter((url): url is string => Boolean(url));

  return candidates.filter((url, index) => candidates.indexOf(url) === index);
}
