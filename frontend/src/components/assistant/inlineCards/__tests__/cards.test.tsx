/**
 * Cards spec match() 边界测试
 *
 * 重点测各 spec 的 match 函数, 确保:
 *   - 关键词触发正确
 *   - 记录意图不会被分析卡截胡
 *   - 优先级符合预期
 */
// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest';
import {
  VitalsCardSpec, SleepCardSpec, WeightCardSpec, BPCardSpec,
  SupplementCardSpec, WeatherCardSpec, ScoreCardSpec, RecordCardSpec, DietCardSpec,
} from '../cards';
import type { CardContext } from '../types';

const mkCtx = (q: string, over?: Partial<CardContext>): CardContext => ({
  query: q,
  query_lower: q.toLowerCase(),
  toolsUsed: new Set(),
  data: {},
  api: { get: vi.fn(), post: vi.fn() },
  ...over,
});

describe('SleepCardSpec.match', () => {
  it('"睡眠如何" → 20', () => expect(SleepCardSpec.match(mkCtx('睡眠如何'))).toBe(20));
  it('"REM 比例" → 20', () => expect(SleepCardSpec.match(mkCtx('REM 比例怎样'))).toBe(20));
  it('"记录睡眠时长" 是记录意图 → null', () => expect(SleepCardSpec.match(mkCtx('记录睡眠时长'))).toBeNull());
  it('无关键词 → null', () => expect(SleepCardSpec.match(mkCtx('天气怎么样'))).toBeNull());
});

describe('WeightCardSpec.match', () => {
  it('"体重多少" → 15', () => expect(WeightCardSpec.match(mkCtx('体重多少'))).toBe(15));
  it('"减肥进度" → 15', () => expect(WeightCardSpec.match(mkCtx('减肥进度'))).toBe(15));
  it('"记录体重" 不带"现在/趋势" → null (走 RecordCard)', () => expect(WeightCardSpec.match(mkCtx('记录体重'))).toBeNull());
  it('"记录我现在的体重" 含 "现在" → 15 (允许)', () => expect(WeightCardSpec.match(mkCtx('记录我现在的体重'))).toBe(15));
});

describe('BPCardSpec.match', () => {
  it('"血压" → 15', () => expect(BPCardSpec.match(mkCtx('血压'))).toBe(15));
  it('"我的高压低压" → 15', () => expect(BPCardSpec.match(mkCtx('我的高压低压'))).toBe(15));
  it('无关键词 → null', () => expect(BPCardSpec.match(mkCtx('心率'))).toBeNull());
});

describe('BPCardSpec.build', () => {
  it('uses the server category, color, and severe-reading guidance from the latest record', async () => {
    const api = { get: vi.fn().mockResolvedValue({ data: [{
      systolic: 185,
      diastolic: 85,
      pulse: 72,
      record_date: '2026-07-18',
      category: '血压严重升高',
      category_color: '#B42318',
      safety_guidance: {
        severity: 'high',
        recheck_instruction: '请静坐至少 1 分钟后复测。',
        emergency_instruction: '若同时出现胸痛，请立即拨打急救电话。',
        action_path: '/blood-pressure',
      },
    }] }) };

    const card = await BPCardSpec.build(mkCtx('血压', { api }));

    expect(api.get).toHaveBeenCalledWith('/blood-pressure/records/me', { params: { limit: 1 } });
    expect(card).toMatchObject({
      category: '血压严重升高',
      category_color: '#B42318',
      safety_guidance: { severity: 'high', action_path: '/blood-pressure' },
    });
  });
});

describe('SupplementCardSpec.match', () => {
  it('"补剂吃了吗" → 15', () => expect(SupplementCardSpec.match(mkCtx('补剂吃了吗'))).toBe(15));
  it('"今天吃了什么补剂" → 15', () => expect(SupplementCardSpec.match(mkCtx('今天吃了什么补剂'))).toBe(15));
  it('"补剂列表" → null (具体短语未匹配)', () => expect(SupplementCardSpec.match(mkCtx('补剂列表'))).toBeNull());
});

describe('WeatherCardSpec.match', () => {
  it('"天气怎么样" → 15', () => expect(WeatherCardSpec.match(mkCtx('天气怎么样'))).toBe(15));
  it('"AQI 多少" → 15', () => expect(WeatherCardSpec.match(mkCtx('AQI 多少'))).toBe(15));
  it('"今天适合跑步吗" → 15 (含 "适合跑")', () => expect(WeatherCardSpec.match(mkCtx('今天适合跑步吗'))).toBe(15));
  it('"心情" → null', () => expect(WeatherCardSpec.match(mkCtx('心情'))).toBeNull());
});

describe('DietCardSpec.match', () => {
  it('"我饮食如何" → 18', () => expect(DietCardSpec.match(mkCtx('我饮食如何'))).toBe(18));
  it('"今天热量多少" → 18 (无 "吃了" 关键词)', () => expect(DietCardSpec.match(mkCtx('今天热量多少'))).toBe(18));
  it('"刚吃了苹果" 是记录意图 → null', () => expect(DietCardSpec.match(mkCtx('刚吃了苹果'))).toBeNull());
  it('"记录早餐" 含 "记录" 但无 "饮食"/"吃" → null (走通用 RecordCard)', () => expect(DietCardSpec.match(mkCtx('记录早餐'))).toBeNull());
  // 注意: "今日吃了什么" 含 "吃了", 当前 spec 视为记录意图过滤掉. 是已知设计,
  // 如果希望"询问类"路径覆盖, 需要在 spec 里区分 "吃了什么" (问) vs "刚吃了" (记).
  it('"今日吃了什么" 当前 spec 视为记录意图 → null', () => expect(DietCardSpec.match(mkCtx('今日吃了什么'))).toBeNull());
  it('toolsUsed 含 record_diet → null (让位 RecordCard)', () => {
    const ctx = mkCtx('饮食如何', { toolsUsed: new Set(['record_diet']) });
    expect(DietCardSpec.match(ctx)).toBeNull();
  });
});

describe('ScoreCardSpec.match', () => {
  it('"健康评分" → 15', () => expect(ScoreCardSpec.match(mkCtx('健康评分'))).toBe(15));
  it('"我健康分多少" → 15 (含 "健康分")', () => expect(ScoreCardSpec.match(mkCtx('我健康分多少'))).toBe(15));
  it('"我多少分" 不含完整关键词 → null', () => expect(ScoreCardSpec.match(mkCtx('我多少分'))).toBeNull());
});

describe('VitalsCardSpec.match (兜底)', () => {
  it('"健康如何" → 10', () => expect(VitalsCardSpec.match(mkCtx('健康如何'))).toBe(10));
  it('"睡眠 + 心率" 多关键词 → 8', () => expect(VitalsCardSpec.match(mkCtx('我的睡眠和心率'))).toBe(8));
  it('单关键词 (光"心率") → null (优先级低于 8)', () => expect(VitalsCardSpec.match(mkCtx('心率'))).toBeNull());
  it('记录意图 → null', () => expect(VitalsCardSpec.match(mkCtx('记录心率'))).toBeNull());
});

describe('RecordCardSpec.match', () => {
  it('toolsUsed 含 health_record → 20 (最高优先级)', () => {
    const ctx = mkCtx('随便', { toolsUsed: new Set(['health_record']) });
    expect(RecordCardSpec.match(ctx)).toBe(20);
  });
  it('"刚喝了水" → 12', () => expect(RecordCardSpec.match(mkCtx('刚喝了水'))).toBe(12));
  it('"喷嚏 +1" → 12', () => expect(RecordCardSpec.match(mkCtx('喷嚏'))).toBe(12));
});

// ── build() 边界 ─────────────────────────────────────────
describe('SleepCardSpec.build', () => {
  it('garmin null → null', async () => {
    const r = await SleepCardSpec.build(mkCtx('睡眠'));
    expect(r).toBeNull();
  });

  it('garmin 有 sleep_score → 返回 score', async () => {
    const r = await SleepCardSpec.build(mkCtx('睡眠', {
      data: { garmin: { sleep_score: 88, total_sleep_duration: 480 } },
    }));
    expect(r).not.toBeNull();
    expect((r as any).score).toBe(88);
    expect((r as any).duration_h).toBe(8); // 480/60
  });
});

describe('WeightCardSpec.build', () => {
  it('API 返回空数组 → null', async () => {
    const api = { get: vi.fn().mockResolvedValue({ data: [] }) };
    const r = await WeightCardSpec.build(mkCtx('体重', { api }));
    expect(r).toBeNull();
  });

  it('API 返回 1 条 → current_kg, 无 trend', async () => {
    const api = { get: vi.fn().mockResolvedValue({
      data: [{ record_date: '2026-04-25', weight_kg: 72.5 }],
    }) };
    const r = await WeightCardSpec.build(mkCtx('体重', { api }));
    expect((r as any).current_kg).toBe(72.5);
    expect((r as any).change_7d_kg).toBeUndefined();
  });

  it('API 返回 7 条 → 计算 7 天变化', async () => {
    const records = [
      { record_date: '2026-04-19', weight_kg: 75.0 },
      { record_date: '2026-04-20', weight_kg: 74.5 },
      { record_date: '2026-04-25', weight_kg: 72.0 },
    ];
    const api = { get: vi.fn().mockResolvedValue({ data: records }) };
    const r = await WeightCardSpec.build(mkCtx('体重', { api }));
    expect((r as any).current_kg).toBe(72.0);
    expect((r as any).change_7d_kg).toBe(-3.0);
  });

  it('API 抛错 → null (不崩溃)', async () => {
    const api = { get: vi.fn().mockRejectedValue(new Error('net')) };
    const r = await WeightCardSpec.build(mkCtx('体重', { api }));
    expect(r).toBeNull();
  });
});

describe('VitalsCardSpec.build', () => {
  it('garmin 全空 + score 也无 → null', async () => {
    const r = await VitalsCardSpec.build(mkCtx('健康如何'));
    expect(r).toBeNull();
  });

  it('只有 score 也能 fallback', async () => {
    const r = await VitalsCardSpec.build(mkCtx('健康如何', {
      data: { score: { total_score: 75 } },
    }));
    expect(r).not.toBeNull();
    expect((r as any).sleep).toContain('评分75');
  });

  it('完整 garmin 数据 → 全字段填充', async () => {
    const r = await VitalsCardSpec.build(mkCtx('健康如何', {
      data: {
        garmin: {
          total_sleep_duration: 432, // 7.2h
          resting_heart_rate: 52,
          hrv: 65.4,
          body_battery_most_charged: 82,
          steps: 8500,
          average_stress_level: 28,
        },
      },
    }));
    expect((r as any).sleep).toBe('7.2h');
    expect((r as any).hr).toBe('52bpm');
    expect((r as any).hrv).toBe('65.4ms');
    expect((r as any).battery).toBe('82');
    expect((r as any).steps).toBe('8,500');
    expect((r as any).stress).toBe('28');
  });
});

describe('DietCardSpec.build', () => {
  it('API 返回 null → null', async () => {
    const api = { get: vi.fn().mockResolvedValue({ data: null }) };
    const r = await DietCardSpec.build(mkCtx('饮食如何', { api }));
    expect(r).toBeNull();
  });

  it('API 返回汇总 → 解析 + 按 meal_type 分组', async () => {
    const api = {
      get: vi.fn().mockResolvedValue({
        data: {
          total_calories: 2000, total_protein: 100, total_carbs: 250,
          total_fat: 70, total_fiber: 30, meals_count: 4,
          meals: [
            { meal_type: 'breakfast', calories: 400 },
            { meal_type: 'lunch', calories: 700 },
            { meal_type: 'dinner', calories: 600 },
            { meal_type: 'snack', calories: 300 },
          ],
        },
      }),
    };
    const r = await DietCardSpec.build(mkCtx('饮食如何', { api }));
    expect((r as any).calories).toBe(2000);
    expect((r as any).meals_by_type).toEqual({
      breakfast: 400, lunch: 700, dinner: 600, snack: 300,
    });
  });

  it('meals 缺 meal_type → 默认归 snack', async () => {
    const api = {
      get: vi.fn().mockResolvedValue({
        data: {
          total_calories: 200, meals_count: 1,
          meals: [{ calories: 200 }],
        },
      }),
    };
    const r = await DietCardSpec.build(mkCtx('饮食如何', { api }));
    expect((r as any).meals_by_type).toEqual({ snack: 200 });
  });
});
