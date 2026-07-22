/**
 * 动态卡片注册表回归测试
 *
 * 覆盖 3 个核心 API:
 *   - dispatchCard(ctx)        : 关键词触发 + 优先级 + build 失败兜底
 *   - renderCard(descriptor)   : 安全降级 + cards_group iPad 双列
 *   - renderServerCards(arr)   : 后端推送过滤
 *
 * 每个公共行为都有一个测试. 任何 ConsultationsCard 那种 'e.reduce is not a
 * function' 类的运行时崩溃应该在这里就被抓住.
 */
// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { api } from '@/services/api/client';
import {
  CARD_REGISTRY,
  CARD_MAP,
  dispatchCard,
  renderCard,
  renderServerCards,
} from '../registry';
import type { CardContext } from '../types';

const ctx = (q: string, over?: Partial<CardContext>): CardContext => ({
  query: q,
  query_lower: q.toLowerCase(),
  toolsUsed: new Set(),
  data: {},
  api: { get: vi.fn(), post: vi.fn() },
  ...over,
});

// ── CARD_REGISTRY 不变量 ────────────────────────────────────
describe('CARD_REGISTRY 结构', () => {
  it('注册了至少 8 张卡片', () => {
    expect(CARD_REGISTRY.length).toBeGreaterThanOrEqual(8);
  });

  it('每张卡片都有完整契约 (type/label/match/build/render)', () => {
    for (const spec of CARD_REGISTRY) {
      expect(spec.type).toBeTruthy();
      expect(spec.label).toBeTruthy();
      expect(typeof spec.match).toBe('function');
      expect(typeof spec.build).toBe('function');
      expect(typeof spec.render).toBe('function');
    }
  });

  it('type 唯一不重复', () => {
    const types = CARD_REGISTRY.map((s) => s.type);
    expect(new Set(types).size).toBe(types.length);
  });

  it('CARD_MAP 完整覆盖所有 spec', () => {
    for (const spec of CARD_REGISTRY) {
      expect(CARD_MAP[spec.type]).toBe(spec);
    }
  });
});

// ── dispatchCard ───────────────────────────────────────────
describe('dispatchCard', () => {
  it('无关键词 → 返回 null', async () => {
    const r = await dispatchCard(ctx('随便问问'));
    expect(r).toBeNull();
  });

  it('"睡眠如何" → SleepCardSpec match (优先级 20)', async () => {
    const r = await dispatchCard(
      ctx('睡眠如何', { data: { garmin: { sleep_score: 85, total_sleep_duration: 480 } } }),
    );
    expect(r?.type).toBe('sleep');
    expect((r?.data as any).score).toBe(85);
  });

  it('"我饮食如何" → DietCardSpec match', async () => {
    const api = {
      get: vi.fn().mockResolvedValue({
        data: {
          total_calories: 1500, total_protein: 80, total_carbs: 200, total_fat: 50,
          total_fiber: 25, meals_count: 3, meals: [],
        },
      }),
    };
    const r = await dispatchCard(ctx('我饮食如何', { api }));
    expect(r?.type).toBe('diet');
    expect((r?.data as any).calories).toBe(1500);
  });

  it('记录类意图 ("刚喝了水") → record 而非 record-like 分析卡', async () => {
    const r = await dispatchCard(ctx('刚喝了一杯水'));
    expect(r?.type).toBe('record');
  });

  it('单卡 build 失败时, 不阻塞其他卡 (回退到下一个候选)', async () => {
    // 体重关键词 → WeightCardSpec match=15. 让 api.get 抛错, 应该返回 null 但不崩溃
    const api = { get: vi.fn().mockRejectedValue(new Error('network')) };
    const r = await dispatchCard(ctx('体重多少', { api }));
    // weight build 失败后没有其他匹配 → null. 不应崩溃.
    expect(r).toBeNull();
  });

  it('build 抛同步异常也被 catch', async () => {
    const api = { get: vi.fn(() => { throw new Error('sync explode'); }) };
    const r = await dispatchCard(ctx('体重多少', { api }));
    expect(r).toBeNull();
  });
});

// ── renderCard ─────────────────────────────────────────────
describe('renderCard', () => {
  it('未知 type → null (安全降级)', () => {
    const r = renderCard({ type: 'unknown_card_xxx', data: {} });
    expect(r).toBeNull();
  });

  it('已知 type → 返回 React 元素', () => {
    const r = renderCard({ type: 'vitals', data: { sleep: '8h', hr: '52bpm' } });
    expect(r).not.toBeNull();
    expect(r?.type).toBeDefined();
  });

  it('renders medical exam import result cards from runtime skills', () => {
    const r = renderCard({
      type: 'medical_exam_import_result',
      data: {
        exam_id: 42,
        source: 'pdf',
        items_count: 28,
        abnormal_count: 3,
        review_required: true,
      },
    });
    expect(r).not.toBeNull();
  });

  it('renders record_quality cards from backend post-record responses', () => {
    const r = renderCard({
      type: 'record_quality',
      data: {
        domain: 'diet',
        title: '午餐已记录',
        summary: '煎牛肉能量碗, 水煮蛋',
        metrics: [
          { label: '热量', value: '770kcal' },
          { label: '蛋白', value: '30g' },
        ],
        progress: {
          calories_total: 1040,
          meals_count: 2,
          protein_total_g: 37,
          protein_target_g: 112,
          remaining_protein_g: 75,
        },
        primary_judgement: '本餐蛋白质到位；今日蛋白 37/112g。',
        personal_cautions: ['胃溃疡记录在案，冷饮/酸性饮品可能刺激胃，建议观察耐受。'],
        next_action: '下一餐补约 45g 蛋白，少油少刺激。',
      },
    });
    expect(r).not.toBeNull();
  });

  it('keeps a server-issued diet draft and its manual confirmation action', () => {
    const cards = renderServerCards([{
      type: 'diet_draft',
      data: {
        meal_type: 'lunch',
        food_items: '鸡胸肉 120g + 米饭',
        calories: 420,
        protein: 37,
        photo_draft_token: 'contextual-diet-photo-token-123456',
        boundary: '营养为图像估算；确认后才写入今日饮食记录。',
      },
      actions: [{
        id: 'confirm-contextual-diet:contextual-diet-photo-token-123456',
        label: '确认记录',
        action: 'diet_record.create',
        endpoint: '/diet/records',
        requires_manual_confirm: true,
        required_receipt: true,
        capability_id: 'diet_draft.v1',
        payload: {
          record: {
            record_date: '2026-07-19',
            meal_type: 'lunch',
            food_items: '鸡胸肉 120g + 米饭',
            photo_draft_token: 'contextual-diet-photo-token-123456',
          },
        },
      }],
    }]);

    expect(cards).toHaveLength(1);
    expect(cards[0].type).toBe('diet_draft');
    expect(cards[0].actions?.[0]).toEqual(expect.objectContaining({
      action: 'diet_record.create',
      capability_id: 'diet_draft.v1',
    }));
    const html = renderToStaticMarkup(renderCard(cards[0])!);
    expect(html).toContain('确认记录');
    expect(html).toContain('鸡胸肉 120g');
  });

  it('renders an automatic contextual meal save as an explicit receipt', () => {
    const card = renderCard({
      type: 'diet_draft',
      data: {
        meal_type: 'lunch',
        food_items: '鸡胸肉 120g + 米饭',
        recorded: true,
        record_id: 76,
        receipt_message: '已自动记录到今日午餐',
      },
    });

    const html = renderToStaticMarkup(card!);
    expect(html).toContain('午餐已记录');
    expect(html).toContain('已自动记录到今日午餐');
    expect(html).not.toContain('确认记录');
  });

  it('forwards a validated diet confirmation action when the user clicks the card', () => {
    const onAction = vi.fn();
    const action = {
      id: 'confirm-contextual-diet:contextual-diet-photo-token-123456',
      label: '确认记录',
      action: 'diet_record.create',
      endpoint: '/diet/records',
      requires_manual_confirm: true,
      required_receipt: true,
      capability_id: 'diet_draft.v1',
      payload: {
        record: {
          record_date: '2026-07-19',
          meal_type: 'lunch',
          food_items: '鸡胸肉 120g + 米饭',
          photo_draft_token: 'contextual-diet-photo-token-123456',
        },
      },
    };
    const card = renderCard({
      type: 'diet_draft',
      data: { food_items: '鸡胸肉 120g + 米饭' },
      actions: [action],
    }, { onAction });

    render(card!);
    fireEvent.click(screen.getByRole('button', { name: '确认记录' }));

    expect(onAction).toHaveBeenCalledTimes(1);
    expect(onAction).toHaveBeenCalledWith(expect.objectContaining({
      action: 'diet_record.create',
      endpoint: '/diet/records',
      capability_id: 'diet_draft.v1',
    }));
  });

  it('keeps only policy-bound medication batch sibling actions for the same intent', () => {
    const policy = {
      requires_manual_confirm: true,
      required_receipt: true,
      capability_id: 'medication_draft.v1',
      autonomy_tier: 'manual_confirm',
      policy_reason: 'manual_confirm_write',
    };
    const cards = renderServerCards([{
      type: 'medication_draft',
      data: {
        items: [
          { medication_name: '伊托必利', actual_dosage: '1粒' },
          { medication_name: '替普瑞酮', actual_dosage: '1粒' },
        ],
      },
      actions: [
        {
          ...policy,
          label: '确认记录',
          action: 'write_intent.confirm',
          endpoint: '/write-intents/42/confirm',
          payload: { write_intent_id: 42 },
          style: 'primary',
        },
        {
          ...policy,
          label: '取消',
          action: 'write_intent.dismiss',
          endpoint: '/write-intents/42/dismiss',
          payload: { write_intent_id: 42 },
        },
        {
          ...policy,
          label: '篡改端点',
          action: 'write_intent.confirm',
          endpoint: '/write-intents/99/confirm',
          payload: { write_intent_id: 42 },
        },
      ],
    }]);

    expect(cards).toHaveLength(1);
    expect(cards[0].actions?.map(action => action.action)).toEqual([
      'write_intent.confirm',
      'write_intent.dismiss',
    ]);
  });

  it('disables both medication sibling actions while their intent group is submitting', () => {
    const onAction = vi.fn();
    const policy = {
      requires_manual_confirm: true,
      required_receipt: true,
      capability_id: 'medication_draft.v1',
      autonomy_tier: 'manual_confirm',
      policy_reason: 'manual_confirm_write',
    };
    const card = renderCard({
      type: 'medication_draft',
      data: {
        items: [{ medication_name: '伊托必利', actual_dosage: '1粒' }],
        action_pending: true,
      },
      actions: [
        {
          ...policy,
          label: '确认记录',
          action: 'write_intent.confirm',
          endpoint: '/write-intents/42/confirm',
          payload: { write_intent_id: 42 },
          style: 'primary',
        },
        {
          ...policy,
          label: '取消',
          action: 'write_intent.dismiss',
          endpoint: '/write-intents/42/dismiss',
          payload: { write_intent_id: 42 },
        },
      ],
    }, { onAction });

    render(card!);

    expect(screen.getByRole('button', { name: '确认记录' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '取消' })).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent('正在提交');
  });

  it('renders a completed private AIGC image job without exposing provider data', () => {
    const r = renderCard({
      type: 'aigc_media_job',
      data: {
        job_id: 'aigc_1',
        kind: 'text_to_image',
        status: 'succeeded',
        progress: 100,
        result: {
          media_type: 'image/png',
          url: '/api/v1/upload/files/aigc/7/output.png?expires=123&signature=abc',
        },
      },
    });

    const html = renderToStaticMarkup(r!);
    expect(html).toContain('小巴创作');
    expect(html).toContain('已完成');
    expect(html).toContain('/api/v1/upload/files/aigc/7/output.png');
    expect(html).not.toContain('aliyuncs.com');
  });

  it('restores a consumed AIGC confirmation as its existing job on mount', async () => {
    const get = vi.spyOn(api, 'get').mockResolvedValueOnce({
      data: {
        id: 'aigc_confirm_restore',
        status: 'dispatched',
        job: {
          id: 'aigc_restored_1',
          kind: 'text_to_video',
          status: 'failed',
          progress: 0,
          can_retry: true,
          error_message: '创作服务授权异常，已通知管理员。',
        },
      },
    } as never).mockResolvedValueOnce({
      data: {
        id: 'aigc_restored_1',
        kind: 'text_to_video',
        status: 'failed',
        progress: 0,
        can_retry: true,
        error_message: '创作服务授权异常，已通知管理员。',
      },
    } as never);
    const card = renderCard({
      type: 'aigc_media_confirmation',
      data: {
        confirmation_id: 'aigc_confirm_restore',
        kind: 'text_to_video',
        status: 'pending',
      },
    });
    render(card!);

    expect(await screen.findByRole('button', { name: '重试生成' })).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith('/aigc/media/confirmations/aigc_confirm_restore');
    get.mockRestore();
  });

  it('renders an indeterminate AIGC submission without claiming a retryable failure', () => {
    const r = renderCard({
      type: 'aigc_media_job',
      data: {
        job_id: 'aigc_unknown_1',
        kind: 'text_to_video',
        status: 'submission_unknown',
        progress: 0,
        error_message: '提交结果待核验，已停止自动重试以避免重复生成',
      },
    });

    const html = renderToStaticMarkup(r!);
    expect(html).toContain('提交待核验');
    expect(html).toContain('已停止自动重试');
    expect(html).not.toContain('重试生成');
  });

  it('retries a definitively rejected AIGC job in place', async () => {
    const get = vi.spyOn(api, 'get').mockResolvedValueOnce({
      data: {
        id: 'aigc_retry_1',
        kind: 'text_to_video',
        status: 'failed',
        progress: 0,
        can_retry: true,
        error_message: '创作服务授权异常，已通知管理员。',
      },
    } as never);
    const post = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: {
        id: 'aigc_retry_1',
        kind: 'text_to_video',
        status: 'queued',
        progress: 10,
        can_retry: false,
      },
    } as never);
    const card = renderCard({
      type: 'aigc_media_job',
      data: {
        job_id: 'aigc_retry_1',
        kind: 'text_to_video',
        status: 'failed',
        progress: 0,
        can_retry: true,
        error_message: '创作服务授权异常，已通知管理员。',
      },
    });
    render(card!);

    fireEvent.click(screen.getByRole('button', { name: '重试生成' }));

    await waitFor(() => expect(post).toHaveBeenCalledWith('/aigc/media/jobs/aigc_retry_1/retry'));
    expect(await screen.findByText('排队中')).toBeInTheDocument();
    get.mockRestore();
    post.mockRestore();
  });

  it('reveals retry after refreshing a persisted failed job with stale card data', async () => {
    const get = vi.spyOn(api, 'get').mockResolvedValueOnce({
      data: {
        id: 'aigc_stale_1',
        kind: 'text_to_video',
        status: 'failed',
        progress: 0,
        can_retry: true,
        error_message: '创作服务授权异常，已通知管理员。',
      },
    } as never);
    const card = renderCard({
      type: 'aigc_media_job',
      data: {
        job_id: 'aigc_stale_1',
        kind: 'text_to_video',
        status: 'failed',
        progress: 0,
        error_message: '创作服务授权异常，已通知管理员。',
      },
    });
    render(card!);

    expect(await screen.findByRole('button', { name: '重试生成' })).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith('/aigc/media/jobs/aigc_stale_1');
    get.mockRestore();
  });

  it('renders safe route actions below backend cards', () => {
    const r = renderCard({
      type: 'record_quality',
      data: { title: '午餐已记录', summary: '牛肉饭' },
      actions: [
        {
          id: 'open-health-chat',
          label: '打开小巴',
          action: 'route.open',
          payload: { route: '/(tabs)/chat?prompt=test' },
          style: 'primary',
        },
      ],
    });

    const html = renderToStaticMarkup(r!);
    expect(html).toContain('打开小巴');
    expect(html).toContain('/(tabs)/chat?prompt=test');
  });

  it('renders inline next-meal actions as same-page details instead of links', () => {
    const r = renderCard({
      type: 'record_quality',
      data: { title: '午餐已记录', summary: '牛肉饭' },
      actions: [
        {
          id: 'show-next-meal',
          label: '看下一餐建议',
          action: 'ui.inline.expand',
          payload: {
            target: 'next_meal',
            patch: {
              expanded_sections: ['next_meal'],
              next_meal_detail: {
                title: '下一餐建议',
                summary: '晚餐优先补 40g 蛋白。',
                options: ['鱼/豆腐 + 熟蔬菜', '鸡胸 + 南瓜'],
                rationale: ['午餐后蛋白仍有缺口'],
                continue_prompt: '可以继续问小巴：如果只能外卖，怎么选。',
              },
            },
          },
          style: 'primary',
        },
      ],
    });

    const html = renderToStaticMarkup(r!);
    expect(html).toContain('看下一餐建议');
    expect(html).toContain('晚餐优先补 40g 蛋白。');
    expect(html).toContain('鱼/豆腐 + 熟蔬菜');
    expect(html).not.toContain('href=');
  });

  it('filters scheme-relative route actions from backend cards', () => {
    const r = renderCard({
      type: 'record_quality',
      data: { title: '午餐已记录', summary: '牛肉饭' },
      actions: [
        {
          id: 'unsafe',
          label: '外部跳转',
          action: 'route.open',
          payload: { route: '//example.test/path' },
          style: 'primary',
        },
      ],
    });

    const html = renderToStaticMarkup(r!);
    expect(html).not.toContain('外部跳转');
    expect(html).not.toContain('//example.test/path');
  });

  it('cards_group 含 1 张子卡 → 直接渲染, 无 grid wrapper', () => {
    const r = renderCard({
      type: 'cards_group',
      data: { cards: [{ type: 'vitals', data: { sleep: '8h' } }] },
    });
    expect(r).not.toBeNull();
  });

  it('cards_group 含 2 张子卡 → 渲染 grid wrapper', () => {
    const r = renderCard({
      type: 'cards_group',
      data: {
        cards: [
          { type: 'vitals', data: { sleep: '8h' } },
          { type: 'weight', data: { current_kg: 72.1 } },
        ],
      },
    });
    expect(r).not.toBeNull();
    // 应该是个 div with grid classes
    expect(r?.props?.className).toContain('grid');
  });

  it('cards_group 全是未知 type → null', () => {
    const r = renderCard({
      type: 'cards_group',
      data: {
        cards: [
          { type: 'aaa', data: {} },
          { type: 'bbb', data: {} },
        ],
      },
    });
    expect(r).toBeNull();
  });

  it('cards_group 无 data.cards → null', () => {
    const r = renderCard({ type: 'cards_group', data: {} });
    expect(r).toBeNull();
  });
});

// ── renderServerCards ──────────────────────────────────────
describe('renderServerCards', () => {
  it('空 / null / undefined → 空数组', () => {
    expect(renderServerCards()).toEqual([]);
    expect(renderServerCards(null)).toEqual([]);
    expect(renderServerCards([])).toEqual([]);
  });

  it('过滤掉未知 type', () => {
    const r = renderServerCards([
      { type: 'vitals', data: {} },
      {
        type: 'record_quality',
        data: { title: '午餐已记录' },
        actions: [
          {
            id: 'open-health-chat',
            label: '打开小巴',
            action: 'route.open',
            payload: { route: '/(tabs)/chat?prompt=test' },
          },
        ],
      },
      { type: 'fake_type', data: {} },
      { type: 'sleep', data: {} },
    ]);
    expect(r.length).toBe(3);
    expect(r.map((c) => c.type)).toEqual(['vitals', 'record_quality', 'sleep']);
    expect(r[1].actions?.[0]).toEqual(expect.objectContaining({ action: 'route.open' }));
  });

  it('非数组输入 → 空数组 (防御 e.reduce is not a function 类 bug)', () => {
    // @ts-expect-error 故意传错类型
    expect(renderServerCards({} as any)).toEqual([]);
    // @ts-expect-error
    expect(renderServerCards('string')).toEqual([]);
  });

  it('过滤掉缺 type 的项', () => {
    const r = renderServerCards([
      { type: 'vitals', data: {} },
      { data: {} } as any,
      null as any,
    ]);
    expect(r.length).toBe(1);
  });
});
