/**
 * Agent-native shell 的底部呼吸空间 —— 单一真源。
 *
 * 早期 RevaTabBar 是 position:absolute 的浮动胶囊,后来短暂改为 docked bar。
 * 现在底部 Tab Bar 已移除,小巴(chat) 是唯一主入口。
 * 为兼容已有调用方,保留 hook 名称,但只返回页面底部的轻量呼吸空间。
 */
export const FLOATING_TAB_BAR_BAR_HEIGHT = 56; // capsule.bar.height
export const FLOATING_TAB_BAR_PADDING_TOP = 8; // capsule.wrap.paddingTop
export const FLOATING_TAB_BAR_MIN_BOTTOM = 10; // capsule.wrap.paddingBottom 下限
export const DOCKED_TAB_BAR_CONTENT_GAP = 12;

/** 无底部 Tab Bar;调用方只需要一点底部留白。 */
export function useFloatingTabBarHeight(): number {
  return DOCKED_TAB_BAR_CONTENT_GAP;
}
