import { Alert } from 'react-native';
import type { AxiosRequestConfig } from 'axios';
import api from './api';
import { showAIConsent } from './aiConsentPresentation';
import { getToken } from './auth';
import {
  acceptAIConsentRevision, aiConsentRevision, AIConsentRequiredError,
  hasAIConsentIdentity, invalidateAIConsent,
  clearAIConsentAuthorization, isAIConsentRevoking, setAIConsentRevoking,
  hasAIConsent,
} from './aiConsentState';

export interface AIConsentPolicy {
  policy_version: string;
  accepted: boolean;
  accepted_at: string | null;
  recipients: { id: string; name: string; purpose: string }[];
  data_types: string[];
  purpose: string;
}

let pending: { revision: number; promise: Promise<boolean> } | null = null;

let revocationInFlight: number | null = null;
let disclosed: { revision: number; policyVersion: string } | null = null;

function validPolicy(value: AIConsentPolicy): boolean {
  return Boolean(value?.policy_version && typeof value.accepted === 'boolean'
    && value.recipients?.length && value.recipients.every(item => item.id && item.name && item.purpose)
    && value.data_types?.length && value.purpose);
}

async function loadPolicy(): Promise<AIConsentPolicy> {
  const { data } = await api.get<AIConsentPolicy>('/auth/ai-consent', { timeout: 8000 });
  if (!validPolicy(data)) throw new Error('invalid_ai_consent_policy');
  return data;
}

function policyFailure(error: unknown): { status?: number; transient: boolean } {
  const failure = error as { code?: string; response?: { status?: number } } | null;
  const status = failure?.response?.status;
  return {
    status,
    transient: status !== undefined
      ? [502, 503, 504].includes(status)
      : ['ERR_NETWORK', 'ECONNABORTED', 'ETIMEDOUT'].includes(failure?.code ?? ''),
  };
}

async function loadCurrentPolicy(revision: number): Promise<AIConsentPolicy> {
  try { return await loadPolicy(); }
  catch (error) {
    // Only retry the read. Grants/revocations and health writes are never replayed.
    if (!policyFailure(error).transient || revision !== aiConsentRevision() || isAIConsentRevoking()) throw error;
    return loadPolicy();
  }
}

function showPolicyFailure(error: unknown): void {
  const { status } = policyFailure(error);
  if (status === 401) {
    Alert.alert('登录已失效', '尚未发送本次 AI 请求。请重新登录后再试。');
  } else if (status !== undefined && status >= 500) {
    Alert.alert('AI 授权服务暂不可用', '尚未发送本次 AI 请求。请稍后重试。');
  } else if (status === 403) {
    Alert.alert('无法读取 AI 授权', '尚未发送本次 AI 请求。请确认当前账号有权使用此功能。');
  } else if (error instanceof Error && error.message === 'invalid_ai_consent_policy') {
    Alert.alert('AI 授权说明暂不可用', '服务器返回的授权说明不完整。尚未发送本次 AI 请求，请稍后重试。');
  } else {
    Alert.alert('暂时无法确认 AI 授权', '尚未发送本次 AI 请求。请检查网络后重试；也可在“设置 → AI 数据共享”查看授权状态。');
  }
}

async function promptConsent(policy: AIConsentPolicy, revision: number): Promise<boolean> {
  clearAIConsentAuthorization(true);
  const decision = await showAIConsent(policy, 'request');
  if (decision !== 'accept' || revision !== aiConsentRevision() || !hasAIConsentIdentity()) return false;
  try {
    const { data } = await api.put<AIConsentPolicy>('/auth/ai-consent', {
      accepted: true, policy_version: policy.policy_version,
    }, { __revaConsentRevision: revision } as AxiosRequestConfig);
    const saved = validPolicy(data) && data.accepted === true && Boolean(data.accepted_at)
      && data.policy_version === policy.policy_version;
    if (!saved || !acceptAIConsentRevision(revision)) return false;
    disclosed = { revision, policyVersion: policy.policy_version };
    return true;
  } catch {
    if (revision === aiConsentRevision()) Alert.alert('授权未保存', '暂未发送内容。请检查网络后重试。');
    return false;
  }
}

export async function ensureAIConsent(): Promise<boolean> {
  // Restoring credentials may rotate the consent generation. Capture it only
  // after auth hydration, before fetching the server's current policy.
  try { await getToken(); }
  catch { clearAIConsentAuthorization(); return false; }
  if (!hasAIConsentIdentity() || isAIConsentRevoking()) return false;
  const revision = aiConsentRevision();
  if (pending?.revision === revision) return pending.promise;
  const promise = (async () => {
    try {
      const policy = await loadCurrentPolicy(revision);
      if (revision !== aiConsentRevision()) return false;
      if (policy.accepted && policy.accepted_at && disclosed?.revision === revision
        && disclosed.policyVersion === policy.policy_version) return acceptAIConsentRevision(revision);
      clearAIConsentAuthorization();
      return await promptConsent(policy, revision);
    } catch (error) {
      if (revision !== aiConsentRevision()) return false;
      clearAIConsentAuthorization();
      showPolicyFailure(error);
      return false;
    }
  })();
  pending = { revision, promise };
  try { return await promise; }
  finally { if (pending?.promise === promise) pending = null; }
}

export async function requireAIConsent(): Promise<void> {
  if (hasAIConsent()) return;
  if (!await ensureAIConsent()) throw new AIConsentRequiredError();
}

export async function manageAIConsent(): Promise<void> {
  let revision: number | undefined;
  try {
    await getToken();
    revision = aiConsentRevision();
    if (revocationInFlight === revision) return;
    const policy = await loadCurrentPolicy(revision);
    if (revision !== aiConsentRevision() || !hasAIConsentIdentity()) return;
    if (!policy.accepted) {
      setAIConsentRevoking(false);
      await ensureAIConsent(); return;
    }
    const decision = await showAIConsent(policy, 'manage');
    if (decision !== 'revoke' || revision !== aiConsentRevision() || !hasAIConsentIdentity()) return;
    invalidateAIConsent(true);
    setAIConsentRevoking(true);
    const revokeRevision = aiConsentRevision();
    revocationInFlight = revokeRevision;
    try {
      const { data } = await api.put<AIConsentPolicy>('/auth/ai-consent', { accepted: false, policy_version: policy.policy_version },
        { __revaConsentRevision: revokeRevision } as AxiosRequestConfig);
      if (revokeRevision !== aiConsentRevision()) return;
      if (data.accepted !== false) throw new Error('revocation_not_saved');
      setAIConsentRevoking(false);
      Alert.alert('已撤回 AI 授权', '后续内容将不再共享给第三方 AI。你仍可查看和管理健康记录。');
    } catch {
      if (revokeRevision === aiConsentRevision()) Alert.alert('撤回尚未完成', '本次撤回未能保存到服务器，请检查网络后重新撤回。');
    } finally {
      if (revocationInFlight === revokeRevision) revocationInFlight = null;
    }
  } catch (error) {
    if (revision === undefined || revision === aiConsentRevision()) showPolicyFailure(error);
  }
}
