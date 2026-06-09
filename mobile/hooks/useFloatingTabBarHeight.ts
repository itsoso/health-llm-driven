import { useSafeAreaInsets } from 'react-native-safe-area-context';

/**
 * 悬浮胶囊 Tab Bar 的几何尺寸 —— 单一真源。
 *
 * RevaTabBar (app/(tabs)/_layout.tsx) 是 position:absolute 的浮动胶囊,
 * 不占布局流。@react-navigation 的 useBottomTabBarHeight() 对这种自定义
 * absolute tab bar 测不准(真机常返回 0),会让页面底部内容/输入框被
 * 悬浮 bar 盖住。任何需要"给 tab bar 留底部空间"的屏都用本 hook,
 * 别再用 useBottomTabBarHeight()。
 *
 * 这三个常量必须与 _layout.tsx 的 capsule 样式保持一致(同源 import)。
 */
export const FLOATING_TAB_BAR_BAR_HEIGHT = 56; // capsule.bar.height
export const FLOATING_TAB_BAR_PADDING_TOP = 8; // capsule.wrap.paddingTop
export const FLOATING_TAB_BAR_MIN_BOTTOM = 10; // capsule.wrap.paddingBottom 下限

/** 悬浮 tab bar 实际占据的总高度(随安全区底部内边距自适应)。 */
export function useFloatingTabBarHeight(): number {
  const insets = useSafeAreaInsets();
  return (
    FLOATING_TAB_BAR_PADDING_TOP +
    FLOATING_TAB_BAR_BAR_HEIGHT +
    Math.max(insets.bottom, FLOATING_TAB_BAR_MIN_BOTTOM)
  );
}
