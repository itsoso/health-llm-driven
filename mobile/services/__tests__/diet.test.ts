/* eslint-disable import/first */

const mockApiPost = jest.fn();

jest.mock('../api', () => ({
  __esModule: true,
  default: {
    post: (...args: any[]) => mockApiPost(...args),
  },
}));

import { createDietRecord, recognizeFood } from '../diet';

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

  it('sends photo draft confirmation idempotency as a header, not record data', async () => {
    mockApiPost.mockResolvedValueOnce({ data: { id: 89 } });

    await createDietRecord({
      record_date: '2026-07-09',
      meal_type: 'lunch',
      food_items: '牛肉面 1碗',
      photo_draft_token: 'draft-token-1234567890',
      idempotency_key: 'diet-photo:draft-token-1234567890',
    });

    expect(mockApiPost).toHaveBeenCalledWith(
      '/diet/records',
      expect.objectContaining({
        photo_draft_token: 'draft-token-1234567890',
        food_items: '牛肉面 1碗',
      }),
      { headers: { 'Idempotency-Key': 'diet-photo:draft-token-1234567890' } },
    );
    expect(mockApiPost.mock.calls[0][1]).not.toHaveProperty('idempotency_key');
  });

  it('asks recognition to create a server photo draft', async () => {
    mockApiPost.mockResolvedValueOnce({
      data: { success: true, foods: [], photo_draft_token: 'draft-token' },
    });

    await recognizeFood('photo-base64');

    expect(mockApiPost).toHaveBeenCalledWith('/diet/recognize', {
      image_base64: 'photo-base64',
      image_type: 'jpeg',
      create_photo_draft: true,
    });
  });
});
