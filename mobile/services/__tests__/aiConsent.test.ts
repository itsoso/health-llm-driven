import { Alert } from 'react-native';
import api from '../api';
import { ensureAIConsent, manageAIConsent, requireAIConsent } from '../aiConsent';
import { setAIConsentIdentity, invalidateAIConsent } from '../aiConsentState';
import { hasAIConsent } from '../aiConsentState';

jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn(), put: jest.fn() } }));
jest.mock('../auth', () => ({ getToken: jest.fn(async () => 'session-a') }));

const policy = {
  policy_version: 'test-policy', accepted: false, accepted_at: null,
  recipients: [{ id: 'provider', name: '测试 AI 提供方', purpose: '健康问答' }],
  data_types: ['健康文本', '图片', '语音'], purpose: '生成健康管理回复',
};
const flush = async () => { for (let n = 0; n < 12; n++) await Promise.resolve(); };
const buttons = () => (Alert.alert as jest.Mock).mock.calls[0][2];

beforeEach(() => {
  jest.clearAllMocks();
  setAIConsentIdentity(null); setAIConsentIdentity('session-a'); invalidateAIConsent();
  jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  (api.get as jest.Mock).mockResolvedValue({ data: policy });
  (api.put as jest.Mock).mockResolvedValue({ data: { ...policy, accepted: true, accepted_at: '2026-09-06T00:00:00Z' } });
});

it('does not authorize or write consent when disclosure is declined', async () => {
  const pending = ensureAIConsent(); await flush();
  expect(Alert.alert).toHaveBeenCalledWith(expect.any(String), expect.stringContaining('测试 AI 提供方'), expect.any(Array), expect.any(Object));
  buttons()[0].onPress();
  await expect(pending).resolves.toBe(false);
  expect(api.put).not.toHaveBeenCalled();
});

it('waits for server persistence before allowing data sharing', async () => {
  let resolveSave: (value: unknown) => void = () => {};
  (api.put as jest.Mock).mockImplementation(() => new Promise(resolve => { resolveSave = resolve; }));
  let allowed = false;
  const pending = ensureAIConsent().then(value => { allowed = value; }); await flush();
  buttons()[1].onPress(); await flush();
  expect(allowed).toBe(false);
  expect(api.put).toHaveBeenCalledWith('/auth/ai-consent', { accepted: true, policy_version: 'test-policy' }, expect.any(Object));
  resolveSave({ data: { ...policy, accepted: true, accepted_at: '2026-09-06T00:00:00Z' } });
  await pending; expect(allowed).toBe(true);
});

it('fails closed if saving explicit consent fails', async () => {
  (api.put as jest.Mock).mockRejectedValue(new Error('offline'));
  const pending = ensureAIConsent(); await flush(); buttons()[1].onPress();
  await expect(pending).resolves.toBe(false);
});

it('does not inherit an open consent dialog across account changes', async () => {
  const pending = ensureAIConsent(); await flush();
  setAIConsentIdentity('session-b'); buttons()[1].onPress();
  await expect(pending).resolves.toBe(false);
  expect(api.put).not.toHaveBeenCalled();
});

it('reuses a persisted decision without repeated dialogs but rechecks server policy', async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: { ...policy, accepted: true, accepted_at: '2026-09-06T00:00:00Z' } });
  await expect(ensureAIConsent()).resolves.toBe(true);
  expect(Alert.alert).not.toHaveBeenCalled();
  (api.get as jest.Mock).mockResolvedValue({ data: { ...policy, policy_version: 'new-policy' } });
  const pending = ensureAIConsent(); await flush(); buttons()[0].onPress();
  await expect(pending).resolves.toBe(false);
});

it('revocation is persisted and blocks later sharing', async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: { ...policy, accepted: true, accepted_at: '2026-09-06T00:00:00Z' } });
  (api.put as jest.Mock).mockResolvedValue({ data: policy });
  const pending = manageAIConsent(); await flush(); buttons()[1].onPress(); await pending;
  expect(api.put).toHaveBeenCalledWith('/auth/ai-consent', { accepted: false, policy_version: 'test-policy' }, expect.any(Object));
  (Alert.alert as jest.Mock).mockClear();
  (api.get as jest.Mock).mockResolvedValue({ data: policy });
  const request = requireAIConsent(); await flush(); buttons()[0].onPress();
  await expect(request).rejects.toThrow('ai_consent_required');
});

it('keeps sharing blocked while revocation is waiting for the server', async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: { ...policy, accepted: true, accepted_at: '2026-09-06T00:00:00Z' } });
  await ensureAIConsent();
  expect(hasAIConsent()).toBe(true);
  let finish: (value: unknown) => void = () => {};
  (api.put as jest.Mock).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const revoke = manageAIConsent(); await flush(); buttons()[1].onPress(); await flush();
  expect(hasAIConsent()).toBe(false);
  await expect(ensureAIConsent()).resolves.toBe(false);
  finish({ data: policy }); await revoke;
});

it('coalesces concurrent first sends into one disclosure', async () => {
  const first = ensureAIConsent(); const second = ensureAIConsent(); await flush();
  expect(Alert.alert).toHaveBeenCalledTimes(1);
  buttons()[0].onPress();
  await expect(Promise.all([first, second])).resolves.toEqual([false, false]);
});

it('clears prior authorization when policy fetch fails', async () => {
  (api.get as jest.Mock).mockResolvedValueOnce({ data: { ...policy, accepted: true, accepted_at: '2026-09-06T00:00:00Z' } });
  await ensureAIConsent();
  (api.get as jest.Mock).mockRejectedValueOnce(new Error('offline'));
  await expect(ensureAIConsent()).resolves.toBe(false);
  expect(hasAIConsent()).toBe(false);
});
