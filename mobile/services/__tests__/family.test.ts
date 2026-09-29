import api from '../api';
import { fetchFamilyMemberHealth, updateFamilyRelationship, leaveFamily, acceptFamilyInvitation } from '../family';
jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn(), delete: jest.fn() } }));

beforeEach(() => jest.clearAllMocks());
it('reads the authorized subject through the family endpoint without switching tokens', async () => {
  const records = { member: { user_id: 42 }, reports: [], episodes: [], limit: 20 };
  (api.get as jest.Mock).mockResolvedValue({ data: records });
  expect(await fetchFamilyMemberHealth(42)).toBe(records);
  expect(api.get).toHaveBeenCalledWith('/family/members/42/health');
  expect(api.post).not.toHaveBeenCalled();
});
it('propagates revoked access rather than pretending there are no reports', async () => {
  const denied = { response: { status: 403 } };
  (api.get as jest.Mock).mockRejectedValue(denied);
  await expect(fetchFamilyMemberHealth(42)).rejects.toBe(denied);
});
it('preserves daughter relationship and nickname during acceptance', async () => {
  (api.post as jest.Mock).mockResolvedValue({ data: {} });
  await acceptFamilyInvitation('ABC123', 'daughter', '小禾');
  expect(api.post).toHaveBeenCalledWith('/family/invitation/accept', { code: 'ABC123', relationship_type: 'daughter', nickname: '小禾' });
});
it('updates relationship without broadening sharing permissions', async () => {
  (api.patch as jest.Mock).mockResolvedValue({ data: {} });
  await updateFamilyRelationship(12, 'daughter', '小禾');
  expect(api.patch).toHaveBeenCalledWith('/family/members/12/relationship', { relationship_type: 'daughter', nickname: '小禾' });
});
it('revokes membership using the membership id', async () => {
  (api.delete as jest.Mock).mockResolvedValue({ data: {} });
  await leaveFamily(12);
  expect(api.delete).toHaveBeenCalledWith('/family/members/12');
});
