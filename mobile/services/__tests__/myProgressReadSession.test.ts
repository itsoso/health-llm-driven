import api, { getAuthSessionSnapshot } from '../api';
import { aiConsentRevision, invalidateAIConsent, setAIConsentIdentity } from '../aiConsentState';
import { fetchMyProgress } from '../myProgress';
import { fetchHealthOperatingReview } from '../healthOperatingReview';

jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn() },
  getAuthSessionSnapshot: jest.fn(),
}));
const mockGet = api.get as jest.Mock;
const mockSnapshot = getAuthSessionSnapshot as jest.Mock;
const session = () => ({ owner: 9, revision: aiConsentRevision(), generation: 7 });

beforeEach(() => {
  mockGet.mockReset().mockResolvedValue({ data: { marker: 'owned' } });
  setAIConsentIdentity(null);
  setAIConsentIdentity('progress-test-credential');
  mockSnapshot.mockReturnValue({ generation: 7, initialized: true, token: 'progress-test-credential' });
});

const readers = [
  { name: 'progress', fetch: (scope: ReturnType<typeof session>) => fetchMyProgress(30, scope), url: '/action-cards/me/progress?days=30' },
  { name: 'review', fetch: (scope: ReturnType<typeof session>) => fetchHealthOperatingReview(30, scope), url: '/daily-plan/review' },
];

describe.each(readers)('$name scoped read', ({ fetch, url }) => {
  it('binds the request to the owner and consent revision', async () => {
    const scope = session();
    await expect(fetch(scope)).resolves.toEqual({ marker: 'owned' });
    expect(mockGet).toHaveBeenCalledWith(url, expect.objectContaining({
      headers: { 'X-Reva-AI-Subject': '9' }, __revaConsentRevision: scope.revision,
    }));
  });

  it('rejects an obsolete consent revision before requesting', async () => {
    const scope = session();
    invalidateAIConsent();
    await expect(fetch(scope)).rejects.toThrow('auth_session_changed');
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('discards a response after consent changes', async () => {
    let resolve!: (value: unknown) => void;
    mockGet.mockReturnValue(new Promise(done => { resolve = done; }));
    const pending = fetch(session());
    invalidateAIConsent(true);
    resolve({ data: { marker: 'obsolete' } });
    await expect(pending).rejects.toThrow('auth_session_changed');
  });

  it('discards a response after a token/account generation changes', async () => {
    let resolve!: (value: unknown) => void;
    mockGet.mockReturnValue(new Promise(done => { resolve = done; }));
    const pending = fetch(session());
    mockSnapshot.mockReturnValue({ generation: 8, initialized: true, token: 'next-credential' });
    resolve({ data: { marker: 'obsolete' } });
    await expect(pending).rejects.toThrow('auth_session_changed');
  });

  it('rejects a changed transport generation before requesting', async () => {
    const scope = session();
    mockSnapshot.mockReturnValue({ generation: 8, initialized: true, token: 'next-credential' });
    await expect(fetch(scope)).rejects.toThrow('auth_session_changed');
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('rejects a session with no consent identity before requesting', async () => {
    setAIConsentIdentity(null);
    await expect(fetch(session())).rejects.toThrow('auth_session_changed');
    expect(mockGet).not.toHaveBeenCalled();
  });

  it('rejects an invalid owner before requesting', async () => {
    await expect(fetch({ ...session(), owner: 0 })).rejects.toThrow('auth_session_changed');
    expect(mockGet).not.toHaveBeenCalled();
  });
});
