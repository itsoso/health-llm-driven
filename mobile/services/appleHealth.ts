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
import AsyncStorage from '@react-native-async-storage/async-storage';
import ReactNativeHealth, {
  type HealthKitPermissions,
  type HealthInputOptions,
  type HealthValue,
  type HealthUnit,
  type ElectrocardiogramSampleValue,
  type BloodPressureSampleValue,
} from 'react-native-health';
import api from './api';

// ── 授权状态持久化 ────────────────────────────────────────────────────────────
// iOS 出于隐私**不暴露 read 授权状态**,且组件 authorized state 重挂载即丢 →
// "授权后仍显示未授权"。这里持久化"是否已授权 + 最近同步时间",挂载时 rehydrate。
// 授权铁证 = 某次同步真读到了数据(见 syncRecentDays 的 coverage)。
const HK_AUTH_FLAG = 'healthkit_authorized_v1';
const HK_LAST_SYNC = 'healthkit_last_sync_v1';

export async function persistHealthKitAuthorized(): Promise<void> {
  try { await AsyncStorage.setItem(HK_AUTH_FLAG, '1'); } catch { /* 存储失败 → 下次同步自愈 */ }
}
export async function getHealthKitAuthorized(): Promise<boolean> {
  try { return (await AsyncStorage.getItem(HK_AUTH_FLAG)) === '1'; } catch { return false; }
}
export async function persistHealthKitLastSync(ts: number): Promise<void> {
  try { await AsyncStorage.setItem(HK_LAST_SYNC, String(ts)); } catch { /* 非关键 */ }
}
export async function getHealthKitLastSync(): Promise<number | null> {
  try { const v = await AsyncStorage.getItem(HK_LAST_SYNC); return v ? Number(v) : null; } catch { return null; }
}
import type { components } from '../types/api.generated';

// 契约护栏:import 出口 payload 显式标注为后端 OpenAPI 生成的 schema。
// 后端改名/删字段(如历史上 sleep_hours→total_sleep_minutes)→ 下面 toApiRecord
// 的对象字面量 excess-property 检查直接让 tsc 红,不再静默丢字段。
// 注:float→int 是运行时值问题(TS 只有 number),由客户端 round + 后端 validator 兜,
// 这层专抓"名字/结构漂移"。
type ApiHealthKitRecord = components['schemas']['HealthKitDailyRecord'];
// 血压点事件出口 payload —— 同样用生成 schema 标注, 防字段漂移。
type ApiBPReading = components['schemas']['BPReadingIn'];
// 整夜逐分钟血氧采样点出口 payload —— 生成 schema 标注, 防字段漂移。
type ApiSpo2Sample = components['schemas']['Spo2SampleIn'];

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
  // data_source='unknown' 时带上原始 HealthKit sourceName(出现最多的那个):
  // 上行后端可走其映射兜底 + warning 日志打出真名(服务器侧可见),
  // 同步弹窗也展示 → 双通道定位"RingConn 在健康里到底叫什么"。
  source_name?: string;
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
  // ECG (Apple Watch 独有). 最近一次分类的原始 HealthKit 字符串 + 记录时间,
  // 加上送窗口内 AtrialFibrillation 次数. 无 ECG 数据时三者均缺省.
  ecg_classification?: string;
  ecg_recorded_at?: string; // ISO 8601, 取自最近一次 sample.startDate
  afib_event_count?: number;
  // 血压点事件 (一天多次, 与 ECG 同范式 —— 逐条进数组, 不塞日聚合).
  // 每条 {systolic, diastolic, measured_at(ISO), source?}; 无数据时缺省.
  blood_pressure_readings?: ApiBPReading[];
  // 整夜逐分钟血氧序列 (RingConn / Apple Watch 等贴肤光路). 每条 {value(0-100), measured_at(ISO)}.
  // 落后端 spo2_samples 表 —— ODI / below-90% 持续负荷的唯一来源 (日聚合 spo2_min 算不出)。
  // 无数据时缺省。
  spo2_samples?: ApiSpo2Sample[];
  // 体脂率 (百分数 0–100, HealthKit 原始 0–1 已 ×100). 随 weight_kg 落 WeightRecord.
  body_fat_percentage?: number;
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
  // Garmin Connect 写 HealthKit 时 sourceName 是显示名 "Connect"(不是 bundle id、
  // 不含 "Garmin")→ 之前漏网落 unknown(生产日志实锤 user3 步数全是 'Connect')。
  'Connect': 'garmin-app',
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

// ── 按源分组 ──────────────────────────────────────────────────────────────────
// 一天内某指标的样本可能来自多源 (Apple Watch + RingConn 同时戴)。不再用 majority-vote
// 把整天揉成一条 (会把 RingConn 的睡眠/血氧/HRV 混进 apple-watch 桶、且永不产出
// data_source="ringconn" 行)。改为按 sourceName 分组,每个源各产出一条记录,
// 值只用该源自己的样本算 —— 后端复合唯一支持一天多行 + 按指标优先级合并。
function samplesForSource(samples: SampleWithSource[], src: DataSource): SampleWithSource[] {
  return samples.filter((s) => mapSourceNameToDataSource(s.sourceName) === src);
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
      // ECG (Apple Watch 房颤筛查信号). 纯运行时读权限 — Info.plist 的
      // NSHealthShareUsageDescription 已覆盖所有 HealthKit 读取, 不需改 native config.
      AppleHealthKit.Constants.Permissions.Electrocardiogram,
      // 血压 (收缩压/舒张压) + 体脂率. 同 ECG, 纯运行时读权限,
      // NSHealthShareUsageDescription 已覆盖, 不需改 native config (可 OTA).
      AppleHealthKit.Constants.Permissions.BloodPressureSystolic,
      AppleHealthKit.Constants.Permissions.BloodPressureDiastolic,
      AppleHealthKit.Constants.Permissions.BodyFatPercentage,
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

// ECG 专用 fetch — 返回类型与通用 fetchSamples (HealthValue[]) 不同, 单列一个.
function fetchEcgSamples(options: HealthInputOptions): Promise<ElectrocardiogramSampleValue[]> {
  return new Promise((resolve) => {
    const fn = AppleHealthKit.getElectrocardiogramSamples as
      | ((
          options: HealthInputOptions,
          cb: (err: string, results: ElectrocardiogramSampleValue[]) => void,
        ) => void)
      | undefined;
    // 旧桥 / Jest mock 可能没这方法 → 安全降级为无 ECG (后端 Optional, 不崩).
    if (typeof fn !== 'function') {
      resolve([]);
      return;
    }
    fn(options, (err, results) => {
      if (err || !results) {
        resolve([]);
        return;
      }
      resolve(results);
    });
  });
}

// 血压样本 = 点事件. 运行时每条带 sourceName (库类型 BloodPressureSampleValue 没声明,
// 本地扩一个). 返回类型与通用 fetchSamples (HealthValue[]) 不同, 单列一个.
type BPSampleWithSource = BloodPressureSampleValue & { sourceName?: string };

function fetchBloodPressureSamples(options: HealthInputOptions): Promise<BPSampleWithSource[]> {
  return new Promise((resolve) => {
    const fn = AppleHealthKit.getBloodPressureSamples as
      | ((
          options: HealthInputOptions,
          cb: (err: string, results: BloodPressureSampleValue[]) => void,
        ) => void)
      | undefined;
    // 旧桥 / Jest mock 可能没这方法 → 安全降级为无血压 (后端 Optional, 不崩).
    if (typeof fn !== 'function') {
      resolve([]);
      return;
    }
    fn(options, (err, results) => {
      if (err || !results) {
        resolve([]);
        return;
      }
      resolve(results as BPSampleWithSource[]);
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
interface MetricSamples {
  steps: SampleWithSource[];
  rhr: SampleWithSource[];
  hrv: SampleWithSource[];
  spo2: SampleWithSource[];
  sleep: SampleWithSource[];
  activeCal: SampleWithSource[];
  basalCal: SampleWithSource[];
  respRate: SampleWithSource[];
  bodyTemp: SampleWithSource[];
  vo2: SampleWithSource[];
  weight: SampleWithSource[];
  waist: SampleWithSource[];
  bodyFat: SampleWithSource[];
}

/** 从「同一个源」的样本束算出一条日记录。纯函数,不读 HealthKit。 */
function buildRecordForSource(
  record_date: string,
  data_source: DataSource,
  m: MetricSamples,
): HealthKitDailyRecord {
  // sleep 分期累计 (DEEP→深睡、REM→REM、CORE→浅睡、ASLEEP→未分期只计总睡)。
  // INBED/AWAKE/UNKNOWN 不算睡着。
  let deepMin = 0;
  let remMin = 0;
  let lightMin = 0; // CORE
  let asleepUnspecMin = 0; // 旧 iOS 只给 ASLEEP
  for (const s of m.sleep as any[]) {
    const mins = (new Date(s.endDate).getTime() - new Date(s.startDate).getTime()) / 60_000;
    if (mins <= 0) continue;
    switch (s.value) {
      case 'DEEP': deepMin += mins; break;
      case 'REM': remMin += mins; break;
      case 'CORE': lightMin += mins; break;
      case 'ASLEEP': asleepUnspecMin += mins; break;
      default: break; // INBED / AWAKE / UNKNOWN 不计
    }
  }
  const totalSleepMin = deepMin + remMin + lightMin + asleepUnspecMin;
  const round = (n: number) => Math.round(n);

  // SpO2 HealthKit 单位是 0–1 小数,转成 0–100 百分数
  const spo2Avg = avg(m.spo2);
  const spo2Min = min(m.spo2);
  // 整夜逐分钟序列: 每个样本各自上行 (value ×100 成百分数 + measured_at ISO)。
  // 这是后端算 ODI / below-90% 持续负荷的唯一来源 —— 日聚合 spo2_min 算不出。
  // 跳过缺 value / startDate 的坏样本; 全空则不带该字段 (后端 Optional)。
  const spo2Samples: ApiSpo2Sample[] = (m.spo2 as SampleWithSource[])
    .filter((s) => s.value != null && s.startDate)
    .map((s) => ({
      value: (s.value as number) * 100,
      measured_at: new Date(s.startDate).toISOString(),
    }));

  // 后端 steps / resting_heart_rate 是 Optional[int],float 会 422 → 客户端先取整。
  const intOr = (n: number | undefined) => (n !== undefined ? Math.round(n) : undefined);

  return {
    record_date,
    data_source,
    steps: intOr(sum(m.steps)),
    resting_heart_rate: intOr(avg(m.rhr)),
    // RNH getHeartRateVariabilitySamples 原生硬用 HKUnit secondUnit(秒),
    // 而全系统(Garmin/DB/Twin)hrv 单位是 ms → 必须 ×1000(踩过:0.0576 入库)。
    hrv: ((s) => (s !== undefined ? Math.round(s * 1000 * 10) / 10 : undefined))(avg(m.hrv)),
    spo2_avg: spo2Avg !== undefined ? spo2Avg * 100 : undefined,
    spo2_min: spo2Min !== undefined && spo2Min !== Infinity ? spo2Min * 100 : undefined,
    spo2_samples: spo2Samples.length > 0 ? spo2Samples : undefined,
    total_sleep_minutes: totalSleepMin > 0 ? round(totalSleepMin) : undefined,
    deep_sleep_minutes: deepMin > 0 ? round(deepMin) : undefined,
    rem_sleep_minutes: remMin > 0 ? round(remMin) : undefined,
    light_sleep_minutes: lightMin > 0 ? round(lightMin) : undefined,
    active_calories: sum(m.activeCal),
    basal_calories: sum(m.basalCal),
    respiration_rate_min: min(m.respRate),
    respiration_rate_max: max(m.respRate),
    body_temp_deviation_c: m.bodyTemp.length > 0 ? avg(m.bodyTemp) : undefined,
    vo2_max: avg(m.vo2),
    weight_kg: avg(m.weight),
    waist_cm: avg(m.waist),
    // HealthKit 体脂率单位是 0–1 小数 (e.g. 0.18) → ×100 成百分数 (18.0),
    // 后端 weight_records.body_fat_percentage 期望百分数 (user_profile ge=1 le=70).
    body_fat_percentage: ((bf) => (bf !== undefined ? Math.round(bf * 100 * 10) / 10 : undefined))(avg(m.bodyFat)),
  };
}

// ── ECG 摘要 ─────────────────────────────────────────────────────────────────
// getElectrocardiogramSamples 每条 = 一次 30s ECG 记录, 形如:
//   { classification: "AtrialFibrillation" | "SinusRhythm" | ..., startDate, endDate,
//     averageHeartRate, samplingFrequency, device, algorithmVersion, voltageMeasurements }
// 取窗口内最近一次的 classification + startDate, 并统计 AtrialFibrillation 次数.
// Apple Watch 独有 → 摘要只挂到 apple-watch 源记录上.
interface EcgSummary {
  classification: string;
  recordedAt: string; // ISO 8601 (最近一次 startDate)
  afibCount: number;
}

function summarizeEcgSamples(samples: ElectrocardiogramSampleValue[]): EcgSummary | null {
  if (!samples || samples.length === 0) return null;
  // 按 startDate 升序排, 取最后一条作"最近一次"; 上游(fetchDailyRecords)虽已 ascending,
  // 但 ECG 走独立调用, 这里自排序不依赖外部顺序.
  const sorted = [...samples].sort(
    (a, b) => new Date(a.startDate).getTime() - new Date(b.startDate).getTime(),
  );
  const latest = sorted[sorted.length - 1];
  const afibCount = sorted.filter((s) => s.classification === 'AtrialFibrillation').length;
  return {
    classification: String(latest.classification),
    recordedAt: latest.startDate,
    afibCount,
  };
}

// ── 血压点事件映射 ───────────────────────────────────────────────────────────
// getBloodPressureSamples 每条 = 一次血压测量, 形如:
//   { bloodPressureSystolicValue, bloodPressureDiastolicValue, startDate, endDate, sourceName? }
// 血压是点事件 (一天可多次) → 逐条映射成 BPReadingIn, 不塞日聚合 (与 ECG 同范式).
// measured_at 取 startDate (后端按 (user_id, measured_at) 去重幂等). source 取 sourceName.
function mapBloodPressureSamples(samples: BPSampleWithSource[]): ApiBPReading[] {
  const out: ApiBPReading[] = [];
  for (const s of samples) {
    const systolic = s.bloodPressureSystolicValue;
    const diastolic = s.bloodPressureDiastolicValue;
    // 任一缺失 → 丢弃该条 (后端坏值也会丢, 但不发更省一趟).
    if (systolic == null || diastolic == null || !s.startDate) continue;
    out.push({
      systolic: Math.round(systolic),
      diastolic: Math.round(diastolic),
      measured_at: new Date(s.startDate).toISOString(),
      source: s.sourceName,
    });
  }
  return out;
}

/** 一条记录是否含任何指标值;全空 (该源当天无数据) 则不产出/不上传。 */
function recordHasData(r: HealthKitDailyRecord): boolean {
  return (
    r.steps !== undefined ||
    r.resting_heart_rate !== undefined ||
    r.hrv !== undefined ||
    r.spo2_avg !== undefined ||
    r.spo2_min !== undefined ||
    r.total_sleep_minutes !== undefined ||
    r.active_calories !== undefined ||
    r.basal_calories !== undefined ||
    r.respiration_rate_min !== undefined ||
    r.body_temp_deviation_c !== undefined ||
    r.vo2_max !== undefined ||
    r.weight_kg !== undefined ||
    r.waist_cm !== undefined ||
    r.ecg_classification !== undefined ||
    r.body_fat_percentage !== undefined ||
    (r.blood_pressure_readings !== undefined && r.blood_pressure_readings.length > 0)
  );
}

/**
 * 读某天 HealthKit,按数据源拆成多条记录 (Apple Watch / RingConn / Withings… 各一条)。
 * 每条只用该源自己的样本算值 —— 这样 RingConn 的睡眠/血氧/HRV 才能以 data_source=
 * "ringconn" 独立上行,被后端 per-source 摘要 + 按指标优先级合并消费。无数据的源不产出。
 */
export async function fetchDailyRecords(date: Date): Promise<HealthKitDailyRecord[]> {
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
    bodyFat,
    bp,
    ecg,
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
    fetchSamples(AppleHealthKit.getBodyFatPercentageSamples, opts),
    fetchBloodPressureSamples(opts),
    fetchEcgSamples(opts),
  ]);

  // ECG 是 Apple Watch 独有, 不参与 per-source 拆分 — 摘要后挂到 apple-watch 记录上.
  const ecgSummary = summarizeEcgSamples(ecg);
  // 血压点事件 (一天多次) — 不参与 per-source 拆分, 逐条进数组挂到单条记录上.
  const bpReadings = mapBloodPressureSamples(bp);

  const record_date = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`;

  const allMetrics = [steps, rhr, hrv, spo2, sleep, activeCal, basalCal, respRate, bodyTemp, vo2, weight, waist, bodyFat];
  const sources = new Set<DataSource>();
  // 未识别来源的原始 sourceName 计数 —— 用于定位"这台设备在健康里叫什么"
  const unknownRawCounts: Record<string, number> = {};
  for (const arr of allMetrics) {
    for (const s of arr) {
      const mapped = mapSourceNameToDataSource(s.sourceName);
      sources.add(mapped);
      if (mapped === 'unknown' && s.sourceName) {
        unknownRawCounts[s.sourceName] = (unknownRawCounts[s.sourceName] ?? 0) + 1;
      }
    }
  }
  const topUnknownRaw = Object.entries(unknownRawCounts).sort((a, b) => b[1] - a[1])[0]?.[0];

  const records: HealthKitDailyRecord[] = [];
  for (const src of sources) {
    const rec = buildRecordForSource(record_date, src, {
      steps: samplesForSource(steps, src),
      rhr: samplesForSource(rhr, src),
      hrv: samplesForSource(hrv, src),
      spo2: samplesForSource(spo2, src),
      sleep: samplesForSource(sleep, src),
      activeCal: samplesForSource(activeCal, src),
      basalCal: samplesForSource(basalCal, src),
      respRate: samplesForSource(respRate, src),
      bodyTemp: samplesForSource(bodyTemp, src),
      vo2: samplesForSource(vo2, src),
      weight: samplesForSource(weight, src),
      waist: samplesForSource(waist, src),
      bodyFat: samplesForSource(bodyFat, src),
    });
    // ECG 只挂 apple-watch 源 (HealthKit 不在 ECG sample 上暴露 sourceName,
    // 且 ECG 仅 Apple Watch 产出). 无 ECG 数据时三字段不填 (后端 Optional).
    if (src === 'apple-watch' && ecgSummary) {
      rec.ecg_classification = ecgSummary.classification;
      rec.ecg_recorded_at = ecgSummary.recordedAt;
      rec.afib_event_count = ecgSummary.afibCount;
    }
    // 血压点事件挂到 apple-watch 记录上 (单条载体即可, 后端按 measured_at 去重
    // 幂等, 不论 data_source). BP 样本的 source 已逐条保留在 reading.source 里.
    if (src === 'apple-watch' && bpReadings.length > 0) {
      rec.blood_pressure_readings = bpReadings;
    }
    if (recordHasData(rec)) {
      if (src === 'unknown' && topUnknownRaw) rec.source_name = topUnknownRaw;
      records.push(rec);
    }
  }

  // 边界情况: 当天有 ECG / 血压 但没产出 apple-watch 记录 (apple-watch 无其它指标).
  // 仍需把 ECG / BP 上行, 否则房颤信号 / 血压点事件丢失. 补一条 apple-watch 记录.
  // (ECG 仅 Apple Watch 产出; BP 用 apple-watch 作单条载体, 后端按 measured_at 去重.)
  if ((ecgSummary || bpReadings.length > 0) && !records.some((r) => r.data_source === 'apple-watch')) {
    const carrier: HealthKitDailyRecord = { record_date, data_source: 'apple-watch' };
    if (ecgSummary) {
      carrier.ecg_classification = ecgSummary.classification;
      carrier.ecg_recorded_at = ecgSummary.recordedAt;
      carrier.afib_event_count = ecgSummary.afibCount;
    }
    if (bpReadings.length > 0) {
      carrier.blood_pressure_readings = bpReadings;
    }
    records.push(carrier);
  }
  return records;
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
// 名字对齐(active_calories→calories_active);后端没有的(vo2_max / waist_cm —
// 走 /waist 端点)不发。weight_kg 平时走 /weight/records 端点,只有在带 body_fat
// 时才随 import 上行(后端 _save_body_composition 要求体脂必须有体重作载体,
// 同 (user_id, record_date) upsert 与 /weight 端点幂等)。对象字面量受生成类型约束。
function toApiRecord(r: HealthKitDailyRecord): ApiHealthKitRecord {
  const caloriesTotal =
    r.active_calories !== undefined && r.basal_calories !== undefined
      ? Math.round(r.active_calories + r.basal_calories)
      : undefined;
  return {
    record_date: r.record_date,
    // unknown 且带原始名 → data_source 发 null,让后端 map_source_name_to_data_source
    // 兜底(后端字典可能更全)并 logger.warning 打出真名 → 服务器日志可定位新设备。
    data_source: r.data_source === 'unknown' && r.source_name ? null : r.data_source,
    source_name: r.source_name,
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
    // ECG — 原样转发 HealthKit 分类字符串 + 记录时间 + 窗口内房颤计数.
    // 无 ECG 时三者 undefined (后端 Optional, 不下发). 对象字面量受 ApiHealthKitRecord
    // 约束 → 后端改名/删字段时这里 tsc 直接红.
    ecg_classification: r.ecg_classification,
    ecg_recorded_at: r.ecg_recorded_at,
    afib_event_count: r.afib_event_count,
    // 血压点事件 — 逐条数组原样转发 (systolic/diastolic 已取整, measured_at ISO).
    // 无血压时 undefined (后端 Optional)。对象字面量受 ApiHealthKitRecord 约束 →
    // 后端改 BPReadingIn 字段时这里 tsc 直接红。
    blood_pressure_readings: r.blood_pressure_readings,
    // 整夜逐分钟血氧序列 — 原样转发 (value 已 ×100, measured_at ISO)。无数据时 undefined。
    // 对象字面量受 ApiHealthKitRecord 约束 → 后端改 Spo2SampleIn 字段时这里 tsc 直接红。
    spo2_samples: r.spo2_samples,
    // 体脂率 (百分数) + 其载体体重。后端要求体脂随体重落库,故仅在有体脂时把
    // weight_kg 一并上行 (round 到 0.1kg); 无体脂则不发 weight_kg (走 /weight 端点)。
    body_fat_percentage: r.body_fat_percentage,
    weight_kg:
      r.body_fat_percentage !== undefined && r.weight_kg !== undefined
        ? Math.round(r.weight_kg * 10) / 10
        : undefined,
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
    const res = await api.post('/devices/healthkit/import', { records: records.map(toApiRecord) });
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

function isHealthKitConsentBlocked(errors: string[]): boolean {
  return errors.some((error) => /HealthKit consent/i.test(error));
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
        // 每天可能产出多条 (每源一条);全空记录已在 fetchDailyRecords 内过滤。
        records.push(...(await fetchDailyRecords(new Date(cursor))));
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
  // 未识别来源的原始 sourceName(去重)。非空说明有设备(如 RingConn)写了
  // 健康但映射字典没收录 → 弹窗展示让用户反馈,补一行映射即可独立识别。
  unknownSources: string[];
}

export function summarizeCoverage(records: HealthKitDailyRecord[]): SyncCoverage {
  const count = (pred: (r: HealthKitDailyRecord) => boolean) => records.filter(pred).length;
  return {
    // 一天可能多条 (每源一条),days 计不同日历日,避免被来源数放大。
    days: new Set(records.map((r) => r.record_date)).size,
    steps: count((r) => r.steps !== undefined),
    hr: count((r) => r.resting_heart_rate !== undefined),
    hrv: count((r) => r.hrv !== undefined),
    spo2: count((r) => r.spo2_avg !== undefined),
    sleep: count((r) => r.total_sleep_minutes !== undefined),
    unknownSources: [...new Set(
      records.filter((r) => r.data_source === 'unknown' && r.source_name)
        .map((r) => r.source_name as string),
    )],
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
      records.push(...(await fetchDailyRecords(d)));
    } catch (e: any) {
      // ignore single day error
    }
  }

  const coverage = summarizeCoverage(records);
  const result = await importBatch(records);
  const bodyErrors = isHealthKitConsentBlocked(result.errors)
    ? []
    : await importBodyMeasurements(records);
  return {
    totalImported: result.imported_count,
    errors: [...result.errors, ...bodyErrors],
    coverage,
  };
}
