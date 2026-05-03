/**
 * actionExecution — ActionCard 一键执行 (Phase 2 of Trust Loop ship).
 *
 * Agent Native: 卡片不只是"建议", 用户能一键让 agent 帮 ta 做下一步.
 *
 * 当前支持 (OTA-safe, 不动 native deps):
 *   - reminder    → 调后端 /notification/reminders 建提醒, APNs 推按时
 *   - navigate    → 跳到对应的录入/详情页 (按 metric_key 路由)
 *
 * 不支持 (留 Phase 2.5, 需要 expo-calendar 即下次 eas build):
 *   - plan        → iOS Calendar event
 *   - guide (无 metric_key) → 暂落到 navigate fallback /(tabs)/record
 */
import type { ActionCard } from './actionCards';
import { createReminder, type Reminder } from './notifications';

export type ExecuteCapability = 'reminder' | 'navigate' | null;

/**
 * 判断卡片是否有可执行的 handler. null = 没有, 不渲染 [执行] 按钮.
 */
export function getExecuteCapability(card: ActionCard): ExecuteCapability {
  // 已完成 / 已归档的卡不该再"执行"
  if (card.status === 'completed' || card.status === 'archived') return null;

  // forecast = 纯预测, 用户什么都不做 — 不渲染 [执行] 按钮
  if (card.card_type === 'forecast') return null;

  if (card.card_type === 'reminder') return 'reminder';

  // recommendation / guide / plan 凡有 metric_key 都可路由到对应录入页
  if (
    (card.card_type === 'recommendation' ||
      card.card_type === 'guide' ||
      card.card_type === 'plan') &&
    card.metric_key
  ) {
    return 'navigate';
  }

  return null;
}

/**
 * 卡片一键执行 button 的中文文案.
 */
export function getExecuteLabel(cap: ExecuteCapability): string {
  switch (cap) {
    case 'reminder':
      return '设置提醒';
    case 'navigate':
      return '现在记录';
    default:
      return '执行';
  }
}

/**
 * metric_key → mobile 路由. 找不到对应路由就回 /(tabs)/record (兜底全局录入页).
 *
 * 路由列表跟 mobile/app/ 下实际存在的页对齐, 不存在的别加 — 跳 404 比跳错更糟.
 *
 * 用 string 而不是 ActionCardMetricKey 的严格 union: 后端加新 metric_key 时
 * 这里能 graceful fallback, 不至于因类型不识别就编不过.
 */
export function getNavigationTarget(card: ActionCard): string {
  const m = (card.metric_key ?? null) as string | null;
  if (!m) return '/(tabs)/record';

  // 体重 / 身体围度: 走 record tab 让用户在身体子卡录入
  if (m === 'weight' || m === 'bmi' || m === 'body_fat') {
    return '/(tabs)/record';
  }

  // 血压: 有专门的页面
  if (m === 'systolic_bp' || m === 'diastolic_bp' || m === 'bp') {
    return '/blood-pressure';
  }

  // 睡眠 / HRV / RHR: 都到 sleep 详情
  if (m === 'sleep_score' || m === 'hrv' || m === 'rhr') {
    return '/sleep';
  }

  // SpO2 / 夜间血氧 — 后端 metric_key 在 spo2_odi 基础上未来可能扩 spo2_avg/min
  if (m.startsWith('spo2')) {
    return '/sleep-spo2-analysis';
  }

  // 化验项 (LDL / HbA1c / ALT 等) → 体检报告/化验录入
  if (
    m === 'ldl' || m === 'hdl' || m === 'tc' || m === 'tg' ||
    m === 'hba1c' || m === 'alt' || m === 'ast'
  ) {
    return '/indicator-history';
  }

  return '/(tabs)/record';
}

/**
 * 直接调后端建一条 custom 提醒. 默认 1 小时后, 用户可在 reminders 页修改.
 *
 * 抛错由调用方处理 (UI 弹 toast).
 */
export async function executeReminderForCard(
  card: ActionCard,
  options?: { time?: string; daysOfWeek?: number[] },
): Promise<Reminder> {
  const time = options?.time ?? defaultReminderTime();
  const message = (card.content || card.title).replace(/[\n\r]+/g, ' ').slice(0, 80);
  return await createReminder({
    reminder_type: 'custom',
    name: card.title,
    reminder_times: [time],
    days_of_week: options?.daysOfWeek ?? [1, 2, 3, 4, 5, 6, 7], // 默认每天
    message,
  });
}

/**
 * 默认提醒时间: 当前 +1 小时, 取整到分钟.
 *
 * 安静时段 23:00-08:00 内的时间一律推到当天/次日 09:00 — 半夜推醒别人不礼貌.
 * (注: 这判断的是 +1h 后落点, 非现在时间. 输入 23:30 → +1h=00:30 仍在安静段 → 09:00)
 */
export function defaultReminderTime(now: Date = new Date()): string {
  const next = new Date(now.getTime() + 60 * 60 * 1000);
  const h = next.getHours();
  const inQuiet = h >= 23 || h < 8;
  if (inQuiet) {
    next.setHours(9, 0, 0, 0);
    // 如果 09:00 还在过去 (now > 09:00), 不可能 — 因为只在 quiet (23 或 <8) 时进这分支,
    // <8 设到当天 09 一定在未来, >=23 是同日设 09:00 在过去, 但提醒按 HH:mm 字符串走,
    // 后端 cron 自然推到下一个 match (即次日 09:00), 所以无需额外 setDate.
  } else {
    next.setSeconds(0);
    next.setMilliseconds(0);
  }
  return `${String(next.getHours()).padStart(2, '0')}:${String(next.getMinutes()).padStart(2, '0')}`;
}
