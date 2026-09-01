/**
 * Chinese (zh-CN) string catalogue — seeded with a minimal set of high-frequency
 * user-facing strings. Add new keys as you touch files; do NOT bulk-extract
 * existing code yet.
 *
 * Key convention: `<feature>.<element>` lowercase dot-separated.
 */
const zh: Record<string, string> = {
  // Generic
  'common.ok': '确定',
  'common.cancel': '取消',
  'common.retry': '重试',
  'common.loading': '加载中...',
  'common.delete': '删除',

  // Tabs
  'tab.home': '首页',
  'tab.actions': '行动',
  'tab.record': '记录',

  // Lock / auth
  'lock.title': '小巴健康',
  'lock.unlock': '解锁',

  // Error fallback
  'error.title': '加载失败',
  'error.offlineTitle': '无法连接网络',
  'error.offlineMessage': '请检查网络连接后重试',
  'error.unknownMessage': '发生了未知错误',

  // A11y
  'a11y.tab.home': '首页，查看健康概览',
  'a11y.tab.actions': '行动，查看安全告警与今日建议',
  'a11y.tab.record': '记录，快速打卡健康数据',
};

export default zh;
