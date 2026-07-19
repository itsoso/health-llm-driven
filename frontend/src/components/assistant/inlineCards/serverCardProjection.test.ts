import { describe, expect, it } from 'vitest';

import { projectServerCards } from './serverCardProjection';

describe('projectServerCards', () => {
  it('preserves every valid server card in one renderable group', () => {
    const projected = projectServerCards([
      { type: 'aigc_media_job', data: { kind: 'text_to_image', title: '早餐海报' } },
      {
        type: 'diet_draft',
        data: { meal_type: 'breakfast', food_items: '鸡蛋', recorded: true },
      },
    ]);

    expect(projected).toEqual({
      type: 'cards_group',
      data: {
        cards: [
          { type: 'aigc_media_job', data: { kind: 'text_to_image', title: '早餐海报' } },
          {
            type: 'diet_draft',
            data: { meal_type: 'breakfast', food_items: '鸡蛋', recorded: true },
          },
        ],
      },
    });
  });

  it('keeps the single-card wire shape stable', () => {
    expect(projectServerCards([
      { type: 'diet_draft', data: { meal_type: 'lunch', food_items: '鸡胸肉' } },
    ])).toEqual({ type: 'diet_draft', data: { meal_type: 'lunch', food_items: '鸡胸肉' } });
  });
});
