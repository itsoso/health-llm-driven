/**
 * notificationRoutes — 把通知 payload 的 deep_link 归一成可 router.push 的 expo-router 路径.
 *
 * 两端共用 (hooks/useNotifications.ts 的 tap 路由 + app/notification-history.tsx 的历史行点击),
 * 保证「活推送点击」与「历史 feed 点击」落同一目的地.
 *
 * 支持两种 deep_link 形态:
 *   1) 纯 expo-router 路径: `/calendar`, `/(tabs)/alerts`, `/voice-chat?intent=briefing` → 原样返回.
 *   2) custom scheme URL: `health://card/{id}` / `mobile://...` / `life.executor.health://...`
 *      → 剥掉 scheme + host 后转成 `/<rest>`. (router.push 直接吃 scheme URL 不可靠.)
 *
 * 另外把 legacy `data.screen` 枚举 + 个别 path-segment 形态 (`/workout-detail/{id}`,
 * 该动态路由在 mobile/app 下不存在, 真实路由是 query 形态 `/workout-detail?id={id}`) 归一掉,
 * 避免后端发出的链接落到不存在的路由.
 *
 * 永不抛: 无法解析时返回 null, 由调用方决定 (tap → 回首页 fallback; 历史行 → 不可点).
 */

const APP_SCHEMES = ['health', 'mobile', 'life.executor.health'];

/** 把 custom-scheme URL 归一成 router 路径, 非 scheme URL 原样返回. */
function stripScheme(raw: string): string {
  const trimmed = raw.trim();
  // 命中 `<scheme>://<rest>` → `/<rest>` (host 段也并进 path, expo-router 用文件路由没有 host 概念).
  const m = trimmed.match(/^([a-zA-Z][a-zA-Z0-9.+-]*):\/\/(.*)$/);
  if (!m) return trimmed;
  const scheme = m[1].toLowerCase();
  const rest = m[2];
  if (!APP_SCHEMES.includes(scheme)) return trimmed; // 非本 app scheme, 不动 (http(s) 等)
  const path = rest.startsWith('/') ? rest : `/${rest}`;
  return path;
}

/**
 * 把后端可能发的 path-segment 形态归一成真实存在的 mobile 路由.
 * 目前只有 workout-detail: 路由是 query 形态, 后端若发 `/workout-detail/{id}` 要转成 `?id={id}`.
 */
function normalizeKnownAliases(path: string): string {
  const wd = path.match(/^\/workout-detail\/(\d+)\/?$/);
  if (wd) return `/workout-detail?id=${wd[1]}`;
  return path;
}

/** legacy data.screen 枚举 → 路径 (与旧 switch 对齐). */
const SCREEN_ROUTES: Record<string, string> = {
  alerts: '/(tabs)/alerts',
  record: '/(tabs)/record',
  chat: '/(tabs)/chat',
  diet: '/diet',
  sleep: '/sleep',
  home: '/(tabs)',
};

/**
 * 从通知 data 解析出一个可 push 的 router 路径; 解析不出返回 null.
 * 优先级: data.deep_link / data.deeplink (归一) > data.screen 枚举.
 * 'home' 仅作为活推送 tap 的兜底语义 — 历史行不应为「回首页」造一个目的地, 所以 home 返回 null.
 */
export function resolveNotificationRoute(
  data: Record<string, any> | null | undefined,
): string | null {
  if (!data) return null;

  const explicit = (data.deep_link ?? data.deeplink) as unknown;
  if (typeof explicit === 'string' && explicit.trim()) {
    return normalizeKnownAliases(stripScheme(explicit));
  }

  const screen = data.screen as string | undefined;
  if (screen && screen in SCREEN_ROUTES) {
    // home 不算「目的地」(历史行无意义), 返回 null; 活推送 tap 自己有回首页 fallback.
    if (screen === 'home') return null;
    return SCREEN_ROUTES[screen];
  }

  return null;
}
