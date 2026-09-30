/**
 * OPEN_LOOP / BEHAVIOR_LOOP 通知后台动作单测。
 *
 * 回归:旧实现两处写路径都包在空 catch {} 里 —— open-loop 反馈与「今天最重要一件事」的
 * 完成/跳过(手表镜像)写失败无人知晓;open-loop 还用动态 import(),在 jest 下直接抛
 * ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING_FLAG,也被空 catch 吞成假绿。
 *
 * 经真实入口 consumeNotificationResponse(含路由分派),只 mock HTTP 客户端,钉死:
 *   - DONE / SNOOZE_7D / NOT_INTERESTED → POST /open-loop/{history_id}/feedback
 *   - LOOP_DONE / LOOP_SKIP → POST /daily-plan/actions/{action_key}/events
 *   - LOOP_LATER → 不写库、不报错
 *   - 请求失败 / 非法载荷 → console.warn + watch_action_failed,不抛;
 *     遥测与日志不回显 action_key(可能回退为行动标题原文)
 */

jest.mock('../../services/api', () => ({
  __esModule: true,
  default: { post: jest.fn() },
}));

jest.mock('../../applib/queryClient', () => ({
  __esModule: true,
  queryClient: { invalidateQueries: jest.fn().mockResolvedValue(undefined) },
  persistOptions: {},
}));

jest.mock('expo-notifications', () => ({
  __esModule: true,
  setNotificationHandler: jest.fn(),
  setNotificationCategoryAsync: jest.fn().mockResolvedValue(undefined),
  getLastNotificationResponseAsync: jest.fn().mockResolvedValue(null),
  clearLastNotificationResponseAsync: jest.fn().mockResolvedValue(undefined),
  scheduleNotificationAsync: jest.fn().mockResolvedValue('noop'),
  dismissNotificationAsync: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('expo-device', () => ({ __esModule: true, isDevice: false }));
jest.mock('expo-constants', () => ({ __esModule: true, default: { expoConfig: { ios: {} } } }));
jest.mock('../../services/notifications', () => ({ bindIOSToken: jest.fn() }));
jest.mock('../../services/clientEvents', () => ({ emitClientEvent: jest.fn() }));
jest.mock('../../services/notificationRoutes', () => ({ resolveNotificationRoute: jest.fn() }));

import type * as Notifications from 'expo-notifications';
import { consumeNotificationResponse } from '../useNotifications';
import api from '../../services/api';
import { emitClientEvent } from '../../services/clientEvents';

const mockPost = api.post as jest.Mock;
const mockEmitClientEvent = emitClientEvent as jest.Mock;

// 每条用唯一 request id:useNotifications 按 `${id}:${action}` 做模块级去重。
function response(
  requestId: string,
  action: string,
  data: Record<string, unknown>,
): Notifications.NotificationResponse {
  return {
    actionIdentifier: action,
    notification: { request: { identifier: requestId, content: { data } } },
  } as unknown as Notifications.NotificationResponse;
}

// 回退形态的 action_key 含行动标题原文 —— 不能出现在遥测或日志里。
const FREE_TEXT_ACTION_KEY = 'sleep.晚上十点前关灯';

let warn: jest.SpyInstance;

beforeEach(() => {
  jest.clearAllMocks();
  mockPost.mockResolvedValue({ data: {} });
  warn = jest.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  warn.mockRestore();
});

describe('OPEN_LOOP background action', () => {
  it.each([
    ['DONE', 'done'],
    ['SNOOZE_7D', 'snooze_7d'],
    ['NOT_INTERESTED', 'not_interested'],
  ])('%s posts feedback for the history row', async (actionId, action) => {
    await expect(consumeNotificationResponse(
      response(`ol-ok-${actionId}`, actionId, { history_id: '42' }),
    )).resolves.toBe(true);

    expect(mockPost).toHaveBeenCalledTimes(1);
    expect(mockPost).toHaveBeenCalledWith('/open-loop/42/feedback', { action });
    expect(mockEmitClientEvent).not.toHaveBeenCalled();
  });

  it('a failed feedback write is logged and emitted as watch_action_failed instead of being swallowed', async () => {
    mockPost.mockRejectedValueOnce(new Error('Request failed with status code 500'));

    await expect(consumeNotificationResponse(
      response('ol-fail', 'DONE', { history_id: 42 }),
    )).resolves.toBe(true);

    expect(warn).toHaveBeenCalledWith(
      '[notificationLoopActions] open-loop feedback failed',
      'Request failed with status code 500',
    );
    expect(mockEmitClientEvent).toHaveBeenCalledWith('watch_action_failed', {
      reason: 'request_failed',
      kind: 'open_loop',
      action: 'DONE',
      history_id: 42,
      error: 'Request failed with status code 500',
    });
  });

  it.each([
    ['missing', undefined],
    ['non-numeric', 'abc'],
    ['zero', 0],
  ])('a %s history_id fails loud without posting', async (label, raw) => {
    await consumeNotificationResponse(response(`ol-invalid-${label}`, 'DONE', { history_id: raw }));

    expect(mockPost).not.toHaveBeenCalled();
    expect(mockEmitClientEvent).toHaveBeenCalledWith('watch_action_failed', {
      reason: 'invalid_history_id',
      kind: 'open_loop',
      action: 'DONE',
    });
    expect(warn).toHaveBeenCalled();
  });
});

describe('BEHAVIOR_LOOP background action', () => {
  it.each([
    ['LOOP_DONE', 'completed'],
    ['LOOP_SKIP', 'skipped'],
  ])('%s records a %s daily-plan action event', async (actionId, eventType) => {
    await expect(consumeNotificationResponse(
      response(`bl-ok-${actionId}`, actionId, { action_key: 'intervention.card.7' }),
    )).resolves.toBe(true);

    expect(mockPost).toHaveBeenCalledTimes(1);
    expect(mockPost).toHaveBeenCalledWith(
      '/daily-plan/actions/intervention.card.7/events',
      { event_type: eventType, payload: { source: 'wrist_notification' } },
    );
    expect(mockEmitClientEvent).not.toHaveBeenCalled();
  });

  it('LOOP_LATER is an intentional no-op: no write, no failure event', async () => {
    await expect(consumeNotificationResponse(
      response('bl-later', 'LOOP_LATER', { action_key: 'intervention.card.7' }),
    )).resolves.toBe(true);

    expect(mockPost).not.toHaveBeenCalled();
    expect(mockEmitClientEvent).not.toHaveBeenCalled();
    expect(warn).not.toHaveBeenCalled();
  });

  it('a failed completion write is logged and emitted without echoing the action_key', async () => {
    mockPost.mockRejectedValueOnce(new Error('Network Error'));

    await expect(consumeNotificationResponse(
      response('bl-fail', 'LOOP_DONE', { action_key: FREE_TEXT_ACTION_KEY }),
    )).resolves.toBe(true);

    expect(warn).toHaveBeenCalledWith(
      '[notificationLoopActions] behavior-loop action failed',
      'Network Error',
    );
    expect(mockEmitClientEvent).toHaveBeenCalledWith('watch_action_failed', {
      reason: 'request_failed',
      kind: 'behavior_loop',
      action: 'LOOP_DONE',
      error: 'Network Error',
    });
    expect(JSON.stringify(mockEmitClientEvent.mock.calls)).not.toContain('关灯');
    expect(JSON.stringify(warn.mock.calls)).not.toContain('关灯');
  });

  it('a missing action_key fails loud without posting', async () => {
    await consumeNotificationResponse(response('bl-invalid', 'LOOP_SKIP', {}));

    expect(mockPost).not.toHaveBeenCalled();
    expect(mockEmitClientEvent).toHaveBeenCalledWith('watch_action_failed', {
      reason: 'invalid_action_key',
      kind: 'behavior_loop',
      action: 'LOOP_SKIP',
    });
    expect(warn).toHaveBeenCalled();
  });
});
