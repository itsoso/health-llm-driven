jest.mock('../api', () => ({
  __esModule: true,
  default: { post: jest.fn() },
}));

import api from '../api';
import { verifyPredictions } from '../consultations';

const mockPost = api.post as jest.Mock;

describe('consultations service', () => {
  beforeEach(() => jest.clearAllMocks());

  it('normalizes backend prediction verification suggestions', async () => {
    mockPost.mockResolvedValueOnce({
      data: [{
        item_id: 11,
        item_code: 'P1',
        title: 'HRV 提升',
        actual_value: 48.5,
        suggested_status: 'met',
      }],
    });

    const result = await verifyPredictions(7);

    expect(mockPost).toHaveBeenCalledWith('/health-consultations/me/7/verify');
    expect(result.verified_count).toBe(1);
    expect(result.predictions[0]).toMatchObject({
      item_id: 11,
      suggested_status: 'met',
      actual_value: 48.5,
    });
  });
});
