/**
 * 今日二级屏 —— 深链/通知落地的整屏路由 (2026-07-06 内容抽入 TodayContent).
 *
 * 主体全部在 components/home/TodayContent.tsx (与 /today-sheet 半屏 sheet 复用同一份卡片组装)。
 * 本文件只保留深链契约:通知/Siri fallback 若落到 /(tabs)/today, 仍渲染完整今日 (mode="screen",
 * 顶部有「返回小巴」)。聊天上滑出的半屏入口走根 Stack 的 /today-sheet (mode="sheet")。
 */

import React from 'react';
import TodayContent from '../../components/home/TodayContent';

export default function TodayScreen() {
  return <TodayContent mode="screen" />;
}
