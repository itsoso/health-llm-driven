import React from 'react';
import { renderHook, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useCompleteAgendaItem } from '../useAgenda';
import { completeAgendaItem } from '../../services/agenda';

jest.mock('../../services/agenda', () => ({
  __esModule: true,
  completeAgendaItem: jest.fn().mockResolvedValue({ wrote: true }),
}));

const mockCompleteAgendaItem = completeAgendaItem as jest.Mock;

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false, gcTime: 0 },
    },
  });
  const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return { wrapper, invalidateSpy };
}

describe('useCompleteAgendaItem management contract', () => {
  beforeEach(() => jest.clearAllMocks());

  it('passes skip status and reason to the verified agenda write', async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useCompleteAgendaItem(), { wrapper });

    result.current.mutate({
      source: { object_type: 'health_protocol', object_id: 42 },
      status: 'skipped',
      skipReason: 'too_tired',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockCompleteAgendaItem).toHaveBeenCalledWith(
      { object_type: 'health_protocol', object_id: 42 },
      'protocol',
      undefined,
      { status: 'skipped', skipReason: 'too_tired' },
    );
  });

  it('refreshes agenda, timeline and chat projections after a verified write', async () => {
    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useCompleteAgendaItem(), { wrapper });

    result.current.mutate({ source: { object_type: 'health_protocol', object_id: 7 } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['agenda'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['timeline', 'today'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['daily-artifact'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['today-dynamic-view'] });
  });

  it('does not refresh projections when the write fails', async () => {
    mockCompleteAgendaItem.mockRejectedValueOnce(new Error('network down'));
    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useCompleteAgendaItem(), { wrapper });

    result.current.mutate({ source: { object_type: 'health_protocol', object_id: 7 } });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
