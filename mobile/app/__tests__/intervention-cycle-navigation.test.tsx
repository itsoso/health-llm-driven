import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import InterventionCycleRoute from '../intervention-cycle';

const mockBack = jest.fn();
const mockReplace = jest.fn();
const mockPush = jest.fn();
const mockStart = jest.fn();
const mockRecheck = jest.fn();
let mockCanGoBack = true;
let mockFontsLoaded = true;
let mockLoading = false;
let mockCycle: Record<string, unknown> | undefined;

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: mockBack, replace: mockReplace, push: mockPush, canGoBack: () => mockCanGoBack }),
}));
jest.mock('../../components/reva/useRevaFonts', () => ({ useRevaFonts: () => mockFontsLoaded }));
jest.mock('../../hooks/useHealthOs', () => ({
  useActiveCycle: () => ({ data: mockCycle, isLoading: mockLoading }),
  useStartCycle: () => ({ mutate: mockStart }),
  useRecheckCycle: () => ({ mutate: mockRecheck }),
  useTreatmentEffect: () => ({ data: undefined }),
}));

describe('intervention cycle return navigation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockCanGoBack = true;
    mockFontsLoaded = true;
    mockLoading = false;
    mockCycle = { id: 1, status: 'active', outcomes: [], stop_conditions: [] };
  });

  it.each(['active', 'rechecked', 'empty', 'loading', 'fonts'] as const)(
    'offers a working return control in the %s state', (state) => {
      if (state === 'rechecked') mockCycle!.latest_snapshot_id = 2;
      if (state === 'empty') mockCycle = undefined;
      if (state === 'loading') mockLoading = true;
      if (state === 'fonts') mockFontsLoaded = false;
      const view = render(<InterventionCycleRoute />);
      fireEvent.press(view.getByRole('button', { name: '返回' }));
      expect(mockBack).toHaveBeenCalledTimes(1);
      expect(mockReplace).not.toHaveBeenCalled();
      expect(mockPush).not.toHaveBeenCalled();
      expect(mockStart).not.toHaveBeenCalled();
      expect(mockRecheck).not.toHaveBeenCalled();
    },
  );

  it('replaces a direct link with the main chat when there is no previous screen', () => {
    mockCanGoBack = false;
    const view = render(<InterventionCycleRoute />);
    fireEvent.press(view.getByRole('button', { name: '返回' }));
    expect(mockReplace).toHaveBeenCalledWith('/(tabs)/chat');
    expect(mockBack).not.toHaveBeenCalled();
    expect(mockPush).not.toHaveBeenCalled();
  });
});
