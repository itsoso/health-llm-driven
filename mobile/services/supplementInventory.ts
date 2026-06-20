/**
 * 补剂库存管理 —— P3 复购检测客户端 service。
 *
 * 后端在 §3.D (D1) 检测「快用完」并通过 write_intent (kind=reorder_nudge) 提醒。
 * 本 service 只做：读库存 / 补货登记 / 校正剩余。**不含下单 / 购买 / 支付**(那是 D2/P5)。
 *
 * ⚠️ 后端 OpenAPI 尚未生成 → 下列接口按 PRD pin 的契约手写,字段名 + 类型逐字对齐。
 * TODO(P3): reconcile with generated types post-merge —— 合并后跑 `npm run generate-types`
 * 用 components['schemas'][...] 替换手写 interface,防 float/int + 改名静默漂移。
 */
import api from './api';

/** 单条补剂库存。后端 GET /supplements/inventory 的 items[] 元素,与 restock/PUT 返回同形。 */
export interface InventoryItem {
  supplement_id: number;
  name: string;
  brand: string; // "" if unset
  spec: string; // "" if unset
  units_remaining: number | null;
  daily_consumption: number | null;
  days_remaining: number | null; // may be fractional
  status: 'ok' | 'low' | 'unknown';
}

export interface InventoryResponse {
  items: InventoryItem[];
}

/** 补货登记 body。units_added 必填;其余可选(首次记录品牌/规格/每包数量)。 */
export interface RestockPayload {
  units_added: number;
  brand?: string | null;
  spec?: string | null;
  package_units?: number | null;
}

/** 校正剩余 body —— 手动直接设定剩余单位数(纠错用)。 */
export interface SetRemainingPayload {
  units_remaining: number;
}

export async function getInventory(): Promise<InventoryItem[]> {
  const { data } = await api.get<InventoryResponse>('/supplements/inventory');
  return data?.items ?? [];
}

export async function restockSupplement(
  supplementId: number,
  payload: RestockPayload,
): Promise<InventoryItem> {
  const { data } = await api.post<InventoryItem>(
    `/supplements/inventory/${supplementId}/restock`,
    payload,
  );
  return data;
}

export async function setUnitsRemaining(
  supplementId: number,
  payload: SetRemainingPayload,
): Promise<InventoryItem> {
  const { data } = await api.put<InventoryItem>(
    `/supplements/inventory/${supplementId}`,
    payload,
  );
  return data;
}
