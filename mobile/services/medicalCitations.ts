export interface MedicalCitation {
  sourceId: string;
  title: string;
  organization: string;
  url: string;
  topic?: string;
  claimScope?: string;
}

export function safeMedicalCitationUrl(value: unknown): string | undefined {
  const url = typeof value === 'string' ? value.trim() : '';
  if (!url || /\s/.test(url)) return undefined;
  try {
    const parsed = new URL(url);
    const hostname = parsed.hostname.toLowerCase().replace(/\.$/, '');
    const isPrivateHost = (
      hostname === 'localhost'
      || hostname.endsWith('.localhost')
      || hostname.endsWith('.local')
      || hostname === '::1'
      || hostname === '0.0.0.0'
      || hostname.startsWith('127.')
      || hostname.startsWith('10.')
      || hostname.startsWith('192.168.')
      || /^172\.(?:1[6-9]|2\d|3[01])\./.test(hostname)
      || hostname.startsWith('169.254.')
      || hostname.includes(':')
    );
    if (
      parsed.protocol !== 'https:'
      || !hostname
      || parsed.username
      || parsed.password
      || isPrivateHost
    ) return undefined;
    return url;
  } catch {
    return undefined;
  }
}

export function normalizeMedicalCitations(value: unknown): MedicalCitation[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const citations: MedicalCitation[] = [];
  const seenUrls = new Set<string>();
  for (const raw of value) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) continue;
    const item = raw as Record<string, unknown>;
    const url = safeMedicalCitationUrl(item.url);
    const title = typeof item.title === 'string' ? item.title.trim() : '';
    const organization = typeof item.organization === 'string' ? item.organization.trim() : '';
    if (!url || !title || !organization || seenUrls.has(url)) continue;
    seenUrls.add(url);
    citations.push({
      sourceId: typeof item.source_id === 'string' && item.source_id.trim()
        ? item.source_id.trim()
        : url,
      title,
      organization,
      url,
      ...(typeof item.topic === 'string' && item.topic.trim()
        ? { topic: item.topic.trim() }
        : {}),
      ...(typeof item.claim_scope === 'string' && item.claim_scope.trim()
        ? { claimScope: item.claim_scope.trim() }
        : {}),
    });
  }
  return citations.length > 0 ? citations : undefined;
}
