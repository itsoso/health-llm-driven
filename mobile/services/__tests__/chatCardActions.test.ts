/* eslint-disable import/first */

const mockApiPost = jest.fn();
const mockApiPut = jest.fn();
const mockConfirmWriteIntent = jest.fn();
const mockDismissWriteIntent = jest.fn();

jest.mock('../api', () => ({
  __esModule: true,
  default: {
    post: (...args: any[]) => mockApiPost(...args),
    put: (...args: any[]) => mockApiPut(...args),
  },
}));

jest.mock('../writeIntents', () => ({
  confirmWriteIntent: (...args: any[]) => mockConfirmWriteIntent(...args),
  dismissWriteIntent: (...args: any[]) => mockDismissWriteIntent(...args),
}));

import { dispatchChatCardAction } from '../chatCardActions';

describe('dispatchChatCardAction', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockApiPost.mockResolvedValue({ data: { ok: true } });
    mockApiPut.mockResolvedValue({ data: { ok: true } });
    mockConfirmWriteIntent.mockResolvedValue({ status: 'executed' });
    mockDismissWriteIntent.mockResolvedValue({ status: 'dismissed' });
  });

  it('completes agenda actions only through the allowed manual-confirm endpoint', async () => {
    await dispatchChatCardAction({
      label: '完成',
      action: 'agenda.complete',
      endpoint: '/agenda/complete',
      requires_manual_confirm: true,
      payload: {
        source: { object_type: 'health_protocol', object_id: 7 },
      },
    });

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

  it('rejects arbitrary endpoints instead of forwarding model-chosen writes', async () => {
    await expect(dispatchChatCardAction({
      label: '危险写入',
      action: 'agenda.complete',
      endpoint: '/medications/7/dose',
      requires_manual_confirm: true,
      payload: {
        source: { object_type: 'health_protocol', object_id: 7 },
      },
    })).rejects.toThrow('unsupported_card_action_endpoint');

    expect(mockApiPost).not.toHaveBeenCalled();
  });

  it('confirms write-intent actions by id', async () => {
    await dispatchChatCardAction({
      label: '确认写入',
      action: 'write_intent.confirm',
      endpoint: '/write-intents/42/confirm',
      requires_manual_confirm: true,
      payload: { write_intent_id: 42 },
    });

    expect(mockConfirmWriteIntent).toHaveBeenCalledWith(42);
  });

  it('opens only app-local route actions', async () => {
    await expect(dispatchChatCardAction({
      label: '打开阿衡',
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
    await dispatchChatCardAction({
      label: '确认记录',
      action: 'diet_record.create',
      endpoint: '/diet/records',
      requires_manual_confirm: true,
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
    });

    expect(mockApiPost).toHaveBeenCalledWith('/diet/records', expect.objectContaining({
      food_items: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
      meal_type: 'lunch',
      calories: 770,
      protein: 30,
      carbs: 70,
      fat: 17,
      record_date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
    }));
  });

  it('normalizes structured food arrays before creating diet records', async () => {
    await dispatchChatCardAction({
      label: '确认记录',
      action: 'diet_record.create',
      endpoint: '/diet/records',
      requires_manual_confirm: true,
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
      payload: {
        record: {
          food_items: '牛肉面',
          meal_type: 'lunch',
        },
      },
    })).resolves.toEqual({ status: 'completed', nutrition_status: 'estimated' });

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
      payload: {
        record: {
          food_items: '鸡蛋 2 个',
          meal_type: 'breakfast',
        },
      },
    })).resolves.toEqual({ status: 'completed', nutrition_status: 'estimate_failed' });

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
      payload: {
        record: {
          food_items: '鸡蛋 2 个',
          meal_type: 'breakfast',
        },
      },
    })).rejects.toThrow('unsupported_card_action_endpoint');

    expect(mockApiPost).not.toHaveBeenCalled();
  });
});
