/**
 * 旧单源「连接日历」入口 —— 已被 Calendar v2 多源流程取代。
 * 保留路由以兼容旧深链/入口,进入即重定向到 /calendar(日历视图,内含「管理源」)。
 * 新增/管理源:/calendar-sources。
 */
import { Redirect } from 'expo-router';

export default function CalendarConnectRedirect() {
  return <Redirect href={'/calendar' as any} />;
}
