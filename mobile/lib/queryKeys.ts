import type { QueryClient } from '@tanstack/react-query';

export const queryKeys = {
  dashboard: ['dashboard'] as const,
  healthScore: ['healthScore'] as const,
  garminToday: ['garminToday'] as const,
  safety: ['safety'] as const,
  weather: ['weather'] as const,
  aqi: ['aqi'] as const,
  forecast: ['forecast'] as const,
  dataHealth: ['dataHealth'] as const,
  todayCoachRoot: ['todayCoach'] as const,
  agentAgendaRoot: ['agentAgenda'] as const,
  actionCards: ['actionCards'] as const,
  profile: ['profile'] as const,
} as const;

export const healthSnapshotQueryKeys = [
  queryKeys.dashboard,
  queryKeys.healthScore,
  queryKeys.garminToday,
  queryKeys.safety,
  queryKeys.dataHealth,
  queryKeys.todayCoachRoot,
  queryKeys.agentAgendaRoot,
] as const;

export const recordMutationQueryKeys = [
  queryKeys.dashboard,
  queryKeys.dataHealth,
  queryKeys.todayCoachRoot,
  queryKeys.agentAgendaRoot,
] as const;

export async function invalidateQueryKeys(
  queryClient: QueryClient,
  keys: readonly (readonly unknown[])[],
): Promise<void> {
  await Promise.all(keys.map(queryKey => queryClient.invalidateQueries({ queryKey })));
}

export function invalidateHealthSnapshot(queryClient: QueryClient): Promise<void> {
  return invalidateQueryKeys(queryClient, healthSnapshotQueryKeys);
}

export function invalidateRecordMutation(queryClient: QueryClient): Promise<void> {
  return invalidateQueryKeys(queryClient, recordMutationQueryKeys);
}
