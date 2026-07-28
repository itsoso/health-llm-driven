import api from '../api';
import {
  durationBucket,
  emitClientEvent,
  sanitizeClientEventMeta,
} from '../clientEvents';

jest.mock('../api', () => ({
  __esModule: true,
  default: { post: jest.fn().mockResolvedValue({ data: { ok: true } }) },
}));

const mockPost = api.post as jest.Mock;

describe('client reliability events', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it.each([
    [0, 'lt_1s'],
    [999, 'lt_1s'],
    [1_000, '1_3s'],
    [2_999, '1_3s'],
    [3_000, '3_10s'],
    [9_999, '3_10s'],
    [10_000, '10_30s'],
    [29_999, '10_30s'],
    [30_000, 'gte_30s'],
  ])('buckets a %d ms operation as %s', (elapsedMs, expected) => {
    expect(durationBucket(10_000, 10_000 + (elapsedMs as number))).toBe(expected);
  });

  it('removes content, audio, URI and resource identifiers from reliability metadata', () => {
    expect(sanitizeClientEventMeta('voice_input_terminal', {
      phase: 'completed',
      duration_bucket: '1_3s',
      action_type: 'dictation',
      content: '我的健康隐私',
      transcript: '我的健康隐私',
      audio: 'base64-secret',
      uri: 'file:///private/voice.m4a',
      resource_id: 42,
    })).toEqual({
      phase: 'completed',
      duration_bucket: '1_3s',
      action_type: 'dictation',
    });
  });

  it('drops invalid reliability values instead of forwarding arbitrary strings', () => {
    expect(sanitizeClientEventMeta('write_receipt_terminal', {
      phase: 'not-a-phase',
      duration_bucket: 'forever',
      action_type: 'diet.update\nsecret',
      error_code: 'x'.repeat(100),
      verified: 'yes',
    })).toEqual({});
  });

  it.each([
    ['verified', false],
    ['unverified', true],
    ['failed', true],
  ])('drops contradictory write receipt phase %s / verified %s', (phase, verified) => {
    expect(sanitizeClientEventMeta('write_receipt_terminal', {
      phase,
      duration_bucket: '1_3s',
      action_type: 'diet.update',
      verified,
    })).toEqual({});
  });

  it('posts only sanitized reliability metadata', async () => {
    await emitClientEvent('write_receipt_terminal', {
      phase: 'verified',
      duration_bucket: '3_10s',
      action_type: 'diet.update',
      verified: true,
      content: '不能上传',
      resource_id: 'meal-123',
    });

    expect(mockPost).toHaveBeenCalledWith('/client-events', {
      event_name: 'write_receipt_terminal',
      meta: {
        phase: 'verified',
        duration_bucket: '3_10s',
        action_type: 'diet.update',
        verified: true,
      },
    });
  });

  it('sanitizes queued-turn telemetry to stable non-content fields', () => {
    expect(sanitizeClientEventMeta('chat_turn_queued', {
      surface: 'mobile',
      channel: 'typed',
      queue_depth_at_submit: 2,
      content: '用户健康隐私',
      turn_id: 'private-turn-id',
    })).toEqual({
      surface: 'mobile',
      channel: 'typed',
      queue_depth_at_submit: 2,
    });
  });

  it('drops an invalid queued-turn telemetry payload instead of sending partial data', () => {
    expect(sanitizeClientEventMeta('chat_turn_queued', {
      surface: 'mobile',
      channel: 'typed',
      queue_depth_at_submit: 99,
      transcript: '用户健康隐私',
    })).toEqual({});
  });

  it('posts queued-turn telemetry without leaking turn content', async () => {
    await emitClientEvent('chat_turn_queued', {
      surface: 'mobile',
      channel: 'voice',
      queue_depth_at_submit: 1,
      transcript: '用户健康隐私',
    });

    expect(mockPost).toHaveBeenCalledWith('/client-events', {
      event_name: 'chat_turn_queued',
      meta: {
        surface: 'mobile',
        channel: 'voice',
        queue_depth_at_submit: 1,
      },
    });
  });

  it('keeps chat attachment telemetry content-free and identifier-free', () => {
    expect(sanitizeClientEventMeta('chat_attachment_terminal', {
      phase: 'accepted',
      stage: 'server_accept',
      image_count: 3,
      duration_bucket: '3_10s',
      payload_bucket: '1_4mb',
      content: '晚餐照片',
      uri: 'file:///private/chat-drafts/meal.jpeg',
      base64: 'private-image-bytes',
      turn_id: 'private-turn-id',
    })).toEqual({
      phase: 'accepted',
      stage: 'server_accept',
      image_count: 3,
      duration_bucket: '3_10s',
      payload_bucket: '1_4mb',
    });
  });

  it('drops invalid chat attachment telemetry instead of forwarding partial data', () => {
    expect(sanitizeClientEventMeta('chat_attachment_terminal', {
      phase: 'completed',
      stage: 'upload',
      image_count: 10,
      duration_bucket: 'forever',
      payload_bucket: 'huge',
      error_code: 'private error text',
    })).toEqual({});
  });

  it('drops identifier-shaped attachment error codes outside the fixed enum', () => {
    expect(sanitizeClientEventMeta('chat_attachment_terminal', {
      phase: 'failed',
      stage: 'server_accept',
      image_count: 1,
      duration_bucket: '1_3s',
      payload_bucket: 'lt_256kb',
      error_code: 'turn_private_identifier',
    })).toEqual({
      phase: 'failed',
      stage: 'server_accept',
      image_count: 1,
      duration_bucket: '1_3s',
      payload_bucket: 'lt_256kb',
    });
  });

  it('keeps ASR quality metadata content-free for voice input tuning', async () => {
    await emitClientEvent('voice_asr_terminal', {
      phase: 'completed',
      duration_bucket: '1_3s',
      action_type: 'hold',
      provider: 'openai_whisper',
      confidence: 'medium',
      empty: false,
      transcript: '不能上传',
      audio: 'base64-secret',
    });

    expect(mockPost).toHaveBeenCalledWith('/client-events', {
      event_name: 'voice_asr_terminal',
      meta: {
        phase: 'completed',
        duration_bucket: '1_3s',
        action_type: 'hold',
        provider: 'openai_whisper',
        confidence: 'medium',
        empty: false,
      },
    });
  });

  it('keeps existing event metadata backward compatible', () => {
    const meta = { source: 'chat', has_image: false };
    expect(sanitizeClientEventMeta('chat_message_sent', meta)).toBe(meta);
  });

  it('keeps AIGC engagement telemetry content-free and identifier-free', () => {
    expect(sanitizeClientEventMeta('aigc_media_shared', {
      phase: 'completed',
      media_kind: 'video',
      share_target: 'wechat',
      job_id: 'private-job-id',
      prompt: '用户健康隐私',
      result_url: 'https://private.example/video.mp4',
    })).toEqual({
      phase: 'completed',
      media_kind: 'video',
      share_target: 'wechat',
    });
    expect(sanitizeClientEventMeta('aigc_media_played', {
      media_kind: 'video',
      job_id: 'private-job-id',
    })).toEqual({
      media_kind: 'video',
    });
  });

  it('keeps app update telemetry content-free and normalizes invalid values', () => {
    expect(sanitizeClientEventMeta('app_update_terminal', {
      phase: 'ready',
      duration_bucket: '3_10s',
      platform: 'ios',
      channel: 'production',
      runtime: '1.3.1',
      native_build: '190',
      update_id: '01234567-89ab-cdef-0123-456789abcdef',
      error_message: '用户的健康数据',
      health_record: 'private',
    })).toEqual({
      phase: 'ready',
      duration_bucket: '3_10s',
      platform: 'ios',
      channel: 'production',
      runtime: '1.3.1',
      native_build: '190',
      update_id: '01234567-89ab-cdef-0123-456789abcdef',
    });

    expect(sanitizeClientEventMeta('app_update_phase', {
      phase: 'downloaded',
      platform: 'iOS',
      update_id: 'file:///private/health.db',
    })).toEqual({});
  });

  it('posts app update terminal telemetry without leaking error text', async () => {
    await emitClientEvent('app_update_terminal', {
      phase: 'failed',
      duration_bucket: '10_30s',
      error_code: 'check_failed',
      error_message: 'token plan quota exhausted',
    });

    expect(mockPost).toHaveBeenCalledWith('/client-events', {
      event_name: 'app_update_terminal',
      meta: {
        phase: 'failed',
        duration_bucket: '10_30s',
        error_code: 'check_failed',
      },
    });
  });
});
