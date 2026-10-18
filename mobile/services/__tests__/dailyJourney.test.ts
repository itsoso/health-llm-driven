import api, { getAuthSessionSnapshot } from '../api';
import { dailyJourneyAPI, dailyJourneyError } from '../dailyJourney';
jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn(), delete: jest.fn() }, getAuthSessionSnapshot: jest.fn() }));
beforeEach(() => {
  jest.clearAllMocks();
  (getAuthSessionSnapshot as jest.Mock).mockReturnValue({ token: 'owner-A', initialized: true, generation: 1 });
  for (const method of [api.get, api.post, api.patch, api.delete]) (method as jest.Mock).mockResolvedValue({ data: {} });
});
it('binds read and annotation requests to the invocation owner and uses private endpoint', async () => {
  await dailyJourneyAPI.review('session');
  await dailyJourneyAPI.annotate('session', { expected_version: 2, annotations: [{ target_id: 'stop-1', label: '目的地' }] });
  expect(api.get).toHaveBeenCalledWith('/daily-journeys/sessions/session/review', { __revaExpectedAuthToken: 'owner-A' });
  expect(api.patch).toHaveBeenCalledWith('/daily-journeys/sessions/session/annotations', expect.any(Object), { __revaExpectedAuthToken: 'owner-A' });
});
it('preserves explicit headless owner expectation for canonical interceptor verification', async () => {
  (getAuthSessionSnapshot as jest.Mock).mockReturnValue({ token: 'owner-B', initialized: true, generation: 2 });
  await dailyJourneyAPI.points('session', { client_id: 'client', segment: 1, points: [] }, 'owner-A');
  expect(api.post).toHaveBeenCalledWith(expect.any(String), expect.any(Object), { __revaExpectedAuthToken: 'owner-A' });
});
it('rejects anonymous calls before transport', async () => {
  (getAuthSessionSnapshot as jest.Mock).mockReturnValue({ token: null });
  await expect(dailyJourneyAPI.list('2026-10-18')).rejects.toThrow('请先登录');
  expect(api.get).not.toHaveBeenCalled();
});
it('never exposes request data, coordinates, credentials or server detail in error copy', () => {
  for (const status of [undefined, 400, 401, 403, 404, 409, 410, 422, 500]) {
    const text = dailyJourneyError({ message: 'secret', config: { headers: { Authorization: 'secret' } }, response: { status, data: { detail: 'secret' } } });
    expect(text).not.toContain('secret');
  }
});
