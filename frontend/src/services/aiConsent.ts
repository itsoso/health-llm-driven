/** The server is the authority; never persist or cache a positive permission. */
export interface AiConsent {
  subject_id: number;
  policy_version: string;
  accepted: boolean;
  accepted_at: string | null;
  recipients: { id: string; name: string; purpose: string }[];
  data_types: string[];
  purpose: string;
}

export class AiConsentError extends Error {
  constructor(message = '尚未同意第三方 AI 数据使用，内容未发送。可在设置中查看和管理授权。') {
    super(message);
    this.name = 'AiConsentError';
  }
}

type Presenter = (policy: AiConsent, save: (accepted: boolean) => Promise<void>) => Promise<boolean>;
const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || '/api';
let userId: number | null = null;
let generation = 0;
let presenter: Presenter | undefined;
const sessionListeners = new Set<() => void>();

export type AiSubjectHeaders = { 'X-Reva-AI-Subject': string };

/** Capture the rendered account, not whatever cookie a different tab may install. */
export function aiSessionHeaders(): Record<string, string> {
  return userId === null ? {} : { 'X-Reva-AI-Subject': String(userId) };
}

export function isAuthSessionChanged(data: unknown): boolean {
  return (data as { detail?: { code?: string } } | null)?.detail?.code === 'auth_session_changed';
}

function changedAccount(): AiConsentError {
  return new AiConsentError('登录账号已变化，请刷新页面后重试；本次操作未执行。');
}

/** Legacy fetch pages share the same expected-subject protection as Axios. */
export async function fetchWithAiSubject(input: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  const subject = aiSessionHeaders()['X-Reva-AI-Subject'];
  // Explicit proof from requireAiConsent wins over a later in-memory session change.
  if (subject && !headers.has('X-Reva-AI-Subject')) headers.set('X-Reva-AI-Subject', subject);
  const response = await fetch(input, { ...init, headers });
  if (response.status === 409 && isAuthSessionChanged(await response.clone().json())) throw changedAccount();
  return response;
}

export function setAiConsentUser(id: number | null) {
  if (id === userId) return;
  userId = id;
  generation += 1;
  sessionListeners.forEach(listener => listener());
}

export function registerAiConsentPresenter(next: Presenter, onSessionChange: () => void) {
  presenter = next;
  sessionListeners.add(onSessionChange);
  return () => {
    if (presenter === next) presenter = undefined;
    sessionListeners.delete(onSessionChange);
  };
}

function assertSession(expected: number) {
  if (userId === null || generation !== expected) {
    throw new AiConsentError('登录状态已变化，请重新登录后操作；内容未发送。');
  }
}

function parsePolicy(value: AiConsent): AiConsent {
  if (!value || !Number.isSafeInteger(value.subject_id) || value.subject_id <= 0
    || typeof value.policy_version !== 'string' || !value.policy_version
    || typeof value.accepted !== 'boolean' || !value.purpose
    || !Array.isArray(value.recipients) || !value.recipients.length
    || !value.recipients.every(item => item.id && item.name && item.purpose)
    || !Array.isArray(value.data_types) || !value.data_types.length
    || !value.data_types.every(item => typeof item === 'string' && item)) {
    throw new AiConsentError('AI 数据使用说明暂时无法加载，内容未发送，请稍后重试。');
  }
  return value;
}

async function readPolicy(expected: number): Promise<AiConsent> {
  assertSession(expected);
  const subject = userId;
  const response = await fetch(`${baseUrl}/auth/ai-consent`, {
    credentials: 'include', cache: 'no-store', headers: aiSessionHeaders(),
  });
  assertSession(expected);
  if (response.status === 409) throw changedAccount();
  if (!response.ok) throw new AiConsentError('无法核实 AI 授权状态，内容未发送，请稍后重试。');
  const policy = parsePolicy(await response.json());
  assertSession(expected);
  if (policy.subject_id !== subject) throw changedAccount();
  return policy;
}

async function presentPolicy(policy: AiConsent, expected: number): Promise<boolean> {
  if (!presenter) throw new AiConsentError();
  let acknowledged = false;
  const allowed = await presenter(policy, async (accepted) => {
    assertSession(expected);
    const response = await fetch(`${baseUrl}/auth/ai-consent`, {
      method: 'PUT', credentials: 'include', headers: {
        'Content-Type': 'application/json', 'X-Reva-AI-Subject': String(policy.subject_id),
      },
      body: JSON.stringify({ accepted, policy_version: policy.policy_version }),
    });
    assertSession(expected);
    if (response.status === 409 && isAuthSessionChanged(await response.clone().json())) throw changedAccount();
    if (!response.ok) throw new AiConsentError('授权未保存，内容未发送。请重试；若说明已更新，请关闭后重新打开。');
    const saved = parsePolicy(await response.json());
    assertSession(expected);
    if (saved.subject_id !== policy.subject_id || saved.accepted !== accepted
      || (accepted && saved.policy_version !== policy.policy_version)) {
      throw new AiConsentError('授权状态尚未确认，内容未发送，请重试。');
    }
    acknowledged = accepted;
  });
  assertSession(expected);
  return allowed && acknowledged;
}

export async function requireAiConsent(expectedSubject?: string): Promise<AiSubjectHeaders> {
  if (expectedSubject !== undefined && expectedSubject !== String(userId)) throw changedAccount();
  const expected = generation;
  const policy = await readPolicy(expected);
  if (!policy.accepted && !await presentPolicy(policy, expected)) throw new AiConsentError();
  assertSession(expected);
  return { 'X-Reva-AI-Subject': String(policy.subject_id) };
}

export async function manageAiConsent(): Promise<void> {
  const expected = generation;
  await presentPolicy(await readPolicy(expected), expected);
}

/** Explicit AI entry points only. Reading records, exporting and deleting stay available. */
export function isAiRequest(url = '', method = 'get'): boolean {
  const path = url.split('?')[0].replace(/^\/api(?:\/v1)?/, '');
  if (method.toLowerCase() === 'get') return false;
  return /^\/(agent\/stream|chat\/(transcribe|voice-command)|speech\/|tts\/|orchestrator\/chat|health-report\/generate|health-trends\/generate|smart-plan\/generate|smart-plan\/goals\/generate|goals\/.*generate-from-analysis|goals\/guidance|supplements\/scientific-recommendation|prescriptions\/recognize|medical-exams\/import\/(text|image|pdf)|family-health\/(medications\/recognize|parse-medical-text|medical-reports\/upload|wechat-bot\/message)|workout\/(pre-workout-guidance|post-workout-analysis))/.test(path);
}

export function isAiConsentRejection(data: unknown): boolean {
  const detail = (data as { detail?: { code?: string } } | null)?.detail;
  return typeof detail?.code === 'string' && detail.code.startsWith('ai_consent_');
}
