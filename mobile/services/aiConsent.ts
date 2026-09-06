import { Alert } from 'react-native';
import type { AxiosRequestConfig } from 'axios';
import api from './api';
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

function disclosure(policy: AIConsentPolicy): string {
  return `接收方：\n${policy.recipients.map(item => `${item.name}：${item.purpose}`).join('\n')}\n\n共享内容：${policy.data_types.join('、')}。包括你发送的文字、相关健康记录与对话上下文，以及你选择提交的图片和语音。\n\n用途：${policy.purpose}\n\n仅在你同意后使用第三方 AI。你可以暂不使用，仍可查看和管理记录、隐私与账号；也可随时在“设置 → AI 数据共享”撤回。撤回后停止后续共享，不会删除已经发送的数据。`;
}

function validPolicy(value: AIConsentPolicy): boolean {
  return Boolean(value?.policy_version && typeof value.accepted === 'boolean'
    && value.recipients?.length && value.recipients.every(item => item.id && item.name && item.purpose)
    && value.data_types?.length && value.purpose);
}

async function loadPolicy(): Promise<AIConsentPolicy> {
  const { data } = await api.get<AIConsentPolicy>('/auth/ai-consent');
  if (!validPolicy(data)) throw new Error('invalid_ai_consent_policy');
  return data;
}

async function promptConsent(policy: AIConsentPolicy, revision: number): Promise<boolean> {
  clearAIConsentAuthorization(true);
  return new Promise(resolve => {
    Alert.alert('使用 AI 前，请确认数据共享', disclosure(policy), [
      { text: '暂不使用', style: 'cancel', onPress: () => resolve(false) },
      { text: '同意并继续', onPress: () => {
        if (revision !== aiConsentRevision() || !hasAIConsentIdentity()) { resolve(false); return; }
        void api.put<AIConsentPolicy>('/auth/ai-consent', {
          accepted: true, policy_version: policy.policy_version,
        }, { __revaConsentRevision: revision } as AxiosRequestConfig).then(({ data }) => {
          const saved = validPolicy(data) && data.accepted === true && Boolean(data.accepted_at)
            && data.policy_version === policy.policy_version;
          resolve(saved && acceptAIConsentRevision(revision));
        }).catch(() => {
          Alert.alert('授权未保存', '暂未发送内容。请检查网络后重试。'); resolve(false);
        });
      } },
    ], { cancelable: true, onDismiss: () => resolve(false) });
  });
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
      const policy = await loadPolicy();
      if (revision !== aiConsentRevision()) return false;
      if (policy.accepted && policy.accepted_at) return acceptAIConsentRevision(revision);
      clearAIConsentAuthorization();
      return await promptConsent(policy, revision);
    } catch {
      if (revision === aiConsentRevision()) clearAIConsentAuthorization();
      Alert.alert('暂时无法确认 AI 授权', '内容未发送，草稿会保留。请检查网络后再试。');
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
  try {
    await getToken();
    const revision = aiConsentRevision();
    const policy = await loadPolicy();
    if (revision !== aiConsentRevision() || !hasAIConsentIdentity()) return;
    if (!policy.accepted) {
      setAIConsentRevoking(false);
      await promptConsent(policy, revision); return;
    }
    await new Promise<void>(resolve => {
      Alert.alert('AI 数据共享 · 已同意', disclosure(policy), [
        { text: '保持授权', style: 'cancel', onPress: () => resolve() },
        { text: '撤回授权', style: 'destructive', onPress: () => {
          if (revision !== aiConsentRevision()) { resolve(); return; }
          // Close local egress immediately while the server persists revocation.
          invalidateAIConsent(true);
          setAIConsentRevoking(true);
          const revokeRevision = aiConsentRevision();
          void api.put<AIConsentPolicy>('/auth/ai-consent', { accepted: false, policy_version: policy.policy_version },
            { __revaConsentRevision: revokeRevision } as AxiosRequestConfig)
            .then(({ data }) => {
              if (revokeRevision !== aiConsentRevision()) return;
              if (data.accepted !== false) throw new Error('revocation_not_saved');
              setAIConsentRevoking(false);
              Alert.alert('已撤回 AI 授权', '后续内容将不再共享给第三方 AI。你仍可查看和管理健康记录。');
            }).catch(() => Alert.alert('撤回尚未完成', '本次撤回未能保存到服务器，请检查网络后重新撤回。'))
            .finally(resolve);
        } },
      ], { cancelable: true, onDismiss: resolve });
    });
  } catch { Alert.alert('暂时无法读取授权', '请检查网络后重试。'); }
}
