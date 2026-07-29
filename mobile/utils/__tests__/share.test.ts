import { Platform, Share } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import api from '../../services/api';

import {
  shareImage,
  shareLocalImage,
  sharePlainCaption,
  sharePlainText,
  shareRemoteVideo,
} from '../share';

jest.mock('expo-clipboard', () => ({
  setStringAsync: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('expo-sharing', () => ({
  isAvailableAsync: jest.fn().mockResolvedValue(true),
  shareAsync: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('expo-file-system/legacy', () => ({
  cacheDirectory: 'file:///cache/',
  downloadAsync: jest.fn(),
  deleteAsync: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('../../services/api', () => ({
  __esModule: true,
  default: {
    post: jest.fn().mockResolvedValue({
      data: {
        share_token: 'token123',
        share_url: 'https://health.executor.life/shared/token123',
      },
    }),
    delete: jest.fn().mockResolvedValue({ data: { message: '已撤销分享' } }),
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

  it('revokes the public page when the native share sheet is dismissed', async () => {
    jest.spyOn(Share, 'share').mockResolvedValueOnce({ action: Share.dismissedAction });

    const result = await sharePlainText({
      title: '小巴 · 对话节选',
      message: '这次没有真的分享出去',
    });

    expect(result.action).toBe(Share.dismissedAction);
    expect(api.delete).toHaveBeenCalledWith('/shared/token123');
  });

  it('revokes the public page when opening the native share sheet fails', async () => {
    jest.spyOn(Share, 'share').mockRejectedValueOnce(new Error('share sheet failed'));

    await expect(sharePlainText({
      title: '小巴 · 对话节选',
      message: '系统分享失败',
    })).rejects.toThrow('share sheet failed');

    expect(api.delete).toHaveBeenCalledWith('/shared/token123');
  });
});

describe('sharePlainCaption', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Share, 'share').mockResolvedValue({ action: Share.sharedAction });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('shares copy-ready text without creating a public url', async () => {
    await sharePlainCaption({
      title: '小巴 · 小红书文案',
      message: '今晚 23:00 前睡觉。\n#健康管理 #小巴',
    });

    expect(api.post).not.toHaveBeenCalled();
    expect(Clipboard.setStringAsync).toHaveBeenCalledWith('今晚 23:00 前睡觉。\n#健康管理 #小巴');
    expect(Share.share).toHaveBeenCalledWith({
      title: '小巴 · 小红书文案',
      message: '今晚 23:00 前睡觉。\n#健康管理 #小巴',
    });
  });
});

describe('shareLocalImage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (Sharing.isAvailableAsync as jest.Mock).mockResolvedValue(true);
    (Sharing.shareAsync as jest.Mock).mockResolvedValue(undefined);
  });

  it('opens the native image share sheet for a local card screenshot', async () => {
    await shareLocalImage('file:///tmp/diet-card.png');

    expect(Sharing.isAvailableAsync).toHaveBeenCalledTimes(1);
    expect(Sharing.shareAsync).toHaveBeenCalledWith('file:///tmp/diet-card.png', {
      dialogTitle: '分享饮食打卡截图',
      mimeType: 'image/png',
      UTI: 'public.png',
    });
  });

  it('fails clearly when native image sharing is unavailable', async () => {
    (Sharing.isAvailableAsync as jest.Mock).mockResolvedValueOnce(false);

    await expect(shareLocalImage('file:///tmp/diet-card.png')).rejects.toThrow('image_sharing_unavailable');
    expect(Sharing.shareAsync).not.toHaveBeenCalled();
  });

  it('normalizes a bare iOS temporary path before sharing', async () => {
    await shareLocalImage('/private/var/mobile/tmp/diet-card.png');

    expect(Sharing.shareAsync).toHaveBeenCalledWith(
      'file:///private/var/mobile/tmp/diet-card.png',
      expect.objectContaining({
        mimeType: 'image/png',
        UTI: 'public.png',
      }),
    );
  });
});

describe('shareImage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (Sharing.isAvailableAsync as jest.Mock).mockResolvedValue(true);
    (Sharing.shareAsync as jest.Mock).mockResolvedValue(undefined);
    (FileSystem.downloadAsync as jest.Mock).mockResolvedValue({
      uri: 'file:///cache/reva-shared-image-aigc-42.jpg',
      status: 200,
    });
  });

  it('downloads a protected remote image before opening the native share sheet', async () => {
    await shareImage(
      'https://health.executor.life/api/v1/upload/files/chat/42/meal.jpg?signature=signed',
      {
        target: 'xiaohongshu',
        cacheKey: 'aigc-42',
        headers: { Authorization: 'Bearer token' },
      },
    );

    expect(FileSystem.downloadAsync).toHaveBeenCalledWith(
      'https://health.executor.life/api/v1/upload/files/chat/42/meal.jpg?signature=signed',
      'file:///cache/reva-shared-image-aigc-42.jpg',
      { headers: { Authorization: 'Bearer token' } },
    );
    expect(Sharing.shareAsync).toHaveBeenCalledWith(
      'file:///cache/reva-shared-image-aigc-42.jpg',
      {
        dialogTitle: '分享到小红书',
        mimeType: 'image/jpeg',
        UTI: 'public.jpeg',
      },
    );
    expect(FileSystem.deleteAsync).toHaveBeenCalledWith(
      'file:///cache/reva-shared-image-aigc-42.jpg',
      { idempotent: true },
    );
  });

  it('cleans up a partial image when the remote download fails', async () => {
    (FileSystem.downloadAsync as jest.Mock).mockRejectedValueOnce(new Error('connection reset'));

    await expect(shareImage(
      'https://health.executor.life/private/result.png',
      { target: 'wechat', cacheKey: 'broken-image' },
    )).rejects.toThrow('connection reset');

    expect(FileSystem.deleteAsync).toHaveBeenCalledWith(
      'file:///cache/reva-shared-image-broken-image.png',
      { idempotent: true },
    );
    expect(Sharing.shareAsync).not.toHaveBeenCalled();
  });
});

describe('shareRemoteVideo', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (Sharing.isAvailableAsync as jest.Mock).mockResolvedValue(true);
    (Sharing.shareAsync as jest.Mock).mockResolvedValue(undefined);
    (FileSystem.downloadAsync as jest.Mock).mockResolvedValue({
      uri: 'file:///cache/reva-aigc-video-job-42.mp4',
      status: 200,
    });
  });

  it('downloads a private video to a local MP4 before opening the WeChat share sheet', async () => {
    await shareRemoteVideo(
      'https://health.executor.life/api/v1/upload/files/aigc/3/today.mp4?signature=signed',
      { target: 'wechat', cacheKey: 'job-42' },
    );

    expect(FileSystem.downloadAsync).toHaveBeenCalledWith(
      'https://health.executor.life/api/v1/upload/files/aigc/3/today.mp4?signature=signed',
      'file:///cache/reva-aigc-video-job-42.mp4',
    );
    expect(Sharing.shareAsync).toHaveBeenCalledWith(
      'file:///cache/reva-aigc-video-job-42.mp4',
      {
        dialogTitle: '分享到微信',
        mimeType: 'video/mp4',
        UTI: 'public.mpeg-4',
      },
    );
    expect(FileSystem.deleteAsync).toHaveBeenCalledWith(
      'file:///cache/reva-aigc-video-job-42.mp4',
      { idempotent: true },
    );
  });

  it('shares an existing local video without downloading or deleting it', async () => {
    await shareRemoteVideo('file:///tmp/aigc-result.mp4', { target: 'xiaohongshu' });

    expect(FileSystem.downloadAsync).not.toHaveBeenCalled();
    expect(Sharing.shareAsync).toHaveBeenCalledWith('file:///tmp/aigc-result.mp4', {
      dialogTitle: '分享到小红书',
      mimeType: 'video/mp4',
      UTI: 'public.mpeg-4',
    });
    expect(FileSystem.deleteAsync).not.toHaveBeenCalled();
  });

  it('removes a partial temporary file when the remote download fails', async () => {
    (FileSystem.downloadAsync as jest.Mock).mockRejectedValueOnce(new Error('connection reset'));

    await expect(shareRemoteVideo(
      'https://health.executor.life/api/v1/upload/files/aigc/3/interrupted.mp4',
      { target: 'xiaohongshu', cacheKey: 'job-interrupted' },
    )).rejects.toThrow('connection reset');

    expect(FileSystem.deleteAsync).toHaveBeenCalledWith(
      'file:///cache/reva-aigc-video-job-interrupted.mp4',
      { idempotent: true },
    );
    expect(Sharing.shareAsync).not.toHaveBeenCalled();
  });
});
