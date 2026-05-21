/**
 * appleHealth.ts 单测
 *
 * 重点测 mapSourceNameToDataSource — 这是最可能需要回头补字典的逻辑,
 * 真机出现新 bundle id 时只要加一行,有这个测试就能立刻验证。
 *
 * fetchDailyAggregates / backfillAll 等异步 API 交互逻辑用最小 mock 验证
 * SpO2 转换、睡眠过滤、批量上传错误兜底。
 */
jest.mock('../api', () => ({
  __esModule: true,
  default: { post: jest.fn() },
}));

jest.mock('react-native-health', () => {
  const mock: any = {
    Constants: {
      Permissions: {
        Steps: 'Steps',
        StepCount: 'StepCount',
        HeartRate: 'HeartRate',
        RestingHeartRate: 'RestingHeartRate',
        HeartRateVariability: 'HeartRateVariability',
        OxygenSaturation: 'OxygenSaturation',
        SleepAnalysis: 'SleepAnalysis',
        ActiveEnergyBurned: 'ActiveEnergyBurned',
        BasalEnergyBurned: 'BasalEnergyBurned',
        RespiratoryRate: 'RespiratoryRate',
        BodyTemperature: 'BodyTemperature',
        Vo2Max: 'Vo2Max',
        Weight: 'Weight',
        WaistCircumference: 'WaistCircumference',
      },
    },
    initHealthKit: jest.fn((_p: any, cb: (e: string) => void) => cb('')),
    getDailyStepCountSamples: jest.fn((_o: any, cb: any) => cb('', [])),
    getRestingHeartRateSamples: jest.fn((_o: any, cb: any) => cb('', [])),
    getHeartRateVariabilitySamples: jest.fn((_o: any, cb: any) => cb('', [])),
    getOxygenSaturationSamples: jest.fn((_o: any, cb: any) => cb('', [])),
    getSleepSamples: jest.fn((_o: any, cb: any) => cb('', [])),
    getActiveEnergyBurned: jest.fn((_o: any, cb: any) => cb('', [])),
    getBasalEnergyBurned: jest.fn((_o: any, cb: any) => cb('', [])),
    getRespiratoryRateSamples: jest.fn((_o: any, cb: any) => cb('', [])),
    getBodyTemperatureSamples: jest.fn((_o: any, cb: any) => cb('', [])),
    getVo2MaxSamples: jest.fn((_o: any, cb: any) => cb('', [])),
    getHeartRateSamples: jest.fn((_o: any, cb: any) => cb('', [])),
    getWeightSamples: jest.fn((_o: any, cb: any) => cb('', [])),
    getWaistCircumferenceSamples: jest.fn((_o: any, cb: any) => cb('', [])),
  };
  return { __esModule: true, default: mock, ...mock };
});

import api from '../api';
import AppleHealthKit from 'react-native-health';
import {
  mapSourceNameToDataSource,
  fetchDailyAggregates,
  isHealthKitAvailable,
  syncRecentDays,
} from '../appleHealth';

const mockHK: any = AppleHealthKit;

describe('mapSourceNameToDataSource', () => {
  it('精确匹配 6 种已知 bundle id', () => {
    expect(mapSourceNameToDataSource('com.apple.health')).toBe('apple-watch');
    expect(mapSourceNameToDataSource('com.apple.healthd')).toBe('apple-watch');
    expect(mapSourceNameToDataSource('com.ringconn.app')).toBe('ringconn');
    expect(mapSourceNameToDataSource('com.ouraring.oura')).toBe('oura');
    expect(mapSourceNameToDataSource('com.withings.wiScaleNG')).toBe('withings-app');
    expect(mapSourceNameToDataSource('com.garmin.connect.mobile')).toBe('garmin-app');
  });

  it('显示名 fallback (用户给设备命名带中文/姓名)', () => {
    expect(mapSourceNameToDataSource('刘磊的 Apple Watch')).toBe('apple-watch');
    expect(mapSourceNameToDataSource("Liqiuhua's Apple Watch Ultra")).toBe('apple-watch');
    expect(mapSourceNameToDataSource('刘磊的 iPhone')).toBe('apple-watch');
    expect(mapSourceNameToDataSource('RingConn Smart Ring')).toBe('ringconn');
    expect(mapSourceNameToDataSource('Oura Ring')).toBe('oura');
    expect(mapSourceNameToDataSource('Withings Body+')).toBe('withings-app');
    expect(mapSourceNameToDataSource('Garmin Connect')).toBe('garmin-app');
  });

  it('未知 bundle id 落 unknown 而不是抛错', () => {
    expect(mapSourceNameToDataSource('com.fitbit.FitbitMobile')).toBe('unknown');
    expect(mapSourceNameToDataSource('com.somerandom.app')).toBe('unknown');
  });

  it('空 / undefined 返回 unknown', () => {
    expect(mapSourceNameToDataSource(undefined)).toBe('unknown');
    expect(mapSourceNameToDataSource('')).toBe('unknown');
  });

  it('精确匹配优先于 fallback regex (大小写敏感)', () => {
    // com.apple.Health 精确命中,虽然 regex 也会 match
    expect(mapSourceNameToDataSource('com.apple.Health')).toBe('apple-watch');
    expect(mapSourceNameToDataSource('com.ringconn.RingConn')).toBe('ringconn');
  });
});

describe('isHealthKitAvailable', () => {
  it('iOS 上 true', () => {
    // jest-expo 默认 Platform.OS === 'ios'
    expect(isHealthKitAvailable()).toBe(true);
  });
});

describe('fetchDailyAggregates', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // 默认所有指标返回空数组
    Object.entries(mockHK).forEach(([k, fn]: [string, any]) => {
      if (typeof fn === 'function' && k.startsWith('get')) {
        fn.mockImplementation((_o: any, cb: any) => cb('', []));
      }
    });
  });

  it('SpO2 HealthKit 0-1 小数转 0-100 百分数', async () => {
    mockHK.getOxygenSaturationSamples.mockImplementation((_o: any, cb: any) =>
      cb('', [
        { value: 0.97, sourceName: 'com.apple.health', startDate: '2026-05-20T03:00:00Z', endDate: '2026-05-20T03:00:00Z' },
        { value: 0.95, sourceName: 'com.apple.health', startDate: '2026-05-20T04:00:00Z', endDate: '2026-05-20T04:00:00Z' },
      ]),
    );
    const rec = await fetchDailyAggregates(new Date('2026-05-20T12:00:00Z'));
    // avg(0.97, 0.95) * 100 = 96
    expect(rec.spo2_avg).toBeCloseTo(96, 1);
    expect(rec.spo2_min).toBeCloseTo(95, 1);
  });

  it('sleep 只统计 ASLEEP/CORE/DEEP/REM,跳过 INBED/AWAKE', async () => {
    const day = new Date('2026-05-20T12:00:00Z');
    mockHK.getSleepSamples.mockImplementation((_o: any, cb: any) =>
      cb('', [
        // 1 小时 INBED — 不计
        { value: 'INBED', startDate: '2026-05-20T22:00:00Z', endDate: '2026-05-20T23:00:00Z', sourceName: 'com.apple.health' },
        // 2 小时 CORE — 计
        { value: 'CORE', startDate: '2026-05-20T23:00:00Z', endDate: '2026-05-21T01:00:00Z', sourceName: 'com.apple.health' },
        // 1 小时 REM — 计
        { value: 'REM', startDate: '2026-05-21T01:00:00Z', endDate: '2026-05-21T02:00:00Z', sourceName: 'com.apple.health' },
        // 30 分钟 AWAKE — 不计
        { value: 'AWAKE', startDate: '2026-05-21T02:00:00Z', endDate: '2026-05-21T02:30:00Z', sourceName: 'com.apple.health' },
      ]),
    );
    const rec = await fetchDailyAggregates(day);
    expect(rec.sleep_hours).toBeCloseTo(3, 1);
  });

  it('无样本返回 unknown source 和大部分字段 undefined', async () => {
    const rec = await fetchDailyAggregates(new Date('2026-05-20T12:00:00Z'));
    expect(rec.data_source).toBe('unknown');
    expect(rec.steps).toBeUndefined();
    expect(rec.spo2_avg).toBeUndefined();
    expect(rec.sleep_hours).toBeUndefined();
  });

  it('多源样本按多数派定 data_source', async () => {
    // 5 个 ringconn HRV + 1 个 apple-watch HRV → ringconn 胜
    mockHK.getHeartRateVariabilitySamples.mockImplementation((_o: any, cb: any) =>
      cb('', [
        { value: 50, sourceName: 'com.ringconn.app', startDate: '2026-05-20T01:00:00Z', endDate: '2026-05-20T01:00:00Z' },
        { value: 51, sourceName: 'com.ringconn.app', startDate: '2026-05-20T02:00:00Z', endDate: '2026-05-20T02:00:00Z' },
        { value: 52, sourceName: 'com.ringconn.app', startDate: '2026-05-20T03:00:00Z', endDate: '2026-05-20T03:00:00Z' },
        { value: 49, sourceName: 'com.ringconn.app', startDate: '2026-05-20T04:00:00Z', endDate: '2026-05-20T04:00:00Z' },
        { value: 53, sourceName: 'com.ringconn.app', startDate: '2026-05-20T05:00:00Z', endDate: '2026-05-20T05:00:00Z' },
        { value: 48, sourceName: 'com.apple.health', startDate: '2026-05-20T06:00:00Z', endDate: '2026-05-20T06:00:00Z' },
      ]),
    );
    const rec = await fetchDailyAggregates(new Date('2026-05-20T12:00:00Z'));
    expect(rec.data_source).toBe('ringconn');
  });

  it('聚合 HealthKit 体重和腰围样本供设备优先同步', async () => {
    mockHK.getWeightSamples.mockImplementation((_o: any, cb: any) =>
      cb('', [
        { value: 82.4, sourceName: 'com.withings.wiScaleNG', startDate: '2026-05-20T06:30:00Z', endDate: '2026-05-20T06:30:00Z' },
      ]),
    );
    mockHK.getWaistCircumferenceSamples.mockImplementation((_o: any, cb: any) =>
      cb('', [
        { value: 91.2, sourceName: 'com.ringconn.app', startDate: '2026-05-20T06:31:00Z', endDate: '2026-05-20T06:31:00Z' },
      ]),
    );

    const rec = await fetchDailyAggregates(new Date('2026-05-20T12:00:00Z'));

    expect(rec.weight_kg).toBeCloseTo(82.4, 1);
    expect(rec.waist_cm).toBeCloseTo(91.2, 1);
  });
});

describe('syncRecentDays', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    Object.entries(mockHK).forEach(([k, fn]: [string, any]) => {
      if (typeof fn === 'function' && k.startsWith('get')) {
        fn.mockImplementation((_o: any, cb: any) => cb('', []));
      }
    });
  });

  it('POST 失败时不抛, errors 累加', async () => {
    (api.post as jest.Mock).mockRejectedValueOnce({
      response: { data: { detail: '500 internal' } },
    });
    const result = await syncRecentDays(3);
    expect(result.totalImported).toBe(0);
    expect(result.errors).toContain('500 internal');
  });

  it('POST 成功时返回 imported_count', async () => {
    (api.post as jest.Mock).mockResolvedValueOnce({
      data: { imported_count: 3, source_breakdown: { 'apple-watch': 3 }, errors: [] },
    });
    const result = await syncRecentDays(3);
    expect(result.totalImported).toBe(3);
    expect(result.errors).toEqual([]);
  });

  it('同步 HealthKit 体重腰围到一屏录入同源 API', async () => {
    mockHK.getWeightSamples.mockImplementation((_o: any, cb: any) =>
      cb('', [{ value: 82.4, sourceName: 'com.withings.wiScaleNG', startDate: new Date().toISOString(), endDate: new Date().toISOString() }]),
    );
    mockHK.getWaistCircumferenceSamples.mockImplementation((_o: any, cb: any) =>
      cb('', [{ value: 91.2, sourceName: 'com.ringconn.app', startDate: new Date().toISOString(), endDate: new Date().toISOString() }]),
    );
    (api.post as jest.Mock).mockResolvedValue({ data: { imported_count: 1, source_breakdown: {}, errors: [] } });

    await syncRecentDays(1);

    expect(api.post).toHaveBeenCalledWith('/weight/records', expect.objectContaining({
      weight: 82.4,
      notes: 'HealthKit 自动同步',
    }));
    expect(api.post).toHaveBeenCalledWith('/waist/records', expect.objectContaining({
      waist_cm: 91.2,
      source: 'apple_health',
      notes: 'HealthKit 自动同步',
    }));
  });
});
