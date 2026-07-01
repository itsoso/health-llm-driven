import React from 'react';
import { act, render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import WriteIntentCard from '../WriteIntentCard';

const mockGetWriteIntents = jest.fn();
const mockConfirmWriteIntent = jest.fn();
const mockDismissWriteIntent = jest.fn();

jest.mock('../../../services/writeIntents', () => ({
  getWriteIntents: (...args: any[]) => mockGetWriteIntents(...args),
  confirmWriteIntent: (...args: any[]) => mockConfirmWriteIntent(...args),
  dismissWriteIntent: (...args: any[]) => mockDismissWriteIntent(...args),
}));

function renderWithQuery(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false, gcTime: Infinity },
    },
  });
  const invalidateSpy = jest.spyOn(qc, 'invalidateQueries');
  const screen = render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
  return { ...screen, qc, invalidateSpy };
}

describe('WriteIntentCard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetWriteIntents.mockResolvedValue([
      {
        id: 101,
        kind: 'recheck_due',
        title: '复查到期:血脂四项',
        description: '血脂四项复查到期,可预约心血管内科。',
        status: 'pending',
        source: 'recheck_window',
        trust_tier: 'manual_confirm',
        target_type: 'intervention_cycle',
        target_id: 7,
        payload: null,
        executed_ref: null,
        created_at: '2026-07-01T09:00:00Z',
      },
      {
        id: 102,
        kind: 'recheck_due',
        title: '复查到期:空腹血糖 / 糖化血红蛋白',
        description: '空腹血糖 / 糖化血红蛋白复查到期,可预约内分泌科。',
        status: 'pending',
        source: 'recheck_window',
        trust_tier: 'manual_confirm',
        target_type: 'intervention_cycle',
        target_id: 8,
        payload: null,
        executed_ref: null,
        created_at: '2026-07-01T09:01:00Z',
      },
    ]);
  });

  it('confirms the second pending item with visible progress and refreshes home data', async () => {
    let resolveConfirm!: (value: { status: string; executed_ref: string }) => void;
    mockConfirmWriteIntent.mockReturnValue(new Promise(resolve => {
      resolveConfirm = resolve;
    }));

    const {
      getByLabelText,
      getByText,
      queryByLabelText,
      queryByText,
      invalidateSpy,
      unmount,
      qc,
      UNSAFE_getByProps,
    } = renderWithQuery(<WriteIntentCard />);

    expect(await waitFor(() => getByText('复查到期:空腹血糖 / 糖化血红蛋白'))).toBeTruthy();

    const secondConfirm = UNSAFE_getByProps({
      accessibilityLabel: '确认:复查到期:空腹血糖 / 糖化血红蛋白',
    });
    expect(secondConfirm?.props.onPress).toEqual(expect.any(Function));

    await act(async () => {
      secondConfirm?.props.onPress();
    });

    await waitFor(() => expect(mockConfirmWriteIntent).toHaveBeenCalledWith(102));
    expect(getByText('执行中')).toBeTruthy();

    expect(getByLabelText('执行中:复查到期:空腹血糖 / 糖化血红蛋白')).toBeTruthy();
    expect(queryByLabelText('确认:复查到期:空腹血糖 / 糖化血红蛋白')).toBeNull();
    expect(mockConfirmWriteIntent).toHaveBeenCalledTimes(1);

    resolveConfirm({ status: 'executed', executed_ref: 'smart_reminder:55' });

    await waitFor(() => {
      expect(getByText('已确认')).toBeTruthy();
    });
    expect(queryByText('执行中')).toBeNull();
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['write-intents'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['timeline', 'today'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['agenda', 'today'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['daily-artifact', 'me'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['today-dynamic-view', 'mobile.today'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['dashboard'] });

    unmount();
    qc.clear();
  });
});
