import { act, renderHook, waitFor } from '@testing-library/react-native';
import { AppState } from 'react-native';
import { useNotifications } from '../useNotifications';
const mockCancel = jest.fn();
jest.mock('../../services/medicationReminders', () => ({ cancelMedicationReminders: () => mockCancel() }));
jest.mock('expo-notifications', () => ({ setNotificationHandler: jest.fn() }));
jest.mock('expo-device', () => ({ isDevice: false }));
jest.mock('expo-constants', () => ({ expoConfig: {} }));
jest.mock('expo-router', () => ({ router: { push: jest.fn() } }));
jest.mock('../useToast', () => ({ useToast: () => ({ show: jest.fn() }) }));
jest.mock('../../services/notifications', () => ({ bindIOSToken: jest.fn() }));
jest.mock('../../applib/queryClient', () => ({ queryClient: { invalidateQueries: jest.fn() } }));

it('cleans legacy reminders even before login and retries after foreground on failure', async () => {
  mockCancel.mockRejectedValueOnce(new Error('native unavailable')).mockResolvedValue(undefined);
  const warning = jest.spyOn(console, 'warn').mockImplementation(() => {});
  let listener: (state: string) => void = () => {};
  const remove = jest.fn();
  const subscription = jest.spyOn(AppState, 'addEventListener').mockImplementation((_event, callback) => {
    listener = callback as typeof listener;
    return { remove };
  });
  const { unmount } = renderHook(() => useNotifications(false, false));
  await waitFor(() => expect(mockCancel).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(warning).toHaveBeenCalled());
  act(() => listener('active'));
  await waitFor(() => expect(mockCancel).toHaveBeenCalledTimes(2));
  unmount();
  expect(remove).toHaveBeenCalled();
  subscription.mockRestore();
  warning.mockRestore();
});
