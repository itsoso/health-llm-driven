import { useState, useRef, useCallback, useEffect, useReducer } from 'react';
import { AppState } from 'react-native';
import { useFocusEffect } from 'expo-router';
import * as Haptics from 'expo-haptics';
import NetInfo from '@react-native-community/netinfo';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { streamChat, getConversations, getConversationMessages, deleteConversation, type ChatMessage, type LlmUsageProfile, type AgentPerfProfile, type MedicationBatchStreamDecision } from '../services/chat';
import { dispatchCard, renderServerCards } from '../components/chat/cards';
import type { ChatCardActionDescriptor, ServerCardDescriptor } from '../components/chat/cards/types';
import api, { BASE_URL } from '../services/api';
import { durationBucket, emitClientEvent } from '../services/clientEvents';
import { sanitizeChatErrorMessage, sanitizeChatStreamToken } from '../utils/chatErrorMessage';
import {
  createIdleAgentTurn,
  isAgentTurnTerminal,
  reduceAgentTurn,
  type AgentTurnEvent,
  type AgentTurnState,
} from '../utils/agentTurnState';
import {
  acknowledgePendingWriteReceipt,
  loadPendingWriteReceipt,
  mergeConversationContinuity,
  rememberVerifiedWriteReceipt,
} from '../services/conversationContinuity';
import { getAuthStorageScope } from '../services/authStorageScope';
import { normalizeWriteReceipt, type WriteReceipt } from '../services/writeReceipt';
import type { MedicationSafetyAlert } from '../services/medications';

function normalizeImageHost(baseUrl: string): string {
  return String(baseUrl || '').replace(/\/+$/, '').replace(/\/api(?:\/v\d+)?$/, '');
}

const IMAGE_HOST = normalizeImageHost(BASE_URL);

export interface UIMessage extends ChatMessage {
  id: string;
  streaming?: boolean;
  thinkingSteps?: string[];
  // P0-1 渐进渲染 (刀⑤): 首 token 前的"细状态行"标签 (中文人话), 由 status SSE 事件驱动。
  // 例: "正在理解…" → "查看步数数据…" → "正在整理回答…"。首 token 到达即清空,
  // 之后收进思考完成态 pill。仅流式期间存在, 从不落后端历史 (与 streaming 一样 ephemeral)。
  currentStatus?: string;
  imageUris?: string[];
  isBriefing?: boolean;
  // 2026-07 State A「小巴先开口」: 用户发第一条消息时, 把当时可见的开场气泡文本
  // 作为一条合成 assistant 消息注入到流顶, 保住上下文连续性。仅本地展示,
  // 从不 POST 到后端历史, reload 后不恢复(与 isBriefing 一样是 ephemeral)。
  localOnly?: boolean;
  cardType?: string;
  cardData?: any;
  cardActions?: ChatCardActionDescriptor[];
  sourceMessageId?: number;
  sourceTurnId?: string;
  createdAt?: string;
  fromSiri?: boolean;
  // 2026-05-13: 性能可观测 — done 事件的耗时 + 模型名, 渲染在 assistant 气泡底部
  elapsedMs?: number;
  llmMs?: number;
  llmRounds?: number;
  llmRoundsMs?: number[];
  model?: string;
  llmUsage?: LlmUsageProfile;
  perf?: AgentPerfProfile;
  // 2026-05-14 #4: 可解释性 — AI 用了什么数据
  sourcesUsed?: string[];
  // 2026-06-12: 本轮调用的 Skill / 工具名 (后端 done.tools_used / meta.tools_used), 对齐 mac/web
  toolsUsed?: string[];
  completionStatus?: 'complete' | 'interrupted' | 'error' | 'unknown';
  writeReceipts?: WriteReceipt[];
  safetyAlerts?: MedicationSafetyAlert[];
  decisionStatus?: MedicationDecisionStatus;
}

export type MedicationDecisionStatus = 'pending' | 'executed' | 'dismissed' | 'expired';

let msgCounter = 0;
function nextId(): string { return `msg-${++msgCounter}-${Date.now()}`; }
let turnCounter = 0;
function nextTurnId(): string { return `turn-${++turnCounter}-${Date.now()}`; }

function digestTurnRequest(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `${(hash >>> 0).toString(16)}-${value.length}`;
}

export function buildTurnRequestFingerprint(
  text: string,
  images?: { uri: string; type?: string }[] | null,
): string {
  return digestTurnRequest(JSON.stringify({
    text: text.trim(),
    images: (images || []).map(image => ({ uri: image.uri, type: image.type || '' })),
  }));
}

export function findReusableTurnMessage(
  messages: UIMessage[],
  role: 'user' | 'assistant',
  turnId: string,
): UIMessage | undefined {
  return [...messages].reverse().find(message => (
    message.role === role
    && !message.cardType
    && message.sourceTurnId === turnId
  ));
}

function upsertOptimisticTurnPair(
  messages: UIMessage[],
  reusableTurnId: string | undefined,
  userMessage: UIMessage,
  assistantMessage: UIMessage,
): UIMessage[] {
  if (!reusableTurnId) return [...messages, userMessage, assistantMessage];
  let foundUser = false;
  let foundAssistant = false;
  const replaced = messages
    .filter(message => !message.cardType || message.sourceTurnId !== reusableTurnId)
    .map((message) => {
      if (message.id === userMessage.id) {
        foundUser = true;
        return userMessage;
      }
      if (message.id === assistantMessage.id) {
        foundAssistant = true;
        return assistantMessage;
      }
      return message;
    });
  if (!foundUser) replaced.push(userMessage);
  if (!foundAssistant) replaced.push(assistantMessage);
  return replaced;
}

/** 2026-05-14 FIX-7: 把 message.meta (后端持久化的性能/可解释性 JSON)
 * 映射到 UIMessage 字段, 让 reload 也能恢复 chat bubble footer. */
function applyMeta(msg: any): Partial<UIMessage> {
  const meta = msg?.meta;
  if (!meta || typeof meta !== 'object') return {};
  const rawDecision = meta.medication_batch_decision;
  const decision = rawDecision && typeof rawDecision === 'object' && !Array.isArray(rawDecision)
    ? rawDecision
    : undefined;
  const decisionStatus = normalizeMedicationDecisionStatus(decision?.status);
  const noWriteTerminal = decisionStatus === 'dismissed' || decisionStatus === 'expired';
  const hasExactReceipts = Array.isArray(decision?.write_receipts);
  const hasExactAlerts = Array.isArray(decision?.safety_alerts);
  return {
    elapsedMs: typeof meta.elapsed_ms === 'number' ? meta.elapsed_ms : undefined,
    llmMs: typeof meta.llm_ms === 'number' ? meta.llm_ms : undefined,
    llmRounds: typeof meta.llm_rounds === 'number' ? meta.llm_rounds : undefined,
    llmRoundsMs: Array.isArray(meta.llm_rounds_ms) ? meta.llm_rounds_ms : undefined,
    model: typeof meta.model === 'string' ? meta.model : undefined,
    llmUsage: meta.llm_usage && typeof meta.llm_usage === 'object' ? meta.llm_usage : undefined,
    perf: meta.perf && typeof meta.perf === 'object' ? meta.perf : undefined,
    sourcesUsed: Array.isArray(meta.sources_used) ? meta.sources_used : undefined,
    toolsUsed: Array.isArray(meta.tools_used) ? meta.tools_used : undefined,
    completionStatus: typeof meta.completion_status === 'string' ? meta.completion_status : undefined,
    thinkingSteps: normalizeThinkingSteps(meta.thinking_steps ?? meta.thought_steps),
    writeReceipts: noWriteTerminal
      ? []
      : hasExactReceipts
        ? normalizeWriteReceipts(decision.write_receipts) ?? []
        : normalizeWriteReceipts(meta.write_receipts),
    safetyAlerts: noWriteTerminal
      ? []
      : hasExactAlerts
        ? normalizeMedicationSafetyAlerts(decision.safety_alerts) ?? []
        : normalizeMedicationSafetyAlerts(meta.safety_alerts),
    decisionStatus,
  };
}

function normalizeWriteReceipts(value: unknown): WriteReceipt[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const receipts = value
    .map(normalizeWriteReceipt)
    .filter((receipt): receipt is WriteReceipt => !!receipt);
  return receipts.length > 0 ? receipts : undefined;
}

function normalizeMedicationSafetyAlerts(value: unknown): MedicationSafetyAlert[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const alerts = value.filter((raw): raw is MedicationSafetyAlert => (
    raw != null
    && typeof raw === 'object'
    && !Array.isArray(raw)
    && typeof (raw as Record<string, unknown>).rule_id === 'string'
    && typeof (raw as Record<string, unknown>).title === 'string'
    && typeof (raw as Record<string, unknown>).message === 'string'
  ));
  return alerts.length > 0 ? alerts : undefined;
}

function normalizeMedicationDecisionStatus(value: unknown): MedicationDecisionStatus | undefined {
  return value === 'pending' || value === 'executed' || value === 'dismissed' || value === 'expired'
    ? value
    : undefined;
}

function medicationIntentId(value: unknown): number | null {
  const normalized = typeof value === 'number'
    ? value
    : typeof value === 'string' && value.trim() ? Number(value) : NaN;
  return Number.isInteger(normalized) && normalized > 0 ? normalized : null;
}

function actionTargetsMedicationIntent(
  action: ChatCardActionDescriptor,
  intentId: number,
): boolean {
  return (action.action === 'write_intent.confirm' || action.action === 'write_intent.dismiss')
    && medicationIntentId(action.payload?.write_intent_id) === intentId;
}

function projectMedicationTerminalDescriptor(
  descriptor: ServerCardDescriptor,
  decision: MedicationBatchStreamDecision,
): { descriptor: ServerCardDescriptor; changed: boolean } {
  if (descriptor.type === 'cards_group' && Array.isArray(descriptor.data?.cards)) {
    let changed = false;
    const cards = (descriptor.data.cards as ServerCardDescriptor[]).map((card) => {
      const projected = projectMedicationTerminalDescriptor(card, decision);
      changed ||= projected.changed;
      return projected.descriptor;
    });
    return changed ? {
      descriptor: { ...descriptor, data: { ...descriptor.data, cards } },
      changed: true,
    } : { descriptor, changed: false };
  }
  if (descriptor.type !== 'medication_draft') return { descriptor, changed: false };
  const targets = medicationIntentId(descriptor.data?.write_intent_id) === decision.intentId
    || (descriptor.actions || []).some(action => (
      actionTargetsMedicationIntent(action, decision.intentId)
    ));
  if (!targets) return { descriptor, changed: false };
  return {
    descriptor: {
      type: descriptor.type,
      data: {
        ...(descriptor.data || {}),
        action_pending: false,
        decision_status: decision.decisionStatus,
        write_receipts: decision.decisionStatus === 'executed'
          ? decision.writeReceipts.map(receipt => ({
            operation_id: receipt.operationId,
            status: receipt.status,
            resource_type: receipt.resourceType,
            resource_id: receipt.resourceId,
            completed_at: receipt.completedAt,
            verified: receipt.verified,
            ...(receipt.executedRef ? { executed_ref: receipt.executedRef } : {}),
          }))
          : [],
        safety_alerts: decision.decisionStatus === 'executed' ? decision.safetyAlerts : [],
      },
      actions: [],
    },
    changed: true,
  };
}

function projectMedicationTerminalMessages(
  messages: UIMessage[],
  decision: MedicationBatchStreamDecision,
): UIMessage[] {
  return messages.map((message) => {
    if (!message.cardType) return message;
    const projected = projectMedicationTerminalDescriptor({
      type: message.cardType,
      data: message.cardData,
      actions: message.cardActions,
    }, decision);
    if (!projected.changed) return message;
    return {
      ...message,
      cardType: projected.descriptor.type,
      cardData: projected.descriptor.data,
      cardActions: projected.descriptor.actions,
      decisionStatus: decision.decisionStatus,
      writeReceipts: decision.decisionStatus === 'executed' ? decision.writeReceipts : [],
      safetyAlerts: decision.decisionStatus === 'executed' ? decision.safetyAlerts : [],
    };
  });
}

function normalizeThinkingSteps(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const out: string[] = [];
  for (const step of value) {
    const normalized = String(step || '').trim();
    if (normalized && !out.includes(normalized)) out.push(normalized);
  }
  return out.length > 0 ? out.slice(-MAX_THINKING_STEPS) : undefined;
}

function absolutizeHistoryImageUri(uri: string, imageHost: string): string | undefined {
  const value = String(uri || '').trim();
  if (!value) return undefined;
  if (/^(https?:|file:|data:)/i.test(value)) return value;
  const host = normalizeImageHost(imageHost);
  if (!host) return value;
  return value.startsWith('/') ? `${host}${value}` : `${host}/${value}`;
}

function parseHistoryImageUris(raw: any, imageHost: string): string[] | undefined {
  if (!raw) return undefined;
  let parsed: any = raw;
  try {
    if (typeof raw === 'string') {
      parsed = JSON.parse(raw);
    }
  } catch {
    parsed = raw;
  }
  const values = Array.isArray(parsed) ? parsed : (typeof parsed === 'string' ? [parsed] : []);
  const uris = values
    .filter((u: any): u is string => typeof u === 'string')
    .map((u: string) => absolutizeHistoryImageUri(u, imageHost))
    .filter((u: string | undefined): u is string => !!u);
  return uris.length > 0 ? uris : undefined;
}

function assistantMessageForTurn(msgs: any[], turnId: string): any | undefined {
  return [...(msgs || [])].reverse().find((message: any) => (
    message?.role === 'assistant'
    && message?.meta?.client_turn_id === turnId
    && typeof message.content === 'string'
    && message.content.trim().length > 0
  ));
}

/** Restore durable chat messages plus server-rendered cards from history.
 *
 * Live streams render cards from the `done.cards` payload. The backend also
 * persists the same descriptors under assistant `message.meta.cards`; history
 * reloads must flatten those descriptors back into card messages or cards will
 * disappear after reopening a conversation.
 */
export function restoreMessagesFromHistory(
  msgs: any[],
  imageHost: string = IMAGE_HOST,
  idPrefix: string = 'hist',
): UIMessage[] {
  const restored: UIMessage[] = [];
  (msgs || []).forEach((m: any, i: number) => {
    const baseId = `${idPrefix}-${m.id || i}`;
    const messageMeta = applyMeta(m);
    const serverCards = renderServerCards(m?.meta?.cards);
    const hasTerminalMedicationCard = serverCards.some((card) => {
      if (card.type !== 'medication_draft') return false;
      const decisionStatus = normalizeMedicationDecisionStatus(card.data?.decision_status)
        ?? messageMeta.decisionStatus;
      return decisionStatus != null && decisionStatus !== 'pending';
    });
    restored.push({
      id: baseId,
      role: m.role,
      content: m.content,
      createdAt: m.created_at,
      sourceTurnId: typeof m?.meta?.client_turn_id === 'string'
        ? m.meta.client_turn_id
        : undefined,
      imageUris: parseHistoryImageUris(m.image_url, imageHost),
      ...messageMeta,
      ...(hasTerminalMedicationCard ? {
        writeReceipts: undefined,
        safetyAlerts: undefined,
        decisionStatus: undefined,
      } : {}),
    });

    serverCards.forEach((card, cardIndex) => {
      const isMedicationCard = card.type === 'medication_draft';
      restored.push({
        id: `${baseId}-card-${cardIndex}`,
        role: 'assistant',
        content: '',
        cardType: card.type,
        cardData: card.data,
        cardActions: card.actions,
        sourceMessageId: typeof m.id === 'number' ? m.id : undefined,
        sourceTurnId: typeof m?.meta?.client_turn_id === 'string'
          ? m.meta.client_turn_id
          : undefined,
        createdAt: m.created_at,
        ...(isMedicationCard ? {
          writeReceipts: normalizeWriteReceipts(card.data?.write_receipts) ?? messageMeta.writeReceipts,
          safetyAlerts: normalizeMedicationSafetyAlerts(card.data?.safety_alerts) ?? messageMeta.safetyAlerts,
          decisionStatus: normalizeMedicationDecisionStatus(card.data?.decision_status)
            ?? messageMeta.decisionStatus,
        } : {}),
      });
    });
  });
  return restored;
}

interface UseChatEngineOptions {
  contextData?: Record<string, any>;
}

interface SendMessageOptions {
  fromSiri?: boolean;
  extraContext?: string;
  forceNewConversation?: boolean;
  channel?: 'typed' | 'voice' | 'siri';
  onAccepted?: (accepted: boolean) => void;
  __queuedTurnId?: string;
  __localUserMessageId?: string;
  __localAssistantMessageId?: string;
  __precreatedLocalMessages?: boolean;
}

interface QueuedChatTurn {
  turnId: string;
  text: string;
  pendingImages?: { uri: string; base64?: string; type?: string }[] | null;
  options?: SendMessageOptions;
  userMessageId: string;
  assistantMessageId: string;
}

const BRIEFING_CONVERSATION_TITLE = '每日健康简报';
const DEFAULT_WINDOW_DAYS = 7;
const LAST_CONVERSATION_ID_KEY = 'chat:last_conversation_id:v1';
const PENDING_STREAM_STARTED_AT_KEY = 'chat:pending_stream_started_at:v1';
const ACTIVE_TURN_KEY = 'chat:active_turn:v1';
const PENDING_STREAM_TTL_MS = 10 * 60 * 1000;
const THINKING_PLACEHOLDER = '⏳ AI 正在思考中...';
const QUEUED_TURN_PLACEHOLDER = '小巴处理中，已加入队列。';
const STREAM_RECOVERY_NOTICE = '小巴还在处理，正在同步完整回答。';
const STREAM_RECOVERY_SUFFIX = '\n\n[连接短暂中断，正在同步完整回答]';
const MAX_THINKING_STEPS = 8;
// P0-5 竞态守卫: 本地 stream 活跃且未超过此窗口时, focus-reload / app-active-reload
// 不得用服务端半截 partial 覆盖本地流式态。超过窗口 (慢流 / 卡死) 才放行服务端恢复,
// 避免永久霸占 UI。与 PENDING_STREAM_TTL_MS(10min, 冷启恢复用)不同 —— 这是前台活跃流的护栏。
const LOCAL_STREAM_HOLD_MS = 30 * 1000;
// P0-1 节流: 思考面板 (thinkingSteps) 更新最小间隔。快路由下 status/tool 事件密集到达,
// 逐事件 setMessages 全量 map 会打满 JS 线程 —— 攒到 >=200ms 才 flush 一次思考步骤。
const THINKING_FLUSH_MS = 200;

export function scopedChatStorageKey(baseKey: string, scope: string): string {
  return `${baseKey}:${scope}`;
}

async function currentChatStorageKey(baseKey: string): Promise<string> {
  return scopedChatStorageKey(baseKey, await getAuthStorageScope());
}

function parseStoredAgentTurn(raw: string | null): AgentTurnState | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw);
    if (
      value?.version !== 1
      || typeof value?.phase !== 'string'
      || typeof value?.turnId !== 'string'
      || typeof value?.recoverable !== 'boolean'
      || typeof value?.hadWrite !== 'boolean'
    ) return null;
    if (typeof value.updatedAt === 'number' && Date.now() - value.updatedAt > PENDING_STREAM_TTL_MS) {
      return null;
    }
    return value as AgentTurnState;
  } catch {
    return null;
  }
}

function stripThinkingPlaceholder(content: string): string {
  return content.replace(THINKING_PLACEHOLDER, '');
}

function mergeAssistantStreamContent(current: string, incoming: string): string {
  if (!incoming) return current;
  return stripThinkingPlaceholder(current) + incoming;
}

function appendThinkingStep(current: string[] | undefined, next: string | undefined): string[] | undefined {
  const normalized = (next || '').trim();
  if (!normalized) return current;
  const existing = Array.isArray(current) ? current : [];
  if (existing[existing.length - 1] === normalized) return existing;
  return [...existing, normalized].slice(-MAX_THINKING_STEPS);
}

function serverCardKey(card: Pick<ServerCardDescriptor, 'type' | 'data' | 'actions'>): string {
  try {
    return JSON.stringify([card.type, card.data ?? {}, card.actions ?? []]);
  } catch {
    return `${card.type}:${Date.now()}`;
  }
}

function insertCardMessagesAfterAssistant(
  messages: UIMessage[],
  assistantId: string,
  cards: ServerCardDescriptor[],
  sourceTurnId?: string,
): UIMessage[] {
  if (cards.length === 0) return messages;
  const insertAtBase = messages.findIndex(m => m.id === assistantId);
  let insertAt = insertAtBase >= 0 ? insertAtBase + 1 : messages.length;
  while (insertAt < messages.length && messages[insertAt]?.role === 'assistant' && !!messages[insertAt]?.cardType) {
    insertAt += 1;
  }
  const cardMessages = cards.map((card) => ({
    id: nextId(),
    role: 'assistant' as const,
    content: '',
    cardType: card.type,
    cardData: card.data,
    cardActions: card.actions,
    sourceTurnId,
  }));
  return [...messages.slice(0, insertAt), ...cardMessages, ...messages.slice(insertAt)];
}

async function readStoredConversationId(): Promise<number | null> {
  try {
    const key = await currentChatStorageKey(LAST_CONVERSATION_ID_KEY);
    await AsyncStorage.removeItem(LAST_CONVERSATION_ID_KEY);
    const raw = await AsyncStorage.getItem(key);
    const id = raw ? Number(raw) : NaN;
    return Number.isFinite(id) && id > 0 ? id : null;
  } catch {
    return null;
  }
}

async function rememberConversationId(id: number | undefined | null): Promise<void> {
  if (!id) return;
  try {
    await AsyncStorage.setItem(await currentChatStorageKey(LAST_CONVERSATION_ID_KEY), String(id));
  } catch {}
}

async function forgetConversationId(): Promise<void> {
  try {
    await AsyncStorage.removeItem(await currentChatStorageKey(LAST_CONVERSATION_ID_KEY));
  } catch {}
}

async function markPendingStream(): Promise<void> {
  try {
    await AsyncStorage.setItem(
      await currentChatStorageKey(PENDING_STREAM_STARTED_AT_KEY),
      String(Date.now()),
    );
  } catch {}
}

async function clearPendingStream(): Promise<void> {
  try {
    await AsyncStorage.removeItem(await currentChatStorageKey(PENDING_STREAM_STARTED_AT_KEY));
  } catch {}
}

async function hasFreshPendingStream(): Promise<boolean> {
  try {
    const raw = await AsyncStorage.getItem(
      await currentChatStorageKey(PENDING_STREAM_STARTED_AT_KEY),
    );
    const startedAt = raw ? Number(raw) : NaN;
    return Number.isFinite(startedAt) && Date.now() - startedAt < PENDING_STREAM_TTL_MS;
  } catch {
    return false;
  }
}

export function useChatEngine(opts: UseChatEngineOptions = {}) {
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const messagesRef = useRef<UIMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [queuedCount, setQueuedCount] = useState(0);
  const [runningTurnId, setRunningTurnId] = useState<string | undefined>(undefined);
  const [activeTurn, reduceAgentTurnDispatch] = useReducer(reduceAgentTurn, undefined, createIdleAgentTurn);
  const activeTurnRef = useRef(activeTurn);
  const queuedTurnsRef = useRef<QueuedChatTurn[]>([]);
  const pumpQueuedTurnsRef = useRef<() => void>(() => undefined);
  const isStreamingRef = useRef(false);
  const runningTurnIdRef = useRef<string | undefined>(undefined);
  const terminalTelemetryKeysRef = useRef<Set<string>>(new Set());
  const emitAgentTurnTerminal = useCallback((
    turnId: string,
    startedAt: number,
    phase: 'completed' | 'failed' | 'interrupted',
    errorCode?: string,
  ) => {
    const key = `${turnId}:${phase}`;
    if (terminalTelemetryKeysRef.current.has(key)) return;
    terminalTelemetryKeysRef.current.add(key);
    if (terminalTelemetryKeysRef.current.size > 200) {
      const oldest = terminalTelemetryKeysRef.current.values().next().value;
      if (oldest) terminalTelemetryKeysRef.current.delete(oldest);
    }
    void emitClientEvent('agent_turn_terminal', {
      phase,
      duration_bucket: durationBucket(startedAt),
      ...(errorCode ? { error_code: errorCode } : {}),
    });
  }, []);
  const hydrationGateRef = useRef<{ promise: Promise<void>; resolve: () => void } | null>(null);
  if (!hydrationGateRef.current) {
    let resolve!: () => void;
    const promise = new Promise<void>((ready) => { resolve = ready; });
    hydrationGateRef.current = { promise, resolve };
  }
  const dispatchAgentTurn = useCallback((event: AgentTurnEvent): AgentTurnState => {
    const next = reduceAgentTurn(activeTurnRef.current, event);
    activeTurnRef.current = next;
    reduceAgentTurnDispatch(event);
    return next;
  }, []);
  const [activeTurnHydrated, setActiveTurnHydrated] = useState(false);
  const [conversationId, setConversationId] = useState<number | undefined>(undefined);
  const conversationIdRef = useRef<number | undefined>(undefined);
  const [windowDays, setWindowDays] = useState<number | undefined>(DEFAULT_WINDOW_DAYS);
  const [hasMoreHistory, setHasMoreHistory] = useState(false);
  const briefingInjected = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => { activeTurnRef.current = activeTurn; }, [activeTurn]);
  useEffect(() => { messagesRef.current = messages; }, [messages]);
  useEffect(() => { isStreamingRef.current = isStreaming; }, [isStreaming]);
  useEffect(() => { runningTurnIdRef.current = runningTurnId; }, [runningTurnId]);
  useEffect(() => { conversationIdRef.current = conversationId; }, [conversationId]);

  useEffect(() => {
    let cancelled = false;
    void currentChatStorageKey(ACTIVE_TURN_KEY).then(async (key) => {
      await AsyncStorage.removeItem(ACTIVE_TURN_KEY);
      return { key, raw: await AsyncStorage.getItem(key) };
    }).then(({ key, raw }) => {
      if (cancelled) return;
      const stored = parseStoredAgentTurn(raw);
      if (stored && stored.phase !== 'idle' && stored.phase !== 'completed') {
        dispatchAgentTurn({ type: 'hydrate', snapshot: stored });
      } else if (raw) {
        void AsyncStorage.removeItem(key);
      }
    }).finally(() => {
      if (!cancelled) {
        setActiveTurnHydrated(true);
        hydrationGateRef.current?.resolve();
      }
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!activeTurnHydrated) return;
    void currentChatStorageKey(ACTIVE_TURN_KEY).then((key) => {
      if (activeTurn.turnId && activeTurn.recoverable && activeTurn.phase !== 'completed') {
        return AsyncStorage.setItem(key, JSON.stringify(activeTurn));
      }
      return AsyncStorage.removeItem(key);
    }).catch(() => undefined);
  }, [activeTurn, activeTurnHydrated]);
  // 2026-05-14: 标记是否有正在进行的 stream — 离开页面回来时, 如果还在 stream
  // 后端 G-W9 bg task 还在跑), 重新 fetch 拉服务端最新消息.
  const streamingRef = useRef(false);
  // P0-5 竞态守卫: 本地 stream 开始时间 (ms epoch)。stream 结束 (done/error/finally) 清 0。
  // localStreamOwnsState() 据此判断"活跃且 <30s"→ 服务端 reload 必须让位, 不覆盖本地流式态。
  const streamStartedAtRef = useRef(0);
  const localStreamOwnsState = useCallback(() => {
    if (!streamingRef.current) return false;
    const startedAt = streamStartedAtRef.current;
    if (!startedAt) return true; // 刚置 streaming、时间戳尚未落 → 保守持有本地态
    return Date.now() - startedAt < LOCAL_STREAM_HOLD_MS;
  }, []);

  // 2026-05-16 FIX: messages.length 不能直接进 useFocusEffect/AppState 的 deps.
  // 当 sendMessage 把 [userMsg, aiMsg] push 进 list, length 0→2 → callback 重建 →
  // useFocusEffect 紧接着触发 reloadCurrentFromServer → 服务端那时还没写完 AI 响应,
  // 只有 user 消息, 把本地的 streaming aiMsg 整个覆盖掉, UI 永远停在"只有用户气泡".
  // 用 ref 读取最新 length, 让 effect 只在 focus / app-state 切换时触发.
  const messagesLengthRef = useRef(0);
  useEffect(() => { messagesLengthRef.current = messages.length; }, [messages.length]);

  // 2026-05-14 FIX-4: 不在 unmount 时 abort.
  // 用户切 tab / 进 SNP 详情时, useChatEngine 的 host (chat tab) 可能 unmount,
  // 之前 cleanup 会 abort SSE, 后端 G-W9 bg task 也跟着断 (HTTPClient 已断流).
  // 改为: 让 fetch promise 自然完成, 依靠 navigation focus 回来时 reloadCurrentFromServer
  // 把后端写入的最终消息拉回前端显示.
  useEffect(() => () => { /* no-op: 不在 unmount 时 abort */ }, []);

  const reconcileActiveTurnFromServer = useCallback((id: number, msgs: any[]) => {
    const current = activeTurnRef.current;
    if (!current.turnId || !current.recoverable) return;
    if (current.conversationId && current.conversationId !== id) return;

    const assistant = assistantMessageForTurn(msgs, current.turnId);
    if (!assistant) {
      dispatchAgentTurn({
        type: 'recover',
        serverStatus: 'running',
        conversationId: id,
        at: Date.now(),
      });
      return;
    }

    const completionStatus = assistant?.meta?.completion_status;
    const recoveredReceipts = normalizeWriteReceipts(assistant?.meta?.write_receipts) || [];
    const recoveredWrite = recoveredReceipts.length > 0;
    const missingWriteReceipt = current.hadWrite && !recoveredWrite;
    if (recoveredWrite) {
      void rememberVerifiedWriteReceipt(recoveredReceipts[recoveredReceipts.length - 1]).catch(() => {
        console.warn('[chat] recovered write receipt persistence failed');
      });
    }
    const recoveredStatus = completionStatus === 'interrupted'
      ? 'interrupted'
      : completionStatus === 'error' || missingWriteReceipt
        ? 'failed'
        : 'completed';
    const recoveredErrorCode = completionStatus === 'interrupted'
      ? 'stream_interrupted'
      : missingWriteReceipt
        ? 'write_receipt_missing_identity'
        : undefined;
    dispatchAgentTurn({
      type: 'recover',
      serverStatus: recoveredStatus,
      conversationId: id,
      messageId: typeof assistant.id === 'number' ? assistant.id : undefined,
      errorCode: recoveredErrorCode,
      hadWrite: current.hadWrite || recoveredWrite,
      writeVerified: recoveredWrite ? true : (current.hadWrite ? false : current.writeVerified),
      at: Date.now(),
    });
    emitAgentTurnTerminal(
      current.turnId,
      current.startedAt ?? Date.now(),
      recoveredStatus,
      recoveredErrorCode,
    );
  }, [emitAgentTurnTerminal]);

  const reloadCurrentFromServer = useCallback(async () => {
    if (!conversationId) return;
    // P0-5: 本地流式态活跃且 <30s → 让位, 不用服务端半截 partial 覆盖本地流。
    // 只有流 done/error 或超过 30s (慢流/卡死) 后才放行服务端恢复。
    if (localStreamOwnsState()) return;
    try {
      const { messages: msgs, total_messages } = await getConversationMessages(
        conversationId, { days: windowDays || DEFAULT_WINDOW_DAYS }
      );
      // 网络往返期间流可能又启动了 (用户快速再发一条) → 二次核查, 仍活跃则丢弃这次结果。
      if (localStreamOwnsState()) return;
      setHasMoreHistory(total_messages > msgs.length);
      if (msgs.length === 0) return;
      const restored = restoreMessagesFromHistory(msgs, IMAGE_HOST, 'hist');
      setMessages(restored);
      setIsStreaming(false);  // 清掉 streaming 残留态
      reconcileActiveTurnFromServer(conversationId, msgs);
    } catch {
      // 网络失败不影响现有 UI
    }
  }, [conversationId, windowDays, reconcileActiveTurnFromServer]);

  const restoreCards = useCallback(async (restored: UIMessage[]) => {
    const userMsgs = restored.filter(m => m.role === 'user' && m.content);
    for (const um of userMsgs) {
      try {
        const card = await dispatchCard({
          query: um.content,
          query_lower: um.content.toLowerCase(),
          toolsUsed: new Set(),
          data: {},
          api,
        });
        if (card) {
          setMessages(prev => {
            const idx = prev.findIndex(m => m.id === um.id);
            if (idx < 0 || prev.find((m, j) => j > idx && m.cardType)) return prev;
            const cardMsg: UIMessage = { id: `card-${um.id}`, role: 'assistant', content: '', cardType: card.type, cardData: card.data };
            const insertAt = Math.min(idx + 2, prev.length);
            return [...prev.slice(0, insertAt), cardMsg, ...prev.slice(insertAt)];
          });
        }
      } catch { console.warn('Card dispatch failed for restored message'); }
    }
  }, []);

  const recoverConversationFromServer = useCallback(async (id: number, expectedTurnId?: string) => {
    try {
      const { messages: msgs, total_messages } = await getConversationMessages(
        id,
        { days: windowDays || DEFAULT_WINDOW_DAYS },
      );
      const turnId = expectedTurnId || activeTurnRef.current.turnId;
      if (!turnId) return false;
      const assistantAnswer = assistantMessageForTurn(msgs, turnId);
      if (!assistantAnswer) return false;

      conversationIdRef.current = id;
      setConversationId(id);
      void rememberConversationId(id);
      setHasMoreHistory(total_messages > msgs.length);
      const restored = restoreMessagesFromHistory(msgs, IMAGE_HOST, 'hist');
      setMessages(restored);
      restoreCards(restored);
      reconcileActiveTurnFromServer(id, msgs);
      const completionStatus = (assistantAnswer as any)?.meta?.completion_status;
      const recoveredReceipts = normalizeWriteReceipts((assistantAnswer as any)?.meta?.write_receipts) || [];
      const current = activeTurnRef.current;
      const missingWriteReceipt = current.turnId === turnId && current.hadWrite && recoveredReceipts.length === 0;
      return {
        completionStatus: typeof completionStatus === 'string'
          ? completionStatus
          : undefined,
        terminalPhase: completionStatus === 'error' || missingWriteReceipt
          ? 'failed' as const
          : completionStatus === 'interrupted'
            ? 'interrupted' as const
            : 'completed' as const,
      };
    } catch {
      return false;
    }
  }, [reconcileActiveTurnFromServer, restoreCards, windowDays]);

  const loadConversationFromServer = useCallback(async (id: number, idPrefix: string = 'hist') => {
    const { messages: msgs, total_messages } = await getConversationMessages(id, { days: DEFAULT_WINDOW_DAYS });
    setWindowDays(DEFAULT_WINDOW_DAYS);
    setHasMoreHistory(total_messages > msgs.length);
    if (msgs.length === 0 && total_messages === 0) return false;

    conversationIdRef.current = id;
    setConversationId(id);
    void rememberConversationId(id);
    const restored = restoreMessagesFromHistory(msgs, IMAGE_HOST, idPrefix);
    setMessages(restored);
    restoreCards(restored);
    reconcileActiveTurnFromServer(id, msgs);
    return true;
  }, [reconcileActiveTurnFromServer, restoreCards]);

  const loadLatestConversation = useCallback(async (options?: { preferBriefing?: boolean }) => {
    await hydrationGateRef.current?.promise;
    // P0-5: 本地流式态活跃且 <30s → 不拉服务端最近对话覆盖当前流。
    if (localStreamOwnsState()) return;
    try {
      const preferBriefing = options?.preferBriefing ?? true;
      const storedConversationId = await readStoredConversationId();
      if (storedConversationId) {
        const restoredStoredConversation = await loadConversationFromServer(storedConversationId, 'hist');
        if (restoredStoredConversation || localStreamOwnsState()) return;
        await forgetConversationId();
      }

      const shouldPreferRecent = await hasFreshPendingStream();
      // 默认进入 chat tab 时优先打开"每日健康简报"；但从后台/其它 tab 恢复未完成新会话时,
      // 必须按真实最近对话找，否则会被旧简报抢走，导致用户看不到刚才那次 Agent 回复。
      let convs = preferBriefing && !shouldPreferRecent ? await getConversations(BRIEFING_CONVERSATION_TITLE) : [];
      if (convs.length === 0) convs = await getConversations();
      convs = [...convs].sort((a: any, b: any) =>
        ((b as any).updated_at || b.created_at || '').localeCompare(
          ((a as any).updated_at || a.created_at || '') as string
        )
      );
      if (convs.length === 0) return;
      if (localStreamOwnsState()) return;

      const latestId = convs[0].id;
      await loadConversationFromServer(latestId, 'hist');
    } catch { console.warn('Failed to load latest conversation'); }
  }, [loadConversationFromServer, localStreamOwnsState]);

  // AppState: App 回前台时, 如果当前消息有 streaming 态但 iOS 已切到 background
  // 30s+ 把 stream 杀掉了, 客户端本地是残缺消息. 服务端 Agent stream
  // 会持续跑并把最终 message 写 conversation. 这里 active 时重新拉服务端最新消息
  // 把断掉的 AI 回复补齐.
  const appStateRef = useRef(AppState.currentState);
  useEffect(() => {
    const sub = AppState.addEventListener('change', (next) => {
      const prev = appStateRef.current;
      appStateRef.current = next;
      if ((prev === 'background' || prev === 'inactive') && next === 'active') {
        // P0-5: 活跃本地流 (<30s) 持有本地态; 流被后台杀掉后 streamingRef 已复位 → 放行恢复。
        if (localStreamOwnsState()) return;
        if (conversationId) {
          reloadCurrentFromServer();
        } else if (messagesLengthRef.current > 0) {
          loadLatestConversation({ preferBriefing: false });
        }
      }
    });
    return () => sub.remove();
  }, [conversationId, loadLatestConversation, reloadCurrentFromServer, localStreamOwnsState]);

  // 2026-05-14 FIX-4 / 2026-05-15 resume: chat tab 重获 focus 时拉最新.
  // 新会话首次发送时 conversationId 可能在 done 前尚未回填；这种情况下按"最近对话"
  // 拉取, 避免用户切走后后台 task 已落库但 UI 永远停在本地 streaming placeholder。
  useFocusEffect(
    useCallback(() => {
      // P0-5: 本地流式态活跃且 <30s → focus 回来不拉服务端, 让本地流继续拥有 UI。
      // 只有流 done/error 或超过 30s (慢流/卡死) 后, focus reload 才允许服务端覆盖。
      if (localStreamOwnsState()) {
        return () => { /* active stream owns local state; avoid overwriting it with partial server history */ };
      }
      if (conversationId) {
        reloadCurrentFromServer();
      } else if (messagesLengthRef.current > 0) {
        loadLatestConversation({ preferBriefing: false });
      }
      return () => { /* unfocus 时不动 */ };
    }, [conversationId, loadLatestConversation, reloadCurrentFromServer, localStreamOwnsState])
  );

  const loadConversation = useCallback(async (id: number) => {
    try {
      const loaded = await loadConversationFromServer(id, 'h');
      if (!loaded) throw new Error('加载对话失败');
    } catch { throw new Error('加载对话失败'); }
  }, [loadConversationFromServer]);

  const loadMoreHistory = useCallback(async () => {
    if (!conversationId || !hasMoreHistory) return;
    const nextDays = (windowDays || DEFAULT_WINDOW_DAYS) + 14;
    try {
      const { messages: msgs, total_messages } = await getConversationMessages(conversationId, { days: nextDays });
      setWindowDays(nextDays);
      setHasMoreHistory(total_messages > msgs.length);
      const restored = restoreMessagesFromHistory(msgs, IMAGE_HOST, 'h');
      setMessages(restored);
      restoreCards(restored);
    } catch { console.warn('loadMoreHistory failed'); }
  }, [conversationId, hasMoreHistory, restoreCards, windowDays]);

  const sendMessage = useCallback(async (
    text: string,
    pendingImages?: { uri: string; base64?: string; type?: string }[] | null,
    sendOpts?: SendMessageOptions,
  ) => {
    let acceptanceSettled = false;
    let acceptedByServer = false;
    const settleAcceptance = (accepted: boolean) => {
      if (acceptanceSettled) return;
      acceptanceSettled = true;
      acceptedByServer = accepted;
      sendOpts?.onAccepted?.(accepted);
    };
    const msg = text.trim();
    const hasImages = pendingImages && pendingImages.length > 0;
    if (!msg && !hasImages) {
      settleAcceptance(false);
      return false;
    }

    const finalMsg = msg || (hasImages ? '请分析这些图片' : '');
    const requestFingerprint = buildTurnRequestFingerprint(finalMsg, pendingImages);
    const forceNewConversation = !!sendOpts?.forceNewConversation;
    const previousTurn = activeTurnRef.current;
    const reusableTurnId = (
      !forceNewConversation
      && previousTurn.recoverable
      && previousTurn.turnId
      && previousTurn.requestFingerprint === requestFingerprint
    ) ? previousTurn.turnId : undefined;
    const turnId = sendOpts?.__queuedTurnId ?? reusableTurnId ?? nextTurnId();
    const uris = hasImages ? pendingImages.map(i => i.uri) : undefined;
    const reusableUserMessage = reusableTurnId
      ? findReusableTurnMessage(messagesRef.current, 'user', reusableTurnId)
      : undefined;
    const reusableAssistantMessage = reusableTurnId
      ? findReusableTurnMessage(messagesRef.current, 'assistant', reusableTurnId)
      : undefined;

    if (isStreamingRef.current && !sendOpts?.__precreatedLocalMessages) {
      const userMessageId = nextId();
      const assistantMessageId = nextId();
      const uris = hasImages ? pendingImages.map(i => i.uri) : undefined;
      const queuedUserMsg: UIMessage = {
        id: userMessageId,
        role: 'user',
        content: finalMsg,
        imageUris: uris,
        fromSiri: sendOpts?.fromSiri,
        sourceTurnId: turnId,
      };
      const queuedAssistantMsg: UIMessage = {
        id: assistantMessageId,
        role: 'assistant',
        content: QUEUED_TURN_PLACEHOLDER,
        currentStatus: '排队中',
        sourceTurnId: turnId,
      };
      queuedTurnsRef.current.push({
        turnId,
        text: finalMsg,
        pendingImages,
        userMessageId,
        assistantMessageId,
        options: {
          ...sendOpts,
          onAccepted: undefined,
          __queuedTurnId: turnId,
          __localUserMessageId: userMessageId,
          __localAssistantMessageId: assistantMessageId,
          __precreatedLocalMessages: true,
        },
      });
      setQueuedCount(queuedTurnsRef.current.length);
      setMessages(prev => [...prev, queuedUserMsg, queuedAssistantMsg]);
      try {
        emitClientEvent('chat_turn_queued', {
          surface: 'mobile',
          channel: sendOpts?.fromSiri ? 'siri' : (sendOpts?.channel ?? 'typed'),
          queue_depth_at_submit: queuedTurnsRef.current.length,
        });
      } catch { /* noop */ }
      settleAcceptance(true);
      return true;
    }

    const turnStartedAt = Date.now();
    const emitAgentTerminal = (
      phase: 'completed' | 'failed' | 'interrupted',
      errorCode?: string,
    ) => {
      emitAgentTurnTerminal(turnId, turnStartedAt, phase, errorCode);
    };
    dispatchAgentTurn({
      type: 'submit',
      turnId,
      at: turnStartedAt,
      requestFingerprint,
      label: '正在提交…',
    });

    let isConnected: boolean | null = null;
    try {
      isConnected = (await NetInfo.fetch()).isConnected;
    } catch {
      if (__DEV__) console.warn('[chat] network status probe failed; attempting request');
    }
    if (isConnected === false) {
      const offlineUserMessage: UIMessage = {
        id: sendOpts?.__localUserMessageId ?? reusableUserMessage?.id ?? nextId(),
        role: 'user',
        content: finalMsg,
        imageUris: uris,
        fromSiri: sendOpts?.fromSiri,
        sourceTurnId: turnId,
      };
      const errMsg: UIMessage = {
        id: sendOpts?.__localAssistantMessageId
          ?? reusableAssistantMessage?.id
          ?? nextId(),
        role: 'assistant',
        content: '⚠️ 网络不可用，请检查网络连接后重试',
        sourceTurnId: turnId,
      };
      setMessages(prev => upsertOptimisticTurnPair(
        prev,
        reusableTurnId,
        offlineUserMessage,
        errMsg,
      ));
      dispatchAgentTurn({
        type: 'fail',
        at: Date.now(),
        errorCode: 'network_unavailable',
        label: '网络不可用',
        recoverable: true,
      });
      emitAgentTerminal('failed', 'network_unavailable');
      settleAcceptance(false);
      return false;
    }

    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);

    // Phase 0.4: 埋点 — 用户实际发出的对话, 区分入口 (siri vs chat)
    const inputChannel: 'typed' | 'voice' | 'siri' = sendOpts?.fromSiri
      ? 'siri'
      : (sendOpts?.channel ?? 'typed');
    try {
      emitClientEvent('chat_message_sent', {
        source: inputChannel === 'typed' ? 'chat' : inputChannel,
        has_image: !!hasImages,
      });
    } catch { /* noop */ }

    const targetConversationId = forceNewConversation ? undefined : conversationIdRef.current;
    if (forceNewConversation) {
      conversationIdRef.current = undefined;
      setConversationId(undefined);
      void forgetConversationId();
      void clearPendingStream();
      briefingInjected.current = false;
    }

    const userMsg: UIMessage = {
      id: sendOpts?.__localUserMessageId ?? reusableUserMessage?.id ?? nextId(),
      role: 'user',
      content: finalMsg,
      imageUris: uris,
      fromSiri: sendOpts?.fromSiri,
      sourceTurnId: turnId,
    };
    const aId = sendOpts?.__localAssistantMessageId
      ?? reusableAssistantMessage?.id
      ?? nextId();
    const aiMsg: UIMessage = {
      id: aId,
      role: 'assistant',
      content: THINKING_PLACEHOLDER,
      streaming: true,
      thinkingSteps: ['正在理解你的问题'],
      sourceTurnId: turnId,
    };

    if (sendOpts?.__precreatedLocalMessages) {
      setMessages(prev => {
        if (forceNewConversation) return [userMsg, aiMsg];
        return prev.map(message => {
          if (message.id === userMsg.id) return userMsg;
          if (message.id === aId) return aiMsg;
          return message;
        });
      });
    } else {
      setMessages((prev) => {
        if (forceNewConversation) return [userMsg, aiMsg];
        return upsertOptimisticTurnPair(prev, reusableTurnId, userMsg, aiMsg);
      });
    }
    setIsStreaming(true);
    isStreamingRef.current = true;
    setRunningTurnId(turnId);
    runningTurnIdRef.current = turnId;
    streamingRef.current = true;
    streamStartedAtRef.current = Date.now();  // P0-5: 记录流开始时刻, 供 30s 竞态守卫。
    void markPendingStream();

    const ac = new AbortController();
    abortRef.current = ac;

    let pendingContinuityReceipt: Awaited<ReturnType<typeof loadPendingWriteReceipt>>;
    try {
      pendingContinuityReceipt = await loadPendingWriteReceipt();
    } catch {
      console.warn('[chat] continuity receipt restore failed');
    }
    const outboundExtraContext = mergeConversationContinuity(
      sendOpts?.extraContext,
      pendingContinuityReceipt,
    );
    let continuityAcknowledged = false;
    const acknowledgeContinuityOnce = async () => {
      if (!pendingContinuityReceipt || continuityAcknowledged) return;
      continuityAcknowledged = true;
      try {
        await acknowledgePendingWriteReceipt(pendingContinuityReceipt.operationId);
      } catch {
        console.warn('[chat] continuity receipt acknowledgement failed');
      }
    };

    let gotFirstToken = false;
    const slowTimer = setTimeout(() => {
      if (!gotFirstToken) {
        setMessages(prev => prev.map(m => m.id === aId && !m.content ? { ...m, content: THINKING_PLACEHOLDER } : m));
      }
    }, 8000);

    let streamConversationId = targetConversationId;
    let keepPendingStreamForRecovery = false;
    const writeToolStartedAt = new Map<string, number>();
    const emitRecoveredTerminal = (phase: 'completed' | 'failed' | 'interrupted') => {
      if (phase === 'failed') {
        emitAgentTerminal('failed', 'recovered_server_error');
      } else if (phase === 'interrupted') {
        emitAgentTerminal('interrupted', 'recovered_server_interrupted');
      } else {
        emitAgentTerminal('completed');
      }
    };
    const scheduleServerRecovery = (conversationToRecover: number) => {
      [1500, 4000, 9000].forEach((delayMs) => {
        const timer = setTimeout(() => {
          const current = activeTurnRef.current;
          if (current.turnId !== turnId || current.phase === 'completed') return;
          void recoverConversationFromServer(conversationToRecover, turnId).then((recovered) => {
            if (recovered) emitRecoveredTerminal(recovered.terminalPhase);
          });
        }, delayMs);
        (timer as any)?.unref?.();
      });
    };

    // Token 攒批: 快路由 (deepseek-v4-flash) 后每个 SSE chunk 到达快得多, 逐 chunk
    // setMessages 全数组 map 是热点. 累积到缓冲, 每 ~80ms flush 一次; done/error/card/
    // 循环结束/异常 前都强制 flush → 不丢字、不改消息顺序 (缓冲按到达顺序追加, 整块合并).
    // 声明在 try 外, 让 catch 也能收尾 flush 已接收内容 (避免异常吞掉最后一批).
    let pendingTokenText = '';
    let tokenFlushTimer: ReturnType<typeof setTimeout> | null = null;
    // 取出并清空 token 缓冲 (含 timer), 不自己 setMessages —— 让调用方把这最后一批
    // 折进同一次 setMessages。done 收尾要用它保证「落最后内容」与「streaming:false」
    // 在同一帧原子完成: 否则 flushTokenBuffer 与 finally 的 streaming:false 是两次
    // 独立 setMessages, done 首帧可能 streaming 已翻 false 但 content 还是半量 →
    // renderedMarkdown memo 拿旧内容, 首帧渲染成生 markdown, 下一次 setState 才刷对。
    const drainPendingTokenText = () => {
      if (tokenFlushTimer) { clearTimeout(tokenFlushTimer); tokenFlushTimer = null; }
      const batch = pendingTokenText;
      pendingTokenText = '';
      return batch;
    };
    const flushTokenBuffer = () => {
      const batch = drainPendingTokenText();
      if (!batch) return;
      setMessages(prev => prev.map(m => m.id === aId ? { ...m, content: mergeAssistantStreamContent(m.content, batch) } : m));
    };

    // P0-1 思考面板节流: thought 事件在快路由下密集到达, 逐事件全量 setMessages map 打满 JS 线程。
    // 攒到最新一批 thought, 每 >=200ms flush 一次 (append 去重, 上限 MAX_THINKING_STEPS)。
    // done/error/循环结束/异常前强制 flush → 不丢最后一步。声明在 try 外, 让 catch/finally 也能收尾。
    const pendingThoughts: string[] = [];
    let thinkingFlushTimer: ReturnType<typeof setTimeout> | null = null;
    const flushThinkingBuffer = () => {
      if (thinkingFlushTimer) { clearTimeout(thinkingFlushTimer); thinkingFlushTimer = null; }
      if (pendingThoughts.length === 0) return;
      const batch = pendingThoughts.splice(0, pendingThoughts.length);
      setMessages(prev => prev.map(m => {
        if (m.id !== aId) return m;
        let steps = m.thinkingSteps;
        for (const t of batch) steps = appendThinkingStep(steps, t);
        return steps === m.thinkingSteps ? m : { ...m, thinkingSteps: steps };
      }));
    };
    const queueThought = (thought: string) => {
      pendingThoughts.push(thought);
      if (!thinkingFlushTimer) {
        thinkingFlushTimer = setTimeout(flushThinkingBuffer, THINKING_FLUSH_MS);
      }
    };

    try {
      const toolsUsed: Set<string> = new Set();
      const streamedCardKeys: Set<string> = new Set();
      let renderedStreamedServerCard = false;
      const removeStreamedTurnCards = () => {
        setMessages(prev => prev.filter(
          message => !message.cardType || message.sourceTurnId !== turnId,
        ));
      };
      let sawDone = false;
      let sawError = false;
      for await (const evt of streamChat(
        finalMsg,
        targetConversationId,
        hasImages ? pendingImages : undefined,
        ac.signal,
        outboundExtraContext,
        inputChannel,
        turnId,
      )) {
        if (evt.thought) {
          // 节流进思考面板 (>=200ms 一批), 不逐事件 setMessages。
          queueThought(evt.thought);
        }
        if (evt.type === 'start') {
          // The backend emits agent_start only after the user message commit.
          // Some older gateways can omit request_persisted from the client
          // stream, so a start carrying its conversation id is also durable
          // acceptance evidence. Reply completion remains a separate state:
          // a later stream interruption must not invite a duplicate submit.
          if (typeof evt.conversationId === 'number') {
            settleAcceptance(true);
            await acknowledgeContinuityOnce();
          }
          dispatchAgentTurn({
            type: 'accepted',
            at: Date.now(),
            conversationId: evt.conversationId,
            label: evt.thought || '正在理解…',
          });
          if (evt.conversationId) {
            streamConversationId = evt.conversationId;
            if (!targetConversationId) {
              conversationIdRef.current = evt.conversationId;
              setConversationId(evt.conversationId);
            }
            void rememberConversationId(evt.conversationId);
          }
        } else if (evt.type === 'persisted') {
          if (evt.clientTurnId !== turnId) {
            console.warn('[chat] ignored mismatched persistence acknowledgement');
            continue;
          }
          if (evt.imageUrls?.length) {
            const persistedImageUris = evt.imageUrls
              .map(uri => absolutizeHistoryImageUri(uri, IMAGE_HOST))
              .filter((uri): uri is string => !!uri);
            setMessages(prev => prev.map(m => (
              m.id === userMsg.id ? { ...m, imageUris: persistedImageUris } : m
            )));
          }
          settleAcceptance(true);
          await acknowledgeContinuityOnce();
          dispatchAgentTurn({
            type: 'accepted',
            at: Date.now(),
            conversationId: evt.conversationId,
            label: '请求已保存，正在处理…',
          });
          if (evt.conversationId) {
            streamConversationId = evt.conversationId;
            if (!targetConversationId) {
              conversationIdRef.current = evt.conversationId;
              setConversationId(evt.conversationId);
            }
            void rememberConversationId(evt.conversationId);
          }
        } else if (evt.type === 'status') {
          dispatchAgentTurn({
            type: 'status',
            at: Date.now(),
            stage: evt.statusStage,
            label: evt.statusLabel,
          });
          // P0-1 (刀⑤): status 事件 → 气泡顶部单行状态。首 token 前才有意义,
          // 首 token 到达后清空 (见下方 token 分支)。只在还没出正文时更新, 避免正文中途回退状态行。
          if (!gotFirstToken && evt.statusLabel) {
            const label = evt.statusLabel;
            setMessages(prev => prev.map(m => (
              m.id === aId && m.currentStatus !== label ? { ...m, currentStatus: label } : m
            )));
          }
        } else if (evt.type === 'token' || evt.type === 'tool') {
          if (evt.type === 'tool' && evt.toolName) {
              if (typeof evt.toolSuccess === 'boolean') {
                const writes = evt.writeAttempted
                  ?? (evt.toolName === 'health_record' && evt.writeCompleted !== false);
              const toolSucceeded = evt.toolSuccess && (!writes || evt.writeCompleted === true);
              dispatchAgentTurn({
                type: 'tool_finished',
                at: Date.now(),
                toolName: evt.toolName,
                writes,
                success: toolSucceeded,
                receiptVerified: writes ? evt.receipt?.verified === true : undefined,
                errorCode: toolSucceeded ? undefined : 'tool_failed',
                label: evt.thought,
              });
              if (writes && toolSucceeded && evt.receipt?.verified === true) {
                try {
                  await rememberVerifiedWriteReceipt(evt.receipt);
                } catch {
                  console.warn('[chat] verified write receipt persistence failed');
                }
              }
              if (writes) {
                const verified = toolSucceeded && evt.receipt?.verified === true;
                void emitClientEvent('write_receipt_terminal', {
                  phase: verified ? 'verified' : (toolSucceeded ? 'unverified' : 'failed'),
                  duration_bucket: durationBucket(writeToolStartedAt.get(evt.toolName) ?? turnStartedAt),
                  action_type: evt.toolName,
                  verified,
                  ...(!verified ? {
                    error_code: toolSucceeded ? 'write_receipt_missing_identity' : 'tool_failed',
                  } : {}),
                });
              }
              writeToolStartedAt.delete(evt.toolName);
            } else {
              const writes = evt.writeAttempted ?? evt.toolName === 'health_record';
              if (writes) writeToolStartedAt.set(evt.toolName, Date.now());
              dispatchAgentTurn({
                type: 'tool_started',
                at: Date.now(),
                toolName: evt.toolName,
                writes,
                label: evt.thought,
              });
            }
          }
          // Token 是正文分片，不是完整错误消息。必须保留首尾空格和换行，否则
          // Markdown 表格/列表跨 token 边界时会被粘成一行，首次流式渲染失败。
          // 真正的 provider 错误仍由 stream-token sanitizer 安全替换。
          const incoming = sanitizeChatStreamToken(evt.content || '');
          if (incoming) {
            if (!gotFirstToken) {
              gotFirstToken = true;
              clearTimeout(slowTimer);
              // 首 token 到达: 清空 status 行 (正文开始渲染, 状态行让位)。
              setMessages(prev => prev.map(m => (
                m.id === aId && m.currentStatus ? { ...m, currentStatus: undefined } : m
              )));
            }
            pendingTokenText += incoming;
            if (!tokenFlushTimer) {
              tokenFlushTimer = setTimeout(flushTokenBuffer, 80);
            }
          }
          if (evt.toolName) toolsUsed.add(evt.toolName);
        } else if (evt.type === 'card') {
          flushTokenBuffer();
          const serverCards = renderServerCards(evt.card ? [evt.card] : []);
          const uniqueCards = serverCards.filter((card) => {
            const key = serverCardKey(card);
            if (streamedCardKeys.has(key)) return false;
            streamedCardKeys.add(key);
            return true;
          });
          if (uniqueCards.length > 0) {
            renderedStreamedServerCard = true;
            setMessages(prev => insertCardMessagesAfterAssistant(prev, aId, uniqueCards, turnId));
          }
        } else if (evt.type === 'done') {
          sawDone = true;
          const effectiveCompletionStatus = evt.requestPersisted === false
            ? 'interrupted'
            : evt.completionStatus;
          const doneProvesPersistence = (
            typeof evt.conversationId === 'number'
            && typeof evt.messageId === 'number'
          );
          if (
            evt.requestPersisted !== false
            && (acceptedByServer || doneProvesPersistence)
          ) {
            settleAcceptance(true);
            await acknowledgeContinuityOnce();
          } else {
            settleAcceptance(false);
          }
          if (evt.writeReceipts?.length) {
            const latestReceipt = evt.writeReceipts[evt.writeReceipts.length - 1];
            dispatchAgentTurn({
              type: 'tool_finished',
              at: Date.now(),
              writes: true,
              success: true,
              receiptVerified: true,
            });
            try {
              await rememberVerifiedWriteReceipt(latestReceipt);
            } catch {
              console.warn('[chat] done write receipt persistence failed');
            }
          }
          const terminalTurn = dispatchAgentTurn({
            type: 'done',
            at: Date.now(),
            completionStatus: effectiveCompletionStatus,
            conversationId: evt.conversationId,
            messageId: evt.messageId,
          });
          if (terminalTurn.phase === 'failed') {
            emitAgentTerminal('failed', terminalTurn.errorCode || 'agent_turn_failed');
          } else if (terminalTurn.phase === 'interrupted') {
            emitAgentTerminal('interrupted', terminalTurn.errorCode || 'server_completion_interrupted');
          } else if (terminalTurn.phase === 'completed') {
            emitAgentTerminal('completed');
          }
          const allowDoneCards = (
            evt.requestPersisted !== false
            && terminalTurn.phase === 'completed'
            && typeof evt.messageId === 'number'
          );
          const rawDoneCards = (
            allowDoneCards && Array.isArray((evt as any).cards)
          ) ? (evt as any).cards : [];
          const terminalServerCards = renderServerCards(rawDoneCards);
          const terminalCard = terminalServerCards.length === 1
            ? terminalServerCards[0]
            : terminalServerCards.length > 1
              ? { type: 'cards_group', data: { cards: terminalServerCards }, actions: [] }
              : undefined;
          // done 收尾原子性: 把 token 缓冲里最后一批一起折进这次 setMessages, 且同帧
          // 把 streaming 翻 false —— 不再靠 finally 的 streaming:false 分帧收尾。这样
          // done 首帧就是「完整内容 + streaming:false」, ChatBubble 的 renderedMarkdown
          // memo 拿到全量文本并走富 markdown, 不会先闪一帧生 markdown 再自动刷正。
          const lastBatch = drainPendingTokenText();
          flushThinkingBuffer();  // 收尾: 把节流缓冲里最后的思考步骤落盘 (done 可能覆盖为服务端权威列表)。
          if (evt.conversationId) {
            streamConversationId = evt.conversationId;
            if (!targetConversationId) {
              conversationIdRef.current = evt.conversationId;
              setConversationId(evt.conversationId);
            }
            void rememberConversationId(evt.conversationId);
          }
          // 把耗时 + 模型名写入当前 assistant 消息 (ChatBubble 渲染 footer)。清空 status 行 (收进思考完成态 pill)。
          setMessages((prev) => {
            const settled = prev
              .filter(m => (
                !m.cardType
                || m.sourceTurnId !== turnId
                || (allowDoneCards && !terminalCard)
              ))
              .map(m => m.id === aId ? {
              ...m,
              content: lastBatch ? mergeAssistantStreamContent(m.content, lastBatch) : m.content,
              streaming: false,
              currentStatus: undefined,
              elapsedMs: evt.elapsedMs,
              llmMs: evt.llmMs,
              llmRounds: evt.llmRounds,
              llmRoundsMs: evt.llmRoundsMs,
              model: evt.model,
              llmUsage: evt.llmUsage,
              perf: evt.perf,
              sourcesUsed: evt.sourcesUsed,
              toolsUsed: evt.toolsUsed,
              completionStatus: effectiveCompletionStatus,
              thinkingSteps: evt.thinkingSteps?.length ? evt.thinkingSteps : m.thinkingSteps,
              writeReceipts: evt.writeReceipts,
              } : m);
            const projected = evt.medicationBatchDecision
              ? projectMedicationTerminalMessages(settled, evt.medicationBatchDecision)
              : settled;
            if (!terminalCard) return projected;
            return [...projected, {
              id: nextId(),
              role: 'assistant' as const,
              content: '',
              cardType: terminalCard.type,
              cardData: terminalCard.data,
              cardActions: terminalCard.actions,
              sourceMessageId: evt.messageId,
              sourceTurnId: turnId,
            }];
          });
          if (allowDoneCards && !terminalCard && !renderedStreamedServerCard) {
            const card = await dispatchCard({
              query: finalMsg,
              query_lower: finalMsg.toLowerCase(),
              toolsUsed,
              data: opts.contextData || {},
              api,
            });
            if (card) {
              setMessages(prev => [...prev, {
                id: nextId(),
                role: 'assistant',
                content: '',
                cardType: card.type,
                cardData: card.data,
                sourceTurnId: turnId,
              }]);
            }
          }
        } else if (evt.type === 'error') {
          sawError = true;
          removeStreamedTurnCards();
          dispatchAgentTurn({
            type: 'fail',
            at: Date.now(),
            errorCode: 'stream_error_event',
            label: sanitizeChatErrorMessage(evt.content, '请求出错，请稍后再试'),
            recoverable: true,
          });
          emitAgentTerminal('failed', 'stream_error_event');
          flushTokenBuffer();
          flushThinkingBuffer();
          const errMsg = sanitizeChatErrorMessage(evt.content, '请求出错，请稍后再试');
          setMessages(prev => prev.map(m => m.id === aId ? {
            ...m,
            currentStatus: undefined,
            completionStatus: 'error',
            content: stripThinkingPlaceholder(m.content)
              ? stripThinkingPlaceholder(m.content) + `\n❌ ${errMsg}`
              : `❌ ${errMsg}`,
          } : m));
        }
      }
      settleAcceptance(false);
      flushTokenBuffer();
      flushThinkingBuffer();
      if (!sawDone && !sawError) {
        removeStreamedTurnCards();
        dispatchAgentTurn({ type: 'interrupt', at: Date.now(), errorCode: 'stream_ended_without_done' });
        emitAgentTerminal('interrupted', 'stream_ended_without_done');
        setMessages(prev => prev.map(m => m.id === aId ? {
          ...m,
          currentStatus: undefined,
          completionStatus: 'interrupted',
          content: stripThinkingPlaceholder(m.content)
            ? `${stripThinkingPlaceholder(m.content)}\n\n[回复中断，已保留已接收内容]`
            : '[回复中断，请重新提问]',
        } : m));
      }
    } catch (err: any) {
      flushTokenBuffer();
      flushThinkingBuffer();
      setMessages(prev => prev.filter(
        message => !message.cardType || message.sourceTurnId !== turnId,
      ));
      const isAbort = err?.message === 'aborted';
      if (streamConversationId) {
        const recovered = await recoverConversationFromServer(streamConversationId, turnId);
        if (recovered) {
          settleAcceptance(true);
          emitRecoveredTerminal(recovered.terminalPhase);
          return true;
        }
      }
      // iOS can report XHR onerror with status 200 when an accepted SSE stream is
      // suspended in the background. The request is already durable at this point,
      // so treat every post-accept transport interruption as recoverable instead of
      // surfacing a false send failure or inviting a duplicate submission.
      const isAcceptedTransportInterruption = acceptedByServer && !!streamConversationId;
      if (isAcceptedTransportInterruption && streamConversationId) {
        keepPendingStreamForRecovery = true;
        scheduleServerRecovery(streamConversationId);
        settleAcceptance(true);
        dispatchAgentTurn({
          type: 'interrupt',
          at: Date.now(),
          errorCode: isAbort ? 'app_backgrounded' : 'stream_transport_interrupted',
          label: STREAM_RECOVERY_NOTICE,
        });
        setMessages(prev => prev.map(m => {
          if (m.id !== aId) return m;
          const currentContent = stripThinkingPlaceholder(m.content).trim();
          return {
            ...m,
            currentStatus: undefined,
            completionStatus: 'interrupted',
            content: currentContent ? `${currentContent}${STREAM_RECOVERY_SUFFIX}` : STREAM_RECOVERY_NOTICE,
          };
        }));
        return true;
      }
      settleAcceptance(false);
      dispatchAgentTurn(isAbort
        ? { type: 'interrupt', at: Date.now(), errorCode: 'stream_aborted' }
        : {
            type: 'fail',
            at: Date.now(),
            errorCode: 'stream_request_failed',
            label: sanitizeChatErrorMessage(err?.message, '请求失败'),
            recoverable: true,
          });
      emitAgentTerminal(
        isAbort ? 'interrupted' : 'failed',
        isAbort ? 'stream_aborted' : 'stream_request_failed',
      );
      setMessages(prev => prev.map(m => m.id === aId ? {
        ...m,
        currentStatus: undefined,
        completionStatus: isAbort ? 'interrupted' : 'error',
        content: stripThinkingPlaceholder(m.content)
          ? (isAbort ? stripThinkingPlaceholder(m.content) + '\n\n[回复中断，已保留已接收内容]' : stripThinkingPlaceholder(m.content) + `\n❌ ${sanitizeChatErrorMessage(err?.message, '请求失败')}`)
          : (isAbort ? '[App 切换到后台，回复中断。请重新提问]' : `[错误] ${sanitizeChatErrorMessage(err?.message, '请求失败')}`),
      } : m));
    } finally {
      flushTokenBuffer(); // 收尾: 清残留 timer + 保证最后一批不丢字 (幂等)
      flushThinkingBuffer(); // 收尾: 清思考节流 timer + 落最后一步 (幂等)
      clearTimeout(slowTimer);
      abortRef.current = null;
      streamingRef.current = false;
      isStreamingRef.current = false;
      runningTurnIdRef.current = undefined;
      setRunningTurnId(undefined);
      streamStartedAtRef.current = 0;  // P0-5: 流结束, 解除本地态霸占 → 允许服务端 reload 恢复。
      if (keepPendingStreamForRecovery) {
        void markPendingStream();
      } else {
        void clearPendingStream();
      }
      // 终态: 停 streaming + 兜底清 status 行 (无论 done/error/interrupt 都不残留状态行)。
      setMessages(prev => prev.map(m => m.id === aId ? { ...m, streaming: false, currentStatus: undefined } : m));
      setIsStreaming(false);
      setTimeout(() => pumpQueuedTurnsRef.current(), 0);
    }
    return acceptedByServer;
  }, [opts.contextData, recoverConversationFromServer]);

  pumpQueuedTurnsRef.current = () => {
    if (isStreamingRef.current) return;
    const next = queuedTurnsRef.current.shift();
    if (!next) {
      return;
    }
    setQueuedCount(queuedTurnsRef.current.length);
    void sendMessage(next.text, next.pendingImages, next.options);
  };

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const cancelActiveTurn = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const cancelTurn = useCallback((turnId: string) => {
    if (runningTurnIdRef.current === turnId) {
      abortRef.current?.abort();
      return;
    }
    const queued = queuedTurnsRef.current.find(turn => turn.turnId === turnId);
    if (!queued) return;
    queuedTurnsRef.current = queuedTurnsRef.current.filter(turn => turn.turnId !== turnId);
    setQueuedCount(queuedTurnsRef.current.length);
    setMessages(prev => prev.filter(message => (
      message.id !== queued.userMessageId
      && message.id !== queued.assistantMessageId
    )));
  }, []);


  const newChat = useCallback(() => {
    queuedTurnsRef.current = [];
    setQueuedCount(0);
    runningTurnIdRef.current = undefined;
    setRunningTurnId(undefined);
    setMessages([]);
    conversationIdRef.current = undefined;
    setConversationId(undefined);
    dispatchAgentTurn({ type: 'reset' });
    void forgetConversationId();
    void clearPendingStream();
    void currentChatStorageKey(ACTIVE_TURN_KEY)
      .then(key => AsyncStorage.removeItem(key))
      .catch(() => undefined);
    briefingInjected.current = false;
  }, []);

  const deleteCurrentConversation = useCallback(async () => {
    if (!conversationId) return;
    await deleteConversation(conversationId);
    newChat();
  }, [conversationId, newChat]);

  return {
    messages,
    isStreaming,
    queuedCount,
    runningTurnId,
    activeTurn,
    conversationId,
    sendMessage,
    stopStreaming,
    cancelActiveTurn,
    cancelTurn,
    newChat,
    loadLatestConversation,
    loadConversation,
    loadMoreHistory,
    hasMoreHistory,
    deleteCurrentConversation,
    setMessages,
  };
}
