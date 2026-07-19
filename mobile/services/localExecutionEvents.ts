import {
  commitLocalHealthMutation,
  type LocalHealthMutation,
} from '../modules/local-health-kernel';

type LocalExecutionEventDependencies = {
  commit: (mutation: LocalHealthMutation) => Promise<void>;
  nextEventId: () => string;
  now: () => Date;
};

const defaultDependencies: LocalExecutionEventDependencies = {
  commit: commitLocalHealthMutation,
  nextEventId: () => `event-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`,
  now: () => new Date(),
};

export async function appendLocalExecutionEvent(
  ownerScope: string,
  kind: string,
  dependencies: Partial<LocalExecutionEventDependencies> = {},
): Promise<void> {
  if (!ownerScope.trim() || !/^[a-z][a-z0-9_]{2,63}$/.test(kind)) {
    throw new Error('invalid_local_execution_event');
  }
  const port = { ...defaultDependencies, ...dependencies };
  const eventId = port.nextEventId();
  const payload = JSON.stringify({
    schema_version: 1,
    owner_scope: ownerScope,
    event_id: eventId,
    kind,
    occurred_at: port.now().toISOString(),
  });
  await port.commit({
    writes: [{
      collection: 'execution_events',
      id: eventId,
      version: 1,
      equalityIndexes: { kind },
      payload,
    }],
    deletes: [],
  });
}
