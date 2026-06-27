import { CARD_REGISTRY, CARD_MAP, dispatchCard, renderCard, renderServerCards } from '../registry';
import type { CardContext } from '../types';

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

  it('renders backend agenda_action cards for the runtime top action', () => {
    const r = renderCard({
      type: 'agenda_action',
      data: {
        title: '喝 200ml 温水',
        subtitle: '起床后补水',
        scheduled_for: '08:00',
        source: { object_type: 'health_protocol', object_id: 12 },
      },
    });
    expect(r).not.toBeNull();
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
      { type: 'fake', data: {} },
      { type: 'sleep', data: {} },
      { type: 'agenda_action', data: { title: '喝水' } },
    ]);
    expect(r.map((c) => c.type)).toEqual(['vitals', 'sleep', 'agenda_action']);
  });

  it('preserves server action descriptors on known cards', () => {
    const r = renderServerCards([
      {
        type: 'record',
        data: { type: 'water', detail: '喝水 200ml' },
        actions: [
          {
            action: 'complete_agenda',
            endpoint: '/agenda/complete',
            label: '完成',
            payload: { source: { object_type: 'health_protocol', object_id: 12 } },
          },
          { action: 'unsupported_x', label: '忽略' },
        ],
      },
    ]);

    expect(r).toHaveLength(1);
    expect(r[0].actions).toEqual([
      {
        action: 'complete_agenda',
        endpoint: '/agenda/complete',
        label: '完成',
        payload: { source: { object_type: 'health_protocol', object_id: 12 } },
      },
      { action: 'unsupported_x', label: '忽略' },
    ]);
  });

  it('非数组 → []', () => {
    expect(renderServerCards({} as any)).toEqual([]);
    expect(renderServerCards('string' as any)).toEqual([]);
  });
});
