import { useQuery } from '@tanstack/react-query';
import { fetchDashboardData, type DashboardData } from '@/services/dashboard';

export function useDashboardData() {
  return useQuery<DashboardData>({
    queryKey: ['dashboard'],
    queryFn: fetchDashboardData,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
  });
}

// Helper to safely extract nested Garmin data (latest day)
export function useLatestGarmin(data: DashboardData | undefined) {
  if (!data?.garminDaily) return null;
  const days = Array.isArray(data.garminDaily)
    ? data.garminDaily
    : [data.garminDaily];
  return days.length > 0 ? days[days.length - 1] : null;
}
