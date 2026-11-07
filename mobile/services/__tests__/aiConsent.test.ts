import { Alert } from 'react-native';
import api from '../api';
import { ensureAIConsent, manageAIConsent, requireAIConsent } from '../aiConsent';
import { setAIConsentIdentity, invalidateAIConsent } from '../aiConsentState';
import { showAIConsent } from '../aiConsentPresentation';
import { hasAIConsent, isAIConsentRequired } from '../aiConsentState';

jest.mock('../aiConsentPresentation', () => ({ showAIConsent: jest.fn() }));
jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn(), put: jest.fn() } }));
jest.mock('../auth', () => ({ getToken: jest.fn(async () => 'session-a') }));

const policy = {
  policy_version: 'test-policy', accepted: false, accepted_at: null,
  recipients: [{ id: 'provider', name: '测试 AI 提供方', purpose: '健康问答' }],
  data_types: ['健康文本', '图片', '语音'], purpose: '生成健康管理回复',
};
const flush = async () => { for (let n = 0; n < 12; n++) await Promise.resolve(); };
let choose: (decision: 'accept' | 'decline' | 'revoke' | 'keep') => void;
const buttons = () => (showAIConsent as jest.Mock).mock.calls.at(-1)[1] === 'manage'
  ? [{ onPress: () => choose('keep') }, { onPress: () => choose('revoke') }]
  : [{ onPress: () => choose('decline') }, { onPress: () => choose('accept') }];

beforeEach(() => {
  jest.clearAllMocks();
  (showAIConsent as jest.Mock).mockImplementation(() => new Promise(resolve => { choose = resolve; }));
  setAIConsentIdentity(null); setAIConsentIdentity('session-a'); invalidateAIConsent();
  jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  (api.get as jest.Mock).mockResolvedValue({ data: policy });
  (api.put as jest.Mock).mockResolvedValue({ data: { ...policy, accepted: true, accepted_at: '2026-09-06T00:00:00Z' } });
});

it('does not authorize or write consent when disclosure is declined', async () => {
  const pending = ensureAIConsent(); await flush();
  expect(showAIConsent).toHaveBeenCalledWith(policy, 'request');
  buttons()[0].onPress();
  await expect(pending).resolves.toBe(false);
  expect(api.put).not.toHaveBeenCalled();
  expect(isAIConsentRequired()).toBe(true);
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
  expect(isAIConsentRequired()).toBe(false);
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

it('reuses a persisted current-policy grant across app sessions without repeated disclosure', async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: { ...policy, accepted: true, accepted_at: '2026-09-06T00:00:00Z' } });
  const restored = ensureAIConsent(); await flush();
  expect(showAIConsent).not.toHaveBeenCalled();
  await expect(restored).resolves.toBe(true);
  expect(api.put).not.toHaveBeenCalled();

  invalidateAIConsent();
  const restarted = ensureAIConsent(); await flush();
  expect(showAIConsent).not.toHaveBeenCalled();
  await expect(restarted).resolves.toBe(true);
  expect(api.put).not.toHaveBeenCalled();

  (api.get as jest.Mock).mockResolvedValue({ data: { ...policy, policy_version: 'new-policy' } });
  const pending = ensureAIConsent(); await flush(); buttons()[0].onPress();
  await expect(pending).resolves.toBe(false);
  expect(showAIConsent).toHaveBeenCalledTimes(1);
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
  await expect(ensureAIConsent()).resolves.toBe(true);
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
  expect(showAIConsent).toHaveBeenCalledTimes(1);
  buttons()[0].onPress();
  await expect(Promise.all([first, second])).resolves.toEqual([false, false]);
});

it('clears prior authorization when policy fetch fails', async () => {
  (api.get as jest.Mock).mockResolvedValueOnce({ data: { ...policy, accepted: true, accepted_at: '2026-09-06T00:00:00Z' } });
  await expect(ensureAIConsent()).resolves.toBe(true);
  (api.get as jest.Mock).mockRejectedValueOnce(new Error('offline'));
  await expect(ensureAIConsent()).resolves.toBe(false);
  expect(hasAIConsent()).toBe(false);
  expect(isAIConsentRequired()).toBe(false);
});

it('retries one transient policy read without granting or sending content early', async () => {
  (api.get as jest.Mock).mockRejectedValueOnce({ code: 'ERR_NETWORK' });
  (api.get as jest.Mock).mockResolvedValueOnce({ data: { ...policy, accepted: true, accepted_at: '2026-09-06T00:00:00Z' } });
  await expect(ensureAIConsent()).resolves.toBe(true);
  expect(api.get).toHaveBeenCalledTimes(2);
  expect(api.put).not.toHaveBeenCalled();
  expect(Alert.alert).not.toHaveBeenCalled();
});

it.each([
  [{ response: { status: 401 } }, '登录已失效'],
  [{ response: { status: 503 } }, 'AI 授权服务暂不可用'],
])('explains policy failures without pretending every failure is offline', async (error, title) => {
  (api.get as jest.Mock).mockRejectedValue(error);
  await expect(ensureAIConsent()).resolves.toBe(false);
  expect(hasAIConsent()).toBe(false);
  expect(api.get).toHaveBeenCalledTimes(title === '登录已失效' ? 1 : 2);
  expect(Alert.alert).toHaveBeenCalledWith(title, expect.any(String));
});

it('does not show a stale policy failure after an account switch', async () => {
  let rejectRead: (error: unknown) => void = () => {};
  (api.get as jest.Mock).mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectRead = reject; }));
  const pending = ensureAIConsent(); await flush();
  setAIConsentIdentity('session-b');
  rejectRead({ code: 'ERR_NETWORK' });
  await expect(pending).resolves.toBe(false);
  expect(api.get).toHaveBeenCalledTimes(1);
  expect(Alert.alert).not.toHaveBeenCalled();
});

it('does not reuse an incomplete server grant without a persisted acceptance time', async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: { ...policy, accepted: true, accepted_at: null } });
  const request = ensureAIConsent(); await flush();
  expect(showAIConsent).toHaveBeenCalledWith(expect.objectContaining({ accepted_at: null }), 'request');
  buttons()[0].onPress();
  await expect(request).resolves.toBe(false);
  expect(hasAIConsent()).toBe(false);
  expect(api.put).not.toHaveBeenCalled();
});

it('shares a pending grant with settings instead of opening a contradictory second decision', async () => {
  let finish!: (value: unknown) => void;
  (api.put as jest.Mock).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const request = ensureAIConsent(); await flush(); buttons()[1].onPress(); await flush();
  const settings = manageAIConsent(); await flush();
  expect(showAIConsent).toHaveBeenCalledTimes(1);
  expect(hasAIConsent()).toBe(false);
  finish({ data: { ...policy, accepted: true, accepted_at: '2026-11-02T00:00:00Z' } });
  await expect(request).resolves.toBe(true); await settings;
});

it('cannot regrant while a completed server revocation is still awaiting its response', async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: { ...policy, accepted: true, accepted_at: '2026-10-01T00:00:00Z' } });
  let finish!: (value: unknown) => void;
  (api.put as jest.Mock).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const revoking = manageAIConsent(); await flush(); buttons()[1].onPress(); await flush();
  (api.get as jest.Mock).mockResolvedValue({ data: policy });
  await manageAIConsent();
  expect(showAIConsent).toHaveBeenCalledTimes(1);
  expect(api.get).toHaveBeenCalledTimes(1);
  expect(hasAIConsent()).toBe(false);
  finish({ data: policy }); await revoking;
  expect(hasAIConsent()).toBe(false);
});
