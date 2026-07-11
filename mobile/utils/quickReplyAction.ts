/**
 * quickReplyAction — 冷启动 quick reply 的本地导航映射 (P0-3)。
 *
 * 契约枚举 photo_meal | record_weight | connect_device 是唯一真源:
 * chat.tsx 的开场气泡 quick reply 与 EmptyStateHome 的 Quick Start 卡共用此表,
 * 避免两处路由漂移。所有目标都是 grep 核实过的既有路由:
 * - photo_meal      → /diet?capture=photo&return_to=chat (既有拍照记饮食路由,确认后回小巴)
 * - record_weight   → /body-measurements  (体重腰围录入屏; today.tsx/record.tsx 已用)
 * - connect_device  → /settings           (数据连接 hub: Garmin 绑定 + Apple Health + 连接授权)
 */
import { router } from 'expo-router';
import type { QuickReplyAction } from '../services/conversationOpener';

/** 每个 action 的展示文案 (Quick Start 卡 + 无障碍标签)。 */
export const QUICK_ACTION_LABEL: Record<QuickReplyAction, string> = {
  photo_meal: '拍照记一餐',
  record_weight: '记录体重',
  connect_device: '连接设备',
};

const QUICK_ACTION_ROUTE: Record<QuickReplyAction, string> = {
  photo_meal: '/diet?capture=photo&return_to=chat',
  record_weight: '/body-measurements',
  connect_device: '/settings',
};

/** 带 action 的 quick reply 点击 → 本地导航 (不发文本)。 */
export function navigateForQuickReplyAction(action: QuickReplyAction): void {
  router.push(QUICK_ACTION_ROUTE[action] as never);
}
