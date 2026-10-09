import api from '../api';
import { fetchHealthWeekNavigation, fetchHealthNavigationAction, recordHealthNavigationEvent, validHealthActionRef, navigationErrorMessage } from '../healthNavigation';
jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));

describe('Health navigation authenticated contract', () => {
  beforeEach(() => jest.clearAllMocks());
  it('reads only the dedicated projection without requesting a generated plan', async () => {
    (api.get as jest.Mock).mockResolvedValue({ data: { schema_version: 'health_week_navigation.v1' } });
    await fetchHealthWeekNavigation();
    expect(api.get).toHaveBeenCalledWith('/health-navigation/summary', expect.objectContaining({ __revaConsentRevision: expect.any(Number) }));
  });
  it('accepts internal references and only the bounded grant-scoped dotted format', async () => {
    const internal = 'ab'.repeat(16);
    const external = 'e8563c9e-ffba-4f7b-a2b0-b2adbdd4da51.' + 'ab'.repeat(32);
    expect(validHealthActionRef(internal)).toBe(true);
    expect(validHealthActionRef(external)).toBe(true);
    (api.get as jest.Mock).mockResolvedValue({ data: {} });
    await fetchHealthNavigationAction(external);
    expect(api.get).toHaveBeenCalledWith(`/health-navigation/actions/${encodeURIComponent(external)}`, expect.any(Object));
    for (const invalid of ['opaque.ref', '../action', 'a.b.c', external + '/detail', external + '?token=x', external.replace('.', '%2e')]) {
      expect(validHealthActionRef(invalid)).toBe(false);
    }
  });
  it('describes feature availability without exposing backend errors', () => {
    expect(navigationErrorMessage({ response: { status: 503 }, message: 'backend-secret' })).toBe('健康周导航暂未开放或暂时不可用，请稍后重试。');
  });
  it('rejects URL payloads and invalid refs before making a request', async () => {
    await expect(fetchHealthNavigationAction('https://example.com/private')).rejects.toThrow();
    expect(api.get).not.toHaveBeenCalled();
  });
  it('sends only versioned event fields and preserves the retry operation identity', async () => {
    (api.post as jest.Mock).mockResolvedValue({ data: { accepted: true } });
    const input = { event_type: 'completed' as const, expected_revision: 'r1', operation_id: 'e8563c9e-ffba-4f7b-a2b0-b2adbdd4da51' };
    await recordHealthNavigationEvent('opaque_ref_123', input);
    expect(api.post).toHaveBeenCalledWith('/health-navigation/actions/opaque_ref_123/events', input, expect.any(Object));
  });
});

it('rejects a response returned after the authentication identity changes', async () => {
  const { invalidateAIConsent } = require('../aiConsentState');
  let complete!: (value: unknown) => void;
  (api.get as jest.Mock).mockImplementationOnce(() => new Promise(resolve => { complete = resolve; }));
  const pending = fetchHealthWeekNavigation();
  invalidateAIConsent();
  complete({ data: { schema_version: 'health_week_navigation.v1' } });
  await expect(pending).rejects.toThrow('登录状态已变化');
});
