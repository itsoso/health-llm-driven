import { fetchHealthOperatingReview } from '../healthOperatingReview';
import api from '../api';

jest.mock('../api', () => ({
  get: jest.fn(),
}));

describe('fetchHealthOperatingReview', () => {
  it('calls daily plan review endpoint with supported window', async () => {
    (api.get as jest.Mock).mockResolvedValueOnce({
      data: { window_days: 7, execution: { total_events: 0 }, metrics: {}, completed_action_keys: [] },
    });

    const data = await fetchHealthOperatingReview(7);

    expect(api.get).toHaveBeenCalledWith('/daily-plan/review', { params: { window_days: 7 } });
    expect(data.window_days).toBe(7);
  });
});
