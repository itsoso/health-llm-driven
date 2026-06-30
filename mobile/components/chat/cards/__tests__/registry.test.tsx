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

  it('renders reminder record cards from chat tool results', () => {
    const r = renderCard({
      type: 'record',
      data: { type: 'reminder', detail: '已设置每日提醒：臀中肌训练' },
    });
    expect(r).not.toBeNull();

    const { getByText } = render(r!);
    expect(getByText('已设置每日提醒：臀中肌训练')).toBeTruthy();
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
          verification_metrics: ['post_meal_walk_completed', 'waist_cm', 'hrv'],
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

    const { getByText, queryByText } = render(r!);
    expect(getByText('7天验证节奏')).toBeTruthy();
    expect(getByText('晚餐后步行 15 分钟')).toBeTruthy();
    expect(queryByText('围绕当前重点动态重排')).toBeNull();
    expect(getByText('基于今日状态重排')).toBeTruthy();
    expect(getByText('晚间')).toBeTruthy();
    expect(getByText('腰围')).toBeTruthy();
    expect(getByText('HRV')).toBeTruthy();
    expect(() => getByText('today_smart_rank')).toThrow();
    expect(() => getByText('waist_cm')).toThrow();
    fireEvent.press(getByText('查看7天计划'));
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'route.open' }),
      expect.objectContaining({ type: 'runtime_agenda' }),
    );
  });

  it('renders operating review cards from backend prediction backtest', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'operating_review',
      data: {
        window_days: 7,
        start_date: '2026-06-22',
        end_date: '2026-06-28',
        execution: {
          total_events: 4,
          completed_events: 3,
          completion_rate: 0.75,
        },
        metrics: [
          { metric: 'waist_cm', current: 94.8, delta: -1.2, current_date: '2026-06-28' },
        ],
        prediction_backtest: {
          status: 'ready',
          ready_candidate_count: 1,
          summary: { met: 1, not_met: 0, inconclusive: 0 },
          results: [
            {
              prediction_id: 'pred-waist-7d',
              action_title: '累计 35-45 分钟中等强度活动',
              metric: 'waist_cm',
              horizon_days: 7,
              observed_delta: -1.2,
              verdict: 'met',
              confidence_after: 'medium',
            },
          ],
          boundary: '预测回测只比较预期信号与窗口内实际变化, 属观察性复盘, 不证明单个行动造成指标变化。',
        },
        causal_memory: {
          notes: [{ metric: 'hrv', text: '晚餐提前之后 HRV 改善(相关非因果)' }],
          claim_boundary: '事件先于指标变化的时序相关,非证明因果;不替代医学结论。',
        },
      },
      actions: [
        {
          id: 'open-operating-review',
          label: '查看复盘详情',
          action: 'route.open',
          payload: { route: '/my-progress' },
          style: 'primary',
        },
      ],
    } as any;
    const r = renderCard(descriptor, { onAction });
    expect(r).not.toBeNull();

    const { getByText } = render(r!);
    expect(getByText('7天复盘')).toBeTruthy();
    expect(getByText('完成率 75%')).toBeTruthy();
    expect(getByText('预测回测: 1/1 支持')).toBeTruthy();
    expect(getByText(/累计 35-45 分钟中等强度活动/)).toBeTruthy();
    expect(getByText(/不证明单个行动造成指标变化/)).toBeTruthy();
    fireEvent.press(getByText('查看复盘详情'));
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'route.open' }),
      expect.objectContaining({ type: 'operating_review' }),
    );
  });

  it('renders metric chart cards from backend health data', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'metric_chart',
      data: {
        metric: 'hrv',
        title: '最近半年 HRV',
        unit: 'ms',
        start_date: '2025-12-29',
        end_date: '2026-06-30',
        coverage: { days_with_data: 181, days_in_window: 184 },
        latest: { date: '2026-06-30', value: 56.0, source: 'apple-watch' },
        summary: {
          avg: 57.3,
          last_7d_avg: 48.8,
          last_30d_avg: 50.9,
          prev_30d_avg: 57.5,
          last_30_vs_prev_30_delta: -6.6,
        },
        series: [
          { date: '2026-06-24', value: 52.0, rolling_7d: 54.0, source: 'garmin' },
          { date: '2026-06-25', value: 49.0, rolling_7d: 53.0, source: 'garmin' },
          { date: '2026-06-30', value: 56.0, rolling_7d: 48.8, source: 'apple-watch' },
        ],
        boundary: 'HRV 趋势仅用于健康管理参考, 不替代诊断或治疗。',
      },
      actions: [
        {
          id: 'open-hrv-history',
          label: '查看HRV历史',
          action: 'route.open',
          payload: { route: '/indicator-history?type=hrv' },
          style: 'secondary',
        },
      ],
    } as any;
    const r = renderCard(descriptor, { onAction });
    expect(r).not.toBeNull();

    const { getByText } = render(r!);
    expect(getByText('最近半年 HRV')).toBeTruthy();
    expect(getByText('56.0ms')).toBeTruthy();
    expect(getByText('181/184 天')).toBeTruthy();
    expect(getByText('近30天 -6.6ms')).toBeTruthy();
    expect(getByText(/不替代诊断或治疗/)).toBeTruthy();
    fireEvent.press(getByText('查看HRV历史'));
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'route.open' }),
      expect.objectContaining({ type: 'metric_chart' }),
    );
  });

  it('renders non-HRV metric chart cards with metric-specific units and actions', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'metric_chart',
      data: {
        metric: 'weight',
        label: '体重',
        title: '最近30天 体重',
        unit: 'kg',
        start_date: '2026-06-01',
        end_date: '2026-06-30',
        coverage: { days_with_data: 3, days_in_window: 31 },
        latest: { date: '2026-06-30', value: 73.8, source: 'manual' },
        summary: {
          avg: 74.1,
          last_7d_avg: 73.9,
          last_30d_avg: 74.1,
          prev_30d_avg: 74.8,
          last_30_vs_prev_30_delta: -0.7,
        },
        series: [
          { date: '2026-06-26', value: 74.5, rolling_7d: 74.5, source: 'manual' },
          { date: '2026-06-28', value: 74.0, rolling_7d: 74.3, source: 'manual' },
          { date: '2026-06-30', value: 73.8, rolling_7d: 74.1, source: 'manual' },
        ],
        boundary: '体重 趋势仅用于健康管理参考, 不替代诊断或治疗。',
      },
      actions: [
        {
          id: 'open-weight-history',
          label: '查看体重历史',
          action: 'route.open',
          payload: { route: '/indicator-history?type=weight' },
          style: 'secondary',
        },
      ],
    } as any;

    const r = renderCard(descriptor, { onAction });
    expect(r).not.toBeNull();

    const { getByText } = render(r!);
    expect(getByText('最近30天 体重')).toBeTruthy();
    expect(getByText('73.8kg')).toBeTruthy();
    expect(getByText('3/31 天')).toBeTruthy();
    expect(getByText('近30天 -0.7kg')).toBeTruthy();
    fireEvent.press(getByText('查看体重历史'));
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'route.open', payload: { route: '/indicator-history?type=weight' } }),
      expect.objectContaining({ type: 'metric_chart' }),
    );
  });

  it('renders generic metric_line_chart dynamic UI cards', () => {
    const descriptor = {
      type: 'metric_line_chart',
      data: {
        schema: 'reva.metric_line_chart.v1',
        component: 'metric_line_chart',
        metric: 'resting_hr',
        range: '6m',
        title: '静息心率趋势',
        unit: 'bpm',
        x: ['06-29', '06-30'],
        series: [
          { name: 'Apple Watch 静息心率', role: 'device', points: [62, 58] },
          { name: '7日滚动均值', role: 'avg_7d', points: [61, 60] },
        ],
        annotations: [{ x: '06-30', label: '最新 58 bpm · Apple Watch', kind: 'latest' }],
        source: 'garmin',
        data_note: '基于 2 天真实数据',
      },
    } as any;

    const r = renderCard(descriptor);
    expect(r).not.toBeNull();

    const { getByText } = render(r!);
    expect(getByText('静息心率趋势')).toBeTruthy();
    expect(getByText('Apple Watch 静息心率')).toBeTruthy();
    expect(getByText('7日滚动均值')).toBeTruthy();
    expect(getByText(/最新 58 bpm/)).toBeTruthy();
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

  it('cards_group preserves child card actions so multi-card replies stay actionable', () => {
    const onAction = jest.fn();
    const r = renderCard({
      type: 'cards_group',
      data: {
        cards: [
          {
            type: 'runtime_agenda',
            data: { next_action: { title: '晚餐后步行 15 分钟' } },
            actions: [
              {
                id: 'open-runtime',
                label: '查看7天计划',
                action: 'route.open',
                payload: { route: '/agenda' },
                style: 'primary',
              },
            ],
          },
          {
            type: 'operating_review',
            data: {
              window_days: 7,
              execution: { total_events: 1, completed_events: 1, completion_rate: 1 },
            },
            actions: [
              {
                id: 'open-review',
                label: '查看复盘详情',
                action: 'route.open',
                payload: { route: '/my-progress' },
                style: 'primary',
              },
            ],
          },
        ],
      },
    }, { onAction });

    expect(r).not.toBeNull();
    const { getByText } = render(r!);

    fireEvent.press(getByText('查看7天计划'));
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'route.open', payload: { route: '/agenda' } }),
      expect.objectContaining({ type: 'runtime_agenda' }),
    );

    fireEvent.press(getByText('查看复盘详情'));
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'route.open', payload: { route: '/my-progress' } }),
      expect.objectContaining({ type: 'operating_review' }),
    );
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

  it('filters unsafe write actions before they reach the chat UI', () => {
    const r = renderServerCards([
      {
        type: 'vitals',
        data: {},
        actions: [
          {
            label: '缺少人工确认的完成按钮',
            action: 'agenda.complete',
            endpoint: '/agenda/complete',
            payload: { source: { object_type: 'health_protocol', object_id: 7 } },
          },
          {
            label: '打开记录页',
            action: 'route.open',
            payload: { route: '/(tabs)/record' },
          },
          {
            label: '确认写入',
            action: 'write_intent.confirm',
            endpoint: '/write-intents/42/confirm',
            requires_manual_confirm: true,
            payload: { write_intent_id: 42 },
          },
        ],
      } as any,
    ]);

    expect(r[0].actions).toEqual([
      expect.objectContaining({ action: 'route.open' }),
      expect.objectContaining({ action: 'write_intent.confirm', requires_manual_confirm: true }),
    ]);
  });

  it('非数组 → []', () => {
    expect(renderServerCards({} as any)).toEqual([]);
    expect(renderServerCards('string' as any)).toEqual([]);
  });
});
