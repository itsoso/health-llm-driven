/** Personal Health OS — React Query hooks (代谢画像 / 干预周期). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getActiveCycle,
  getBiomarkers,
  getMetabolicProfile,
  recheckCycle,
  startCycle,
  type InterventionCycle,
  type MetabolicProfile,
} from '../services/healthOs';

export function useMetabolicProfile() {
  return useQuery<MetabolicProfile>({ queryKey: ['metabolic-profile'], queryFn: getMetabolicProfile });
}

export function useBiomarkers() {
  return useQuery({ queryKey: ['biomarkers'], queryFn: getBiomarkers });
}

export function useActiveCycle() {
  return useQuery<InterventionCycle | null>({ queryKey: ['intervention-cycle', 'active'], queryFn: getActiveCycle });
}

export function useStartCycle() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (days: number = 90) => startCycle(days),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['intervention-cycle', 'active'] }),
  });
}

export function useRecheckCycle() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cycleId: number) => recheckCycle(cycleId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['intervention-cycle', 'active'] }),
  });
}
