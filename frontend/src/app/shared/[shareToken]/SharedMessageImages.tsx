export function parseSharedImageUrls(raw?: string | null): string[] {
  if (!raw) return [];
  let parsed: unknown = raw;
  try {
    parsed = JSON.parse(raw);
  } catch {
    parsed = raw;
  }
  const values = Array.isArray(parsed) ? parsed : [parsed];
  return values
    .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
    .map(value => value.trim());
}

export default function SharedMessageImages({ imageUrl }: { imageUrl?: string | null }) {
  const imageUrls = parseSharedImageUrls(imageUrl);
  if (imageUrls.length === 0) return null;
  return (
    <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
      {imageUrls.map((src, imageIndex) => (
        <img
          key={`${src}-${imageIndex}`}
          src={src}
          alt={`对话图片 ${imageIndex + 1}`}
          className="max-h-80 w-full rounded-xl border border-slate-200 object-cover"
          loading="lazy"
        />
      ))}
    </div>
  );
}
