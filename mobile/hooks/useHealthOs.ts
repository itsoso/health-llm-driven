/** Personal Health OS — React Query hooks (代谢画像 / 干预周期). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { emitClientEvent } from '../services/clientEvents';
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
    onSuccess: (cycle: InterventionCycle) => {
      qc.invalidateQueries({ queryKey: ['intervention-cycle', 'active'] });
      qc.invalidateQueries({ queryKey: ['treatment-effect'] }); // 复查后裁决随之刷新
      // N-of-1 北极星埋点:复查产出 ≥1 个非 pending 裁决 = 一条「已验证闭环」。
      // 全 pending(无新数据)不算闭环,不发,保证事件数 == 真实闭环数。
      const verdicts = (cycle?.outcomes ?? []).filter((o) => o.status !== 'pending').length;
      if (verdicts > 0) {
        emitClientEvent('verified_loop', {
          cycle_id: cycle.id,
          verdict_count: verdicts,
          total: cycle.outcomes?.length ?? 0,
        });
      }
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
