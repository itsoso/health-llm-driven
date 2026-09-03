import AsyncStorage from '@react-native-async-storage/async-storage';
import api from '../api';
import {
  durationBucket,
  emitClientEvent,
  flushClientEventOutbox,
  sanitizeClientEventMeta,
} from '../clientEvents';

jest.mock('../api', () => ({
  __esModule: true,
  default: { post: jest.fn().mockResolvedValue({ data: { ok: true } }) },
}));
jest.mock('../authStorageScope', () => ({
  getAuthStorageScope: jest.fn().mockResolvedValue('user-7'),
}));

const mockPost = api.post as jest.Mock;

describe('client reliability events', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockPost.mockReset();
    mockPost.mockResolvedValue({ data: { ok: true } });
    return AsyncStorage.clear();
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

  it('keeps only content-free agent turn milestone fields', () => {
    expect(sanitizeClientEventMeta('agent_turn_milestone', {
      phase: 'first_useful',
      duration_ms: 842,
      action_type: 'diet_record',
      has_image: false,
      content: '一个桃子',
      resource_id: 'diet-111',
      transcript: '不能上传',
    })).toEqual({
      phase: 'first_useful',
      duration_ms: 842,
      action_type: 'diet_record',
      has_image: false,
    });
  });

  it.each([
    'first_semantic_progress',
    'first_content_painted',
    'first_key_content',
    'first_interactive',
    'citations_received',
    'citations_painted',
  ])('accepts the content-free %s milestone', (phase) => {
    expect(sanitizeClientEventMeta('agent_turn_milestone', {
      phase,
      duration_ms: 1_240,
      action_type: 'generic',
      has_image: false,
      content: '帮我算我的 BMI',
    })).toEqual({
      phase,
      duration_ms: 1_240,
      action_type: 'generic',
      has_image: false,
    });
  });

  it('drops invalid agent turn milestone values as one atomic payload', () => {
    expect(sanitizeClientEventMeta('agent_turn_milestone', {
      phase: 'raw_reasoning',
      duration_ms: 300_001,
      action_type: 'diet_record\nprivate',
      has_image: 'no',
    })).toEqual({});
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

  it('persists an attachment terminal event when delivery fails', async () => {
    mockPost.mockRejectedValueOnce(new Error('offline'));

    await emitClientEvent('chat_attachment_terminal', {
      phase: 'accepted',
      stage: 'server_accept',
      image_count: 2,
      duration_bucket: '3_10s',
      payload_bucket: '1_4mb',
      content: 'private meal description',
    }, { eventKey: 'attachment-terminal-1' });

    const stored = await AsyncStorage.getItem('client-events:outbox:v1:user-7');
    expect(JSON.parse(stored || '[]')).toEqual([{
      eventKey: 'attachment-terminal-1',
      name: 'chat_attachment_terminal',
      meta: {
        phase: 'accepted',
        stage: 'server_accept',
        image_count: 2,
        duration_bucket: '3_10s',
        payload_bucket: '1_4mb',
      },
    }]);
  });

  it('recovers a corrupted outbox before persisting a new terminal event', async () => {
    await AsyncStorage.setItem('client-events:outbox:v1:user-7', '{not-json');
    mockPost.mockRejectedValueOnce(new Error('offline'));

    await emitClientEvent('chat_attachment_terminal', {
      phase: 'accepted',
      stage: 'server_accept',
      image_count: 1,
      duration_bucket: '1_3s',
      payload_bucket: 'lt_256kb',
    }, { eventKey: 'attachment-terminal-after-corruption' });

    const stored = await AsyncStorage.getItem('client-events:outbox:v1:user-7');
    expect(JSON.parse(stored || '[]')).toEqual([{
      eventKey: 'attachment-terminal-after-corruption',
      name: 'chat_attachment_terminal',
      meta: {
        phase: 'accepted',
        stage: 'server_accept',
        image_count: 1,
        duration_bucket: '1_3s',
        payload_bucket: 'lt_256kb',
      },
    }]);
  });

  it('retries a persisted attachment terminal event and removes it after acknowledgement', async () => {
    await AsyncStorage.setItem('client-events:outbox:v1:user-7', JSON.stringify([{
      eventKey: 'attachment-terminal-2',
      name: 'chat_attachment_terminal',
      meta: {
        phase: 'failed',
        stage: 'server_accept',
        image_count: 1,
        duration_bucket: '1_3s',
        payload_bucket: 'lt_256kb',
        error_code: 'server_not_accepted',
      },
    }]));

    await flushClientEventOutbox();

    expect(mockPost).toHaveBeenCalledWith('/client-events', {
      event_name: 'chat_attachment_terminal',
      event_key: 'attachment-terminal-2',
      meta: {
        phase: 'failed',
        stage: 'server_accept',
        image_count: 1,
        duration_bucket: '1_3s',
        payload_bucket: 'lt_256kb',
        error_code: 'server_not_accepted',
      },
    });
    expect(await AsyncStorage.getItem('client-events:outbox:v1:user-7')).toBeNull();
  });

  it('retains a persisted terminal event when the server resolves with ok false', async () => {
    await AsyncStorage.setItem('client-events:outbox:v1:user-7', JSON.stringify([{
      eventKey: 'attachment-terminal-not-persisted',
      name: 'chat_attachment_terminal',
      meta: {
        phase: 'accepted',
        stage: 'server_accept',
        image_count: 1,
        duration_bucket: '1_3s',
        payload_bucket: 'lt_256kb',
      },
    }]));
    mockPost.mockResolvedValueOnce({ data: { ok: false } });

    await flushClientEventOutbox();

    const stored = await AsyncStorage.getItem('client-events:outbox:v1:user-7');
    expect(JSON.parse(stored || '[]')).toHaveLength(1);
  });

  it('resolves a terminal emit after local persistence without waiting for network acknowledgement', async () => {
    let resolvePost: ((value: { data: { ok: boolean } }) => void) | undefined;
    mockPost.mockImplementationOnce(() => new Promise((resolve) => {
      resolvePost = resolve;
    }));

    await emitClientEvent('chat_attachment_terminal', {
      phase: 'accepted',
      stage: 'server_accept',
      image_count: 1,
      duration_bucket: '1_3s',
      payload_bucket: 'lt_256kb',
    }, { eventKey: 'attachment-terminal-local-first' });
    const storedBeforeNetworkAck = await AsyncStorage.getItem('client-events:outbox:v1:user-7');
    for (let index = 0; index < 10 && !resolvePost; index += 1) {
      await Promise.resolve();
    }

    expect(JSON.parse(storedBeforeNetworkAck || '[]')).toHaveLength(1);
    expect(resolvePost).toBeDefined();
    resolvePost?.({ data: { ok: true } });
    await flushClientEventOutbox();
  });

  it('deduplicates an attachment terminal event in the local outbox', async () => {
    mockPost.mockRejectedValue(new Error('offline'));
    const payload = {
      phase: 'accepted',
      stage: 'server_accept',
      image_count: 1,
      duration_bucket: '1_3s',
      payload_bucket: 'lt_256kb',
    };

    await emitClientEvent(
      'chat_attachment_terminal',
      payload,
      { eventKey: 'attachment-terminal-3' },
    );
    await emitClientEvent(
      'chat_attachment_terminal',
      payload,
      { eventKey: 'attachment-terminal-3' },
    );

    const stored = await AsyncStorage.getItem('client-events:outbox:v1:user-7');
    expect(JSON.parse(stored || '[]')).toHaveLength(1);
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

  it('keeps diet share terminal telemetry bounded and strips private meal data', () => {
    expect(sanitizeClientEventMeta('diet_share_terminal', {
      phase: 'completed',
      duration_ms: 1200,
      has_photo: true,
      share_target: 'xiaohongshu',
      image_uri: 'file:///private/photo.png',
      food_items: 'private meal',
      record_id: 88,
      calories: 520,
      server_total_ms: 800,
      food_count: 3,
      table_calibrated_count: 2,
      verified: true,
      corrected: true,
      error_code: 'beef_salad',
    })).toEqual({
      phase: 'completed',
      duration_ms: 1200,
      has_photo: true,
      share_target: 'xiaohongshu',
    });

    expect(sanitizeClientEventMeta('diet_share_terminal', {
      phase: 'failed',
      duration_ms: 1300,
      has_photo: true,
      share_target: 'generic',
      error_code: 'poster_share_failed',
    })).toEqual({
      phase: 'failed',
      duration_ms: 1300,
      has_photo: true,
      share_target: 'generic',
      error_code: 'poster_share_failed',
    });

    expect(sanitizeClientEventMeta('diet_share_terminal', {
      phase: 'cancelled',
      duration_ms: 900,
      has_photo: true,
      share_target: 'generic',
      image_uri: 'file:///private/cancelled.png',
    })).toEqual({
      phase: 'cancelled',
      duration_ms: 900,
      has_photo: true,
      share_target: 'generic',
    });
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
