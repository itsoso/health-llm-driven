/**
 * (tabs) 根路由 = 纯转发到阿衡 chat。
 *
 * expo-router 规则: 路径 "/" 永远解析到 index 路由, initialRouteName /
 * unstable_settings 都改不了这一点 —— 所以 agent-native「chat 即首页」
 * 必须由 index 显式 Redirect 实现。原「今日」屏整体挪到 ./today.tsx
 * (路由 '/(tabs)/today'), chat 顶部的今日简报条指向它。
 * 通知 fallback 的 home('/(tabs)') 经此转发落 chat, 与 agent-native 语义一致。
 */
import { Redirect } from 'expo-router';

export default function TabsIndexRedirect() {
  return <Redirect href="/(tabs)/chat" />;
}
