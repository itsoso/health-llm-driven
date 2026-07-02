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

  it('renders record quality cards with personal cautions and inline next-meal actions', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'record_quality',
      data: {
        domain: 'diet',
        title: '午餐已记录',
        summary: '770 kcal · 蛋白 30g · 碳水 70g',
        metrics: [
          { label: '热量', value: '770kcal' },
          { label: '蛋白', value: '30g' },
        ],
        progress: {
          protein_total_g: 37,
          protein_target_g: 112,
          remaining_protein_g: 75,
          calories_total: 1040,
          meals_count: 2,
        },
        primary_judgement: '蛋白质到位，但晚餐仍要补足。',
        personal_cautions: ['胃溃疡记录在案，冷饮/酸性饮品可能刺激胃，建议观察耐受。'],
        next_action: '晚餐优先 40g 蛋白，少油少刺激。',
        boundary: '健康管理建议，不替代医生诊断或治疗。',
      },
      actions: [
        {
          id: 'show-next-meal',
          label: '看下一餐建议',
          action: 'ui.inline.expand',
          style: 'primary',
          payload: {
            target: 'next_meal',
            patch: {
              expanded_sections: ['next_meal'],
              next_meal_detail: {
                title: '下一餐建议',
                summary: '晚餐优先 40g 蛋白，少油少刺激。',
                options: ['鱼/豆腐 + 熟蔬菜 + 少量主食', '鸡胸/鸡蛋 + 南瓜 + 绿叶菜'],
                rationale: ['午餐后今日蛋白还差约 75g', '胃溃疡背景下避免冷饮和强刺激'],
                continue_prompt: '可以继续问阿衡：如果今晚只能外卖，怎么选。',
              },
            },
          },
        },
      ],
    } as any;

    const element = renderCard(descriptor, { onAction });
    expect(element).not.toBeNull();

    const { getByText } = render(element!);
    expect(getByText('午餐已记录')).toBeTruthy();
    expect(getByText('770 kcal · 蛋白 30g · 碳水 70g')).toBeTruthy();
    expect(getByText('37/112g')).toBeTruthy();
    expect(getByText('已记 1040 kcal · 2 餐 · 还差约 75g 蛋白')).toBeTruthy();
    expect(getByText('胃溃疡记录在案，冷饮/酸性饮品可能刺激胃，建议观察耐受。')).toBeTruthy();

    fireEvent.press(getByText('看下一餐建议'));
    expect(onAction).not.toHaveBeenCalled();
    expect(getByText('下一餐建议')).toBeTruthy();
    expect(getByText('鱼/豆腐 + 熟蔬菜 + 少量主食')).toBeTruthy();
    expect(getByText('可以继续问阿衡：如果今晚只能外卖，怎么选。')).toBeTruthy();
  });

  it('renders confirmable diet draft cards with next action guidance', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'diet_draft',
      data: {
        meal_type: 'lunch',
        food_items: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
        calories: 770,
        protein: 30,
        carbs: 70,
        fat: 17,
        confidence: 0.82,
        source: 'chat_photo',
        suggestions: ['晚餐优先补 40g 蛋白', '餐后轻走 8-10 分钟'],
        post_meal_walk: { recommended: true, minutes: 10 },
        boundary: '营养为估算值,确认后写入今日饮食记录。',
      },
      actions: [
        {
          id: 'confirm-diet-draft',
          label: '确认记录',
          action: 'diet_record.create',
          endpoint: '/diet/records',
          requires_manual_confirm: true,
          style: 'primary',
          payload: {
            record: {
              meal_type: 'lunch',
              food_items: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
              calories: 770,
              protein: 30,
              carbs: 70,
              fat: 17,
              notes: '来源: chat_photo; 置信度 82%',
            },
          },
        },
        {
          id: 'open-diet',
          label: '去饮食页修正',
          action: 'route.open',
          payload: { route: '/diet' },
        },
      ],
    } as any;

    const element = renderCard(descriptor, { onAction });
    expect(element).not.toBeNull();

    const { getByText } = render(element!);
    expect(getByText('待确认饮食记录')).toBeTruthy();
    expect(getByText('午餐')).toBeTruthy();
    expect(getByText('煎牛肉能量碗 + 姜黄鲜柠维C茶')).toBeTruthy();
    expect(getByText('热量 770kcal')).toBeTruthy();
    expect(getByText('蛋白 30g')).toBeTruthy();
    expect(getByText('置信度 82% · 来源: 对话/图片')).toBeTruthy();
    expect(getByText('餐后轻走 10 分钟')).toBeTruthy();
    expect(getByText('营养为估算值,确认后写入今日饮食记录。')).toBeTruthy();

    fireEvent.press(getByText('确认记录'));
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'diet_record.create', endpoint: '/diet/records' }),
      expect.objectContaining({ type: 'diet_draft' }),
    );
  });

  it('lets users edit a diet draft inline before confirming it', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'diet_draft',
      data: {
        meal_type: 'lunch',
        food_items: '煎牛肉能量碗',
        calories: 770,
        protein: 30,
        carbs: 70,
        fat: 17,
      },
      actions: [
        {
          id: 'confirm-diet-draft',
          label: '确认记录',
          action: 'diet_record.create',
          endpoint: '/diet/records',
          requires_manual_confirm: true,
          style: 'primary',
          payload: {
            record: {
              meal_type: 'lunch',
              food_items: '煎牛肉能量碗',
              calories: 770,
              protein: 30,
              carbs: 70,
              fat: 17,
            },
          },
        },
      ],
    } as any;

    const element = renderCard(descriptor, { onAction });
    expect(element).not.toBeNull();

    const { getByText, getByLabelText } = render(element!);
    fireEvent.press(getByText('修正'));
    fireEvent.press(getByText('晚餐'));
    fireEvent.changeText(getByLabelText('食物描述'), '鸡胸肉 200g + 杂粮饭 100g');
    fireEvent.changeText(getByLabelText('蛋白'), '46');
    fireEvent.press(getByText('确认记录'));

    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({
        action: 'diet_record.create',
        payload: expect.objectContaining({
          record: expect.objectContaining({
            meal_type: 'dinner',
            food_items: '鸡胸肉 200g + 杂粮饭 100g',
            calories: 770,
            protein: 46,
            carbs: 70,
            fat: 17,
          }),
        }),
      }),
      expect.objectContaining({ type: 'diet_draft' }),
    );
  });

  it('lets users save and confirm an edited diet draft from the editor', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'diet_draft',
      data: {
        meal_type: 'lunch',
        food_items: '煎牛肉能量碗',
        calories: 770,
        protein: 30,
        carbs: 70,
        fat: 17,
      },
      actions: [
        {
          id: 'confirm-diet-draft',
          label: '确认记录',
          action: 'diet_record.create',
          endpoint: '/diet/records',
          requires_manual_confirm: true,
          style: 'primary',
          payload: {
            record: {
              meal_type: 'lunch',
              food_items: '煎牛肉能量碗',
              calories: 770,
              protein: 30,
              carbs: 70,
              fat: 17,
            },
          },
        },
      ],
    } as any;

    const element = renderCard(descriptor, { onAction });
    expect(element).not.toBeNull();

    const { getByText, getByLabelText } = render(element!);
    fireEvent.press(getByText('修正'));
    fireEvent.press(getByText('晚餐'));
    fireEvent.changeText(getByLabelText('食物描述'), '鸡胸肉 200g + 杂粮饭 100g');
    fireEvent.changeText(getByLabelText('蛋白'), '46');
    fireEvent.press(getByText('保存并确认'));

    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({
        action: 'diet_record.create',
        payload: expect.objectContaining({
          record: expect.objectContaining({
            meal_type: 'dinner',
            food_items: '鸡胸肉 200g + 杂粮饭 100g',
            calories: 770,
            protein: 46,
            carbs: 70,
            fat: 17,
          }),
        }),
      }),
      expect.objectContaining({ type: 'diet_draft' }),
    );
  });

  it('renders structured diet draft food arrays as a readable meal line', () => {
    const element = renderCard({
      type: 'diet_draft',
      data: {
        meal_type: 'dinner',
        food_items: ['鸡胸肉 200g', '杂粮饭 100g', '西兰花'],
        protein: 46,
      },
    } as any);

    expect(element).not.toBeNull();
    const { getByText } = render(element!);
    expect(getByText('鸡胸肉 200g + 杂粮饭 100g + 西兰花')).toBeTruthy();
    expect(getByText('晚餐')).toBeTruthy();
    expect(getByText('蛋白 46g')).toBeTruthy();
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

  it('preserves interaction metadata on safe write actions', () => {
    const r = renderServerCards([
      {
        type: 'vitals',
        data: {},
        actions: [
          {
            label: '确认记录',
            action: 'write_intent.confirm',
            endpoint: '/write-intents/42/confirm',
            requires_manual_confirm: true,
            payload: { write_intent_id: 42 },
            confirmation: {
              title: '记录 30 个俯卧撑？',
              detail: '将写入今天的运动记录',
              confirm_label: '确认记录',
              cancel_label: '再看看',
            },
            optimistic: true,
          },
        ],
      } as any,
    ]);

    expect(r[0].actions?.[0]).toEqual(expect.objectContaining({
      action: 'write_intent.confirm',
      confirmation: expect.objectContaining({ title: '记录 30 个俯卧撑？' }),
      optimistic: true,
    }));
  });

  it('renders disabled card actions without dispatching them', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'vitals',
      data: { sleep: '8h' },
      actions: [
        {
          id: 'complete-missing-source',
          label: '完成',
          action: 'agenda.complete',
          endpoint: '/agenda/complete',
          requires_manual_confirm: true,
          disabled_reason: '缺少可完成的行动来源',
          payload: {},
        },
      ],
    } as any;

    const element = renderCard(descriptor, { onAction });
    expect(element).not.toBeNull();

    const { getByText } = render(element!);
    fireEvent.press(getByText('完成'));

    expect(onAction).not.toHaveBeenCalled();
    expect(getByText('缺少可完成的行动来源')).toBeTruthy();
  });

  it('renders in-flight card actions as disabled execution feedback', () => {
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

    const element = renderCard(descriptor, {
      onAction,
      actionStateByKey: { 'complete-now': 'running' },
    } as any);
    expect(element).not.toBeNull();

    const { getByText } = render(element!);
    fireEvent.press(getByText('执行中'));

    expect(onAction).not.toHaveBeenCalled();
  });

  it('renders completed diet record actions as recorded feedback', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'diet_draft',
      data: { food_items: '鸡胸肉 200g', meal_type: 'lunch' },
      actions: [
        {
          id: 'confirm-diet',
          label: '确认记录',
          action: 'diet_record.create',
          endpoint: '/diet/records',
          requires_manual_confirm: true,
          payload: { record: { food_items: '鸡胸肉 200g', meal_type: 'lunch' } },
        },
      ],
    } as any;

    const element = renderCard(descriptor, {
      onAction,
      actionStateByKey: { 'confirm-diet': 'done' },
    } as any);
    expect(element).not.toBeNull();

    const { getByText } = render(element!);
    fireEvent.press(getByText('已记录'));

    expect(onAction).not.toHaveBeenCalled();
  });

  it('shows in-card completion feedback after a diet draft is recorded', () => {
    const descriptor = {
      type: 'diet_draft',
      data: {
        food_items: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
        meal_type: 'lunch',
        calories: 770,
        protein: 30,
        carbs: 70,
        fat: 17,
        suggestions: ['晚餐优先补 40g 蛋白'],
        post_meal_walk: { recommended: true, minutes: 10 },
      },
      actions: [
        {
          id: 'confirm-diet-draft',
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
        },
      ],
    } as any;

    const element = renderCard(descriptor, {
      actionStateByKey: { 'confirm-diet-draft': 'done' },
    } as any);
    expect(element).not.toBeNull();

    const { getByText } = render(element!);
    expect(getByText('已写入今日饮食')).toBeTruthy();
    expect(getByText('午餐 · 770 kcal · 蛋白 30g')).toBeTruthy();
    expect(getByText('下一步: 餐后轻走 10 分钟')).toBeTruthy();
    expect(getByText('可在记录页继续修正,阿衡会把这餐纳入今日饮食进度。')).toBeTruthy();
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

  it('renders metric_empty_state dynamic UI cards', () => {
    const descriptor = {
      type: 'metric_empty_state',
      data: {
        schema: 'reva.metric_empty_state.v1',
        component: 'metric_empty_state',
        metric: 'blood_glucose',
        range: '7d',
        title: '血糖数据不足',
        message: '暂无足够数据，至少需要 3 天真实记录后才能生成趋势图。',
        suggestions: ['同步 HealthKit 或可穿戴设备数据', '补录最近几天的关键指标'],
        boundary: '仅用于健康管理参考，不替代诊断或治疗。',
      },
    } as any;

    const r = renderCard(descriptor);
    expect(r).not.toBeNull();

    const { getByText } = render(r!);
    expect(getByText('血糖数据不足')).toBeTruthy();
    expect(getByText(/至少需要 3 天真实记录/)).toBeTruthy();
    expect(getByText('同步 HealthKit 或可穿戴设备数据')).toBeTruthy();
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

  it('preserves manual-confirm diet record create actions', () => {
    const r = renderServerCards([
      {
        type: 'diet_draft',
        data: { food_items: '鸡蛋 2 个', meal_type: 'breakfast' },
        actions: [
          {
            label: '确认记录',
            action: 'diet_record.create',
            endpoint: '/diet/records',
            requires_manual_confirm: true,
            payload: {
              record: { food_items: '鸡蛋 2 个', meal_type: 'breakfast', protein: 12 },
            },
          },
          {
            label: '静默写入',
            action: 'diet_record.create',
            endpoint: '/diet/records',
            payload: {
              record: { food_items: '鸡蛋 2 个', meal_type: 'breakfast' },
            },
          },
        ],
      } as any,
    ]);

    expect(r[0].actions).toEqual([
      expect.objectContaining({
        action: 'diet_record.create',
        endpoint: '/diet/records',
        requires_manual_confirm: true,
      }),
    ]);
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

  it('filters unsafe route actions before they reach the chat UI', () => {
    const r = renderServerCards([
      {
        type: 'vitals',
        data: {},
        actions: [
          {
            label: '打开外部站点',
            action: 'route.open',
            payload: { route: '//example.test/path' },
          },
          {
            label: '打开异常路径',
            action: 'route.open',
            payload: { route: '/(tabs)/chat\ninject' },
          },
          {
            label: '打开阿衡',
            action: 'route.open',
            payload: { route: '/(tabs)/chat?prompt=hrv' },
          },
        ],
      } as any,
    ]);

    expect(r[0].actions).toEqual([
      expect.objectContaining({
        action: 'route.open',
        payload: { route: '/(tabs)/chat?prompt=hrv' },
      }),
    ]);
  });

  it('非数组 → []', () => {
    expect(renderServerCards({} as any)).toEqual([]);
    expect(renderServerCards('string' as any)).toEqual([]);
  });
});
