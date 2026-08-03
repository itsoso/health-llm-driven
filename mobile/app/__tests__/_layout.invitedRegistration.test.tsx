/* eslint-disable import/first, @typescript-eslint/no-require-imports */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

const mockReplace = jest.fn();
const mockClearInvite = jest.fn();
let mockInviteToken: string | null = null;
let mockSession: { mode: 'cloud_account'; cloudUser: { id: number } } | null = null;
let mockAuthenticated = false;

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
    ErrorBoundary: ({ children }: { children: React.ReactNode }) => children,
  };
});

jest.mock('expo-status-bar', () => ({ StatusBar: () => null }));
jest.mock('@tanstack/react-query', () => ({ focusManager: { setFocused: jest.fn() } }));
jest.mock('@tanstack/react-query-persist-client', () => ({
  PersistQueryClientProvider: ({ children }: { children: React.ReactNode }) => children,
}));
jest.mock('react-native-gesture-handler', () => ({
  GestureHandlerRootView: ({ children }: { children: React.ReactNode }) => children,
}));
jest.mock('../../applib/queryClient', () => ({ queryClient: {}, persistOptions: {} }));
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
  useAppSession: () => ({ session: mockSession, isLoading: false, errorCode: null }),
}));
jest.mock('../../hooks/useToast', () => ({ ToastProvider: ({ children }: { children: React.ReactNode }) => children }));
jest.mock('../../hooks/useAppUpdate', () => ({ AppUpdateProvider: ({ children }: { children: React.ReactNode }) => children }));
jest.mock('../../hooks/useNotifications', () => ({ useNotifications: jest.fn() }));
jest.mock('../../hooks/useEyeBreakReminders', () => ({ useEyeBreakReminders: jest.fn() }));
jest.mock('../../hooks/useBiometricLock', () => ({ useBiometricLock: () => ({ isLocked: false, authenticate: jest.fn() }) }));
jest.mock('../../hooks/useGPSAutoRefresh', () => ({ useGPSAutoRefresh: jest.fn() }));
jest.mock('../../hooks/useDeviceTimezoneSync', () => ({ useDeviceTimezoneSync: jest.fn() }));
jest.mock('../../hooks/useHealthKitForegroundSync', () => ({ useHealthKitForegroundSync: jest.fn() }));
jest.mock('../../components/reva/useRevaFonts', () => ({ useRevaFonts: jest.fn() }));
jest.mock('../../components/AppLockScreen', () => () => null);
jest.mock('../../components/notifications/NotificationBanner', () => () => null);
jest.mock('../../components/updates/AppUpdateBanner', () => () => null);
jest.mock('../../components/RootErrorBoundary', () => ({ children }: { children: React.ReactNode }) => children);
jest.mock('../../services/backgroundLocationTask', () => ({ registerBackgroundLocationTask: jest.fn() }));
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
