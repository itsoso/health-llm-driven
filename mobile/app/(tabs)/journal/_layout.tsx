/**
 * Journal tab — 内嵌 Stack, 让 index 和 [id] 在同一个 tab 里前后导航,
 * 而不是被外层 Tabs._layout 当成两个独立 tab 暴露 (那样底部会出现
 * "journal/index" / "journal/[id]" 这种原始路由名).
 */
import React from 'react';
import { Stack } from 'expo-router';

export default function JournalStackLayout() {
  return <Stack screenOptions={{ headerShown: false }} />;
}
