/**
 * useSkipAgendaItem 跳过接线单测。
 *
 * 镜像 hooks/__tests__/useTrendData.test.ts 的 renderHook + QueryClientProvider 风格。
 * 验证:选一个原因 → completeAgendaItem(source,'protocol',undefined,{status:'skipped',skipReason})
 * + 成功后 invalidate ['timeline','today'] + ['agenda','today'](首页两个 query 熄灭)。
 *
 * 顺带守门 SKIP_REASONS 常量与后端 8 个枚举值逐字对齐(漂移即学习闭环坏)。
 */
import { renderHook, waitFor } from '@testing-library/react-native';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useSkipAgendaItem } from '../useTodayTimeline';
import { completeAgendaItem } from '../../services/agenda';
import { SKIP_REASONS } from '../../constants/skipReasons';

jest.mock('../../services/agenda', () => ({
  __esModule: true,
  completeAgendaItem: jest.fn().mockResolvedValue({ wrote: true }),
}));

const mockCompleteAgendaItem = completeAgendaItem as jest.Mock;

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false, gcTime: 0 },
    },
  });
  const invalidateSpy = jest.spyOn(qc, 'invalidateQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return { wrapper, invalidateSpy };
}

describe('useSkipAgendaItem', () => {
  beforeEach(() => jest.clearAllMocks());

  it('skips with a reason → completeAgendaItem(skipped, skipReason) for the right source', async () => {
    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useSkipAgendaItem(), { wrapper });

    result.current.mutate({
      source: { object_type: 'health_protocol', object_id: 42 },
      skipReason: 'too_tired',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockCompleteAgendaItem).toHaveBeenCalledTimes(1);
    expect(mockCompleteAgendaItem).toHaveBeenCalledWith(
      { object_type: 'health_protocol', object_id: 42 },
      'protocol',
      undefined,
      { status: 'skipped', skipReason: 'too_tired' },
    );

    // 首页两个 query key 都失效 → 已跳过的项熄灭。
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['timeline', 'today'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['agenda', 'today'] });
  });

  it('skips without a reason → skipReason undefined (service default applies)', async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useSkipAgendaItem(), { wrapper });

    result.current.mutate({
      source: { object_type: 'medication', object_id: 7 },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockCompleteAgendaItem).toHaveBeenCalledWith(
      { object_type: 'medication', object_id: 7 },
      'protocol',
      undefined,
      { status: 'skipped', skipReason: undefined },
    );
  });

  it('surfaces service failure (mutation throws — caller must give feedback)', async () => {
    mockCompleteAgendaItem.mockRejectedValueOnce(new Error('network down'));
    const { wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useSkipAgendaItem(), { wrapper });

    result.current.mutate({
      source: { object_type: 'health_protocol', object_id: 1 },
      skipReason: 'forgot',
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    // 失败时不失效(避免无谓刷新 + 让调用方感知)。
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});

describe('SKIP_REASONS constant', () => {
  it('mirrors the 8 backend skip_reason enum values verbatim', () => {
    expect(SKIP_REASONS.map((r) => r.value)).toEqual([
      'no_time',
      'forgot',
      'no_supply',
      'too_tired',
      'wrong_place',
      'too_hard',
      'unwell',
      'social',
    ]);
    // every option has a Chinese label
    expect(SKIP_REASONS.every((r) => r.label.length > 0)).toBe(true);
  });
});
