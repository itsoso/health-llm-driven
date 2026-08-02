import type { DietRecord } from '../../../services/diet';
import {
  buildChatDietShareInput,
  buildDietSharePresentation,
  normalizePrivateDietPhotoUri,
} from '../dietSharePresentation';

function photoRecord(overrides: Partial<DietRecord> = {}): DietRecord {
  return {
    id: 705,
    user_id: 12,
    record_date: '2026-08-01',
    meal_type: 'breakfast',
    food_items: '猪柳蛋麦满分 + 脆香油条 + 大杯豆乳',
    source: 'chat_photo',
    calories: 900,
    protein: 36,
    carbs: 103,
    fat: 42,
    fiber: 5,
    alcohol_units: 0,
    image_url: '/api/v1/upload/files/diet/12/breakfast.jpg?signature=signed',
    notes: null,
    health_tips: '下一餐可以补一份蔬菜',
    ai_recognized: 1,
    ai_confidence: 0.88,
    ...overrides,
  };
}

const cardData: Record<string, unknown> = {
  recorded: true,
  record_id: 705,
  meal_type: 'breakfast',
  food_items: '猪柳蛋麦满分 + 脆香油条 + 大杯豆乳',
  source: 'chat_photo',
  calories: 900,
  protein: 36,
  carbs: 103,
  fat: 42,
  fiber: 5,
  confidence: 0.88,
  suggestions: ['下一餐可以补一份蔬菜'],
  photo_url: '/api/v1/upload/files/diet/12/breakfast.jpg?signature=signed',
};

const verifiedReceipt = {
  status: 'verified',
  resourceType: 'diet_record',
  resourceId: '705',
};

describe('buildDietSharePresentation', () => {
  it('builds approximate nutrition copy without confidence percentages', () => {
    const view = buildDietSharePresentation(photoRecord({
      calories: 900,
      protein: 36,
      carbs: 103,
      fat: 42,
      ai_confidence: 0.88,
    }));

    expect(view.macroLines).toEqual([
      '约 900 kcal · 蛋白质 36g',
      '碳水 103g · 脂肪 42g',
    ]);
    expect(JSON.stringify(view)).not.toContain('88%');
  });

  it('hides exact nutrition for a low-confidence photo record', () => {
    const view = buildDietSharePresentation(photoRecord({ ai_confidence: 0.42 }));

    expect(view.macroLines).toEqual(['营养待核对']);
    expect(JSON.stringify(view)).not.toContain('900');
  });

  it('does not leak exact nutrition from health tips on a low-confidence poster', () => {
    const view = buildDietSharePresentation(photoRecord({
      ai_confidence: 0.42,
      health_tips: '下一餐补蛋白质 30g，少吃 300 kcal',
    }));

    expect(view.nextAction).toBeUndefined();
    expect(JSON.stringify(view)).not.toMatch(/30g|300\s*kcal/i);
  });

  it('keeps user-corrected nutrition public even when stale AI confidence is low', () => {
    const view = buildDietSharePresentation(photoRecord({
      source: 'user_corrected',
      ai_confidence: 0.42,
    }));

    expect(view.macroLines).toContain('约 900 kcal · 蛋白质 36g');
    expect(view.disclosure).toBe('营养数据已由用户确认');
  });
});

describe('buildChatDietShareInput', () => {
  it.each([
    ['missing', Object.fromEntries(Object.entries(cardData).filter(([key]) => !['recorded', 'record_id'].includes(key)))],
    ['false', { ...cardData, recorded: false, record_id: undefined }],
  ])('accepts a live verified receipt when recorded is %s and record_id is absent', (_case, liveCard) => {
    const input = buildChatDietShareInput(liveCard, verifiedReceipt);

    expect(input).toMatchObject({
      available: true,
      record: {
        id: 705,
        meal_type: 'breakfast',
        food_items: '猪柳蛋麦满分 + 脆香油条 + 大杯豆乳',
      },
      photoUri: 'https://health.executor.life/api/v1/upload/files/diet/12/breakfast.jpg?signature=signed',
    });
    if (input.available) {
      expect(input.record).not.toHaveProperty('user_id');
      expect(input.record).not.toHaveProperty('record_date');
    }
  });

  it('accepts a restored persisted card without a receipt', () => {
    expect(buildChatDietShareInput(cardData, null)).toMatchObject({
      available: true,
      record: { id: 705, meal_type: 'breakfast' },
    });
  });

  it('rejects a dismissed receipt instead of treating it as live proof', () => {
    expect(buildChatDietShareInput(cardData, {
      ...verifiedReceipt,
      status: 'dismissed',
    })).toEqual({
      available: false,
      reason: 'unverified',
    });
  });

  it('rejects a card with neither live nor restored persistence proof', () => {
    const unprovedCard = Object.fromEntries(
      Object.entries(cardData).filter(([key]) => !['recorded', 'record_id'].includes(key)),
    );

    expect(buildChatDietShareInput(unprovedCard, null)).toEqual({
      available: false,
      reason: 'unverified',
    });
  });

  it('rejects a verified card without an accessible photo', () => {
    const { photo_url: _photoUrl, ...withoutPhoto } = cardData;

    expect(buildChatDietShareInput(withoutPhoto, verifiedReceipt)).toEqual({
      available: false,
      reason: 'photo_missing',
    });
  });

  it('rejects a restored card without a persisted record identity', () => {
    const { record_id: _recordId, ...withoutRecordId } = cardData;
    expect(buildChatDietShareInput(withoutRecordId, null)).toEqual({
      available: false,
      reason: 'record_missing',
    });
    expect(buildChatDietShareInput(cardData, {
      ...verifiedReceipt,
      resourceId: '',
    })).toEqual({
      available: false,
      reason: 'record_missing',
    });
  });

  it('rejects a card whose persisted identity differs from the receipt', () => {
    expect(buildChatDietShareInput({ ...cardData, record_id: 706 }, verifiedReceipt)).toEqual({
      available: false,
      reason: 'record_missing',
    });
  });

  it.each(['invalid', ''])(
    'rejects an invalid card identity instead of ignoring it beside a live receipt: %j',
    (recordId) => {
      expect(buildChatDietShareInput({ ...cardData, record_id: recordId }, verifiedReceipt)).toEqual({
        available: false,
        reason: 'record_missing',
      });
    },
  );

  it.each([
    ['food_items', { ...cardData, food_items: '   ' }],
    ['meal_type', { ...cardData, meal_type: 'brunch' }],
  ])('rejects a persisted projection with invalid %s', (_field, candidate) => {
    expect(buildChatDietShareInput(candidate, verifiedReceipt)).toEqual({
      available: false,
      reason: 'record_missing',
    });
  });
});

describe('normalizePrivateDietPhotoUri', () => {
  it('normalizes a protected relative path to the API origin', () => {
    expect(normalizePrivateDietPhotoUri('/api/v1/upload/files/diet/12/meal.jpg?signature=signed'))
      .toBe('https://health.executor.life/api/v1/upload/files/diet/12/meal.jpg?signature=signed');
  });

  it('preserves a same-origin HTTPS photo URL', () => {
    const uri = 'https://health.executor.life/api/v1/upload/files/diet/12/meal.jpg?signature=signed';
    expect(normalizePrivateDietPhotoUri(uri)).toBe(uri);
  });

  it.each([
    'https://evil.example/api/v1/upload/files/diet/12/meal.jpg',
    'http://health.executor.life/api/v1/upload/files/diet/12/meal.jpg',
    'https://user:secret@health.executor.life/api/v1/upload/files/diet/12/meal.jpg',
    'file:///private/meal.jpg',
  ])('rejects an untrusted absolute photo URL: %s', (uri) => {
    expect(normalizePrivateDietPhotoUri(uri)).toBeUndefined();
  });
});
