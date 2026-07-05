import {
  getMainTabAccessibilityLabels,
  getMainTabBarPresentation,
  getMainTabLabels,
  getMainTabRouteNames,
  unstable_settings,
} from '../_layout';

describe('agent-native mobile shell', () => {
  it('uses Xiaoba as the single primary entry instead of private coach wording', () => {
    expect(getMainTabLabels()).toEqual(['今日', '小巴', '记录', '我']);
    expect(getMainTabLabels()).not.toContain('私教');
  });

  it('keeps the assistant tab accessibility label aligned with Xiaoba', () => {
    expect(getMainTabAccessibilityLabels().chat).toBe('小巴，与忠实的健康参谋对话');
  });

  it('pins the tab route segments — deep links depend on "chat" staying stable', () => {
    // router.push('/(tabs)/chat'), notification routing, and share deep links
    // all hardcode these segments; a silent rename breaks them at runtime.
    expect(getMainTabRouteNames()).toEqual(['index', 'chat', 'record', 'me']);
    expect(getMainTabRouteNames()).toContain('chat');
  });

  it('pins chat as the cold-start entry for the agent-native shell', () => {
    expect(unstable_settings.initialRouteName).toBe('chat');
  });

  it('keeps the bottom tab bar hidden and out of layout flow', () => {
    expect(getMainTabBarPresentation()).toEqual({
      layout: 'hidden',
      overlaysContent: false,
      visible: false,
      primaryEntry: 'chat',
    });
  });

  it('keeps legacy tab segments reachable without making them visible global tabs', () => {
    expect(getMainTabBarPresentation('chat')).toEqual({
      layout: 'hidden',
      overlaysContent: false,
      visible: false,
      primaryEntry: 'chat',
    });
  });
});
