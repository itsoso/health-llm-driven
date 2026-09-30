/**
 * SUPPLEMENT_REMINDER 通知后台动作(已服用 / 跳过)单测。
 *
 * 回归:旧实现 POST /supplements/me/checkin —— 后端从无此路由(404),且 catch {} 静默吞掉,
 * 点「已服用」从不落 supplement_records.taken,也无人知晓。
 *
 * 经真实入口 consumeNotificationResponse(含路由分派),只 mock HTTP 客户端,钉死:
 *   - TAKEN → POST /supplements/records/batch
 *             { record_date: 用户本地日, checkins: [{ supplement_id: <整数>, taken: true }] }
 *             成功后刷新补剂打卡卡片所读的 dashboard 缓存
 *   - SKIP  → 不写库(taken:false 即「取消打卡」,会清掉当天已记的已服)
 *   - 延后重放(冷启动/回前台重放 last response)跨了本地日 → 不写、上报 stale_response
 *   - 请求失败 / 非法 supplement_id → console.warn + watch_action_failed(kind: 'supplement'),
 *     不抛;遥测与日志不回显通知原值(可能是补剂名)
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
import { queryClient } from '../../applib/queryClient';
import { emitClientEvent } from '../../services/clientEvents';

const mockPost = api.post as jest.Mock;
const mockInvalidateQueries = queryClient.invalidateQueries as jest.Mock;
const mockEmitClientEvent = emitClientEvent as jest.Mock;

// 每条用唯一 request id:useNotifications 按 `${id}:${action}` 做模块级去重。
// deliveredAt 与 iOS 一致用秒;缺省 = 当前(已钉住的)时刻,即当天送达、当场处理。
function supplementResponse(
  requestId: string,
  action: 'TAKEN' | 'SKIP',
  data: Record<string, unknown>,
  deliveredAt: number | null = Date.now() / 1000,
): Notifications.NotificationResponse {
  return {
    actionIdentifier: action,
    notification: { date: deliveredAt, request: { identifier: requestId, content: { data } } },
  } as unknown as Notifications.NotificationResponse;
}

describe('SUPPLEMENT_REMINDER background action', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockPost.mockResolvedValue({ data: { message: '批量打卡成功', results: [] } });
    // 本地 10-01 00:30。注意:「本地日 vs UTC 日」只在正偏移时区的 runner 上有区分度
    // (UTC 的 CI 上两者相同);在文件内改 process.env.TZ 对 jest-expo 不生效。
    jest.useFakeTimers();
    jest.setSystemTime(new Date(2026, 9, 1, 0, 30, 0));
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('TAKEN records the intake via the batch check-in endpoint with an explicit boolean taken', async () => {
    await expect(consumeNotificationResponse(
      supplementResponse('supp-taken', 'TAKEN', { reminder_type: 'supplement', supplement_id: 12 }),
    )).resolves.toBe(true);

    expect(mockPost).toHaveBeenCalledTimes(1);
    expect(mockPost).toHaveBeenCalledWith('/supplements/records/batch', {
      record_date: '2026-10-01',
      checkins: [{ supplement_id: 12, taken: true }],
    });
    expect(typeof mockPost.mock.calls[0][1].checkins[0].taken).toBe('boolean');
    // 补剂打卡卡片读 dashboard(record.tsx),与 App 内打卡同一刷新
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['dashboard'] });
    expect(mockEmitClientEvent).not.toHaveBeenCalled();
  });

  it('TAKEN sends a numeric-string supplement_id from the push payload as a JSON integer', async () => {
    await consumeNotificationResponse(
      supplementResponse('supp-taken-string-id', 'TAKEN', { reminder_type: 'supplement', supplement_id: '12' }),
    );

    expect(mockPost).toHaveBeenCalledWith('/supplements/records/batch', {
      record_date: '2026-10-01',
      checkins: [{ supplement_id: 12, taken: true }],
    });
  });

  it('SKIP writes nothing: taken=false would erase an intake already recorded today', async () => {
    await expect(consumeNotificationResponse(
      supplementResponse('supp-skip', 'SKIP', { reminder_type: 'supplement', supplement_id: 12 }),
    )).resolves.toBe(true);

    expect(mockPost).not.toHaveBeenCalled();
    expect(mockInvalidateQueries).not.toHaveBeenCalled();
    expect(mockEmitClientEvent).not.toHaveBeenCalled();
  });

  it('a failed write is logged and emitted as watch_action_failed instead of being swallowed', async () => {
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});
    mockPost.mockRejectedValueOnce(new Error('Request failed with status code 404'));

    // 与议程动作一致:listener 边界记录、不抛;不回放重试(重放会按新的「今天」记错日)。
    await expect(consumeNotificationResponse(
      supplementResponse('supp-fail', 'TAKEN', { reminder_type: 'supplement', supplement_id: 12 }),
    )).resolves.toBe(true);

    expect(warn).toHaveBeenCalledWith(
      '[supplementReminderActions] supplement reminder action failed',
      expect.any(Error),
    );
    expect(mockEmitClientEvent).toHaveBeenCalledWith('watch_action_failed', {
      reason: 'request_failed',
      kind: 'supplement',
      action: 'TAKEN',
      supplement_id: 12,
      error: 'Request failed with status code 404',
    });
    expect(mockInvalidateQueries).not.toHaveBeenCalled();
    warn.mockRestore();
  });

  it('a tap replayed on a later local day writes nothing instead of recording the wrong day', async () => {
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});
    // 09-30 23:50 本地送达并点按,10-01 00:30 才被冷启动/回前台重放
    const deliveredPrevDay = new Date(2026, 8, 30, 23, 50, 0).getTime() / 1000;

    await consumeNotificationResponse(
      supplementResponse('supp-stale', 'TAKEN', { reminder_type: 'supplement', supplement_id: 12 }, deliveredPrevDay),
    );

    expect(mockPost).not.toHaveBeenCalled();
    expect(mockInvalidateQueries).not.toHaveBeenCalled();
    expect(mockEmitClientEvent).toHaveBeenCalledWith('watch_action_failed', {
      reason: 'stale_response',
      kind: 'supplement',
      action: 'TAKEN',
      supplement_id: 12,
    });
    warn.mockRestore();
  });

  it('a response without a delivery date fails closed', async () => {
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});

    await consumeNotificationResponse(
      supplementResponse('supp-no-date', 'TAKEN', { reminder_type: 'supplement', supplement_id: 12 }, null),
    );

    expect(mockPost).not.toHaveBeenCalled();
    expect(mockEmitClientEvent).toHaveBeenCalledWith(
      'watch_action_failed',
      expect.objectContaining({ reason: 'stale_response' }),
    );
    warn.mockRestore();
  });

  it.each([
    ['missing', undefined],
    ['non-numeric', '鱼油'],
    ['boolean', true],
  ])('TAKEN with a %s supplement_id fails loud without posting or echoing the raw value', async (label, raw) => {
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});

    await consumeNotificationResponse(
      supplementResponse(`supp-invalid-${label}`, 'TAKEN', { reminder_type: 'supplement', supplement_id: raw }),
    );

    expect(mockPost).not.toHaveBeenCalled();
    expect(mockEmitClientEvent).toHaveBeenCalledWith('watch_action_failed', {
      reason: 'invalid_supplement_id',
      kind: 'supplement',
      action: 'TAKEN',
    });
    expect(warn).toHaveBeenCalled();
    expect(warn.mock.calls.flat()).not.toContain(raw);
    warn.mockRestore();
  });
});
