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
});
