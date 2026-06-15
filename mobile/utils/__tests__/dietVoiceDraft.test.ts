import { voiceDraftToDietDefaults } from '../dietVoiceDraft';

describe('voiceDraftToDietDefaults', () => {
  it('turns a voice draft into confirmable diet form defaults', () => {
    const defaults = voiceDraftToDietDefaults({
      raw_text: '晚饭吃了鸡胸肉和米饭',
      meal_type: 'dinner',
      meal_type_label: '晚餐',
      foods: [
        { name: '鸡胸肉', quantity: 120, unit: 'g', calories: 198, protein: 37 },
        { name: '米饭', quantity: 1, unit: '碗', calories: 230, carbs: 52 },
      ],
      risk_tags: [],
      confidence: 0.86,
      needs_confirmation: false,
      clarifying_question: null,
      parser_version: 'voice-1.0',
    }, '2026-06-15');

    expect(defaults).toMatchObject({
      record_date: '2026-06-15',
      meal_type: 'dinner',
      food_items: '鸡胸肉 120g、米饭 1碗',
      calories: 428,
      protein: 37,
      carbs: 52,
    });
  });

  it('keeps a single clarification note for risky low-confidence drafts', () => {
    const defaults = voiceDraftToDietDefaults({
      raw_text: '喝了一杯奶茶',
      meal_type: 'snack',
      meal_type_label: '加餐',
      foods: [{ name: '奶茶', quantity: null, unit: null }],
      risk_tags: ['sweet_drink'],
      confidence: 0.42,
      needs_confirmation: true,
      clarifying_question: '「奶茶」大概多少量?',
      parser_version: 'voice-1.0',
    }, '2026-06-15');

    expect(defaults.food_items).toBe('奶茶');
    expect(defaults.notes).toContain('需确认');
    expect(defaults.notes).toContain('甜饮');
    expect(defaults.notes).toContain('「奶茶」大概多少量?');
  });
});
