/**
 * 补剂库存 React Query hooks —— 读库存 + 补货 + 校正剩余。
 * 写操作成功后统一 invalidate ['supplement-inventory'] 触发列表刷新。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  getInventory,
  restockSupplement,
  setUnitsRemaining,
  type InventoryItem,
  type RestockPayload,
  type SetRemainingPayload,
} from '../services/supplementInventory';

const KEY = ['supplement-inventory'] as const;

export function useSupplementInventory() {
  return useQuery<InventoryItem[]>({
    queryKey: KEY,
    queryFn: getInventory,
    staleTime: 60 * 1000,
  });
}

export function useRestockSupplement() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ supplementId, payload }: { supplementId: number; payload: RestockPayload }) =>
      restockSupplement(supplementId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
    },
  });
}

export function useSetUnitsRemaining() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ supplementId, payload }: { supplementId: number; payload: SetRemainingPayload }) =>
      setUnitsRemaining(supplementId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY });
    },
  });
}
