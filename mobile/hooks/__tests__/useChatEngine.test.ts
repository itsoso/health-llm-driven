import { act, renderHook, waitFor } from '@testing-library/react-native';
import { AppState } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

const mockStreamChat = jest.fn();
const mockGetConversations = jest.fn();
const mockGetConversationMessages = jest.fn();
const mockDeleteConversation = jest.fn();
const mockRenderServerCards = jest.fn();
const mockDispatchCard = jest.fn().mockResolvedValue(null);
const mockEmitClientEvent = jest.fn().mockResolvedValue(undefined);
const mockDurationBucket = jest.fn().mockReturnValue('10_30s');
let mockAsyncStorage: Record<string, string> = {};
const TEST_STORAGE_SCOPE = 'user-7';
const scopedStorageKey = (base: string) => `${base}:${TEST_STORAGE_SCOPE}`;

jest.mock('../../services/authStorageScope', () => ({
  getAuthStorageScope: jest.fn().mockResolvedValue('user-7'),
}));

jest.mock('expo-router', () => ({
  useFocusEffect: (cb: any) => {
    const React = require('react');
    React.useEffect(() => cb(), [cb]);
  },
}));

jest.mock('../../services/chat', () => ({
  streamChat: (...args: any[]) => mockStreamChat(...args),
  getConversations: (...args: any[]) => mockGetConversations(...args),
  getConversationMessages: (...args: any[]) => mockGetConversationMessages(...args),
  deleteConversation: (...args: any[]) => mockDeleteConversation(...args),
}));

jest.mock('@react-native-async-storage/async-storage', () => ({
  getItem: jest.fn(async (key: string) => mockAsyncStorage[key] ?? null),
  setItem: jest.fn(async (key: string, value: string) => { mockAsyncStorage[key] = value; }),
  removeItem: jest.fn(async (key: string) => { delete mockAsyncStorage[key]; }),
}));

jest.mock('../../components/chat/cards', () => ({
  dispatchCard: (...args: any[]) => mockDispatchCard(...args),
  renderServerCards: (...args: any[]) => mockRenderServerCards(...args),
}));

jest.mock('../../services/api', () => ({
  __esModule: true,
  default: {},
  BASE_URL: 'https://example.test/api/v1',
}));

jest.mock('../../services/clientEvents', () => ({
  emitClientEvent: (...args: any[]) => mockEmitClientEvent(...args),
  durationBucket: (...args: any[]) => mockDurationBucket(...args),
}));

import {
  findReusableTurnMessage,
  restoreMessagesFromHistory,
  useChatEngine,
} from '../useChatEngine';

let finishStream: (() => void) | undefined;
let failStream: (() => void) | undefined;
let persistStream: (() => void) | undefined;

async function* streamStartThenWait() {
  yield { type: 'start', conversationId: 777 };
  await new Promise<void>((resolve) => {
    finishStream = resolve;
  });
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

async function* streamStartWaitForPersistenceThenDone(...args: any[]) {
  await new Promise<void>((resolve) => {
    persistStream = resolve;
  });
  yield { type: 'start', conversationId: 777 };
  yield {
    type: 'persisted',
    conversationId: 777,
    userMessageId: 41,
    clientTurnId: args[6],
  };
  yield { type: 'done', conversationId: 777, messageId: 42 };
}

async function* streamPersistsRelativeImageUrl(...args: any[]) {
  yield { type: 'start', conversationId: 777 };
  yield {
    type: 'persisted',
    conversationId: 777,
    userMessageId: 41,
    clientTurnId: args[6],
    imageUrls: ['/api/v1/chat/uploads/private-photo.jpg'],
  };
  yield { type: 'done', conversationId: 777, messageId: 42 };
}

async function* streamStartThenTimeout() {
  yield { type: 'start', conversationId: 777 };
  await new Promise<void>((resolve) => {
    failStream = resolve;
  });
  throw new Error('请求超时');
}

async function* streamStartThenAbort() {
  yield { type: 'start', conversationId: 777 };
  await new Promise<void>((resolve) => {
    failStream = resolve;
  });
  throw new Error('aborted');
}

async function* streamStartThenStatus200Failure() {
  yield { type: 'start', conversationId: 777 };
  await new Promise<void>((resolve) => {
    failStream = resolve;
  });
  throw new Error('网络请求失败 (status: 200)');
}

async function* streamInterruptedWithoutPersistence() {
  yield { type: 'start' };
  yield {
    type: 'done',
    conversationId: 777,
    messageId: null,
    completionStatus: 'interrupted',
  };
}

async function* streamAcceptedThenEndsWithoutDone() {
  // Compatibility path used by older gateways: agent_start is emitted only
  // after the user message has been persisted, but request_persisted may be
  // absent from the client-visible stream.
  yield { type: 'start', conversationId: 777 };
  yield { type: 'token', content: '已经收到，我正在查询。' };
}

async function* streamDoneExplicitlyNotPersisted() {
  yield { type: 'start' };
  yield {
    type: 'card',
    card: {
      type: 'diet',
      data: { items: ['不应执行'] },
      actions: [{
        id: 'unsafe-confirm',
        label: '确认记录',
        action: 'write_intent.confirm',
        endpoint: '/write-intents/999/confirm',
        payload: { write_intent_id: 999 },
        requires_manual_confirm: true,
      }],
    },
  };
  yield {
    type: 'done',
    conversationId: 777,
    messageId: 42,
    requestPersisted: false,
    completionStatus: 'complete',
    cards: [{
      type: 'diet',
      data: { items: ['也不应执行'] },
      actions: [{
        id: 'unsafe-done-confirm',
        label: '确认记录',
        action: 'write_intent.confirm',
        endpoint: '/write-intents/1000/confirm',
        payload: { write_intent_id: 1000 },
        requires_manual_confirm: true,
      }],
    }],
  };
}

async function* streamCardThenEndsWithoutDone() {
  yield { type: 'start', conversationId: 777 };
  yield {
    type: 'card',
    card: {
      type: 'diet',
      data: { items: ['中断前草稿'] },
      actions: [{
        id: 'interrupted-confirm',
        label: '确认记录',
        action: 'write_intent.confirm',
        endpoint: '/write-intents/2000/confirm',
        payload: { write_intent_id: 2000 },
        requires_manual_confirm: true,
      }],
    },
  };
}

async function* streamStartToolThenWait() {
  yield { type: 'start', conversationId: 777 };
  yield { type: 'tool', toolName: 'weather_context', content: '' };
  await new Promise<void>((resolve) => {
    finishStream = resolve;
  });
  yield { type: 'token', content: '今天户外运动建议先看空气质量。' };
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

async function* streamThoughtsThenWait() {
  yield { type: 'start', conversationId: 777, thought: '正在理解你的问题' };
  yield { type: 'tool', toolName: 'health_query', content: '', thought: '读取健康数据' };
  yield { type: 'tool', toolName: 'health_query', content: '', toolSuccess: true, thought: '已取得健康数据' };
  yield { type: 'token', content: '今晚优先固定睡眠时间。' };
  await new Promise<void>((resolve) => {
    finishStream = resolve;
  });
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

async function* streamTokenCardThenWait() {
  yield { type: 'start', conversationId: 777 };
  yield { type: 'token', content: '我先把这顿饭识别为待确认记录。' };
  yield {
    type: 'card',
    anchor: 'after-token-1',
    card: {
      type: 'diet',
      data: { items: ['鸡蛋', '牛奶'] },
      actions: [
        {
          id: 'confirm-diet',
          label: '确认记录',
          action: 'write_intent.confirm',
          endpoint: '/write-intents/12/confirm',
          payload: { write_intent_id: 12 },
          requires_manual_confirm: true,
        },
      ],
    },
  };
  await new Promise<void>((resolve) => {
    finishStream = resolve;
  });
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

const verifiedDietReceipt = {
  operationId: 'health_record:diet_record:81',
  status: 'verified',
  resourceType: 'diet_record',
  resourceId: '81',
  completedAt: '2026-07-22T12:00:00.000Z',
  verified: true,
};

function streamDietCardThenDone(cards: 'missing' | 'empty' | 'summary' | 'duplicate_summary') {
  return async function* () {
    yield { type: 'start', conversationId: 777 };
    yield {
      type: 'tool',
      toolName: 'health_record',
      toolSuccess: true,
      writeAttempted: true,
      writeCompleted: true,
      receipt: verifiedDietReceipt,
    };
    yield {
      type: 'card',
      card: {
        type: 'record_quality',
        data: { domain: 'diet', summary: '已记录旧版饮食摘要' },
        actions: [],
      },
    };
    const done: Record<string, unknown> = {
      type: 'done',
      conversationId: 777,
      messageId: 82,
      completionStatus: 'complete',
      writeReceipts: [verifiedDietReceipt],
    };
    if (cards === 'empty') done.cards = [];
    if (cards === 'summary') {
      done.cards = [{
        type: 'diet_daily_summary',
        data: { date: '2026-07-22', summary: '服务端终态新版饮食摘要' },
        actions: [],
      }];
    }
    if (cards === 'duplicate_summary') {
      done.cards = [
        {
          type: 'diet_daily_summary',
          data: { date: '2026-07-22', summary: '服务端终态新版饮食摘要' },
          actions: [],
        },
        {
          type: 'diet_daily_summary',
          data: { date: '2026-07-22', summary: '服务端终态新版饮食摘要' },
          actions: [],
        },
      ];
    }
    yield done;
  };
}

async function* streamUnrenderableDoneCard() {
  yield { type: 'start', conversationId: 777 };
  yield {
    type: 'tool',
    toolName: 'health_record',
    toolSuccess: true,
    writeAttempted: true,
    writeCompleted: true,
    receipt: verifiedDietReceipt,
  };
  yield { type: 'token', content: '饮食记录已经保存。' };
  yield {
    type: 'done',
    conversationId: 777,
    messageId: 83,
    completionStatus: 'complete',
    writeReceipts: [verifiedDietReceipt],
    cards: [{
      type: 'future_diet_card',
      data: { domain: 'diet', summary: '当前客户端尚不支持' },
      actions: [],
    }],
  };
}

async function* streamCardThenUnrenderableDoneCard() {
  yield { type: 'start', conversationId: 777 };
  yield {
    type: 'tool',
    toolName: 'health_record',
    toolSuccess: true,
    writeAttempted: true,
    writeCompleted: true,
    receipt: verifiedDietReceipt,
  };
  yield {
    type: 'card',
    card: {
      type: 'record_quality',
      data: { domain: 'diet', summary: '仅是流式 provisional 卡' },
      actions: [{
        id: 'confirm-provisional-diet',
        label: '确认记录',
        action: 'write_intent.confirm',
        payload: { write_intent_id: 99 },
        requires_manual_confirm: true,
      }],
    },
  };
  yield {
    type: 'done',
    conversationId: 777,
    messageId: 84,
    completionStatus: 'complete',
    writeReceipts: [verifiedDietReceipt],
    cards: [{
      type: 'future_diet_card',
      data: { domain: 'diet', summary: '服务端终态，当前客户端尚不支持' },
      actions: [],
    }],
  };
}

// 快路由: 一批 token 紧挨着到达 (worst case for the ~80ms 攒批 throttle).
// 攒批后终态必须是逐 token 顺序拼接, 不丢字、不乱序.
const BURST_TOKENS = ['第一', '段。', '第二', '段。', '第三', '段。', '收尾。'];
async function* streamTokenBurstThenDone() {
  yield { type: 'start', conversationId: 777 };
  for (const t of BURST_TOKENS) {
    yield { type: 'token', content: t };
  }
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

// Bug 1 原子性: 最后一批 token 紧挨 done 到达 (中间无 await gap → token flush timer
// 还没触发就进了 done)。done 收尾必须把这最后一批折进同一次 setMessages 且同帧翻
// streaming:false —— 否则 done 首帧 content 半量但 streaming 已 false, 渲染成生 markdown。
async function* streamLastTokenThenDoneAtomic() {
  yield { type: 'start', conversationId: 777 };
  yield { type: 'token', content: '## 今日状态总览 ' };
  // 最后一批, 紧接着 done, 不给 80ms flush timer 触发的机会。
  yield { type: 'token', content: '这是最后一段正文。' };
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

// Markdown 的结构字符经常刚好落在 provider token 边界。客户端必须逐字保留
// 分片首尾空白，否则表格的换行会被粘掉，直播首帧显示成生 Markdown；重新进入
// 对话读取后端完整消息时却又恢复正常。
const EXECUTABLE_ACTION_MARKDOWN_TOKENS = [
  '行动拆解（晨起记录方案）：\n',
  '| 步骤 | 操作 | 记录字段 |\n',
  '| --- | --- | --- |\n',
  '| 1 | 晨起后排空大小便 | - |\n',
  '| 2 | 脱鞋站上体重秤 | weight |',
];
async function* streamMarkdownTokenBoundariesThenDone() {
  yield { type: 'start', conversationId: 777 };
  for (const content of EXECUTABLE_ACTION_MARKDOWN_TOKENS) {
    yield { type: 'token', content };
  }
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

// 攒批后走 error 分支: 已接收 token 必须先 flush, 再拼错误尾巴.
async function* streamTokenBurstThenError() {
  yield { type: 'start', conversationId: 777 };
  yield { type: 'token', content: '开头一段' };
  yield { type: 'token', content: '还没说完' };
  yield { type: 'error', content: '请求出错，请稍后再试' };
}

async function* streamQuotaErrorAsToken() {
  yield { type: 'start', conversationId: 777, thought: '正在理解你的问题' };
  yield {
    type: 'token',
    content: "Agent 执行遇到问题: Error code: 429 - {'error': {'message': 'Your token-plan quota has been exhausted.', 'type': 'insufficient_quota', 'code': 'insufficient_quota'}}",
  };
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

// P0-5 竞态: start → conversationId 回填 (触发 focus-reload) → 已流出一段本地正文 → 暂停。
// 暂停期间服务端只有半截 (user-only)。断言本地正文不被覆盖。
async function* streamStartTokenThenWait() {
  yield { type: 'start', conversationId: 777 };
  yield { type: 'token', content: '本地流式正文，请勿覆盖。' };
  await new Promise<void>((resolve) => {
    finishStream = resolve;
  });
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

// P0-1 status 状态机: accepted → tool(label) → 首 token → done。
// 断言 currentStatus 依次变化, 首 token 到达即清空, 且 status 从不进思考步骤。
async function* streamStatusThenToken() {
  yield { type: 'start', conversationId: 777 };
  yield { type: 'status', statusLabel: '正在理解…', statusStage: 'accepted' };
  yield { type: 'status', statusLabel: '查看步数数据…', statusStage: 'tool' };
  yield { type: 'token', content: '你今天走了 8000 步。' };
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

// P0-1: status 事件在首 token 前设置 currentStatus, 暂停在 token 前, 供断言中间态。
async function* streamStatusThenWait() {
  yield { type: 'start', conversationId: 777 };
  yield { type: 'status', statusLabel: '正在理解…', statusStage: 'accepted' };
  yield { type: 'status', statusLabel: '正在整理回答…', statusStage: 'synthesis' };
  await new Promise<void>((resolve) => {
    finishStream = resolve;
  });
  yield { type: 'token', content: '整理完成。' };
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

// 未知事件容错: 混入 useChatEngine 不认识的 type, 必须静默忽略, 不污染状态、不崩。
async function* streamUnknownEventThenToken() {
  yield { type: 'start', conversationId: 777 };
  yield { type: 'mystery_future_event', payload: { anything: true } } as any;
  yield { type: 'status', statusLabel: '正在理解…', statusStage: 'accepted' };
  yield { type: 'another_unknown', foo: 'bar' } as any;
  yield { type: 'token', content: '正常回答。' };
  yield { type: 'yet_another_unknown' } as any;
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

async function* streamVerifiedWriteThenDone() {
  yield { type: 'start', conversationId: 777 };
  yield {
    type: 'tool',
    toolName: 'health_record',
    toolSuccess: true,
    writeCompleted: true,
    receipt: {
      operationId: 'health_record:diet:81',
      status: 'verified',
      resourceType: 'diet_record',
      resourceId: '81',
      completedAt: '2026-07-09T12:00:00.000Z',
      verified: true,
    },
  };
  yield { type: 'done', conversationId: 777, messageId: 2 };
}

async function* streamFailedWriteThenDone() {
  yield { type: 'start', conversationId: 777 };
  yield {
    type: 'tool',
    toolName: 'health_record',
    toolSuccess: false,
    writeAttempted: true,
    writeCompleted: false,
  };
  yield { type: 'done', conversationId: 777, messageId: 2, completionStatus: 'complete' };
}

async function* streamLegacyHealthManageQueryThenDone() {
  yield { type: 'start', conversationId: 777 };
  yield {
    type: 'tool',
    toolName: 'health_manage',
  };
  yield {
    type: 'tool',
    toolName: 'health_manage',
    toolSuccess: true,
  };
  yield { type: 'token', content: '查询完成。' };
  yield { type: 'done', conversationId: 777, messageId: 2, completionStatus: 'complete' };
}

describe('useChatEngine', () => {

  it('never reuses an older message solely because the text is identical', () => {
    const messages = [
      { id: 'old', role: 'user', content: '相同内容', sourceTurnId: 'turn-old' },
    ] as any;

    expect(findReusableTurnMessage(messages, 'user', 'turn-new')).toBeUndefined();
  });
  beforeEach(() => {
    jest.clearAllMocks();
    mockDispatchCard.mockResolvedValue(null);
    mockAsyncStorage = {};
    finishStream = undefined;
    failStream = undefined;
    persistStream = undefined;
    mockGetConversations.mockResolvedValue([]);
    mockGetConversationMessages.mockResolvedValue({ total_messages: 0, messages: [] });
    mockDeleteConversation.mockResolvedValue(true);
    mockRenderServerCards.mockImplementation((cards: any[]) => Array.isArray(cards) ? cards : []);
    (NetInfo.fetch as jest.Mock).mockResolvedValue({ isConnected: true });
    (SecureStore.getItemAsync as jest.Mock).mockImplementation(
      async (key: string) => mockAsyncStorage[key] ?? null,
    );
    (SecureStore.setItemAsync as jest.Mock).mockImplementation(
      async (key: string, value: string) => { mockAsyncStorage[key] = value; },
    );
    (SecureStore.deleteItemAsync as jest.Mock).mockImplementation(
      async (key: string) => { delete mockAsyncStorage[key]; },
    );
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('restores persisted safe thinking steps from assistant history meta', () => {
    const restored = restoreMessagesFromHistory([
      {
        id: 42,
        role: 'assistant',
        content: '今天饮食总结如下。',
        created_at: '2026-07-03T12:00:00Z',
        meta: {
          thinking_steps: ['正在理解你的问题', '读取记录信息', '整理回复中'],
          thinking_steps_kind: 'safe_progress_summary',
        },
      },
    ]);

    expect(restored[0]).toEqual(expect.objectContaining({
      role: 'assistant',
      content: '今天饮食总结如下。',
      thinkingSteps: ['正在理解你的问题', '读取记录信息', '整理回复中'],
    }));
  });

  it('restores verified write receipts from assistant history meta', () => {
    const restored = restoreMessagesFromHistory([{
      id: 51,
      role: 'assistant',
      content: '午餐已记录。',
      meta: {
        write_receipts: [{
          operation_id: 'health_record:diet_record:701',
          status: 'verified',
          resource_type: 'diet_record',
          resource_id: '701',
          completed_at: '2026-07-09T12:00:00.000Z',
          verified: true,
        }],
      },
    }]);

    expect(restored[0].writeReceipts).toEqual([expect.objectContaining({
      resourceType: 'diet_record',
      resourceId: '701',
      verified: true,
    })]);
  });

  it('restores medication terminal state, every receipt, and safety alerts onto the durable card', () => {
    const writeReceipts = [
      {
        operation_id: 'write_intent:medication_intake_batch:42:101',
        status: 'verified',
        resource_type: 'medication_log',
        resource_id: '101',
        completed_at: '2026-07-21T21:15:01-04:00',
        verified: true,
      },
      {
        operation_id: 'write_intent:medication_intake_batch:42:102',
        status: 'verified',
        resource_type: 'medication_log',
        resource_id: '102',
        completed_at: '2026-07-21T21:15:02-04:00',
        verified: true,
      },
    ];
    const safetyAlerts = [{
      rule_id: 'medication.safety_precheck_incomplete',
      category: 'medication',
      severity: { value: 3, label: 'high', label_zh: '警告' },
      title: '自动安全筛查暂未完成',
      message: '这不代表当前用药组合安全。',
    }];

    const restored = restoreMessagesFromHistory([{
      id: 61,
      role: 'assistant',
      content: '请确认记录本次服药。',
      meta: {
        medication_batch_decision: { intent_id: 42, status: 'executed' },
        write_receipts: writeReceipts,
        safety_alerts: safetyAlerts,
        cards: [{
          type: 'medication_draft',
          data: {
            items: [{ medication_name: '伊托必利' }, { medication_name: '替普瑞酮' }],
            decision_status: 'executed',
            write_receipts: writeReceipts,
            safety_alerts: safetyAlerts,
          },
          actions: [],
        }],
      },
    }]);

    expect(restored).toHaveLength(2);
    expect(restored[0].writeReceipts).toBeUndefined();
    expect(restored[1]).toEqual(expect.objectContaining({
      cardType: 'medication_draft',
      decisionStatus: 'executed',
      writeReceipts: [
        expect.objectContaining({ resourceType: 'medication_log', resourceId: '101' }),
        expect.objectContaining({ resourceType: 'medication_log', resourceId: '102' }),
      ],
      safetyAlerts,
    }));
  });

  it('restores exact namespaced medication evidence without same-turn receipt or alert contamination', () => {
    const medicationReceipt = {
      operation_id: 'write_intent:medication_intake_batch:42:101',
      status: 'verified',
      resource_type: 'medication_log',
      resource_id: '101',
      completed_at: '2026-07-21T21:15:01-04:00',
      verified: true,
    };
    const unrelatedReceipt = {
      operation_id: 'health_record:diet_record:701',
      status: 'verified',
      resource_type: 'diet_record',
      resource_id: '701',
      completed_at: '2026-07-21T21:15:00-04:00',
      verified: true,
    };
    const medicationAlert = {
      rule_id: 'ddi.medication', category: 'ddi',
      severity: { value: 3, label: 'high', label_zh: '警告' },
      title: '用药提示', message: '用药消息',
    };
    const unrelatedAlert = {
      rule_id: 'diet.unrelated', category: 'diet',
      severity: { value: 3, label: 'high', label_zh: '警告' },
      title: '饮食提示', message: '饮食消息',
    };

    const restored = restoreMessagesFromHistory([{
      id: 62,
      role: 'assistant',
      content: '已处理。',
      meta: {
        medication_batch_decision: {
          intent_id: 42,
          status: 'executed',
          write_receipts: [medicationReceipt],
          safety_alerts: [medicationAlert],
        },
        write_receipts: [unrelatedReceipt, medicationReceipt],
        safety_alerts: [unrelatedAlert, medicationAlert],
        cards: [{
          type: 'medication_draft',
          data: {
            write_intent_id: 42,
            items: [{ medication_name: '伊托必利', actual_dosage: '1粒' }],
            decision_status: 'executed',
          },
          actions: [],
        }],
      },
    }]);

    const card = restored.find(message => message.cardType === 'medication_draft');
    expect(card?.writeReceipts).toEqual([
      expect.objectContaining({ resourceType: 'medication_log', resourceId: '101' }),
    ]);
    expect(card?.safetyAlerts).toEqual([medicationAlert]);
  });

  it('projects a text-confirm done decision onto the earlier pending medication card', async () => {
    mockStreamChat.mockImplementation(async function* () {
      yield { type: 'start', conversationId: 777 };
      yield { type: 'token', content: '已记录本次服药。' };
      yield {
        type: 'done',
        conversationId: 777,
        messageId: 63,
        completionStatus: 'complete',
        cards: [],
        medicationBatchDecision: {
          intentId: 42,
          decisionStatus: 'executed',
          writeReceipts: [
            {
              operationId: 'write_intent:medication_intake_batch:42:101',
              status: 'verified', resourceType: 'medication_log', resourceId: '101',
              completedAt: '2026-07-21T21:15:01-04:00', verified: true,
            },
            {
              operationId: 'write_intent:medication_intake_batch:42:102',
              status: 'verified', resourceType: 'medication_log', resourceId: '102',
              completedAt: '2026-07-21T21:15:02-04:00', verified: true,
            },
          ],
          safetyAlerts: [{
            rule_id: 'ddi.text-confirm', category: 'ddi',
            severity: { value: 3, label: 'high', label_zh: '警告' },
            title: '文本确认安全提示', message: '完整保留批次提示。',
          }],
        },
      };
    });
    const { result } = renderHook(() => useChatEngine());
    act(() => {
      result.current.setMessages([{
        id: 'pending-medication-42',
        role: 'assistant',
        content: '请确认记录本次服药。',
        cardType: 'medication_draft',
        cardData: {
          write_intent_id: 42,
          items: [
            { medication_name: '伊托必利', actual_dosage: '1粒' },
            { medication_name: '替普瑞酮', actual_dosage: '1粒' },
          ],
        },
        cardActions: [{
          id: 'medication-batch-confirm:42',
          label: '确认记录',
          action: 'write_intent.confirm',
          endpoint: '/write-intents/42/confirm',
          payload: { write_intent_id: 42 },
        }],
      }, {
        id: 'unrelated-card',
        role: 'assistant',
        content: '',
        cardType: 'diet_draft',
        cardData: { food_items: '鸡蛋' },
      }]);
    });

    await act(async () => {
      await result.current.sendMessage('确认');
    });

    const card = result.current.messages.find(message => message.id === 'pending-medication-42');
    expect(card).toEqual(expect.objectContaining({
      decisionStatus: 'executed',
      cardActions: [],
      writeReceipts: [
        expect.objectContaining({ resourceId: '101' }),
        expect.objectContaining({ resourceId: '102' }),
      ],
      safetyAlerts: [expect.objectContaining({ rule_id: 'ddi.text-confirm' })],
    }));
    expect(card?.cardData).toEqual(expect.objectContaining({ decision_status: 'executed' }));
    expect(result.current.messages.find(message => message.id === 'unrelated-card')?.cardData)
      .toEqual({ food_items: '鸡蛋' });
  });

  it.each(['dismissed', 'expired'] as const)(
    'projects a text %s decision with no fabricated receipt',
    async (decisionStatus) => {
      mockStreamChat.mockImplementation(async function* () {
        yield { type: 'start', conversationId: 777 };
        yield {
          type: 'done', conversationId: 777, messageId: 64, cards: [],
          medicationBatchDecision: {
            intentId: 42,
            decisionStatus,
            writeReceipts: [],
            safetyAlerts: [],
          },
        };
      });
      const { result } = renderHook(() => useChatEngine());
      act(() => {
        result.current.setMessages([{
          id: 'pending-medication-42',
          role: 'assistant',
          content: '请确认。',
          cardType: 'medication_draft',
          cardData: { write_intent_id: 42, items: [{ medication_name: '伊托必利' }] },
          cardActions: [{
            label: '确认记录', action: 'write_intent.confirm',
            payload: { write_intent_id: 42 },
          }],
        }]);
      });

      await act(async () => {
        await result.current.sendMessage('确认');
      });

      const card = result.current.messages.find(message => message.id === 'pending-medication-42');
      expect(card).toEqual(expect.objectContaining({
        decisionStatus,
        cardActions: [],
      }));
      expect(card?.writeReceipts).toEqual([]);
    },
  );

  it('restores the last active conversation after the chat page is remounted', async () => {
    mockAsyncStorage[scopedStorageKey('chat:last_conversation_id:v1')] = '321';
    mockGetConversationMessages.mockResolvedValueOnce({
      total_messages: 2,
      messages: [
        { id: 1, role: 'user', content: '上一轮问题', created_at: '2026-05-22T10:00:00Z' },
        { id: 2, role: 'assistant', content: '上一轮回答', created_at: '2026-05-22T10:00:10Z' },
      ],
    });

    const { result } = renderHook(() => useChatEngine());

    await act(async () => {
      await result.current.loadLatestConversation();
    });

    await waitFor(() => {
      expect(result.current.conversationId).toBe(321);
      expect(result.current.messages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ role: 'assistant', content: '上一轮回答' }),
        ]),
      );
    });
    expect(mockGetConversationMessages).toHaveBeenCalledWith(321, { days: 7 });
    expect(mockGetConversations).not.toHaveBeenCalledWith('每日健康简报');
  });

  it('can force a context entry to start a new server conversation', async () => {
    mockAsyncStorage[scopedStorageKey('chat:last_conversation_id:v1')] = '321';
    mockGetConversationMessages.mockResolvedValueOnce({
      total_messages: 2,
      messages: [
        { id: 1, role: 'user', content: '上一轮问题', created_at: '2026-05-22T10:00:00Z' },
        { id: 2, role: 'assistant', content: '上一轮回答', created_at: '2026-05-22T10:00:10Z' },
      ],
    });
    mockStreamChat.mockImplementation(streamStartThenWait);

    const { result } = renderHook(() => useChatEngine());

    await act(async () => {
      await result.current.loadLatestConversation();
    });
    await waitFor(() => expect(result.current.conversationId).toBe(321));

    act(() => {
      void result.current.sendMessage(
        '请基于我近 7 天睡眠数据分析今晚最该调整的 3 件事。',
        null,
        { extraContext: '{"from":"sleep/7d"}', forceNewConversation: true } as any,
      );
    });

    await waitFor(() => {
      expect(mockStreamChat).toHaveBeenCalledWith(
        '请基于我近 7 天睡眠数据分析今晚最该调整的 3 件事。',
        undefined,
        undefined,
        expect.any(AbortSignal),
        '{"from":"sleep/7d"}',
        'typed',
        expect.stringMatching(/^turn-/),
      );
    });
    await act(async () => {
      finishStream?.();
      await Promise.resolve();
    });
  });

  it('shows a visible thinking assistant bubble immediately after sending', async () => {
    mockStreamChat.mockImplementation(streamStartThenWait);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('请基于杭州天气调整今天安排');
    });

    await waitFor(() => {
      expect(result.current.messages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            role: 'assistant',
            streaming: true,
            content: '⏳ AI 正在思考中...',
          }),
        ]),
      );
    });

    await act(async () => {
      finishStream?.();
      await Promise.resolve();
    });
  });

  it('accepts a second message while the current turn is still streaming', async () => {
    mockStreamChat.mockImplementation(streamStartThenWait);
    const onAccepted = jest.fn();

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('第一条先慢慢分析');
    });

    await waitFor(() => {
      expect(result.current.isStreaming).toBe(true);
      expect(mockStreamChat).toHaveBeenCalledTimes(1);
    });

    let accepted: boolean | undefined;
    await act(async () => {
      accepted = await result.current.sendMessage('第二条继续补充', null, { onAccepted } as any);
    });

    expect(accepted).toBe(true);
    expect(onAccepted).toHaveBeenCalledWith(true);
    expect(result.current.queuedCount).toBe(1);
    expect(result.current.messages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ role: 'user', content: '第二条继续补充' }),
        expect.objectContaining({ role: 'assistant', content: '小巴处理中，已加入队列。' }),
      ]),
    );
    expect(mockStreamChat).toHaveBeenCalledTimes(1);

    await act(async () => {
      finishStream?.();
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(mockStreamChat).toHaveBeenCalledTimes(2);
    });
  });

  it('tracks and persists the active Agent turn through stream completion', async () => {
    mockStreamChat.mockImplementation(streamStatusThenWait);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('我今天走了多少步');
    });

    await waitFor(() => {
      expect(result.current.activeTurn).toMatchObject({
        phase: 'running',
        conversationId: 777,
        label: '正在整理回答…',
        recoverable: true,
      });
    });
    expect(JSON.parse(mockAsyncStorage[scopedStorageKey('chat:active_turn:v1')])).toMatchObject({
      phase: 'running',
      conversationId: 777,
    });

    await act(async () => {
      finishStream?.();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(result.current.activeTurn).toMatchObject({
        phase: 'completed',
        conversationId: 777,
        messageId: 2,
        recoverable: false,
      });
    });
    await waitFor(() => {
      expect(mockAsyncStorage[scopedStorageKey('chat:active_turn:v1')]).toBeUndefined();
    });
    expect(mockEmitClientEvent).toHaveBeenCalledWith('agent_turn_terminal', {
      phase: 'completed',
      duration_bucket: '10_30s',
    });
  });

  it('continues the real request when the network status probe itself fails', async () => {
    (NetInfo.fetch as jest.Mock).mockRejectedValueOnce(new Error('netinfo unavailable'));
    mockStreamChat.mockImplementation(streamTokenBurstThenDone);
    const { result } = renderHook(() => useChatEngine());

    const onAccepted = jest.fn();
    let accepted: boolean | undefined;
    await act(async () => {
      accepted = await result.current.sendMessage('继续分析', null, { onAccepted } as any);
    });

    expect(mockStreamChat).toHaveBeenCalled();
    expect(accepted).toBe(true);
    expect(onAccepted).toHaveBeenCalledTimes(1);
    expect(onAccepted).toHaveBeenCalledWith(true);
    expect(result.current.activeTurn.phase).toBe('completed');
    expect(mockEmitClientEvent).toHaveBeenCalledWith('agent_turn_terminal', {
      phase: 'completed',
      duration_bucket: '10_30s',
    });
  });

  it('does not acknowledge or clear the composer until the server accepts the persisted turn', async () => {
    mockStreamChat.mockImplementation(streamStartWaitForPersistenceThenDone);
    const onAccepted = jest.fn();
    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('这条消息先不要清草稿', null, { onAccepted } as any);
    });

    await waitFor(() => {
      expect(mockStreamChat).toHaveBeenCalled();
    });
    expect(onAccepted).not.toHaveBeenCalled();
    expect(mockStreamChat).toHaveBeenCalledWith(
      '这条消息先不要清草稿',
      undefined,
      undefined,
      expect.anything(),
      undefined,
      'typed',
      expect.stringMatching(/^turn-/),
    );

    await act(async () => {
      persistStream?.();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(onAccepted).toHaveBeenCalledTimes(1);
      expect(onAccepted).toHaveBeenCalledWith(true);
      expect(result.current.conversationId).toBe(777);
    });
  });

  it('keeps a newly uploaded image visible when persistence returns a relative URL', async () => {
    mockStreamChat.mockImplementation(streamPersistsRelativeImageUrl);
    const { result } = renderHook(() => useChatEngine());

    await act(async () => {
      await result.current.sendMessage('请分析这张照片', [
        { uri: 'file:///private-photo.jpg', base64: 'abc123', type: 'jpeg' },
      ]);
    });

    expect(result.current.messages).toEqual(expect.arrayContaining([
      expect.objectContaining({
        role: 'user',
        imageUris: ['https://example.test/api/v1/chat/uploads/private-photo.jpg'],
      }),
    ]));
  });

  it('forwards a voice transcript as the voice transport channel', async () => {
    mockStreamChat.mockImplementation(streamTokenBurstThenDone);
    const { result } = renderHook(() => useChatEngine());

    await act(async () => {
      await result.current.sendMessage('午餐吃了鸡胸肉', null, { channel: 'voice' } as any);
    });

    expect(mockStreamChat).toHaveBeenCalledWith(
      '午餐吃了鸡胸肉',
      undefined,
      undefined,
      expect.anything(),
      undefined,
      'voice',
      expect.stringMatching(/^turn-/),
    );
    expect(mockEmitClientEvent).toHaveBeenCalledWith('chat_message_sent', {
      source: 'voice',
      has_image: false,
    });
  });

  it('rejects before acceptance when the device is known to be offline', async () => {
    (NetInfo.fetch as jest.Mock).mockResolvedValueOnce({ isConnected: false });
    const onAccepted = jest.fn();
    const { result } = renderHook(() => useChatEngine());
    let accepted: boolean | undefined;

    await act(async () => {
      accepted = await result.current.sendMessage('离线消息', null, { onAccepted } as any);
    });

    expect(accepted).toBe(false);
    expect(onAccepted).toHaveBeenCalledTimes(1);
    expect(onAccepted).toHaveBeenCalledWith(false);
    expect(mockStreamChat).not.toHaveBeenCalled();
    expect(result.current.activeTurn).toMatchObject({
      phase: 'failed',
      errorCode: 'network_unavailable',
    });
  });

  it('does not accept an interrupted done event without durable persistence evidence', async () => {
    mockStreamChat.mockImplementation(streamInterruptedWithoutPersistence);
    const onAccepted = jest.fn();
    const { result } = renderHook(() => useChatEngine());
    let accepted: boolean | undefined;

    await act(async () => {
      accepted = await result.current.sendMessage(
        '保留这条草稿',
        null,
        { onAccepted } as any,
      );
    });

    expect(accepted).toBe(false);
    expect(onAccepted).toHaveBeenCalledTimes(1);
    expect(onAccepted).toHaveBeenCalledWith(false);
    expect(result.current.activeTurn).toMatchObject({
      phase: 'interrupted',
      recoverable: true,
    });
    expect(result.current.messages.find(message => message.role === 'assistant')).toMatchObject({
      completionStatus: 'interrupted',
    });
    expect(result.current.messages.filter(message => message.cardType)).toHaveLength(0);
  });

  it('keeps an accepted voice turn submitted when the reply stream ends before done', async () => {
    mockStreamChat.mockImplementation(streamAcceptedThenEndsWithoutDone);
    const onAccepted = jest.fn();
    const { result } = renderHook(() => useChatEngine());
    let accepted: boolean | undefined;

    await act(async () => {
      accepted = await result.current.sendMessage(
        '昨天晚上我睡得怎么样？',
        null,
        { channel: 'voice', onAccepted } as any,
      );
    });

    expect(accepted).toBe(true);
    expect(onAccepted).toHaveBeenCalledTimes(1);
    expect(onAccepted).toHaveBeenCalledWith(true);
    expect(result.current.activeTurn).toMatchObject({
      phase: 'interrupted',
      recoverable: true,
    });
    expect(result.current.messages.find(message => message.role === 'assistant')).toMatchObject({
      completionStatus: 'interrupted',
      content: expect.stringContaining('已保留已接收内容'),
    });
  });

  it('does not acknowledge done ids when the server explicitly says request was not persisted', async () => {
    mockStreamChat.mockImplementation(streamDoneExplicitlyNotPersisted);
    const onAccepted = jest.fn();
    const { result } = renderHook(() => useChatEngine());

    let accepted: boolean | undefined;
    await act(async () => {
      accepted = await result.current.sendMessage(
        '保留这条草稿',
        null,
        { onAccepted } as any,
      );
    });

    expect(accepted).toBe(false);
    expect(onAccepted).toHaveBeenCalledWith(false);
    expect(result.current.activeTurn).toMatchObject({
      phase: 'interrupted',
      recoverable: true,
    });
    expect(result.current.messages.find(message => message.role === 'assistant')).toMatchObject({
      completionStatus: 'interrupted',
    });
    expect(result.current.messages.filter(message => message.cardType)).toHaveLength(0);
  });

  it('removes streamed action cards when the stream ends without done', async () => {
    mockStreamChat.mockImplementation(streamCardThenEndsWithoutDone);
    const { result } = renderHook(() => useChatEngine());

    await act(async () => {
      await result.current.sendMessage('记录这顿饭');
    });

    expect(result.current.activeTurn).toMatchObject({
      phase: 'interrupted',
      recoverable: true,
    });
    expect(result.current.messages.filter(message => message.cardType)).toHaveLength(0);
  });

  it('reuses the same client turn when an unchanged offline draft is retried', async () => {
    (NetInfo.fetch as jest.Mock)
      .mockResolvedValueOnce({ isConnected: false })
      .mockResolvedValueOnce({ isConnected: true });
    mockStreamChat.mockImplementation(streamTokenBurstThenDone);
    const { result } = renderHook(() => useChatEngine());

    await act(async () => {
      await result.current.sendMessage('午餐吃了鸡胸肉');
    });
    const failedTurnId = result.current.activeTurn.turnId;

    await act(async () => {
      await result.current.sendMessage('午餐吃了鸡胸肉');
    });

    expect(failedTurnId).toMatch(/^turn-/);
    expect(mockStreamChat.mock.calls[0][6]).toBe(failedTurnId);
    expect(result.current.messages.filter(message => (
      message.role === 'user' && message.content === '午餐吃了鸡胸肉'
    ))).toHaveLength(1);
    expect(result.current.messages.filter(message => message.role === 'assistant')).toHaveLength(1);
  });

  it('keeps one optimistic pair across repeated offline retries before recovery', async () => {
    (NetInfo.fetch as jest.Mock)
      .mockResolvedValueOnce({ isConnected: false })
      .mockResolvedValueOnce({ isConnected: false })
      .mockResolvedValueOnce({ isConnected: true });
    mockStreamChat.mockImplementation(streamTokenBurstThenDone);
    const { result } = renderHook(() => useChatEngine());

    await act(async () => { await result.current.sendMessage('准备睡觉了，给我建议'); });
    const failedTurnId = result.current.activeTurn.turnId;
    await act(async () => { await result.current.sendMessage('准备睡觉了，给我建议'); });
    await act(async () => { await result.current.sendMessage('准备睡觉了，给我建议'); });

    expect(mockStreamChat.mock.calls[0][6]).toBe(failedTurnId);
    expect(result.current.messages.filter(message => message.role === 'user')).toHaveLength(1);
    expect(result.current.messages.filter(message => (
      message.role === 'assistant' && !message.cardType
    ))).toHaveLength(1);
  });

  it('waits for active-turn hydration before reconciling initial history', async () => {
    let releaseHydration!: () => void;
    const hydrationGate = new Promise<void>((resolve) => { releaseHydration = resolve; });
    mockAsyncStorage[scopedStorageKey('chat:active_turn:v1')] = JSON.stringify({
      version: 1,
      phase: 'interrupted',
      turnId: 'turn-hydration-race',
      conversationId: 321,
      startedAt: Date.now() - 1000,
      updatedAt: Date.now() - 500,
      recoverable: true,
      hadWrite: false,
    });
    (AsyncStorage.getItem as jest.Mock).mockImplementation(async (key: string) => {
      if (key === scopedStorageKey('chat:active_turn:v1')) await hydrationGate;
      return mockAsyncStorage[key] ?? null;
    });
    mockGetConversations.mockResolvedValue([{ id: 321, title: '最近对话' }]);
    mockGetConversationMessages.mockResolvedValue({
      total_messages: 2,
      messages: [
        { id: 1, role: 'user', content: '问题', meta: { client_turn_id: 'turn-hydration-race' } },
        {
          id: 2,
          role: 'assistant',
          content: '已完成',
          meta: { client_turn_id: 'turn-hydration-race', completion_status: 'complete' },
        },
      ],
    });
    const { result } = renderHook(() => useChatEngine());
    let loadPromise: Promise<unknown> | undefined;

    act(() => {
      loadPromise = result.current.loadLatestConversation();
    });
    expect(mockGetConversations).not.toHaveBeenCalled();
    await act(async () => {
      releaseHydration();
      await loadPromise;
    });

    expect(result.current.activeTurn).toMatchObject({
      turnId: 'turn-hydration-race',
      phase: 'completed',
      messageId: 2,
    });
  });

  it('reports a failed terminal event when a write attempt has no successful receipt', async () => {
    mockStreamChat.mockImplementation(streamFailedWriteThenDone);
    const { result } = renderHook(() => useChatEngine());

    await act(async () => {
      await result.current.sendMessage('记录午餐');
    });

    expect(result.current.activeTurn).toMatchObject({ phase: 'failed', hadWrite: true });
    expect(mockEmitClientEvent).toHaveBeenCalledWith('agent_turn_terminal', {
      phase: 'failed',
      duration_bucket: '10_30s',
      error_code: 'tool_failed',
    });
    expect(mockEmitClientEvent).not.toHaveBeenCalledWith(
      'agent_turn_terminal',
      expect.objectContaining({ phase: 'completed' }),
    );
  });

  it('does not infer a legacy health-manage query is a failed write', async () => {
    mockStreamChat.mockImplementation(streamLegacyHealthManageQueryThenDone);
    const { result } = renderHook(() => useChatEngine());

    await act(async () => {
      await result.current.sendMessage('查询今天的饮食记录');
    });

    expect(result.current.activeTurn).toMatchObject({ phase: 'completed', hadWrite: false });
    expect(mockEmitClientEvent).not.toHaveBeenCalledWith(
      'write_receipt_terminal',
      expect.anything(),
    );
  });

  it('hydrates an interrupted Agent turn and resolves it from authoritative history', async () => {
    mockAsyncStorage[scopedStorageKey('chat:last_conversation_id:v1')] = '321';
    mockAsyncStorage[scopedStorageKey('chat:active_turn:v1')] = JSON.stringify({
      version: 1,
      phase: 'interrupted',
      turnId: 'turn-restored',
      conversationId: 321,
      startedAt: Date.now() - 1000,
      updatedAt: Date.now() - 500,
      errorCode: 'app_backgrounded',
      recoverable: true,
      hadWrite: false,
    });
    mockGetConversationMessages.mockResolvedValue({
      total_messages: 2,
      messages: [
        { id: 1, role: 'user', content: '上一轮问题', created_at: '2026-07-09T10:00:00Z' },
        {
          id: 2,
          role: 'assistant',
          content: '服务端已经完成。',
          created_at: '2026-07-09T10:00:05Z',
          meta: { completion_status: 'complete', client_turn_id: 'turn-restored' },
        },
      ],
    });

    const { result } = renderHook(() => useChatEngine());

    await waitFor(() => {
      expect(result.current.activeTurn).toMatchObject({
        phase: 'interrupted',
        turnId: 'turn-restored',
        conversationId: 321,
      });
    });

    await act(async () => {
      await result.current.loadLatestConversation();
    });

    await waitFor(() => {
      expect(result.current.activeTurn).toMatchObject({
        phase: 'completed',
        turnId: 'turn-restored',
        conversationId: 321,
        messageId: 2,
        recoverable: false,
      });
    });
    expect(mockEmitClientEvent).toHaveBeenCalledWith('agent_turn_terminal', {
      phase: 'completed',
      duration_bucket: '10_30s',
    });
  });

  it('does not certify an older assistant reply as completion of a newer interrupted turn', async () => {
    mockAsyncStorage[scopedStorageKey('chat:last_conversation_id:v1')] = '322';
    mockAsyncStorage[scopedStorageKey('chat:active_turn:v1')] = JSON.stringify({
      version: 1,
      phase: 'interrupted',
      turnId: 'turn-new',
      conversationId: 322,
      startedAt: Date.now() - 1000,
      updatedAt: Date.now() - 500,
      errorCode: 'app_backgrounded',
      recoverable: true,
      hadWrite: false,
    });
    mockGetConversationMessages.mockResolvedValue({
      total_messages: 3,
      messages: [
        { id: 1, role: 'user', content: '旧问题', meta: { client_turn_id: 'turn-old' } },
        {
          id: 2,
          role: 'assistant',
          content: '旧问题的答案',
          meta: { completion_status: 'complete', client_turn_id: 'turn-old' },
        },
        { id: 3, role: 'user', content: '本轮尚未完成', meta: { client_turn_id: 'turn-new' } },
      ],
    });

    const { result } = renderHook(() => useChatEngine());
    await waitFor(() => expect(result.current.activeTurn.turnId).toBe('turn-new'));

    await act(async () => {
      await result.current.loadLatestConversation();
    });

    await waitFor(() => {
      expect(result.current.activeTurn).toMatchObject({
        turnId: 'turn-new',
        phase: 'running',
        recoverable: true,
      });
    });
    expect(result.current.activeTurn.messageId).toBeUndefined();
  });

  it('fails closed when recovered write history has no verified resource receipt', async () => {
    mockAsyncStorage[scopedStorageKey('chat:last_conversation_id:v1')] = '323';
    mockAsyncStorage[scopedStorageKey('chat:active_turn:v1')] = JSON.stringify({
      version: 1,
      phase: 'interrupted',
      turnId: 'turn-write-no-receipt',
      conversationId: 323,
      startedAt: Date.now() - 1000,
      updatedAt: Date.now() - 500,
      recoverable: true,
      hadWrite: true,
    });
    mockGetConversationMessages.mockResolvedValue({
      total_messages: 2,
      messages: [
        { id: 1, role: 'user', content: '记录午餐', meta: { client_turn_id: 'turn-write-no-receipt' } },
        {
          id: 2,
          role: 'assistant',
          content: '已处理。',
          meta: { completion_status: 'complete', client_turn_id: 'turn-write-no-receipt' },
        },
      ],
    });

    const { result } = renderHook(() => useChatEngine());
    await waitFor(() => expect(result.current.activeTurn.turnId).toBe('turn-write-no-receipt'));
    await act(async () => { await result.current.loadLatestConversation(); });

    await waitFor(() => {
      expect(result.current.activeTurn).toMatchObject({
        phase: 'failed',
        hadWrite: true,
        writeVerified: false,
        errorCode: 'write_receipt_missing_identity',
        recoverable: true,
      });
    });
  });

  it('preserves interrupted recovery and emits one interrupted terminal event', async () => {
    mockAsyncStorage[scopedStorageKey('chat:last_conversation_id:v1')] = '324';
    mockAsyncStorage[scopedStorageKey('chat:active_turn:v1')] = JSON.stringify({
      version: 1,
      phase: 'interrupted',
      turnId: 'turn-server-interrupted',
      conversationId: 324,
      startedAt: Date.now() - 1000,
      updatedAt: Date.now() - 500,
      recoverable: true,
      hadWrite: false,
    });
    mockGetConversationMessages.mockResolvedValue({
      total_messages: 2,
      messages: [
        { id: 1, role: 'user', content: '上一轮', meta: { client_turn_id: 'turn-server-interrupted' } },
        {
          id: 2,
          role: 'assistant',
          content: '本轮中断。',
          meta: { completion_status: 'interrupted', client_turn_id: 'turn-server-interrupted' },
        },
      ],
    });

    const { result } = renderHook(() => useChatEngine());
    await waitFor(() => expect(result.current.activeTurn.turnId).toBe('turn-server-interrupted'));
    await act(async () => { await result.current.loadLatestConversation(); });

    await waitFor(() => {
      expect(result.current.activeTurn).toMatchObject({
        phase: 'interrupted',
        errorCode: 'stream_interrupted',
        recoverable: true,
      });
    });
    const terminalCalls = mockEmitClientEvent.mock.calls.filter(
      ([name]) => name === 'agent_turn_terminal',
    );
    expect(terminalCalls).toEqual([[
      'agent_turn_terminal',
      {
        phase: 'interrupted',
        duration_bucket: '10_30s',
        error_code: 'stream_interrupted',
      },
    ]]);
  });

  it('keeps the thinking bubble while empty tool events arrive before text tokens', async () => {
    mockStreamChat.mockImplementation(streamStartToolThenWait);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('请结合天气、空气质量和日程安排户外活动');
    });

    await waitFor(() => {
      expect(result.current.conversationId).toBe(777);
    });

    expect(result.current.messages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          role: 'assistant',
          streaming: true,
          content: '⏳ AI 正在思考中...',
        }),
      ]),
    );

    await act(async () => {
      finishStream?.();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(result.current.messages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            role: 'assistant',
            content: '今天户外运动建议先看空气质量。',
          }),
        ]),
      );
    });
  });

  it('streams safe thinking steps separately from assistant answer text', async () => {
    mockStreamChat.mockImplementation(streamThoughtsThenWait);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('分析我最近 7 天睡眠');
    });

    await waitFor(() => {
      expect(result.current.messages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            role: 'assistant',
            streaming: true,
            content: '今晚优先固定睡眠时间。',
            thinkingSteps: expect.arrayContaining([
              '正在理解你的问题',
              '读取健康数据',
              '已取得健康数据',
            ]),
          }),
        ]),
      );
    });

    await act(async () => {
      finishStream?.();
      await Promise.resolve();
    });
  });

  it('batches bursty tokens without dropping or reordering (攒批终态逐段拼接)', async () => {
    mockStreamChat.mockImplementation(streamTokenBurstThenDone);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('快路由压测');
    });

    // 终态: 逐 token 顺序拼接, 一字不差 (最后一批必 flush).
    await waitFor(() => {
      const assistant = result.current.messages.find(m => m.role === 'assistant');
      expect(assistant?.content).toBe(BURST_TOKENS.join(''));
      expect(assistant?.streaming).toBe(false);
    });
  });

  it('lands the last token batch and streaming:false atomically on done (done 首帧内容完整)', async () => {
    mockStreamChat.mockImplementation(streamLastTokenThenDoneAtomic);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('原子收尾压测');
    });

    // done 之后: 最后一批 token 不丢, streaming 已翻 false —— 二者同一帧完成。
    // (若非原子, 会短暂出现 content 缺 "最后一段" 但 streaming:false 的中间态。)
    // token 首尾空白属于正文，必须原样保留；两批都在、顺序对、streaming 已 false。
    await waitFor(() => {
      const assistant = result.current.messages.find(m => m.role === 'assistant');
      expect(assistant?.content).toBe('## 今日状态总览 这是最后一段正文。');
      expect(assistant?.streaming).toBe(false);
    });

    // done 帧内容既包含首批也包含最后一批, 无残缺; thinking placeholder 已剥掉。
    const assistant = result.current.messages.find(m => m.role === 'assistant');
    expect(assistant?.content).not.toContain('⏳');
    expect(assistant?.content).toContain('## 今日状态总览');
    expect(assistant?.content).toContain('这是最后一段正文。');
  });

  it('preserves token-boundary whitespace so Markdown renders correctly on the first pass', async () => {
    mockStreamChat.mockImplementation(streamMarkdownTokenBoundariesThenDone);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('把晨起测量拆成可执行步骤');
    });

    await waitFor(() => {
      const assistant = result.current.messages.find(m => m.role === 'assistant');
      expect(assistant?.streaming).toBe(false);
      expect(assistant?.content).toBe(EXECUTABLE_ACTION_MARKDOWN_TOKENS.join(''));
    });
  });

  it('flushes buffered tokens before an error tail (攒批不吞已接收内容)', async () => {
    mockStreamChat.mockImplementation(streamTokenBurstThenError);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('中途报错');
    });

    await waitFor(() => {
      const assistant = result.current.messages.find(m => m.role === 'assistant');
      // 已接收的两批 token 都保留 (未被吞), 且顺序不变, 位于错误尾巴 (❌) 之前.
      const content = assistant?.content ?? '';
      expect(content).toContain('开头一段还没说完');
      expect(content).toContain('❌');
      expect(content.indexOf('开头一段还没说完')).toBeLessThan(content.indexOf('❌'));
    });
    expect(mockEmitClientEvent).toHaveBeenCalledWith('agent_turn_terminal', {
      phase: 'failed',
      duration_bucket: '10_30s',
      error_code: 'stream_error_event',
    });
    expect(mockEmitClientEvent.mock.calls.filter(([name]) => name === 'agent_turn_terminal')).toHaveLength(1);
  });

  it('sanitizes provider quota errors that arrive as legacy token text', async () => {
    mockStreamChat.mockImplementation(streamQuotaErrorAsToken);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('我适合怎样的锻炼');
    });

    await waitFor(() => {
      const assistant = result.current.messages.find(m => m.role === 'assistant');
      expect(assistant?.content).toContain('模型额度');
      expect(assistant?.content).toContain('切换模型');
      expect(assistant?.content).not.toContain('insufficient_quota');
      expect(assistant?.content).not.toContain('token-plan quota');
      expect(assistant?.content).not.toContain('Error code: 429');
    });
  });

  it('inserts streamed server cards before the assistant done event', async () => {
    mockStreamChat.mockImplementation(streamTokenCardThenWait);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('吃了两个鸡蛋一杯牛奶');
    });

    await waitFor(() => {
      expect(result.current.messages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            role: 'assistant',
            streaming: true,
            content: '我先把这顿饭识别为待确认记录。',
          }),
          expect.objectContaining({
            role: 'assistant',
            content: '',
            cardType: 'diet',
            cardData: { items: ['鸡蛋', '牛奶'] },
            cardActions: [
              expect.objectContaining({
                action: 'write_intent.confirm',
                requires_manual_confirm: true,
              }),
            ],
          }),
        ]),
      );
    });
    const streamedCard = result.current.messages.find(message => message.cardType === 'diet');
    expect(streamedCard?.sourceTurnId).toBe(result.current.activeTurn.turnId);

    await act(async () => {
      finishStream?.();
      await Promise.resolve();
    });
  });

  it.each([
    ['missing', 'omits cards'],
    ['empty', 'returns an empty cards array'],
  ] as const)(
    'keeps one streamed diet card and skips local fallback when done %s (%s)',
    async (cards, _description) => {
      mockStreamChat.mockImplementation(streamDietCardThenDone(cards));
      mockDispatchCard.mockResolvedValue({
        type: 'record',
        data: { domain: 'diet', summary: '本地 fallback 饮食卡' },
      });
      const { result } = renderHook(() => useChatEngine());

      await act(async () => {
        await result.current.sendMessage('记录午餐牛肉面');
      });

      const turnId = result.current.activeTurn.turnId;
      const dietCards = result.current.messages.filter(message => (
        message.sourceTurnId === turnId
        && message.cardData?.domain === 'diet'
      ));
      expect(dietCards).toHaveLength(1);
      expect(dietCards[0]).toEqual(expect.objectContaining({
        cardType: 'record_quality',
        cardData: expect.objectContaining({ summary: '已记录旧版饮食摘要' }),
      }));
      expect(mockDispatchCard).not.toHaveBeenCalled();
    },
  );

  it('replaces the streamed diet card with the authoritative done snapshot', async () => {
    mockStreamChat.mockImplementation(streamDietCardThenDone('summary'));
    mockDispatchCard.mockResolvedValue({
      type: 'record',
      data: { domain: 'diet', summary: '不应出现的本地 fallback' },
    });
    const { result } = renderHook(() => useChatEngine());

    await act(async () => {
      await result.current.sendMessage('记录午餐牛肉面');
    });

    const turnId = result.current.activeTurn.turnId;
    const turnCards = result.current.messages.filter(message => (
      message.sourceTurnId === turnId && !!message.cardType
    ));
    expect(turnCards).toHaveLength(1);
    expect(turnCards[0]).toEqual(expect.objectContaining({
      cardType: 'diet_daily_summary',
      cardData: expect.objectContaining({ summary: '服务端终态新版饮食摘要' }),
      sourceMessageId: 82,
      sourceTurnId: turnId,
    }));
    expect(mockDispatchCard).not.toHaveBeenCalled();
  });

  it('deduplicates identical cards inside the authoritative done snapshot', async () => {
    mockStreamChat.mockImplementation(streamDietCardThenDone('duplicate_summary'));
    const { result } = renderHook(() => useChatEngine());

    await act(async () => {
      await result.current.sendMessage('记录午餐牛肉面');
    });

    const currentTurnCards = result.current.messages.filter(message => (
      message.sourceTurnId === result.current.activeTurn.turnId && !!message.cardType
    ));
    expect(currentTurnCards).toHaveLength(1);
    expect(currentTurnCards[0]).toEqual(expect.objectContaining({
      cardType: 'diet_daily_summary',
      cardData: expect.objectContaining({ summary: '服务端终态新版饮食摘要' }),
      sourceMessageId: 82,
    }));
  });

  it('does not fabricate a local fallback when supplied done cards are unrenderable', async () => {
    mockStreamChat.mockImplementation(streamUnrenderableDoneCard);
    mockRenderServerCards.mockReturnValue([]);
    mockDispatchCard.mockResolvedValue({
      type: 'record',
      data: { domain: 'diet', summary: '不应伪造的本地饮食卡' },
    });
    const { result } = renderHook(() => useChatEngine());

    await act(async () => {
      await result.current.sendMessage('记录午餐牛肉面');
    });

    expect(result.current.messages).toEqual(expect.arrayContaining([
      expect.objectContaining({
        role: 'assistant',
        content: '饮食记录已经保存。',
        streaming: false,
      }),
    ]));
    expect(result.current.messages.filter(message => (
      message.sourceTurnId === result.current.activeTurn.turnId && !!message.cardType
    ))).toHaveLength(0);
    expect(mockDispatchCard).not.toHaveBeenCalled();
  });

  it('retires a streamed provisional card when supplied done cards are unrenderable', async () => {
    mockStreamChat.mockImplementation(streamCardThenUnrenderableDoneCard);
    mockRenderServerCards.mockImplementation((cards: any[]) => (
      Array.isArray(cards)
        ? cards.filter(card => card?.type === 'record_quality')
        : []
    ));
    mockDispatchCard.mockResolvedValue({
      type: 'record',
      data: { domain: 'diet', summary: '不应伪造的本地饮食卡' },
    });
    const { result } = renderHook(() => useChatEngine());

    await act(async () => {
      await result.current.sendMessage('记录午餐牛肉面');
    });

    expect(result.current.messages.filter(message => (
      message.sourceTurnId === result.current.activeTurn.turnId && !!message.cardType
    ))).toHaveLength(0);
    expect(mockDispatchCard).not.toHaveBeenCalled();
  });

  it('replaces only current-turn cards when applying the authoritative done snapshot', async () => {
    mockStreamChat.mockImplementation(streamDietCardThenDone('summary'));
    const previousMedicationActions = [{
      id: 'medication-batch-confirm:42',
      label: '确认记录',
      action: 'write_intent.confirm',
      payload: { write_intent_id: 42 },
    }];
    const previousMedicationCard = {
      id: 'pending-medication-42',
      role: 'assistant' as const,
      content: '',
      cardType: 'medication_draft',
      cardData: { write_intent_id: 42, items: [{ medication_name: '伊托必利' }] },
      cardActions: previousMedicationActions,
      sourceTurnId: 'turn-before-medication',
    };
    const previousUnrelatedCard = {
      id: 'previous-unrelated-card',
      role: 'assistant' as const,
      content: '',
      cardType: 'health_snapshot',
      cardData: { summary: '上一轮健康快照' },
      cardActions: [],
      sourceTurnId: 'turn-before-snapshot',
    };
    const { result } = renderHook(() => useChatEngine());
    act(() => {
      result.current.setMessages([previousMedicationCard, previousUnrelatedCard]);
    });

    await act(async () => {
      await result.current.sendMessage('记录午餐牛肉面');
    });

    expect(result.current.messages.find(message => message.id === previousMedicationCard.id))
      .toBe(previousMedicationCard);
    expect(result.current.messages.find(message => message.id === previousMedicationCard.id)?.cardActions)
      .toBe(previousMedicationActions);
    expect(result.current.messages.find(message => message.id === previousUnrelatedCard.id))
      .toBe(previousUnrelatedCard);
    const currentTurnCards = result.current.messages.filter(message => (
      message.sourceTurnId === result.current.activeTurn.turnId && !!message.cardType
    ));
    expect(currentTurnCards).toHaveLength(1);
    expect(currentTurnCards[0].cardType).toBe('diet_daily_summary');
  });

  it('keeps the local streaming assistant bubble when conversation id arrives mid-stream', async () => {
    mockStreamChat.mockImplementation(streamStartThenWait);
    mockGetConversationMessages.mockResolvedValue({
      total_messages: 1,
      messages: [
        {
          id: 1,
          role: 'user',
          content: '请分析这些图片',
          created_at: '2026-05-16T21:19:00Z',
          image_url: '["/uploads/chat/test.jpg"]',
        },
      ],
    });

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('请分析这些图片', [
        { uri: 'file:///lab-report.jpg', base64: 'abc123', type: 'jpeg' },
      ]);
    });

    await waitFor(() => {
      expect(result.current.conversationId).toBe(777);
    });

    expect(result.current.messages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          role: 'assistant',
          streaming: true,
        }),
      ]),
    );
    expect(result.current.messages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          role: 'user',
          imageUris: ['file:///lab-report.jpg'],
        }),
      ]),
    );

    await act(async () => {
      finishStream?.();
      await Promise.resolve();
    });
  });

  it('recovers the server answer when a local stream times out after leaving the page', async () => {
    mockStreamChat.mockImplementation(streamStartThenTimeout);
    mockGetConversationMessages.mockImplementationOnce(async () => {
      const clientTurnId = mockStreamChat.mock.calls[0]?.[6];
      return {
        total_messages: 2,
        messages: [
          {
            id: 1,
            role: 'user',
            content: '继续分析图片记录饮食',
            created_at: '2026-05-22T23:30:00Z',
            meta: { client_turn_id: clientTurnId },
          },
          {
            id: 2,
            role: 'assistant',
            content: '已从服务端恢复的完整回答',
            created_at: '2026-05-22T23:31:00Z',
            meta: { client_turn_id: clientTurnId, completion_status: 'complete' },
          },
        ],
      };
    });

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('继续分析图片记录饮食');
    });

    await waitFor(() => {
      expect(result.current.conversationId).toBe(777);
    });

    await act(async () => {
      await Promise.resolve();
      failStream?.();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(result.current.messages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ role: 'assistant', content: '已从服务端恢复的完整回答' }),
        ]),
      );
    });
    expect(result.current.messages).not.toEqual(
      expect.arrayContaining([
        expect.objectContaining({ content: expect.stringContaining('请求超时') }),
      ]),
    );
    expect(mockGetConversationMessages).toHaveBeenCalledWith(777, { days: 7 });
  });

  it('recovers an accepted background-aborted stream from server history on foreground', async () => {
    let appStateListener: ((state: string) => void) | undefined;
    jest.spyOn(AppState, 'addEventListener').mockImplementation(((_event: string, handler: (state: string) => void) => {
      appStateListener = handler;
      return { remove: jest.fn() } as any;
    }) as any);
    mockStreamChat.mockImplementation(streamStartThenAbort);
    let serverAnswerReady = false;
    mockGetConversationMessages.mockImplementation(async () => {
      const clientTurnId = mockStreamChat.mock.calls[0]?.[6];
      if (!serverAnswerReady) {
        return {
          total_messages: 1,
          messages: [
            {
              id: 1,
              role: 'user',
              content: '离开 App 后继续输出',
              created_at: '2026-07-16T15:40:00Z',
              meta: { client_turn_id: clientTurnId },
            },
          ],
        };
      }
      return {
        total_messages: 2,
        messages: [
          {
            id: 1,
            role: 'user',
            content: '离开 App 后继续输出',
            created_at: '2026-07-16T15:40:00Z',
            meta: { client_turn_id: clientTurnId },
          },
          {
            id: 2,
            role: 'assistant',
            content: '服务端后台完成的完整回答',
            created_at: '2026-07-16T15:40:20Z',
            meta: { client_turn_id: clientTurnId, completion_status: 'complete' },
          },
        ],
      };
    });
    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('离开 App 后继续输出');
    });

    await waitFor(() => {
      expect(result.current.conversationId).toBe(777);
    });

    act(() => {
      appStateListener?.('background');
    });

    await act(async () => {
      failStream?.();
      await Promise.resolve();
    });

    await waitFor(() => {
      const assistant = result.current.messages.find(message => message.role === 'assistant');
      expect(assistant?.content).not.toContain('请重新提问');
      expect(result.current.activeTurn).toMatchObject({
        phase: 'interrupted',
        recoverable: true,
      });
    });

    await act(async () => {
      serverAnswerReady = true;
      appStateListener?.('active');
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(result.current.messages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ role: 'assistant', content: '服务端后台完成的完整回答' }),
        ]),
      );
      expect(result.current.activeTurn).toMatchObject({
        phase: 'completed',
        messageId: 2,
        recoverable: false,
      });
    });
  });

  it('does not surface status 200 as a network failure after an accepted stream is backgrounded', async () => {
    let appStateListener: ((state: string) => void) | undefined;
    jest.spyOn(AppState, 'addEventListener').mockImplementation(((_event: string, handler: (state: string) => void) => {
      appStateListener = handler;
      return { remove: jest.fn() } as any;
    }) as any);
    mockStreamChat.mockImplementation(streamStartThenStatus200Failure);
    let serverAnswerReady = false;
    mockGetConversationMessages.mockImplementation(async () => {
      const clientTurnId = mockStreamChat.mock.calls[0]?.[6];
      return {
        total_messages: serverAnswerReady ? 2 : 1,
        messages: [
          {
            id: 1,
            role: 'user',
            content: '切换 App 后继续回复',
            created_at: '2026-07-17T17:00:00Z',
            meta: { client_turn_id: clientTurnId },
          },
          ...(serverAnswerReady ? [{
            id: 2,
            role: 'assistant',
            content: '切回 App 后恢复的完整回答',
            created_at: '2026-07-17T17:00:20Z',
            meta: { client_turn_id: clientTurnId, completion_status: 'complete' },
          }] : []),
        ],
      };
    });
    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('切换 App 后继续回复');
    });
    await waitFor(() => expect(result.current.conversationId).toBe(777));

    act(() => appStateListener?.('background'));
    await act(async () => {
      failStream?.();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(result.current.messages.map(message => message.content).join('\n'))
        .not.toContain('网络请求失败');
      expect(result.current.activeTurn).toMatchObject({
        phase: 'interrupted',
        recoverable: true,
      });
    });

    await act(async () => {
      serverAnswerReady = true;
      appStateListener?.('active');
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(result.current.messages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ role: 'assistant', content: '切回 App 后恢复的完整回答' }),
        ]),
      );
      expect(result.current.activeTurn).toMatchObject({
        phase: 'completed',
        messageId: 2,
        recoverable: false,
      });
    });
  });

  // ── P0-5 竞态守卫: 流式活跃时 focus-reload 不用服务端半截 partial 覆盖本地流 ──
  it('holds the local streaming bubble during an active stream even if the server only has a partial', async () => {
    mockStreamChat.mockImplementation(streamStartTokenThenWait);
    // 服务端此刻只落库了 user 消息 (assistant 还没写完) —— 若守卫失效会用它覆盖本地流。
    mockGetConversationMessages.mockResolvedValue({
      total_messages: 1,
      messages: [
        { id: 1, role: 'user', content: '半截问题', created_at: '2026-07-05T10:00:00Z' },
      ],
    });

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('请分析我的步数');
    });

    // conversationId 回填 → focus effect / reloadCurrentFromServer 的 callback 身份变化 →
    // useFocusEffect mock 重跑。守卫应让位, 不覆盖本地已流出的正文。
    // 等本地流式正文出现 (token 攒批 80ms flush) —— 这段窗口也给足 focus-reload 机会跑。
    await waitFor(() => {
      const assistant = result.current.messages.find(m => m.role === 'assistant');
      expect(assistant?.content).toBe('本地流式正文，请勿覆盖。');
      expect(assistant?.streaming).toBe(true);
    });

    // 服务端半截 (只有 user "半截问题") 不应替换掉本地这轮消息。
    expect(result.current.messages).not.toEqual(
      expect.arrayContaining([
        expect.objectContaining({ role: 'user', content: '半截问题' }),
      ]),
    );
    // 本地用户消息仍是原文 ("请分析我的步数"), 未被服务端历史替换。
    expect(result.current.messages).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ role: 'user', content: '请分析我的步数' }),
      ]),
    );

    await act(async () => {
      finishStream?.();
      await Promise.resolve();
    });

    // 流结束后本地正文完整保留。
    await waitFor(() => {
      expect(result.current.messages).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            role: 'assistant',
            streaming: false,
            content: '本地流式正文，请勿覆盖。',
          }),
        ]),
      );
    });
  });

  // ── P0-1 status 行状态机: accepted → tool → 首 token 清空; status 不进思考步骤 ──
  it('surfaces status labels as currentStatus and clears them once the first token arrives', async () => {
    mockStreamChat.mockImplementation(streamStatusThenWait);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('我今天走了多少步');
    });

    // 首 token 前: currentStatus 反映最新 status 标签 (synthesis 覆盖 accepted)。
    await waitFor(() => {
      const assistant = result.current.messages.find(m => m.role === 'assistant');
      expect(assistant?.currentStatus).toBe('正在整理回答…');
      expect(assistant?.streaming).toBe(true);
    });

    // status 标签绝不混进思考步骤列表 (刀⑤: 状态行与思考步骤分离)。
    {
      const assistant = result.current.messages.find(m => m.role === 'assistant');
      expect(assistant?.thinkingSteps || []).not.toContain('正在整理回答…');
      expect(assistant?.thinkingSteps || []).not.toContain('正在理解…');
    }

    // 放行首 token → currentStatus 被清空。
    await act(async () => {
      finishStream?.();
      await Promise.resolve();
    });

    await waitFor(() => {
      const assistant = result.current.messages.find(m => m.role === 'assistant');
      expect(assistant?.content).toBe('整理完成。');
      expect(assistant?.currentStatus).toBeFalsy();
    });
  });

  it('clears currentStatus on done even when statuses precede the tokens', async () => {
    mockStreamChat.mockImplementation(streamStatusThenToken);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('步数分析');
    });

    await waitFor(() => {
      const assistant = result.current.messages.find(m => m.role === 'assistant');
      expect(assistant?.content).toBe('你今天走了 8000 步。');
      expect(assistant?.streaming).toBe(false);
      // 终态: status 行已清空 (收进思考完成态 pill)。
      expect(assistant?.currentStatus).toBeFalsy();
    });
  });

  // ── 未知事件容错: 混入未知 SSE type 必须静默忽略, 不崩、不污染 ──
  it('silently ignores unknown stream event types without corrupting message state', async () => {
    mockStreamChat.mockImplementation(streamUnknownEventThenToken);

    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('混入未知事件');
    });

    // 未知事件被忽略, 已知的 status/token/done 正常处理, 正文完整。
    await waitFor(() => {
      const assistant = result.current.messages.find(m => m.role === 'assistant');
      expect(assistant?.content).toBe('正常回答。');
      expect(assistant?.streaming).toBe(false);
      expect(assistant?.currentStatus).toBeFalsy();
    });

    // 未知事件不应作为思考步骤或状态残留。
    const assistant = result.current.messages.find(m => m.role === 'assistant');
    expect(JSON.stringify(assistant?.thinkingSteps || [])).not.toContain('mystery_future_event');
    expect(JSON.stringify(assistant?.thinkingSteps || [])).not.toContain('another_unknown');
  });

  it('carries the latest verified write receipt into the next structured request context', async () => {
    mockAsyncStorage[scopedStorageKey('chat:conversation_continuity:v2')] = JSON.stringify({
      version: 1,
      storedAt: Date.now(),
      receipt: {
        operationId: 'health_record:diet:81',
        status: 'verified',
        resourceType: 'diet_record',
        resourceId: '81',
        completedAt: '2026-07-09T12:00:00.000Z',
        verified: true,
      },
    });
    mockStreamChat.mockImplementation(streamStartThenWait);
    const { result } = renderHook(() => useChatEngine());

    act(() => {
      void result.current.sendMessage('那我今天总热量是多少？', null, {
        extraContext: '{"from":"diet/today"}',
      });
    });

    await waitFor(() => expect(mockStreamChat).toHaveBeenCalled());
    const outboundContext = JSON.parse(mockStreamChat.mock.calls[0][4]);
    expect(outboundContext).toEqual(expect.objectContaining({
      from: 'diet/today',
      continuity: {
        latest_verified_write: expect.objectContaining({
          operation_id: 'health_record:diet:81',
          resource_type: 'diet_record',
          resource_id: '81',
          verified: true,
        }),
      },
    }));
    await waitFor(() => {
      expect(mockAsyncStorage[scopedStorageKey('chat:conversation_continuity:v2')]).toBeUndefined();
    });

    await act(async () => {
      finishStream?.();
      await Promise.resolve();
    });
  });

  it('stores a verified tool write receipt for the following turn', async () => {
    mockStreamChat.mockImplementation(streamVerifiedWriteThenDone);
    const { result } = renderHook(() => useChatEngine());

    await act(async () => {
      await result.current.sendMessage('记录午餐');
    });

    await waitFor(() => {
      const stored = JSON.parse(mockAsyncStorage[scopedStorageKey('chat:conversation_continuity:v2')]);
      expect(stored.receipt).toEqual(expect.objectContaining({
        operationId: 'health_record:diet:81',
        resourceType: 'diet_record',
        resourceId: '81',
        verified: true,
      }));
    });
    expect(mockEmitClientEvent).toHaveBeenCalledWith('write_receipt_terminal', {
      phase: 'verified',
      duration_bucket: '10_30s',
      action_type: 'health_record',
      verified: true,
    });
  });
});
