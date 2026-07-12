import * as SecureStore from 'expo-secure-store';

import {
  clearDietPhotoDraft,
  dietPhotoDraftStorageKey,
  loadDietPhotoDraft,
  saveDietPhotoDraft,
} from '../dietPhotoDraftStorage';

const getItemAsync = SecureStore.getItemAsync as jest.Mock;
const setItemAsync = SecureStore.setItemAsync as jest.Mock;
const deleteItemAsync = SecureStore.deleteItemAsync as jest.Mock;

describe('dietPhotoDraftStorage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getItemAsync.mockResolvedValue(null);
  });

  it('uses a valid user-scoped SecureStore key', () => {
    expect(dietPhotoDraftStorageKey(7)).toBe('diet_photo_draft_v1_user_7');
  });

  it('persists compact metadata without image bytes or unrestricted model output', async () => {
    await saveDietPhotoDraft(7, {
      record_date: '2026-07-11',
      meal_type: 'lunch',
      food_items: '鸡胸肉 200g',
      image_base64: 'private-photo-base64',
      photo_draft_token: 'photo-draft-token-1234567890',
      ai_raw_result: {
        success: true,
        foods: [{
          name: '鸡胸肉', quantity: '200g', calories: 330, protein: 62,
          carbs: 0, fat: 7.2, fiber: 0, confidence: 0.9,
          food_id: 'cfc:chicken_breast', source: 'china_food_composition',
          quantity_grams: 200,
          nutrition_basis: 'food_table',
          portion_basis: 'vision_estimate',
          portion_confidence: 0.72,
        }],
        meal_description: '鸡胸肉 200g',
        health_tips: '这段不应持久化',
        total_calories: 330,
        total_protein: 62,
        total_carbs: 0,
        total_fat: 7.2,
        error: null,
      },
    }, 1_000);

    const [, raw] = setItemAsync.mock.calls[0];
    expect(raw).not.toContain('private-photo-base64');
    expect(raw).not.toContain('这段不应持久化');
    expect(JSON.parse(raw)).toMatchObject({
      version: 1,
      saved_at: 1_000,
      expires_at: 1_000 + 24 * 60 * 60 * 1_000,
      record: {
        food_items: '鸡胸肉 200g',
        photo_draft_token: 'photo-draft-token-1234567890',
        ai_raw_result: {
          foods: [{
            name: '鸡胸肉',
            nutrition_basis: 'food_table',
            portion_basis: 'vision_estimate',
            portion_confidence: 0.72,
          }],
        },
      },
    });
    expect(JSON.parse(raw).record).not.toHaveProperty('image_base64');
  });

  it('deletes and ignores an expired snapshot', async () => {
    getItemAsync.mockResolvedValueOnce(JSON.stringify({
      version: 1,
      saved_at: 1_000,
      expires_at: 2_000,
      record: {
        record_date: '2026-07-11', meal_type: 'lunch', food_items: '鸡胸肉',
        photo_draft_token: 'photo-draft-token-1234567890',
      },
    }));

    await expect(loadDietPhotoDraft(7, 2_001)).resolves.toBeNull();
    expect(deleteItemAsync).toHaveBeenCalledWith('diet_photo_draft_v1_user_7');
  });

  it('clears only the current user snapshot', async () => {
    await clearDietPhotoDraft(7);
    expect(deleteItemAsync).toHaveBeenCalledWith('diet_photo_draft_v1_user_7');
  });
});
