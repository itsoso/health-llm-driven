import { beforeEach, expect, it, vi } from 'vitest';
const client = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }));
vi.mock('./client', () => ({ default: client }));
import { familyApi } from './family';
beforeEach(() => vi.clearAllMocks());
it('reads shared records without switching the session and asks not to cache', () => {
  const signal = new AbortController().signal;
  familyApi.getMemberHealth(42, signal);
  expect(client.get).toHaveBeenCalledWith('/family/members/42/health', { signal, headers: { 'Cache-Control': 'no-store' } });
  expect(client.post).not.toHaveBeenCalled();
});
it('uses the actual invitation endpoints and preserves relationship and nickname', () => {
  familyApi.createInvitation();
  familyApi.acceptInvitation({ code: 'ABC123', relationship_type: 'daughter', nickname: '小禾' });
  expect(client.post).toHaveBeenCalledWith('/family/invitation/create');
  expect(client.post).toHaveBeenCalledWith('/family/invitation/accept', { code: 'ABC123', relationship_type: 'daughter', nickname: '小禾' });
});
