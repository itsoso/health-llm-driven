import React from 'react';
import { act, fireEvent, render } from '@testing-library/react-native';
import type { Notification } from 'expo-notifications';
import NotificationBanner from '../NotificationBanner';

const mockAnimationCallbacks: ((finished?: boolean) => void)[] = [];
let mockForegroundListener: ((notification: Notification) => void) | null = null;

jest.mock('react-native-reanimated', () => {
  const { View } = jest.requireActual('react-native');
  return {
    __esModule: true,
    default: { View },
    useSharedValue: (value: number) => ({ value }),
    useAnimatedStyle: (factory: () => object) => factory(),
    withSpring: (value: number, _config: object, callback?: (finished?: boolean) => void) => {
      if (callback) mockAnimationCallbacks.push(callback);
      return value;
    },
    runOnJS: (callback: (...args: any[]) => unknown) => callback,
  };
});

jest.mock('react-native-safe-area-context', () => ({
  useSafeAreaInsets: () => ({ top: 0, right: 0, bottom: 0, left: 0 }),
}));

jest.mock('../../../hooks/useNotifications', () => ({
  setOnForegroundNotification: (listener: ((notification: Notification) => void) | null) => {
    mockForegroundListener = listener;
  },
}));

jest.mock('../../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      brand: '#159767',
      bgCard: '#ffffff',
      labelPrimary: '#111111',
      labelSecondary: '#666666',
    },
  }),
}));

function notification(identifier: string, title: string): Notification {
  return {
    request: {
      identifier,
      content: { title, body: `${title}正文`, data: {} },
      trigger: null,
    },
    date: Date.now(),
  } as Notification;
}

describe('NotificationBanner', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockAnimationCallbacks.length = 0;
    mockForegroundListener = null;
  });

  it('does not let a cancelled old exit animation clear a newer notification', () => {
    const screen = render(<NotificationBanner />);
    const first = notification('first', '第一条提醒');
    const second = notification('second', '第二条提醒');

    act(() => {
      mockForegroundListener?.(first);
    });
    fireEvent.press(screen.getByText('第一条提醒'));

    act(() => {
      mockForegroundListener?.(second);
    });
    act(() => {
      mockAnimationCallbacks[0]?.(false);
    });

    expect(screen.getByText('第二条提醒')).toBeTruthy();
  });
});
