jest.mock('../api', () => ({ __esModule: true, BASE_URL: 'https://synthetic.invalid/api', default: { get: jest.fn(), post: jest.fn() } }));
import api from '../api';
import { aiConsentRevision, setAIConsentIdentity } from '../aiConsentState';
import { bowelPhotoUrl, createBowelRecord, listBowelRecords, uploadBowelPhoto } from '../excretion';

beforeEach(() => { jest.clearAllMocks(); setAIConsentIdentity(`synthetic-${Math.random()}`); });
it('binds writes to the captured session and preserves the request UUID', async () => {
  (api.post as jest.Mock).mockResolvedValueOnce({ data: { id: 3, user_id: 7 } });
  const session = { owner: 7, revision: aiConsentRevision() };
  const input = { type: 'bowel' as const, record_date: '2026-10-11', record_time: '08:30:00', client_request_id: 'bdbe0a80-b169-4a45-86d3-f4c28419654d' };
  await createBowelRecord(session, input);
  expect(api.post).toHaveBeenCalledWith('/excretion/records', input, expect.objectContaining({ headers: { 'X-Reva-AI-Subject': '7' }, __revaConsentRevision: session.revision }));
});
it('rejects a stale session before sending and after a delayed response', async () => {
  const session = { owner: 7, revision: aiConsentRevision() };
  setAIConsentIdentity('synthetic-switched');
  await expect(listBowelRecords(session, '2026-10-11')).rejects.toThrow('auth_session_changed');
  expect(api.get).not.toHaveBeenCalled();
  const next = { owner: 8, revision: aiConsentRevision() };
  (api.get as jest.Mock).mockImplementationOnce(async () => {
    setAIConsentIdentity('synthetic-switched-again'); return { data: [] };
  });
  await expect(listBowelRecords(next, '2026-10-11')).rejects.toThrow('auth_session_changed');
});
it('only accepts an upload result for the captured owner', async () => {
  (api.post as jest.Mock).mockResolvedValueOnce({ data: { success: true, filename: 'medical/8/photo.jpg' } });
  await expect(uploadBowelPhoto({ owner: 7, revision: aiConsentRevision() }, { uri: 'file:///synthetic.jpg' })).rejects.toThrow('private_upload_failed');
});
it('allows only private backend photo paths', () => {
  expect(bowelPhotoUrl('/api/v1/upload/files/medical/7/photo.jpg?expires=123&signature=synthetic')).toBe('https://synthetic.invalid/api/v1/upload/files/medical/7/photo.jpg?expires=123&signature=synthetic');
  expect(() => bowelPhotoUrl('https://other.invalid/secret.jpg')).toThrow();
  expect(() => bowelPhotoUrl('/api/v1/upload/files/avatar/photo.jpg')).toThrow();
});
it('rejects a response owned by another account', async () => {
  (api.get as jest.Mock).mockResolvedValueOnce({ data: [{ id: 3, user_id: 8 }] });
  await expect(listBowelRecords({ owner: 7, revision: aiConsentRevision() }, '2026-10-11')).rejects.toThrow('record_owner_mismatch');
});
