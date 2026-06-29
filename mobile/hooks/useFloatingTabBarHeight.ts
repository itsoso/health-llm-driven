/**
 * 主 Tab Bar 的几何尺寸 —— 单一真源。
 *
 * 早期 RevaTabBar 是 position:absolute 的浮动胶囊,本 hook 返回完整几何高度。
 * 现在 Tab Bar 已改为布局流内 docked bar,页面内容不需要再手动让出整块高度。
 * 为兼容已有调用方,保留 hook 名称,但只返回页面底部的轻量呼吸空间。
 *
 * 这三个常量必须与 _layout.tsx 的 capsule 样式保持一致(同源 import)。
 */
export const FLOATING_TAB_BAR_BAR_HEIGHT = 56; // capsule.bar.height
export const FLOATING_TAB_BAR_PADDING_TOP = 8; // capsule.wrap.paddingTop
export const FLOATING_TAB_BAR_MIN_BOTTOM = 10; // capsule.wrap.paddingBottom 下限
export const DOCKED_TAB_BAR_CONTENT_GAP = 12;

/** docked tab bar 已占布局流;调用方只需要一点底部留白。 */
export function useFloatingTabBarHeight(): number {
  return DOCKED_TAB_BAR_CONTENT_GAP;
}
