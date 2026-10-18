import * as Notifications from 'expo-notifications';
import { cancelMedicationReminders, scheduleMedicationReminders } from '../medicationReminders';
jest.mock('react-native', () => ({ Platform: { OS: 'ios' } }));
jest.mock('expo-notifications', () => ({
  getPermissionsAsync: jest.fn(),
  getAllScheduledNotificationsAsync: jest.fn(),
  scheduleNotificationAsync: jest.fn(),
  cancelScheduledNotificationAsync: jest.fn(),
}));
const pending = Notifications.getAllScheduledNotificationsAsync as jest.Mock;
const cancel = Notifications.cancelScheduledNotificationAsync as jest.Mock;
beforeEach(() => {
  jest.clearAllMocks();
  pending.mockResolvedValue([
    { identifier: 'med-a', content: { data: { kind: 'medication_reminder' } } },
    { identifier: 'med-b', content: { data: { kind: 'medication_reminder' } } },
    { identifier: 'other', content: { data: { kind: 'open_loop' } } },
  ]);
  cancel.mockResolvedValue(undefined);
});
it('retires all legacy duplicates without creating another local reminder or asking permission', async () => {
  await expect(scheduleMedicationReminders([{ id: 1, name: 'private', dosage: 'private', reminder_times: ['18:30'] }])).resolves.toBe(0);
  expect(cancel.mock.calls).toEqual([['med-a'], ['med-b']]);
  expect(Notifications.scheduleNotificationAsync).not.toHaveBeenCalled();
  expect(Notifications.getPermissionsAsync).not.toHaveBeenCalled();
});
it('concurrent refreshes never schedule duplicates', async () => {
  await Promise.all([scheduleMedicationReminders([]), scheduleMedicationReminders([]), cancelMedicationReminders()]);
  expect(Notifications.scheduleNotificationAsync).not.toHaveBeenCalled();
  expect(cancel).not.toHaveBeenCalledWith('other');
});
it('surfaces native cancellation failure and permits a later retry', async () => {
  cancel.mockRejectedValueOnce(new Error('native unavailable'));
  await expect(cancelMedicationReminders()).rejects.toThrow('native unavailable');
  await expect(cancelMedicationReminders()).resolves.toBeUndefined();
});
