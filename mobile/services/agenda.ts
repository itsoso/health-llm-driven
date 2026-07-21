/**
 * 统一健康议程 service —— 消费后端 /agenda(R1)。
 * 协议待办 + 到期复查聚成一条 today;双轨完成经 /agenda/complete 路由写真实业务记录。
 *
 * 注:后端 /agenda、/protocols 端点尚未进 mobile/types/api.generated.ts(待 npm run generate-types)。
 * 本文件先手写最小契约,字段对齐 backend/app/services/agenda_service.py。
 */
import api from './api';

export interface AgendaSource {
  object_type: string; // health_protocol / health_problem
  object_id: number | string;
  // F5b 多剂闭环:剂量槽 "HH:MM"。仅真多剂(后端 reminder_times ≥2 个时点)的项带它,
  // 透传给 /agenda/complete 让该剂各自闭环;单剂/每日一次省略(行为与改前一致)。
  slot?: string;
}

export interface AgendaItem {
  type: string; // hydration/medication/diet/checkup/...
  title: string;
  status: string; // pending/completed/skipped/due/overdue
  time_window?: string;
  priority: number;
  can_default_complete?: boolean;
  detail?: string;
  responsible?: string;
  next_due?: string;
  snoozed_until?: string | null;
  // 训练决策灯(type === 'training', status === 'info')专属字段
  light?: 'green' | 'yellow' | 'red';
  zone?: string;
  readiness_score?: number | null;
  confidence?: string | number;
  source: AgendaSource;
}

export interface AgendaToday {
  agenda_date: string;
  count: number;
  items: AgendaItem[];
}

export interface TrajectoryContext {
  domain?: string;
  level?: 'high' | 'attention' | 'unknown' | 'ok' | string;
  state_variable?: string | null;
  horizon?: string | null;
  why?: string | null;
  signals?: string[];
  primary_action?: string | null;
  modifiable_levers?: string[];
  uncertainty?: { level?: string; drivers?: string[] } | null;
  evidence_tier?: string | null;
  confidence?: string | number | null;
  claim_boundary?: string | null;
  verification_window?: { days?: number; signal?: string } | null;
  verification_window_days?: number | null;
  verification_signal?: string | null;
}

export interface SmartAgendaItem {
  id: string;
  type: string;
  title: string;
  status: string;
  time?: string | null;
  time_window?: string;
  priority: number;
  rank_score?: number;
  rank_reason?: Record<string, unknown>;
  source: AgendaSource;
  why_now: string;
  do_now: string;
  verify_by: Record<string, unknown>;
  replan_policy: Record<string, string>;
  surface: { primary: string; alternates?: string[] };
  autonomy_tier: string;
  can_complete: boolean;
  can_snooze: boolean;
  can_skip: boolean;
  trajectory_context?: TrajectoryContext | null;
  target_state_variable?: string | null;
  verification_signal?: string | null;
  /**
   * 含糊语音(Rokid「确认/跳过」)可否安全自动完成 —— 后端权威安全门(R4)。
   * 后端从协议 source_model 派生:完成会写医疗级依从(MedicationLog/SupplementRecord)
   * 或为复查项 → false。比 domain 更可靠(domain↔source_model 可漂移)。
   * 可选:旧后端不发该字段时为 undefined,客户端回退到 domain 白名单。
   * 见 backend agenda_service._is_voice_actionable / rokidVoiceAgenda.ts。
   */
  voice_actionable?: boolean;
  confidence?: string | number | null;
  claim_boundary?: string | null;
}

export interface SmartAgendaToday extends AgendaToday {
  mode: 'smart';
  source_count: number;
  smart: {
    generated_by?: string;
    ranking?: string;
    top_items: SmartAgendaItem[];
  };
}

export interface RuntimeAgendaContext {
  surface: 'agenda' | string;
  current_state_summary?: string | null;
  evidence?: Record<string, unknown>;
  safety_boundary: string;
  freshness?: Record<string, unknown>;
  verification_window: {
    window_days: number;
    metrics: string[];
  };
  replan_reason: string;
  next_replan_triggers?: string[];
}

export interface RuntimeAgendaItem extends SmartAgendaItem {
  scheduled_for: string;
  runtime_context: RuntimeAgendaContext;
}

export interface RuntimeAgendaTimeWindow {
  time_window: string;
  items: RuntimeAgendaItem[];
}

export interface RuntimeAgendaDay {
  date: string;
  is_today: boolean;
  state: 'today' | 'planned' | string;
  next_action?: RuntimeAgendaItem | null;
  time_windows: RuntimeAgendaTimeWindow[];
}

export interface RuntimeAgendaRange {
  start: string;
  end: string;
  mode: 'runtime';
  generated_by: string;
  horizon_days: number;
  runtime_context: Record<string, unknown>;
  next_action?: RuntimeAgendaItem | null;
  days: RuntimeAgendaDay[];
}

export async function getAgendaToday(): Promise<AgendaToday> {
  const resp = await api.get<AgendaToday>('/agenda/today');
  return resp.data;
}

export async function getSmartAgendaToday(maxItems = 3): Promise<SmartAgendaToday> {
  const resp = await api.get<SmartAgendaToday>('/agenda/today', {
    params: { mode: 'smart', max_items: maxItems },
  });
  return resp.data;
}

export async function getRuntimeAgendaRange(days = 7): Promise<RuntimeAgendaRange> {
  const resp = await api.get<RuntimeAgendaRange>('/agenda/range', {
    params: { days, mode: 'runtime' },
  });
  return resp.data;
}

/** done = 记录完成(写真实业务记录);skipped = 记录未做(R14 带可选失败原因)。 */
export type AgendaCompleteStatus = 'done' | 'skipped';

/** R14 跳过原因枚举(对齐后端 agenda/complete 的 skip_reason 校验)。 */
export type AgendaSkipReason =
  | 'no_time'
  | 'forgot'
  | 'no_supply'
  | 'too_tired'
  | 'wrong_place'
  | 'too_hard'
  | 'unwell'
  | 'social';

export interface CompleteAgendaOptions {
  /** 默认 'done'。'skipped' 走 R14 跳过路径。 */
  status?: AgendaCompleteStatus;
  /** 仅 status==='skipped' 时携带;省略=不带原因。 */
  skipReason?: AgendaSkipReason;
}

// 契约护栏:POST /agenda/complete 请求体出口 payload。
// 注:types/api.generated.ts 的 components['schemas']['AgendaComplete'] 是后端
// f845ff9f 上线**前**生成的旧 shape(只有 object_type/object_id/track/value),
// 尚无 status/skip_reason 字段 —— 现在用它标注会把新字段判成 excess-property(假红)。
// 后端部署后需 `npm run generate-types` 重新生成,再把下面手写接口换成 schema 标注。
// TODO regenerate after backend deploy → 换成 components['schemas']['AgendaComplete']
interface AgendaCompletePayload {
  object_type: string;
  object_id: number;
  status: AgendaCompleteStatus;
  skip_reason?: AgendaSkipReason | null;
  track: 'protocol' | 'manual';
  value?: Record<string, unknown> | null;
  // F5b:仅真多剂项透传(source.slot 存在时)。后端单剂忽略,additive。
  slot?: string;
}

function normalizeAgendaObjectId(raw: number | string): number {
  if (typeof raw === 'number' && Number.isInteger(raw)) return raw;
  if (typeof raw === 'string' && /^\d+$/.test(raw.trim())) return Number(raw);
  throw new Error('agenda object_id must be numeric');
}

/**
 * 统一完成/跳过:按 source 路由(协议→双轨写真实记录)。
 * status 默认 'done'(所有既有调用方零改动);'skipped' 走 R14 跳过路径,可带 skipReason。
 * track 默认协议轨;手工轨带 value(量/剂量)。
 */
export async function completeAgendaItem(
  source: AgendaSource,
  track: 'protocol' | 'manual' = 'protocol',
  value?: Record<string, unknown>,
  options?: CompleteAgendaOptions,
): Promise<unknown> {
  const status: AgendaCompleteStatus = options?.status ?? 'done';
  const payload: AgendaCompletePayload = {
    object_type: source.object_type,
    object_id: normalizeAgendaObjectId(source.object_id),
    status,
    track,
    value: value ?? null,
  };
  // F5b:真多剂项带 slot → 透传(后端据它分槽闭环各剂);单剂省略 → 行为与改前一致。
  if (source.slot) {
    payload.slot = source.slot;
  }
  // skipped 必须有原因;通知后台动作没有上下文时默认 no_time,避免无原因跳过污染分析。
  if (status === 'skipped') {
    payload.skip_reason = options?.skipReason ?? 'no_time';
  }
  const resp = await api.post('/agenda/complete', payload);
  return resp.data;
}

export async function snoozeAgendaItem(
  source: AgendaSource,
  minutes = 30,
): Promise<unknown> {
  const resp = await api.post('/agenda/snooze', {
    object_type: source.object_type,
    object_id: normalizeAgendaObjectId(source.object_id),
    minutes,
  });
  return resp.data;
}

export async function resumeAgendaItem(source: AgendaSource): Promise<unknown> {
  const resp = await api.post('/agenda/resume', {
    object_type: source.object_type,
    object_id: normalizeAgendaObjectId(source.object_id),
  });
  return resp.data;
}

/** 域 → 手工轨录入配置(提问 + value 字段名 + 是否数字)。双轨原则:手工永远一个点击之遥。 */
export const MANUAL_CAPTURE: Record<string, {
  prompt: string; valueKey: string; numeric: boolean; placeholder?: string;
}> = {
  hydration: { prompt: '实际喝了多少毫升?', valueKey: 'volume_ml', numeric: true, placeholder: '如 500' },
  medication: { prompt: '实际剂量(留空=按医嘱)', valueKey: 'actual_dosage', numeric: false, placeholder: '如 1片 / 20mg' },
  diet: { prompt: '吃了什么?', valueKey: 'food_items', numeric: false, placeholder: '如 鸡胸肉沙拉' },
};

/** 跳过(仅协议来源),带失败原因(R14)。 */
export async function skipProtocol(protocolId: number, reason?: string): Promise<unknown> {
  const resp = await api.post(`/protocols/${protocolId}/skip`, { reason: reason ?? null });
  return resp.data;
}

/** 该 agenda item 是否可由协议轨「一键完成」(协议来源且未完成)。 */
export function isProtocolActionable(item: AgendaItem): boolean {
  return item.source.object_type === 'health_protocol' && item.status === 'pending';
}

/** 一键试用:seed 一个 2000ml 温水杯协议 + 登记胃溃疡(Hp-),让议程立刻有内容。 */
export async function seedDemo(): Promise<void> {
  await api.post('/protocols/seed/water-cup');
  await api.post('/problems/seed/gastric-ulcer-hp-neg');
}
