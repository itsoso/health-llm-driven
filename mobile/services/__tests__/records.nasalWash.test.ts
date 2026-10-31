import api from '../api';
import { createNasalWashRequest, recordNasalWash } from '../records';
jest.mock('../api', () => ({ __esModule: true, default: { post: jest.fn() } }));
jest.mock('expo-modules-core', () => ({ uuid: { v4: jest.fn(() => 'nasal-event-id') } }));
it('posts one event without a cached total, owner or invented volume', async () => {
  (api.post as jest.Mock).mockResolvedValue({ data: { nasal_wash_times: [{ event_id: 'nasal-event-id' }] } });
  const request = createNasalWashRequest();
  await recordNasalWash(request);
  expect(api.post).toHaveBeenCalledWith('/checkin/nasal-wash', {
    event_id: 'nasal-event-id', record_date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/), count: 1,
  });
});

it('rejects an acknowledgement without this event', async () => {
  (api.post as jest.Mock).mockResolvedValue({ data: { nasal_wash_times: [] } });
  await expect(recordNasalWash(createNasalWashRequest())).rejects.toThrow('记录未确认');
});

it('explains validation rejection without claiming a network failure', async () => {
  (api.post as jest.Mock).mockRejectedValue({ response: { status: 422 } });
  await expect(recordNasalWash(createNasalWashRequest())).rejects.toThrow('记录内容未通过校验');
});
