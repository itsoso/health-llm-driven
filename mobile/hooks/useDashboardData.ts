import { useQuery } from '@tanstack/react-query';
import { fetchDashboardData, type DashboardData } from '../services/dashboard';

export function useDashboardData() {
  return useQuery<DashboardData>({
    queryKey: ['dashboard'],
    queryFn: fetchDashboardData,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
  });
}

// Helper to safely extract the most recent Garmin data
export function useLatestGarmin(data: DashboardData | undefined) {
  if (!data?.garminDaily) return null;
  const days = Array.isArray(data.garminDaily)
    ? data.garminDaily
    : [data.garminDaily];
  // API returns newest first, so take the first element
  return days.length > 0 ? days[0] : null;
}
