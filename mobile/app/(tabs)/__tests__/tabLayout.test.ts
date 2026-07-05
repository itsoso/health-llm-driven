import {
  getMainTabAccessibilityLabels,
  getMainTabBarPresentation,
  getMainTabLabels,
  getMainTabRouteNames,
} from '../_layout';

describe('main tab labels', () => {
  it('uses Xiaoba as the assistant tab instead of private coach wording', () => {
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

  it('keeps the custom tab bar docked in layout flow instead of covering page content', () => {
    expect(getMainTabBarPresentation()).toEqual({
      layout: 'docked',
      overlaysContent: false,
    });
  });

  it('keeps the four global tabs visible on the assistant surface', () => {
    expect(getMainTabBarPresentation('chat')).toEqual({
      layout: 'docked',
      overlaysContent: false,
    });
  });
});
