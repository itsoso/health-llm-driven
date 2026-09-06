import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { isAiRequest, manageAiConsent, registerAiConsentPresenter, requireAiConsent, setAiConsentUser } from './aiConsent';

const policy = {
  policy_version: 'test-v1', accepted: false, accepted_at: null,
  recipients: [{ id: 'test-vendor', name: '测试 AI 服务', purpose: '处理输入' }],
  data_types: ['用户输入'], purpose: '响应请求',
};
let cleanup: (() => void) | undefined;
let requests: { url: string; method: string; body: unknown }[];
let accepted = false;
let cookieUser = 101;
beforeEach(() => {
  requests = []; accepted = false; cookieUser = 101;
  setAiConsentUser(101);
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    requests.push({ url, method: init?.method || 'GET', body: init?.body });
    if (url.endsWith('/auth/me')) return Response.json({ id: cookieUser });
    if (init?.method === 'PUT') accepted = JSON.parse(String(init.body)).accepted;
    return Response.json({ ...policy, accepted });
  });
});
afterEach(() => { cleanup?.(); setAiConsentUser(null); vi.unstubAllGlobals(); });

describe('AI consent authority', () => {
  it('declining does not persist permission', async () => {
    cleanup = registerAiConsentPresenter(async () => false, () => {});
    await expect(requireAiConsent()).rejects.toThrow('未发送');
    expect(requests.some(item => item.method === 'PUT')).toBe(false);
  });

  it('presenter cannot grant permission without server acknowledgement', async () => {
    cleanup = registerAiConsentPresenter(async () => true, () => {});
    await expect(requireAiConsent()).rejects.toThrow('未发送');
  });

  it('sends the reviewed policy version only on explicit agreement', async () => {
    cleanup = registerAiConsentPresenter(async (_, save) => { await save(true); return true; }, () => {});
    await requireAiConsent();
    expect(JSON.parse(String(requests.find(item => item.method === 'PUT')?.body)))
      .toEqual({ accepted: true, policy_version: 'test-v1' });
  });

  it('checks revocation again on the next dispatch', async () => {
    accepted = true;
    await requireAiConsent();
    accepted = false;
    cleanup = registerAiConsentPresenter(async () => false, () => {});
    await expect(requireAiConsent()).rejects.toThrow('未发送');
  });

  it('withdraws through the server without granting permission', async () => {
    accepted = true;
    cleanup = registerAiConsentPresenter(async (_, save) => { await save(false); return false; }, () => {});
    await manageAiConsent();
    expect(accepted).toBe(false);
  });

  it('rejects a dialog from the previous signed-in user', async () => {
    cleanup = registerAiConsentPresenter(async (_, save) => {
      setAiConsentUser(202);
      await save(true);
      return true;
    }, () => {});
    await expect(requireAiConsent()).rejects.toThrow('登录状态');
    expect(requests.some(item => item.method === 'PUT')).toBe(false);
  });

  it('does not reuse a cookie account switched in another tab', async () => {
    cookieUser = 202; accepted = true;
    await expect(requireAiConsent()).rejects.toThrow('账号已变化');
  });

  it('fails closed when the policy service is unavailable', async () => {
    vi.stubGlobal('fetch', async () => new Response('', { status: 503 }));
    await expect(requireAiConsent()).rejects.toThrow();
  });
});

it.each(['/daily-health/water', '/diet/records', '/auth/delete-account', '/export/health-data', '/profile/me'])
  ('does not gate non-AI records or account controls: %s', path => expect(isAiRequest(path, 'post')).toBe(false));
it.each(['/agent/stream', '/chat/transcribe', '/orchestrator/chat', '/medical-exams/import/image', '/health-report/generate', '/prescriptions/recognize'])
  ('gates explicit AI actions: %s', path => expect(isAiRequest(path, 'post')).toBe(true));
