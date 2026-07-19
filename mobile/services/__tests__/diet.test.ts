/* eslint-disable import/first */

const mockApiPost = jest.fn();

jest.mock('../api', () => ({
  __esModule: true,
  default: {
    post: (...args: any[]) => mockApiPost(...args),
  },
}));

import { createDietRecord, dietRecordImageUrls, type DietRecord } from '../diet';

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

  it('uses ordered photo assets before legacy image fields and removes duplicates', () => {
    const record = {
      id: 88,
      user_id: 1,
      record_date: '2026-07-19',
      meal_type: 'lunch',
      food_items: '鸡胸肉和杂粮饭',
      calories: 560,
      protein: 42,
      carbs: 48,
      fat: 12,
      fiber: 6,
      alcohol_units: null,
      image_url: '/legacy-cover.jpg',
      image_urls: ['/fallback.jpg'],
      photo_assets: [
        { id: 'asset-2', url: '/second.jpg', ordinal: 1, captured_at: null, origin: 'chat' },
        { id: 'asset-1', url: '/first.jpg', ordinal: 0, captured_at: null, origin: 'chat' },
      ],
      notes: null,
      health_tips: null,
    } satisfies DietRecord;

    expect(dietRecordImageUrls(record)).toEqual(['/first.jpg', '/second.jpg']);
  });

  it('falls back to the legacy cover image for records created before photo assets', () => {
    const record = {
      id: 89,
      user_id: 1,
      record_date: '2026-07-19',
      meal_type: 'dinner',
      food_items: '番茄鸡蛋面',
      calories: null,
      protein: null,
      carbs: null,
      fat: null,
      fiber: null,
      alcohol_units: null,
      image_url: '/legacy-cover.jpg',
      notes: null,
      health_tips: null,
    } satisfies DietRecord;

    expect(dietRecordImageUrls(record)).toEqual(['/legacy-cover.jpg']);
  });
});
