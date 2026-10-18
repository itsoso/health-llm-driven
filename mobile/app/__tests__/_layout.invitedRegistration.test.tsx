/* eslint-disable import/first, @typescript-eslint/no-require-imports */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

const mockReplace = jest.fn();
const mockClearInvite = jest.fn();
let mockInviteToken: string | null = null;
let mockSession: { mode: 'cloud_account'; cloudUser: { id: number } } | null = null;
let mockAuthenticated = false;
let mockLoading = false;
let mockLocked = false;
let mockSessionError: string | null = null;
let mockLockReady = true;
let mockLockInitializationFailed = false;
let mockNavigationKey: string | undefined = 'root';
const mockUseNotifications = jest.fn();
const mockRetryLockInitialization = jest.fn();

jest.mock('expo-router', () => {
  const ReactRuntime = require('react');
  const Stack = Object.assign(
    ({ children }: { children: React.ReactNode }) => ReactRuntime.createElement(
      ReactRuntime.Fragment,
      null,
      children,
    ),
    { Screen: () => null },
  );
  return {
    Stack,
    useRouter: () => ({ replace: mockReplace }),
    useRootNavigationState: () => mockNavigationKey ? { key: mockNavigationKey } : undefined,
    ErrorBoundary: ({ children }: { children: React.ReactNode }) => children,
  };
});

jest.mock('expo-status-bar', () => ({ StatusBar: () => null }));
jest.mock('@tanstack/react-query', () => ({
  focusManager: { setFocused: jest.fn() },
  QueryClientProvider: ({ children }: { children: React.ReactNode }) => children,
}));
jest.mock('react-native-gesture-handler', () => ({
  GestureHandlerRootView: ({ children }: { children: React.ReactNode }) => children,
}));
jest.mock('../../applib/queryClient', () => ({ queryClient: {}, retireLegacyQueryCache: jest.fn().mockResolvedValue(undefined) }));
jest.mock('../../applib/sentry', () => ({
  configureSentryForAppMode: jest.fn(),
  Sentry: { wrap: (component: unknown) => component },
  SENTRY_ENABLED: false,
}));

jest.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    isAuthenticated: mockAuthenticated,
    user: mockAuthenticated ? { id: 7 } : null,
    retrySession: jest.fn(),
  }),
}));
jest.mock('../../hooks/useAppSession', () => ({
  AppSessionProvider: ({ children }: { children: React.ReactNode }) => {
    const { View } = require('react-native');
    return <View testID="app-session-provider">{children}</View>;
  },
  useAppSession: () => ({ session: mockSession, isLoading: mockLoading, errorCode: mockSessionError }),
}));
jest.mock('../../hooks/useToast', () => ({ ToastProvider: ({ children }: { children: React.ReactNode }) => children }));
jest.mock('../../hooks/useAppUpdate', () => ({ AppUpdateProvider: ({ children }: { children: React.ReactNode }) => children }));
jest.mock('../../hooks/useNotifications', () => ({ useNotifications: (...args: unknown[]) => mockUseNotifications(...args) }));
jest.mock('../../hooks/useEyeBreakReminders', () => ({ useEyeBreakReminders: jest.fn() }));
jest.mock('../../hooks/useBiometricLock', () => ({
  useBiometricLock: () => ({
    isLocked: mockLocked,
    isReady: mockLockReady,
    initializationFailed: mockLockInitializationFailed,
    retryInitialization: mockRetryLockInitialization,
    authenticate: jest.fn(),
  }),
}));
jest.mock('../../hooks/useGPSAutoRefresh', () => ({ useGPSAutoRefresh: jest.fn() }));
jest.mock('../../hooks/useDeviceTimezoneSync', () => ({ useDeviceTimezoneSync: jest.fn() }));
jest.mock('../../hooks/useHealthKitForegroundSync', () => ({ useHealthKitForegroundSync: jest.fn() }));
jest.mock('../../components/reva/useRevaFonts', () => ({ useRevaFonts: jest.fn() }));
jest.mock('../../components/AppLockScreen', () => () => null);
jest.mock('../../components/notifications/NotificationBanner', () => () => null);
jest.mock('../../components/updates/AppUpdateBanner', () => () => null);
jest.mock('../../components/RootErrorBoundary', () => ({ children }: { children: React.ReactNode }) => children);
jest.mock('../../services/backgroundLocationTask', () => ({ registerBackgroundLocationTask: jest.fn() }));
const mockJourneyInitialize = jest.fn().mockResolvedValue(undefined);
jest.mock('../../services/dailyJourneyCapture', () => ({ dailyJourneyCapture: { initialize: () => mockJourneyInitialize() } }));
jest.mock('../../config/releaseCapabilities', () => ({ getReleaseCapabilities: () => ({ backgroundLocation: false }) }));
jest.mock('../../services/dietPhotoDraftStorage', () => ({
  loadDietPhotoDraft: jest.fn().mockResolvedValue(null),
}));
jest.mock('../../services/clientEvents', () => ({
  flushClientEventOutbox: jest.fn().mockResolvedValue(undefined),
}));
jest.mock('../../services/registrationInviteDeepLink', () => ({
  useRegistrationInviteDeepLink: () => ({ token: mockInviteToken, clear: mockClearInvite }),
}));
jest.mock('../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgPrimary: '#fff',
      bgCard: '#fff',
      brand: '#080',
      labelPrimary: '#111',
      labelSecondary: '#666',
    },
  }),
}));
jest.mock('../login', () => ({
  __esModule: true,
  default: (props: {
    invitationLinkToken?: string | null;
    registrationCompleted?: boolean;
    onInvitedRegistrationComplete?: () => void;
    onStartHealthProfile?: () => void;
  }) => {
    const { Text } = require('react-native');
    if (props.registrationCompleted) {
      return <Text testID="start-health-profile" onPress={props.onStartHealthProfile}>welcome</Text>;
    }
    return (
      <>
        <Text testID="login-invite-token">{props.invitationLinkToken ?? 'none'}</Text>
        <Text testID="complete-registration" onPress={props.onInvitedRegistrationComplete}>complete</Text>
      </>
    );
  },
}));

import { AppContent, RootLayout } from '../_layout';

describe('invited registration root integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockInviteToken = null;
    mockSession = null;
    mockAuthenticated = false;
    mockLoading = false;
    mockLocked = false;
    mockSessionError = null;
    mockLockReady = true;
    mockLockInitializationFailed = false;
    mockNavigationKey = 'root';
  });

  it('checks an existing journey only after authenticated hydration; never requests a new start', () => {
    const view = render(<AppContent />);
    expect(mockJourneyInitialize).not.toHaveBeenCalled();
    mockAuthenticated = true;
    mockSession = { mode: 'cloud_account', cloudUser: { id: 7 } };
    view.rerender(<AppContent />);
    expect(mockJourneyInitialize).toHaveBeenCalledTimes(1);
  });

  it('defers notification consumption until the app is unlocked and navigation is mounted', () => {
    mockAuthenticated = true;
    mockSession = { mode: 'cloud_account', cloudUser: { id: 7 } };
    mockLocked = true;
    const view = render(<AppContent />);
    expect(mockUseNotifications).toHaveBeenLastCalledWith(true, false);

    mockLocked = false;
    mockNavigationKey = undefined;
    view.rerender(<AppContent />);
    expect(mockUseNotifications).toHaveBeenLastCalledWith(true, false);

    mockNavigationKey = 'ready';
    view.rerender(<AppContent />);
    expect(mockUseNotifications).toHaveBeenLastCalledWith(true, true);
  });

  it('keeps authenticated content hidden until app lock initialization succeeds', () => {
    mockAuthenticated = true;
    mockSession = { mode: 'cloud_account', cloudUser: { id: 7 } };
    mockLockReady = false;
    mockLockInitializationFailed = true;

    render(<AppContent />);

    expect(screen.getByText('暂时无法确认应用锁状态')).toBeTruthy();
    fireEvent.press(screen.getByLabelText('重试应用锁检查'));
    expect(mockRetryLockInitialization).toHaveBeenCalledTimes(1);
    expect(mockUseNotifications).toHaveBeenLastCalledWith(true, false);
  });

  it('clears an in-memory invite as soon as auth is known, before session hydration, and does not revive it after logout', async () => {
    mockInviteToken = 'abcdefghijklmnopqrstuvwxyz_123456';
    mockAuthenticated = true;
    mockSession = null;
    const view = render(<AppContent />);

    await waitFor(() => expect(mockClearInvite).toHaveBeenCalledTimes(1));
    mockInviteToken = null;
    mockAuthenticated = false;
    mockSession = null;
    view.rerender(<AppContent />);

    expect(screen.getByTestId('login-invite-token')).toHaveTextContent('none');
  });

  it('preserves welcome then routes through the mounted root stack into Reva onboarding', async () => {
    render(<AppContent />);
    fireEvent.press(screen.getByTestId('complete-registration'));
    expect(screen.getByTestId('start-health-profile')).toHaveTextContent('welcome');

    mockAuthenticated = true;
    mockSession = { mode: 'cloud_account', cloudUser: { id: 9 } };
    fireEvent.press(screen.getByTestId('start-health-profile'));

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/reva-onboarding'));
  });

  it('mounts one app session/auth provider around the unauthenticated login surface', () => {
    render(<RootLayout />);
    expect(screen.getAllByTestId('app-session-provider')).toHaveLength(1);
    expect(screen.getByTestId('login-invite-token')).toBeTruthy();
  });
});

describe('notification navigation readiness', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSession = { mode: 'cloud_account', cloudUser: { id: 7 } };
    mockAuthenticated = true;
    mockLoading = false;
    mockLocked = false;
    mockSessionError = null;
    mockLockReady = true;
    mockNavigationKey = 'root';
  });
  it.each(['loading', 'locked', 'recovering'])('retains a cold-start tap until the root stack mounts: %s', (state) => {
    mockLoading = state === 'loading';
    mockLocked = state === 'locked';
    mockSessionError = state === 'recovering' ? 'session_recovery_required' : null;
    const view = render(<AppContent />);
    expect(mockUseNotifications).toHaveBeenLastCalledWith(true, false);
    mockLoading = false;
    mockLocked = false;
    mockSessionError = null;
    view.rerender(<AppContent />);
    expect(mockUseNotifications).toHaveBeenLastCalledWith(true, true);
  });
});
