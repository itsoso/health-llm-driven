/* eslint-disable import/first */
const mockPush = jest.fn();
const mockClear = jest.fn().mockResolvedValue(undefined);
const mockLast = jest.fn();

jest.mock('expo-router', () => ({ router: { push: (...args: unknown[]) => mockPush(...args) } }));
jest.mock('expo-notifications', () => ({
  setNotificationHandler: jest.fn(),
  getLastNotificationResponseAsync: (...args: unknown[]) => mockLast(...args),
  clearLastNotificationResponseAsync: (...args: unknown[]) => mockClear(...args),
}));
jest.mock('expo-device', () => ({ isDevice: false }));
jest.mock('expo-constants', () => ({ expoConfig: { ios: {} } }));
jest.mock('../../services/notifications', () => ({ bindIOSToken: jest.fn() }));
jest.mock('../../services/api', () => ({ __esModule: true, default: { post: jest.fn() } }));
jest.mock('../../applib/queryClient', () => ({ queryClient: { invalidateQueries: jest.fn() } }));
jest.mock('../../services/clientEvents', () => ({ emitClientEvent: jest.fn() }));

import type { NotificationResponse } from 'expo-notifications';
import { consumeLastNotificationResponse, consumeNotificationResponse } from '../useNotifications';

function response(id: string, data: Record<string, unknown>): NotificationResponse {
  return {
    actionIdentifier: 'expo.modules.notifications.actions.DEFAULT',
    notification: { request: { identifier: id, content: { data } } },
  } as NotificationResponse;
}

describe('notification tap landing', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockPush.mockReset();
  });

  it.each(['/notification-history', '/workout-detail?id=123', '/episode/456'])(
    'opens the intended destination %s', async (path) => {
      await expect(consumeNotificationResponse(response(path, { deep_link: path }))).resolves.toBe(true);
      expect(mockPush).toHaveBeenCalledWith(path);
      expect(mockClear).toHaveBeenCalledTimes(1);
    },
  );

  it('lands on notification history when no destination is provided', async () => {
    await consumeNotificationResponse(response('missing-destination', {}));
    expect(mockPush).toHaveBeenCalledWith('/notification-history');
  });

  it('retains a cold-start response when navigation fails, then opens it after readiness', async () => {
    const notification = response('cold-start-retry', { deep_link: '/notification-history' });
    mockLast.mockResolvedValue(notification);
    mockPush.mockImplementationOnce(() => { throw new Error('Navigator not mounted'); });
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      await expect(consumeLastNotificationResponse()).resolves.toBe(false);
      expect(mockClear).not.toHaveBeenCalled();
      expect(mockPush).toHaveBeenCalledTimes(1);

      await expect(consumeLastNotificationResponse()).resolves.toBe(true);
      expect(mockPush).toHaveBeenLastCalledWith('/notification-history');
      expect(mockClear).toHaveBeenCalledTimes(1);
    } finally {
      warn.mockRestore();
    }
  });

  it('retains a response when readiness changes while the native response is loading', async () => {
    const notification = response('readiness-race', { deep_link: '/notification-history' });
    let resolveLast: ((value: NotificationResponse) => void) | undefined;
    mockLast.mockReturnValue(new Promise<NotificationResponse>((resolve) => { resolveLast = resolve; }));
    let ready = true;

    const pending = consumeLastNotificationResponse(undefined, { canNavigate: () => ready });
    ready = false;
    resolveLast?.(notification);

    await expect(pending).resolves.toBe(false);
    expect(mockPush).not.toHaveBeenCalled();
    expect(mockClear).not.toHaveBeenCalled();

    ready = true;
    mockLast.mockResolvedValue(notification);
    await expect(consumeLastNotificationResponse(undefined, { canNavigate: () => ready })).resolves.toBe(true);
    expect(mockPush).toHaveBeenCalledWith('/notification-history');
    expect(mockClear).toHaveBeenCalledTimes(1);
  });
});
