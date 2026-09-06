import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { agentApi } from './api/ai';
import { fetchWithAiSubject, registerAiConsentPresenter, requireAiConsent, setAiConsentUser } from './aiConsent';
import api from './api/client';

let cookieSubject: number;
let changeAt: 'grant' | 'ai' | null;
let grants: number[];
let dispatches: number[];
let cleanup: () => void;

beforeEach(() => {
  cookieSubject = 101; changeAt = null; grants = []; dispatches = [];
  setAiConsentUser(101);
  cleanup = registerAiConsentPresenter(async (_, save) => { await save(true); return true; }, () => {});
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    if (url.endsWith('/auth/me')) return Response.json({ id: cookieSubject });
    if ((init?.method === 'PUT' && changeAt === 'grant') || (url.endsWith('/agent/stream') && changeAt === 'ai')) {
      cookieSubject = 202; // Another tab replaces the cookie immediately before dispatch.
    }
    const expected = new Headers(init?.headers).get('X-Reva-AI-Subject');
    if (expected !== null && expected !== String(cookieSubject)) {
      return Response.json({ detail: { code: 'auth_session_changed' } }, { status: 409 });
    }
    if (url.endsWith('/agent/stream')) {
      dispatches.push(cookieSubject);
      return new Response(new ReadableStream({ start(controller) { controller.close(); } }));
    }
    if (init?.method === 'PUT') grants.push(cookieSubject);
    return Response.json({
      subject_id: cookieSubject, policy_version: 'subject-test-v1',
      accepted: grants.includes(cookieSubject), accepted_at: null,
      recipients: [{ id: 'synthetic', name: '测试接收方', purpose: '处理输入' }],
      data_types: ['输入'], purpose: '响应请求',
    });
  });
});
afterEach(() => { cleanup(); setAiConsentUser(null); vi.unstubAllGlobals(); });

it('cannot grant B after reviewing A disclosure even if the cookie changes after the last identity read', async () => {
  changeAt = 'grant';
  await expect(requireAiConsent()).rejects.toThrow();
  expect(grants).toEqual([]);
});

it('cannot dispatch A draft as B when the cookie changes after granting and before stream dispatch', async () => {
  changeAt = 'ai';
  await expect(agentApi.streamMessage('synthetic A draft').next()).rejects.toThrow();
  expect(grants).toEqual([101]);
  expect(dispatches).toEqual([]);
});

it('does not replace an explicit A permit with the new in-memory B subject in legacy fetch', async () => {
  const headers = await requireAiConsent();
  setAiConsentUser(202); cookieSubject = 202;
  await expect(fetchWithAiSubject('/api/agent/stream', { method: 'POST', headers }))
    .rejects.toThrow('账号已变化');
  expect(dispatches).toEqual([]);
});

it('binds Axios AI dispatch to the subject that granted even when the cookie changes just before adapter dispatch', async () => {
  await expect(api.post('/chat/transcribe', { audio_base64: 'synthetic A audio' }, {
    adapter: async config => {
      cookieSubject = 202;
      if (config.headers.get('X-Reva-AI-Subject') !== String(cookieSubject)) {
        throw { response: { status: 409, data: { detail: { code: 'auth_session_changed' } } } };
      }
      dispatches.push(cookieSubject);
      return { config, data: {}, status: 200, statusText: 'OK', headers: {} };
    },
  })).rejects.toThrow('账号已变化');
  expect(dispatches).toEqual([]);
});

it('does not prepare an old draft again under a newly rendered account', async () => {
  const headers = await requireAiConsent();
  setAiConsentUser(202); cookieSubject = 202;
  await expect(agentApi.streamMessage('synthetic A draft', undefined, undefined, undefined, undefined, undefined,
    undefined, headers['X-Reva-AI-Subject']).next()).rejects.toThrow('账号已变化');
  expect(grants).toEqual([101]);
  expect(dispatches).toEqual([]);
});

it('rejects a server receipt for a different subject instead of treating it as an acknowledgement', async () => {
  vi.stubGlobal('fetch', async (_url: string, init?: RequestInit) => Response.json({
    subject_id: init?.method === 'PUT' ? 202 : 101,
    policy_version: 'subject-test-v1', accepted: init?.method === 'PUT', accepted_at: null,
    recipients: [{ id: 'synthetic', name: '测试接收方', purpose: '处理输入' }],
    data_types: ['输入'], purpose: '响应请求',
  }));
  await expect(requireAiConsent()).rejects.toThrow('授权状态尚未确认');
});
