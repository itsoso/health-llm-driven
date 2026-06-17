/** Personal Health OS — React Query hooks (代谢画像 / 干预周期). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getActiveCycle,
  getBiomarkers,
  getMetabolicProfile,
  getTreatmentEffect,
  recheckCycle,
  startCycle,
  type InterventionCycle,
  type MetabolicProfile,
  type TreatmentEffectResponse,
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['intervention-cycle', 'active'] });
      qc.invalidateQueries({ queryKey: ['treatment-effect'] }); // 复查后裁决随之刷新
    },
  });
}

// 干预效应裁决。仅在已复查 (latest_snapshot_id != null) 时 enabled,避免对零复查周期空跑。
export function useTreatmentEffect(cycleId: number | undefined, enabled: boolean) {
  return useQuery<TreatmentEffectResponse>({
    queryKey: ['treatment-effect', cycleId],
    queryFn: () => getTreatmentEffect(cycleId as number),
    enabled: enabled && cycleId != null,
  });
}
