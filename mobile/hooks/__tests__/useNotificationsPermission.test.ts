/* eslint-disable import/first */
const mockGetPermissionsAsync = jest.fn();
const mockRequestPermissionsAsync = jest.fn();
const mockGetDevicePushTokenAsync = jest.fn();
const mockBindIOSToken = jest.fn();

jest.mock('react-native', () => ({ Platform: { OS: 'ios' } }));
jest.mock('expo-device', () => ({ isDevice: true }));
jest.mock('expo-constants', () => ({
  expoConfig: { ios: { bundleIdentifier: 'life.executor.health' } },
}));
jest.mock('expo-router', () => ({ router: { push: jest.fn() } }));
jest.mock('expo-notifications', () => ({
  setNotificationHandler: jest.fn(),
  getPermissionsAsync: (...args: unknown[]) => mockGetPermissionsAsync(...args),
  requestPermissionsAsync: (...args: unknown[]) => mockRequestPermissionsAsync(...args),
  getDevicePushTokenAsync: (...args: unknown[]) => mockGetDevicePushTokenAsync(...args),
  setNotificationCategoryAsync: jest.fn(),
  addNotificationReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
  addNotificationResponseReceivedListener: jest.fn(() => ({ remove: jest.fn() })),
}));
jest.mock('../../services/notifications', () => ({
  bindIOSToken: (...args: unknown[]) => mockBindIOSToken(...args),
}));
jest.mock('../../services/clientEvents', () => ({ emitClientEvent: jest.fn() }));
jest.mock('../../services/notificationRoutes', () => ({ resolveNotificationRoute: jest.fn() }));
jest.mock('../../applib/queryClient', () => ({ queryClient: { invalidateQueries: jest.fn() } }));
jest.mock('../../services/agenda', () => ({ completeAgendaItem: jest.fn() }));

import {
  requestPushPermissionAndRegister,
  syncGrantedPushRegistration,
} from '../useNotifications';

describe('contextual push permission', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetDevicePushTokenAsync.mockResolvedValue({ data: 'device-token' });
    mockBindIOSToken.mockResolvedValue(undefined);
  });

  it('does not request notification permission during authenticated startup', async () => {
    mockGetPermissionsAsync.mockResolvedValue({ status: 'undetermined' });

    await expect(syncGrantedPushRegistration()).resolves.toEqual({
      status: 'not_granted',
      bound: false,
    });

    expect(mockRequestPermissionsAsync).not.toHaveBeenCalled();
    expect(mockBindIOSToken).not.toHaveBeenCalled();
  });

  it('requests and binds only after an explicit user action', async () => {
    mockGetPermissionsAsync.mockResolvedValue({ status: 'undetermined' });
    mockRequestPermissionsAsync.mockResolvedValue({ status: 'granted' });

    await expect(requestPushPermissionAndRegister()).resolves.toEqual({
      status: 'granted',
      bound: true,
    });

    expect(mockRequestPermissionsAsync).toHaveBeenCalledTimes(1);
    expect(mockBindIOSToken).toHaveBeenCalledWith('device-token', 'life.executor.health');
  });
});
