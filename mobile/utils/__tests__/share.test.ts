import { Platform, Share } from 'react-native';
import * as Clipboard from 'expo-clipboard';

import { sharePlainText } from '../share';

jest.mock('expo-clipboard', () => ({
  setStringAsync: jest.fn().mockResolvedValue(undefined),
}));

describe('sharePlainText', () => {
  const originalOS = Platform.OS;

  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Share, 'share').mockResolvedValue({ action: Share.sharedAction });
  });

  afterEach(() => {
    Object.defineProperty(Platform, 'OS', { value: originalOS });
    jest.restoreAllMocks();
  });

  it('adds a web url and copies the original text on iOS so WeChat accepts the share type', async () => {
    Object.defineProperty(Platform, 'OS', { value: 'ios' });

    await sharePlainText({
      title: '菜单分享',
      message: '今晚吃鱼 + 米饭',
    });

    expect(Clipboard.setStringAsync).toHaveBeenCalledWith('今晚吃鱼 + 米饭');
    expect(Share.share).toHaveBeenCalledWith({
      title: '菜单分享',
      message: expect.stringContaining('今晚吃鱼 + 米饭'),
      url: 'https://executor.life',
    });
  });

  it('keeps Android text-only sharing unchanged', async () => {
    Object.defineProperty(Platform, 'OS', { value: 'android' });

    await sharePlainText({
      title: '健康 Agent',
      message: '今天休息',
    });

    expect(Clipboard.setStringAsync).not.toHaveBeenCalled();
    expect(Share.share).toHaveBeenCalledWith({
      title: '健康 Agent',
      message: '今天休息',
    });
  });
});
