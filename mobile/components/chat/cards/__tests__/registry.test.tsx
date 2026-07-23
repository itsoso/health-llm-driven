jest.mock('../../../../services/api', () => ({
  __esModule: true,
  BASE_URL: 'https://health.executor.life/api',
  default: { get: jest.fn(), post: jest.fn() },
}));

jest.mock('expo-web-browser', () => ({
  openBrowserAsync: jest.fn(),
}));

const mockVideoPlay = jest.fn();
const mockShareRemoteVideo = jest.fn();
const mockShareImage = jest.fn();
const mockEmitClientEvent = jest.fn();
jest.mock('expo-video', () => {
  const React = require('react');
  return {
    useVideoPlayer: jest.fn((source: string | null) => ({ source, play: mockVideoPlay })),
    VideoView: (props: Record<string, unknown>) => React.createElement('VideoView', { ...props, testID: 'aigc-video-player' }),
  };
}, { virtual: true });

jest.mock('../../../../utils/share', () => ({
  shareImage: (...args: unknown[]) => mockShareImage(...args),
  shareRemoteVideo: (...args: unknown[]) => mockShareRemoteVideo(...args),
}));
jest.mock('../../../../services/clientEvents', () => ({
  emitClientEvent: (...args: unknown[]) => mockEmitClientEvent(...args),
}));

import { CARD_REGISTRY, CARD_MAP, dispatchCard, renderCard, renderServerCards } from '../registry';
import type { CardContext } from '../types';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import { AppState } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import * as WebBrowser from 'expo-web-browser';
import api from '../../../../services/api';

const DIET_WRITE_POLICY = {
  capability_id: 'diet_draft.v1',
  required_receipt: true,
  autonomy_tier: 'manual_confirm',
  policy_reason: 'manual_confirm_write',
};

const RUNTIME_AGENDA_WRITE_POLICY = {
  capability_id: 'runtime_agenda.v1',
  required_receipt: true,
  autonomy_tier: 'manual_confirm',
  policy_reason: 'manual_confirm_write',
};

const WRITE_INTENT_POLICY = {
  capability_id: 'write_intent.v1',
  required_receipt: true,
  autonomy_tier: 'manual_confirm',
  policy_reason: 'manual_confirm_write',
};

const MEDICATION_WRITE_POLICY = {
  ...WRITE_INTENT_POLICY,
  capability_id: 'medication_draft.v1',
};

function makeContext(query: string, overrides?: Partial<CardContext>): CardContext {
  return {
    query,
    query_lower: query.toLowerCase(),
    toolsUsed: new Set(),
    data: {},
    api: { get: jest.fn(), post: jest.fn() },
    ...overrides,
  };
}

describe('CARD_REGISTRY', () => {
  it('has at least 10 registered cards', () => {
    expect(CARD_REGISTRY.length).toBeGreaterThanOrEqual(10);
  });

  it('each card has required fields', () => {
    for (const spec of CARD_REGISTRY) {
      expect(spec.type).toBeTruthy();
      expect(spec.label).toBeTruthy();
      expect(typeof spec.match).toBe('function');
      expect(typeof spec.build).toBe('function');
      expect(typeof spec.render).toBe('function');
    }
  });
});

describe('CARD_MAP', () => {
  it('maps all registry entries by type', () => {
    for (const spec of CARD_REGISTRY) {
      expect(CARD_MAP[spec.type]).toBe(spec);
    }
  });
});

describe('card match priorities', () => {
  it('sleep query matches sleep card', () => {
    const ctx = makeContext('我昨晚睡眠怎么样');
    const sleepSpec = CARD_REGISTRY.find((s) => s.type === 'sleep');
    expect(sleepSpec).toBeDefined();
    const score = sleepSpec!.match(ctx);
    expect(score).toBeGreaterThan(0);
  });

  it('weight query matches weight card', () => {
    const ctx = makeContext('我的体重多少');
    const weightSpec = CARD_REGISTRY.find((s) => s.type === 'weight');
    expect(weightSpec).toBeDefined();
    const score = weightSpec!.match(ctx);
    expect(score).toBeGreaterThan(0);
  });

  it('unrelated query does not match specific cards', () => {
    const ctx = makeContext('今天天气怎么样');
    const bpSpec = CARD_REGISTRY.find((s) => s.type === 'blood_pressure');
    expect(bpSpec).toBeDefined();
    const score = bpSpec!.match(ctx);
    expect(score === null || score === 0).toBe(true);
  });
});

describe('dispatchCard', () => {
  it('returns null for empty query with no matching cards', async () => {
    const ctx = makeContext('');
    const result = await dispatchCard(ctx);
    expect(result).toBeNull();
  });

  it('build 抛错时不阻塞, 返回 null', async () => {
    const ctx = makeContext('体重多少', {
      api: { get: jest.fn().mockRejectedValue(new Error('net')), post: jest.fn() },
    });
    const result = await dispatchCard(ctx);
    expect(result).toBeNull();
  });
});

describe('renderCard 安全降级', () => {
  it('未知 type 返回 null, 不抛异常', () => {
    expect(renderCard({ type: 'fake_xxx', data: {} })).toBeNull();
  });

  it('已知 type → 返回 React 元素', () => {
    const r = renderCard({ type: 'vitals', data: { sleep: '8h' } });
    expect(r).not.toBeNull();
  });

  it('renders the private meal photo supplied with a contextual diet draft', () => {
    const element = renderCard({
      type: 'diet_draft',
      data: {
        meal_type: 'lunch',
        food_items: '鸡胸肉 + 杂粮饭',
        calories: 560,
        protein: 42,
        source: 'chat_photo',
        photo_url: '/api/v1/upload/files/diet/1/lunch.jpg?expires=1&signature=signed',
      },
    });

    const screen = render(element!);
    expect(screen.getByTestId('diet-draft-photo')).toHaveProp(
      'source',
      expect.arrayContaining([
        expect.objectContaining({
          uri: 'https://health.executor.life/api/v1/upload/files/diet/1/lunch.jpg?expires=1&signature=signed',
        }),
      ]),
    );
  });

  it('renders an automatic contextual meal save as a visible receipt without an action', () => {
    const element = renderCard({
      type: 'diet_draft',
      data: {
        meal_type: 'lunch',
        food_items: '鸡胸肉 + 杂粮饭',
        recorded: true,
        record_id: 76,
        receipt_message: '已自动记录到今日午餐',
        source: 'chat_photo',
      },
    });

    const screen = render(element!);
    expect(screen.getByText('午餐已记录')).toBeTruthy();
    expect(screen.getByText('已自动记录到今日午餐')).toBeTruthy();
    expect(screen.queryByText('确认记录')).toBeNull();
  });

  it('renders and refreshes a private AIGC media job card', async () => {
    let resolveRequest: ((value: unknown) => void) | undefined;
    (api.get as jest.Mock).mockImplementationOnce(() => new Promise((resolve) => {
      resolveRequest = resolve;
    }));
    const element = renderCard({
      type: 'aigc_media_job',
      data: {
        job_id: 'aigc_1',
        kind: 'image_to_video',
        status: 'queued',
        progress: 10,
        title: '小巴创作',
        result: { media_type: null, url: null },
      },
    });

    expect(element).not.toBeNull();
    const screen = render(element!);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/aigc/media/jobs/aigc_1'));
    await act(async () => {
      resolveRequest?.({
        data: {
          id: 'aigc_1',
          kind: 'image_to_video',
          status: 'running',
          progress: 56,
          title: '小巴创作',
          result: { media_type: null, url: null },
        },
      });
      await Promise.resolve();
    });
    expect(screen.getByText('生成中')).toBeTruthy();
    expect(screen.getByText('56%')).toBeTruthy();
    screen.unmount();
  });

  it('refreshes an active AIGC job immediately on foreground and network recovery', async () => {
    (api.get as jest.Mock).mockReset();
    let appStateListener: ((state: string) => void) | undefined;
    let networkListener: ((state: { isConnected: boolean | null }) => void) | undefined;
    const appStateSpy = jest.spyOn(AppState, 'addEventListener').mockImplementation(
      ((_event: string, listener: (state: string) => void) => {
        appStateListener = listener;
        return { remove: jest.fn() };
      }) as typeof AppState.addEventListener,
    );
    (NetInfo.addEventListener as jest.Mock).mockImplementation(
      (listener: (state: { isConnected: boolean | null }) => void) => {
        networkListener = listener;
        return jest.fn();
      },
    );
    (api.get as jest.Mock).mockResolvedValue({
      data: {
        id: 'aigc_resume_1',
        kind: 'text_to_video',
        status: 'running',
        progress: 50,
        result: { media_type: null, url: null },
      },
    });
    const screen = render(renderCard({
      type: 'aigc_media_job',
      data: {
        job_id: 'aigc_resume_1',
        kind: 'text_to_video',
        status: 'running',
        progress: 25,
        result: { media_type: null, url: null },
      },
    })!);
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
    (api.get as jest.Mock).mockClear();

    await act(async () => {
      appStateListener?.('background');
      appStateListener?.('active');
      await Promise.resolve();
    });
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));
    (api.get as jest.Mock).mockClear();

    await act(async () => {
      networkListener?.({ isConnected: false });
      networkListener?.({ isConnected: true });
      await Promise.resolve();
    });
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(1));

    screen.unmount();
    appStateSpy.mockRestore();
  });

  it('describes HappyHorse image-to-video ratio as following the source image', () => {
    const screen = render(renderCard({
      type: 'aigc_media_job',
      data: {
        job_id: 'aigc_source_ratio',
        kind: 'image_to_video',
        status: 'running',
        progress: 50,
        spec: {
          duration_seconds: 10,
          ratio_mode: 'source',
          resolution: '720P',
          generates_audio: true,
        },
        result: { media_type: null, url: null },
      },
    })!);

    expect(screen.getByText('10秒 · 跟随原图 · 720P · 含音频')).toBeTruthy();
    expect(screen.queryByText(/9:16/)).toBeNull();
    screen.unmount();
  });

  it('restores a consumed AIGC confirmation as its existing job on mount', async () => {
    (api.get as jest.Mock).mockResolvedValueOnce({
      data: {
        id: 'aigc_confirm_restore',
        status: 'dispatched',
        job: {
          id: 'aigc_restored_1',
          kind: 'text_to_video',
          status: 'failed',
          progress: 0,
          can_retry: true,
          error_message: '创作服务授权异常，已通知管理员。',
          result: { media_type: null, url: null },
        },
      },
    }).mockResolvedValueOnce({
      data: {
        id: 'aigc_restored_1',
        kind: 'text_to_video',
        status: 'failed',
        progress: 0,
        can_retry: true,
        error_message: '创作服务授权异常，已通知管理员。',
        result: { media_type: null, url: null },
      },
    });
    const element = renderCard({
      type: 'aigc_media_confirmation',
      data: {
        confirmation_id: 'aigc_confirm_restore',
        kind: 'text_to_video',
        status: 'pending',
      },
    });
    const screen = render(element!);

    expect(await screen.findByText('重试生成')).toBeTruthy();
    expect(api.get).toHaveBeenCalledWith('/aigc/media/confirmations/aigc_confirm_restore');
    screen.unmount();
  });

  it('lets the user choose a disclosed video duration before the one-time confirmation', async () => {
    (api.get as jest.Mock).mockResolvedValueOnce({
      data: { id: 'aigc_confirm_duration', status: 'pending', job: null },
    });
    (api.post as jest.Mock).mockResolvedValueOnce({
      data: {
        id: 'aigc_duration_job',
        kind: 'text_to_video',
        status: 'queued',
        progress: 10,
        spec: {
          duration_seconds: 15,
          ratio: '9:16',
          resolution: '720P',
          generates_audio: true,
        },
        result: { media_type: null, url: null },
      },
    });
    const screen = render(renderCard({
      type: 'aigc_media_confirmation',
      data: {
        confirmation_id: 'aigc_confirm_duration',
        kind: 'text_to_video',
        status: 'pending',
        duration_seconds: 5,
        duration_options: [5, 10, 15],
        ratio: '9:16',
        resolution: '720P',
        provider: '百炼 HappyHorse',
      },
    })!);

    fireEvent.press(screen.getByLabelText('选择15秒'));
    fireEvent.press(screen.getByLabelText('确认生成15秒短视频'));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/aigc/media/confirmations/aigc_confirm_duration/confirm',
      { duration_seconds: 15 },
    ));
    expect(await screen.findByText('15秒 · 9:16 · 720P · 含音频')).toBeTruthy();
    screen.unmount();
    (api.post as jest.Mock).mockClear();
  });

  it('shows an expired AIGC draft as re-confirmable instead of a failed submission', async () => {
    (api.get as jest.Mock).mockResolvedValueOnce({
      data: {
        id: 'aigc_confirm_expired',
        status: 'expired',
        job: null,
        spec: {
          duration_seconds: 5,
          ratio: '9:16',
          resolution: '720P',
          generates_audio: true,
        },
      },
    });
    const screen = render(renderCard({
      type: 'aigc_media_confirmation',
      data: {
        confirmation_id: 'aigc_confirm_expired',
        kind: 'text_to_video',
        status: 'pending',
        duration_seconds: 5,
        duration_options: [5, 10, 15],
      },
    })!);

    expect(await screen.findByText('草稿已过期，点击下方可重新确认生成。')).toBeTruthy();
    expect(screen.getByLabelText('重新确认生成5秒短视频')).toBeTruthy();
    expect(screen.queryByText('提交未完成，请稍后重试。')).toBeNull();
    screen.unmount();
  });

  it('resolves an indeterminate AIGC confirmation before reporting a failure', async () => {
    (api.get as jest.Mock)
      .mockResolvedValueOnce({
        data: { id: 'aigc_confirm_reconcile', status: 'pending', job: null },
      })
      .mockResolvedValueOnce({
        data: {
          id: 'aigc_confirm_reconcile',
          status: 'dispatched',
          job: {
            id: 'aigc_reconciled_job',
            kind: 'text_to_video',
            status: 'queued',
            progress: 10,
            result: { media_type: null, url: null },
          },
        },
      })
      .mockResolvedValueOnce({
        data: {
          id: 'aigc_reconciled_job',
          kind: 'text_to_video',
          status: 'queued',
          progress: 10,
          result: { media_type: null, url: null },
        },
      });
    (api.post as jest.Mock).mockRejectedValueOnce({
      response: {
        status: 409,
        data: { detail: 'AIGC 任务正在提交，请稍后查看' },
      },
    });
    const screen = render(renderCard({
      type: 'aigc_media_confirmation',
      data: {
        confirmation_id: 'aigc_confirm_reconcile',
        kind: 'text_to_video',
        status: 'pending',
      },
    })!);

    fireEvent.press(screen.getByLabelText('确认生成5秒短视频'));

    expect(await screen.findByText('排队中')).toBeTruthy();
    expect(screen.queryByText('提交未完成，请稍后重试。')).toBeNull();
    expect(api.get).toHaveBeenCalledWith(
      '/aigc/media/confirmations/aigc_confirm_reconcile',
    );
    screen.unmount();
    (api.post as jest.Mock).mockClear();
  });

  it('keeps reconciling a dispatching confirmation until its durable job appears', async () => {
    (api.get as jest.Mock)
      .mockResolvedValueOnce({
        data: { id: 'aigc_confirm_dispatching', status: 'pending', can_confirm: true, job: null },
      })
      .mockResolvedValueOnce({
        data: { id: 'aigc_confirm_dispatching', status: 'dispatching', can_confirm: false, job: null },
      })
      .mockResolvedValueOnce({
        data: {
          id: 'aigc_confirm_dispatching',
          status: 'dispatched',
          can_confirm: false,
          job: {
            id: 'aigc_dispatching_job',
            kind: 'text_to_video',
            status: 'queued',
            progress: 10,
            result: { media_type: null, url: null },
          },
        },
      })
      .mockResolvedValueOnce({
        data: {
          id: 'aigc_dispatching_job',
          kind: 'text_to_video',
          status: 'queued',
          progress: 10,
          result: { media_type: null, url: null },
        },
      });
    (api.post as jest.Mock).mockRejectedValueOnce({
      response: {
        status: 409,
        data: { detail: 'AIGC 任务正在提交，请稍后查看' },
      },
    });
    const screen = render(renderCard({
      type: 'aigc_media_confirmation',
      data: {
        confirmation_id: 'aigc_confirm_dispatching',
        kind: 'text_to_video',
        status: 'pending',
      },
    })!);

    fireEvent.press(screen.getByLabelText('确认生成5秒短视频'));

    expect(await screen.findByText('排队中')).toBeTruthy();
    const confirmationGets = (api.get as jest.Mock).mock.calls.filter(
      ([url]) => url === '/aigc/media/confirmations/aigc_confirm_dispatching',
    );
    screen.unmount();
    (api.get as jest.Mock).mockClear();
    (api.post as jest.Mock).mockClear();
    expect(confirmationGets).toHaveLength(3);
  });

  it('renders a private generated short video inline with native controls', async () => {
    mockVideoPlay.mockClear();
    mockShareRemoteVideo.mockResolvedValueOnce(undefined);
    const relativeVideoUrl = '/api/v1/upload/files/aigc/3/today.mp4?expires=1&signature=signed';
    (api.get as jest.Mock).mockResolvedValueOnce({
      data: {
        id: 'aigc_video_1',
        kind: 'image_to_video',
        status: 'succeeded',
        progress: 100,
        title: '小巴创作',
        result: { media_type: 'video/mp4', url: relativeVideoUrl },
      },
    });
    const element = renderCard({
      type: 'aigc_media_job',
      data: {
        job_id: 'aigc_video_1',
        kind: 'image_to_video',
        status: 'succeeded',
        progress: 100,
        title: '小巴创作',
        result: { media_type: 'video/mp4', url: relativeVideoUrl },
      },
    });
    const screen = render(element!);

    const player = await screen.findByTestId('aigc-video-player');
    expect(player).toHaveProp('player', expect.objectContaining({
      source: 'https://health.executor.life/api/v1/upload/files/aigc/3/today.mp4?expires=1&signature=signed',
    }));
    expect(player).toHaveProp('nativeControls', true);
    expect(player).toHaveProp('fullscreenOptions', expect.objectContaining({ enable: true }));
    fireEvent.press(screen.getByLabelText('播放短视频'));
    expect(mockVideoPlay).toHaveBeenCalledTimes(1);
    expect(mockEmitClientEvent).toHaveBeenCalledWith('aigc_media_played', {
      media_kind: 'video',
    });
    fireEvent.press(screen.getByLabelText('分享到微信'));
    await waitFor(() => {
      expect(mockShareRemoteVideo).toHaveBeenCalledWith(
        'https://health.executor.life/api/v1/upload/files/aigc/3/today.mp4?expires=1&signature=signed',
        { target: 'wechat', cacheKey: 'aigc_video_1' },
      );
    });
    expect(mockEmitClientEvent).toHaveBeenCalledWith('aigc_media_shared', {
      phase: 'completed',
      media_kind: 'video',
      share_target: 'wechat',
    });
    expect(api.post).not.toHaveBeenCalled();
    expect(WebBrowser.openBrowserAsync).not.toHaveBeenCalled();
    screen.unmount();
  });

  it('shares a completed generated image without submitting another generation request', async () => {
    mockShareImage.mockResolvedValueOnce(undefined);
    const relativeImageUrl = '/api/v1/upload/files/aigc/3/result.jpg?expires=1&signature=signed';
    (api.get as jest.Mock).mockResolvedValueOnce({
      data: {
        id: 'aigc_image_1',
        kind: 'text_to_image',
        status: 'succeeded',
        progress: 100,
        result: { media_type: 'image/jpeg', url: relativeImageUrl },
      },
    });
    const screen = render(renderCard({
      type: 'aigc_media_job',
      data: {
        job_id: 'aigc_image_1',
        kind: 'text_to_image',
        status: 'succeeded',
        progress: 100,
        result: { media_type: 'image/jpeg', url: relativeImageUrl },
      },
    })!);

    fireEvent.press(await screen.findByLabelText('图片分享到小红书'));
    await waitFor(() => {
      expect(mockShareImage).toHaveBeenCalledWith(
        'https://health.executor.life/api/v1/upload/files/aigc/3/result.jpg?expires=1&signature=signed',
        {
          target: 'xiaohongshu',
          cacheKey: 'aigc_image_1',
          mimeType: 'image/jpeg',
        },
      );
    });
    expect(api.post).not.toHaveBeenCalled();
    screen.unmount();
  });

  it('coalesces repeated video share taps while the first share is active', async () => {
    let finishShare: (() => void) | undefined;
    mockShareRemoteVideo.mockImplementationOnce(() => new Promise<void>((resolve) => {
      finishShare = resolve;
    }));
    const resultUrl = '/api/v1/upload/files/aigc/3/share-once.mp4?signature=signed';
    (api.get as jest.Mock).mockResolvedValue({
      data: {
        id: 'aigc_video_share_once',
        kind: 'text_to_video',
        status: 'succeeded',
        progress: 100,
        result: { media_type: 'video/mp4', url: resultUrl },
      },
    });
    const screen = render(renderCard({
      type: 'aigc_media_job',
      data: {
        job_id: 'aigc_video_share_once',
        kind: 'text_to_video',
        status: 'succeeded',
        progress: 100,
        result: { media_type: 'video/mp4', url: resultUrl },
      },
    })!);

    const shareButton = await screen.findByLabelText('分享到小红书');
    fireEvent.press(shareButton);
    fireEvent.press(shareButton);
    await waitFor(() => expect(mockShareRemoteVideo).toHaveBeenCalledTimes(1));

    await act(async () => {
      finishShare?.();
    });
    screen.unmount();
  });

  it('drops stale generation actions from a completed AIGC job card', () => {
    const [card] = renderServerCards([{
      type: 'aigc_media_job',
      data: {
        job_id: 'aigc_video_done',
        kind: 'text_to_video',
        status: 'succeeded',
        progress: 100,
      },
      actions: [{
        id: 'stale-confirm',
        label: '再次生成',
        action: 'aigc_media.confirm',
        endpoint: '/aigc/media/confirmations/stale/confirm',
        requires_manual_confirm: true,
        required_receipt: true,
        capability_id: 'aigc_media_confirmation.v1',
        autonomy_tier: 'manual_confirm',
        policy_reason: 'manual_confirm_write',
      }],
    }]);

    expect(card.actions).toEqual([]);
  });

  it('renders an indeterminate AIGC submission as terminal and does not claim failure', () => {
    const element = renderCard({
      type: 'aigc_media_job',
      data: {
        job_id: 'aigc_unknown_1',
        kind: 'text_to_video',
        status: 'submission_unknown',
        progress: 0,
        error_message: '提交结果待核验，已停止自动重试以避免重复生成',
        result: { media_type: null, url: null },
      },
    });

    const screen = render(element!);

    expect(screen.getByText('提交待核验')).toBeTruthy();
    expect(screen.getByText(/已停止自动重试/)).toBeTruthy();
    expect(screen.queryByText('重试生成')).toBeNull();
    screen.unmount();
  });

  it('retries a definitively rejected AIGC job from the failed card', async () => {
    (api.get as jest.Mock).mockResolvedValueOnce({
      data: {
        id: 'aigc_retry_1',
        kind: 'text_to_video',
        status: 'failed',
        progress: 0,
        can_retry: true,
        error_code: 'provider_auth_failed',
        error_message: '创作服务授权异常，已通知管理员。',
        result: { media_type: null, url: null },
      },
    });
    (api.post as jest.Mock).mockResolvedValueOnce({
      data: {
        id: 'aigc_retry_1',
        kind: 'text_to_video',
        status: 'queued',
        progress: 10,
        can_retry: false,
        result: { media_type: null, url: null },
      },
    });
    const element = renderCard({
      type: 'aigc_media_job',
      data: {
        job_id: 'aigc_retry_1',
        kind: 'text_to_video',
        status: 'failed',
        progress: 0,
        can_retry: true,
        error_code: 'provider_auth_failed',
        error_message: '创作服务授权异常，已通知管理员。',
        result: { media_type: null, url: null },
      },
    });
    const screen = render(element!);
    const retry = await screen.findByText('重试生成');

    fireEvent.press(retry);

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/aigc/media/jobs/aigc_retry_1/retry'));
    expect(await screen.findByText('排队中')).toBeTruthy();
    screen.unmount();
  });

  it('renders reminder record cards from chat tool results', () => {
    const r = renderCard({
      type: 'record',
      data: { type: 'reminder', detail: '已设置每日提醒：臀中肌训练' },
    });
    expect(r).not.toBeNull();

    const { getByText } = render(r!);
    expect(getByText('已设置每日提醒：臀中肌训练')).toBeTruthy();
  });

  it('renders diet record cards with meal visuals (calorie hero + food chips)', () => {
    const r = renderCard({
      type: 'record',
      data: {
        type: 'diet',
        detail: '已记录',
        meal_type: 'lunch',
        food: '鸡胸肉 + 糙米饭 + 西兰花',
        calories: 520.4,
        protein: 42,
        carbs: 55,
        fat: 14,
      },
    });
    expect(r).not.toBeNull();

    const { getByText } = render(r!);
    // 餐次标题 + 类目 badge.
    expect(getByText('午餐已记录')).toBeTruthy();
    expect(getByText('饮食')).toBeTruthy();
    // 热量 hero 走 Math.round (520.4 → 520);hero 是嵌套 Text (数字 + " kcal"),
    // 用 substring 匹配整段文本, 并确认取整后的数字进了 hero.
    expect(getByText('kcal', { exact: false })).toBeTruthy();
    expect(getByText(/520/)).toBeTruthy();
    // 食材拆成独立 chip.
    expect(getByText('鸡胸肉')).toBeTruthy();
    expect(getByText('糙米饭')).toBeTruthy();
    expect(getByText('西兰花')).toBeTruthy();
  });

  it('falls back to the simple record row for a bare diet record (no food/macros)', () => {
    const r = renderCard({
      type: 'record',
      data: { type: 'diet', detail: '已记录早餐' },
    });
    expect(r).not.toBeNull();

    const { getByText, queryByText } = render(r!);
    // 无 food/macros → 走简单行, 显示 detail, 不出现餐食可视化标题.
    expect(getByText('已记录早餐')).toBeTruthy();
    expect(queryByText('饮食')).toBeNull();
  });

  it('renders record quality cards with personal cautions and inline next-meal actions', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'record_quality',
      data: {
        domain: 'diet',
        title: '午餐已记录',
        summary: '770 kcal · 蛋白 30g · 碳水 70g',
        metrics: [
          { label: '热量', value: '770kcal' },
          { label: '蛋白', value: '30g' },
        ],
        progress: {
          protein_total_g: 37,
          protein_target_g: 112,
          remaining_protein_g: 75,
          calories_total: 1040,
          meals_count: 2,
        },
        primary_judgement: '蛋白质到位，但晚餐仍要补足。',
        personal_cautions: ['胃溃疡记录在案，冷饮/酸性饮品可能刺激胃，建议观察耐受。'],
        next_action: '晚餐优先 40g 蛋白，少油少刺激。',
        boundary: '健康管理建议，不替代医生诊断或治疗。',
      },
      actions: [
        {
          id: 'show-next-meal',
          label: '看下一餐建议',
          action: 'ui.inline.expand',
          style: 'primary',
          payload: {
            target: 'next_meal',
            patch: {
              expanded_sections: ['next_meal'],
              next_meal_detail: {
                title: '下一餐建议',
                summary: '晚餐优先 40g 蛋白，少油少刺激。',
                options: ['鱼/豆腐 + 熟蔬菜 + 少量主食', '鸡胸/鸡蛋 + 南瓜 + 绿叶菜'],
                rationale: ['午餐后今日蛋白还差约 75g', '胃溃疡背景下避免冷饮和强刺激'],
                continue_prompt: '可以继续问小巴：如果今晚只能外卖，怎么选。',
              },
            },
          },
        },
      ],
    } as any;

    const element = renderCard(descriptor, { onAction });
    expect(element).not.toBeNull();

    const { getAllByText, getByText } = render(element!);
    expect(getByText('午餐已记录')).toBeTruthy();
    expect(getByText('770 kcal · 蛋白 30g · 碳水 70g')).toBeTruthy();
    expect(getAllByText('37/112g').length).toBeGreaterThanOrEqual(1);
    expect(getByText('已记 1040 kcal · 2 餐 · 还差约 75g 蛋白')).toBeTruthy();
    expect(getByText('胃溃疡记录在案，冷饮/酸性饮品可能刺激胃，建议观察耐受。')).toBeTruthy();

    fireEvent.press(getByText('看下一餐建议'));
    expect(onAction).not.toHaveBeenCalled();
    expect(getByText('下一餐建议')).toBeTruthy();
    expect(getByText('鱼/豆腐 + 熟蔬菜 + 少量主食')).toBeTruthy();
    expect(getByText('可以继续问小巴：如果今晚只能外卖，怎么选。')).toBeTruthy();
  });

  it('renders confirmable diet draft cards with next action guidance', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'diet_draft',
      data: {
        meal_type: 'lunch',
        food_items: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
        calories: 770,
        protein: 30,
        carbs: 70,
        fat: 17,
        confidence: 0.82,
        source: 'chat_photo',
        suggestions: ['晚餐优先补 40g 蛋白', '餐后轻走 8-10 分钟'],
        post_meal_walk: { recommended: true, minutes: 10 },
        boundary: '营养为估算值,确认后写入今日饮食记录。',
      },
      actions: [
        {
          id: 'confirm-diet-draft',
          label: '确认记录',
          action: 'diet_record.create',
          endpoint: '/diet/records',
          requires_manual_confirm: true,
          ...DIET_WRITE_POLICY,
          style: 'primary',
          payload: {
            record: {
              meal_type: 'lunch',
              food_items: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
              calories: 770,
              protein: 30,
              carbs: 70,
              fat: 17,
              notes: '来源: chat_photo; 置信度 82%',
            },
          },
        },
        {
          id: 'open-diet',
          label: '去饮食页修正',
          action: 'route.open',
          payload: { route: '/diet' },
        },
      ],
    } as any;

    const element = renderCard(descriptor, { onAction });
    expect(element).not.toBeNull();

    const { getByText, queryByText } = render(element!);
    // 拍照草稿按原型收敛为识别摘要,不再堆满营养与建议模块。
    expect(getByText('午餐草稿 · 识别完成')).toBeTruthy();
    expect(getByText('高置信')).toBeTruthy();
    expect(getByText('煎牛肉能量碗')).toBeTruthy();
    expect(getByText('姜黄鲜柠维C茶')).toBeTruthy();
    expect(getByText('kcal', { exact: false })).toBeTruthy();
    expect(getByText('蛋白')).toBeTruthy();
    expect(getByText('30g')).toBeTruthy();
    expect(getByText('营养为估算值，保存前可继续修正')).toBeTruthy();
    expect(getByText('修正')).toBeTruthy();
    expect(queryByText('餐后轻走 10 分钟')).toBeNull();

    fireEvent.press(getByText('确认记录'));
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'diet_record.create', endpoint: '/diet/records' }),
      expect.objectContaining({ type: 'diet_draft' }),
    );
  });

  it('renders medication draft cards with safe route actions', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'medication_draft',
      data: {
        medication_name: '替普瑞酮胶囊（施维舒）',
        dose: '20mg',
        confidence: 0.9,
        source: 'chat',
        suggestions: ['确认前核对药名、剂量和服用时间'],
        boundary: '确认后记录为已服用; 不替代医嘱, 不调整剂量。',
      },
      actions: [
        {
          id: 'open-medication-draft',
          label: '去用药页记录',
          action: 'route.open',
          style: 'primary',
          payload: { route: '/medications?draft=medication&name=%E6%9B%BF%E6%99%AE%E7%91%9E%E9%85%AE' },
        },
        {
          id: 'ask-medication-draft',
          label: '问小巴',
          action: 'route.open',
          style: 'secondary',
          payload: { route: '/chat?prompt=%E8%AF%B7%E5%B8%AE%E6%88%91%E6%A0%B8%E5%AF%B9' },
        },
      ],
    } as any;

    const element = renderCard(descriptor, { onAction });
    expect(element).not.toBeNull();

    const { getByText } = render(element!);
    expect(getByText('用药 · 待确认')).toBeTruthy();
    expect(getByText('替普瑞酮胶囊（施维舒）')).toBeTruthy();
    expect(getByText('20mg')).toBeTruthy();
    expect(getByText('置信度 90% · 来源: 对话')).toBeTruthy();
    expect(getByText('确认后记录为已服用; 不替代医嘱, 不调整剂量。')).toBeTruthy();

    fireEvent.press(getByText('去用药页记录'));
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'route.open' }),
      expect.objectContaining({ type: 'medication_draft' }),
    );
  });

  it('renders supplement draft cards with safe route actions', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'supplement_draft',
      data: {
        supplement_name: '鱼油',
        confidence: 0.82,
        source: 'chat',
        suggestions: ['确认前核对补剂名、剂量和服用时间'],
        boundary: '确认后记录为已服用; 如正在用药或有慢病, 先核对相互作用。',
      },
      actions: [
        {
          id: 'open-supplement-draft',
          label: '去补剂页记录',
          action: 'route.open',
          style: 'primary',
          payload: { route: '/supplement-inventory?draft=supplement&name=%E9%B1%BC%E6%B2%B9' },
        },
        {
          id: 'ask-supplement-draft',
          label: '问小巴',
          action: 'route.open',
          style: 'secondary',
          payload: { route: '/chat?prompt=%E8%AF%B7%E5%B8%AE%E6%88%91%E6%A0%B8%E5%AF%B9' },
        },
      ],
    } as any;

    const element = renderCard(descriptor, { onAction });
    expect(element).not.toBeNull();

    const { getByText } = render(element!);
    expect(getByText('补剂 · 待确认')).toBeTruthy();
    expect(getByText('鱼油')).toBeTruthy();
    expect(getByText('置信度 82% · 来源: 对话')).toBeTruthy();
    expect(getByText('确认后记录为已服用; 如正在用药或有慢病, 先核对相互作用。')).toBeTruthy();

    fireEvent.press(getByText('去补剂页记录'));
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'route.open' }),
      expect.objectContaining({ type: 'supplement_draft' }),
    );
  });

  it('lets users edit a diet draft inline before confirming it', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'diet_draft',
      data: {
        meal_type: 'lunch',
        food_items: '煎牛肉能量碗',
        calories: 770,
        protein: 30,
        carbs: 70,
        fat: 17,
      },
      actions: [
        {
          id: 'confirm-diet-draft',
          label: '确认记录',
          action: 'diet_record.create',
          endpoint: '/diet/records',
          requires_manual_confirm: true,
          ...DIET_WRITE_POLICY,
          style: 'primary',
          payload: {
            record: {
              meal_type: 'lunch',
              food_items: '煎牛肉能量碗',
              calories: 770,
              protein: 30,
              carbs: 70,
              fat: 17,
            },
          },
        },
      ],
    } as any;

    const element = renderCard(descriptor, { onAction });
    expect(element).not.toBeNull();

    const { getByText, getByLabelText, getByTestId } = render(element!);
    fireEvent.press(getByText('修正'));
    const stopPropagation = jest.fn();
    fireEvent(getByTestId('diet-draft-inline-editor'), 'touchStart', { stopPropagation });
    expect(stopPropagation).toHaveBeenCalledTimes(1);
    fireEvent.press(getByText('晚餐'));
    fireEvent.changeText(getByLabelText('食物描述'), '鸡胸肉 200g + 杂粮饭 100g');
    fireEvent.changeText(getByLabelText('蛋白'), '46');
    fireEvent.press(getByText('确认记录'));

    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({
        action: 'diet_record.create',
        payload: expect.objectContaining({
          record: expect.objectContaining({
            meal_type: 'dinner',
            food_items: '鸡胸肉 200g + 杂粮饭 100g',
            calories: 770,
            protein: 46,
            carbs: 70,
            fat: 17,
          }),
        }),
      }),
      expect.objectContaining({ type: 'diet_draft' }),
    );
  });

  it('lets users save and confirm an edited diet draft from the editor', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'diet_draft',
      data: {
        meal_type: 'lunch',
        food_items: '煎牛肉能量碗',
        calories: 770,
        protein: 30,
        carbs: 70,
        fat: 17,
      },
      actions: [
        {
          id: 'confirm-diet-draft',
          label: '确认记录',
          action: 'diet_record.create',
          endpoint: '/diet/records',
          requires_manual_confirm: true,
          ...DIET_WRITE_POLICY,
          style: 'primary',
          payload: {
            record: {
              meal_type: 'lunch',
              food_items: '煎牛肉能量碗',
              calories: 770,
              protein: 30,
              carbs: 70,
              fat: 17,
            },
          },
        },
      ],
    } as any;

    const element = renderCard(descriptor, { onAction });
    expect(element).not.toBeNull();

    const { getByText, getByLabelText } = render(element!);
    fireEvent.press(getByText('修正'));
    fireEvent.press(getByText('晚餐'));
    fireEvent.changeText(getByLabelText('食物描述'), '鸡胸肉 200g + 杂粮饭 100g');
    fireEvent.changeText(getByLabelText('蛋白'), '46');
    fireEvent.press(getByText('保存并确认'));

    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({
        action: 'diet_record.create',
        payload: expect.objectContaining({
          record: expect.objectContaining({
            meal_type: 'dinner',
            food_items: '鸡胸肉 200g + 杂粮饭 100g',
            calories: 770,
            protein: 46,
            carbs: 70,
            fat: 17,
          }),
        }),
      }),
      expect.objectContaining({ type: 'diet_draft' }),
    );
  });

  it('renders structured diet draft food arrays as a readable meal line', () => {
    const element = renderCard({
      type: 'diet_draft',
      data: {
        meal_type: 'dinner',
        food_items: ['鸡胸肉 200g', '杂粮饭 100g', '西兰花'],
        protein: 46,
      },
    } as any);

    expect(element).not.toBeNull();
    const { getByText } = render(element!);
    // food_items 数组 → 每项一个食材 chip。
    expect(getByText('鸡胸肉 200g')).toBeTruthy();
    expect(getByText('杂粮饭 100g')).toBeTruthy();
    expect(getByText('西兰花')).toBeTruthy();
    expect(getByText('晚餐草稿 · 识别完成')).toBeTruthy();
    expect(getByText('蛋白')).toBeTruthy();
    expect(getByText('46g')).toBeTruthy();
    expect(getByText('营养为估算值，保存前可继续修正')).toBeTruthy();
  });

  it('marks incomplete agent diet drafts as pending nutrition backfill', () => {
    const element = renderCard({
      type: 'diet_draft',
      data: {
        meal_type: 'lunch',
        food_items: '鸡胸肉 200g + 糙米饭一碗',
        source: 'voice',
      },
      actions: [
        {
          id: 'confirm-diet-draft',
          label: '确认记录',
          action: 'diet_record.create',
          endpoint: '/diet/records',
          requires_manual_confirm: true,
          ...DIET_WRITE_POLICY,
          style: 'primary',
          payload: {
            record: {
              meal_type: 'lunch',
              food_items: '鸡胸肉 200g + 糙米饭一碗',
            },
          },
        },
      ],
    } as any);

    expect(element).not.toBeNull();
    const { getByText } = render(element!);
    expect(getByText('午餐草稿 · 识别完成')).toBeTruthy();
    expect(getByText('营养为估算值，保存前可继续修正')).toBeTruthy();
  });

  it('does not render diet drafts built from captured UI copy instead of food', () => {
    const element = renderCard({
      type: 'diet_draft',
      data: {
        meal_type: 'lunch',
        food_items: '和午餐食品营养卡',
        calories: 0,
        protein: 0,
        carbs: 0,
        fat: 0,
      },
      actions: [{
        id: 'confirm-diet-draft',
        label: '确认记录',
        action: 'diet_record.create',
        endpoint: '/diet/records',
        requires_manual_confirm: true,
        ...DIET_WRITE_POLICY,
        payload: {
          record: {
            meal_type: 'lunch',
            food_items: '和午餐食品营养卡',
          },
        },
      }],
    } as any);

    expect(element).toBeNull();
  });

  it('renders server card actions and dispatches through onAction', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'vitals',
      data: { sleep: '8h' },
      actions: [
        {
          id: 'complete-now',
          label: '完成',
          action: 'agenda.complete',
          endpoint: '/agenda/complete',
          requires_manual_confirm: true,
          ...RUNTIME_AGENDA_WRITE_POLICY,
          payload: {
            source: { object_type: 'health_protocol', object_id: 7 },
          },
        },
      ],
    } as any;

    const element = renderCard(descriptor, { onAction });
    expect(element).not.toBeNull();

    const { getByText } = render(element!);
    fireEvent.press(getByText('完成'));

    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'agenda.complete' }),
      expect.objectContaining({ type: 'vitals' }),
    );
  });

  it('removes both write-intent actions when either sibling reaches a terminal state', () => {
    const descriptor = {
      type: 'medication_draft',
      data: { items: [{ medication_name: '伊托必利' }] },
      actions: [
        {
          id: 'confirm-medication-42',
          label: '确认记录',
          action: 'write_intent.confirm',
          endpoint: '/write-intents/42/confirm',
          requires_manual_confirm: true,
          ...MEDICATION_WRITE_POLICY,
          payload: { write_intent_id: 42 },
        },
        {
          id: 'dismiss-medication-42',
          label: '取消记录',
          action: 'write_intent.dismiss',
          endpoint: '/write-intents/42/dismiss',
          requires_manual_confirm: true,
          ...MEDICATION_WRITE_POLICY,
          payload: { write_intent_id: 42 },
        },
      ],
    } as any;

    const element = renderCard(descriptor, {
      onAction: jest.fn(),
      actionStateByKey: { 'confirm-medication-42': 'done' },
    });
    const { queryByText } = render(element!);

    expect(queryByText('确认记录')).toBeNull();
    expect(queryByText('取消记录')).toBeNull();
  });

  it('keeps card action touch targets at least 44 points high', () => {
    const descriptor = {
      type: 'medication_draft',
      data: { items: [{ medication_name: '伊托必利' }] },
      actions: [{
        id: 'confirm-medication-42',
        label: '确认记录',
        action: 'write_intent.confirm',
        endpoint: '/write-intents/42/confirm',
        requires_manual_confirm: true,
        ...MEDICATION_WRITE_POLICY,
        payload: { write_intent_id: 42 },
      }],
    } as any;

    const element = renderCard(descriptor, { onAction: jest.fn() });
    const { getByLabelText } = render(element!);
    const button = getByLabelText('确认记录');

    expect(button.props.style).toEqual(expect.arrayContaining([
      expect.objectContaining({ minHeight: 44 }),
    ]));
  });

  it('rejects write-intent actions outside the medication draft contract', () => {
    const r = renderServerCards([
      {
        type: 'vitals',
        data: {},
        actions: [
          {
            label: '确认记录',
            action: 'write_intent.confirm',
            endpoint: '/write-intents/42/confirm',
            requires_manual_confirm: true,
            ...WRITE_INTENT_POLICY,
            payload: { write_intent_id: 42 },
            confirmation: {
              title: '记录 30 个俯卧撑？',
              detail: '将写入今天的运动记录',
              confirm_label: '确认记录',
              cancel_label: '再看看',
            },
            optimistic: true,
          },
        ],
      } as any,
    ]);

    expect(r[0].actions).toEqual([]);
  });

  it('accepts only exact medication capability, intent id, and endpoint metadata', () => {
    const safe = {
      label: '确认记录',
      action: 'write_intent.confirm',
      endpoint: '/write-intents/42/confirm',
      requires_manual_confirm: true,
      ...WRITE_INTENT_POLICY,
      capability_id: 'medication_draft.v1',
      payload: { write_intent_id: 42 },
    } as any;
    const cards = renderServerCards([
      { type: 'medication_draft', data: {}, actions: [safe] } as any,
      {
        type: 'medication_draft',
        data: {},
        actions: [
          { ...safe, capability_id: 'anything.v99' },
          { ...safe, endpoint: undefined },
          { ...safe, endpoint: '/write-intents/43/confirm' },
          { ...safe, payload: { id: 42 } },
        ],
      } as any,
    ]);

    expect(cards[0].actions).toHaveLength(1);
    expect(cards[1].actions).toEqual([]);
  });

  it('renders disabled card actions without dispatching them', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'vitals',
      data: { sleep: '8h' },
      actions: [
        {
          id: 'complete-missing-source',
          label: '完成',
          action: 'agenda.complete',
          endpoint: '/agenda/complete',
          requires_manual_confirm: true,
          ...RUNTIME_AGENDA_WRITE_POLICY,
          disabled_reason: '缺少可完成的行动来源',
          payload: {},
        },
      ],
    } as any;

    const element = renderCard(descriptor, { onAction });
    expect(element).not.toBeNull();

    const { getByText } = render(element!);
    fireEvent.press(getByText('完成'));

    expect(onAction).not.toHaveBeenCalled();
    expect(getByText('缺少可完成的行动来源')).toBeTruthy();
  });

  it('renders in-flight card actions as disabled execution feedback', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'vitals',
      data: { sleep: '8h' },
      actions: [
        {
          id: 'complete-now',
          label: '完成',
          action: 'agenda.complete',
          endpoint: '/agenda/complete',
          requires_manual_confirm: true,
          ...RUNTIME_AGENDA_WRITE_POLICY,
          payload: {
            source: { object_type: 'health_protocol', object_id: 7 },
          },
        },
      ],
    } as any;

    const element = renderCard(descriptor, {
      onAction,
      actionStateByKey: { 'complete-now': 'running' },
    } as any);
    expect(element).not.toBeNull();

    const { getByText } = render(element!);
    fireEvent.press(getByText('执行中'));

    expect(onAction).not.toHaveBeenCalled();
  });

  it('renders completed diet record actions as recorded feedback', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'diet_draft',
      data: { food_items: '鸡胸肉 200g', meal_type: 'lunch' },
      actions: [
        {
          id: 'confirm-diet',
          label: '确认记录',
          action: 'diet_record.create',
          endpoint: '/diet/records',
          requires_manual_confirm: true,
          ...DIET_WRITE_POLICY,
          payload: { record: { food_items: '鸡胸肉 200g', meal_type: 'lunch' } },
        },
      ],
    } as any;

    const element = renderCard(descriptor, {
      onAction,
      actionStateByKey: { 'confirm-diet': 'done' },
    } as any);
    expect(element).not.toBeNull();

    const { getByText, queryByText } = render(element!);
    // 已记录态: 标题「午餐已记录」+ hero 勾图标; 不再有独立「已写入今日饮食」标题行。
    expect(getByText('午餐已记录')).toBeTruthy();
    // action-bar 的 done 态「已记录」按钮被 registry 隐藏, 卡内也不再有「已记录」文本。
    expect(queryByText('已记录')).toBeNull();

    expect(onAction).not.toHaveBeenCalled();
  });

  it('drops diet draft cards that are actually delete or undo intents', () => {
    const descriptor = {
      type: 'diet_draft',
      data: {
        meal_type: 'dinner',
        food_items: '我刚才不小心删除了',
        calories: 0,
        protein: 0,
        carbs: 0,
        fat: 0,
      },
      actions: [
        {
          id: 'confirm-delete-as-diet',
          label: '确认记录',
          action: 'diet_record.create',
          endpoint: '/diet/records',
          requires_manual_confirm: true,
          ...DIET_WRITE_POLICY,
          payload: {
            record: {
              meal_type: 'dinner',
              food_items: '我刚才不小心删除了',
            },
          },
        },
      ],
    } as any;

    expect(renderCard(descriptor, { onAction: jest.fn() })).toBeNull();
    expect(renderServerCards([descriptor])).toEqual([]);
    expect(renderCard({
      ...descriptor,
      data: {
        ...descriptor.data,
        food_items: '恢复刚才误删的晚餐',
      },
    }, { onAction: jest.fn() })).toBeNull();
  });

  it('shows in-card completion feedback after a diet draft is recorded', () => {
    const descriptor = {
      type: 'diet_draft',
      data: {
        food_items: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
        meal_type: 'lunch',
        calories: 770,
        protein: 30,
        carbs: 70,
        fat: 17,
        suggestions: ['晚餐优先补 40g 蛋白'],
        post_meal_walk: { recommended: true, minutes: 10 },
      },
      actions: [
        {
          id: 'confirm-diet-draft',
          label: '确认记录',
          action: 'diet_record.create',
          endpoint: '/diet/records',
          requires_manual_confirm: true,
          ...DIET_WRITE_POLICY,
          payload: {
            record: {
              food_items: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
              meal_type: 'lunch',
              calories: 770,
              protein: 30,
              carbs: 70,
              fat: 17,
            },
          },
        },
      ],
    } as any;

    const element = renderCard(descriptor, {
      actionStateByKey: { 'confirm-diet-draft': 'done' },
    } as any);
    expect(element).not.toBeNull();

    const { getByText } = render(element!);
    // 已记录态: 标题「午餐已记录」; 卡路里/营养在 hero + 网格; 下一步 + 帮助文案保留。
    expect(getByText('午餐已记录')).toBeTruthy();
    expect(getByText('kcal', { exact: false })).toBeTruthy();
    expect(getByText('蛋白质')).toBeTruthy();
    expect(getByText('已进入今日饮食进度')).toBeTruthy();
    expect(getByText('今日饮食打卡')).toBeTruthy();
    expect(getByText('小巴生成')).toBeTruthy();
    expect(getByText('可直接分享至微信 / 小红书')).toBeTruthy();
    expect(getByText('下一步: 餐后轻走 10 分钟')).toBeTruthy();
    expect(getByText('可在记录页继续修正,小巴会把这餐纳入今日饮食进度。')).toBeTruthy();
  });

  it('opens an inline editor for an already recorded diet card', () => {
    const descriptor = {
      type: 'diet_draft',
      data: {
        recorded: true,
        record_id: 805,
        food_items: '番茄炒蛋面 1 碗',
        meal_type: 'lunch',
        calories: 420,
        protein: 16,
        carbs: 65,
        fat: 10,
      },
      actions: [{
        id: 'adjust-record',
        label: '调整记录',
        action: 'ui.inline.expand',
        payload: {
          target: 'adjust_record',
          patch: {
            expanded_sections: ['adjust_record'],
            adjust_record: {
              record_id: 805,
              meal_type: 'lunch',
              food_items: '番茄炒蛋面 1 碗',
              calories: 420,
              protein: 16,
              carbs: 65,
              fat: 10,
            },
          },
        },
        style: 'secondary',
      }],
    } as any;

    const element = renderCard(descriptor, { onAction: jest.fn() });
    expect(element).not.toBeNull();
    const { getByText, getByTestId } = render(element!);

    fireEvent.press(getByText('调整记录'));

    expect(getByTestId('diet-adjust-inline-editor')).toBeTruthy();
    expect(getByText('保存修正')).toBeTruthy();
  });

  it('expands next-meal guidance inside a diet draft card without dispatching an action', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'diet_draft',
      data: {
        food_items: '煎牛肉能量碗 + 姜黄鲜柠维C茶',
        meal_type: 'lunch',
        calories: 770,
        protein: 30,
        carbs: 70,
        fat: 17,
        next_meal_detail: {
          title: '下一餐建议',
          summary: '下一餐优先补足蛋白和蔬菜,避免连续高油高糖。',
          context: '基于本餐营养估算和今日饮食闭环生成。',
          options: [
            '鱼/鸡胸/瘦牛肉 150-200g + 熟蔬菜 + 半份主食',
            '豆腐/鸡蛋 + 希腊酸奶或牛奶,补足蛋白缺口',
          ],
          rationale: ['这餐已有明确热量和蛋白估算。'],
          continue_prompt: '基于这餐和今天目标,帮我安排下一餐',
        },
      },
      actions: [
        {
          id: 'expand-next-meal',
          label: '看下一餐建议',
          action: 'ui.inline.expand',
          payload: {
            target: 'diet_draft',
            patch: {
              expanded_sections: ['next_meal'],
              next_meal_detail: {
                title: '下一餐建议',
                summary: '下一餐优先补足蛋白和蔬菜,避免连续高油高糖。',
                context: '基于本餐营养估算和今日饮食闭环生成。',
                options: [
                  '鱼/鸡胸/瘦牛肉 150-200g + 熟蔬菜 + 半份主食',
                  '豆腐/鸡蛋 + 希腊酸奶或牛奶,补足蛋白缺口',
                ],
                rationale: ['这餐已有明确热量和蛋白估算。'],
                continue_prompt: '基于这餐和今天目标,帮我安排下一餐',
              },
            },
          },
          style: 'secondary',
        },
      ],
    } as any;

    const element = renderCard(descriptor, { onAction });
    expect(element).not.toBeNull();

    const { getByText, queryByText } = render(element!);
    expect(queryByText('鱼/鸡胸/瘦牛肉 150-200g + 熟蔬菜 + 半份主食')).toBeNull();

    fireEvent.press(getByText('看下一餐建议'));

    expect(getByText('下一餐建议')).toBeTruthy();
    expect(getByText('下一餐优先补足蛋白和蔬菜,避免连续高油高糖。')).toBeTruthy();
    expect(getByText('鱼/鸡胸/瘦牛肉 150-200g + 熟蔬菜 + 半份主食')).toBeTruthy();
    expect(getByText('基于这餐和今天目标,帮我安排下一餐')).toBeTruthy();
    expect(onAction).not.toHaveBeenCalled();
  });

  it('renders medical exam import result cards from runtime skills', () => {
    const r = renderCard({
      type: 'medical_exam_import_result',
      data: {
        exam_id: 42,
        items_count: 28,
        abnormal_count: 3,
        source: 'pdf',
        review_required: true,
      },
    });
    expect(r).not.toBeNull();
  });

  it('renders runtime agenda cards from backend runtime projection', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'runtime_agenda',
      data: {
        presentation_mode: 'horizon',
        generated_by: 'rolling_health_runtime_v1',
        horizon_days: 7,
        next_action: {
          title: '晚餐后步行 15 分钟',
          kind: 'movement',
          time_window: 'evening',
          priority_tier: 'P1',
          current_state_summary: '晚餐后是今天最短的代谢干预窗口。',
          replan_reason: 'today_smart_rank',
          verification_metrics: ['post_meal_walk_completed', 'waist_cm', 'hrv'],
          verification_window_days: 7,
        },
        days: [
          { date: '2026-06-28', next_action_title: '晚餐后步行 15 分钟', items_count: 1 },
          { date: '2026-06-29', next_action_title: '晨间补水', items_count: 2 },
        ],
        safety_boundary: '这是健康管理行动建议,不替代医生诊断。',
      },
      actions: [
        {
          id: 'open-runtime-agenda',
          label: '查看完整计划',
          action: 'route.open',
          payload: { route: '/agenda' },
          style: 'primary',
        },
      ],
    } as any;
    const r = renderCard(descriptor, { onAction });
    expect(r).not.toBeNull();

    const { getByText, queryByText } = render(r!);
    expect(getByText('本周验证节奏')).toBeTruthy();
    expect(getByText('晚餐后步行 15 分钟')).toBeTruthy();
    expect(queryByText('围绕当前重点动态重排')).toBeNull();
    expect(getByText('基于今日状态重排')).toBeTruthy();
    expect(getByText('晚间')).toBeTruthy();
    expect(getByText('腰围')).toBeTruthy();
    expect(getByText('HRV')).toBeTruthy();
    expect(() => getByText('today_smart_rank')).toThrow();
    expect(() => getByText('waist_cm')).toThrow();
    fireEvent.press(getByText('查看完整计划'));
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'route.open' }),
      expect.objectContaining({ type: 'runtime_agenda' }),
    );
  });

  it('renders operating review cards from backend prediction backtest', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'operating_review',
      data: {
        window_days: 7,
        start_date: '2026-06-22',
        end_date: '2026-06-28',
        execution: {
          total_events: 4,
          completed_events: 3,
          completion_rate: 0.75,
        },
        metrics: [
          { metric: 'waist_cm', current: 94.8, delta: -1.2, current_date: '2026-06-28' },
        ],
        prediction_backtest: {
          status: 'ready',
          ready_candidate_count: 1,
          summary: { met: 1, not_met: 0, inconclusive: 0 },
          results: [
            {
              prediction_id: 'pred-waist-7d',
              action_title: '累计 35-45 分钟中等强度活动',
              metric: 'waist_cm',
              horizon_days: 7,
              observed_delta: -1.2,
              verdict: 'met',
              confidence_after: 'medium',
            },
          ],
          boundary: '预测回测只比较预期信号与窗口内实际变化, 属观察性复盘, 不证明单个行动造成指标变化。',
        },
        causal_memory: {
          notes: [{ metric: 'hrv', text: '晚餐提前之后 HRV 改善(相关非因果)' }],
          claim_boundary: '事件先于指标变化的时序相关,非证明因果;不替代医学结论。',
        },
      },
      actions: [
        {
          id: 'open-operating-review',
          label: '查看复盘详情',
          action: 'route.open',
          payload: { route: '/my-progress' },
          style: 'primary',
        },
      ],
    } as any;
    const r = renderCard(descriptor, { onAction });
    expect(r).not.toBeNull();

    const { getByText, queryByText } = render(r!);
    expect(getByText('7天复盘')).toBeTruthy();
    // badge 为中文"复盘",不再泄漏英文 "Review"
    expect(getByText('复盘')).toBeTruthy();
    expect(queryByText('Review')).toBeNull();
    expect(getByText('完成率 75%')).toBeTruthy();
    expect(getByText('预测回测: 1/1 支持')).toBeTruthy();
    expect(getByText(/累计 35-45 分钟中等强度活动/)).toBeTruthy();
    expect(getByText(/不证明单个行动造成指标变化/)).toBeTruthy();
    fireEvent.press(getByText('查看复盘详情'));
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'route.open' }),
      expect.objectContaining({ type: 'operating_review' }),
    );
  });

  it('operating review with 0/0 actions shows accumulating state, not a misleading 0%', () => {
    const descriptor = {
      type: 'operating_review',
      data: {
        window_days: 30,
        start_date: '2026-06-05',
        end_date: '2026-07-04',
        execution: {
          total_events: 0,
          completed_events: 0,
          completion_rate: 0,
        },
        // 真实预测指标 chips 应保留
        metrics: [
          { metric: 'weight', delta: 2.1 },
          { metric: 'sleep_score', delta: 7 },
          { metric: 'hrv', delta: -15 },
        ],
      },
    } as any;
    const r = renderCard(descriptor);
    expect(r).not.toBeNull();

    const { getByText, queryByText } = render(r!);
    // 平静的积累态文案取代 0% 大数字
    expect(getByText('行动数据积累中')).toBeTruthy();
    expect(getByText('首个 30 天复盘将在有行动记录后生成')).toBeTruthy();
    // 误导性的 0% / 0/0 hero 不再出现
    expect(queryByText('完成率 0%')).toBeNull();
    expect(queryByText(/0\/0 个行动/)).toBeNull();
    // 真实预测 chips 仍然渲染
    expect(getByText('体重 +2.1')).toBeTruthy();
    expect(getByText('睡眠评分 +7')).toBeTruthy();
    expect(getByText('HRV -15')).toBeTruthy();
    // badge 仍为中文
    expect(getByText('复盘')).toBeTruthy();
  });

  it('renders metric chart cards from backend health data', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'metric_chart',
      data: {
        metric: 'hrv',
        title: '最近半年 HRV',
        unit: 'ms',
        start_date: '2025-12-29',
        end_date: '2026-06-30',
        coverage: { days_with_data: 181, days_in_window: 184 },
        latest: { date: '2026-06-30', value: 56.0, source: 'apple-watch' },
        summary: {
          avg: 57.3,
          last_7d_avg: 48.8,
          last_30d_avg: 50.9,
          prev_30d_avg: 57.5,
          last_30_vs_prev_30_delta: -6.6,
        },
        series: [
          { date: '2026-06-24', value: 52.0, rolling_7d: 54.0, source: 'garmin' },
          { date: '2026-06-25', value: 49.0, rolling_7d: 53.0, source: 'garmin' },
          { date: '2026-06-30', value: 56.0, rolling_7d: 48.8, source: 'apple-watch' },
        ],
        boundary: 'HRV 趋势仅用于健康管理参考, 不替代诊断或治疗。',
      },
      actions: [
        {
          id: 'open-hrv-history',
          label: '查看HRV历史',
          action: 'route.open',
          payload: { route: '/indicator-history?type=hrv' },
          style: 'secondary',
        },
      ],
    } as any;
    const r = renderCard(descriptor, { onAction });
    expect(r).not.toBeNull();

    const { getByText } = render(r!);
    expect(getByText('最近半年 HRV')).toBeTruthy();
    expect(getByText('56.0ms')).toBeTruthy();
    expect(getByText('181/184 天')).toBeTruthy();
    expect(getByText('近30天 -6.6ms')).toBeTruthy();
    expect(getByText(/不替代诊断或治疗/)).toBeTruthy();
    fireEvent.press(getByText('查看HRV历史'));
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'route.open' }),
      expect.objectContaining({ type: 'metric_chart' }),
    );
  });

  it('renders non-HRV metric chart cards with metric-specific units and actions', () => {
    const onAction = jest.fn();
    const descriptor = {
      type: 'metric_chart',
      data: {
        metric: 'weight',
        label: '体重',
        title: '最近30天 体重',
        unit: 'kg',
        start_date: '2026-06-01',
        end_date: '2026-06-30',
        coverage: { days_with_data: 3, days_in_window: 31 },
        latest: { date: '2026-06-30', value: 73.8, source: 'manual' },
        summary: {
          avg: 74.1,
          last_7d_avg: 73.9,
          last_30d_avg: 74.1,
          prev_30d_avg: 74.8,
          last_30_vs_prev_30_delta: -0.7,
        },
        series: [
          { date: '2026-06-26', value: 74.5, rolling_7d: 74.5, source: 'manual' },
          { date: '2026-06-28', value: 74.0, rolling_7d: 74.3, source: 'manual' },
          { date: '2026-06-30', value: 73.8, rolling_7d: 74.1, source: 'manual' },
        ],
        boundary: '体重 趋势仅用于健康管理参考, 不替代诊断或治疗。',
      },
      actions: [
        {
          id: 'open-weight-history',
          label: '查看体重历史',
          action: 'route.open',
          payload: { route: '/indicator-history?type=weight' },
          style: 'secondary',
        },
      ],
    } as any;

    const r = renderCard(descriptor, { onAction });
    expect(r).not.toBeNull();

    const { getByText } = render(r!);
    expect(getByText('最近30天 体重')).toBeTruthy();
    expect(getByText('73.8kg')).toBeTruthy();
    expect(getByText('3/31 天')).toBeTruthy();
    expect(getByText('近30天 -0.7kg')).toBeTruthy();
    fireEvent.press(getByText('查看体重历史'));
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'route.open', payload: { route: '/indicator-history?type=weight' } }),
      expect.objectContaining({ type: 'metric_chart' }),
    );
  });

  it('renders generic metric_line_chart dynamic UI cards', () => {
    const descriptor = {
      type: 'metric_line_chart',
      data: {
        schema: 'reva.metric_line_chart.v1',
        component: 'metric_line_chart',
        metric: 'resting_hr',
        range: '6m',
        title: '静息心率趋势',
        unit: 'bpm',
        x: ['06-29', '06-30'],
        series: [
          { name: 'Apple Watch 静息心率', role: 'device', points: [62, 58] },
          { name: '7日滚动均值', role: 'avg_7d', points: [61, 60] },
        ],
        annotations: [{ x: '06-30', label: '最新 58 bpm · Apple Watch', kind: 'latest' }],
        source: 'garmin',
        data_note: '基于 2 天真实数据',
      },
    } as any;

    const r = renderCard(descriptor);
    expect(r).not.toBeNull();

    const { getByText } = render(r!);
    expect(getByText('静息心率趋势')).toBeTruthy();
    expect(getByText('Apple Watch 静息心率')).toBeTruthy();
    expect(getByText('7日滚动均值')).toBeTruthy();
    expect(getByText(/最新 58 bpm/)).toBeTruthy();
  });

  it('renders metric_empty_state dynamic UI cards', () => {
    const descriptor = {
      type: 'metric_empty_state',
      data: {
        schema: 'reva.metric_empty_state.v1',
        component: 'metric_empty_state',
        metric: 'blood_glucose',
        range: '7d',
        title: '血糖数据不足',
        message: '暂无足够数据，至少需要 3 天真实记录后才能生成趋势图。',
        suggestions: ['同步 HealthKit 或可穿戴设备数据', '补录最近几天的关键指标'],
        boundary: '仅用于健康管理参考，不替代诊断或治疗。',
      },
    } as any;

    const r = renderCard(descriptor);
    expect(r).not.toBeNull();

    const { getByText } = render(r!);
    expect(getByText('血糖数据不足')).toBeTruthy();
    expect(getByText(/至少需要 3 天真实记录/)).toBeTruthy();
    expect(getByText('同步 HealthKit 或可穿戴设备数据')).toBeTruthy();
  });

  it('cards_group 1 张子卡 → 直接渲染, 不包 grid', () => {
    const r = renderCard({
      type: 'cards_group',
      data: { cards: [{ type: 'vitals', data: { sleep: '8h' } }] },
    });
    expect(r).not.toBeNull();
  });

  it('cards_group 2 张子卡 → wrapper View', () => {
    const r = renderCard({
      type: 'cards_group',
      data: {
        cards: [
          { type: 'vitals', data: { sleep: '8h' } },
          { type: 'weight', data: { current_kg: 72 } },
        ],
      },
    });
    expect(r).not.toBeNull();
  });

  it('cards_group preserves child card actions so multi-card replies stay actionable', () => {
    const onAction = jest.fn();
    const r = renderCard({
      type: 'cards_group',
      data: {
        cards: [
          {
            type: 'runtime_agenda',
            data: { next_action: { title: '晚餐后步行 15 分钟' } },
            actions: [
              {
                id: 'open-runtime',
                label: '查看7天计划',
                action: 'route.open',
                payload: { route: '/agenda' },
                style: 'primary',
              },
            ],
          },
          {
            type: 'operating_review',
            data: {
              window_days: 7,
              execution: { total_events: 1, completed_events: 1, completion_rate: 1 },
            },
            actions: [
              {
                id: 'open-review',
                label: '查看复盘详情',
                action: 'route.open',
                payload: { route: '/my-progress' },
                style: 'primary',
              },
            ],
          },
        ],
      },
    }, { onAction });

    expect(r).not.toBeNull();
    const { getByText } = render(r!);

    fireEvent.press(getByText('查看7天计划'));
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'route.open', payload: { route: '/agenda' } }),
      expect.objectContaining({ type: 'runtime_agenda' }),
    );

    fireEvent.press(getByText('查看复盘详情'));
    expect(onAction).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'route.open', payload: { route: '/my-progress' } }),
      expect.objectContaining({ type: 'operating_review' }),
    );
  });

  it('cards_group 全是未知 type → null', () => {
    const r = renderCard({
      type: 'cards_group',
      data: { cards: [{ type: 'aaa', data: {} }, { type: 'bbb', data: {} }] },
    });
    expect(r).toBeNull();
  });

  it('cards_group 无 data.cards → null', () => {
    expect(renderCard({ type: 'cards_group', data: {} })).toBeNull();
  });
});

describe('renderServerCards 防御', () => {
  it('null/undefined/[] → []', () => {
    expect(renderServerCards()).toEqual([]);
    expect(renderServerCards(null)).toEqual([]);
    expect(renderServerCards([])).toEqual([]);
  });

  it('过滤未知 type', () => {
    const r = renderServerCards([
      { type: 'vitals', data: {} },
      { type: 'runtime_agenda', data: { next_action: { title: '今日重点' } } },
      { type: 'fake', data: {} },
      { type: 'sleep', data: {} },
    ]);
    expect(r.map((c) => c.type)).toEqual(['vitals', 'runtime_agenda', 'sleep']);
  });

  it('preserves allowed server card actions for chat dispatch', () => {
    const r = renderServerCards([
      {
        type: 'vitals',
        data: {},
        actions: [
          {
            label: '完成',
            action: 'agenda.complete',
            endpoint: '/agenda/complete',
            requires_manual_confirm: true,
            ...RUNTIME_AGENDA_WRITE_POLICY,
            payload: { source: { object_type: 'health_protocol', object_id: 7 } },
          },
        ],
      } as any,
    ]);

    expect(r[0]).toEqual(expect.objectContaining({
      type: 'vitals',
      actions: [expect.objectContaining({ action: 'agenda.complete' })],
    }));
  });

  it('preserves manual-confirm diet record create actions', () => {
    const r = renderServerCards([
      {
        type: 'diet_draft',
        data: { food_items: '鸡蛋 2 个', meal_type: 'breakfast' },
        actions: [
          {
            label: '确认记录',
            action: 'diet_record.create',
            endpoint: '/diet/records',
            requires_manual_confirm: true,
            ...DIET_WRITE_POLICY,
            payload: {
              record: { food_items: '鸡蛋 2 个', meal_type: 'breakfast', protein: 12 },
            },
          },
          {
            label: '静默写入',
            action: 'diet_record.create',
            endpoint: '/diet/records',
            payload: {
              record: { food_items: '鸡蛋 2 个', meal_type: 'breakfast' },
            },
          },
        ],
      } as any,
    ]);

    expect(r[0].actions).toEqual([
      expect.objectContaining({
        action: 'diet_record.create',
        endpoint: '/diet/records',
        requires_manual_confirm: true,
      }),
    ]);
  });

  it('filters unsafe write actions before they reach the chat UI', () => {
    const r = renderServerCards([
      {
        type: 'vitals',
        data: {},
        actions: [
          {
            label: '缺少人工确认的完成按钮',
            action: 'agenda.complete',
            endpoint: '/agenda/complete',
            payload: { source: { object_type: 'health_protocol', object_id: 7 } },
          },
          {
            label: '打开记录页',
            action: 'route.open',
            payload: { route: '/(tabs)/record' },
          },
          {
            label: '确认写入',
            action: 'write_intent.confirm',
            endpoint: '/write-intents/42/confirm',
            requires_manual_confirm: true,
            ...WRITE_INTENT_POLICY,
            payload: { write_intent_id: 42 },
          },
        ],
      } as any,
    ]);

    expect(r[0].actions).toEqual([
      expect.objectContaining({ action: 'route.open' }),
    ]);
  });

  it('filters unsafe route actions before they reach the chat UI', () => {
    const r = renderServerCards([
      {
        type: 'vitals',
        data: {},
        actions: [
          {
            label: '打开外部站点',
            action: 'route.open',
            payload: { route: '//example.test/path' },
          },
          {
            label: '打开异常路径',
            action: 'route.open',
            payload: { route: '/(tabs)/chat\ninject' },
          },
          {
            label: '打开小巴',
            action: 'route.open',
            payload: { route: '/(tabs)/chat?prompt=hrv' },
          },
        ],
      } as any,
    ]);

    expect(r[0].actions).toEqual([
      expect.objectContaining({
        action: 'route.open',
        payload: { route: '/(tabs)/chat?prompt=hrv' },
      }),
    ]);
  });

  it('非数组 → []', () => {
    expect(renderServerCards({} as any)).toEqual([]);
    expect(renderServerCards('string' as any)).toEqual([]);
  });
});
