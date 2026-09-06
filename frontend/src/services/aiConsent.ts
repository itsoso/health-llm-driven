/** The server is the authority; never persist or cache a positive permission. */
export interface AiConsent {
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
  if (!value || typeof value.policy_version !== 'string' || !value.policy_version
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
  const identity = await fetch(`${baseUrl}/auth/me`, { credentials: 'include', cache: 'no-store' });
  assertSession(expected);
  if (!identity.ok || (await identity.json()).id !== userId) {
    throw new AiConsentError('登录账号已变化或无法核实，请刷新页面后重试；内容未发送。');
  }
  assertSession(expected);
  const response = await fetch(`${baseUrl}/auth/ai-consent`, { credentials: 'include', cache: 'no-store' });
  assertSession(expected);
  if (!response.ok) throw new AiConsentError('无法核实 AI 授权状态，内容未发送，请稍后重试。');
  const policy = parsePolicy(await response.json());
  assertSession(expected);
  return policy;
}

async function presentPolicy(policy: AiConsent, expected: number): Promise<boolean> {
  if (!presenter) throw new AiConsentError();
  let acknowledged = false;
  const allowed = await presenter(policy, async (accepted) => {
    assertSession(expected);
    // Cookie sessions can also change in another tab; never grant for that account.
    const identity = await fetch(`${baseUrl}/auth/me`, { credentials: 'include', cache: 'no-store' });
    if (!identity.ok || (await identity.json()).id !== userId) {
      throw new AiConsentError('登录账号已变化，请刷新页面后重新查看说明。');
    }
    assertSession(expected);
    const response = await fetch(`${baseUrl}/auth/ai-consent`, {
      method: 'PUT', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ accepted, policy_version: policy.policy_version }),
    });
    assertSession(expected);
    if (!response.ok) throw new AiConsentError('授权未保存，内容未发送。请重试；若说明已更新，请关闭后重新打开。');
    const saved = parsePolicy(await response.json());
    assertSession(expected);
    if (saved.accepted !== accepted || (accepted && saved.policy_version !== policy.policy_version)) {
      throw new AiConsentError('授权状态尚未确认，内容未发送，请重试。');
    }
    acknowledged = accepted;
  });
  assertSession(expected);
  return allowed && acknowledged;
}

export async function requireAiConsent(): Promise<void> {
  const expected = generation;
  const policy = await readPolicy(expected);
  if (!policy.accepted && !await presentPolicy(policy, expected)) throw new AiConsentError();
  assertSession(expected);
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
