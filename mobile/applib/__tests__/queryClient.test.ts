/**
 * lib/queryClient smoke tests.
 *
 * Goal: catch regressions where the persist configuration silently stops
 * working (stale queries cached forever, errors cached, wrong buster).
 */

// AsyncStorage has no in-Node runtime; use the official jest mock shipped
// with the package.
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

import { queryClient, retireLegacyQueryCache } from '../queryClient';
import { QueryClient, QueryObserver } from '@tanstack/react-query';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { setRuntimeAuthToken } from '../../services/api';

describe('lib/queryClient', () => {
  afterEach(() => { queryClient.clear(); });
  it('constructs a QueryClient with 24h gcTime and retry/staleTime defaults', () => {
    expect(queryClient).toBeInstanceOf(QueryClient);
    const defaults = queryClient.getDefaultOptions();
    expect(defaults.queries?.retry).toBe(2);
    expect(defaults.queries?.staleTime).toBe(60_000);
    expect(defaults.queries?.gcTime).toBe(24 * 60 * 60 * 1000);
  });

  it('retires only the legacy health cache without reading or rewriting records', async () => {
    jest.clearAllMocks();
    await retireLegacyQueryCache();
    expect(AsyncStorage.removeItem).toHaveBeenCalledWith('HEALTHPILOT_RQ_CACHE_V1');
    expect(AsyncStorage.getItem).not.toHaveBeenCalled();
    expect(AsyncStorage.setItem).not.toHaveBeenCalled();
    expect(AsyncStorage.clear).not.toHaveBeenCalled();
  });

  it.each(['switch', 'logout-and-return'])('clears cached data and mounted observer state: %s', change => {
    setRuntimeAuthToken('synthetic-a');
    queryClient.setQueryData(['diet', 'today'], { owner: 'synthetic-a' });
    const observer = new QueryObserver(queryClient, { queryKey: ['diet', 'today'], enabled: false });
    const stop = observer.subscribe(() => undefined);
    expect(observer.getCurrentResult().data).toEqual({ owner: 'synthetic-a' });
    if (change === 'switch') setRuntimeAuthToken('synthetic-b');
    else { setRuntimeAuthToken(null); setRuntimeAuthToken('synthetic-a'); }
    expect(queryClient.getQueryData(['diet', 'today'])).toBeUndefined();
    expect(observer.getCurrentResult().data).toBeUndefined();
    stop();
    observer.destroy();
    observer.getCurrentQuery().destroy();
  });

  it('does not seed the new account cache from a cancelled old query', async () => {
    setRuntimeAuthToken('synthetic-a');
    let finish!: (data: unknown) => void;
    const pending = queryClient.fetchQuery({ queryKey: ['diet', 'today'],
      queryFn: () => new Promise(resolve => { finish = resolve; }) });
    const rejected = expect(pending).rejects.toBeDefined();
    setRuntimeAuthToken('synthetic-b');
    finish({ owner: 'synthetic-a' });
    await rejected;
    expect(queryClient.getQueryData(['diet', 'today'])).toBeUndefined();
  });

  it('reports a failed legacy cleanup without hydrating old records', async () => {
    (AsyncStorage.removeItem as jest.Mock).mockRejectedValueOnce(new Error('synthetic-storage-error'));
    await expect(retireLegacyQueryCache()).rejects.toThrow('synthetic-storage-error');
    expect(AsyncStorage.getItem).not.toHaveBeenCalled();
  });

  it('does not retain a day-long GC timer when an old fetch settles after session removal', async () => {
    jest.useFakeTimers();
    try {
      setRuntimeAuthToken('synthetic-a');
      let finish!: (data: unknown) => void;
      const pending = queryClient.fetchQuery({ queryKey: ['retired-fetch'],
        queryFn: () => new Promise(resolve => { finish = resolve; }) });
      const rejected = expect(pending).rejects.toBeDefined();
      setRuntimeAuthToken('synthetic-b');
      finish({ owner: 'synthetic-a' });
      await rejected;
      await Promise.resolve();
      jest.advanceTimersByTime(0);
      expect(jest.getTimerCount()).toBe(0);
    } finally {
      jest.useRealTimers();
    }
  });
});
