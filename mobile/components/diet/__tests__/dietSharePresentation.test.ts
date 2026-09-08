import type { DietRecord } from '../../../services/diet';
import {
  buildChatDietShareInput,
  buildDietShareDateLabel,
  buildDietSharePresentation,
  normalizePrivateDietPhotoUri,
} from '../dietSharePresentation';

describe('buildDietShareDateLabel', () => {
  it('formats a persisted record date without claiming it is today', () => {
    expect(buildDietShareDateLabel('2026-08-01')).toBe('2026.08.01');
  });

  it.each([undefined, null, '', 'today', '2026-99-99'])(
    'uses a neutral label for missing or invalid dates: %p',
    (value) => expect(buildDietShareDateLabel(value)).toBe('餐食记录'),
  );
});

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
      '约 900 kcal · 蛋白质约 36g',
      '碳水约 103g · 脂肪约 42g',
    ]);
    expect(view.nutritionItems).toEqual([
      { key: 'calories', label: '热量', value: '900', unit: 'kcal', qualifier: '约' },
      { key: 'protein', label: '蛋白质', value: '36', unit: 'g', qualifier: '约' },
      { key: 'carbs', label: '碳水', value: '103', unit: 'g', qualifier: '约' },
      { key: 'fat', label: '脂肪', value: '42', unit: 'g', qualifier: '约' },
    ]);
    expect(JSON.stringify(view)).not.toContain('88%');
    expect(view.publicNote).toBe('食物与份量来自本次记录，营养数值为估算。');
  });

  it('hides exact nutrition for a low-confidence photo record', () => {
    const view = buildDietSharePresentation(photoRecord({ ai_confidence: 0.42 }));

    expect(view.macroLines).toEqual(['营养待核对']);
    expect(view.nutritionItems).toEqual([]);
    expect(JSON.stringify(view)).not.toContain('900');
  });

  it('does not leak exact nutrition from health tips on a low-confidence poster', () => {
    const view = buildDietSharePresentation(photoRecord({
      ai_confidence: 0.42,
      health_tips: '下一餐补蛋白质 30g，少吃 300 kcal',
    }));

    expect(view).not.toHaveProperty('nextAction');
    expect(JSON.stringify(view)).not.toMatch(/30g|300\s*kcal/i);
  });

  it('never exports private health tips into the public presentation', () => {
    const view = buildDietSharePresentation(photoRecord({
      health_tips: '胃溃疡恢复期，今晚停用某药并把体重降到 60kg',
    }));

    expect(view).not.toHaveProperty('nextAction');
    expect(JSON.stringify(view)).not.toMatch(/胃溃疡|某药|60kg/i);
  });

  it.each([null, undefined, Number.NaN, -1, 101])(
    'fails closed when photo confidence is missing or invalid: %p',
    (aiConfidence) => {
      const view = buildDietSharePresentation(photoRecord({ ai_confidence: aiConfidence }));

      expect(view.nutritionItems).toEqual([]);
      expect(view.tags).toEqual(['待核对']);
      expect(view.disclosure).toBe('营养待核对');
      expect(JSON.stringify(view)).not.toContain('900');
    },
  );

  it('keeps user-corrected nutrition public even when stale AI confidence is low', () => {
    const view = buildDietSharePresentation(photoRecord({
      source: 'user_corrected',
      ai_confidence: 0.42,
    }));

    expect(view.macroLines).toContain('900 kcal · 蛋白质36g');
    expect(view.macroLines.join(' ')).not.toContain('约');
    expect(view.nutritionItems[0]).toEqual(expect.objectContaining({ value: '900', qualifier: null }));
    expect(view.disclosure).toBe('营养数据已由用户确认');
  });

  it('marks incomplete photo nutrition as a partial estimate', () => {
    const view = buildDietSharePresentation(photoRecord({ protein: null, carbs: null, fat: null }));

    expect(view.nutritionItems).toEqual([
      { key: 'calories', label: '热量', value: '900', unit: 'kcal', qualifier: '约' },
    ]);
    expect(view.disclosure).toBe('营养为部分估算');
    expect(view.publicNote).toContain('部分营养估算');
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

  it('carries only a valid persisted date into the public record projection', () => {
    const dated = buildChatDietShareInput({ ...cardData, record_date: '2026-08-01' }, verifiedReceipt);
    const invalid = buildChatDietShareInput({ ...cardData, record_date: '2026-99-99' }, verifiedReceipt);

    expect(dated).toMatchObject({ available: true, record: { record_date: '2026-08-01' } });
    if (invalid.available) expect(invalid.record).not.toHaveProperty('record_date');
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
