import { Platform, Share } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import api from '../../services/api';

import {
  materializeImageForLocalUse,
  shareImage,
  shareAgentSelection,
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
  BASE_URL: 'https://health.executor.life/api',
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

describe('shareAgentSelection', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Share, 'share').mockResolvedValue({ action: Share.sharedAction });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('sends only conversation and durable message ids to the Agent share API', async () => {
    await shareAgentSelection({
      title: '小巴 · 对话节选',
      conversationId: 77,
      messageIds: [41, 42],
    });

    expect(api.post).toHaveBeenCalledWith('/shared/create', {
      conversation_id: 77,
      source_type: 'agent',
      message_ids: [41, 42],
    });
    expect(api.post).not.toHaveBeenCalledWith(
      '/shared/create-text',
      expect.anything(),
    );
    expect(Clipboard.setStringAsync).toHaveBeenCalledWith(
      'https://health.executor.life/shared/token123',
    );
  });

  it('fails before network access when durable identity is missing', async () => {
    await expect(shareAgentSelection({
      title: '小巴 · 对话节选',
      conversationId: 0,
      messageIds: [41],
    })).rejects.toThrow('selected_agent_share_not_durable');

    expect(api.post).not.toHaveBeenCalled();
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

  it('reports both image download and cleanup failure without exposing a path', async () => {
    (FileSystem.downloadAsync as jest.Mock).mockRejectedValueOnce(new Error('connection reset'));
    (FileSystem.deleteAsync as jest.Mock).mockRejectedValueOnce(new Error('private path unavailable'));

    await expect(shareImage(
      'https://health.executor.life/private/result.png?secret=do-not-expose',
      { target: 'wechat', cacheKey: 'broken-image' },
    )).rejects.toThrow(/^image_share_download_failed_cleanup_failed$/);

    expect(Sharing.shareAsync).not.toHaveBeenCalled();
  });
});

describe('materializeImageForLocalUse', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (FileSystem.downloadAsync as jest.Mock).mockImplementation(
      async (_sourceUri: string, localUri: string) => ({ uri: localUri, status: 200 }),
    );
  });

  it('downloads a protected HTTPS image with headers and returns explicit cleanup', async () => {
    const materialized = await materializeImageForLocalUse(
      'https://health.executor.life/api/v1/upload/files/chat/705/meal.jpg?signature=signed',
      {
        headers: { Authorization: 'Bearer token' },
        cacheKey: 'diet-705',
      },
    );

    expect(FileSystem.downloadAsync).toHaveBeenCalledWith(
      'https://health.executor.life/api/v1/upload/files/chat/705/meal.jpg?signature=signed',
      expect.stringMatching(/^file:\/\/\/cache\/reva-local-image-[a-z0-9]+\.jpg$/),
      { headers: { Authorization: 'Bearer token' } },
    );
    const localUri = (FileSystem.downloadAsync as jest.Mock).mock.calls[0][1] as string;
    expect(localUri).not.toContain('diet-705');
    expect(localUri).not.toContain('/705/');
    expect(materialized.uri).toBe(localUri);
    expect(FileSystem.deleteAsync).not.toHaveBeenCalled();

    await materialized.cleanup();

    expect(FileSystem.deleteAsync).toHaveBeenCalledWith(
      localUri,
      { idempotent: true },
    );
  });

  it('rejects authentication headers for an external origin before downloading', async () => {
    await expect(materializeImageForLocalUse(
      'https://cdn.example.invalid/private/meal.jpg',
      { headers: { Authorization: 'Bearer token' }, cacheKey: 'diet-705' },
    )).rejects.toThrow(/^image_materialization_headers_untrusted_origin$/);

    expect(FileSystem.downloadAsync).not.toHaveBeenCalled();
  });

  it('rejects URL userinfo before downloading even without headers', async () => {
    await expect(materializeImageForLocalUse(
      'https://user:password@health.executor.life/private/meal.jpg',
    )).rejects.toThrow(/^image_materialization_url_credentials_forbidden$/);

    expect(FileSystem.downloadAsync).not.toHaveBeenCalled();
  });

  it('creates isolated artifacts for concurrent calls with the same cache key', async () => {
    const nowSpy = jest.spyOn(Date, 'now').mockReturnValue(1_700_000_000_000);
    try {
      const [first, second] = await Promise.all([
        materializeImageForLocalUse(
          'https://health.executor.life/public/meal.jpg',
          { cacheKey: 'diet-705' },
        ),
        materializeImageForLocalUse(
          'https://health.executor.life/public/meal.jpg',
          { cacheKey: 'diet-705' },
        ),
      ]);

      expect(first.uri).not.toBe(second.uri);
      expect(first.uri).not.toContain('diet-705');
      expect(second.uri).not.toContain('diet-705');

      await first.cleanup();
      await second.cleanup();

      expect(FileSystem.deleteAsync).toHaveBeenCalledWith(first.uri, { idempotent: true });
      expect(FileSystem.deleteAsync).toHaveBeenCalledWith(second.uri, { idempotent: true });
      expect(FileSystem.deleteAsync).toHaveBeenCalledTimes(2);
    } finally {
      nowSpy.mockRestore();
    }
  });

  it('cleans up a partial download and throws for a non-success status', async () => {
    (FileSystem.downloadAsync as jest.Mock).mockResolvedValueOnce({
      uri: 'file:///cache/reva-local-image-broken.jpg',
      status: 403,
    });

    await expect(materializeImageForLocalUse(
      'https://health.executor.life/private/meal.jpg?secret=do-not-log',
      { cacheKey: 'broken' },
    )).rejects.toThrow('image_materialization_download_failed');

    expect(FileSystem.deleteAsync).toHaveBeenCalledWith(
      'file:///cache/reva-local-image-broken.jpg',
      { idempotent: true },
    );
  });

  it('cleans up the planned partial file when download throws', async () => {
    (FileSystem.downloadAsync as jest.Mock).mockRejectedValueOnce(new Error('connection reset'));

    await expect(materializeImageForLocalUse(
      'https://health.executor.life/private/meal.png?secret=do-not-log',
      { cacheKey: 'interrupted' },
    )).rejects.toThrow('image_materialization_download_failed');

    const localUri = (FileSystem.downloadAsync as jest.Mock).mock.calls[0][1] as string;
    expect(localUri).not.toContain('interrupted');
    expect(FileSystem.deleteAsync).toHaveBeenCalledWith(
      localUri,
      { idempotent: true },
    );
  });

  it('reports both download and cleanup failure when a thrown download leaves an undeletable partial', async () => {
    (FileSystem.downloadAsync as jest.Mock).mockRejectedValueOnce(new Error('connection reset'));
    (FileSystem.deleteAsync as jest.Mock).mockRejectedValueOnce(new Error('private path unavailable'));

    await expect(materializeImageForLocalUse(
      'https://health.executor.life/private/meal.png?secret=do-not-expose',
      { cacheKey: 'download-and-cleanup-fail' },
    )).rejects.toThrow(/^image_materialization_download_failed_cleanup_failed$/);
  });

  it('reports both status and cleanup failure when a non-success download cannot be removed', async () => {
    (FileSystem.downloadAsync as jest.Mock).mockResolvedValueOnce({
      uri: 'file:///cache/non-success-partial.jpg',
      status: 503,
    });
    (FileSystem.deleteAsync as jest.Mock).mockRejectedValueOnce(new Error('private path unavailable'));

    await expect(materializeImageForLocalUse(
      'https://health.executor.life/private/meal.jpg?secret=do-not-expose',
      { cacheKey: 'status-and-cleanup-fail' },
    )).rejects.toThrow(/^image_materialization_download_failed_cleanup_failed$/);
  });

  it('returns a local file URI with noop cleanup and no filesystem copy', async () => {
    const materialized = await materializeImageForLocalUse('file:///tmp/diet-card.jpg');

    expect(materialized.uri).toBe('file:///tmp/diet-card.jpg');
    expect(FileSystem.downloadAsync).not.toHaveBeenCalled();

    await materialized.cleanup();

    expect(FileSystem.deleteAsync).not.toHaveBeenCalled();
  });

  it('returns a bare absolute path unchanged with noop cleanup', async () => {
    const materialized = await materializeImageForLocalUse('/private/tmp/diet-card.jpg');

    expect(materialized.uri).toBe('/private/tmp/diet-card.jpg');
    await materialized.cleanup();
    expect(FileSystem.downloadAsync).not.toHaveBeenCalled();
    expect(FileSystem.deleteAsync).not.toHaveBeenCalled();
  });

  it('rejects empty and unsupported URIs without exposing the input', async () => {
    await expect(materializeImageForLocalUse('')).rejects.toThrow('image_materialization_uri_missing');
    await expect(materializeImageForLocalUse('content://private/photo.jpg'))
      .rejects.toThrow('image_materialization_requires_file_or_https');
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
