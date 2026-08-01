import type { DietRecord } from '../../../services/diet';
import {
  buildChatDietShareInput,
  buildDietSharePresentation,
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
  record_date: '2026-08-01',
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
});

describe('buildChatDietShareInput', () => {
  it('adapts only a verified recorded chat card with a photo', () => {
    const input = buildChatDietShareInput(cardData, verifiedReceipt);

    expect(input).toMatchObject({
      available: true,
      record: {
        id: 705,
        record_date: '2026-08-01',
        meal_type: 'breakfast',
        food_items: '猪柳蛋麦满分 + 脆香油条 + 大杯豆乳',
      },
      photoUri: 'https://health.executor.life/api/v1/upload/files/diet/12/breakfast.jpg?signature=signed',
    });
    if (input.available) expect(input.record).not.toHaveProperty('user_id');
  });

  it('rejects a card without a verified diet receipt', () => {
    expect(buildChatDietShareInput(cardData, null)).toEqual({
      available: false,
      reason: 'unverified',
    });
    expect(buildChatDietShareInput(cardData, {
      ...verifiedReceipt,
      status: 'dismissed',
    })).toEqual({
      available: false,
      reason: 'unverified',
    });
  });

  it.each([
    ['false', { ...cardData, recorded: false }],
    ['missing', Object.fromEntries(Object.entries(cardData).filter(([key]) => key !== 'recorded'))],
  ])('rejects a card when recorded is %s', (_case, candidate) => {
    expect(buildChatDietShareInput(candidate, verifiedReceipt)).toEqual({
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

  it('rejects a verified photo card without a persisted record identity', () => {
    const { record_id: _recordId, ...withoutRecordId } = cardData;
    expect(buildChatDietShareInput(withoutRecordId, verifiedReceipt)).toEqual({
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

  it.each([
    ['record_date', { ...cardData, record_date: '' }],
    ['food_items', { ...cardData, food_items: '   ' }],
    ['meal_type', { ...cardData, meal_type: 'brunch' }],
  ])('rejects a persisted projection with invalid %s', (_field, candidate) => {
    expect(buildChatDietShareInput(candidate, verifiedReceipt)).toEqual({
      available: false,
      reason: 'record_missing',
    });
  });
});
