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

  it('restores medication terminal receipts and every safety alert from assistant meta', () => {
    const receipts = [
      { operation_id: 'receipt-1', resource_id: '101', verified: true },
      { operation_id: 'receipt-2', resource_id: '102', verified: true },
    ];
    const alerts = [
      { rule_id: 'ddi.1', title: '提示一', message: '消息一' },
      { rule_id: 'ddi.2', title: '提示二', message: '消息二' },
    ];
    const projected = projectServerCards([
      {
        type: 'medication_draft',
        data: { items: [{ medication_name: '伊托必利', actual_dosage: '1粒' }] },
        actions: [{
          label: '确认记录',
          action: 'write_intent.confirm',
          endpoint: '/write-intents/42/confirm',
          payload: { write_intent_id: 42 },
          requires_manual_confirm: true,
          capability_id: 'medication_draft.v1',
          required_receipt: true,
          autonomy_tier: 'manual_confirm',
          policy_reason: 'manual_confirm_write',
        }],
      },
    ], {
      medication_batch_decision: { intent_id: 42, status: 'executed' },
      write_receipts: receipts,
      safety_alerts: alerts,
    });

    expect(projected).toEqual({
      type: 'medication_draft',
      data: expect.objectContaining({
        decision_status: 'executed',
        write_receipts: receipts,
        safety_alerts: alerts,
      }),
    });
  });

  it('prefers exact batch-scoped terminal evidence over unrelated same-turn projections', () => {
    const medicationReceipt = {
      operation_id: 'write_intent:medication_intake_batch:42:101',
      resource_type: 'medication_log',
      resource_id: '101',
      verified: true,
    };
    const unrelatedReceipt = {
      operation_id: 'health_record:diet_record:701',
      resource_type: 'diet_record',
      resource_id: '701',
      verified: true,
    };
    const medicationAlert = { rule_id: 'ddi.medication', title: '用药提示', message: '用药消息' };
    const unrelatedAlert = { rule_id: 'diet.unrelated', title: '饮食提示', message: '饮食消息' };

    const projected = projectServerCards([
      {
        type: 'medication_draft',
        data: { items: [{ medication_name: '伊托必利', actual_dosage: '1粒' }] },
        actions: [{
          label: '确认记录',
          action: 'write_intent.confirm',
          payload: { write_intent_id: 42 },
        }],
      },
    ], {
      medication_batch_decision: {
        intent_id: 42,
        status: 'executed',
        write_receipts: [medicationReceipt],
        safety_alerts: [medicationAlert],
      },
      write_receipts: [unrelatedReceipt, medicationReceipt],
      safety_alerts: [unrelatedAlert, medicationAlert],
    });

    expect(projected).toEqual({
      type: 'medication_draft',
      data: expect.objectContaining({
        decision_status: 'executed',
        write_receipts: [medicationReceipt],
        safety_alerts: [medicationAlert],
      }),
    });
  });
});
