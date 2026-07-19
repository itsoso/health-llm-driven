import { appendLocalExecutionEvent } from '../localExecutionEvents';

describe('appendLocalExecutionEvent', () => {
  it('stores only owner scope, event kind, time and random event id', async () => {
    const commit = jest.fn().mockResolvedValue(undefined);
    await appendLocalExecutionEvent('local-owner', 'privacy_egress_blocked', {
      commit,
      nextEventId: () => 'event-fixed',
      now: () => new Date('2026-07-19T12:00:00.000Z'),
    });

    expect(commit).toHaveBeenCalledWith({
      writes: [expect.objectContaining({
        collection: 'execution_events',
        id: 'event-fixed',
        equalityIndexes: { kind: 'privacy_egress_blocked' },
        payload: JSON.stringify({
          schema_version: 1,
          owner_scope: 'local-owner',
          event_id: 'event-fixed',
          kind: 'privacy_egress_blocked',
          occurred_at: '2026-07-19T12:00:00.000Z',
        }),
      })],
      deletes: [],
    });
  });
});
