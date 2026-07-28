import AsyncStorage from '@react-native-async-storage/async-storage';

import api from './api';
import { getAuthStorageScope } from './authStorageScope';

export type ClientEventName =
  // 上一季 ship 的 3 个事件 (2026-05-01)
  | 'reasoning_sheet_opened'
  | 'journal_timeline_entered'
  | 'specialist_scorecard_entered'
  // Phase 0.4 (2026-05-04) — 5 种核心事件让看板看得见用户操作
  | 'home_chip_clicked'           // 首页 chip 点击 (TrustHero / SpecialistChipRow)
  | 'action_card_executed'        // ActionCard 执行/完成按钮
  | 'push_notification_opened'    // 从推送进 app (deep_link 路由后 emit)
  | 'chat_message_sent'           // 用户发送对话 (chat / voice 入口)
  | 'chat_runtime_skill_completed' // Chat 内确定性 runtime skill 完成
  | 'quick_record_logged'         // 快速记录 (BP / 体重 / 用药 / 喝水) 提交
  // Phase 4 (2026-05-29) — cold start 观测
  | 'home_cold_start_perf'        // 首页 critical query 全部就绪的耗时分布
  // Phase 5 (2026-05-29) — starter chip CTR (调权从拍脑袋变成有据)
  | 'starter_chips_shown'         // 新对话空状态 chips 曝光 (CTR 分母)
  | 'starter_chip_clicked'        // 新对话 chip 点击 (CTR 分子)
  // 冷启动包 (2026-07-05, P0-3) — 冷启动 quick reply / Quick Start 卡动作点击
  | 'cold_start_action_clicked'   // meta: { action: 'photo_meal'|'record_weight'|'connect_device', source: 'chat' }
  // Watch leverage-action loop (2026-06-16)
  | 'watch_action_shown'
  | 'watch_action_completed'
  | 'watch_action_snoozed'
  | 'watch_action_skipped'
  | 'watch_action_failed'
  | 'agenda_action_failed'
  // Mobile Agent 可靠性闭环 (2026-07-09) — 只允许无正文、无资源标识的终态元数据
  | 'chat_turn_queued'
  | 'chat_attachment_terminal'
  | 'agent_turn_terminal'
  | 'voice_input_terminal'
  | 'voice_asr_terminal'
  | 'write_receipt_terminal'
  | 'diet_photo_recognition_terminal'
  | 'diet_photo_confirmation_terminal'
  | 'diet_share_terminal'
  | 'aigc_media_played'
  | 'aigc_media_shared'
  // App update control plane — content-free lifecycle telemetry only
  | 'app_update_phase'
  | 'app_update_terminal'
  | 'app_update_launch'
  // N-of-1 闭环北极星 (2026-06-17) — 已验证闭环数
  | 'verified_loop';              // meta: { cycle_id, verdict_count, total } 复查产出 ≥1 非 pending 裁决

export type DurationBucket = 'lt_1s' | '1_3s' | '3_10s' | '10_30s' | 'gte_30s';

const RELIABILITY_PHASES = {
  agent_turn_terminal: new Set(['completed', 'failed', 'interrupted']),
  voice_input_terminal: new Set(['completed', 'failed', 'cancelled']),
  voice_asr_terminal: new Set(['completed', 'failed']),
  write_receipt_terminal: new Set(['verified', 'unverified', 'failed']),
} as const;

const DIET_CAPTURE_PHASES = {
  diet_photo_recognition_terminal: new Set(['completed', 'failed', 'cancelled']),
  diet_photo_confirmation_terminal: new Set(['completed', 'failed']),
  diet_share_terminal: new Set(['completed', 'failed']),
} as const;
const DIET_SHARE_TARGETS = new Set(['generic', 'wechat', 'xiaohongshu']);
const AIGC_MEDIA_KINDS = new Set(['image', 'video']);
const AIGC_SHARE_TARGETS = new Set(['wechat', 'xiaohongshu']);
const APP_UPDATE_PHASES = {
  app_update_phase: new Set(['checking', 'downloading', 'applying']),
  app_update_terminal: new Set([
    'disabled',
    'current',
    'ready',
    'failed',
    'applied',
    'native_update_required',
    'native_update_recommended',
  ]),
} as const;
const APP_UPDATE_LAUNCH_SOURCES = new Set(['embedded', 'ota', 'emergency', 'unknown']);
const CHAT_QUEUE_SURFACES = new Set(['mobile', 'web', 'mac']);
const CHAT_QUEUE_CHANNELS = new Set(['typed', 'voice', 'siri', 'card']);
const CHAT_ATTACHMENT_PHASES = new Set(['accepted', 'failed']);
const CHAT_ATTACHMENT_STAGES = new Set(['local_prepare', 'server_accept']);
const CHAT_ATTACHMENT_PAYLOAD_BUCKETS = new Set([
  'unknown',
  'lt_256kb',
  '256kb_1mb',
  '1_4mb',
  'gte_4mb',
]);
const CHAT_ATTACHMENT_ERROR_CODES = new Set([
  'draft_hydration_failed',
  'server_not_accepted',
  'send_rejected',
]);

type ReliabilityEventName = keyof typeof RELIABILITY_PHASES;

const DURATION_BUCKETS = new Set<DurationBucket>([
  'lt_1s',
  '1_3s',
  '3_10s',
  '10_30s',
  'gte_30s',
]);
const SAFE_TOKEN = /^[a-z0-9][a-z0-9_.:-]{0,63}$/;
const CLIENT_EVENT_OUTBOX_PREFIX = 'client-events:outbox:v1';

type AttachmentTerminalOutboxItem = {
  eventKey: string;
  name: 'chat_attachment_terminal';
  meta: Record<string, unknown>;
};

let clientEventOutboxMutation: Promise<void> = Promise.resolve();

function serializeClientEventOutbox<T>(operation: () => Promise<T>): Promise<T> {
  const result = clientEventOutboxMutation.then(operation, operation);
  clientEventOutboxMutation = result.then(
    () => undefined,
    () => undefined,
  );
  return result;
}

export function durationBucket(startedAt: number, endedAt = Date.now()): DurationBucket {
  const elapsedMs = Math.max(0, endedAt - startedAt);
  if (elapsedMs < 1_000) return 'lt_1s';
  if (elapsedMs < 3_000) return '1_3s';
  if (elapsedMs < 10_000) return '3_10s';
  if (elapsedMs < 30_000) return '10_30s';
  return 'gte_30s';
}

function isReliabilityEvent(name: ClientEventName): name is ReliabilityEventName {
  return Object.prototype.hasOwnProperty.call(RELIABILITY_PHASES, name);
}

type DietCaptureEventName = keyof typeof DIET_CAPTURE_PHASES;

function isDietCaptureEvent(name: ClientEventName): name is DietCaptureEventName {
  return Object.prototype.hasOwnProperty.call(DIET_CAPTURE_PHASES, name);
}

function isAppUpdateEvent(name: ClientEventName): boolean {
  return name === 'app_update_phase' || name === 'app_update_terminal' || name === 'app_update_launch';
}

/** Reliability events are deliberately content-free and identifier-free. */
export function sanitizeClientEventMeta(
  name: ClientEventName,
  meta?: Record<string, unknown>,
): Record<string, unknown> | undefined {
  if (!meta) return meta;
  if (isAppUpdateEvent(name)) {
    const sanitized: Record<string, unknown> = {};
    if (name === 'app_update_launch') {
      if (typeof meta.launch_source === 'string' && APP_UPDATE_LAUNCH_SOURCES.has(meta.launch_source)) {
        sanitized.launch_source = meta.launch_source;
      }
    } else {
      const allowedPhases = name === 'app_update_phase'
        ? APP_UPDATE_PHASES.app_update_phase
        : APP_UPDATE_PHASES.app_update_terminal;
      if (typeof meta.phase === 'string' && allowedPhases.has(meta.phase)) {
        sanitized.phase = meta.phase;
      }
    }
    if (
      name === 'app_update_terminal'
      && typeof meta.duration_bucket === 'string'
      && DURATION_BUCKETS.has(meta.duration_bucket as DurationBucket)
    ) {
      sanitized.duration_bucket = meta.duration_bucket;
    }
    for (const key of ['platform', 'channel', 'runtime', 'native_build', 'update_id', 'error_code']) {
      const value = meta[key];
      if (typeof value === 'string' && SAFE_TOKEN.test(value)) sanitized[key] = value;
    }
    return sanitized;
  }
  if (isDietCaptureEvent(name)) {
    const phase = typeof meta.phase === 'string' && DIET_CAPTURE_PHASES[name].has(meta.phase as never)
      ? meta.phase
      : undefined;
    const numberInRange = (value: unknown, max: number): number | undefined => (
      typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= max
        ? Math.round(value)
        : undefined
    );
    const durationMs = numberInRange(meta.duration_ms, 300_000);
    const foodCount = numberInRange(meta.food_count, 20);
    const tableCount = numberInRange(meta.table_calibrated_count, 20);
    const sanitized: Record<string, unknown> = {};
    if (phase) sanitized.phase = phase;
    if (durationMs !== undefined) sanitized.duration_ms = durationMs;
    const serverTotalMs = numberInRange(meta.server_total_ms, 300_000);
    if (serverTotalMs !== undefined) sanitized.server_total_ms = serverTotalMs;
    if (name === 'diet_photo_recognition_terminal') {
      const clientPrepareMs = numberInRange(meta.client_prepare_ms, 300_000);
      const payloadBytes = numberInRange(meta.payload_bytes, 20 * 1024 * 1024);
      if (clientPrepareMs !== undefined) sanitized.client_prepare_ms = clientPrepareMs;
      if (payloadBytes !== undefined) sanitized.payload_bytes = payloadBytes;
    }
    if (foodCount !== undefined) sanitized.food_count = foodCount;
    if (tableCount !== undefined && (foodCount === undefined || tableCount <= foodCount)) {
      sanitized.table_calibrated_count = tableCount;
    }
    if (typeof meta.verified === 'boolean') sanitized.verified = meta.verified;
    if (name === 'diet_photo_confirmation_terminal' && typeof meta.corrected === 'boolean') {
      sanitized.corrected = meta.corrected;
    }
    if (typeof meta.has_photo === 'boolean') sanitized.has_photo = meta.has_photo;
    if (
      name === 'diet_share_terminal'
      && typeof meta.share_target === 'string'
      && DIET_SHARE_TARGETS.has(meta.share_target)
    ) {
      sanitized.share_target = meta.share_target;
    }
    if (typeof meta.error_code === 'string' && SAFE_TOKEN.test(meta.error_code)) {
      sanitized.error_code = meta.error_code;
    }
    return sanitized;
  }
  if (name === 'aigc_media_played' || name === 'aigc_media_shared') {
    const sanitized: Record<string, unknown> = {};
    if (typeof meta.media_kind === 'string' && AIGC_MEDIA_KINDS.has(meta.media_kind)) {
      sanitized.media_kind = meta.media_kind;
    }
    if (name === 'aigc_media_shared') {
      if (meta.phase === 'completed' || meta.phase === 'failed') {
        sanitized.phase = meta.phase;
      }
      if (typeof meta.share_target === 'string' && AIGC_SHARE_TARGETS.has(meta.share_target)) {
        sanitized.share_target = meta.share_target;
      }
      if (typeof meta.error_code === 'string' && SAFE_TOKEN.test(meta.error_code)) {
        sanitized.error_code = meta.error_code;
      }
    }
    return sanitized;
  }
  if (name === 'chat_turn_queued') {
    const surface = meta.surface;
    const channel = meta.channel;
    const queueDepth = meta.queue_depth_at_submit;
    if (
      typeof surface !== 'string'
      || !CHAT_QUEUE_SURFACES.has(surface)
      || typeof channel !== 'string'
      || !CHAT_QUEUE_CHANNELS.has(channel)
      || typeof queueDepth !== 'number'
      || !Number.isInteger(queueDepth)
      || queueDepth < 1
      || queueDepth > 50
    ) {
      return {};
    }
    return {
      surface,
      channel,
      queue_depth_at_submit: queueDepth,
    };
  }
  if (name === 'chat_attachment_terminal') {
    const phase = meta.phase;
    const stage = meta.stage;
    const imageCount = meta.image_count;
    const bucket = meta.duration_bucket;
    const payloadBucket = meta.payload_bucket;
    if (
      typeof phase !== 'string'
      || !CHAT_ATTACHMENT_PHASES.has(phase)
      || typeof stage !== 'string'
      || !CHAT_ATTACHMENT_STAGES.has(stage)
      || typeof imageCount !== 'number'
      || !Number.isInteger(imageCount)
      || imageCount < 1
      || imageCount > 9
      || typeof bucket !== 'string'
      || !DURATION_BUCKETS.has(bucket as DurationBucket)
      || typeof payloadBucket !== 'string'
      || !CHAT_ATTACHMENT_PAYLOAD_BUCKETS.has(payloadBucket)
    ) {
      return {};
    }
    const sanitized: Record<string, unknown> = {
      phase,
      stage,
      image_count: imageCount,
      duration_bucket: bucket,
      payload_bucket: payloadBucket,
    };
    if (
      typeof meta.error_code === 'string'
      && CHAT_ATTACHMENT_ERROR_CODES.has(meta.error_code)
    ) {
      sanitized.error_code = meta.error_code;
    }
    return sanitized;
  }
  if (!isReliabilityEvent(name)) return meta;

  const sanitized: Record<string, unknown> = {};
  if (typeof meta.phase === 'string' && RELIABILITY_PHASES[name].has(meta.phase as never)) {
    sanitized.phase = meta.phase;
  }
  if (
    typeof meta.duration_bucket === 'string'
    && DURATION_BUCKETS.has(meta.duration_bucket as DurationBucket)
  ) {
    sanitized.duration_bucket = meta.duration_bucket;
  }
  if (typeof meta.action_type === 'string' && SAFE_TOKEN.test(meta.action_type)) {
    sanitized.action_type = meta.action_type;
  }
  if (typeof meta.error_code === 'string' && SAFE_TOKEN.test(meta.error_code)) {
    sanitized.error_code = meta.error_code;
  }
  if (typeof meta.verified === 'boolean') {
    sanitized.verified = meta.verified;
  }
  if (name === 'voice_asr_terminal') {
    if (typeof meta.provider === 'string' && SAFE_TOKEN.test(meta.provider)) {
      sanitized.provider = meta.provider;
    }
    if (
      typeof meta.confidence === 'string'
      && (meta.confidence === 'high' || meta.confidence === 'medium' || meta.confidence === 'low')
    ) {
      sanitized.confidence = meta.confidence;
    }
    if (typeof meta.empty === 'boolean') {
      sanitized.empty = meta.empty;
    }
  }
  if (name === 'write_receipt_terminal') {
    const phase = sanitized.phase;
    const verified = sanitized.verified;
    if (
      typeof phase === 'string'
      && typeof verified === 'boolean'
      && ((phase === 'verified') !== verified)
    ) {
      return {};
    }
  }
  return sanitized;
}

function isAttachmentTerminalMeta(
  meta: Record<string, unknown> | undefined,
): meta is Record<string, unknown> {
  return Boolean(
    meta
    && typeof meta.phase === 'string'
    && CHAT_ATTACHMENT_PHASES.has(meta.phase)
    && typeof meta.stage === 'string'
    && CHAT_ATTACHMENT_STAGES.has(meta.stage)
    && typeof meta.image_count === 'number'
    && Number.isInteger(meta.image_count)
    && meta.image_count >= 1
    && meta.image_count <= 9
    && typeof meta.duration_bucket === 'string'
    && DURATION_BUCKETS.has(meta.duration_bucket as DurationBucket)
    && typeof meta.payload_bucket === 'string'
    && CHAT_ATTACHMENT_PAYLOAD_BUCKETS.has(meta.payload_bucket),
  );
}

async function clientEventOutboxStorageKey(): Promise<string> {
  return `${CLIENT_EVENT_OUTBOX_PREFIX}:${await getAuthStorageScope()}`;
}

async function readClientEventOutbox(
  storageKey: string,
): Promise<AttachmentTerminalOutboxItem[]> {
  const stored = await AsyncStorage.getItem(storageKey);
  if (!stored) return [];

  let parsed: unknown;
  try {
    parsed = JSON.parse(stored);
  } catch {
    await AsyncStorage.removeItem(storageKey);
    return [];
  }
  if (!Array.isArray(parsed)) {
    await AsyncStorage.removeItem(storageKey);
    return [];
  }
  return parsed.flatMap((item): AttachmentTerminalOutboxItem[] => {
    if (
      !item
      || typeof item !== 'object'
      || (item as AttachmentTerminalOutboxItem).name !== 'chat_attachment_terminal'
      || typeof (item as AttachmentTerminalOutboxItem).eventKey !== 'string'
      || !SAFE_TOKEN.test((item as AttachmentTerminalOutboxItem).eventKey)
    ) {
      return [];
    }
    const sanitized = sanitizeClientEventMeta(
      'chat_attachment_terminal',
      (item as AttachmentTerminalOutboxItem).meta,
    );
    if (!isAttachmentTerminalMeta(sanitized)) return [];
    return [{
      eventKey: (item as AttachmentTerminalOutboxItem).eventKey,
      name: 'chat_attachment_terminal',
      meta: sanitized,
    }];
  });
}

async function writeClientEventOutbox(
  storageKey: string,
  items: AttachmentTerminalOutboxItem[],
): Promise<void> {
  if (items.length === 0) {
    await AsyncStorage.removeItem(storageKey);
    return;
  }
  await AsyncStorage.setItem(storageKey, JSON.stringify(items));
}

async function enqueueAttachmentTerminalEvent(
  eventKey: string,
  meta: Record<string, unknown>,
): Promise<void> {
  await serializeClientEventOutbox(async () => {
    const storageKey = await clientEventOutboxStorageKey();
    const items = await readClientEventOutbox(storageKey);
    if (items.some((item) => item.eventKey === eventKey)) return;
    await writeClientEventOutbox(storageKey, [
      ...items,
      { eventKey, name: 'chat_attachment_terminal', meta },
    ]);
  });
}

/**
 * Replays content-free attachment terminal events after network/app interruptions.
 * The server deduplicates by event_key; each acknowledged item is removed durably.
 */
export async function flushClientEventOutbox(): Promise<void> {
  await serializeClientEventOutbox(async () => {
    const storageKey = await clientEventOutboxStorageKey();
    const items = await readClientEventOutbox(storageKey);
    let remaining = items;
    while (remaining.length > 0) {
      const item = remaining[0];
      try {
        const response = await api.post('/client-events', {
          event_name: item.name,
          event_key: item.eventKey,
          meta: item.meta,
        });
        if (response?.data?.ok !== true) {
          return;
        }
      } catch {
        return;
      }
      remaining = remaining.slice(1);
      await writeClientEventOutbox(storageKey, remaining);
    }
  });
}

/**
 * 发一条 UI 埋点事件. 失败静默 — 埋点不该影响用户流程.
 * 后端 /client-events 把事件写入 client_events 表, 观察期看板用来算行为率.
 *
 * meta 约定 (各事件):
 * - home_chip_clicked: { chip: 'trust_hero' | 'specialist', target?: string }
 * - action_card_executed: { card_id: number, action: 'execute' | 'complete' | 'reminder' }
 * - push_notification_opened: { kind?: string, deep_link?: string }
 * - chat_message_sent: { source: 'chat' | 'voice' | 'siri', has_image: boolean }
 * - chat_runtime_skill_completed: { skill_id: string, card_type: string }
 * - quick_record_logged: { kind: 'bp' | 'weight' | 'water' | 'medication' | 'supplement' | 'mood' | ... }
 * - starter_chips_shown: { keys: string[], source: 'chat' }
 * - starter_chip_clicked: { key: string, priority: number, position: number, source: 'chat' }
 * - watch_action_*: { action_id: string, kind: string, priority_tier?: 'P0'|'P1'|'P2'|'P3'|'P4', reason?: string }
 * - agenda_action_failed: { reason: string, object_type?: string, object_id?: unknown, status?: string }
 */
export async function emitClientEvent(
  name: ClientEventName,
  meta?: Record<string, unknown>,
  options?: { eventKey?: string },
): Promise<void> {
  const eventKey = options?.eventKey;
  const sanitizedMeta = sanitizeClientEventMeta(name, meta);
  if (
    name === 'chat_attachment_terminal'
    && typeof eventKey === 'string'
    && SAFE_TOKEN.test(eventKey)
    && isAttachmentTerminalMeta(sanitizedMeta)
  ) {
    try {
      await enqueueAttachmentTerminalEvent(eventKey, sanitizedMeta);
      void flushClientEventOutbox().catch(() => {
        // The durable outbox owns retry; network delivery must not block cleanup.
      });
    } catch {
      // Callers await this function before cleanup, so a local persistence failure
      // leaves the draft intact even though telemetry itself stays UI-silent.
      throw new Error('client_event_outbox_persistence_failed');
    }
    return;
  }

  try {
    await api.post('/client-events', {
      event_name: name,
      ...(typeof eventKey === 'string' && SAFE_TOKEN.test(eventKey)
        ? { event_key: eventKey }
        : {}),
      meta: sanitizedMeta,
    });
  } catch {
    // swallow — 埋点不该影响 UI
  }
}
