jest.mock('react-native', () => ({ Platform: { OS: 'ios' } }));

jest.mock('expo-notifications', () => ({
  __esModule: true,
  SchedulableTriggerInputTypes: { DAILY: 'daily' },
  getPermissionsAsync: jest.fn(),
  getAllScheduledNotificationsAsync: jest.fn(),
  scheduleNotificationAsync: jest.fn(),
  cancelScheduledNotificationAsync: jest.fn(),
}));

import * as Notifications from 'expo-notifications';
import {
  buildReminderEntries,
  scheduleMedicationReminders,
  todayItemsToSources,
} from '../medicationReminders';

const mockNotif = Notifications as unknown as {
  getPermissionsAsync: jest.Mock;
  getAllScheduledNotificationsAsync: jest.Mock;
  scheduleNotificationAsync: jest.Mock;
  cancelScheduledNotificationAsync: jest.Mock;
};

beforeEach(() => {
  jest.clearAllMocks();
  mockNotif.getAllScheduledNotificationsAsync.mockResolvedValue([]);
  mockNotif.scheduleNotificationAsync.mockResolvedValue('id');
  mockNotif.cancelScheduledNotificationAsync.mockResolvedValue(undefined);
});

const med = (id: number, times: string[] | null) => ({
  id,
  name: `药${id}`,
  dosage: '1片',
  reminder_times: times,
});

describe('buildReminderEntries', () => {
  it('每药每时段各一条, 跳过空 reminder_times', () => {
    const entries = buildReminderEntries([
      med(1, ['08:00', '20:00']),
      med(2, []),
      med(3, null),
      med(4, ['12:30']),
    ]);
    expect(entries).toHaveLength(3);
    expect(entries.map((e) => `${e.medicationId}@${e.time}`)).toEqual([
      '1@08:00',
      '1@20:00',
      '4@12:30',
    ]);
    expect(entries[0]).toMatchObject({ hour: 8, minute: 0 });
    expect(entries[2]).toMatchObject({ hour: 12, minute: 30 });
  });

  it('丢弃非法时间格式', () => {
    expect(buildReminderEntries([med(1, ['25:00', 'abc', '9:5', '09:05'])])).toHaveLength(1);
  });
});

describe('todayItemsToSources', () => {
  it('medication_id 映射成 id', () => {
    const src = todayItemsToSources([
      {
        medication_id: 5,
        name: '二甲双胍',
        dosage: '0.5g',
        category: null,
        total_count: 2,
        taken_count: 0,
        skipped_count: 0,
        last_taken_time: null,
        reminder_times: ['08:00'],
        logs: [],
      },
    ]);
    expect(src[0]).toEqual({ id: 5, name: '二甲双胍', dosage: '0.5g', reminder_times: ['08:00'] });
  });
});

describe('scheduleMedicationReminders', () => {
  it('有权限时: 先 cancel 旧的, 再按时段数排新的', async () => {
    mockNotif.getPermissionsAsync.mockResolvedValue({ status: 'granted' });
    mockNotif.getAllScheduledNotificationsAsync.mockResolvedValue([
      { identifier: 'old1', content: { data: { kind: 'medication_reminder' } } },
      { identifier: 'other', content: { data: { kind: 'open_loop' } } },
    ]);

    const n = await scheduleMedicationReminders([med(1, ['08:00', '20:00'])]);

    expect(n).toBe(2);
    // 只 cancel 自己排的, 不动 open_loop
    expect(mockNotif.cancelScheduledNotificationAsync).toHaveBeenCalledTimes(1);
    expect(mockNotif.cancelScheduledNotificationAsync).toHaveBeenCalledWith('old1');
    expect(mockNotif.scheduleNotificationAsync).toHaveBeenCalledTimes(2);

    const firstCall = mockNotif.scheduleNotificationAsync.mock.calls[0][0];
    expect(firstCall.trigger).toEqual({ type: 'daily', hour: 9, minute: 0 });
    expect(firstCall.content.categoryIdentifier).toBe('MEDICATION_REMINDER');
    expect(firstCall.content.data).toMatchObject({
      reminder_type: 'medication',
      medication_id: 1,
      taken_time: '08:00',
      scheduled_time: '09:00',
    });
  });

  it('§5 推送隐私: 锁屏可见 title/body 不带药名/剂量, 名称只进 data', async () => {
    mockNotif.getPermissionsAsync.mockResolvedValue({ status: 'granted' });
    mockNotif.getAllScheduledNotificationsAsync.mockResolvedValue([]);

    await scheduleMedicationReminders([
      { id: 9, name: '二甲双胍', dosage: '500mg', reminder_times: ['08:00'] },
    ]);

    const call = mockNotif.scheduleNotificationAsync.mock.calls[0][0];
    expect(call.content.title).not.toContain('二甲双胍');
    expect(call.content.body).not.toContain('二甲双胍');
    expect(call.content.body).not.toContain('500mg');
    expect(call.content.data).toMatchObject({
      medication_name: '二甲双胍',
      dosage: '500mg',
    });
  });

  it('无权限时: 不排新的 (返回 0)', async () => {
    mockNotif.getPermissionsAsync.mockResolvedValue({ status: 'denied' });
    const n = await scheduleMedicationReminders([med(1, ['08:00'])]);
    expect(n).toBe(0);
    expect(mockNotif.scheduleNotificationAsync).not.toHaveBeenCalled();
  });
});
