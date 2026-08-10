/* eslint-disable import/first */

const mockApiPost = jest.fn();
const mockApiPatch = jest.fn();
const mockApiPut = jest.fn();
const mockConfirmWriteIntent = jest.fn();
const mockDismissWriteIntent = jest.fn();

jest.mock('../api', () => ({
  __esModule: true,
  default: {
    post: (...args: any[]) => mockApiPost(...args),
    patch: (...args: any[]) => mockApiPatch(...args),
    put: (...args: any[]) => mockApiPut(...args),
  },
}));

jest.mock('../writeIntents', () => ({
  confirmWriteIntent: (...args: any[]) => mockConfirmWriteIntent(...args),
  dismissWriteIntent: (...args: any[]) => mockDismissWriteIntent(...args),
}));

import { dispatchChatCardAction } from '../chatCardActions';

const AGENDA_WRITE_POLICY = {
  capability_id: 'runtime_agenda.v1',
  required_receipt: true,
  autonomy_tier: 'manual_confirm',
  policy_reason: 'manual_confirm_write',
};
const DIET_WRITE_POLICY = {
  capability_id: 'diet_draft.v1',
  required_receipt: true,
  autonomy_tier: 'manual_confirm',
  policy_reason: 'manual_confirm_write',
};
const WRITE_INTENT_POLICY = {
  capability_id: 'write_intent.v1',
  required_receipt: true,
  autonomy_tier: 'manual_confirm',
  policy_reason: 'manual_confirm_write',
};
const MEDICATION_WRITE_POLICY = {
  ...WRITE_INTENT_POLICY,
  capability_id: 'medication_draft.v1',
};
const AIGC_WRITE_POLICY = {
  capability_id: 'aigc_media_confirmation.v1',
  required_receipt: true,
  autonomy_tier: 'manual_confirm',
  policy_reason: 'manual_confirm_write',
};
const MEDICATION_CARD_CONTEXT = {
  cardType: 'medication_draft',
  cardData: {
    write_intent_id: 42,
    items: [
      { medication_name: '伊托必利', actual_dosage: '1粒' },
      { medication_name: '替普瑞酮', actual_dosage: '1粒' },
    ],
  },
};

describe('dispatchChatCardAction', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockApiPost.mockResolvedValue({ data: { event_id: 71, agenda_status: 'completed' } });
    mockApiPut.mockResolvedValue({ data: { ok: true } });
    mockApiPatch.mockResolvedValue({ data: { id: 42, status: 'completed' } });
    mockConfirmWriteIntent.mockResolvedValue({ id: 42, status: 'executed', executed_ref: 'smart_reminder:18' });
    mockDismissWriteIntent.mockResolvedValue({ status: 'dismissed' });
  });

  it('completes agenda actions only through the allowed manual-confirm endpoint', async () => {
    await expect(dispatchChatCardAction({
      label: '完成',
      action: 'agenda.complete',
      endpoint: '/agenda/complete',
      requires_manual_confirm: true,
      ...AGENDA_WRITE_POLICY,
      payload: {
        source: { object_type: 'health_protocol', object_id: 7 },
      },
    })).resolves.toEqual(expect.objectContaining({
      status: 'completed',
      receipt: expect.objectContaining({
        status: 'verified',
        resourceType: 'agenda_event',
        resourceId: '71',
        verified: true,
      }),
    }));

    expect(mockApiPost).toHaveBeenCalledWith('/agenda/complete', {
      object_type: 'health_protocol',
      object_id: 7,
      status: 'done',
      track: 'protocol',
      value: null,
    });
  });

  it('rejects write actions that are not explicitly manual-confirmed', async () => {
    await expect(dispatchChatCardAction({
      label: '完成',
      action: 'agenda.complete',
      endpoint: '/agenda/complete',
      payload: {
        source: { object_type: 'health_protocol', object_id: 7 },
      },
    })).rejects.toThrow('manual_confirm_required');

    expect(mockApiPost).not.toHaveBeenCalled();
  });

  it('rejects manual-confirmed writes without a registered capability policy', async () => {
    await expect(dispatchChatCardAction({
      label: '完成',
      action: 'agenda.complete',
      endpoint: '/agenda/complete',
      requires_manual_confirm: true,
      payload: {
        source: { object_type: 'health_protocol', object_id: 7 },
      },
    })).rejects.toThrow('registered_write_policy_required');

    expect(mockApiPost).not.toHaveBeenCalled();
  });

  it('rejects arbitrary endpoints instead of forwarding model-chosen writes', async () => {
    await expect(dispatchChatCardAction({
      label: '危险写入',
      action: 'agenda.complete',
      endpoint: '/medications/7/dose',
      requires_manual_confirm: true,
      ...AGENDA_WRITE_POLICY,
      payload: {
        source: { object_type: 'health_protocol', object_id: 7 },
      },
    })).rejects.toThrow('unsupported_card_action_endpoint');

    expect(mockApiPost).not.toHaveBeenCalled();
  });

  it('completes daily plan actions through their validated event endpoint', async () => {
    mockApiPost.mockResolvedValueOnce({
      data: { id: 88, action_id: 'intervention.card.42', event_type: 'completed' },
    });

    await expect(dispatchChatCardAction({
      label: '完成这一步',
      action: 'daily_plan_action.complete',
      endpoint: '/daily-plan/actions/intervention.card.42/events',
      requires_manual_confirm: true,
      ...AGENDA_WRITE_POLICY,
      payload: { action_id: 'intervention.card.42', event_type: 'completed' },
    })).resolves.toEqual(expect.objectContaining({
      status: 'completed',
      receipt: expect.objectContaining({
        resourceType: 'intervention_event',
        resourceId: '88',
        verified: true,
      }),
    }));

    expect(mockApiPost).toHaveBeenCalledWith(
      '/daily-plan/actions/intervention.card.42/events',
      { event_type: 'completed', payload: { source: 'chat_card' } },
    );
  });

  it('rejects a mismatched daily plan action endpoint', async () => {
    await expect(dispatchChatCardAction({
      label: '完成这一步',
      action: 'daily_plan_action.complete',
      endpoint: '/daily-plan/actions/other.action/events',
      requires_manual_confirm: true,
      ...AGENDA_WRITE_POLICY,
      payload: { action_id: 'intervention.card.42', event_type: 'completed' },
    })).rejects.toThrow('unsupported_card_action_endpoint');

    expect(mockApiPost).not.toHaveBeenCalled();
  });

  it('confirms write-intent actions by id', async () => {
    await expect(dispatchChatCardAction({
      label: '确认写入',
      action: 'write_intent.confirm',
      endpoint: '/write-intents/42/confirm',
      requires_manual_confirm: true,
      ...WRITE_INTENT_POLICY,
      payload: { write_intent_id: 42 },
    })).resolves.toEqual(expect.objectContaining({
      status: 'completed',
      receipt: expect.objectContaining({
        executedRef: 'smart_reminder:18',
        resourceType: 'smart_reminder',
        resourceId: '18',
        verified: true,
      }),
    }));

    expect(mockConfirmWriteIntent).toHaveBeenCalledWith(42);
  });

  it('uses the persisted WriteIntent as the receipt when execution is acknowledged without a downstream ref', async () => {
    mockConfirmWriteIntent.mockResolvedValueOnce({
      id: 42,
      status: 'executed',
      executed_ref: 'acknowledged',
    });

    await expect(dispatchChatCardAction({
      label: '确认写入',
      action: 'write_intent.confirm',
      endpoint: '/write-intents/42/confirm',
      requires_manual_confirm: true,
      ...WRITE_INTENT_POLICY,
      payload: { write_intent_id: 42 },
    })).resolves.toEqual(expect.objectContaining({
      status: 'completed',
      receipt: expect.objectContaining({
        executedRef: 'acknowledged',
        resourceType: 'write_intent',
        resourceId: '42',
        verified: true,
      }),
    }));
  });

  it('preserves every verified medication receipt and safety alert returned by the server', async () => {
    mockConfirmWriteIntent.mockResolvedValueOnce({
      id: 42,
      status: 'executed',
      executed_ref: 'medication_logs:101,102',
      write_receipts: [
        {
          operation_id: 'write_intent:medication_intake_batch:42:101',
          status: 'verified',
          resource_type: 'medication_log',
          resource_id: '101',
          completed_at: '2026-07-21T21:15:01-04:00',
          verified: true,
        },
        {
          operation_id: 'write_intent:medication_intake_batch:42:102',
          status: 'verified',
          resource_type: 'medication_log',
          resource_id: '102',
          completed_at: '2026-07-21T21:15:02-04:00',
          verified: true,
        },
      ],
      safety_alerts: [{
        rule_id: 'medication.safety_precheck_incomplete',
        category: 'medication',
        severity: { value: 3, label: 'high', label_zh: '警告' },
        title: '自动安全筛查暂未完成',
        message: '这不代表当前用药组合安全。',
        action: '如有明显不适，请及时就医。',
      }],
    });

    const result = await dispatchChatCardAction({
      label: '确认记录',
      action: 'write_intent.confirm',
      endpoint: '/write-intents/42/confirm',
      requires_manual_confirm: true,
      ...MEDICATION_WRITE_POLICY,
      payload: { write_intent_id: 42 },
    }, undefined, MEDICATION_CARD_CONTEXT);

    expect(result.write_receipts).toEqual([
      expect.objectContaining({ resourceType: 'medication_log', resourceId: '101' }),
      expect.objectContaining({ resourceType: 'medication_log', resourceId: '102' }),
    ]);
    expect(result.receipt).toEqual(expect.objectContaining({
      operationId: 'write_intent:medication_intake_batch:42:102',
      resourceId: '102',
    }));
    expect(result.safety_alerts).toEqual([
      expect.objectContaining({
        rule_id: 'medication.safety_precheck_incomplete',
        message: '这不代表当前用药组合安全。',
      }),
    ]);
  });

  it('fails closed instead of inventing one receipt for a medication batch', async () => {
    mockConfirmWriteIntent.mockResolvedValueOnce({
      id: 42,
      status: 'executed',
      executed_ref: 'medication_logs:101,102',
      write_receipts: [],
      safety_alerts: [],
    });

    await expect(dispatchChatCardAction({
      label: '确认记录',
      action: 'write_intent.confirm',
      endpoint: '/write-intents/42/confirm',
      requires_manual_confirm: true,
      ...MEDICATION_WRITE_POLICY,
      payload: { write_intent_id: 42 },
    }, undefined, MEDICATION_CARD_CONTEXT)).rejects.toThrow('medication_batch_write_receipts_missing');
  });

  it('rejects incomplete or non-medication receipts for the frozen item count', async () => {
    mockConfirmWriteIntent.mockResolvedValue({
      id: 42,
      status: 'executed',
      executed_ref: 'medication_logs:101,102',
      write_receipts: [
        {
          operation_id: 'write_intent:medication_intake_batch:42:101',
          status: 'verified',
          resource_type: 'health_record',
          resource_id: '101',
          completed_at: '2026-07-21T21:15:01-04:00',
          verified: true,
        },
        {
          operation_id: 'write_intent:medication_intake_batch:42:102',
          status: 'verified',
          resource_type: 'health_record',
          resource_id: '102',
          completed_at: '2026-07-21T21:15:02-04:00',
          verified: true,
        },
      ],
    });

    await expect(dispatchChatCardAction({
      label: '确认记录',
      action: 'write_intent.confirm',
      endpoint: '/write-intents/42/confirm',
      requires_manual_confirm: true,
      ...MEDICATION_WRITE_POLICY,
      payload: { write_intent_id: 42 },
    }, undefined, MEDICATION_CARD_CONTEXT)).rejects.toThrow(
      'medication_batch_write_receipts_invalid',
    );
  });

  it('maps the server 409 expiry response to a terminal expired result', async () => {
    mockConfirmWriteIntent.mockRejectedValueOnce({
      response: {
        status: 409,
        data: { detail: '确认计划已过期，请重新提交记录' },
      },
    });

    await expect(dispatchChatCardAction({
      label: '确认记录',
      action: 'write_intent.confirm',
      endpoint: '/write-intents/42/confirm',
      requires_manual_confirm: true,
      ...MEDICATION_WRITE_POLICY,
      payload: { write_intent_id: 42 },
    }, undefined, MEDICATION_CARD_CONTEXT)).resolves.toEqual({
      status: 'expired',
      decision_status: 'expired',
    });
  });

  it('keeps an expired plan expired when an idempotent retry returns dismissed storage status', async () => {
    mockConfirmWriteIntent.mockResolvedValueOnce({
      id: 42,
      status: 'dismissed',
      decision_status: 'expired',
    });

    await expect(dispatchChatCardAction({
      label: '确认记录',
      action: 'write_intent.confirm',
      endpoint: '/write-intents/42/confirm',
      requires_manual_confirm: true,
      ...MEDICATION_WRITE_POLICY,
      payload: { write_intent_id: 42 },
    }, undefined, MEDICATION_CARD_CONTEXT)).resolves.toEqual({
      status: 'expired',
      decision_status: 'expired',
    });
  });

  it('reconciles a confirm request when dismissal already won the terminal race', async () => {
    mockConfirmWriteIntent.mockResolvedValueOnce({
      id: 42,
      status: 'dismissed',
      decision_status: 'dismissed',
    });

    await expect(dispatchChatCardAction({
      label: '确认记录',
      action: 'write_intent.confirm',
      endpoint: '/write-intents/42/confirm',
      requires_manual_confirm: true,
      ...MEDICATION_WRITE_POLICY,
      payload: { write_intent_id: 42 },
    }, undefined, MEDICATION_CARD_CONTEXT)).resolves.toEqual({
      status: 'dismissed',
      decision_status: 'dismissed',
    });
  });

  it('reconciles a dismiss request when confirmation already wrote the frozen batch', async () => {
    mockDismissWriteIntent.mockResolvedValueOnce({
      id: 42,
      status: 'executed',
      decision_status: 'executed',
      executed_ref: 'medication_logs:101,102',
      write_receipts: [
        {
          operation_id: 'write_intent:medication_intake_batch:42:101',
          status: 'verified',
          resource_type: 'medication_log',
          resource_id: '101',
          completed_at: '2026-07-21T21:15:01-04:00',
          verified: true,
        },
        {
          operation_id: 'write_intent:medication_intake_batch:42:102',
          status: 'verified',
          resource_type: 'medication_log',
          resource_id: '102',
          completed_at: '2026-07-21T21:15:02-04:00',
          verified: true,
        },
      ],
      safety_alerts: [],
    });

    await expect(dispatchChatCardAction({
      label: '取消',
      action: 'write_intent.dismiss',
      endpoint: '/write-intents/42/dismiss',
      requires_manual_confirm: true,
      ...MEDICATION_WRITE_POLICY,
      payload: { write_intent_id: 42 },
    }, undefined, MEDICATION_CARD_CONTEXT)).resolves.toEqual(expect.objectContaining({
      status: 'completed',
      decision_status: 'executed',
      write_receipts: [
        expect.objectContaining({ resourceType: 'medication_log', resourceId: '101' }),
        expect.objectContaining({ resourceType: 'medication_log', resourceId: '102' }),
      ],
    }));
  });

  it('rejects medication actions whose trusted card contract does not match the action', async () => {
    const baseAction = {
      label: '确认记录',
      action: 'write_intent.confirm' as const,
      endpoint: '/write-intents/42/confirm',
      requires_manual_confirm: true,
      ...MEDICATION_WRITE_POLICY,
      payload: { write_intent_id: 42 },
    };

    await expect(dispatchChatCardAction(
      { ...baseAction, capability_id: 'anything.v99' },
      undefined,
      MEDICATION_CARD_CONTEXT,
    )).rejects.toThrow('invalid_medication_batch_action');
    await expect(dispatchChatCardAction(
      { ...baseAction, endpoint: '/write-intents/43/confirm' },
      undefined,
      MEDICATION_CARD_CONTEXT,
    )).rejects.toThrow('unsupported_card_action_endpoint');
    await expect(dispatchChatCardAction(
      { ...baseAction, payload: { id: 42 } as any },
      undefined,
      MEDICATION_CARD_CONTEXT,
    )).rejects.toThrow('invalid_card_action_id');
    expect(mockConfirmWriteIntent).not.toHaveBeenCalled();
  });

  it('treats medication dismissal as a receiptless decision', async () => {
    mockDismissWriteIntent.mockResolvedValueOnce({
      id: 42,
      status: 'dismissed',
      decision_status: 'dismissed',
    });

    await expect(dispatchChatCardAction({
      label: '取消',
      action: 'write_intent.dismiss',
      endpoint: '/write-intents/42/dismiss',
      requires_manual_confirm: true,
      ...MEDICATION_WRITE_POLICY,
      payload: { write_intent_id: 42 },
    }, undefined, MEDICATION_CARD_CONTEXT)).resolves.toEqual({
      status: 'dismissed',
      decision_status: 'dismissed',
    });
  });

  it('opens only app-local route actions', async () => {
    await expect(dispatchChatCardAction({
      label: '打开小巴',
      action: 'route.open',
      payload: { route: '/(tabs)/chat?prompt=hrv' },
    })).resolves.toEqual({
      status: 'opened',
      route: '/(tabs)/chat?prompt=hrv',
    });
  });

  it('returns inline UI patches without opening a route', async () => {
    await expect(dispatchChatCardAction({
      label: '看下一餐建议',
      action: 'ui.inline.expand',
      payload: {
        target: 'next_meal',
        patch: {
          expanded_sections: ['next_meal'],
          next_meal_detail: { title: '下一餐建议' },
        },
      },
    })).resolves.toEqual({
      status: 'completed',
      patch: {
        expanded_sections: ['next_meal'],
        next_meal_detail: { title: '下一餐建议' },
      },
    });

    expect(mockApiPost).not.toHaveBeenCalled();
  });

  it('rejects scheme-relative and control-character route actions', async () => {
    await expect(dispatchChatCardAction({
      label: '打开外部站点',
      action: 'route.open',
      payload: { route: '//example.test/path' },
    })).rejects.toThrow('invalid_route_action');

    await expect(dispatchChatCardAction({
      label: '打开异常路径',
      action: 'route.open',
      payload: { route: '/(tabs)/chat\ninject' },
    })).rejects.toThrow('invalid_route_action');
  });

  it('creates diet records only through the manual-confirm diet endpoint', async () => {
    mockApiPost.mockResolvedValueOnce({ data: { id: 77 } });

    await expect(dispatchChatCardAction({
      label: '确认记录',
      action: 'diet_record.create',
      endpoint: '/diet/records',
      requires_manual_confirm: true,
      ...DIET_WRITE_POLICY,
      payload: {
        record: {
          food_items: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
          meal_type: 'lunch',
          calories: 770,
          protein: 30,
          carbs: 70,
          fat: 17,
        },
      },
    }, 'diet-card-lunch-77')).resolves.toEqual(expect.objectContaining({
      status: 'completed',
      receipt: expect.objectContaining({
        resourceType: 'diet_record',
        resourceId: '77',
        verified: true,
      }),
    }));

    expect(mockApiPost).toHaveBeenCalledWith(
      '/diet/records',
      expect.objectContaining({
        food_items: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
        meal_type: 'lunch',
        calories: 770,
        protein: 30,
        carbs: 70,
        fat: 17,
        record_date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      }),
      { headers: { 'Idempotency-Key': 'diet-card-lunch-77' } },
    );
  });

  it('preserves an owner-bound photo draft when a food portion uses 片', async () => {
    const photoDraftToken = 'photo-draft-token-1234567890';
    const foodItems = '小米粥 约1碗 + 虾仁炒时蔬 约1小碗 + 煎蛋 1个 + 玉米 约1/4根 + 胡萝卜 约3片 + 南瓜 约2块';
    mockApiPost.mockResolvedValueOnce({ data: { id: 1074 } });

    await expect(dispatchChatCardAction({
      id: `confirm-contextual-diet:${photoDraftToken}`,
      label: '确认记录',
      action: 'diet_record.create',
      endpoint: '/diet/records',
      requires_manual_confirm: true,
      ...DIET_WRITE_POLICY,
      payload: {
        record: {
          record_date: '2026-08-10',
          meal_type: 'lunch',
          food_items: foodItems,
          calories: 610,
          protein: 31,
          carbs: 90,
          fat: 15,
          source: 'chat_photo',
          photo_draft_token: photoDraftToken,
        },
      },
    }, 'diet-photo-card-production-regression')).resolves.toEqual(expect.objectContaining({
      status: 'completed',
      receipt: expect.objectContaining({
        resourceType: 'diet_record',
        resourceId: '1074',
        verified: true,
      }),
    }));

    expect(mockApiPost).toHaveBeenCalledWith(
      '/diet/records',
      expect.objectContaining({
        food_items: foodItems,
        photo_draft_token: photoDraftToken,
      }),
      { headers: { 'Idempotency-Key': 'diet-photo-card-production-regression' } },
    );
  });

  it('preserves photo draft foods with 段 块 颗 portions before posting', async () => {
    const photoDraftToken = 'photo-draft-token-1234567890';
    const foodItems = '胡萝卜 约3段 · 南瓜 约2块 · 红枣 约3颗 · 玉米 约1小段';
    mockApiPost.mockResolvedValueOnce({ data: { id: 1075 } });

    await expect(dispatchChatCardAction({
      id: `confirm-contextual-diet:${photoDraftToken}`,
      label: '确认记录',
      action: 'diet_record.create',
      endpoint: '/diet/records',
      requires_manual_confirm: true,
      ...DIET_WRITE_POLICY,
      payload: {
        record: {
          record_date: '2026-08-10',
          meal_type: 'breakfast',
          food_items: foodItems,
          calories: 655,
          protein: 19,
          carbs: 135,
          source: 'chat_photo',
          photo_draft_token: photoDraftToken,
        },
      },
    }, 'diet-photo-card-breakfast-root-veg')).resolves.toEqual(expect.objectContaining({
      status: 'completed',
      receipt: expect.objectContaining({
        resourceType: 'diet_record',
        resourceId: '1075',
        verified: true,
      }),
    }));

    expect(mockApiPost).toHaveBeenCalledWith(
      '/diet/records',
      expect.objectContaining({
        food_items: foodItems,
        meal_type: 'breakfast',
        calories: 655,
        protein: 19,
        carbs: 135,
        photo_draft_token: photoDraftToken,
      }),
      { headers: { 'Idempotency-Key': 'diet-photo-card-breakfast-root-veg' } },
    );
  });

  it('rejects malformed photo draft tokens before posting', async () => {
    await expect(dispatchChatCardAction({
      label: '确认记录',
      action: 'diet_record.create',
      endpoint: '/diet/records',
      requires_manual_confirm: true,
      ...DIET_WRITE_POLICY,
      payload: {
        record: {
          meal_type: 'lunch',
          food_items: '胡萝卜 约3片',
          photo_draft_token: '../not-an-owner-token',
        },
      },
    })).rejects.toThrow('invalid_diet_photo_draft_token');

    expect(mockApiPost).not.toHaveBeenCalled();
  });

  it.each([
    ['阿司匹林 1片'],
    ['阿奇霉素 1片'],
    ['华法林 1片'],
    ['warfarin 1片'],
    ['warfarin1片'],
    ['aspirin 1片'],
    ['azithromycin1片'],
    ['维生素D 1片'],
    ['fish oil 2粒'],
    ['fish oil2粒'],
    ['omega-3 2粒'],
    ['magnesium2粒'],
    ['coq102粒'],
    ['b122粒'],
    ['d32粒'],
    ['胡萝卜 + coq102粒'],
    ['Ｄ３2粒'],
    ['ＣｏＱ１０2粒'],
    ['Ｂ１２2粒'],
    ['fish‑oil2粒'],
    ['fish–oil2粒'],
    ['fish​oil2粒'],
    ['d₃2粒'],
    ['coq₁₀2粒'],
    ['vitamin D 2粒'],
    ['vitamin D1000IU'],
    ['coq10200mg'],
    ['b121000mcg'],
    ['d31000IU'],
    ['fish oil1000mg'],
    ['magnesium500mg'],
    ['nac600mg'],
    ['vitaminDfishoil'],
    ['vitamindandfishoil'],
    ['d3-fish-oil'],
    ['胡萝卜 约3片 + warfarin 1片'],
  ])('rejects non-diet intake even with an owner-bound photo token: %s', async (foodItems) => {
    await expect(dispatchChatCardAction({
      label: '确认记录',
      action: 'diet_record.create',
      endpoint: '/diet/records',
      requires_manual_confirm: true,
      ...DIET_WRITE_POLICY,
      payload: {
        record: {
          meal_type: 'lunch',
          food_items: foodItems,
          photo_draft_token: 'photo-draft-token-1234567890',
        },
      },
    })).rejects.toThrow('invalid_diet_food_items_non_diet');

    expect(mockApiPost).not.toHaveBeenCalled();
  });

  it('normalizes structured food arrays before creating diet records', async () => {
    mockApiPost.mockResolvedValueOnce({ data: { id: 78 } });

    await dispatchChatCardAction({
      label: '确认记录',
      action: 'diet_record.create',
      endpoint: '/diet/records',
      requires_manual_confirm: true,
      ...DIET_WRITE_POLICY,
      payload: {
        record: {
          food_items: ['鸡胸肉 200g', '杂粮饭 100g', '西兰花'],
          meal_type: 'dinner',
          protein: 46,
        },
      },
    });

    expect(mockApiPost).toHaveBeenCalledWith('/diet/records', expect.objectContaining({
      food_items: '鸡胸肉 200g + 杂粮饭 100g + 西兰花',
      meal_type: 'dinner',
      protein: 46,
    }));
  });

  it('does not treat words containing nac as NAC supplement intake', async () => {
    mockApiPost.mockResolvedValueOnce({ data: { id: 79 } });

    await dispatchChatCardAction({
      label: '确认记录',
      action: 'diet_record.create',
      endpoint: '/diet/records',
      requires_manual_confirm: true,
      ...DIET_WRITE_POLICY,
      payload: {
        record: {
          food_items: '测试snack',
          meal_type: 'snack',
        },
      },
    });

    expect(mockApiPost).toHaveBeenCalledWith('/diet/records', expect.objectContaining({
      food_items: '测试snack',
      meal_type: 'snack',
    }));
  });

  it('fails diet card confirmation when the backend does not return a record id', async () => {
    mockApiPost.mockResolvedValueOnce({ data: { ok: true } });

    await expect(dispatchChatCardAction({
      label: '确认记录',
      action: 'diet_record.create',
      endpoint: '/diet/records',
      requires_manual_confirm: true,
      ...DIET_WRITE_POLICY,
      payload: {
        record: {
          food_items: '牛肉面',
          meal_type: 'lunch',
          calories: 620,
          protein: 28,
          carbs: 78,
          fat: 18,
        },
      },
    })).rejects.toThrow('diet_record_missing_id');
  });

  it('estimates and backfills nutrition after confirming a diet record without macros', async () => {
    mockApiPost
      .mockResolvedValueOnce({ data: { id: 88, food_items: '牛肉面', meal_type: 'lunch' } })
      .mockResolvedValueOnce({
        data: {
          success: true,
          total_calories: 620,
          total_protein: 28,
          total_carbs: 78,
          total_fat: 18,
        },
      });

    await expect(dispatchChatCardAction({
      label: '确认记录',
      action: 'diet_record.create',
      endpoint: '/diet/records',
      requires_manual_confirm: true,
      ...DIET_WRITE_POLICY,
      payload: {
        record: {
          food_items: '牛肉面',
          meal_type: 'lunch',
        },
      },
    })).resolves.toEqual(expect.objectContaining({
      status: 'completed',
      nutrition_status: 'estimated',
      receipt: expect.objectContaining({ resourceType: 'diet_record', resourceId: '88', verified: true }),
    }));

    expect(mockApiPost).toHaveBeenNthCalledWith(1, '/diet/records', expect.objectContaining({
      food_items: '牛肉面',
      meal_type: 'lunch',
    }));
    expect(mockApiPost).toHaveBeenNthCalledWith(2, '/diet/estimate-nutrition?food_description=%E7%89%9B%E8%82%89%E9%9D%A2');
    expect(mockApiPut).toHaveBeenCalledWith('/diet/records/88', {
      calories: 620,
      protein: 28,
      carbs: 78,
      fat: 18,
    });
  });

  it('returns an estimate failure status without rolling back a saved diet record', async () => {
    mockApiPost
      .mockResolvedValueOnce({ data: { id: 89 } })
      .mockRejectedValueOnce(new Error('estimate unavailable'));

    await expect(dispatchChatCardAction({
      label: '确认记录',
      action: 'diet_record.create',
      endpoint: '/diet/records',
      requires_manual_confirm: true,
      ...DIET_WRITE_POLICY,
      payload: {
        record: {
          food_items: '鸡蛋 2 个',
          meal_type: 'breakfast',
        },
      },
    })).resolves.toEqual(expect.objectContaining({
      status: 'completed',
      nutrition_status: 'estimate_failed',
      receipt: expect.objectContaining({ resourceType: 'diet_record', resourceId: '89', verified: true }),
    }));

    expect(mockApiPost).toHaveBeenNthCalledWith(1, '/diet/records', expect.objectContaining({
      food_items: '鸡蛋 2 个',
    }));
    expect(mockApiPut).not.toHaveBeenCalled();
  });

  it('rejects diet record actions with arbitrary endpoints', async () => {
    await expect(dispatchChatCardAction({
      label: '危险饮食写入',
      action: 'diet_record.create',
      endpoint: '/medications/7/dose',
      requires_manual_confirm: true,
      ...DIET_WRITE_POLICY,
      payload: {
        record: {
          food_items: '鸡蛋 2 个',
          meal_type: 'breakfast',
        },
      },
    })).rejects.toThrow('unsupported_card_action_endpoint');

    expect(mockApiPost).not.toHaveBeenCalled();
  });

  it.each([
    ['我刚才不小心删除了', 'invalid_diet_food_items_management'],
    ['替普瑞酮胶囊（施维舒）', 'invalid_diet_food_items_non_diet'],
    ['鱼油', 'invalid_diet_food_items_non_diet'],
    ['晨跑 30 分钟', 'invalid_diet_food_items_health_metric'],
    ['体重 73.1kg 腰围 84cm', 'invalid_diet_food_items_health_metric'],
    ['昨晚睡了 6 小时', 'invalid_diet_food_items_health_metric'],
  ])('rejects non-food diet card payloads before posting: %s', async (foodItems, errorCode) => {
    await expect(dispatchChatCardAction({
      label: '确认记录',
      action: 'diet_record.create',
      endpoint: '/diet/records',
      requires_manual_confirm: true,
      ...DIET_WRITE_POLICY,
      payload: {
        record: {
          food_items: foodItems,
          meal_type: 'dinner',
        },
      },
    })).rejects.toThrow(errorCode);

    expect(mockApiPost).not.toHaveBeenCalled();
  });

  it('rejects generic AIGC confirmation dispatch without runtime prompt review', async () => {
    await expect(dispatchChatCardAction({
      id: 'aigc_media.confirm:aigc_confirm_owner_review',
      label: '确认并生成',
      action: 'aigc_media.confirm',
      endpoint: '/aigc/media/confirmations/aigc_confirm_owner_review/confirm',
      requires_manual_confirm: true,
      ...AIGC_WRITE_POLICY,
    })).rejects.toThrow('aigc_media_confirmation_requires_inline_review');

    expect(mockApiPost).not.toHaveBeenCalled();
  });
});
