/**
 * Apple HealthKit 集成
 *
 * 通过 react-native-health 读取 iPhone HealthKit 中的健康数据,
 * 按天聚合为 NormalizedHealthData 后 POST /devices/healthkit/import.
 *
 * data_source 由每条样本的 sourceName (iOS bundle id) 映射决定 —
 * 同一天可能多源,按样本数多数派选定。
 */
import { Platform, NativeModules } from 'react-native';
import ReactNativeHealth, {
  type HealthKitPermissions,
  type HealthInputOptions,
  type HealthValue,
  type HealthUnit,
} from 'react-native-health';
import api from './api';
import type { components } from '../types/api.generated';

// 契约护栏:import 出口 payload 显式标注为后端 OpenAPI 生成的 schema。
// 后端改名/删字段(如历史上 sleep_hours→total_sleep_minutes)→ 下面 toApiRecord
// 的对象字面量 excess-property 检查直接让 tsc 红,不再静默丢字段。
// 注:float→int 是运行时值问题(TS 只有 number),由客户端 round + 后端 validator 兜,
// 这层专抓"名字/结构漂移"。
type ApiHealthKitRecord = components['schemas']['HealthKitDailyRecord'];

type AppleHealthKitModule = typeof ReactNativeHealth & Record<string, any>;

const NativeAppleHealthKit = NativeModules.AppleHealthKit as AppleHealthKitModule | undefined;
const ReactNativeAppleHealthKit = ReactNativeHealth as AppleHealthKitModule;

/*
 * react-native-health 1.19 的默认 export 通过 Object.assign({}, NativeModules.AppleHealthKit, {Constants})
 * 构造。在 RN 0.83 bridgeless/TurboModule 下，native proxy 方法可能不是 own enumerable，
 * Object.assign 会丢失 initHealthKit/getXxxSamples。生产优先从 NativeModules 取方法；
 * Jest/旧桥 fallback 到默认 export。Constants 仍复用库公开的默认 export。
 */
const AppleHealthKit = new Proxy((NativeAppleHealthKit ?? ReactNativeAppleHealthKit) as AppleHealthKitModule, {
  get(target, prop: string | symbol) {
    if (prop === 'Constants') {
      return ReactNativeAppleHealthKit.Constants;
    }
    if (typeof prop === 'symbol') {
      return Reflect.get(target, prop);
    }
    return target?.[prop] ?? ReactNativeAppleHealthKit?.[prop];
  },
});

if (__DEV__ && Platform.OS === 'ios') {
  // eslint-disable-next-line no-console
  console.log(
    '[appleHealth][diag] native module:',
    !!NativeAppleHealthKit,
    'initHealthKit:',
    typeof AppleHealthKit.initHealthKit,
  );
}

// ── Types ────────────────────────────────────────────────────────────────────
export type DataSource =
  | 'apple-watch'
  | 'ringconn'
  | 'oura'
  | 'withings-app'
  | 'garmin-app'
  | 'manual'
  | 'unknown';

export interface HealthKitDailyRecord {
  record_date: string; // YYYY-MM-DD
  data_source: DataSource;
  steps?: number;
  resting_heart_rate?: number;
  hrv?: number;
  spo2_avg?: number;
  spo2_min?: number;
  // 睡眠按后端契约发分钟分期。后端 HealthKitDailyRecord 只认 total_sleep_minutes
  // 等字段;历史上 mobile 发的 sleep_hours 会被 Pydantic 静默丢弃 → 睡眠永不入库。
  total_sleep_minutes?: number;
  deep_sleep_minutes?: number;
  rem_sleep_minutes?: number;
  light_sleep_minutes?: number;
  active_calories?: number;
  basal_calories?: number;
  respiration_rate_min?: number;
  respiration_rate_max?: number;
  body_temp_deviation_c?: number;
  vo2_max?: number;
  weight_kg?: number;
  waist_cm?: number;
}

export interface BackfillProgress {
  currentMonth: string; // YYYY-MM
  totalMonths: number;
  monthsDone: number;
  importedCount: number;
  errors: string[];
}

interface SampleWithSource extends HealthValue {
  sourceName?: string;
  sourceId?: string;
}

// ── Source name → data_source 映射 ────────────────────────────────────────────
// HealthKit sourceName 是 iOS App 的 bundle id (大小写敏感)。
// 未知 bundle id 落 'unknown',logger.warning 后续补字典。
const SOURCE_NAME_MAP: Record<string, DataSource> = {
  // Apple 系
  'com.apple.health': 'apple-watch',
  'com.apple.Health': 'apple-watch',
  'com.apple.healthd': 'apple-watch',
  // 戒指
  'com.ringconn.app': 'ringconn',
  'com.ringconn.RingConn': 'ringconn',
  'com.ouraring.oura': 'oura',
  'com.ouraring.Oura': 'oura',
  // 智能秤 / 第三方
  'com.withings.wiScaleNG': 'withings-app',
  'com.garmin.connect.mobile': 'garmin-app',
};

export function mapSourceNameToDataSource(sourceName?: string): DataSource {
  if (!sourceName) return 'unknown';
  // 精确匹配
  if (SOURCE_NAME_MAP[sourceName]) return SOURCE_NAME_MAP[sourceName];
  // Apple Watch 设备名常以中文 / 用户名出现 (e.g. "刘磊的 Apple Watch")
  if (/Apple\s*Watch/i.test(sourceName)) return 'apple-watch';
  if (/iPhone/i.test(sourceName)) return 'apple-watch'; // 步数等 iPhone 直采 → 计入 apple-watch 桶
  if (/RingConn/i.test(sourceName)) return 'ringconn';
  if (/Oura/i.test(sourceName)) return 'oura';
  if (/Withings/i.test(sourceName)) return 'withings-app';
  if (/Garmin/i.test(sourceName)) return 'garmin-app';
  // 未知 — dev console 打印一次,真机调试时方便看到漏的 bundle id
  if (__DEV__) {
    console.warn(`[appleHealth] unknown sourceName="${sourceName}", falling back to 'unknown'. Add to SOURCE_NAME_MAP if recurring.`);
  }
  return 'unknown';
}

// ── 多源 majority-vote ────────────────────────────────────────────────────────
// 一天内某指标的样本可能来自多源 (Apple Watch + RingConn 同时戴),按样本数定 data_source。
function majoritySource(samples: SampleWithSource[]): DataSource {
  if (samples.length === 0) return 'unknown';
  const counts: Record<string, number> = {};
  for (const s of samples) {
    const ds = mapSourceNameToDataSource(s.sourceName);
    counts[ds] = (counts[ds] ?? 0) + 1;
  }
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  return (sorted[0]?.[0] as DataSource) ?? 'unknown';
}

// ── 权限清单 ─────────────────────────────────────────────────────────────────
const PERMISSIONS: HealthKitPermissions = {
  permissions: {
    read: [
      AppleHealthKit.Constants.Permissions.Steps,
      AppleHealthKit.Constants.Permissions.StepCount,
      AppleHealthKit.Constants.Permissions.HeartRate,
      AppleHealthKit.Constants.Permissions.RestingHeartRate,
      AppleHealthKit.Constants.Permissions.HeartRateVariability,
      AppleHealthKit.Constants.Permissions.OxygenSaturation,
      AppleHealthKit.Constants.Permissions.SleepAnalysis,
      AppleHealthKit.Constants.Permissions.ActiveEnergyBurned,
      AppleHealthKit.Constants.Permissions.BasalEnergyBurned,
      AppleHealthKit.Constants.Permissions.RespiratoryRate,
      AppleHealthKit.Constants.Permissions.BodyTemperature,
      AppleHealthKit.Constants.Permissions.Vo2Max,
      AppleHealthKit.Constants.Permissions.Weight,
      AppleHealthKit.Constants.Permissions.WaistCircumference,
    ],
    write: [],
  },
};

// ── Init / 权限 ──────────────────────────────────────────────────────────────
let initialized = false;

export function isHealthKitAvailable(): boolean {
  return Platform.OS === 'ios';
}

export async function requestPermissions(): Promise<void> {
  if (!isHealthKitAvailable()) {
    throw new Error('HealthKit 仅在 iOS 上可用');
  }
  if (initialized) return;
  return new Promise((resolve, reject) => {
    AppleHealthKit.initHealthKit(PERMISSIONS, (err: string) => {
      if (err) {
        reject(new Error(err));
        return;
      }
      initialized = true;
      resolve();
    });
  });
}

// ── 单类样本 fetch helper ────────────────────────────────────────────────────
function fetchSamples(
  fn: (
    options: HealthInputOptions,
    cb: (err: string, results: HealthValue[]) => void,
  ) => void,
  options: HealthInputOptions,
): Promise<SampleWithSource[]> {
  return new Promise((resolve) => {
    fn(options, (err, results) => {
      if (err || !results) {
        resolve([]);
        return;
      }
      resolve(results as SampleWithSource[]);
    });
  });
}

function fetchSingle(
  fn: (
    options: HealthInputOptions,
    cb: (err: string, results: HealthValue) => void,
  ) => void,
  options: HealthInputOptions,
): Promise<SampleWithSource | null> {
  return new Promise((resolve) => {
    fn(options, (err, result) => {
      if (err || !result) {
        resolve(null);
        return;
      }
      resolve(result as SampleWithSource);
    });
  });
}

// ── 聚合工具 ─────────────────────────────────────────────────────────────────
function avg(samples: SampleWithSource[]): number | undefined {
  if (samples.length === 0) return undefined;
  const total = samples.reduce((s, x) => s + (x.value ?? 0), 0);
  return total / samples.length;
}

function sum(samples: SampleWithSource[]): number | undefined {
  if (samples.length === 0) return undefined;
  return samples.reduce((s, x) => s + (x.value ?? 0), 0);
}

function min(samples: SampleWithSource[]): number | undefined {
  if (samples.length === 0) return undefined;
  return Math.min(...samples.map((x) => x.value ?? Infinity));
}

function max(samples: SampleWithSource[]): number | undefined {
  if (samples.length === 0) return undefined;
  return Math.max(...samples.map((x) => x.value ?? -Infinity));
}

// ── 单日聚合 ─────────────────────────────────────────────────────────────────
export async function fetchDailyAggregates(
  date: Date,
): Promise<HealthKitDailyRecord> {
  const start = new Date(date);
  start.setHours(0, 0, 0, 0);
  const end = new Date(date);
  end.setHours(23, 59, 59, 999);

  const opts: HealthInputOptions = {
    startDate: start.toISOString(),
    endDate: end.toISOString(),
    ascending: true,
    includeManuallyAdded: true,
  };

  const [
    steps,
    rhr,
    hrv,
    spo2,
    sleep,
    activeCal,
    basalCal,
    respRate,
    bodyTemp,
    vo2,
    weight,
    waist,
  ] = await Promise.all([
    fetchSamples(AppleHealthKit.getDailyStepCountSamples, opts),
    fetchSamples(AppleHealthKit.getRestingHeartRateSamples, opts),
    fetchSamples(AppleHealthKit.getHeartRateVariabilitySamples, opts),
    fetchSamples(AppleHealthKit.getOxygenSaturationSamples, {
      ...opts,
      unit: 'percent' as HealthUnit,
    }),
    fetchSamples(AppleHealthKit.getSleepSamples, opts),
    fetchSamples(AppleHealthKit.getActiveEnergyBurned, opts),
    fetchSamples(AppleHealthKit.getBasalEnergyBurned, opts),
    fetchSamples(AppleHealthKit.getRespiratoryRateSamples, opts),
    fetchSamples(AppleHealthKit.getBodyTemperatureSamples, opts),
    fetchSamples(AppleHealthKit.getVo2MaxSamples, opts),
    fetchSamples(AppleHealthKit.getWeightSamples, {
      ...opts,
      unit: 'kg' as HealthUnit,
    }),
    fetchSamples(AppleHealthKit.getWaistCircumferenceSamples, {
      ...opts,
      unit: 'cm' as HealthUnit,
    }),
  ]);

  // sleep 样本是分期片段 (INBED/ASLEEP/CORE/DEEP/REM/AWAKE,见 react-native-health
  // Queries.m)。按后端契约累计各期分钟:DEEP→深睡、REM→REM、CORE→浅睡(core≈light),
  // ASLEEP(旧版未分期)只计入总睡眠。INBED/AWAKE/UNKNOWN 不算睡着。
  let deepMin = 0;
  let remMin = 0;
  let lightMin = 0; // CORE
  let asleepUnspecMin = 0; // 旧 iOS 只给 ASLEEP
  for (const s of sleep as any[]) {
    const min = (new Date(s.endDate).getTime() - new Date(s.startDate).getTime()) / 60_000;
    if (min <= 0) continue;
    switch (s.value) {
      case 'DEEP': deepMin += min; break;
      case 'REM': remMin += min; break;
      case 'CORE': lightMin += min; break;
      case 'ASLEEP': asleepUnspecMin += min; break;
      default: break; // INBED / AWAKE / UNKNOWN 不计
    }
  }
  const totalSleepMin = deepMin + remMin + lightMin + asleepUnspecMin;
  const round = (n: number) => Math.round(n);

  // 多源 majority vote — 用样本最多的一类 (HR / steps) 决定 data_source
  const allSamples = [
    ...steps,
    ...rhr,
    ...hrv,
    ...spo2,
    ...sleep,
    ...activeCal,
    ...basalCal,
    ...respRate,
    ...bodyTemp,
    ...vo2,
    ...weight,
    ...waist,
  ];
  const data_source = majoritySource(allSamples);

  const record_date = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`;

  // SpO2 HealthKit 单位是 0–1 小数,转成 0–100 百分数
  const spo2Avg = avg(spo2);
  const spo2Min = min(spo2);

  // 后端 steps / resting_heart_rate 是 Optional[int],Pydantic v2 拒绝带小数的
  // float(avg(rhr)=52.5 → 整批 422 → 0 导入)。int 目标字段在客户端先取整。
  const intOr = (n: number | undefined) => (n !== undefined ? Math.round(n) : undefined);
  const stepsSum = sum(steps);
  const rhrAvg = avg(rhr);

  return {
    record_date,
    data_source,
    steps: intOr(stepsSum),
    resting_heart_rate: intOr(rhrAvg),
    hrv: avg(hrv),
    spo2_avg: spo2Avg !== undefined ? spo2Avg * 100 : undefined,
    spo2_min: spo2Min !== undefined && spo2Min !== Infinity ? spo2Min * 100 : undefined,
    total_sleep_minutes: totalSleepMin > 0 ? round(totalSleepMin) : undefined,
    deep_sleep_minutes: deepMin > 0 ? round(deepMin) : undefined,
    rem_sleep_minutes: remMin > 0 ? round(remMin) : undefined,
    light_sleep_minutes: lightMin > 0 ? round(lightMin) : undefined,
    active_calories: sum(activeCal),
    basal_calories: sum(basalCal),
    respiration_rate_min: min(respRate),
    respiration_rate_max: max(respRate),
    body_temp_deviation_c: bodyTemp.length > 0 ? avg(bodyTemp) : undefined,
    vo2_max: avg(vo2),
    weight_kg: avg(weight),
    waist_cm: avg(waist),
  };
}

// ── 找最早样本日期 ───────────────────────────────────────────────────────────
async function getEarliestSampleDate(): Promise<Date> {
  // 用心率作为最常见的连续指标探测最早日期 (Apple Watch 戴第一天就有)
  const opts: HealthInputOptions = {
    startDate: new Date('2010-01-01').toISOString(),
    endDate: new Date().toISOString(),
    ascending: true,
    limit: 1,
  };
  const samples = await fetchSamples(AppleHealthKit.getHeartRateSamples, opts);
  if (samples.length > 0) {
    return new Date(samples[0].startDate);
  }
  // fallback: 30 天前
  const fallback = new Date();
  fallback.setDate(fallback.getDate() - 30);
  return fallback;
}

// ── 月份切片 + POST 一批 ─────────────────────────────────────────────────────
const BATCH_LIMIT = 30; // 后端 100,客户端 30 留 buffer

function ymKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function generateMonthRanges(start: Date, end: Date): { start: Date; end: Date; key: string }[] {
  const ranges: { start: Date; end: Date; key: string }[] = [];
  let cursor = new Date(start.getFullYear(), start.getMonth(), 1);
  while (cursor <= end) {
    const monthEnd = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0);
    const sliceEnd = monthEnd > end ? end : monthEnd;
    ranges.push({
      start: new Date(cursor),
      end: sliceEnd,
      key: ymKey(cursor),
    });
    cursor = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1);
  }
  return ranges;
}

// 本地聚合 record(superset)→ 后端 import schema。只挑后端认的字段;
// 名字对齐(active_calories→calories_active);后端没有的(vo2_max / weight_kg /
// waist_cm — 后两者走 /weight、/waist 端点)不发。对象字面量受生成类型约束。
function toApiRecord(r: HealthKitDailyRecord): ApiHealthKitRecord {
  const caloriesTotal =
    r.active_calories !== undefined && r.basal_calories !== undefined
      ? Math.round(r.active_calories + r.basal_calories)
      : undefined;
  return {
    record_date: r.record_date,
    data_source: r.data_source,
    steps: r.steps,
    resting_heart_rate: r.resting_heart_rate,
    hrv: r.hrv,
    spo2_avg: r.spo2_avg,
    spo2_min: r.spo2_min,
    total_sleep_minutes: r.total_sleep_minutes,
    deep_sleep_minutes: r.deep_sleep_minutes,
    rem_sleep_minutes: r.rem_sleep_minutes,
    light_sleep_minutes: r.light_sleep_minutes,
    calories_active: r.active_calories !== undefined ? Math.round(r.active_calories) : undefined,
    calories_total: caloriesTotal,
    respiration_rate_min: r.respiration_rate_min,
    respiration_rate_max: r.respiration_rate_max,
    body_temp_deviation_c: r.body_temp_deviation_c,
  };
}

async function importBatch(records: HealthKitDailyRecord[]): Promise<{
  imported_count: number;
  source_breakdown: Record<string, number>;
  errors: string[];
}> {
  if (records.length === 0) {
    return { imported_count: 0, source_breakdown: {}, errors: [] };
  }
  try {
    const res = await api.post('/v1/devices/healthkit/import', { records: records.map(toApiRecord) });
    return res.data;
  } catch (e: any) {
    return {
      imported_count: 0,
      source_breakdown: {},
      errors: [e?.response?.data?.detail ?? e?.message ?? '上传失败'],
    };
  }
}

async function importBodyMeasurements(records: HealthKitDailyRecord[]): Promise<string[]> {
  const errors: string[] = [];
  for (const record of records) {
    const tasks: Promise<unknown>[] = [];
    if (record.weight_kg != null) {
      tasks.push(api.post('/weight/records', {
        record_date: record.record_date,
        weight: Math.round(record.weight_kg * 10) / 10,
        notes: 'HealthKit 自动同步',
      }));
    }
    if (record.waist_cm != null) {
      tasks.push(api.post('/waist/records', {
        record_date: record.record_date,
        waist_cm: Math.round(record.waist_cm * 10) / 10,
        source: 'apple_health',
        notes: 'HealthKit 自动同步',
      }));
    }
    try {
      await Promise.all(tasks);
    } catch (e: any) {
      errors.push(e?.response?.data?.detail ?? e?.message ?? `${record.record_date}: 体重/腰围上传失败`);
    }
  }
  return errors;
}

// ── 全量回填 ─────────────────────────────────────────────────────────────────
export async function backfillAll(
  onProgress?: (p: BackfillProgress) => void,
): Promise<{ totalImported: number; errors: string[] }> {
  if (!initialized) await requestPermissions();

  const earliest = await getEarliestSampleDate();
  const today = new Date();
  const months = generateMonthRanges(earliest, today);

  let totalImported = 0;
  const allErrors: string[] = [];

  for (let i = 0; i < months.length; i++) {
    const { start, end, key } = months[i];

    // 当月按天采集,串成 records[]
    const records: HealthKitDailyRecord[] = [];
    const cursor = new Date(start);
    while (cursor <= end) {
      try {
        const rec = await fetchDailyAggregates(new Date(cursor));
        // 跳过完全空的 record (整天没数据)
        if (
          rec.steps !== undefined ||
          rec.resting_heart_rate !== undefined ||
          rec.hrv !== undefined ||
          rec.spo2_avg !== undefined ||
          rec.total_sleep_minutes !== undefined
        ) {
          records.push(rec);
        }
      } catch (e: any) {
        allErrors.push(`${cursor.toISOString().slice(0, 10)}: ${e?.message ?? 'fetch 失败'}`);
      }
      cursor.setDate(cursor.getDate() + 1);
    }

    // 批量上传 (BATCH_LIMIT 一批)
    for (let j = 0; j < records.length; j += BATCH_LIMIT) {
      const batch = records.slice(j, j + BATCH_LIMIT);
      const result = await importBatch(batch);
      totalImported += result.imported_count;
      allErrors.push(...result.errors);
    }

    onProgress?.({
      currentMonth: key,
      totalMonths: months.length,
      monthsDone: i + 1,
      importedCount: totalImported,
      errors: allErrors,
    });
  }

  return { totalImported, errors: allErrors };
}

// 本机从 HealthKit 实际读到几天有各项指标 —— 用于诊断:
// 若某项为 0,说明 HealthKit 没给数据(多半权限没勾 / 设备没录,如美版 Apple Watch
// 血氧被禁),而不是后端管线问题。
export interface SyncCoverage {
  days: number;
  steps: number;
  hr: number;
  hrv: number;
  spo2: number;
  sleep: number;
}

export function summarizeCoverage(records: HealthKitDailyRecord[]): SyncCoverage {
  const count = (pred: (r: HealthKitDailyRecord) => boolean) => records.filter(pred).length;
  return {
    days: records.length,
    steps: count((r) => r.steps !== undefined),
    hr: count((r) => r.resting_heart_rate !== undefined),
    hrv: count((r) => r.hrv !== undefined),
    spo2: count((r) => r.spo2_avg !== undefined),
    sleep: count((r) => r.total_sleep_minutes !== undefined),
  };
}

// ── 增量同步 (只取最近 N 天) ──────────────────────────────────────────────────
export async function syncRecentDays(
  days: number = 7,
): Promise<{ totalImported: number; errors: string[]; coverage: SyncCoverage }> {
  if (!initialized) await requestPermissions();

  const records: HealthKitDailyRecord[] = [];
  const today = new Date();
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    try {
      const rec = await fetchDailyAggregates(d);
      records.push(rec);
    } catch (e: any) {
      // ignore single day error
    }
  }

  const coverage = summarizeCoverage(records);
  const result = await importBatch(records);
  const bodyErrors = await importBodyMeasurements(records);
  return {
    totalImported: result.imported_count,
    errors: [...result.errors, ...bodyErrors],
    coverage,
  };
}
