/**
 * appleHealth.ts 单测
 *
 * 重点测 mapSourceNameToDataSource — 这是最可能需要回头补字典的逻辑,
 * 真机出现新 bundle id 时只要加一行,有这个测试就能立刻验证。
 *
 * fetchDailyRecords / backfillAll 等异步 API 交互逻辑用最小 mock 验证
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
        Electrocardiogram: 'Electrocardiogram',
        BloodPressureSystolic: 'BloodPressureSystolic',
        BloodPressureDiastolic: 'BloodPressureDiastolic',
        BodyFatPercentage: 'BodyFatPercentage',
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
    getElectrocardiogramSamples: jest.fn((_o: any, cb: any) => cb('', [])),
    getBodyFatPercentageSamples: jest.fn((_o: any, cb: any) => cb('', [])),
    getBloodPressureSamples: jest.fn((_o: any, cb: any) => cb('', [])),
  };
  return { __esModule: true, default: mock, ...mock };
});

import api from '../api';
import AppleHealthKit from 'react-native-health';
import {
  mapSourceNameToDataSource,
  fetchDailyRecords,
  isHealthKitAvailable,
  syncRecentDays,
  summarizeCoverage,
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

  it('Garmin Connect 的 HealthKit 显示名 "Connect" → garmin-app (回归: 之前落 unknown)', () => {
    // react-native-health 给 Garmin Connect 返回显示名 "Connect"(非 bundle id、
    // 不含 "Garmin"), 精确匹配命中, 不再走正则漏到 unknown。
    expect(mapSourceNameToDataSource('Connect')).toBe('garmin-app');
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

describe('fetchDailyRecords (按源拆分)', () => {
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
    const recs = await fetchDailyRecords(new Date('2026-05-20T12:00:00Z'));
    const rec = recs.find((r) => r.data_source === 'apple-watch');
    expect(rec).toBeDefined();
    // avg(0.97, 0.95) * 100 = 96
    expect(rec!.spo2_avg).toBeCloseTo(96, 1);
    expect(rec!.spo2_min).toBeCloseTo(95, 1);
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
    const recs = await fetchDailyRecords(day);
    const rec = recs.find((r) => r.data_source === 'apple-watch');
    expect(rec).toBeDefined();
    // CORE 2h→浅睡 120,REM 1h→60,DEEP 0;总 180 分钟(按后端契约发分钟)
    expect(rec!.total_sleep_minutes).toBe(180);
    expect(rec!.light_sleep_minutes).toBe(120);
    expect(rec!.rem_sleep_minutes).toBe(60);
    expect(rec!.deep_sleep_minutes).toBeUndefined();
  });

  it('整天无样本 → 返回空数组 (不产出任何源记录)', async () => {
    const recs = await fetchDailyRecords(new Date('2026-05-20T12:00:00Z'));
    expect(recs).toHaveLength(0);
  });

  it('多源样本按源各产出一条 (RingConn 与 Apple Watch 分开,不再 majority 揉合)', async () => {
    // 5 个 ringconn HRV + 1 个 apple-watch HRV → 各成一条,值各算各的
    // RNH 原生返回 HRV 单位是**秒**(HKUnit secondUnit),mock 用秒级值
    mockHK.getHeartRateVariabilitySamples.mockImplementation((_o: any, cb: any) =>
      cb('', [
        { value: 0.050, sourceName: 'com.ringconn.app', startDate: '2026-05-20T01:00:00Z', endDate: '2026-05-20T01:00:00Z' },
        { value: 0.051, sourceName: 'com.ringconn.app', startDate: '2026-05-20T02:00:00Z', endDate: '2026-05-20T02:00:00Z' },
        { value: 0.052, sourceName: 'com.ringconn.app', startDate: '2026-05-20T03:00:00Z', endDate: '2026-05-20T03:00:00Z' },
        { value: 0.049, sourceName: 'com.ringconn.app', startDate: '2026-05-20T04:00:00Z', endDate: '2026-05-20T04:00:00Z' },
        { value: 0.053, sourceName: 'com.ringconn.app', startDate: '2026-05-20T05:00:00Z', endDate: '2026-05-20T05:00:00Z' },
        { value: 0.048, sourceName: 'com.apple.health', startDate: '2026-05-20T06:00:00Z', endDate: '2026-05-20T06:00:00Z' },
      ]),
    );
    const recs = await fetchDailyRecords(new Date('2026-05-20T12:00:00Z'));
    const ring = recs.find((r) => r.data_source === 'ringconn');
    const watch = recs.find((r) => r.data_source === 'apple-watch');
    expect(ring).toBeDefined();
    expect(watch).toBeDefined();
    // 秒 → ms(×1000):avg(0.050..0.053)=0.051s → 51ms
    expect(ring!.hrv).toBeCloseTo(51, 1);
    expect(watch!.hrv).toBeCloseTo(48, 1); // 只用 apple-watch 自己的样本
  });

  it('未识别来源:source_name 带原始名 + coverage.unknownSources 暴露', async () => {
    // 模拟 RingConn Gen3 在健康里用了我们字典没有的名字
    mockHK.getHeartRateVariabilitySamples.mockImplementation((_o: any, cb: any) =>
      cb('', [
        { value: 0.050, sourceName: '神秘戒指App', startDate: '2026-05-20T01:00:00Z', endDate: '2026-05-20T01:00:00Z' },
        { value: 0.052, sourceName: '神秘戒指App', startDate: '2026-05-20T02:00:00Z', endDate: '2026-05-20T02:00:00Z' },
      ]),
    );
    const recs = await fetchDailyRecords(new Date('2026-05-20T12:00:00Z'));
    const unk = recs.find((r) => r.data_source === 'unknown');
    expect(unk).toBeDefined();
    expect(unk!.source_name).toBe('神秘戒指App'); // 原始名带出,可上行+展示
    const cov = summarizeCoverage(recs);
    expect(cov.unknownSources).toEqual(['神秘戒指App']);
  });

  it('不同源的体重/腰围拆到各自记录 (withings 秤 vs ringconn)', async () => {
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

    const recs = await fetchDailyRecords(new Date('2026-05-20T12:00:00Z'));
    const scale = recs.find((r) => r.data_source === 'withings-app');
    const ring = recs.find((r) => r.data_source === 'ringconn');
    expect(scale!.weight_kg).toBeCloseTo(82.4, 1);
    expect(scale!.waist_cm).toBeUndefined();
    expect(ring!.waist_cm).toBeCloseTo(91.2, 1);
    expect(ring!.weight_kg).toBeUndefined();
  });
});

describe('ECG (Apple Watch 房颤筛查)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    Object.entries(mockHK).forEach(([k, fn]: [string, any]) => {
      if (typeof fn === 'function' && k.startsWith('get')) {
        fn.mockImplementation((_o: any, cb: any) => cb('', []));
      }
    });
  });

  it('取最近一次 classification + startDate, 统计窗口内房颤次数, 挂 apple-watch 记录', async () => {
    // 需要 apple-watch 有其它指标 → 才会在主循环产出 apple-watch 记录
    mockHK.getRestingHeartRateSamples.mockImplementation((_o: any, cb: any) =>
      cb('', [{ value: 58, sourceName: 'com.apple.health', startDate: '2026-05-20T06:00:00Z', endDate: '2026-05-20T06:00:00Z' }]),
    );
    mockHK.getElectrocardiogramSamples.mockImplementation((_o: any, cb: any) =>
      cb('', [
        { classification: 'SinusRhythm', startDate: '2026-05-20T08:00:00Z', endDate: '2026-05-20T08:00:30Z' },
        { classification: 'AtrialFibrillation', startDate: '2026-05-20T12:00:00Z', endDate: '2026-05-20T12:00:30Z' },
        { classification: 'AtrialFibrillation', startDate: '2026-05-20T18:00:00Z', endDate: '2026-05-20T18:00:30Z' },
      ]),
    );
    const recs = await fetchDailyRecords(new Date('2026-05-20T12:00:00Z'));
    const watch = recs.find((r) => r.data_source === 'apple-watch');
    expect(watch).toBeDefined();
    // 最近一次 = 18:00 的 AtrialFibrillation
    expect(watch!.ecg_classification).toBe('AtrialFibrillation');
    expect(watch!.ecg_recorded_at).toBe('2026-05-20T18:00:00Z');
    // 窗口内 2 次房颤
    expect(watch!.afib_event_count).toBe(2);
  });

  it('当天仅有 ECG (无其它指标) 仍补一条 apple-watch 记录上行', async () => {
    mockHK.getElectrocardiogramSamples.mockImplementation((_o: any, cb: any) =>
      cb('', [
        { classification: 'SinusRhythm', startDate: '2026-05-20T09:00:00Z', endDate: '2026-05-20T09:00:30Z' },
      ]),
    );
    const recs = await fetchDailyRecords(new Date('2026-05-20T12:00:00Z'));
    expect(recs).toHaveLength(1);
    const watch = recs[0];
    expect(watch.data_source).toBe('apple-watch');
    expect(watch.ecg_classification).toBe('SinusRhythm');
    expect(watch.afib_event_count).toBe(0);
  });

  it('无 ECG 数据 → 三字段缺省 (后端 Optional)', async () => {
    mockHK.getRestingHeartRateSamples.mockImplementation((_o: any, cb: any) =>
      cb('', [{ value: 58, sourceName: 'com.apple.health', startDate: '2026-05-20T06:00:00Z', endDate: '2026-05-20T06:00:00Z' }]),
    );
    const recs = await fetchDailyRecords(new Date('2026-05-20T12:00:00Z'));
    const watch = recs.find((r) => r.data_source === 'apple-watch');
    expect(watch).toBeDefined();
    expect(watch!.ecg_classification).toBeUndefined();
    expect(watch!.ecg_recorded_at).toBeUndefined();
    expect(watch!.afib_event_count).toBeUndefined();
  });
});

describe('血压 + 体脂 (身体度量自动化)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    Object.entries(mockHK).forEach(([k, fn]: [string, any]) => {
      if (typeof fn === 'function' && k.startsWith('get')) {
        fn.mockImplementation((_o: any, cb: any) => cb('', []));
      }
    });
  });

  it('血压点事件逐条进数组 (不塞日聚合), 取整 + measured_at = startDate(ISO)', async () => {
    mockHK.getBloodPressureSamples.mockImplementation((_o: any, cb: any) =>
      cb('', [
        {
          bloodPressureSystolicValue: 128.4,
          bloodPressureDiastolicValue: 82.6,
          startDate: '2026-05-20T07:00:00.000Z',
          endDate: '2026-05-20T07:00:00.000Z',
          sourceName: 'com.withings.wiScaleNG',
        },
        {
          bloodPressureSystolicValue: 119,
          bloodPressureDiastolicValue: 78,
          startDate: '2026-05-20T20:00:00.000Z',
          endDate: '2026-05-20T20:00:00.000Z',
          sourceName: 'com.withings.wiScaleNG',
        },
      ]),
    );
    const recs = await fetchDailyRecords(new Date('2026-05-20T12:00:00Z'));
    // 仅有血压 → 补一条 apple-watch 载体记录 (与 ECG 同范式)
    const carrier = recs.find((r) => r.blood_pressure_readings !== undefined);
    expect(carrier).toBeDefined();
    expect(carrier!.blood_pressure_readings).toHaveLength(2);
    // 逐条点事件, 取整, measured_at = startDate
    expect(carrier!.blood_pressure_readings![0]).toEqual({
      systolic: 128,
      diastolic: 83,
      measured_at: '2026-05-20T07:00:00.000Z',
      source: 'com.withings.wiScaleNG',
    });
    expect(carrier!.blood_pressure_readings![1].systolic).toBe(119);
  });

  it('血压坏值 (缺收缩/舒张) 整条丢弃, 不进数组', async () => {
    mockHK.getBloodPressureSamples.mockImplementation((_o: any, cb: any) =>
      cb('', [
        { bloodPressureSystolicValue: 120, bloodPressureDiastolicValue: 80, startDate: '2026-05-20T07:00:00.000Z', endDate: '2026-05-20T07:00:00.000Z' },
        { bloodPressureSystolicValue: null, bloodPressureDiastolicValue: 80, startDate: '2026-05-20T08:00:00.000Z', endDate: '2026-05-20T08:00:00.000Z' },
      ]),
    );
    const recs = await fetchDailyRecords(new Date('2026-05-20T12:00:00Z'));
    const carrier = recs.find((r) => r.blood_pressure_readings !== undefined);
    expect(carrier!.blood_pressure_readings).toHaveLength(1);
  });

  it('体脂 HealthKit 0–1 小数 ×100 成百分数, 随体重落 weight_kg', async () => {
    mockHK.getBodyFatPercentageSamples.mockImplementation((_o: any, cb: any) =>
      cb('', [{ value: 0.182, sourceName: 'com.withings.wiScaleNG', startDate: '2026-05-20T07:00:00Z', endDate: '2026-05-20T07:00:00Z' }]),
    );
    mockHK.getWeightSamples.mockImplementation((_o: any, cb: any) =>
      cb('', [{ value: 80.0, sourceName: 'com.withings.wiScaleNG', startDate: '2026-05-20T07:00:00Z', endDate: '2026-05-20T07:00:00Z' }]),
    );
    const recs = await fetchDailyRecords(new Date('2026-05-20T12:00:00Z'));
    const rec = recs.find((r) => r.body_fat_percentage !== undefined);
    expect(rec).toBeDefined();
    // 0.182 ×100 = 18.2 (百分数), 不是 0.182
    expect(rec!.body_fat_percentage).toBe(18.2);
    expect(rec!.weight_kg).toBe(80.0);
  });

  it('血压/体脂经 toApiRecord 进入 import 出口 payload (体脂随 weight_kg)', async () => {
    mockHK.getBloodPressureSamples.mockImplementation((_o: any, cb: any) =>
      cb('', [{ bloodPressureSystolicValue: 130, bloodPressureDiastolicValue: 85, startDate: '2026-05-20T07:00:00.000Z', endDate: '2026-05-20T07:00:00.000Z', sourceName: 'com.apple.health' }]),
    );
    mockHK.getBodyFatPercentageSamples.mockImplementation((_o: any, cb: any) =>
      cb('', [{ value: 0.2, sourceName: 'com.withings.wiScaleNG', startDate: '2026-05-20T07:00:00Z', endDate: '2026-05-20T07:00:00Z' }]),
    );
    mockHK.getWeightSamples.mockImplementation((_o: any, cb: any) =>
      cb('', [{ value: 75.5, sourceName: 'com.withings.wiScaleNG', startDate: '2026-05-20T07:00:00Z', endDate: '2026-05-20T07:00:00Z' }]),
    );
    (api.post as jest.Mock).mockResolvedValue({ data: { imported_count: 1, source_breakdown: {}, errors: [] } });

    await syncRecentDays(1);

    const importCall = (api.post as jest.Mock).mock.calls.find(([url]) => url === '/devices/healthkit/import');
    expect(importCall).toBeDefined();
    const records = importCall![1].records;
    // 血压挂在 apple-watch 载体上
    const bpRec = records.find((r: any) => r.blood_pressure_readings?.length);
    expect(bpRec.blood_pressure_readings[0]).toEqual({
      systolic: 130, diastolic: 85, measured_at: '2026-05-20T07:00:00.000Z', source: 'com.apple.health',
    });
    // 体脂 + 其载体体重一并上行 (后端要求体脂随体重落库)
    const bfRec = records.find((r: any) => r.body_fat_percentage !== undefined);
    expect(bfRec.body_fat_percentage).toBe(20);
    expect(bfRec.weight_kg).toBe(75.5);
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
    // 需有样本才会产出记录 → 才会触发 import POST(按源拆分后,空天不产记录)
    mockHK.getHeartRateVariabilitySamples.mockImplementation((_o: any, cb: any) =>
      cb('', [{ value: 50, sourceName: 'com.apple.health', startDate: '2026-05-20T03:00:00Z', endDate: '2026-05-20T03:00:00Z' }]),
    );
    (api.post as jest.Mock).mockRejectedValueOnce({
      response: { data: { detail: '500 internal' } },
    });
    const result = await syncRecentDays(3);
    expect(result.totalImported).toBe(0);
    expect(result.errors).toContain('500 internal');
  });

  it('POST 成功时返回 imported_count', async () => {
    mockHK.getHeartRateVariabilitySamples.mockImplementation((_o: any, cb: any) =>
      cb('', [{ value: 50, sourceName: 'com.apple.health', startDate: '2026-05-20T03:00:00Z', endDate: '2026-05-20T03:00:00Z' }]),
    );
    (api.post as jest.Mock).mockResolvedValueOnce({
      data: { imported_count: 3, source_breakdown: { 'apple-watch': 3 }, errors: [] },
    });
    const result = await syncRecentDays(3);
    expect(result.totalImported).toBe(3);
    expect(result.errors).toEqual([]);
  });

  it('ECG 三字段经 toApiRecord 进入 import POST 出口 payload', async () => {
    mockHK.getElectrocardiogramSamples.mockImplementation((_o: any, cb: any) =>
      cb('', [
        { classification: 'AtrialFibrillation', startDate: '2026-05-20T18:00:00Z', endDate: '2026-05-20T18:00:30Z' },
      ]),
    );
    (api.post as jest.Mock).mockResolvedValue({
      data: { imported_count: 1, source_breakdown: {}, errors: [] },
    });
    await syncRecentDays(1);
    const importCall = (api.post as jest.Mock).mock.calls.find(
      ([url]) => url === '/devices/healthkit/import',
    );
    expect(importCall).toBeDefined();
    const posted = importCall![1].records.find((r: any) => r.data_source === 'apple-watch');
    expect(posted.ecg_classification).toBe('AtrialFibrillation');
    expect(posted.ecg_recorded_at).toBe('2026-05-20T18:00:00Z');
    expect(posted.afib_event_count).toBe(1);
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
