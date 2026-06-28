import { CARD_REGISTRY, CARD_MAP, dispatchCard, renderCard, renderServerCards } from '../registry';
import type { CardContext } from '../types';
import { fireEvent, render } from '@testing-library/react-native';

function makeContext(query: string, overrides?: Partial<CardContext>): CardContext {
  return {
    query,
    query_lower: query.toLowerCase(),
    toolsUsed: new Set(),
    data: {},
    api: { get: jest.fn(), post: jest.fn() },
    ...overrides,
  };
}

describe('CARD_REGISTRY', () => {
  it('has at least 10 registered cards', () => {
    expect(CARD_REGISTRY.length).toBeGreaterThanOrEqual(10);
  });

  it('each card has required fields', () => {
    for (const spec of CARD_REGISTRY) {
      expect(spec.type).toBeTruthy();
      expect(spec.label).toBeTruthy();
      expect(typeof spec.match).toBe('function');
      expect(typeof spec.build).toBe('function');
      expect(typeof spec.render).toBe('function');
    }
  });
});

describe('CARD_MAP', () => {
  it('maps all registry entries by type', () => {
    for (const spec of CARD_REGISTRY) {
      expect(CARD_MAP[spec.type]).toBe(spec);
    }
  });
});

describe('card match priorities', () => {
  it('sleep query matches sleep card', () => {
    const ctx = makeContext('我昨晚睡眠怎么样');
    const sleepSpec = CARD_REGISTRY.find((s) => s.type === 'sleep');
    expect(sleepSpec).toBeDefined();
    const score = sleepSpec!.match(ctx);
    expect(score).toBeGreaterThan(0);
  });

  it('weight query matches weight card', () => {
    const ctx = makeContext('我的体重多少');
    const weightSpec = CARD_REGISTRY.find((s) => s.type === 'weight');
    expect(weightSpec).toBeDefined();
    const score = weightSpec!.match(ctx);
    expect(score).toBeGreaterThan(0);
  });

  it('unrelated query does not match specific cards', () => {
    const ctx = makeContext('今天天气怎么样');
    const bpSpec = CARD_REGISTRY.find((s) => s.type === 'blood_pressure');
    expect(bpSpec).toBeDefined();
    const score = bpSpec!.match(ctx);
    expect(score === null || score === 0).toBe(true);
  });
});

describe('dispatchCard', () => {
  it('returns null for empty query with no matching cards', async () => {
    const ctx = makeContext('');
    const result = await dispatchCard(ctx);
    expect(result).toBeNull();
  });

  it('build 抛错时不阻塞, 返回 null', async () => {
    const ctx = makeContext('体重多少', {
      api: { get: jest.fn().mockRejectedValue(new Error('net')), post: jest.fn() },
    });
    const result = await dispatchCard(ctx);
    expect(result).toBeNull();
  });
});

describe('renderCard 安全降级', () => {
  it('未知 type 返回 null, 不抛异常', () => {
    expect(renderCard({ type: 'fake_xxx', data: {} })).toBeNull();
  });

  it('已知 type → 返回 React 元素', () => {
    const r = renderCard({ type: 'vitals', data: { sleep: '8h' } });
    expect(r).not.toBeNull();
  });

  it('renders server card actions and dispatches through onAction', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'vitals',
      data: { sleep: '8h' },
      actions: [
        {
          id: 'complete-now',
          label: '完成',
          action: 'agenda.complete',
          endpoint: '/agenda/complete',
          requires_manual_confirm: true,
          payload: {
            source: { object_type: 'health_protocol', object_id: 7 },
          },
        },
      ],
    } as any;

    const element = renderCard(descriptor, { onAction });
    expect(element).not.toBeNull();

    const { getByText } = render(element!);
    fireEvent.press(getByText('完成'));

    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'agenda.complete' }),
      expect.objectContaining({ type: 'vitals' }),
    );
  });

  it('renders medical exam import result cards from runtime skills', () => {
    const r = renderCard({
      type: 'medical_exam_import_result',
      data: {
        exam_id: 42,
        items_count: 28,
        abnormal_count: 3,
        source: 'pdf',
        review_required: true,
      },
    });
    expect(r).not.toBeNull();
  });

  it('renders runtime agenda cards from backend runtime projection', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'runtime_agenda',
      data: {
        generated_by: 'rolling_health_runtime_v1',
        horizon_days: 7,
        next_action: {
          title: '晚餐后步行 15 分钟',
          kind: 'movement',
          time_window: 'evening',
          priority_tier: 'P1',
          current_state_summary: '晚餐后是今天最短的代谢干预窗口。',
          replan_reason: 'today_smart_rank',
          verification_metrics: ['post_meal_walk_completed', 'waist_cm'],
          verification_window_days: 7,
        },
        days: [
          { date: '2026-06-28', next_action_title: '晚餐后步行 15 分钟', items_count: 1 },
          { date: '2026-06-29', next_action_title: '晨间补水', items_count: 2 },
        ],
        safety_boundary: '这是健康管理行动建议,不替代医生诊断。',
      },
      actions: [
        {
          id: 'open-runtime-agenda',
          label: '查看7天计划',
          action: 'route.open',
          payload: { route: '/agenda' },
          style: 'primary',
        },
      ],
    } as any;
    const r = renderCard(descriptor, { onAction });
    expect(r).not.toBeNull();

    const { getByText } = render(r!);
    expect(getByText('7天健康运行时')).toBeTruthy();
    expect(getByText('晚餐后步行 15 分钟')).toBeTruthy();
    fireEvent.press(getByText('查看7天计划'));
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'route.open' }),
      expect.objectContaining({ type: 'runtime_agenda' }),
    );
  });

  it('cards_group 1 张子卡 → 直接渲染, 不包 grid', () => {
    const r = renderCard({
      type: 'cards_group',
      data: { cards: [{ type: 'vitals', data: { sleep: '8h' } }] },
    });
    expect(r).not.toBeNull();
  });

  it('cards_group 2 张子卡 → wrapper View', () => {
    const r = renderCard({
      type: 'cards_group',
      data: {
        cards: [
          { type: 'vitals', data: { sleep: '8h' } },
          { type: 'weight', data: { current_kg: 72 } },
        ],
      },
    });
    expect(r).not.toBeNull();
  });

  it('cards_group 全是未知 type → null', () => {
    const r = renderCard({
      type: 'cards_group',
      data: { cards: [{ type: 'aaa', data: {} }, { type: 'bbb', data: {} }] },
    });
    expect(r).toBeNull();
  });

  it('cards_group 无 data.cards → null', () => {
    expect(renderCard({ type: 'cards_group', data: {} })).toBeNull();
  });
});

describe('renderServerCards 防御', () => {
  it('null/undefined/[] → []', () => {
    expect(renderServerCards()).toEqual([]);
    expect(renderServerCards(null)).toEqual([]);
    expect(renderServerCards([])).toEqual([]);
  });

  it('过滤未知 type', () => {
    const r = renderServerCards([
      { type: 'vitals', data: {} },
      { type: 'runtime_agenda', data: { next_action: { title: '今日重点' } } },
      { type: 'fake', data: {} },
      { type: 'sleep', data: {} },
    ]);
    expect(r.map((c) => c.type)).toEqual(['vitals', 'runtime_agenda', 'sleep']);
  });

  it('preserves allowed server card actions for chat dispatch', () => {
    const r = renderServerCards([
      {
        type: 'vitals',
        data: {},
        actions: [
          {
            label: '完成',
            action: 'agenda.complete',
            endpoint: '/agenda/complete',
            requires_manual_confirm: true,
            payload: { source: { object_type: 'health_protocol', object_id: 7 } },
          },
        ],
      } as any,
    ]);

    expect(r[0]).toEqual(expect.objectContaining({
      type: 'vitals',
      actions: [expect.objectContaining({ action: 'agenda.complete' })],
    }));
  });

  it('非数组 → []', () => {
    expect(renderServerCards({} as any)).toEqual([]);
    expect(renderServerCards('string' as any)).toEqual([]);
  });
});
