import { formatLocalDate, todayStr } from '../utils/dietDate';
import { emitClientEvent } from './clientEvents';
import { supplementApi } from './records';

// 推送 data 里的 supplement_id 可能是整数或数字字符串;后端只收 JSON 整数(布尔/名称一律不认)。
function normalizeSupplementId(raw: unknown): number | null {
  if (typeof raw === 'number' && Number.isInteger(raw)) return raw;
  if (typeof raw === 'string' && /^\d+$/.test(raw.trim())) return Number(raw);
  return null;
}

// iOS 的 notification.date 是秒(timeIntervalSince1970),本仓库自造的 response 用毫秒。
function deliveredLocalDay(deliveredAt: unknown): string | null {
  if (typeof deliveredAt !== 'number' || !Number.isFinite(deliveredAt) || deliveredAt <= 0) return null;
  return formatLocalDate(new Date(deliveredAt < 1e12 ? deliveredAt * 1000 : deliveredAt));
}

/**
 * SUPPLEMENT_REMINDER 通知的「已服用 / 跳过」后台动作(data.reminder_type === 'supplement')。
 *
 * - 已服用 → POST /supplements/records/batch,与 App 内补剂打卡同一写路径:
 *   用户本地日 + 显式布尔 taken:true。
 *   点按可能被延后处理(冷启动 / 回前台 / 联网后重放 last response),所以只在
 *   「通知送达的本地日 == 今天」时写;跨日或送达时间未知 → 不写、上报 stale_response,
 *   绝不把前一天的服用记到今天。
 * - 跳过 → 不写库:supplement_records 每补剂每天一行、只有 taken 布尔,没有「已跳过」态;
 *   taken:false 即「取消打卡」,会把当天已记的已服清掉。
 * - 失败在 listener 边界记录(console.warn + watch_action_failed),不抛;
 *   日志与遥测不回显通知原值(可能是补剂名)。
 *
 * 返回是否写入了服用记录(调用方据此刷新缓存)。
 */
export async function recordSupplementReminderAction(
  action: 'TAKEN' | 'SKIP',
  data: Record<string, any> | undefined,
  deliveredAt: unknown,
): Promise<boolean> {
  if (data?.reminder_type !== 'supplement' || action === 'SKIP') return false;
  const supplementId = normalizeSupplementId(data.supplement_id);
  if (supplementId == null) {
    console.warn('[supplementReminderActions] invalid supplement_id in reminder payload');
    await emitClientEvent('watch_action_failed', {
      reason: 'invalid_supplement_id',
      kind: 'supplement',
      action,
    });
    return false;
  }
  const recordDate = todayStr();
  if (deliveredLocalDay(deliveredAt) !== recordDate) {
    console.warn('[supplementReminderActions] reminder action not processed on its delivery day');
    await emitClientEvent('watch_action_failed', {
      reason: 'stale_response',
      kind: 'supplement',
      action,
      supplement_id: supplementId,
    });
    return false;
  }
  try {
    await supplementApi.batchCheckin(recordDate, supplementId, true);
    return true;
  } catch (error) {
    console.warn('[supplementReminderActions] supplement reminder action failed', error);
    await emitClientEvent('watch_action_failed', {
      reason: 'request_failed',
      kind: 'supplement',
      action,
      supplement_id: supplementId,
      error: error instanceof Error ? error.message : String(error),
    });
    return false;
  }
}
