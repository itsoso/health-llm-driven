import { streamChat } from '../chat';
import { setAppEgressMode } from '../egressPolicy';
import {
  acceptAIConsentRevision, aiConsentRevision, hasAIConsent, invalidateAIConsent,
  isAIConsentRequired, setAIConsentIdentity,
} from '../aiConsentState';

jest.mock('../auth', () => ({ getToken: jest.fn(async () => 'session-a') }));
jest.mock('../api', () => ({ BASE_URL: 'https://example.invalid/api' }));

class PendingXHR {
  static instances: PendingXHR[] = [];
  status = 200;
  responseText = '';
  timeout = 0;
  onload?: () => void;
  onprogress?: () => void;
  open = jest.fn();
  setRequestHeader = jest.fn();
  send = jest.fn();
  abort = jest.fn();
  constructor() { PendingXHR.instances.push(this); }
}

const originalXHR = global.XMLHttpRequest;
beforeEach(() => {
  PendingXHR.instances = [];
  global.XMLHttpRequest = PendingXHR as unknown as typeof XMLHttpRequest;
  setAppEgressMode('cloud_account');
  setAIConsentIdentity('session-a');
  acceptAIConsentRevision(aiConsentRevision());
});
afterEach(() => {
  global.XMLHttpRequest = originalXHR;
  setAppEgressMode(null);
  setAIConsentIdentity(null);
});

it.each(['http403', 'sse'])('invalidates the current grant and still reports %s', async (kind) => {
  const iter = streamChat('hello'); const first = iter.next();
  await Promise.resolve();
  const xhr = PendingXHR.instances[0];
  if (kind === 'http403') {
    xhr.status = 403; xhr.responseText = '{"detail":{"code":"ai_consent_required"}}'; xhr.onload?.();
    await expect(first).rejects.toThrow('重新确认');
  } else {
    xhr.responseText = 'data: {"event":"error","data":{"code":"ai_consent_required"}}\n\n'; xhr.onprogress?.();
    await expect(first).resolves.toMatchObject({ value: { type: 'error' } });
    await iter.return(undefined);
  }
  expect(hasAIConsent()).toBe(false);
  expect(isAIConsentRequired()).toBe(true);
  expect(xhr.send).toHaveBeenCalledTimes(1);
});

it.each([
  ['http403', 'account-switch'], ['sse', 'account-switch'],
  ['http403', 'new-consent-generation'], ['sse', 'new-consent-generation'],
])('preserves a new grant after a late %s from %s', async (kind, change) => {
  const iter = streamChat('hello'); const first = iter.next();
  await Promise.resolve();
  const xhr = PendingXHR.instances[0];
  if (change === 'account-switch') setAIConsentIdentity('session-b');
  else invalidateAIConsent(true);
  acceptAIConsentRevision(aiConsentRevision());
  if (kind === 'http403') {
    xhr.status = 403; xhr.responseText = '{"detail":{"code":"ai_consent_required"}}'; xhr.onload?.();
    await expect(first).rejects.toThrow('重新确认');
  } else {
    xhr.responseText = 'data: {"event":"error","data":{"code":"ai_consent_required"}}\n\n'; xhr.onprogress?.();
    await expect(first).resolves.toMatchObject({ value: { type: 'error' } });
    await iter.return(undefined);
  }
  expect(hasAIConsent()).toBe(true);
  expect(isAIConsentRequired()).toBe(false);
  expect(xhr.send).toHaveBeenCalledTimes(1);
  expect(PendingXHR.instances).toHaveLength(1);
});
