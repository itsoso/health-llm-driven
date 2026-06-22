/**
 * AGENDA_ACTION 通知后台动作(完成 / 跳过)单测。
 *
 * 镜像 services/__tests__/notificationRoutes.test.ts 的风格,但目标是
 * hooks/useNotifications.ts 的 handleAgendaAction:
 *   - COMPLETE → completeAgendaItem(ref, 'protocol', undefined, {status:'done'})
 *   - SKIP     → ... {status:'skipped'}
 *   - 之后 invalidate ['timeline','today'] + ['agenda','today'](首页项熄灭)
 *   - 缺 complete_ref → 不调用 service、不 invalidate
 *   - service 抛错 → listener 边界吞掉,不抛(fire-and-forget)
 *
 * useNotifications.ts 在 module load 时跑 Notifications.setNotificationHandler,
 * 并 import expo-notifications/device/constants + applib/queryClient + services/*,
 * 全部在这里 mock 掉,隔离纯 handler 逻辑。
 */

// completeAgendaItem 走动态 import('../services/agenda'),mock 该模块。
jest.mock('../../services/agenda', () => ({
  __esModule: true,
  completeAgendaItem: jest.fn(),
}));

// queryClient 单例:只关心 invalidateQueries 被怎么调。
jest.mock('../../applib/queryClient', () => ({
  __esModule: true,
  queryClient: { invalidateQueries: jest.fn().mockResolvedValue(undefined) },
  persistOptions: {},
}));

// expo-notifications: handler 注册 + category API 在 module load 跑,给最小 stub。
jest.mock('expo-notifications', () => ({
  __esModule: true,
  setNotificationHandler: jest.fn(),
  setNotificationCategoryAsync: jest.fn().mockResolvedValue(undefined),
  getPermissionsAsync: jest.fn().mockResolvedValue({ status: 'granted' }),
  requestPermissionsAsync: jest.fn().mockResolvedValue({ status: 'granted' }),
  getDevicePushTokenAsync: jest.fn().mockResolvedValue({ data: 'tok' }),
  addNotificationReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
  addNotificationResponseReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
  DEFAULT_ACTION_IDENTIFIER: 'expo.modules.notifications.actions.DEFAULT',
}));

jest.mock('expo-device', () => ({ __esModule: true, isDevice: false }));
jest.mock('expo-constants', () => ({ __esModule: true, default: { expoConfig: { ios: {} } } }));
jest.mock('../../services/notifications', () => ({ bindIOSToken: jest.fn() }));
jest.mock('../../services/clientEvents', () => ({ emitClientEvent: jest.fn() }));
jest.mock('../../services/notificationRoutes', () => ({ resolveNotificationRoute: jest.fn() }));

import { handleAgendaAction } from '../useNotifications';
import { completeAgendaItem } from '../../services/agenda';
import { queryClient } from '../../applib/queryClient';

const mockCompleteAgendaItem = completeAgendaItem as jest.Mock;
const mockInvalidateQueries = queryClient.invalidateQueries as jest.Mock;

const REF = { object_type: 'health_protocol', object_id: 42 };

describe('handleAgendaAction (AGENDA_ACTION background action)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCompleteAgendaItem.mockResolvedValue({ wrote: true });
  });

  it('COMPLETE → completeAgendaItem with status done + invalidates home queries', async () => {
    await handleAgendaAction('done', { complete_ref: REF, category: 'AGENDA_ACTION' });

    expect(mockCompleteAgendaItem).toHaveBeenCalledTimes(1);
    expect(mockCompleteAgendaItem).toHaveBeenCalledWith(
      { object_type: 'health_protocol', object_id: 42 },
      'protocol',
      undefined,
      { status: 'done' },
    );
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['timeline', 'today'] });
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['agenda', 'today'] });
  });

  it('SKIP → completeAgendaItem with status skipped + invalidates home queries', async () => {
    await handleAgendaAction('skipped', { complete_ref: REF, category: 'AGENDA_ACTION' });

    expect(mockCompleteAgendaItem).toHaveBeenCalledWith(
      { object_type: 'health_protocol', object_id: 42 },
      'protocol',
      undefined,
      { status: 'skipped' },
    );
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['timeline', 'today'] });
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['agenda', 'today'] });
  });

  it('passes string object_id through unchanged (e.g. daily_plan_action keys)', async () => {
    await handleAgendaAction('done', {
      complete_ref: { object_type: 'medication', object_id: 'med_7' },
    });
    expect(mockCompleteAgendaItem).toHaveBeenCalledWith(
      { object_type: 'medication', object_id: 'med_7' },
      'protocol',
      undefined,
      { status: 'done' },
    );
  });

  it('no complete_ref → does nothing (no service call, no invalidation)', async () => {
    await handleAgendaAction('done', { category: 'AGENDA_ACTION' });
    await handleAgendaAction('done', undefined);
    await handleAgendaAction('done', { complete_ref: { object_type: 'health_protocol' } }); // missing id

    expect(mockCompleteAgendaItem).not.toHaveBeenCalled();
    expect(mockInvalidateQueries).not.toHaveBeenCalled();
  });

  it('swallows service failure at the listener boundary (does not throw)', async () => {
    mockCompleteAgendaItem.mockRejectedValueOnce(new Error('network down'));
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});

    await expect(
      handleAgendaAction('done', { complete_ref: REF }),
    ).resolves.toBeUndefined();

    // failure surfaced via log, not a thrown error; no invalidation on failure
    expect(warn).toHaveBeenCalled();
    expect(mockInvalidateQueries).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});
