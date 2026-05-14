import {
  AGENT_CONTEXT_MAX_CHARS,
  buildChatContextRoute,
  createDietAgentContext,
  createSafetyAlertAgentContext,
  serializeAgentContext,
} from '../agentContext';

describe('agentContext', () => {
  it('builds chat route params with serialized context and badge', () => {
    const route = buildChatContextRoute({
      prompt: '今天饮食结构怎么样?',
      context: { from: 'diet/2026-05-14', date: '2026-05-14' },
      badge: '基于今日饮食 3 餐',
    });

    expect(route.pathname).toBe('/(tabs)/chat');
    expect(route.params.prompt).toBe('今天饮食结构怎么样?');
    expect(route.params.badge).toBe('基于今日饮食 3 餐');
    expect(JSON.parse(route.params.context)).toEqual({
      from: 'diet/2026-05-14',
      date: '2026-05-14',
    });
  });

  it('limits serialized context to the backend max length', () => {
    const context = serializeAgentContext({
      from: 'oversized',
      text: 'x'.repeat(AGENT_CONTEXT_MAX_CHARS + 500),
    });

    expect(context.length).toBeLessThanOrEqual(AGENT_CONTEXT_MAX_CHARS);
    expect(context).toContain('[truncated]');
  });

  it('creates compact diet context from daily summary', () => {
    const context = createDietAgentContext({
      record_date: '2026-05-14',
      total_calories: 1820,
      total_protein: 92,
      total_carbs: 180,
      total_fat: 58,
      total_fiber: 21,
      meals_count: 2,
      meals: [
        {
          id: 1,
          user_id: 1,
          record_date: '2026-05-14',
          meal_type: 'breakfast',
          food_items: '鸡蛋、燕麦',
          calories: 520,
          protein: 28,
          carbs: 60,
          fat: 18,
          fiber: 8,
          alcohol_units: null,
          image_url: null,
          notes: '训练前',
          health_tips: null,
        },
      ],
    });

    expect(context).toEqual({
      from: 'diet/2026-05-14',
      date: '2026-05-14',
      totals: {
        calories: 1820,
        protein: 92,
        carbs: 180,
        fat: 58,
        fiber: 21,
      },
      targets: null,
      meals: [
        {
          meal_type: 'breakfast',
          food_items: '鸡蛋、燕麦',
          calories: 520,
          protein: 28,
          carbs: 60,
          fat: 18,
          fiber: 8,
          notes: '训练前',
        },
      ],
    });
  });

  it('keeps safety alert rule context with the alert payload', () => {
    const context = createSafetyAlertAgentContext({
      rule_id: 'hrv_drop',
      severity: 'high',
      category: 'recovery',
      title: 'HRV 连续下降',
      message: 'HRV 低于 7 日均值 20%',
      action: '今晚降低训练强度',
      context: { hrv_today: 28, hrv_7d: 40 },
    });

    expect(context).toEqual({
      from: 'safety-alert/hrv_drop',
      alert_id: 'hrv_drop',
      rule_name: 'HRV 连续下降',
      severity: 'high',
      category: 'recovery',
      message: 'HRV 低于 7 日均值 20%',
      action: '今晚降低训练强度',
      triggered_metrics: { hrv_today: 28, hrv_7d: 40 },
    });
  });
});
