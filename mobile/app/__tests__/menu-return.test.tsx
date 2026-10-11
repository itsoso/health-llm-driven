import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import AlertsScreen from '../(tabs)/alerts';
import JournalScreen from '../(tabs)/journal';
import AccountSecurityScreen from '../account-security';
import CaseDetailScreen from '../(tabs)/journal/[id]';
import TraceDetailScreen from '../trace/[id]';

const mockNavigate = jest.fn();
const mockBack = jest.fn();
const mockReplace = jest.fn();
let mockCanGoBack = false;
let mockLoading = false;
jest.mock('expo-router', () => ({
  router: { navigate: (...args: unknown[]) => mockNavigate(...args) },
  useRouter: () => ({ navigate: mockNavigate, back: mockBack, replace: mockReplace, canGoBack: () => mockCanGoBack }),
  Stack: { Screen: () => null },
  useLocalSearchParams: () => ({ id: '1' }),
}));
jest.mock('@tanstack/react-query', () => ({ useQuery: () => ({ isLoading: mockLoading, refetch: jest.fn() }) }));
jest.mock('../../hooks/useJournalTimeline', () => ({ useJournalTimeline: () => ({ isLoading: mockLoading, refetch: jest.fn() }) }));
jest.mock('../../hooks/useClinicalJournal', () => ({ useCaseDetail: () => ({ isLoading: mockLoading, refetch: jest.fn() }) }));
jest.mock('../../hooks/useReasoningTrace', () => ({ useTraceDetail: () => ({ isLoading: mockLoading, refetch: jest.fn() }) }));
jest.mock('../../hooks/useToast', () => ({ useToast: () => ({ show: jest.fn() }) }));
jest.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user: { has_password: true } }) }));
jest.mock('../../services/clientEvents', () => ({ emitClientEvent: jest.fn() }));
jest.mock('../../services/auth', () => ({ changePassword: jest.fn(), setPassword: jest.fn() }));

describe('menu destinations always have an exit', () => {
  beforeEach(() => { jest.clearAllMocks(); mockCanGoBack = false; mockLoading = false; });
  it.each([
    ['safety', AlertsScreen], ['journal', JournalScreen],
  ])('%s exposes a home exit during loading and when empty', (_name, Screen) => {
    for (const loading of [true, false]) {
      mockNavigate.mockClear();
      mockLoading = loading;
      const view = render(<Screen />);
      fireEvent.press(view.getByRole('button', { name: '返回小巴' }));
      expect(mockNavigate).toHaveBeenLastCalledWith('/(tabs)/chat');
      expect(mockNavigate).toHaveBeenCalledTimes(1);
      view.unmount();
    }
  });
  it.each([true, false])('account security returns with history=%s', (history) => {
    mockCanGoBack = history;
    const view = render(<AccountSecurityScreen />);
    fireEvent.press(view.getByRole('button', { name: '返回' }));
    if (history) {
      expect(mockBack).toHaveBeenCalledTimes(1);
      expect(mockReplace).not.toHaveBeenCalled();
    } else {
      expect(mockReplace).toHaveBeenCalledWith('/(tabs)/chat');
      expect(mockBack).not.toHaveBeenCalled();
    }
  });
  it.each([['case detail', CaseDetailScreen], ['trace detail', TraceDetailScreen]])('%s can exit loading and missing data', (_name, Screen) => {
    for (const loading of [true, false]) {
      mockReplace.mockClear();
      mockLoading = loading;
      const view = render(<Screen />);
      fireEvent.press(view.getByRole('button', { name: '返回' }));
      expect(mockReplace).toHaveBeenLastCalledWith('/(tabs)/chat');
      expect(mockReplace).toHaveBeenCalledTimes(1);
      view.unmount();
    }
  });
});
