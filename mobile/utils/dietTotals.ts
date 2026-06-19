import type { DietRecord } from '../services/diet';

/**
 * 异步营养估算: 记录先入库 (nutrition 全 null), 后台估算回填 calories 等.
 * 这些纯函数让首页汇总「不假装成功」—— pending 记录不被当 0 计入总量.
 */

/** calories 仍为 null/undefined ⇒ 营养尚未估算 (估算中 或 估算失败). */
export function isPendingNutrition(record: Pick<DietRecord, 'calories'>): boolean {
  return record.calories == null;
}

export interface DietDayTotals {
  calories: number;
  protein: number;
  carbs: number;
  fat: number;
  fiber: number;
  /** 已计入总量的记录数 (calories 非 null). */
  countedMeals: number;
  /** 营养仍在估算中 / 估算失败、未计入总量的记录数. */
  pendingMeals: number;
}

/**
 * 从记录列表算当日总量, **排除** pending (营养 null) 记录, 并报告 pending 数量,
 * 这样头部不会把 null 静默当 0 显示成假精确总量.
 */
export function computeDietTotals(records: readonly DietRecord[]): DietDayTotals {
  const totals: DietDayTotals = {
    calories: 0, protein: 0, carbs: 0, fat: 0, fiber: 0,
    countedMeals: 0, pendingMeals: 0,
  };
  for (const r of records) {
    if (isPendingNutrition(r)) {
      totals.pendingMeals += 1;
      continue;
    }
    totals.calories += r.calories ?? 0;
    totals.protein += r.protein ?? 0;
    totals.carbs += r.carbs ?? 0;
    totals.fat += r.fat ?? 0;
    totals.fiber += r.fiber ?? 0;
    totals.countedMeals += 1;
  }
  return totals;
}
