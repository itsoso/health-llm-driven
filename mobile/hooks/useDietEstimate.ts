import { useCallback, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  estimateNutrition,
  recognizeFood,
  parseVoiceFood,
  updateDietRecord,
  type DietRecord,
  type DietRecordCreate,
} from '../services/diet';

/** 后台估算的营养补丁; 营养全 undefined 表示估算未得到任何数值 (视为失败). */
export interface NutritionPatch {
  calories?: number;
  protein?: number;
  carbs?: number;
  fat?: number;
  /** 照片/语音识别可顺带修正食物描述 (文字流不改, 用户已自己输入). */
  food_items?: string;
}

/** 一条待估算任务: 记录已入库 (有 id), 用 source 决定走哪条 LLM 估算. */
export type EstimateSource =
  | { kind: 'text'; description: string }
  | { kind: 'photo'; imageBase64?: string; imageUri?: string }
  | { kind: 'voice'; rawText: string };

export interface EstimateSourceCache {
  source: EstimateSource;
  foodItems: string;
}

/** A capture source is only valid for the exact food description it produced. */
export function estimateSourceForRecord(foodItems: string, cached?: EstimateSourceCache): EstimateSource {
  const normalize = (value: string) => value.trim().replace(/\s+/g, ' ');
  if (cached && cached.source.kind !== 'text' && normalize(cached.foodItems) === normalize(foodItems)) {
    return cached.source;
  }
  return { kind: 'text', description: foodItems };
}

function hasValue(p: NutritionPatch): boolean {
  return [p.calories, p.protein, p.carbs, p.fat].some(v => typeof v === 'number' && Number.isFinite(v));
}

async function runEstimate(source: EstimateSource): Promise<NutritionPatch> {
  if (source.kind === 'photo') {
    if (!source.imageBase64) return {};
    const r = await recognizeFood(source.imageBase64);
    const desc = r.meal_description || (r.foods ?? []).map(f => f.name).filter(Boolean).join('、');
    return {
      calories: r.total_calories ?? undefined,
      protein: r.total_protein ?? undefined,
      carbs: r.total_carbs ?? undefined,
      fat: r.total_fat ?? undefined,
      food_items: desc || undefined,
    };
  }
  if (source.kind === 'voice') {
    const draft = await parseVoiceFood(source.rawText);
    const sum = (key: 'calories' | 'protein' | 'carbs' | 'fat') => {
      const vals = (draft.foods ?? [])
        .map(f => f[key])
        .filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
      return vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) * 10) / 10 : undefined;
    };
    return { calories: sum('calories'), protein: sum('protein'), carbs: sum('carbs'), fat: sum('fat') };
  }
  const est = await estimateNutrition(source.description);
  if (!est.success) return {};
  return {
    calories: est.total_calories ?? undefined,
    protein: est.total_protein ?? undefined,
    carbs: est.total_carbs ?? undefined,
    fat: est.total_fat ?? undefined,
  };
}

/**
 * 异步营养估算: 记录已入库 (nutrition null), 这里在后台跑 LLM 估算并回填.
 * 不阻塞 UI; 失败让调用方感知 (failedIds), 不静默把 0 当成功.
 */
export function useDietEstimate() {
  const qc = useQueryClient();
  const generationRef = useRef<Map<number, number>>(new Map());
  const inFlightWriteRef = useRef<Map<number, Promise<DietRecord>>>(new Map());
  const [pendingIds, setPendingIds] = useState<Set<number>>(new Set());
  const [failedIds, setFailedIds] = useState<Set<number>>(new Set());

  const mutate = useCallback((set: React.Dispatch<React.SetStateAction<Set<number>>>, id: number, present: boolean) => {
    set(prev => {
      const next = new Set(prev);
      if (present) next.add(id); else next.delete(id);
      return next;
    });
  }, []);

  const estimate = useCallback(async (recordId: number, source: EstimateSource) => {
    const generation = (generationRef.current.get(recordId) ?? 0) + 1;
    generationRef.current.set(recordId, generation);
    const isCurrent = () => generationRef.current.get(recordId) === generation;
    mutate(setPendingIds, recordId, true);
    mutate(setFailedIds, recordId, false);
    let write: Promise<DietRecord> | undefined;
    try {
      const patch = await runEstimate(source);
      if (!isCurrent()) return;
      if (!hasValue(patch)) throw new Error('estimate returned no nutrition');
      const update: Partial<DietRecordCreate> = {
        calories: patch.calories,
        protein: patch.protein,
        carbs: patch.carbs,
        fat: patch.fat,
      };
      if (patch.food_items) update.food_items = patch.food_items;
      write = updateDietRecord(recordId, update);
      inFlightWriteRef.current.set(recordId, write);
      await write;
      qc.invalidateQueries({ queryKey: ['diet'] });
    } catch {
      if (isCurrent()) mutate(setFailedIds, recordId, true);
    } finally {
      if (write && inFlightWriteRef.current.get(recordId) === write) {
        inFlightWriteRef.current.delete(recordId);
      }
      if (isCurrent()) mutate(setPendingIds, recordId, false);
    }
  }, [mutate, qc]);

  const cancelEstimate = useCallback((recordId: number) => {
    generationRef.current.set(recordId, (generationRef.current.get(recordId) ?? 0) + 1);
    mutate(setPendingIds, recordId, false);
    mutate(setFailedIds, recordId, false);
    // A request already on the wire cannot be canceled locally. Join it before
    // issuing a corrected write so its returned revision can guard the CAS.
    return inFlightWriteRef.current.get(recordId)?.catch(() => null)
      ?? Promise.resolve(null);
  }, [mutate]);

  return { estimate, cancelEstimate, pendingIds, failedIds };
}
