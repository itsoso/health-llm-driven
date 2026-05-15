import { Platform, Share } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import api from '../../services/api';

import { sharePlainText } from '../share';

jest.mock('expo-clipboard', () => ({
  setStringAsync: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('../../services/api', () => ({
  __esModule: true,
  default: {
    post: jest.fn().mockResolvedValue({
      data: { share_url: 'https://health.executor.life/shared/token123' },
    }),
  },
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

  it('creates a web share page and shares that url on iOS so WeChat accepts the share type', async () => {
    Object.defineProperty(Platform, 'OS', { value: 'ios' });

    await sharePlainText({
      title: '菜单分享',
      message: '今晚吃鱼 + 米饭',
    });

    expect(api.post).toHaveBeenCalledWith('/shared/create-text', {
      title: '菜单分享',
      message: '今晚吃鱼 + 米饭',
    });
    expect(Clipboard.setStringAsync).toHaveBeenCalledWith('今晚吃鱼 + 米饭');
    expect(Share.share).toHaveBeenCalledWith({
      title: '菜单分享',
      message: '菜单分享\nhttps://health.executor.life/shared/token123',
      url: 'https://health.executor.life/shared/token123',
    });
  });

  it('shares the web page url on Android too', async () => {
    Object.defineProperty(Platform, 'OS', { value: 'android' });

    await sharePlainText({
      title: '健康 Agent',
      message: '今天休息',
    });

    expect(api.post).toHaveBeenCalledWith('/shared/create-text', {
      title: '健康 Agent',
      message: '今天休息',
    });
    expect(Clipboard.setStringAsync).toHaveBeenCalledWith('今天休息');
    expect(Share.share).toHaveBeenCalledWith({
      title: '健康 Agent',
      message: '健康 Agent\nhttps://health.executor.life/shared/token123',
    });
  });
});
