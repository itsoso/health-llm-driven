/* eslint-disable import/first */

const mockApiPost = jest.fn();

jest.mock('../api', () => ({
  __esModule: true,
  default: {
    post: (...args: any[]) => mockApiPost(...args),
  },
}));

import { createDietRecord } from '../diet';

describe('diet service', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('returns persisted diet records with an id', async () => {
    mockApiPost.mockResolvedValueOnce({
      data: {
        id: 88,
        record_date: '2026-07-09',
        meal_type: 'lunch',
        food_items: '牛肉面',
      },
    });

    await expect(createDietRecord({
      record_date: '2026-07-09',
      meal_type: 'lunch',
      food_items: '牛肉面',
    })).resolves.toEqual(expect.objectContaining({ id: 88 }));
  });

  it('rejects create responses that do not include a persisted record id', async () => {
    mockApiPost.mockResolvedValueOnce({ data: { ok: true } });

    await expect(createDietRecord({
      record_date: '2026-07-09',
      meal_type: 'lunch',
      food_items: '牛肉面',
    })).rejects.toThrow('diet_record_missing_id');
  });
});
