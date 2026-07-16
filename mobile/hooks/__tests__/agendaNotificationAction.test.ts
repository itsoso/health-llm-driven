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

jest.mock('../../services/medications', () => ({
  __esModule: true,
  logMedication: jest.fn(),
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
  getLastNotificationResponseAsync: jest.fn().mockResolvedValue(null),
  clearLastNotificationResponseAsync: jest.fn().mockResolvedValue(undefined),
  scheduleNotificationAsync: jest.fn().mockResolvedValue('medication-action-failed'),
  dismissNotificationAsync: jest.fn().mockResolvedValue(undefined),
  DEFAULT_ACTION_IDENTIFIER: 'expo.modules.notifications.actions.DEFAULT',
}));

jest.mock('expo-device', () => ({ __esModule: true, isDevice: false }));
jest.mock('expo-constants', () => ({ __esModule: true, default: { expoConfig: { ios: {} } } }));
jest.mock('../../services/notifications', () => ({ bindIOSToken: jest.fn() }));
jest.mock('../../services/clientEvents', () => ({ emitClientEvent: jest.fn() }));
jest.mock('../../services/notificationRoutes', () => ({ resolveNotificationRoute: jest.fn() }));

import * as Notifications from 'expo-notifications';
import {
  consumeLastNotificationResponse,
  consumeNotificationResponse,
  handleAgendaAction,
  handleMedicationReminderAction,
  registerNotificationCategories,
} from '../useNotifications';
import { completeAgendaItem } from '../../services/agenda';
import { logMedication } from '../../services/medications';
import { queryClient } from '../../applib/queryClient';
import { emitClientEvent } from '../../services/clientEvents';

const mockCompleteAgendaItem = completeAgendaItem as jest.Mock;
const mockInvalidateQueries = queryClient.invalidateQueries as jest.Mock;
const mockEmitClientEvent = emitClientEvent as jest.Mock;
const mockLogMedication = logMedication as jest.Mock;
const mockNotifications = Notifications as unknown as {
  setNotificationCategoryAsync: jest.Mock;
  getLastNotificationResponseAsync: jest.Mock;
  clearLastNotificationResponseAsync: jest.Mock;
  scheduleNotificationAsync: jest.Mock;
  dismissNotificationAsync: jest.Mock;
};

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

  it('numeric string object_id is coerced before completing', async () => {
    await handleAgendaAction('done', {
      complete_ref: { object_type: 'medication', object_id: '7' },
    });
    expect(mockCompleteAgendaItem).toHaveBeenCalledWith(
      { object_type: 'medication', object_id: 7 },
      'protocol',
      undefined,
      { status: 'done' },
    );
  });

  it('non-numeric object_id is rejected and recorded without posting', async () => {
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});

    await handleAgendaAction('done', {
      complete_ref: { object_type: 'medication', object_id: 'med_7' },
    });

    expect(mockCompleteAgendaItem).not.toHaveBeenCalled();
    expect(mockInvalidateQueries).not.toHaveBeenCalled();
    expect(mockEmitClientEvent).toHaveBeenCalledWith(
      'agenda_action_failed',
      expect.objectContaining({
        reason: 'invalid_object_id',
        object_type: 'medication',
        object_id: 'med_7',
      }),
    );
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
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
    expect(mockEmitClientEvent).toHaveBeenCalledWith(
      'agenda_action_failed',
      expect.objectContaining({
        reason: 'request_failed',
        object_type: 'health_protocol',
        object_id: 42,
      }),
    );
    expect(mockInvalidateQueries).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});

describe('Watch medication reminder action', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockLogMedication.mockResolvedValue({ id: 88, medication_id: 7, status: 'taken' });
    mockNotifications.getLastNotificationResponseAsync.mockResolvedValue(null);
    mockNotifications.clearLastNotificationResponseAsync.mockResolvedValue(undefined);
    mockNotifications.scheduleNotificationAsync.mockResolvedValue('medication-action-failed');
    mockNotifications.dismissNotificationAsync.mockResolvedValue(undefined);
  });

  it('registers 服用 as a reliable action that wakes a terminated iOS app', async () => {
    await registerNotificationCategories();

    const medicationCall = mockNotifications.setNotificationCategoryAsync.mock.calls
      .find(([identifier]) => identifier === 'MEDICATION_REMINDER');
    expect(medicationCall).toBeTruthy();
    expect(medicationCall[1]).toEqual(expect.arrayContaining([
      expect.objectContaining({
        identifier: 'TAKEN',
        buttonTitle: '服用',
        options: expect.objectContaining({ opensAppToForeground: true }),
      }),
    ]));
  });

  it('writes a taken MedicationLog with the reminder slot and refreshes medication state', async () => {
    await handleMedicationReminderAction('TAKEN', {
      reminder_type: 'medication',
      medication_id: '7',
      scheduled_date: '2026-07-16',
      scheduled_time: '08:30',
      scheduled_timezone: 'Asia/Shanghai',
      rule_id: 'medication_reminder.7.2026-07-16.08:30',
    });

    expect(mockLogMedication).toHaveBeenCalledWith({
      medication_id: 7,
      taken_date: '2026-07-16',
      taken_time: '08:30',
      status: 'taken',
    });
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['medications'] });
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['medicationToday'] });
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['timeline', 'today'] });
  });

  it('consumes a cold-start Watch action and clears it to prevent a second write', async () => {
    const response = {
      actionIdentifier: 'TAKEN',
      notification: {
        request: {
          identifier: 'medication-reminder-7-0830',
          content: {
            data: {
              reminder_type: 'medication',
              medication_id: 7,
              scheduled_date: '2026-07-16',
              scheduled_time: '08:30',
              scheduled_timezone: 'Asia/Shanghai',
              rule_id: 'medication_reminder.7.2026-07-16.08:30',
            },
          },
        },
      },
    };
    mockNotifications.getLastNotificationResponseAsync.mockResolvedValue(response);

    await consumeLastNotificationResponse();

    expect(mockLogMedication).toHaveBeenCalledTimes(1);
    expect(mockNotifications.clearLastNotificationResponseAsync).toHaveBeenCalledTimes(1);
  });

  it('keeps a failed cold-start Watch action available for a later retry', async () => {
    mockLogMedication.mockRejectedValueOnce(new Error('offline'));
    mockNotifications.getLastNotificationResponseAsync.mockResolvedValue({
      actionIdentifier: 'TAKEN',
      notification: {
        request: {
          identifier: 'medication-reminder-7-0900',
          content: {
            data: {
              reminder_type: 'medication',
              medication_id: 7,
              scheduled_date: '2026-07-16',
              scheduled_time: '09:00',
              scheduled_timezone: 'Asia/Shanghai',
              rule_id: 'medication_reminder.7.2026-07-16.09:00',
            },
          },
        },
      },
    });
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});

    await consumeLastNotificationResponse();

    expect(mockLogMedication).toHaveBeenCalledTimes(1);
    expect(mockNotifications.clearLastNotificationResponseAsync).not.toHaveBeenCalled();
    expect(mockEmitClientEvent).toHaveBeenCalledWith(
      'watch_action_failed',
      expect.objectContaining({ reason: 'request_failed', kind: 'medication' }),
    );
    expect(mockNotifications.scheduleNotificationAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        content: expect.objectContaining({
          title: '用药打卡未保存',
          body: expect.not.stringContaining('药'),
        }),
        trigger: null,
      }),
    );

    mockLogMedication.mockResolvedValueOnce({ id: 89, medication_id: 7, status: 'taken' });
    await consumeLastNotificationResponse();

    expect(mockLogMedication).toHaveBeenCalledTimes(2);
    expect(mockNotifications.clearLastNotificationResponseAsync).toHaveBeenCalledTimes(1);
    expect(mockNotifications.dismissNotificationAsync).toHaveBeenCalled();
    warn.mockRestore();
  });

  it('fails closed when the medication occurrence date, timezone or rule id is missing', async () => {
    await expect(handleMedicationReminderAction('TAKEN', {
      reminder_type: 'medication',
      medication_id: 7,
      scheduled_time: '08:30',
    })).resolves.toBe(false);

    expect(mockLogMedication).not.toHaveBeenCalled();
    expect(mockEmitClientEvent).toHaveBeenCalledWith(
      'watch_action_failed',
      expect.objectContaining({ reason: 'invalid_medication_occurrence' }),
    );
  });

  it('uses rule_id rather than a reused iOS request id to deduplicate daily occurrences', async () => {
    const responseFor = (date: string) => ({
      actionIdentifier: 'TAKEN',
      notification: {
        date: Date.parse(`${date}T08:30:00+08:00`),
        request: {
          identifier: 'repeating-medication-request-7',
          content: {
            data: {
              reminder_type: 'medication',
              medication_id: 7,
              scheduled_date: date,
              scheduled_time: '08:30',
              scheduled_timezone: 'Asia/Shanghai',
              rule_id: `medication_reminder.7.${date}.08:30`,
            },
          },
        },
      },
    });

    await consumeNotificationResponse(responseFor('2026-07-18') as any);
    await consumeNotificationResponse(responseFor('2026-07-19') as any);

    expect(mockLogMedication).toHaveBeenCalledTimes(2);
    expect(mockLogMedication).toHaveBeenNthCalledWith(1, expect.objectContaining({ taken_date: '2026-07-18' }));
    expect(mockLogMedication).toHaveBeenNthCalledWith(2, expect.objectContaining({ taken_date: '2026-07-19' }));
  });
});
