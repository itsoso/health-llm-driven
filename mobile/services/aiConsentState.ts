// In-process authorization is scoped to the exact login credential. The server
// owns the durable decision and policy version; this never persists a local yes.
let identity: string | null = null;
let revision = 0;
let authorized = false;
let revocationPending = false;
const invalidationListeners = new Set<() => void>();

export function setAIConsentIdentity(value: string | null): void {
  if (identity === value) return;
  identity = value;
  revocationPending = false;
  invalidateAIConsent();
}

export function invalidateAIConsent(): void {
  revision += 1;
  authorized = false;
  invalidationListeners.forEach(listener => listener());
}

export function subscribeAIConsentInvalidation(listener: () => void): () => void {
  invalidationListeners.add(listener);
  return () => { invalidationListeners.delete(listener); };
}

export function aiConsentRevision(): number { return revision; }
export function hasAIConsentIdentity(): boolean { return identity !== null; }
export function hasAIConsent(): boolean { return identity !== null && authorized; }
export function clearAIConsentAuthorization(): void { authorized = false; }
export function isAIConsentRevoking(): boolean { return revocationPending; }
export function setAIConsentRevoking(value: boolean): void { revocationPending = value; }
export function acceptAIConsentRevision(value: number): boolean {
  if (value !== revision || !identity || revocationPending) return false;
  authorized = true;
  return true;
}

export class AIConsentRequiredError extends Error {
  constructor() { super('ai_consent_required'); this.name = 'AIConsentRequiredError'; }
}

export function isAIConsentError(error: unknown): boolean {
  const candidate = error as { response?: { status?: number; data?: { detail?: { code?: string } } } };
  return error instanceof AIConsentRequiredError
    || (candidate?.response?.status === 403 && candidate.response.data?.detail?.code === 'ai_consent_required');
}
