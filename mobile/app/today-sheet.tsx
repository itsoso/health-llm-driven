/**
 * 今日半屏 sheet —— 从聊天上滑出的 iOS 原生 formSheet (2026-07-06 刀④).
 *
 * agent-native shell 下, 聊天(chat) 是主屏。「今日简报条」不再整屏导航离开对话,
 * 而是把今日以半高原生 sheet 盖在聊天上:半高瞥待办/时间线, 下滑关闭回到对话。
 *
 * 半高 + 拖拽下滑关 + 抓手全部由根 Stack 的 presentation:'formSheet' + sheetAllowedDetents
 * 原生提供 (见 app/_layout.tsx 的 <Stack.Screen name="today-sheet">), 本文件零手搓动画。
 * 内容与 /(tabs)/today 整屏路由复用同一 TodayContent (mode="sheet": 不渲染「返回小巴」,
 * 靠抓手 + 下滑关)。
 */

import React from 'react';
import TodayContent from '../components/home/TodayContent';

export default function TodaySheet() {
  return <TodayContent mode="sheet" />;
}
