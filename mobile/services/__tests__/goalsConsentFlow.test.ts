import { Alert } from 'react-native';
import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import api, { setRuntimeAuthToken } from '../api';
import { generateGoalsFromAnalysis } from '../goals';
import { hasAIConsent, invalidateAIConsent } from '../aiConsentState';

jest.mock('../auth', () => ({ getToken: jest.fn(async () => 'synthetic-consent-session') }));

const policy = {
  policy_version: 'synthetic-policy', accepted: true, accepted_at: '2026-10-12T00:00:00Z',
  recipients: [{ id: 'synthetic', name: '测试接收方', purpose: '测试' }],
  data_types: ['测试文本'], purpose: '测试',
};

describe('goals → API interceptor → consent → transport', () => {
  const originalAdapter = api.defaults.adapter;
  beforeEach(() => {
    setRuntimeAuthToken('synthetic-consent-session');
    invalidateAIConsent();
    jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  });
  afterEach(() => { api.defaults.adapter = originalAdapter; jest.restoreAllMocks(); });

  it('recovers a transient read then sends the generate request exactly once', async () => {
    const requests: string[] = [];
    api.defaults.adapter = async config => {
      requests.push(config.url!);
      if (requests.length === 1) throw new AxiosError('synthetic network failure', 'ERR_NETWORK', config);
      return { config, status: 200, statusText: 'OK', headers: {}, data: config.url === '/auth/ai-consent' ? policy : [] };
    };
    await expect(generateGoalsFromAnalysis()).resolves.toEqual([]);
    expect(requests).toEqual(['/auth/ai-consent', '/auth/ai-consent', '/goals/me/generate-from-analysis']);
    expect(hasAIConsent()).toBe(true);
    expect(Alert.alert).not.toHaveBeenCalled();
  });

  it.each([401, 503])('sends no generation when policy status is %s', async status => {
    const requests: string[] = [];
    api.defaults.adapter = async config => {
      requests.push(config.url!);
      throw new AxiosError('synthetic policy failure', 'ERR_BAD_RESPONSE', config, undefined,
        { config, status, statusText: 'failed', headers: {}, data: {} });
    };
    await expect(generateGoalsFromAnalysis()).rejects.toThrow('ai_consent_required');
    expect(requests).toEqual(Array(status === 401 ? 1 : 2).fill('/auth/ai-consent'));
    expect(hasAIConsent()).toBe(false);
  });

  it('does not generate or save consent if the disclosure is declined', async () => {
    const requests: string[] = [];
    api.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
      requests.push(config.url!);
      return { config, status: 200, statusText: 'OK', headers: {}, data: { ...policy, accepted: false, accepted_at: null } };
    };
    (Alert.alert as jest.Mock).mockImplementation((_title, _message, buttons) => buttons[0].onPress());
    await expect(generateGoalsFromAnalysis()).rejects.toThrow('ai_consent_required');
    expect(requests).toEqual(['/auth/ai-consent']);
    expect(hasAIConsent()).toBe(false);
  });

  it('invalidates a server-rejected grant without replaying the generation write', async () => {
    const requests: string[] = [];
    api.defaults.adapter = async config => {
      requests.push(config.url!);
      if (config.url === '/auth/ai-consent') {
        return { config, status: 200, statusText: 'OK', headers: {}, data: policy };
      }
      throw new AxiosError('synthetic policy change', 'ERR_BAD_RESPONSE', config, undefined,
        { config, status: 403, statusText: 'Forbidden', headers: {}, data: { detail: { code: 'ai_consent_required' } } });
    };
    await expect(generateGoalsFromAnalysis()).rejects.toMatchObject({ response: { status: 403 } });
    expect(requests).toEqual(['/auth/ai-consent', '/goals/me/generate-from-analysis']);
    expect(hasAIConsent()).toBe(false);
  });
});
