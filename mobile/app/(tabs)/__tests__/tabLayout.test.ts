import {
  getMainTabAccessibilityLabels,
  getMainTabBarPresentation,
  getMainTabLabels,
} from '../_layout';

describe('main tab labels', () => {
  it('uses Aheng as the assistant tab instead of private coach wording', () => {
    expect(getMainTabLabels()).toEqual(['今日', '阿衡', '记录', '我']);
    expect(getMainTabLabels()).not.toContain('私教');
  });

  it('keeps the assistant tab accessibility label aligned with Aheng', () => {
    expect(getMainTabAccessibilityLabels().chat).toBe('阿衡，与健康参谋对话');
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
