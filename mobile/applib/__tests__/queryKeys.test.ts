import { healthSnapshotQueryKeys, queryKeys, recordMutationQueryKeys } from '../queryKeys';

describe('queryKeys', () => {
  it('keeps health snapshot invalidation keys in one place', () => {
    expect(healthSnapshotQueryKeys).toEqual([
      queryKeys.dashboard,
      queryKeys.healthScore,
      queryKeys.garminToday,
      queryKeys.safety,
      queryKeys.dataHealth,
      queryKeys.todayCoachRoot,
      queryKeys.agentAgendaRoot,
    ]);
  });

  it('invalidates coach and data health after user record mutations', () => {
    expect(recordMutationQueryKeys).toEqual([
      queryKeys.dashboard,
      queryKeys.dataHealth,
      queryKeys.todayCoachRoot,
      queryKeys.agentAgendaRoot,
    ]);
  });
});
